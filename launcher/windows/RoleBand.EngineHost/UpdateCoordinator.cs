using System.Runtime.InteropServices;
using System.Text.Json;
using Windows.Management.Deployment;
using Windows.Networking.Connectivity;

namespace RoleBand.EngineHost;

/// <summary>Replaces this app's package; Windows may end this process while it does.</summary>
public interface IPackageDeployer
{
    /// <param name="downgrade">Register a lower version, to return to the previous one.</param>
    /// <param name="progress">Windows' own percentage of the install.</param>
    Task AddAsync(string package, bool downgrade, IProgress<int>? progress, CancellationToken cancellation);

    /// <summary>Where Windows' install of a release file stands, as its own deployment log says.</summary>
    /// <param name="packageName">The package's name, without version or publisher.</param>
    /// <param name="since">When the update began; earlier installs are not this one.</param>
    Task<InstallFinding> FindAsync(string packageName, string version, string file, DateTimeOffset since, CancellationToken cancellation);

    /// <summary>Asks Windows to open the app again once an install has closed it.</summary>
    void ReopenWhenReplaced();
}

/// <summary>An update command refused the step, with its reason and the kind of failure it reported.</summary>
/// <param name="Kind">"missing" when the release is no longer published, "offline", "space", or null.</param>
public sealed class UpdateRefused(string reason, string? kind) : IOException(reason)
{
    public string? Kind { get; } = kind;
}

/// <summary>The engine's `desktop.py update` commands, each answering one JSON object.</summary>
public interface IUpdateCommands
{
    /// <param name="lines">Told each line the command writes to stderr while it runs, such as a download's progress.</param>
    /// <param name="cancellation">Stops a download and every process it started. Every other command changes the journal or
    /// the database and runs to its end, since one stopped partway would leave them half-changed.</param>
    Task<JsonElement> RunAsync(IReadOnlyList<string> arguments, CancellationToken cancellation, Action<string>? lines = null);
}

public sealed class WindowsPackageDeployer : IPackageDeployer
{
    public async Task AddAsync(string package, bool downgrade, IProgress<int>? progress, CancellationToken cancellation)
    {
        var options = new AddPackageOptions
        {
            ForceAppShutdown = true, ForceTargetAppShutdown = true, ForceUpdateFromAnyVersion = downgrade,
        };
        var result = await new PackageManager().AddPackageByUriAsync(new Uri(package), options)
            .AsTask(cancellation, new Percentage(progress));
        if (result.ExtendedErrorCode is { } error)
            throw new IOException(result.ErrorText, error);
    }

    /// <summary>How far before the update began the deployment log is read, so the install's own start is in it.</summary>
    private static readonly TimeSpan LogMargin = TimeSpan.FromMinutes(5);

    public async Task<InstallFinding> FindAsync(string packageName, string version, string file, DateTimeOffset since,
                                                CancellationToken cancellation)
    {
        var events = await WindowsDeployments.ReadAsync(DateTimeOffset.Now - since + LogMargin, cancellation);
        return WindowsDeployments.Find(events, packageName, version, file, since, DateTimeOffset.Now);
    }

    public void ReopenWhenReplaced() => _ = RegisterApplicationRestart(null, 0);

    private sealed class Percentage(IProgress<int>? progress) : IProgress<DeploymentProgress>
    {
        public void Report(DeploymentProgress value) => progress?.Report((int)Math.Min(value.percentage, 100u));
    }

    [DllImport("kernel32.dll", CharSet = CharSet.Unicode)]
    private static extern int RegisterApplicationRestart(string? commandLine, int flags);
}

public sealed class EngineUpdateCommands(EngineConfiguration configuration) : IUpdateCommands
{
    public async Task<JsonElement> RunAsync(IReadOnlyList<string> arguments, CancellationToken cancellation, Action<string>? lines = null)
    {
        var start = configuration.EngineStart(["update", .. arguments, "--state", configuration.State]);
        using var process = System.Diagnostics.Process.Start(start) ?? throw new IOException("The update command did not start.");
        // A cancelled download stops at once: its partial file stays, and the next one resumes from it.
        var download = arguments[0] == "download";
        using var stop = download ? cancellation.Register(() =>
        {
            try { process.Kill(entireProcessTree: true); }
            catch (InvalidOperationException) { }
            catch (System.ComponentModel.Win32Exception) { }
        }) : default;
        var output = process.StandardOutput.ReadToEndAsync(CancellationToken.None);
        var errors = ReadLinesAsync(process.StandardError, lines);
        await process.WaitForExitAsync(CancellationToken.None);
        if (download) cancellation.ThrowIfCancellationRequested();
        var text = await output;
        try
        {
            using var document = JsonDocument.Parse(text);
            return document.RootElement.Clone();
        }
        catch (JsonException error)
        {
            throw new IOException("The update command failed: " + (await errors).Trim(), error);
        }
    }

    /// <summary>Every stderr line goes to <paramref name="lines"/> as it arrives; the whole text explains a failure.</summary>
    private static async Task<string> ReadLinesAsync(StreamReader reader, Action<string>? lines)
    {
        var text = new System.Text.StringBuilder();
        while (await reader.ReadLineAsync() is { } line)
        {
            text.AppendLine(line);
            lines?.Invoke(line);
        }
        return text.ToString();
    }
}

/// <summary>When a paused download tries again: as soon as Windows reports a network change, and otherwise after a delay
/// that grows, so hours offline cost a few attempts, not hundreds.</summary>
public static class Reconnection
{
    private static readonly TimeSpan[] Delays =
        [TimeSpan.FromSeconds(15), TimeSpan.FromSeconds(30), TimeSpan.FromMinutes(1), TimeSpan.FromMinutes(2), TimeSpan.FromMinutes(5)];

    /// <summary>A network that just came up needs a moment before it carries traffic.</summary>
    private static readonly TimeSpan Settle = TimeSpan.FromSeconds(3);

    public static TimeSpan Delay(int attempt) => Delays[Math.Clamp(attempt, 0, Delays.Length - 1)];

    public static async Task WaitAsync(TimeSpan delay, CancellationToken cancellation)
    {
        var changed = new TaskCompletionSource(TaskCreationOptions.RunContinuationsAsynchronously);
        void Changed(object sender) => changed.TrySetResult();
        NetworkInformation.NetworkStatusChanged += Changed;
        try
        {
            if (await Task.WhenAny(changed.Task, Task.Delay(delay, cancellation)) == changed.Task)
                await Task.Delay(Settle, cancellation);
            cancellation.ThrowIfCancellationRequested();
        }
        finally { NetworkInformation.NetworkStatusChanged -= Changed; }
    }
}

/// <summary>
/// Drives one package update around the engine: the journal is begun only with the engine
/// stopped, settled by the version that runs next, and never left `applying` by a switch
/// Windows refused.
/// </summary>
/// <param name="wait">Waits between readings of Windows' deployment log.</param>
public sealed class UpdateCoordinator(IUpdateCommands commands, IPackageDeployer deployer,
                                      Func<TimeSpan, CancellationToken, Task>? wait = null)
{
    /// <summary>How often Windows' deployment log is read while it installs an update this version began.</summary>
    public static readonly TimeSpan InstallPoll = TimeSpan.FromSeconds(3);

    /// <summary>How long Windows is given to close this version once it has put another in its place.</summary>
    public static readonly TimeSpan CloseGrace = TimeSpan.FromSeconds(30);

    private readonly Func<TimeSpan, CancellationToken, Task> wait = wait ?? Task.Delay;

    public static UpdateCoordinator For(EngineConfiguration configuration) =>
        new(new EngineUpdateCommands(configuration), new WindowsPackageDeployer());

    /// <summary>
    /// This version opened while the update it began is still applying. Settling the journal now would record that the
    /// switch never happened, while Windows may still be installing it or have installed it; so Windows' deployment log
    /// is asked first. While it installs, <paramref name="report"/> is told so and the wait goes on; Windows closes this
    /// version when it is done and opens the new one, which settles the update. Once Windows has installed it, this
    /// version never settles it: the engine stays closed. A failed install is reported with Windows' reason.
    /// </summary>
    /// <param name="packageName">The installed package's name, without version or publisher.</param>
    /// <returns>Whether this version may settle the update as not having happened and start its engine.</returns>
    public async Task<bool> AwaitWindowsAsync(LastUpdate pending, string packageName, Action<UpdateRun?> report,
                                              CancellationToken cancellation = default)
    {
        var since = pending.Since ?? DateTimeOffset.Now - WindowsDeployments.Patience;
        var reopens = false;
        while (true)
        {
            var finding = await deployer.FindAsync(packageName, pending.To, pending.Package!, since, cancellation);
            switch (finding.State)
            {
                case InstallProgress.Running:
                    // Only a process that asked is opened again after Windows closes it for the install.
                    if (!reopens) deployer.ReopenWhenReplaced();
                    reopens = true;
                    report(new UpdateRun(UpdateStep.Installing, pending.To));
                    await wait(InstallPoll, cancellation);
                    continue;
                case InstallProgress.Finished:
                    report(new UpdateRun(UpdateStep.Installing, pending.To, Percent: 100));
                    return false;
                case InstallProgress.Failed:
                    report(new UpdateRun(UpdateStep.InstallFailed, pending.To, Reason: finding.Reason));
                    return true;
                default:
                    report(null);
                    return true;
            }
        }
    }

    /// <summary>
    /// Reads where updates stand, as the first step of every open, and asks Windows about an update this version began
    /// that is still applying. A status that cannot be read throws, since without it nothing says whether Windows is
    /// installing that update: the journal stays as it is and the engine closed until a later open reads it.
    /// </summary>
    /// <param name="packageName">The installed package's name, or null for a copy without a package, which Windows never
    /// replaces.</param>
    /// <param name="read">Told where updates stand, before Windows is asked.</param>
    /// <param name="report">Told how Windows' install goes, as <see cref="AwaitWindowsAsync"/> reports it.</param>
    /// <returns>Whether this version may settle the journal and start its engine.</returns>
    public async Task<bool> MaySettleAsync(string? packageName, Action<UpdateFacts> read, Action<UpdateRun?> report,
                                           CancellationToken cancellation = default)
    {
        var reply = await commands.RunAsync(["status"], cancellation);
        read(UpdateFacts.Read(reply));
        // A build without a usable update identity reports updates unavailable, and still names the update.
        if (UpdateFacts.ReadLast(reply) is not { Phase: "applying", Running: "from" } pending || packageName is null) return true;
        if (pending.Package is null)
            throw new IOException("The unfinished update names no package, so Windows cannot be asked whether it is installing it.");
        return await AwaitWindowsAsync(pending, packageName, report, cancellation);
    }

    /// <summary>Settles a journal the previous run left; call before starting the engine.</summary>
    public async Task<string?> ResumeAsync(CancellationToken cancellation = default) =>
        (await ResumeWithRoleAsync(cancellation)).Phase;

    private async Task<(string? Phase, string? Running)> ResumeWithRoleAsync(CancellationToken cancellation)
    {
        var answer = await commands.RunAsync(["resume"], cancellation);
        static string? Text(JsonElement answer, string name) =>
            answer.TryGetProperty(name, out var value) && value.ValueKind == JsonValueKind.String ? value.GetString() : null;
        return (Text(answer, "phase"), Text(answer, "running"));
    }

    /// <summary>
    /// Starts the engine after settling the journal. When this run is the new version of an
    /// update, waits for its preparation and records the verdict: Ready completes the update;
    /// a failed database preparation, or an engine that keeps exiting before it is ever ready,
    /// marks it failed, which keeps everything closed until recovery.
    /// </summary>
    public async Task<string?> StartAsync(EngineSession session, CancellationToken cancellation = default)
    {
        var (phase, running) = await ResumeWithRoleAsync(cancellation);
        // A failed update stays closed until it is undone; the new version offers Undo again
        // when the switch back has not happened yet.
        if (phase == "failed" || (phase == "recovering" && running == "to")) return phase;
        if (phase == "recovering")
        {
            var recovered = await commands.RunAsync(["recover"], cancellation);
            if (!recovered.TryGetProperty("phase", out var next) || next.GetString() != "recovered")
                throw new IOException(Reason(recovered) ?? "The previous version's database could not be restored.");
            phase = "recovered";
        }
        // The journal's commands run to their end; only the engine's start stops here, as when Windows is ending the app.
        cancellation.ThrowIfCancellationRequested();
        await session.StartAsync();
        if (phase != "preparing") return phase;
        var verdict = new TaskCompletionSource<bool?>(TaskCreationOptions.RunContinuationsAsynchronously);
        void Observe(EngineSnapshot snapshot)
        {
            if (snapshot.State == EngineState.Ready) verdict.TrySetResult(true);
            else if (snapshot.State == EngineState.Attention) verdict.TrySetResult(session.PreparationFailed || session.GaveUp ? false : null);
            else if (snapshot.State == EngineState.Stopped) verdict.TrySetResult(null);
        }
        session.Changed += Observe;
        try
        {
            Observe(session.Snapshot);
            if (await verdict.Task.WaitAsync(cancellation) is not { } prepared) return phase;
            var settled = await SettleAsync(prepared, cancellation);
            return settled.TryGetProperty("phase", out var next) ? next.GetString() : phase;
        }
        finally
        {
            session.Changed -= Observe;
        }
    }

    public Task<JsonElement> CheckAsync(bool manual, CancellationToken cancellation = default) =>
        commands.RunAsync(manual ? ["check", "--manual"] : ["check"], cancellation);

    /// <summary>Where updates stand, from what earlier checks kept; no request is made.</summary>
    public async Task<UpdateFacts> StatusAsync(CancellationToken cancellation = default) =>
        UpdateFacts.Read(await commands.RunAsync(["status"], cancellation));

    /// <returns>What the check found, and its status: up-to-date, offered, failed, rate-limited, not-allowed, throttled or unavailable.</returns>
    public async Task<(UpdateFacts Facts, string Status)> CheckNowAsync(bool manual, CancellationToken cancellation = default)
    {
        var reply = await CheckAsync(manual, cancellation);
        return (UpdateFacts.Read(reply), reply.GetProperty("status").GetString() ?? "");
    }

    /// <summary>Records the automatic-check choice with the words shown and their language.</summary>
    public async Task ConsentAsync(bool automatic, string text, string language, CancellationToken cancellation = default)
    {
        var reply = await commands.RunAsync(
            ["consent", "--automatic", automatic ? "on" : "off", "--text", text, "--language", language], cancellation);
        if (!reply.TryGetProperty("recorded", out var recorded) || recorded.ValueKind != JsonValueKind.True)
            throw new IOException(Reason(reply) ?? "The update choice was not recorded.");
    }

    /// <param name="progress">Told the bytes downloaded so far and the total, as the command counts them.</param>
    public Task<JsonElement> DownloadAsync(IProgress<(long Received, long Total)>? progress = null, CancellationToken cancellation = default) =>
        commands.RunAsync(["download"], cancellation, line =>
        {
            if (UpdateRun.Progress(line) is { } counted) progress?.Report(counted);
        });

    /// <param name="progress">Windows' percentage of the install, while this version stays open until Windows closes it.</param>
    /// <param name="cancellation">Cancels the update until the journal records it, as when Windows ends the session during
    /// the engine's stop; once recorded, Windows' install runs to its end.</param>
    public async Task ApplyAsync(EngineSession session, string package, IProgress<int>? progress = null, CancellationToken cancellation = default)
    {
        await session.StopAsync();
        if (session.OwnsEngine) throw new IOException("The engine did not stop, so the update was not started.");
        cancellation.ThrowIfCancellationRequested();
        var begun = await commands.RunAsync(["begin", "--package", package], CancellationToken.None);
        if (!begun.TryGetProperty("phase", out var phase) || phase.GetString() != "applying")
            throw new IOException(Reason(begun) ?? "The update could not be started.");
        deployer.ReopenWhenReplaced();
        try
        {
            await deployer.AddAsync(package, downgrade: false, progress, CancellationToken.None);
        }
        catch
        {
            // Still the old version: the journal records that the switch never happened.
            await commands.RunAsync(["resume"], CancellationToken.None);
            throw;
        }
    }

    /// <summary>
    /// From a failed update: registers the retained previous package again. That version's next
    /// Start puts back the database the update replaced, keeping the replaced one.
    /// </summary>
    /// <param name="cancellation">Cancels the undo until the journal records it; once recorded, Windows' install runs to
    /// its end.</param>
    public async Task ReturnToPreviousAsync(EngineSession session, IProgress<int>? progress = null, CancellationToken cancellation = default)
    {
        await session.StopAsync();
        if (session.OwnsEngine) throw new IOException("The engine did not stop, so the update was not undone.");
        cancellation.ThrowIfCancellationRequested();
        var begun = await commands.RunAsync(["recover-begin"], CancellationToken.None);
        if (!begun.TryGetProperty("package", out var package) || package.ValueKind != JsonValueKind.String)
            throw new UpdateRefused(Reason(begun) ?? "The previous version could not be prepared.",
                begun.TryGetProperty("kind", out var kind) && kind.ValueKind == JsonValueKind.String ? kind.GetString() : null);
        deployer.ReopenWhenReplaced();
        await deployer.AddAsync(package.GetString()!, downgrade: true, progress, CancellationToken.None);
    }

    /// <summary>Records the new version's verdict on its own preparation.</summary>
    public Task<JsonElement> SettleAsync(bool prepared, CancellationToken cancellation = default) =>
        commands.RunAsync(["settle", "--prepared", prepared ? "yes" : "no"], cancellation);

    private static string? Reason(JsonElement answer) =>
        answer.TryGetProperty("reason", out var reason) && reason.ValueKind == JsonValueKind.String ? reason.GetString() : null;
}

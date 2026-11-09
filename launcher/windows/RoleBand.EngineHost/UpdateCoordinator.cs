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
}

/// <summary>The engine's `desktop.py update` commands, each answering one JSON object.</summary>
public interface IUpdateCommands
{
    /// <param name="lines">Told each line the command writes to stderr while it runs, such as a download's progress.</param>
    /// <param name="cancellation">Stops the command and every process it started.</param>
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

    private sealed class Percentage(IProgress<int>? progress) : IProgress<DeploymentProgress>
    {
        public void Report(DeploymentProgress value) => progress?.Report((int)Math.Min(value.percentage, 100u));
    }
}

public sealed class EngineUpdateCommands(EngineConfiguration configuration) : IUpdateCommands
{
    public async Task<JsonElement> RunAsync(IReadOnlyList<string> arguments, CancellationToken cancellation, Action<string>? lines = null)
    {
        var start = configuration.EngineStart(["update", .. arguments, "--state", configuration.State]);
        using var process = System.Diagnostics.Process.Start(start) ?? throw new IOException("The update command did not start.");
        // A cancelled download stops at once: its partial file stays, and the next one resumes from it.
        using var stop = cancellation.Register(() =>
        {
            try { process.Kill(entireProcessTree: true); }
            catch (InvalidOperationException) { }
            catch (System.ComponentModel.Win32Exception) { }
        });
        var output = process.StandardOutput.ReadToEndAsync(CancellationToken.None);
        var errors = ReadLinesAsync(process.StandardError, lines);
        await process.WaitForExitAsync(CancellationToken.None);
        cancellation.ThrowIfCancellationRequested();
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
public sealed class UpdateCoordinator(IUpdateCommands commands, IPackageDeployer deployer)
{
    public static UpdateCoordinator For(EngineConfiguration configuration) =>
        new(new EngineUpdateCommands(configuration), new WindowsPackageDeployer());

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
    public async Task ApplyAsync(EngineSession session, string package, IProgress<int>? progress = null, CancellationToken cancellation = default)
    {
        await session.StopAsync();
        if (session.OwnsEngine) throw new IOException("The engine did not stop, so the update was not started.");
        var begun = await commands.RunAsync(["begin", "--package", package], cancellation);
        if (!begun.TryGetProperty("phase", out var phase) || phase.GetString() != "applying")
            throw new IOException(Reason(begun) ?? "The update could not be started.");
        // Ask Windows to open RoleBand again once the replacement has closed it.
        _ = RegisterApplicationRestart(null, 0);
        try
        {
            await deployer.AddAsync(package, downgrade: false, progress, cancellation);
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
    public async Task ReturnToPreviousAsync(EngineSession session, IProgress<int>? progress = null, CancellationToken cancellation = default)
    {
        await session.StopAsync();
        if (session.OwnsEngine) throw new IOException("The engine did not stop, so the update was not undone.");
        var begun = await commands.RunAsync(["recover-begin"], cancellation);
        if (!begun.TryGetProperty("package", out var package) || package.ValueKind != JsonValueKind.String)
            throw new IOException(Reason(begun) ?? "The previous version could not be prepared.");
        _ = RegisterApplicationRestart(null, 0);
        await deployer.AddAsync(package.GetString()!, downgrade: true, progress, cancellation);
    }

    /// <summary>Records the new version's verdict on its own preparation.</summary>
    public Task<JsonElement> SettleAsync(bool prepared, CancellationToken cancellation = default) =>
        commands.RunAsync(["settle", "--prepared", prepared ? "yes" : "no"], cancellation);

    private static string? Reason(JsonElement answer) =>
        answer.TryGetProperty("reason", out var reason) && reason.ValueKind == JsonValueKind.String ? reason.GetString() : null;

    [DllImport("kernel32.dll", CharSet = CharSet.Unicode)]
    private static extern int RegisterApplicationRestart(string? commandLine, int flags);
}

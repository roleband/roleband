using System.Runtime.InteropServices;
using System.Text.Json;
using Windows.Management.Deployment;

namespace RoleBand.EngineHost;

/// <summary>Replaces this app's package; Windows may end this process while it does.</summary>
public interface IPackageDeployer
{
    /// <param name="downgrade">Register a lower version, to return to the previous one.</param>
    Task AddAsync(string package, bool downgrade, CancellationToken cancellation);
}

/// <summary>The engine's `desktop.py update` commands, each answering one JSON object.</summary>
public interface IUpdateCommands
{
    Task<JsonElement> RunAsync(IReadOnlyList<string> arguments, CancellationToken cancellation);
}

public sealed class WindowsPackageDeployer : IPackageDeployer
{
    public async Task AddAsync(string package, bool downgrade, CancellationToken cancellation)
    {
        var options = new AddPackageOptions
        {
            ForceAppShutdown = true, ForceTargetAppShutdown = true, ForceUpdateFromAnyVersion = downgrade,
        };
        var result = await new PackageManager().AddPackageByUriAsync(new Uri(package), options).AsTask(cancellation);
        if (result.ExtendedErrorCode is { } error)
            throw new IOException("Windows did not install the update: " + result.ErrorText, error);
    }
}

public sealed class EngineUpdateCommands(EngineConfiguration configuration) : IUpdateCommands
{
    public async Task<JsonElement> RunAsync(IReadOnlyList<string> arguments, CancellationToken cancellation)
    {
        var start = configuration.EngineStart(["update", .. arguments, "--state", configuration.State]);
        using var process = System.Diagnostics.Process.Start(start) ?? throw new IOException("The update command did not start.");
        var output = process.StandardOutput.ReadToEndAsync(cancellation);
        var errors = process.StandardError.ReadToEndAsync(cancellation);
        await process.WaitForExitAsync(cancellation);
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
    /// a failed database preparation marks it failed, which keeps everything closed until recovery.
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
            else if (snapshot.State == EngineState.Attention) verdict.TrySetResult(session.PreparationFailed ? false : null);
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

    public Task<JsonElement> DownloadAsync(CancellationToken cancellation = default) =>
        commands.RunAsync(["download"], cancellation);

    public async Task ApplyAsync(EngineSession session, string package, CancellationToken cancellation = default)
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
            await deployer.AddAsync(package, downgrade: false, cancellation);
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
    public async Task ReturnToPreviousAsync(EngineSession session, CancellationToken cancellation = default)
    {
        await session.StopAsync();
        if (session.OwnsEngine) throw new IOException("The engine did not stop, so the update was not undone.");
        var begun = await commands.RunAsync(["recover-begin"], cancellation);
        if (!begun.TryGetProperty("package", out var package) || package.ValueKind != JsonValueKind.String)
            throw new IOException(Reason(begun) ?? "The previous version could not be prepared.");
        _ = RegisterApplicationRestart(null, 0);
        await deployer.AddAsync(package.GetString()!, downgrade: true, cancellation);
    }

    /// <summary>Records the new version's verdict on its own preparation.</summary>
    public Task<JsonElement> SettleAsync(bool prepared, CancellationToken cancellation = default) =>
        commands.RunAsync(["settle", "--prepared", prepared ? "yes" : "no"], cancellation);

    private static string? Reason(JsonElement answer) =>
        answer.TryGetProperty("reason", out var reason) && reason.ValueKind == JsonValueKind.String ? reason.GetString() : null;

    [DllImport("kernel32.dll", CharSet = CharSet.Unicode)]
    private static extern int RegisterApplicationRestart(string? commandLine, int flags);
}

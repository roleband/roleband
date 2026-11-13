using System.ComponentModel;
using System.Diagnostics;
using System.Runtime.InteropServices;
using System.Text;
using System.Text.Json;

namespace RoleBand.EngineHost;

public enum EngineState { Stopped, Starting, Preparing, Ready, Recovering, Stopping, Attention }
/// <param name="Preparation">The engine's last account of its first preparation, kept through a failure so it can say which part failed.</param>
public sealed record EngineSnapshot(EngineState State, string? Diagnostic = null, int? ProcessId = null,
                                   EnginePreparation? Preparation = null);

/// <summary>How long the session waits and how often it restarts. Tests shorten these.</summary>
/// <param name="PreparationDeadline">How long an engine that is not yet ready may go without its preparation changing.
/// The engine bounds each step of its own preparation, such as a database migration, within this.</param>
/// <param name="SilentPreparation">How long an engine that is not yet ready may go without answering at all.</param>
public sealed record EngineSessionOptions(
    TimeSpan StopTimeout, TimeSpan RestartWindow, int RestartLimit, TimeSpan FirstBackoff, TimeSpan MaximumBackoff,
    TimeSpan PreparationDeadline, TimeSpan SilentPreparation, long LogLimitBytes)
{
    public static EngineSessionOptions Default { get; } = new(
        TimeSpan.FromSeconds(90), TimeSpan.FromMinutes(10), 3, TimeSpan.FromSeconds(1), TimeSpan.FromSeconds(60),
        TimeSpan.FromSeconds(1920), TimeSpan.FromSeconds(60), 10 * 1024 * 1024);
}

// One monitor owns the engine process from spawn to exit. It alone sends the stop
// request, at most once per process, and the lease is released only when no engine
// process of this session remains. An engine that did not confirm a stop is kept, with
// the lease, until it exits; its exit releases the lease, so the session can start again.
public sealed class EngineSession : IAsyncDisposable
{
    private enum Outcome { Exited, Unhealthy, PreparationFailed, Cancelled }

    private const string Preserved = "The engine has not confirmed a clean stop. Its process was preserved.";

    /// <summary>How long an exited engine's output is still read: a process it started can hold its pipes open.</summary>
    private static readonly TimeSpan DrainGrace = TimeSpan.FromSeconds(5);

    private readonly EngineConfiguration configuration;
    private readonly EngineSessionOptions options;
    private readonly DesktopLog log;
    private readonly SemaphoreSlim operations = new(1);
    private readonly Lock signalGate = new();
    private FileStream? lease;
    private Process? process;
    private Task? stopSignal;
    private Task? drains;
    private CancellationTokenSource? stopping;
    private Task? monitor;
    private EngineSnapshot snapshot = new(EngineState.Stopped);
    private EnginePreparation? preparation;
    public EngineSnapshot Snapshot => Volatile.Read(ref snapshot);
    public bool OwnsEngine => lease is not null;
    /// <summary>The last start ended because the engine could not prepare its database.</summary>
    public bool PreparationFailed { get; private set; }

    /// <summary>The last start ended because the engine kept exiting until the restart limit.</summary>
    public bool GaveUp { get; private set; }
    public event Action<EngineSnapshot>? Changed;

    public EngineSession(EngineConfiguration configuration, EngineSessionOptions? options = null)
    {
        this.configuration = configuration;
        this.options = options ?? EngineSessionOptions.Default;
        log = new DesktopLog(Path.Combine(configuration.State, "logs", "desktop.log"), this.options.LogLimitBytes);
    }

    private void Publish(EngineState state, string? diagnostic = null)
    {
        var next = new EngineSnapshot(state, diagnostic, process is { HasExited: false } ? process.Id : null, preparation);
        Volatile.Write(ref snapshot, next);
        Changed?.Invoke(next);
    }

    public async Task StartAsync()
    {
        await operations.WaitAsync();
        try
        {
            if (monitor is { IsCompleted: false }) return;
            if (process is { } kept)
            {
                // A kept engine still running holds the data; one that has exited is let go here.
                if (!kept.HasExited) return;
                await ReleaseKeptAsync();
            }
            PreparationFailed = false;
            GaveUp = false;
            preparation = null;
            lease = PrivateStorage.Lease(configuration.State, "desktop.lock");
            PrivateStorage.EnsureDirectory(Path.Combine(configuration.State, "logs"));
            RecoveryGuard.RequireLaunchable(configuration.State);
            RefuseLivePredecessor();
            stopping?.Dispose();
            stopping = new CancellationTokenSource();
            Publish(EngineState.Starting);
            monitor = MonitorAsync(stopping.Token);
        }
        catch (Exception error)
        {
            ReleaseLease();
            Publish(EngineState.Attention, error.Message);
        }
        finally { operations.Release(); }
    }

    private void RefuseLivePredecessor()
    {
        var path = Path.Combine(configuration.State, "launcher", "owned-engine.json");
        if (!File.Exists(path)) return;
        // A record that fails the private-state check stays a refusal; one whose content cannot be read names no
        // process, so nothing it says can still be running. The next engine publishes its own over it.
        using var record = ReadRecord(PrivateStorage.Read(path));
        if (record is null)
        {
            log.Append("The previous engine's record could not be read; it names no engine that is still running.");
            return;
        }
        var root = record.RootElement;
        // Windows reuses process IDs: only a running process that started when the record says
        // is the recorded engine. A record of an engine that has exited blocks nothing.
        if (Number(root, "pid") is not { } pid || !pid.TryGetInt32(out var id)
            || Number(root, "started") is not { } start || !start.TryGetDouble(out var started)
            || !double.IsFinite(started) || started <= 0
            || ProcessClock.RunningSince(id) is not { } began || Math.Abs(began - started) >= 0.002)
            return;
        if (!SameInstallation(root)) throw new IOException("A different installation owns this engine record.");
        throw new IOException("The previous engine is still closing or another app owns it.");
    }

    private static JsonDocument? ReadRecord(byte[] bytes)
    {
        try
        {
            var record = JsonDocument.Parse(bytes);
            if (record.RootElement.ValueKind == JsonValueKind.Object) return record;
            record.Dispose();
            return null;
        }
        catch (JsonException) { return null; }
    }

    private static JsonElement? Number(JsonElement root, string name) =>
        root.TryGetProperty(name, out var value) && value.ValueKind == JsonValueKind.Number ? value : null;

    private bool SameInstallation(JsonElement root)
    {
        static string? Text(JsonElement root, string name) =>
            root.TryGetProperty(name, out var value) && value.ValueKind == JsonValueKind.String ? value.GetString() : null;
        return Number(root, "format") is { } format && format.TryGetInt32(out var number) && number == 1
            && Text(root, "resources") is { } resources && Path.IsPathFullyQualified(resources)
            && Path.GetFullPath(resources).Equals(configuration.Resources, StringComparison.OrdinalIgnoreCase)
            && Text(root, "state") is { } state && Path.IsPathFullyQualified(state)
            && Path.GetFullPath(state).Equals(configuration.State, StringComparison.OrdinalIgnoreCase);
    }

    private Process Spawn(string marker)
    {
        var arguments = new List<string> { "run", "--marker", marker };
        if (configuration.Development || configuration.SyntheticFixture) arguments.Add("--dry-run-network");
        if (configuration.SyntheticFixture) arguments.Add("--synthetic-fixture");
        var start = configuration.EngineStart(arguments);
        start.RedirectStandardInput = true;
        return Process.Start(start) ?? throw new IOException("The engine process did not start.");
    }

    private async Task MonitorAsync(CancellationToken cancellation)
    {
        var restarts = new Queue<double>();
        var backoff = options.FirstBackoff;
        try
        {
            while (true)
            {
                RecoveryGuard.RequireLaunchable(configuration.State);
                var marker = Guid.NewGuid().ToString("N");
                var engine = Spawn(marker);
                lock (signalGate) { process = engine; stopSignal = null; }
                drains = Task.WhenAll(DrainAsync(engine.StandardOutput), DrainAsync(engine.StandardError));
                var outcome = await WatchAsync(engine, marker, cancellation);
                if (!await EndProcessAsync())
                {
                    Preserve();
                    return;
                }
                if (outcome == Outcome.Cancelled) return;
                if (outcome == Outcome.PreparationFailed)
                {
                    PreparationFailed = true;
                    Publish(EngineState.Attention, "Engine preparation failed. The preparation log contains details.");
                    return;
                }
                var now = AwakeSeconds();
                while (restarts.TryPeek(out var previous) && now - previous > options.RestartWindow.TotalSeconds) restarts.Dequeue();
                if (restarts.Count >= options.RestartLimit)
                {
                    GaveUp = true;
                    Publish(EngineState.Attention, "Automatic recovery reached its limit. The engine log contains details.");
                    return;
                }
                restarts.Enqueue(now);
                Publish(EngineState.Recovering);
                try { await Task.Delay(backoff, cancellation); }
                catch (OperationCanceledException) { return; }
                backoff = TimeSpan.FromTicks(Math.Min(backoff.Ticks * 2, options.MaximumBackoff.Ticks));
            }
        }
        catch (Exception error)
        {
            Publish(EngineState.Attention, error.Message);
            if (!await EndProcessAsync()) Preserve();
        }
        finally
        {
            if (process is null) ReleaseLease();
        }
    }

    private async Task<Outcome> WatchAsync(Process engine, string marker, CancellationToken cancellation)
    {
        // Silence counts from the last answer, the deadline from the preparation's last change, never from the
        // launch: an update's migration of a long history can outlast the deadline alone, and the engine bounds
        // each of its own steps. Until the first answer, silence alone applies.
        var lastAnswer = AwakeSeconds();
        var lastProgress = lastAnswer;
        EnginePreparation? previous = null;
        var wasReady = false;
        var failures = 0;
        string? lastFailure = null;
        try
        {
            while (!engine.HasExited)
            {
                cancellation.ThrowIfCancellationRequested();
                try
                {
                    VerifyOwnedRecord(engine, marker);
                    using var client = new EngineClient(configuration.State);
                    using var health = await client.RequestAsync(HttpMethod.Get, "/api/launcher-health", cancellation: cancellation);
                    var root = health.RootElement;
                    var identity = root.GetProperty("launcher");
                    if (root.GetProperty("status").GetString() != "ok"
                        || identity.GetProperty("product").GetString() != "roleband"
                        || identity.GetProperty("version").GetString() != configuration.Version
                        || identity.GetProperty("api_origin").GetString() != client.Origin.GetLeftPart(UriPartial.Authority))
                        throw new IOException("The authenticated engine identity does not match this app.");
                    preparation = EnginePreparation.Read(root.GetProperty("preparation"));
                    if (preparation is null || preparation.Ready)
                    {
                        wasReady = true;
                        failures = 0;
                        lastFailure = null;
                        Publish(EngineState.Ready);
                    }
                    else if (preparation.Failed)
                    {
                        return Outcome.PreparationFailed;
                    }
                    else
                    {
                        lastAnswer = AwakeSeconds();
                        if (preparation != previous) lastProgress = lastAnswer;
                        previous = preparation;
                        Publish(EngineState.Preparing);
                    }
                }
                // A slow or malformed answer is one failed read, counted against the restart budget; only the
                // session's own cancellation ends the watch.
                catch (Exception error) when (error is IOException or HttpRequestException or JsonException
                    or KeyNotFoundException or InvalidOperationException or FormatException
                    || (error is OperationCanceledException && !cancellation.IsCancellationRequested))
                {
                    if (cancellation.IsCancellationRequested) return Outcome.Cancelled;
                    var failure = error.GetType().Name + ": " + error.Message;
                    if (failure != lastFailure) log.Append(failure);
                    lastFailure = failure;
                    failures++;
                    if ((wasReady && failures >= 3) || (!wasReady && AwakeSeconds() - lastAnswer > options.SilentPreparation.TotalSeconds))
                        return Outcome.Unhealthy;
                }
                if (!wasReady && previous is not null && AwakeSeconds() - lastProgress > options.PreparationDeadline.TotalSeconds)
                    return Outcome.Unhealthy;
                await Task.Delay(TimeSpan.FromSeconds(1), cancellation);
            }
            return Outcome.Exited;
        }
        catch (OperationCanceledException) when (cancellation.IsCancellationRequested)
        {
            return Outcome.Cancelled;
        }
    }

    // Asks the current engine to stop, once, and waits for it. False leaves it running.
    private async Task<bool> EndProcessAsync()
    {
        Process? engine;
        Task signal;
        lock (signalGate)
        {
            engine = process;
            if (engine is null) return true;
            signal = stopSignal ??= engine.HasExited ? Task.CompletedTask : SignalAsync(engine);
        }
        try { await signal; }
        catch (IOException) { }
        using (var timeout = new CancellationTokenSource(options.StopTimeout))
        {
            try { await engine.WaitForExitAsync(timeout.Token); }
            catch (OperationCanceledException) { return false; }
        }
        if (drains is not null)
        {
            try { await drains.WaitAsync(DrainGrace); }
            catch (TimeoutException) { log.Append("The engine's output stayed open after it exited."); }
        }
        lock (signalGate)
        {
            process = null;
            stopSignal = null;
        }
        engine.Dispose();
        return true;
    }

    private static async Task SignalAsync(Process engine)
    {
        await engine.StandardInput.WriteLineAsync("stop");
        await engine.StandardInput.FlushAsync();
    }

    private void VerifyOwnedRecord(Process engine, string marker)
    {
        using var record = JsonDocument.Parse(PrivateStorage.Read(Path.Combine(configuration.State, "launcher", "owned-engine.json")));
        var root = record.RootElement;
        if (root.GetProperty("pid").GetInt32() != engine.Id || root.GetProperty("marker").GetString() != marker
            || !Path.GetFullPath(root.GetProperty("resources").GetString()!).Equals(configuration.Resources, StringComparison.OrdinalIgnoreCase))
            throw new IOException("The engine process did not publish its owned identity.");
    }

    private async Task DrainAsync(StreamReader reader)
    {
        try
        {
            while (await reader.ReadLineAsync() is { } line) log.Append(line);
        }
        // A read still waiting after the grace ends when the process object closes its pipes.
        catch (Exception error) when (error is ObjectDisposedException or IOException) { }
    }

    private void ReleaseLease()
    {
        lease?.Dispose();
        lease = null;
    }

    /// <summary>Keeps the engine that did not confirm a stop, and lets it go, with the lease, once it exits.</summary>
    private void Preserve()
    {
        Publish(EngineState.Attention, Preserved);
        if (process is { } kept) _ = ReleaseWhenExitedAsync(kept);
    }

    private async Task ReleaseWhenExitedAsync(Process kept)
    {
        try
        {
            await kept.WaitForExitAsync();
            await operations.WaitAsync();
            try
            {
                if (process != kept) return;
                // The monitor that kept it may still be finishing; it never waits on this lock.
                if (monitor is not null) await monitor;
                await ReleaseKeptAsync();
                Publish(EngineState.Stopped);
            }
            finally { operations.Release(); }
        }
        // The session was disposed first: the lease goes with this app's process.
        catch (Exception error) when (error is ObjectDisposedException or InvalidOperationException) { }
    }

    /// <summary>Lets go of a kept engine that has exited. Called holding <see cref="operations"/>.</summary>
    private async Task ReleaseKeptAsync()
    {
        await EndProcessAsync();
        ReleaseLease();
        monitor = null;
        stopping?.Dispose();
        stopping = null;
    }

    public async Task StopAsync()
    {
        await operations.WaitAsync();
        try
        {
            var watched = monitor is { IsCompleted: false };
            if (process is { HasExited: false }) Publish(EngineState.Stopping);
            stopping?.Cancel();
            if (monitor is not null) await monitor;
            // A process an earlier stop could not end gets one more wait; one this stop
            // could not end stays preserved for the person to inspect.
            if (!watched && process is not null && !await EndProcessAsync()) Preserve();
            if (process is not null) return;
            ReleaseLease();
            monitor = null;
            stopping?.Dispose();
            stopping = null;
            Publish(EngineState.Stopped);
        }
        finally { operations.Release(); }
    }

    public async Task<Uri> BrowserUriAsync(BrowserRoute route = BrowserRoute.Radar)
    {
        using var client = Connect();
        return ScanPanel.Route(await client.BrowserUriAsync(), route);
    }

    /// <summary>An authenticated connection to the engine this session runs; the caller disposes it.</summary>
    public EngineClient Connect()
    {
        if (Snapshot.State != EngineState.Ready) throw new IOException("The engine is not ready.");
        return new EngineClient(configuration.State);
    }

    public async ValueTask DisposeAsync()
    {
        await StopAsync();
        stopping?.Dispose();
        operations.Dispose();
    }

    private static double AwakeSeconds()
    {
        if (!QueryUnbiasedInterruptTime(out var count)) throw new Win32Exception(Marshal.GetLastWin32Error());
        return count / 10_000_000.0;
    }

    [DllImport("kernel32.dll", SetLastError = true)]
    [return: MarshalAs(UnmanagedType.Bool)]
    private static extern bool QueryUnbiasedInterruptTime(out ulong count);
}

using System.ComponentModel;
using System.Diagnostics;
using System.Runtime.InteropServices;
using System.Text;
using System.Text.Json;

namespace RoleBand.EngineHost;

public enum EngineState { Stopped, Starting, Preparing, Ready, Recovering, Stopping, Attention }
public sealed record EngineSnapshot(EngineState State, string? Diagnostic = null, int? ProcessId = null);

/// <summary>How long the session waits and how often it restarts. Tests shorten these.</summary>
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
// process of this session remains.
public sealed class EngineSession : IAsyncDisposable
{
    private enum Outcome { Exited, Unhealthy, PreparationFailed, Cancelled }

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
    public EngineSnapshot Snapshot => Volatile.Read(ref snapshot);
    public bool OwnsEngine => lease is not null;
    public event Action<EngineSnapshot>? Changed;

    public EngineSession(EngineConfiguration configuration, EngineSessionOptions? options = null)
    {
        this.configuration = configuration;
        this.options = options ?? EngineSessionOptions.Default;
        log = new DesktopLog(Path.Combine(configuration.State, "logs", "desktop.log"), this.options.LogLimitBytes);
    }

    private void Publish(EngineState state, string? diagnostic = null)
    {
        var next = new EngineSnapshot(state, diagnostic, process is { HasExited: false } ? process.Id : null);
        Volatile.Write(ref snapshot, next);
        Changed?.Invoke(next);
    }

    public async Task StartAsync()
    {
        await operations.WaitAsync();
        try
        {
            if (OwnsEngine) return;
            lease = PrivateStorage.Lease(configuration.State, "desktop.lock");
            PrivateStorage.EnsureDirectory(Path.Combine(configuration.State, "logs"));
            RecoveryGuard.RequireLaunchable(configuration.State);
            RefuseLivePredecessor();
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
        using var record = JsonDocument.Parse(PrivateStorage.Read(path));
        var root = record.RootElement;
        var resources = root.GetProperty("resources").GetString();
        var started = root.GetProperty("started").GetDouble();
        if (root.GetProperty("format").GetInt32() != 1
            || resources is null || !Path.IsPathFullyQualified(resources) || !double.IsFinite(started) || started <= 0
            || !Path.GetFullPath(root.GetProperty("state").GetString()!).Equals(configuration.State, StringComparison.OrdinalIgnoreCase))
            throw new IOException("A different installation owns this engine record.");
        // Windows reuses process IDs: only a running process that started when the
        // record says is the recorded engine.
        if (ProcessClock.RunningSince(root.GetProperty("pid").GetInt32()) is not { } began || Math.Abs(began - started) >= 0.002)
            return;
        if (!Path.GetFullPath(resources).Equals(configuration.Resources, StringComparison.OrdinalIgnoreCase))
            throw new IOException("A different installation owns this engine record.");
        throw new IOException("The previous engine is still closing or another app owns it.");
    }

    private Process Spawn(string marker)
    {
        var start = new ProcessStartInfo(configuration.NativePython)
        {
            WorkingDirectory = configuration.EngineDirectory,
            UseShellExecute = false,
            CreateNoWindow = true,
            RedirectStandardInput = true,
            RedirectStandardOutput = true,
            RedirectStandardError = true,
            StandardOutputEncoding = Encoding.UTF8,
            StandardErrorEncoding = Encoding.UTF8,
        };
        start.Environment.Clear();
        foreach (var name in new[] { "SystemRoot", "WINDIR", "TEMP", "TMP", "USERPROFILE", "LOCALAPPDATA", "APPDATA", "SYSTEMDRIVE" })
            if (Environment.GetEnvironmentVariable(name) is { } value) start.Environment[name] = value;
        var system = Environment.GetFolderPath(Environment.SpecialFolder.System);
        start.Environment["PATH"] = Path.GetDirectoryName(configuration.NativePython) + ";" + system;
        if (configuration.Development) start.Environment["__PYVENV_LAUNCHER__"] = configuration.Python;
        var state = configuration.State;
        foreach (var (name, value) in new Dictionary<string, string>
        {
            ["ROLEBAND_STATE_DIR"] = state, ["ROLEBAND_PGDATA"] = Path.Combine(state, "db"),
            ["ROLEBAND_CACHE_DIR"] = Path.Combine(state, "cache"), ["ROLEBAND_PLUGINS_DIR"] = Path.Combine(state, "plugins"),
            ["ROLEBAND_SECRET_KEY_FILE"] = Path.Combine(state, "secret.key"), ["ROLEBAND_DATABASE_URL"] = "",
            ["ROLEBAND_DB_EMBEDDED"] = "true", ["ROLEBAND_API_HOST"] = "127.0.0.1",
            ["ROLEBAND_API_PORT"] = EngineConfiguration.AvailablePort().ToString(System.Globalization.CultureInfo.InvariantCulture),
            ["ROLEBAND_LOCAL_AUTH"] = "1", ["PYTHONUTF8"] = "1", ["PYTHONNOUSERSITE"] = "1",
            ["PYTHONDONTWRITEBYTECODE"] = "1",
        }) start.Environment[name] = value;
        if (configuration.Development || configuration.SyntheticFixture)
        {
            start.Environment["ROLEBAND_NO_USAGE_STATS"] = "1";
            start.Environment["ROLEBAND_SEARCH_SEMANTIC_ENABLED"] = "false";
            start.Environment["ROLEBAND_SEARCH_WARM_MODEL_ON_STARTUP"] = "false";
        }
        start.ArgumentList.Add("-I");
        start.ArgumentList.Add("-B");
        start.ArgumentList.Add(configuration.Bootstrap);
        if (configuration.Development) start.ArgumentList.Add("--source");
        start.ArgumentList.Add("run");
        start.ArgumentList.Add("--marker");
        start.ArgumentList.Add(marker);
        if (configuration.Development || configuration.SyntheticFixture) start.ArgumentList.Add("--dry-run-network");
        if (configuration.SyntheticFixture) start.ArgumentList.Add("--synthetic-fixture");
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
                    Publish(EngineState.Attention, "The engine has not confirmed a clean stop. Its process was preserved.");
                    return;
                }
                if (outcome == Outcome.Cancelled) return;
                if (outcome == Outcome.PreparationFailed)
                {
                    Publish(EngineState.Attention, "Engine preparation failed. The preparation log contains details.");
                    return;
                }
                var now = AwakeSeconds();
                while (restarts.TryPeek(out var previous) && now - previous > options.RestartWindow.TotalSeconds) restarts.Dequeue();
                if (restarts.Count >= options.RestartLimit)
                {
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
            if (!await EndProcessAsync())
                Publish(EngineState.Attention, "The engine has not confirmed a clean stop. Its process was preserved.");
        }
        finally
        {
            if (process is null) ReleaseLease();
        }
    }

    private async Task<Outcome> WatchAsync(Process engine, string marker, CancellationToken cancellation)
    {
        var began = AwakeSeconds();
        var lastPreparation = began;
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
                    var preparation = root.GetProperty("preparation");
                    if (preparation.ValueKind == JsonValueKind.Null
                        || (preparation.GetProperty("database").GetString() == "ready" && preparation.GetProperty("service").GetString() == "ready"))
                    {
                        wasReady = true;
                        failures = 0;
                        lastFailure = null;
                        Publish(EngineState.Ready);
                    }
                    else if (preparation.GetProperty("database").GetString() == "failed" || preparation.GetProperty("service").GetString() == "failed")
                    {
                        return Outcome.PreparationFailed;
                    }
                    else
                    {
                        lastPreparation = AwakeSeconds();
                        Publish(EngineState.Preparing);
                    }
                }
                catch (Exception error) when (error is IOException or HttpRequestException or JsonException
                    or KeyNotFoundException or InvalidOperationException or TaskCanceledException)
                {
                    if (cancellation.IsCancellationRequested) return Outcome.Cancelled;
                    var failure = error.GetType().Name + ": " + error.Message;
                    if (failure != lastFailure) log.Append(failure);
                    lastFailure = failure;
                    failures++;
                    if ((wasReady && failures >= 3) || (!wasReady && AwakeSeconds() - lastPreparation > options.SilentPreparation.TotalSeconds))
                        return Outcome.Unhealthy;
                }
                if (!wasReady && AwakeSeconds() - began > options.PreparationDeadline.TotalSeconds) return Outcome.Unhealthy;
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
        if (drains is not null) await drains;
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
        while (await reader.ReadLineAsync() is { } line) log.Append(line);
    }

    private void ReleaseLease()
    {
        lease?.Dispose();
        lease = null;
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
            if (!watched && process is not null && !await EndProcessAsync())
                Publish(EngineState.Attention, "The engine has not confirmed a clean stop. Its process was preserved.");
            if (process is not null) return;
            ReleaseLease();
            monitor = null;
            stopping?.Dispose();
            stopping = null;
            Publish(EngineState.Stopped);
        }
        finally { operations.Release(); }
    }

    public async Task<Uri> BrowserUriAsync()
    {
        if (Snapshot.State != EngineState.Ready) throw new IOException("The engine is not ready.");
        using var client = new EngineClient(configuration.State);
        return await client.BrowserUriAsync();
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

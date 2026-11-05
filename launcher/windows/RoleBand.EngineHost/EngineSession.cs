using System.ComponentModel;
using System.Diagnostics;
using System.Runtime.InteropServices;
using System.Text;
using System.Text.Json;

namespace RoleBand.EngineHost;

public enum EngineState { Stopped, Starting, Preparing, Ready, Recovering, Stopping, Attention }
public sealed record EngineSnapshot(EngineState State, string? Diagnostic = null, int? ProcessId = null);

public sealed class EngineSession : IAsyncDisposable
{
    private readonly EngineConfiguration configuration;
    private readonly SemaphoreSlim operations = new(1);
    private FileStream? lease;
    private Process? process;
    private readonly List<Process> ownedProcesses = [];
    private CancellationTokenSource? stopping;
    private Task? monitor;
    private EngineSnapshot snapshot = new(EngineState.Stopped);
    public EngineSnapshot Snapshot => Volatile.Read(ref snapshot);
    public bool OwnsEngine => lease is not null;
    public event Action<EngineSnapshot>? Changed;

    public EngineSession(EngineConfiguration configuration) => this.configuration = configuration;

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
            RefuseLivePredecessor();
            stopping = new CancellationTokenSource();
            Publish(EngineState.Starting);
            monitor = MonitorAsync(stopping.Token);
        }
        catch (Exception error)
        {
            lease?.Dispose();
            lease = null;
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
        if (root.GetProperty("format").GetInt32() != 1
            || !Path.GetFullPath(root.GetProperty("resources").GetString()!).Equals(configuration.Resources, StringComparison.OrdinalIgnoreCase)
            || !Path.GetFullPath(root.GetProperty("state").GetString()!).Equals(configuration.State, StringComparison.OrdinalIgnoreCase))
            throw new IOException("A different installation owns this engine record.");
        Process candidate;
        try { candidate = Process.GetProcessById(root.GetProperty("pid").GetInt32()); }
        catch (ArgumentException) { return; }
        using (candidate)
        {
            var began = new DateTimeOffset(candidate.StartTime.ToUniversalTime()).ToUnixTimeMilliseconds() / 1000.0;
            if (!candidate.HasExited && Math.Abs(began - root.GetProperty("started").GetDouble()) < 0.002)
                throw new IOException("The previous engine is still closing or another app owns it.");
        }
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
        var backoff = 1;
        try
        {
            while (!cancellation.IsCancellationRequested)
            {
                var marker = Guid.NewGuid().ToString("N");
                process = Spawn(marker);
                ownedProcesses.Add(process);
                var output = DrainAsync(process.StandardOutput);
                var errors = DrainAsync(process.StandardError);
                var began = AwakeSeconds();
                var lastPreparation = began;
                var wasReady = false;
                var failures = 0;
                string? lastFailure = null;
                while (!cancellation.IsCancellationRequested && !process.HasExited)
                {
                    try
                    {
                        VerifyOwnedRecord(marker);
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
                        else
                        {
                            if (preparation.GetProperty("database").GetString() == "failed" || preparation.GetProperty("service").GetString() == "failed")
                            {
                                Publish(EngineState.Attention, "Engine preparation failed. The preparation log contains details.");
                                return;
                            }
                            lastPreparation = AwakeSeconds();
                            Publish(EngineState.Preparing);
                        }
                    }
                    catch (Exception error) when (error is IOException or HttpRequestException or JsonException or KeyNotFoundException or TaskCanceledException)
                    {
                        if (cancellation.IsCancellationRequested) break;
                        var failure = error.GetType().Name + ": " + error.Message;
                        if (failure != lastFailure)
                            lock (configuration) File.AppendAllText(Path.Combine(configuration.State, "logs", "desktop.log"),
                                failure + Environment.NewLine, Encoding.UTF8);
                        lastFailure = failure;
                        failures++;
                        if ((wasReady && failures >= 3) || (!wasReady && AwakeSeconds() - lastPreparation > 60)) break;
                    }
                    if (AwakeSeconds() - began > 1920 && !wasReady) break;
                    await Task.Delay(TimeSpan.FromSeconds(1), cancellation);
                }
                if (!process.HasExited)
                {
                    await process.StandardInput.WriteLineAsync("stop");
                    await process.StandardInput.FlushAsync();
                    using var timeout = new CancellationTokenSource(TimeSpan.FromSeconds(90));
                    try { await process.WaitForExitAsync(timeout.Token); }
                    catch (OperationCanceledException)
                    {
                        Publish(EngineState.Attention, "The engine has not confirmed a clean stop. Its process was preserved.");
                        return;
                    }
                }
                await Task.WhenAll(output, errors);
                process = null;
                if (cancellation.IsCancellationRequested) break;
                var now = AwakeSeconds();
                while (restarts.TryPeek(out var previous) && now - previous > 600) restarts.Dequeue();
                if (restarts.Count >= 3)
                {
                    Publish(EngineState.Attention, "Automatic recovery reached its limit. The engine log contains details.");
                    return;
                }
                restarts.Enqueue(now);
                Publish(EngineState.Recovering);
                await Task.Delay(TimeSpan.FromSeconds(backoff), cancellation);
                backoff = Math.Min(backoff * 2, 60);
            }
        }
        catch (OperationCanceledException) when (cancellation.IsCancellationRequested) { }
        catch (Exception error) { Publish(EngineState.Attention, error.Message); }
        finally
        {
            if (process is null)
            {
                lease?.Dispose();
                lease = null;
                if (cancellation.IsCancellationRequested) Publish(EngineState.Stopped);
            }
        }
    }

    private void VerifyOwnedRecord(string marker)
    {
        using var record = JsonDocument.Parse(PrivateStorage.Read(Path.Combine(configuration.State, "launcher", "owned-engine.json")));
        var root = record.RootElement;
        if (process is null || root.GetProperty("pid").GetInt32() != process.Id || root.GetProperty("marker").GetString() != marker
            || !Path.GetFullPath(root.GetProperty("resources").GetString()!).Equals(configuration.Resources, StringComparison.OrdinalIgnoreCase))
            throw new IOException("The engine process did not publish its owned identity.");
    }

    private async Task DrainAsync(StreamReader reader)
    {
        var path = Path.Combine(configuration.State, "logs", "desktop.log");
        while (await reader.ReadLineAsync() is { } line)
            lock (configuration) File.AppendAllText(path, line + Environment.NewLine, Encoding.UTF8);
    }

    public async Task StopAsync()
    {
        await operations.WaitAsync();
        try
        {
            stopping?.Cancel();
            if (process is { HasExited: false })
            {
                Publish(EngineState.Stopping);
                await process.StandardInput.WriteLineAsync("stop");
                await process.StandardInput.FlushAsync();
                using var timeout = new CancellationTokenSource(TimeSpan.FromSeconds(90));
                await process.WaitForExitAsync(timeout.Token);
            }
            if (monitor is not null) await monitor;
            foreach (var owned in ownedProcesses) owned.Dispose();
            ownedProcesses.Clear();
            process = null;
            lease?.Dispose();
            lease = null;
            stopping?.Dispose();
            stopping = null;
            Publish(EngineState.Stopped);
        }
        catch (Exception error) { Publish(EngineState.Attention, error.Message); throw; }
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

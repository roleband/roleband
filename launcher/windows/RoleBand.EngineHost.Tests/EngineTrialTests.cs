using System.Diagnostics;
using System.Text.Json;
using Microsoft.VisualStudio.TestTools.UnitTesting;

namespace RoleBand.EngineHost.Tests;

[TestClass]
public sealed class EngineTrialTests
{
    [TestMethod]
    public async Task SourceEngineAuthenticatesPreparesAndStopsWithoutLosingFixture()
    {
        var checkout = new DirectoryInfo(AppContext.BaseDirectory);
        while (!File.Exists(Path.Combine(checkout.FullName, "backend", "desktop.py")))
            checkout = checkout.Parent ?? throw new IOException("Source checkout not found.");
        var state = Path.Combine(Path.GetTempPath(), "roleband-desktop-tests", Guid.NewGuid().ToString("N"));
        var configuration = EngineConfiguration.Source(checkout.FullName, state, fixture: true);
        await Exercise(configuration);
    }

    [TestMethod]
    public async Task BundledEngineStartsWithoutDeveloperPythonAndRetainsFixture()
    {
        var resources = Environment.GetEnvironmentVariable("ROLEBAND_WINDOWS_TRIAL_RESOURCES");
        if (resources is null) Assert.Inconclusive("Set ROLEBAND_WINDOWS_TRIAL_RESOURCES to an assembled trial's Resources directory.");
        var state = Path.Combine(Path.GetTempPath(), "roleband-bundle-tests", Guid.NewGuid().ToString("N"));
        var configuration = EngineConfiguration.Packaged(resources, state, fixture: true);
        Assert.IsFalse(configuration.Development);
        Assert.AreEqual(Path.GetFullPath(Path.Combine(resources, "runtime", "python.exe")), configuration.NativePython);
        var defaultTrial = EngineConfiguration.Packaged(resources);
        Assert.IsTrue(defaultTrial.SyntheticFixture);
        Assert.IsTrue(defaultTrial.State.StartsWith(Path.Combine(KnownFolders.LocalAppData,
            "RoleBandTrials") + Path.DirectorySeparatorChar, StringComparison.OrdinalIgnoreCase));
        await Exercise(configuration);
    }

    private static async Task Exercise(EngineConfiguration configuration)
    {
        var state = configuration.State;
        PrivateStorage.EnsureDirectory(state);
        PrivateStorage.EnsureDirectory(Path.Combine(state, "launcher"));
        using (var predecessor = Process.Start(new ProcessStartInfo(Path.Combine(
            Environment.GetFolderPath(Environment.SpecialFolder.System), "hostname.exe"))
            { UseShellExecute = false, CreateNoWindow = true, RedirectStandardOutput = true })
            ?? throw new IOException("Could not create the predecessor fixture."))
        {
            var pid = predecessor.Id;
            var began = new DateTimeOffset(predecessor.StartTime.ToUniversalTime()).ToUnixTimeMilliseconds() / 1000.0;
            await predecessor.WaitForExitAsync();
            File.WriteAllText(Path.Combine(state, "launcher", "owned-engine.json"), JsonSerializer.Serialize(new
            {
                format = 1, pid, started = began, state,
                resources = Path.Combine(state, "previous-package", "Resources"),
            }));
        }
        await using var session = new EngineSession(configuration);
        await session.StartAsync();
        var deadline = Stopwatch.StartNew();
        while (session.Snapshot.State != EngineState.Ready && deadline.Elapsed < TimeSpan.FromSeconds(120))
        {
            Assert.AreNotEqual(EngineState.Attention, session.Snapshot.State, session.Snapshot.Diagnostic);
            await Task.Delay(100);
        }
        Assert.AreEqual(EngineState.Ready, session.Snapshot.State, ReadLog(state));
        await using (var second = new EngineSession(configuration))
        {
            await second.StartAsync();
            Assert.AreEqual(EngineState.Attention, second.Snapshot.State);
            Assert.IsFalse(second.OwnsEngine);
        }
        int total;
        using (var client = new EngineClient(state))
        using (var jobs = await client.RequestAsync(HttpMethod.Get, "/api/jobs?limit=20"))
            total = jobs.RootElement.GetProperty("total").GetInt32();
        Assert.IsGreaterThan(0, total);
        var browser = await session.BrowserUriAsync();
        Assert.IsTrue(browser.Host.EndsWith(".localhost", StringComparison.Ordinal));
        Assert.IsTrue(browser.Fragment.StartsWith("#roleband=", StringComparison.Ordinal));
        await session.StopAsync();
        Assert.IsFalse(File.Exists(Path.Combine(state, "db", "postmaster.pid")));
        Assert.IsTrue(File.Exists(Path.Combine(state, "db", "PG_VERSION")));
        Assert.IsFalse(File.Exists(Path.Combine(state, "launcher", "http-engine.json")));
        Assert.IsFalse(File.Exists(Path.Combine(state, "launcher", "owned-engine.json")));
        await session.StartAsync();
        deadline.Restart();
        while (session.Snapshot.State != EngineState.Ready && deadline.Elapsed < TimeSpan.FromSeconds(120))
        {
            Assert.AreNotEqual(EngineState.Attention, session.Snapshot.State, session.Snapshot.Diagnostic);
            await Task.Delay(100);
        }
        Assert.AreEqual(EngineState.Ready, session.Snapshot.State, ReadLog(state));
        using var resumed = new EngineClient(state);
        using var retained = await resumed.RequestAsync(HttpMethod.Get, "/api/jobs?limit=20");
        Assert.AreEqual(total, retained.RootElement.GetProperty("total").GetInt32());
        var previous = session.Snapshot.ProcessId ?? throw new IOException("No owned engine PID.");
        using (var crashed = Process.GetProcessById(previous))
        {
            crashed.Kill();
            await crashed.WaitForExitAsync();
        }
        deadline.Restart();
        while ((session.Snapshot.State != EngineState.Ready || session.Snapshot.ProcessId == previous)
               && deadline.Elapsed < TimeSpan.FromSeconds(120))
        {
            Assert.AreNotEqual(EngineState.Attention, session.Snapshot.State, session.Snapshot.Diagnostic);
            await Task.Delay(100);
        }
        Assert.AreEqual(EngineState.Ready, session.Snapshot.State, ReadLog(state));
        Assert.AreNotEqual(previous, session.Snapshot.ProcessId);
        using var recovered = new EngineClient(state);
        using var afterCrash = await recovered.RequestAsync(HttpMethod.Get, "/api/jobs?limit=20");
        Assert.AreEqual(total, afterCrash.RootElement.GetProperty("total").GetInt32());
    }

    private static string ReadLog(string state)
    {
        var path = Path.Combine(state, "logs", "desktop.log");
        return File.Exists(path) ? File.ReadAllText(path) : "No desktop log was written.";
    }
}

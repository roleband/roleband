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
        await ExerciseScanTab(session);
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

    /// <summary>The Scan tab against the engine itself: its status reply, a pause and resume through the
    /// schedule plan, and a handoff that opens New. Scan now is left out: it would read real job boards.</summary>
    private static async Task ExerciseScanTab(EngineSession session)
    {
        using var client = session.Connect();
        var status = await ScanStatus.ReadAsync(client);
        Assert.IsNotNull(status.Queue, "the engine reports its scan queue");
        Assert.IsNotNull(status.Picture, "the engine sends its scan picture");
        var plan = status.Picture.Schedule ?? throw new AssertFailedException("The engine does not say how scans start.");
        foreach (var language in new[] { "en", "es", "zh-Hans" })
            _ = ScanPanel.View(new NativeCopy(language), session.Snapshot, status, null, DateTimeOffset.UtcNow);
        Assert.IsTrue(plan.Pausable, "the synthetic engine scans on the schedule plan");
        Assert.IsFalse(plan.IsPaused(DateTimeOffset.UtcNow));
        var zone = ScanControl.LocalTimezone();
        var paused = await ScanControl.PauseAsync(client, PauseAction.Hour, zone, () => DateTimeOffset.UtcNow);
        var seen = (await ScanStatus.ReadAsync(client)).Picture?.Schedule;
        Assert.AreEqual(paused.PausedUntil, seen?.PausedUntil, "the status reports the pause the schedule took");
        Assert.AreEqual(PauseControl.Resume,
            ScanPanel.View(new NativeCopy("en"), session.Snapshot, await ScanStatus.ReadAsync(client), null, DateTimeOffset.UtcNow).Pause);
        await Assert.ThrowsExactlyAsync<ControlStateChangedException>(
            () => ScanControl.PauseAsync(client, PauseAction.Tomorrow, zone, () => DateTimeOffset.UtcNow));
        Assert.IsNull((await ScanControl.PauseAsync(client, PauseAction.Resume, zone, () => DateTimeOffset.UtcNow)).PausedUntil);
        Assert.IsNull((await ScanStatus.ReadAsync(client)).Picture?.Schedule?.PausedUntil);
        // A zone the engine cannot read is refused, never stored.
        await Assert.ThrowsExactlyAsync<IOException>(
            () => ScanControl.PauseAsync(client, PauseAction.Hour, "Nowhere/Atlantis", () => DateTimeOffset.UtcNow));
        var newRoles = await session.BrowserUriAsync(BrowserRoute.NewRoles);
        Assert.AreEqual("/?lens=new", newRoles.PathAndQuery);
        Assert.IsTrue(newRoles.Fragment.StartsWith("#roleband=", StringComparison.Ordinal));
    }

    private static string ReadLog(string state)
    {
        var path = Path.Combine(state, "logs", "desktop.log");
        return File.Exists(path) ? File.ReadAllText(path) : "No desktop log was written.";
    }
}

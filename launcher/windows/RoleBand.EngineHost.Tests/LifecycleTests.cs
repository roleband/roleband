using System.Diagnostics;
using System.Text.Json;
using System.Text.RegularExpressions;
using Microsoft.VisualStudio.TestTools.UnitTesting;

namespace RoleBand.EngineHost.Tests;

// EngineSession against a real stand-in engine process. The stand-in uses the engine's own
// owned-record publication, private discovery and authenticated health responder; only
// its behaviour (slow health, ignored stop, failed preparation, crash) is chosen per test.
[TestClass]
public sealed class LifecycleTests
{
    private const string Script = """
        import json, os, sys, time
        from pathlib import Path

        HERE = Path(__file__).resolve().parent
        behaviour = json.loads((HERE / "behaviour.json").read_text(encoding="utf-8"))
        sys.path.insert(0, behaviour["backend"])
        os.environ["ROLEBAND_LOCAL_AUTH"] = "1"

        import psutil
        from tracker.platform import preparation
        from tracker.platform.paths import DATA_DIR
        from tracker.platform.windows_fs import publish
        from tracker.supervisor import prepare

        mode = behaviour["mode"]

        def note(text):
            with (HERE / "events.log").open("a", encoding="utf-8") as stream:
                stream.write(text + "\n")

        marker = sys.argv[sys.argv.index("--marker") + 1]
        record = {"format": 1, "pid": os.getpid(), "started": psutil.Process().create_time(), "executable": sys.executable,
                  "resources": str(HERE.parent), "state": str(DATA_DIR), "marker": marker}
        publish(DATA_DIR / "launcher" / "owned-engine.json", json.dumps(record).encode())
        failed = mode == "prepare-fail"
        preparation.update(DATA_DIR, database="failed" if failed else "ready", service="failed" if failed else "ready",
                           model="unused", reason="service_failed" if failed else None)
        if mode == "slow-health":
            real = prepare.health

            def slow(**arguments):
                note("health-begin")
                time.sleep(1.5)
                note("health-end")
                return real(**arguments)

            prepare.health = slow
        for _ in range(behaviour["noise"]):
            print("x" * 100, flush=True)
        note("started")
        with prepare.PreparationServer("127.0.0.1", 0):
            if mode == "crash":
                time.sleep(1.5)
                note("crashed")
                os._exit(3)
            for line in sys.stdin:
                note("stdin " + line.strip())
                if line.strip() == "stop" and mode != "ignore-stop":
                    break
        note("exited")
        """;

    private sealed class StandIn
    {
        public string Root { get; }
        public string State { get; }
        public EngineConfiguration Configuration { get; }

        public StandIn(string mode, int noise = 0)
        {
            var checkout = new DirectoryInfo(AppContext.BaseDirectory);
            while (!File.Exists(Path.Combine(checkout.FullName, "backend", "desktop.py")))
                checkout = checkout.Parent ?? throw new IOException("Source checkout not found.");
            var scratch = Path.Combine(Path.GetTempPath(), "roleband-lifecycle-tests", Guid.NewGuid().ToString("N"));
            Root = Path.Combine(scratch, "resources");
            State = Path.Combine(scratch, "state");
            Directory.CreateDirectory(Path.Combine(Root, "backend"));
            File.WriteAllText(Path.Combine(Root, "backend", "desktop.py"), Script);
            Behave(mode, noise, checkout.FullName);
            var python = Path.Combine(checkout.FullName, "backend", ".venv", "Scripts", "python.exe");
            var native = File.ReadAllLines(Path.Combine(checkout.FullName, "backend", ".venv", "pyvenv.cfg"))
                .Select(line => line.Split('=', 2)).Where(parts => parts.Length == 2 && parts[0].Trim() == "executable")
                .Select(parts => parts[1].Trim()).Single();
            using var package = JsonDocument.Parse(File.ReadAllBytes(Path.Combine(checkout.FullName, "dashboard", "package.json")));
            Configuration = new EngineConfiguration(Root, State, python, native,
                package.RootElement.GetProperty("version").GetString()!, true, false);
        }

        public void Behave(string mode, int noise = 0, string? checkout = null)
        {
            var path = Path.Combine(Root, "backend", "behaviour.json");
            checkout ??= Path.GetDirectoryName(JsonDocument.Parse(File.ReadAllText(path)).RootElement.GetProperty("backend").GetString())!;
            File.WriteAllText(path, JsonSerializer.Serialize(new { backend = Path.Combine(checkout, "backend"), mode, noise }));
        }

        public string[] Events()
        {
            var path = Path.Combine(Root, "backend", "events.log");
            return File.Exists(path) ? File.ReadAllLines(path) : [];
        }
    }

    private static readonly EngineSessionOptions Quick = EngineSessionOptions.Default with
    {
        StopTimeout = TimeSpan.FromSeconds(3), FirstBackoff = TimeSpan.FromMilliseconds(50),
    };

    private static async Task Until(Func<bool> condition, TimeSpan limit, string what)
    {
        var watch = Stopwatch.StartNew();
        while (!condition())
        {
            if (watch.Elapsed > limit) Assert.Fail($"Timed out waiting for {what}.");
            await Task.Delay(50);
        }
    }

    [TestMethod]
    public async Task StopDuringAHealthRequestAsksTheEngineToStopOnce()
    {
        var engine = new StandIn("slow-health");
        await using var session = new EngineSession(engine.Configuration, Quick);
        await session.StartAsync();
        await Until(() => session.Snapshot.State == EngineState.Ready, TimeSpan.FromSeconds(90), "Ready");
        var settled = engine.Events().Count(line => line == "health-end");
        await Until(() => engine.Events().Count(line => line == "health-begin") > settled, TimeSpan.FromSeconds(10), "a health request");
        await session.StopAsync();
        Assert.AreEqual(EngineState.Stopped, session.Snapshot.State);
        Assert.IsFalse(session.OwnsEngine);
        Assert.AreEqual(1, engine.Events().Count(line => line == "stdin stop"));
        Assert.AreEqual("exited", engine.Events().Last());
    }

    [TestMethod]
    public async Task AnUnconfirmedStopPreservesTheEngineAndTheLease()
    {
        var engine = new StandIn("ignore-stop");
        await using var session = new EngineSession(engine.Configuration, Quick);
        await session.StartAsync();
        await Until(() => session.Snapshot.State == EngineState.Ready, TimeSpan.FromSeconds(90), "Ready");
        await session.StopAsync();
        Assert.AreEqual(EngineState.Attention, session.Snapshot.State);
        Assert.IsTrue(session.OwnsEngine);
        var pid = session.Snapshot.ProcessId ?? throw new AssertFailedException("The preserved engine has no process ID.");
        Assert.ThrowsExactly<IOException>(() => PrivateStorage.Lease(engine.State, "desktop.lock"));
        await session.StopAsync();
        Assert.AreEqual(EngineState.Attention, session.Snapshot.State);
        Assert.AreEqual(1, engine.Events().Count(line => line == "stdin stop"), "the stop request is sent once per engine");
        using (var preserved = Process.GetProcessById(pid))
        {
            preserved.Kill();
            await preserved.WaitForExitAsync();
        }
        await session.StopAsync();
        Assert.AreEqual(EngineState.Stopped, session.Snapshot.State);
        Assert.IsFalse(session.OwnsEngine);
    }

    [TestMethod]
    public async Task FailedPreparationEndsTheEngineAndOneStartRetries()
    {
        var engine = new StandIn("prepare-fail");
        await using var session = new EngineSession(engine.Configuration, Quick);
        await session.StartAsync();
        await Until(() => session.Snapshot.State == EngineState.Attention, TimeSpan.FromSeconds(90), "Attention");
        StringAssert.Contains(session.Snapshot.Diagnostic!, "preparation failed");
        Assert.IsFalse(session.OwnsEngine);
        Assert.IsNull(session.Snapshot.ProcessId);
        Assert.AreEqual("exited", engine.Events().Last());
        engine.Behave("ready");
        await session.StartAsync();
        await Until(() => session.Snapshot.State == EngineState.Ready, TimeSpan.FromSeconds(90), "Ready after retry");
        await session.StopAsync();
        Assert.AreEqual(EngineState.Stopped, session.Snapshot.State);
    }

    [TestMethod]
    public async Task RepeatedCrashesReachTheRestartLimitAndReleaseTheLease()
    {
        var engine = new StandIn("crash");
        await using var session = new EngineSession(engine.Configuration, Quick);
        await session.StartAsync();
        await Until(() => session.Snapshot.State == EngineState.Attention, TimeSpan.FromSeconds(120), "the restart limit");
        StringAssert.Contains(session.Snapshot.Diagnostic!, "reached its limit");
        Assert.AreEqual(Quick.RestartLimit + 1, engine.Events().Count(line => line == "started"));
        Assert.IsFalse(session.OwnsEngine);
        using var lease = PrivateStorage.Lease(engine.State, "desktop.lock");
    }

    [TestMethod]
    public async Task OnlyARunningProcessWithTheRecordedStartBlocksAStart()
    {
        var engine = new StandIn("ready");
        PrivateStorage.EnsureDirectory(engine.State);
        PrivateStorage.EnsureDirectory(Path.Combine(engine.State, "launcher"));
        var began = ProcessClock.RunningSince(Environment.ProcessId) ?? throw new AssertFailedException("No start time.");
        var record = Path.Combine(engine.State, "launcher", "owned-engine.json");
        void Record(double started) => File.WriteAllText(record, JsonSerializer.Serialize(new
        {
            format = 1, pid = Environment.ProcessId, started, state = engine.State, resources = engine.Root,
        }));
        await using var session = new EngineSession(engine.Configuration, Quick);
        Record(began);
        await session.StartAsync();
        Assert.AreEqual(EngineState.Attention, session.Snapshot.State);
        StringAssert.Contains(session.Snapshot.Diagnostic!, "still closing");
        Assert.IsFalse(session.OwnsEngine);
        Record(began - 60);
        await session.StartAsync();
        await Until(() => session.Snapshot.State == EngineState.Ready, TimeSpan.FromSeconds(90), "Ready beside a recycled ID");
        await session.StopAsync();
    }

    [TestMethod]
    public async Task TheHostLogIsTimestampedAndKeepsOnePreviousCopy()
    {
        var engine = new StandIn("ready", noise: 400);
        var options = Quick with { LogLimitBytes = 8 * 1024 };
        await using var session = new EngineSession(engine.Configuration, options);
        await session.StartAsync();
        await Until(() => session.Snapshot.State == EngineState.Ready, TimeSpan.FromSeconds(90), "Ready");
        await session.StopAsync();
        var current = Path.Combine(engine.State, "logs", "desktop.log");
        var previous = current + ".1";
        Assert.IsTrue(File.Exists(previous), "the log rotated");
        foreach (var path in new[] { current, previous })
        {
            Assert.IsTrue(new FileInfo(path).Length <= options.LogLimitBytes);
            foreach (var line in File.ReadAllLines(path))
                Assert.IsTrue(Regex.IsMatch(line, @"\A\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d\.\d{3}[+-]\d\d:\d\d "), line);
        }
        CollectionAssert.AreEquivalent(new[] { "desktop.log", "desktop.log.1" },
            Directory.EnumerateFiles(Path.Combine(engine.State, "logs")).Select(Path.GetFileName)
                .Where(name => name!.StartsWith("desktop", StringComparison.Ordinal)).ToArray());
    }

    private sealed class RecordingCommands(Func<bool> engineRunning, params (string Action, string Answer)[] answers) : IUpdateCommands
    {
        public List<string> Calls { get; } = [];
        public List<bool> EngineRunningAt { get; } = [];

        public Task<JsonElement> RunAsync(IReadOnlyList<string> arguments, CancellationToken cancellation)
        {
            Calls.Add(string.Join(' ', arguments));
            EngineRunningAt.Add(engineRunning());
            var answer = answers.FirstOrDefault(item => item.Action == arguments[0]).Answer ?? "{}";
            using var document = JsonDocument.Parse(answer);
            return Task.FromResult(document.RootElement.Clone());
        }
    }

    private sealed class RecordingDeployer(Exception? failure = null) : IPackageDeployer
    {
        public List<string> Packages { get; } = [];

        public Task AddAsync(string package, CancellationToken cancellation)
        {
            Packages.Add(package);
            return failure is null ? Task.CompletedTask : Task.FromException(failure);
        }
    }

    private const string Package = @"C:\state\packages\RoleBand-0.9.0-Windows-x64.msix";

    [TestMethod]
    public async Task AnUpdateIsJournaledOnlyAfterTheEngineStoppedAndThenSwitched()
    {
        var engine = new StandIn("ready");
        await using var session = new EngineSession(engine.Configuration, Quick);
        await session.StartAsync();
        await Until(() => session.Snapshot.State == EngineState.Ready, TimeSpan.FromSeconds(90), "Ready");
        var commands = new RecordingCommands(() => session.OwnsEngine, ("begin", """{"phase": "applying"}"""));
        var deployer = new RecordingDeployer();
        await new UpdateCoordinator(commands, deployer).ApplyAsync(session, Package);
        CollectionAssert.AreEqual(new[] { "begin --package " + Package }, commands.Calls);
        CollectionAssert.AreEqual(new[] { false }, commands.EngineRunningAt);
        CollectionAssert.AreEqual(new[] { Package }, deployer.Packages);
        Assert.AreEqual("exited", engine.Events().Last());
    }

    [TestMethod]
    public async Task ARefusedJournalNeverSwitchesThePackage()
    {
        var engine = new StandIn("ready");
        await using var session = new EngineSession(engine.Configuration, Quick);
        var commands = new RecordingCommands(() => session.OwnsEngine,
            ("begin", """{"status": "refused", "reason": "The package is not a verified retained update."}"""));
        var deployer = new RecordingDeployer();
        var error = await Assert.ThrowsExactlyAsync<IOException>(() => new UpdateCoordinator(commands, deployer).ApplyAsync(session, Package));
        StringAssert.Contains(error.Message, "not a verified retained update");
        Assert.AreEqual(0, deployer.Packages.Count);
    }

    [TestMethod]
    public async Task ASwitchWindowsRefusedIsRecordedAsNeverHappened()
    {
        var engine = new StandIn("ready");
        await using var session = new EngineSession(engine.Configuration, Quick);
        var commands = new RecordingCommands(() => session.OwnsEngine, ("begin", """{"phase": "applying"}"""),
            ("resume", """{"phase": "aborted"}"""));
        var deployer = new RecordingDeployer(new IOException("0x80073CF3 package conflict"));
        await Assert.ThrowsExactlyAsync<IOException>(() => new UpdateCoordinator(commands, deployer).ApplyAsync(session, Package));
        CollectionAssert.AreEqual(new[] { "begin --package " + Package, "resume" }, commands.Calls);
    }

    [TestMethod]
    public async Task TheNewVersionCompletesTheUpdateOnceItIsReady()
    {
        var engine = new StandIn("ready");
        await using var session = new EngineSession(engine.Configuration, Quick);
        var commands = new RecordingCommands(() => session.OwnsEngine, ("resume", """{"phase": "preparing"}"""),
            ("settle", """{"phase": "complete"}"""));
        var phase = await new UpdateCoordinator(commands, new RecordingDeployer()).StartAsync(session);
        Assert.AreEqual("complete", phase);
        Assert.AreEqual(EngineState.Ready, session.Snapshot.State);
        CollectionAssert.AreEqual(new[] { "resume", "settle --prepared yes" }, commands.Calls);
        CollectionAssert.AreEqual(new[] { false, true }, commands.EngineRunningAt, "resume runs before the engine starts");
    }

    [TestMethod]
    public async Task ANewVersionThatCannotPrepareMarksTheUpdateFailed()
    {
        var engine = new StandIn("prepare-fail");
        await using var session = new EngineSession(engine.Configuration, Quick);
        var commands = new RecordingCommands(() => session.OwnsEngine, ("resume", """{"phase": "preparing"}"""),
            ("settle", """{"phase": "failed"}"""));
        var phase = await new UpdateCoordinator(commands, new RecordingDeployer()).StartAsync(session);
        Assert.AreEqual("failed", phase);
        Assert.IsTrue(session.PreparationFailed);
        CollectionAssert.AreEqual(new[] { "resume", "settle --prepared no" }, commands.Calls);
    }

    [TestMethod]
    public async Task AnOrdinaryStartSettlesNothing()
    {
        var engine = new StandIn("ready");
        await using var session = new EngineSession(engine.Configuration, Quick);
        var commands = new RecordingCommands(() => session.OwnsEngine, ("resume", """{"phase": "complete"}"""));
        Assert.AreEqual("complete", await new UpdateCoordinator(commands, new RecordingDeployer()).StartAsync(session));
        CollectionAssert.AreEqual(new[] { "resume" }, commands.Calls);
        await session.StopAsync();
    }
}

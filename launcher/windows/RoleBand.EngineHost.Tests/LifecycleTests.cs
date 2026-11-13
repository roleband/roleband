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

        if mode == "download" and "update" in sys.argv:
            import subprocess
            child = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(120)"])
            note(f"child {child.pid}")
            for received in (0, 150, 300):
                print(json.dumps({"received": received, "total": 300}), file=sys.stderr, flush=True)
            print("not a progress line", file=sys.stderr, flush=True)
            time.sleep(120)
            sys.exit(0)
        if mode == "slow-command" and "update" in sys.argv:
            note("command-begin")
            time.sleep(3)
            note("command-end")
            print(json.dumps({"phase": "recovered"}), flush=True)
            sys.exit(0)
        if mode == "exit-early":
            note("started")
            os._exit(3)
        marker = sys.argv[sys.argv.index("--marker") + 1]
        record = {"format": 1, "pid": os.getpid(), "started": psutil.Process().create_time(), "executable": sys.executable,
                  "resources": str(HERE.parent), "state": str(DATA_DIR), "marker": marker}
        publish(DATA_DIR / "launcher" / "owned-engine.json", json.dumps(record).encode())
        if mode == "silent":
            note("started")
            for line in sys.stdin:
                note("stdin " + line.strip())
                if line.strip() == "stop":
                    break
            note("exited")
            sys.exit(0)
        if mode == "holds-output":
            import subprocess
            child = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(120)"], stdout=sys.stdout, stderr=sys.stderr)
            note(f"child {child.pid}")
        failed = mode == "prepare-fail"
        if mode in ("stuck", "progressing"):
            preparation.update(DATA_DIR, database="creating", service="starting", model="downloading", downloaded_bytes=0,
                               total_bytes=100, reason=None)
        else:
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
        if mode == "malformed-health":
            real = prepare.health
            answers = {"count": 0}

            def malformed(**arguments):
                answer = real(**arguments)
                answers["count"] += 1
                if answers["count"] <= 2:
                    note("health-malformed")
                    big = 10 ** 30
                    answer = {**answer, "preparation": {"format": 1, "database": "ready", "model": "unused",
                              "service": "ready", "downloaded_bytes": big, "total_bytes": big, "reason": None}}
                return answer

            prepare.health = malformed
        if mode == "malformed-after-ready":
            real = prepare.health
            answers = {"count": 0}

            def flaky(**arguments):
                answer = real(**arguments)
                answers["count"] += 1
                if 1 < answers["count"] <= 1 + behaviour["bad"]:
                    note("health-malformed")
                    big = 10 ** 30
                    return {**answer, "preparation": {"format": 1, "database": "ready", "model": "unused",
                            "service": "ready", "downloaded_bytes": big, "total_bytes": big, "reason": None}}
                if answers["count"] > 1:
                    note("health-good")
                return answer

            prepare.health = flaky
        for _ in range(behaviour["noise"]):
            print("x" * 100, flush=True)
        note("started")
        with prepare.PreparationServer("127.0.0.1", 0):
            if mode == "crash":
                time.sleep(1.5)
                note("crashed")
                os._exit(3)
            if mode == "progressing":
                for received in range(3, 91, 3):
                    time.sleep(0.3)
                    preparation.update(DATA_DIR, downloaded_bytes=received)
                preparation.update(DATA_DIR, database="ready", service="ready", model="ready")
                note("prepared")
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

        public StandIn(string mode, int noise = 0, int bad = 0)
        {
            var checkout = new DirectoryInfo(AppContext.BaseDirectory);
            while (!File.Exists(Path.Combine(checkout.FullName, "backend", "desktop.py")))
                checkout = checkout.Parent ?? throw new IOException("Source checkout not found.");
            var scratch = Path.Combine(Path.GetTempPath(), "roleband-lifecycle-tests", Guid.NewGuid().ToString("N"));
            Root = Path.Combine(scratch, "resources");
            State = Path.Combine(scratch, "state");
            Directory.CreateDirectory(Path.Combine(Root, "backend"));
            File.WriteAllText(Path.Combine(Root, "backend", "desktop.py"), Script);
            Behave(mode, noise, checkout.FullName, bad);
            var python = Path.Combine(checkout.FullName, "backend", ".venv", "Scripts", "python.exe");
            var native = File.ReadAllLines(Path.Combine(checkout.FullName, "backend", ".venv", "pyvenv.cfg"))
                .Select(line => line.Split('=', 2)).Where(parts => parts.Length == 2 && parts[0].Trim() == "executable")
                .Select(parts => parts[1].Trim()).Single();
            using var package = JsonDocument.Parse(File.ReadAllBytes(Path.Combine(checkout.FullName, "dashboard", "package.json")));
            Configuration = new EngineConfiguration(Root, State, python, native,
                package.RootElement.GetProperty("version").GetString()!, true, false);
        }

        /// <param name="bad">For "malformed-after-ready": how many answers after the first are malformed.</param>
        public void Behave(string mode, int noise = 0, string? checkout = null, int bad = 0)
        {
            var path = Path.Combine(Root, "backend", "behaviour.json");
            checkout ??= Path.GetDirectoryName(JsonDocument.Parse(File.ReadAllText(path)).RootElement.GetProperty("backend").GetString())!;
            File.WriteAllText(path, JsonSerializer.Serialize(new { backend = Path.Combine(checkout, "backend"), mode, noise, bad }));
        }

        /// <summary>The stand-in's events so far. It appends while it runs, so the read shares writing with it; a line
        /// it is still writing is left for the next read.</summary>
        public string[] Events()
        {
            var path = Path.Combine(Root, "backend", "events.log");
            if (!File.Exists(path)) return [];
            using var stream = new FileStream(path, FileMode.Open, FileAccess.Read, FileShare.ReadWrite | FileShare.Delete);
            var text = new StreamReader(stream).ReadToEnd();
            return text[..(text.LastIndexOf('\n') + 1)].Split('\n', StringSplitOptions.RemoveEmptyEntries)
                .Select(line => line.TrimEnd('\r')).ToArray();
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
    public async Task CancelStopsADownloadAndEveryProcessItStartedAtOnce()
    {
        var engine = new StandIn("download");
        var coordinator = new UpdateCoordinator(new EngineUpdateCommands(engine.Configuration), new RecordingDeployer());
        var counted = new List<(long Received, long Total)>();
        var whole = new TaskCompletionSource(TaskCreationOptions.RunContinuationsAsynchronously);
        using var cancel = new CancellationTokenSource();
        var download = coordinator.DownloadAsync(new Inline<(long Received, long Total)>(value =>
        {
            lock (counted) counted.Add(value);
            if (value.Received == value.Total) whole.TrySetResult();
        }), cancel.Token);
        await whole.Task.WaitAsync(TimeSpan.FromSeconds(60));
        await Until(() => engine.Events().Any(line => line.StartsWith("child ", StringComparison.Ordinal)), TimeSpan.FromSeconds(10), "the child");
        var child = int.Parse(engine.Events().Single(line => line.StartsWith("child ", StringComparison.Ordinal))[6..],
            System.Globalization.CultureInfo.InvariantCulture);
        var clock = Stopwatch.StartNew();
        cancel.Cancel();
        await Assert.ThrowsAsync<OperationCanceledException>(() => download);
        Assert.IsTrue(clock.Elapsed < TimeSpan.FromSeconds(10), $"Cancel took {clock.Elapsed}");
        CollectionAssert.AreEqual(new[] { (0L, 300L), (150L, 300L), (300L, 300L) }, counted, "only progress lines count");
        await Until(() => !Running(child), TimeSpan.FromSeconds(10), "the download's own child to end");
    }

    [TestMethod]
    public async Task OnlyADownloadIsStoppedByCancelEveryOtherCommandRunsToItsEnd()
    {
        // A restore of the database, a resume or a settle stopped partway would leave the journal or the data half-changed.
        var engine = new StandIn("slow-command");
        using var cancel = new CancellationTokenSource();
        var recover = new EngineUpdateCommands(engine.Configuration).RunAsync(["recover"], cancel.Token);
        await Until(() => engine.Events().Contains("command-begin"), TimeSpan.FromSeconds(30), "the command to begin");
        cancel.Cancel();
        var answer = await recover.WaitAsync(TimeSpan.FromSeconds(30));
        Assert.AreEqual("recovered", answer.GetProperty("phase").GetString());
        CollectionAssert.Contains(engine.Events(), "command-end");
    }

    private static readonly LastUpdate Applying =
        new("applying", "0.8.0", "0.9.0", "from", DateTimeOffset.Now.AddMinutes(-2), "RoleBand-0.9.0-Windows-x64.msix");

    [TestMethod]
    public async Task AVersionOpenedWhileWindowsInstallsItsUpdateWaitsAndNeverSettlesAnInstalledOne()
    {
        var waits = new List<TimeSpan>();
        Task Wait(TimeSpan span, CancellationToken cancellation) { waits.Add(span); return Task.CompletedTask; }
        var deployer = new RecordingDeployer(null, new InstallFinding(InstallProgress.Running), new InstallFinding(InstallProgress.Running),
            new InstallFinding(InstallProgress.Finished));
        var commands = new RecordingCommands(() => false);
        var reported = new List<UpdateRun?>();
        var settle = await new UpdateCoordinator(commands, deployer, Wait).AwaitWindowsAsync(Applying, "RoleBand.Windows", reported.Add);
        Assert.IsFalse(settle, "Windows installed the new version, which settles the update when it opens");
        CollectionAssert.AreEqual(new[] { "find", "reopen", "find", "find" }, deployer.Steps,
            "asked to open the new version before the wait, or Windows closes this one and nothing opens");
        CollectionAssert.AreEqual(new UpdateRun?[] { new(UpdateStep.Installing, "0.9.0"), new(UpdateStep.Installing, "0.9.0"),
            new(UpdateStep.Installing, "0.9.0", Percent: 100) }, reported, "Installing, then Restarting to update, and it stays");
        CollectionAssert.AreEqual(new[] { UpdateCoordinator.InstallPoll, UpdateCoordinator.InstallPoll }, waits);
        Assert.AreEqual(0, commands.Calls.Count, "nothing touches the journal");
    }

    [TestMethod]
    public async Task AnInstallWindowsRefusedOrNeverBeganLeavesTheUpdateForThisVersionToSettle()
    {
        Task Wait(TimeSpan span, CancellationToken cancellation) => Task.CompletedTask;
        var refused = new RecordingDeployer(null, new InstallFinding(InstallProgress.Failed, "The disk is full."));
        var reported = new List<UpdateRun?>();
        Assert.IsTrue(await new UpdateCoordinator(new RecordingCommands(() => false), refused, Wait)
            .AwaitWindowsAsync(Applying, "RoleBand.Windows", reported.Add));
        Assert.AreEqual(new UpdateRun(UpdateStep.InstallFailed, "0.9.0", Reason: "The disk is full."), reported.Single());
        CollectionAssert.AreEqual(new[] { "find" }, refused.Steps, "nothing for Windows to open again");

        var never = new RecordingDeployer();
        reported.Clear();
        Assert.IsTrue(await new UpdateCoordinator(new RecordingCommands(() => false), never, Wait)
            .AwaitWindowsAsync(Applying, "RoleBand.Windows", reported.Add));
        CollectionAssert.AreEqual(new UpdateRun?[] { null }, reported);
    }

    private static bool Running(int pid)
    {
        try
        {
            using var process = Process.GetProcessById(pid);
            return !process.HasExited;
        }
        catch (ArgumentException) { return false; }
    }

    /// <summary>Reports on the caller's thread, so the test sees every value before the download ends.</summary>
    private sealed class Inline<T>(Action<T> report) : IProgress<T>
    {
        public void Report(T value) => report(value);
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

    [TestMethod]
    public async Task AHostLogThatCannotBeWrittenNeitherStallsTheEngineNorEndsItsWatch()
    {
        // The engine's output fills its pipe unless the host keeps reading it, log or no log.
        var engine = new StandIn("ready", noise: 400);
        PrivateStorage.EnsureDirectory(engine.State);
        PrivateStorage.EnsureDirectory(Path.Combine(engine.State, "logs"));
        Directory.CreateDirectory(Path.Combine(engine.State, "logs", "desktop.log"));
        await using var session = new EngineSession(engine.Configuration, Quick);
        await session.StartAsync();
        await Until(() => session.Snapshot.State == EngineState.Ready, TimeSpan.FromSeconds(90), "Ready");
        await session.StopAsync();
        Assert.AreEqual(EngineState.Stopped, session.Snapshot.State);
    }

    [TestMethod]
    public async Task AMalformedHealthAnswerIsOneFailedReadNotTheEndOfTheWatch()
    {
        var engine = new StandIn("malformed-health");
        var states = new List<EngineState>();
        await using var session = new EngineSession(engine.Configuration, Quick);
        session.Changed += snapshot => { lock (states) states.Add(snapshot.State); };
        await session.StartAsync();
        await Until(() => session.Snapshot.State == EngineState.Ready, TimeSpan.FromSeconds(90), "Ready");
        Assert.AreEqual(2, engine.Events().Count(line => line == "health-malformed"), "the engine answered badly twice");
        lock (states) CollectionAssert.DoesNotContain(states, EngineState.Attention);
        await session.StopAsync();
    }

    /// <summary>Long enough for a stand-in still starting its interpreter to read the stop it was sent.</summary>
    private static readonly EngineSessionOptions Patient = Quick with { StopTimeout = TimeSpan.FromSeconds(30) };

    [TestMethod]
    public async Task AnEngineThatNeverAnswersIsEndedAndRetriedUntilTheLimit()
    {
        var engine = new StandIn("silent");
        await using var session = new EngineSession(engine.Configuration, Patient with { SilentPreparation = TimeSpan.FromSeconds(2) });
        await session.StartAsync();
        await Until(() => session.Snapshot.State == EngineState.Attention, TimeSpan.FromSeconds(180), "the restart limit");
        StringAssert.Contains(session.Snapshot.Diagnostic!, "reached its limit");
        Assert.IsTrue(session.GaveUp);
        Assert.AreEqual(Quick.RestartLimit + 1, engine.Events().Count(line => line == "started"));
        Assert.AreEqual(Quick.RestartLimit + 1, engine.Events().Count(line => line == "stdin stop"), "each silent engine was asked to stop");
        Assert.IsFalse(session.OwnsEngine);
        using var lease = PrivateStorage.Lease(engine.State, "desktop.lock");
    }

    [TestMethod]
    public async Task APreparationThatStopsChangingIsEndedAtTheDeadline()
    {
        var engine = new StandIn("stuck");
        var states = new List<EngineState>();
        await using var session = new EngineSession(engine.Configuration, Patient with { PreparationDeadline = TimeSpan.FromSeconds(2) });
        session.Changed += snapshot => { lock (states) states.Add(snapshot.State); };
        await session.StartAsync();
        await Until(() => session.Snapshot.State == EngineState.Attention, TimeSpan.FromSeconds(180), "the restart limit");
        StringAssert.Contains(session.Snapshot.Diagnostic!, "reached its limit");
        Assert.IsTrue(session.GaveUp);
        Assert.IsFalse(session.PreparationFailed, "a stalled preparation is not one the engine reported failed");
        lock (states) CollectionAssert.Contains(states, EngineState.Preparing);
        Assert.AreEqual(Quick.RestartLimit + 1, engine.Events().Count(line => line == "stdin stop"));
        Assert.IsFalse(session.OwnsEngine);
    }

    [TestMethod]
    public async Task APreparationThatKeepsChangingOutlastsTheDeadline()
    {
        // An update's migration of a long history can take longer than the deadline from launch; only a preparation
        // that stops changing is ended.
        // Thirty changes 0.3 s apart: nine seconds in all against a four-second deadline, with a wide margin per gap.
        var engine = new StandIn("progressing");
        await using var session = new EngineSession(engine.Configuration, Quick with { PreparationDeadline = TimeSpan.FromSeconds(4) });
        await session.StartAsync();
        await Until(() => session.Snapshot.State == EngineState.Ready, TimeSpan.FromSeconds(90), "Ready");
        CollectionAssert.Contains(engine.Events(), "prepared");
        Assert.AreEqual(1, engine.Events().Count(line => line == "started"));
        CollectionAssert.DoesNotContain(engine.Events(), "stdin stop", "the engine was never asked to stop while it prepared");
        await session.StopAsync();
        Assert.AreEqual(EngineState.Stopped, session.Snapshot.State);
    }

    [TestMethod]
    [DataRow(2, false)]
    [DataRow(1000, true)]
    public async Task AReadyEngineIsRestartedAfterThreeFailedReadsInARow(int bad, bool restarted)
    {
        var engine = new StandIn("malformed-after-ready", bad: bad);
        var states = new List<EngineState>();
        await using var session = new EngineSession(engine.Configuration, Quick);
        session.Changed += snapshot => { lock (states) states.Add(snapshot.State); };
        await session.StartAsync();
        await Until(() => session.Snapshot.State == EngineState.Ready, TimeSpan.FromSeconds(90), "Ready");
        if (restarted)
        {
            await Until(() => engine.Events().Count(line => line == "started") >= 2, TimeSpan.FromSeconds(60), "a second engine");
            Assert.IsTrue(engine.Events().Count(line => line == "health-malformed") >= 3);
            CollectionAssert.Contains(engine.Events(), "stdin stop", "the unhealthy engine was asked to stop");
            lock (states) CollectionAssert.Contains(states, EngineState.Recovering);
        }
        else
        {
            await Until(() => engine.Events().Count(line => line == "health-good") >= 2, TimeSpan.FromSeconds(30),
                "good answers after the failed ones");
            Assert.AreEqual(2, engine.Events().Count(line => line == "health-malformed"));
            Assert.AreEqual(1, engine.Events().Count(line => line == "started"));
            lock (states) CollectionAssert.DoesNotContain(states, EngineState.Recovering);
            Assert.AreEqual(EngineState.Ready, session.Snapshot.State);
        }
        await session.StopAsync();
    }

    [TestMethod]
    public async Task StopDuringTheWaitBeforeARestartEndsAtOnce()
    {
        var engine = new StandIn("crash");
        await using var session = new EngineSession(engine.Configuration, Quick with { FirstBackoff = TimeSpan.FromMinutes(5) });
        await session.StartAsync();
        await Until(() => session.Snapshot.State == EngineState.Recovering, TimeSpan.FromSeconds(90), "the wait before a restart");
        var clock = Stopwatch.StartNew();
        await session.StopAsync();
        Assert.IsTrue(clock.Elapsed < TimeSpan.FromSeconds(10), $"Stop took {clock.Elapsed}");
        Assert.AreEqual(EngineState.Stopped, session.Snapshot.State);
        Assert.IsFalse(session.OwnsEngine);
        Assert.AreEqual(1, engine.Events().Count(line => line == "started"), "no engine starts after the stop");
        using var lease = PrivateStorage.Lease(engine.State, "desktop.lock");
    }

    [TestMethod]
    [DataRow(true)]
    [DataRow(false)]
    public async Task AKeptEngineThatExitsLetsTheNextStartReachReady(bool waitForRelease)
    {
        var engine = new StandIn("ignore-stop");
        var trail = new List<string>();
        int recorded;
        await using var session = new EngineSession(engine.Configuration, Quick);
        session.Changed += snapshot => { lock (trail) trail.Add($"{snapshot.State} {snapshot.Diagnostic}"); };
        await session.StartAsync();
        await Until(() => session.Snapshot.State == EngineState.Ready, TimeSpan.FromSeconds(90), "Ready");
        await session.StopAsync();
        Assert.AreEqual(EngineState.Attention, session.Snapshot.State);
        var pid = session.Snapshot.ProcessId ?? throw new AssertFailedException("The kept engine has no process ID.");
        // The record names the interpreter that runs the engine, which can be a child of the process the session started.
        using (var record = JsonDocument.Parse(File.ReadAllBytes(Path.Combine(engine.State, "launcher", "owned-engine.json"))))
            recorded = record.RootElement.GetProperty("pid").GetInt32();
        try
        {
            await session.StartAsync();
            Assert.AreEqual(EngineState.Attention, session.Snapshot.State, "a kept engine still running blocks a start");
            Assert.IsTrue(session.OwnsEngine);
            Assert.AreEqual(1, engine.Events().Count(line => line == "started"));
        }
        finally
        {
            // The stand-in ignores every stop, so a failed assertion must not leave it running.
            using var kept = Process.GetProcessById(pid);
            kept.Kill(entireProcessTree: true);
            await kept.WaitForExitAsync();
        }
        // Until the recorded engine is gone too, a start is rightly refused as still closing. The wait asks what the session
        // asks: a process can leave the process list before its handle reports the exit.
        await Until(() => ProcessClock.RunningSince(recorded) is null, TimeSpan.FromSeconds(30),
            $"the recorded engine {recorded} (kept {pid}) to exit");
        engine.Behave("ready");
        if (waitForRelease)
        {
            await Until(() => !session.OwnsEngine, TimeSpan.FromSeconds(30), "the lock to go with the kept engine");
            Assert.AreEqual(EngineState.Stopped, session.Snapshot.State);
            using (PrivateStorage.Lease(engine.State, "desktop.lock")) { }
        }
        await session.StartAsync();
        try
        {
            await Until(() => session.Snapshot.State == EngineState.Ready, TimeSpan.FromSeconds(90), "Ready after the kept engine exited");
        }
        catch (AssertFailedException)
        {
            string[] seen;
            lock (trail) seen = [.. trail];
            Assert.Fail($"No Ready after the kept engine exited. States: {string.Join(" | ", seen)}. Stand-in: {string.Join(" | ", engine.Events())}");
        }
        Assert.AreEqual(2, engine.Events().Count(line => line == "started"));
        await session.StopAsync();
        Assert.AreEqual(EngineState.Stopped, session.Snapshot.State);
    }

    [TestMethod]
    [DataRow("""{"format": 1, "pid": """)]
    [DataRow("[]")]
    [DataRow("""{"format": 2, "pid": PID, "started": 1}""")]
    public async Task ARecordThatNamesNoRunningEngineDoesNotBlockAStart(string text)
    {
        var engine = new StandIn("ready");
        PrivateStorage.EnsureDirectory(engine.State);
        PrivateStorage.EnsureDirectory(Path.Combine(engine.State, "launcher"));
        File.WriteAllText(Path.Combine(engine.State, "launcher", "owned-engine.json"),
            text.Replace("PID", Environment.ProcessId.ToString(System.Globalization.CultureInfo.InvariantCulture), StringComparison.Ordinal));
        await using var session = new EngineSession(engine.Configuration, Quick);
        await session.StartAsync();
        await Until(() => session.Snapshot.State == EngineState.Ready, TimeSpan.FromSeconds(90), "Ready beside the old record");
        await session.StopAsync();
        Assert.AreEqual(EngineState.Stopped, session.Snapshot.State);
    }

    [TestMethod]
    public async Task AProcessThatKeepsTheEngineOutputOpenDoesNotHoldUpAStop()
    {
        var engine = new StandIn("holds-output");
        await using var session = new EngineSession(engine.Configuration, Quick);
        await session.StartAsync();
        await Until(() => session.Snapshot.State == EngineState.Ready, TimeSpan.FromSeconds(90), "Ready");
        var child = int.Parse(engine.Events().Single(line => line.StartsWith("child ", StringComparison.Ordinal))[6..],
            System.Globalization.CultureInfo.InvariantCulture);
        try
        {
            var clock = Stopwatch.StartNew();
            await session.StopAsync().WaitAsync(TimeSpan.FromSeconds(60));
            Assert.IsTrue(clock.Elapsed < TimeSpan.FromSeconds(30), $"Stop took {clock.Elapsed}");
            Assert.AreEqual(EngineState.Stopped, session.Snapshot.State);
            Assert.IsFalse(session.OwnsEngine);
            Assert.IsTrue(Running(child), "the process holding the output outlived the engine");
        }
        finally
        {
            try
            {
                using var held = Process.GetProcessById(child);
                held.Kill();
            }
            catch (ArgumentException) { }
        }
    }

    private static Task NoWait(TimeSpan span, CancellationToken cancellation) => Task.CompletedTask;

    private const string Unfinished = """
        "update": {"phase": "applying", "from": "0.8.0", "to": "0.9.0", "running": "from", "since": 1800000000,
                   "package": "RoleBand-0.9.0-Windows-x64.msix"}
        """;

    [TestMethod]
    public async Task AnUpdateLeftApplyingIsTakenToWindowsEvenWhenUpdatesAreUnavailable()
    {
        // A build whose update identity is damaged reports updates unavailable; the update it began is still Windows' to finish.
        var deployer = new RecordingDeployer(null, new InstallFinding(InstallProgress.Running), new InstallFinding(InstallProgress.Finished));
        var commands = new RecordingCommands(() => false,
            ("status", $$"""{"status": "unavailable", "reason": "This build's update identity is damaged.", {{Unfinished}}}"""));
        var read = new List<UpdateFacts>();
        var settle = await new UpdateCoordinator(commands, deployer, NoWait).MaySettleAsync("RoleBand.Windows", read.Add, _ => { });
        Assert.IsFalse(settle, "Windows installed the new version, which settles the update");
        CollectionAssert.AreEqual(new[] { "find", "reopen", "find" }, deployer.Steps);
        Assert.AreEqual(UpdateFacts.Unavailable, read.Single());
        CollectionAssert.AreEqual(new[] { "status" }, commands.Calls, "nothing touches the journal");
    }

    [TestMethod]
    public async Task AStatusThatCannotBeReadSettlesNothing()
    {
        var deployer = new RecordingDeployer();
        var commands = new RecordingCommands(() => false, ("status", """{"reason": "no status in this answer"}"""));
        var read = new List<UpdateFacts>();
        await Assert.ThrowsExactlyAsync<IOException>(
            () => new UpdateCoordinator(commands, deployer, NoWait).MaySettleAsync("RoleBand.Windows", read.Add, _ => { }));
        CollectionAssert.AreEqual(new[] { "status" }, commands.Calls);
        Assert.AreEqual(0, deployer.Steps.Count);
        Assert.AreEqual(0, read.Count);
    }

    [TestMethod]
    [DataRow("RoleBand.Windows", """{"status": "ok"}""")]
    [DataRow(null, $$"""{"status": "ok", {{Unfinished}}}""")]
    public async Task WindowsIsAskedOnlyAboutAnUpdateThisPackageLeftApplying(string? packageName, string status)
    {
        var deployer = new RecordingDeployer(null, new InstallFinding(InstallProgress.Running));
        var commands = new RecordingCommands(() => false, ("status", status));
        var read = new List<UpdateFacts>();
        Assert.IsTrue(await new UpdateCoordinator(commands, deployer, NoWait).MaySettleAsync(packageName, read.Add, _ => { }));
        Assert.AreEqual(0, deployer.Steps.Count, "no update applying, or a copy without a package, which Windows never replaces");
        Assert.IsTrue(read.Single().Available);
    }

    private sealed class RecordingCommands(Func<bool> engineRunning, params (string Action, string Answer)[] answers) : IUpdateCommands
    {
        public List<string> Calls { get; } = [];
        public List<bool> EngineRunningAt { get; } = [];

        public Task<JsonElement> RunAsync(IReadOnlyList<string> arguments, CancellationToken cancellation, Action<string>? lines = null)
        {
            Calls.Add(string.Join(' ', arguments));
            EngineRunningAt.Add(engineRunning());
            var answer = answers.FirstOrDefault(item => item.Action == arguments[0]).Answer ?? "{}";
            using var document = JsonDocument.Parse(answer);
            return Task.FromResult(document.RootElement.Clone());
        }
    }

    /// <summary>Windows' installer, recording what it is asked; its deployment log answers the findings given, one per
    /// reading, and keeps the last.</summary>
    private sealed class RecordingDeployer(Exception? failure = null, params InstallFinding[] findings) : IPackageDeployer
    {
        public List<string> Packages { get; } = [];

        public List<bool> Downgrades { get; } = [];

        /// <summary>What the coordinator did, in order: "add", "find", "reopen".</summary>
        public List<string> Steps { get; } = [];

        public Task AddAsync(string package, bool downgrade, IProgress<int>? progress, CancellationToken cancellation)
        {
            Steps.Add("add");
            Packages.Add(package);
            Downgrades.Add(downgrade);
            foreach (var percent in new[] { 12, 57, 100 }) progress?.Report(percent);
            return failure is null ? Task.CompletedTask : Task.FromException(failure);
        }

        public Task<InstallFinding> FindAsync(string packageName, string version, string file, DateTimeOffset since,
                                              CancellationToken cancellation)
        {
            var reading = Steps.Count(step => step == "find");
            Steps.Add("find");
            return Task.FromResult(findings.Length == 0 ? new InstallFinding(InstallProgress.None) : findings[Math.Min(reading, findings.Length - 1)]);
        }

        public void ReopenWhenReplaced() => Steps.Add("reopen");
    }

    private sealed class Collected : IProgress<int>
    {
        public List<int> Values { get; } = [];
        public void Report(int value) => Values.Add(value);
    }

    [TestMethod]
    public async Task WindowsOwnProgressReachesTheAppWhileItInstallsOrPutsBackAVersion()
    {
        var engine = new StandIn("ready");
        await using var session = new EngineSession(engine.Configuration, Quick);
        var commands = new RecordingCommands(() => session.OwnsEngine, ("begin", """{"phase": "applying"}"""),
            ("recover-begin", """{"phase": "recovering", "package": "C:\\state\\packages\\previous.msix"}"""));
        var installing = new Collected();
        var deployer = new RecordingDeployer();
        await new UpdateCoordinator(commands, deployer).ApplyAsync(session, Package, installing);
        CollectionAssert.AreEqual(new[] { 12, 57, 100 }, installing.Values);
        CollectionAssert.AreEqual(new[] { "reopen", "add" }, deployer.Steps, "Windows is asked to open the app again before it closes it");
        var returning = new Collected();
        var back = new RecordingDeployer();
        await new UpdateCoordinator(commands, back).ReturnToPreviousAsync(session, returning);
        CollectionAssert.AreEqual(new[] { 12, 57, 100 }, returning.Values);
        CollectionAssert.AreEqual(new[] { "reopen", "add" }, back.Steps);
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
    [DataRow(false, DisplayName = "update")]
    [DataRow(true, DisplayName = "undo")]
    public async Task AnUpdateOrUndoCancelledDuringTheStopIsNeverRecordedOrInstalled(bool undo)
    {
        var engine = new StandIn("ready");
        await using var session = new EngineSession(engine.Configuration, Quick);
        await session.StartAsync();
        await Until(() => session.Snapshot.State == EngineState.Ready, TimeSpan.FromSeconds(90), "Ready");
        // Windows ends the session once the engine has begun to stop, as at sign-out.
        using var ending = new CancellationTokenSource();
        session.Changed += snapshot =>
        {
            if (snapshot.State == EngineState.Stopping) ending.Cancel();
        };
        var commands = new RecordingCommands(() => session.OwnsEngine, ("begin", """{"phase": "applying"}"""),
            ("recover-begin", $$"""{"phase": "recovering", "package": {{JsonSerializer.Serialize(Previous)}}}"""));
        var deployer = new RecordingDeployer();
        var coordinator = new UpdateCoordinator(commands, deployer);

        await Assert.ThrowsAsync<OperationCanceledException>(() => undo
            ? coordinator.ReturnToPreviousAsync(session, cancellation: ending.Token)
            : coordinator.ApplyAsync(session, Package, cancellation: ending.Token));

        Assert.IsTrue(ending.IsCancellationRequested, "the session ended during the stop");
        Assert.IsFalse(session.OwnsEngine, "the engine still stops");
        CollectionAssert.AreEqual(Array.Empty<string>(), commands.Calls, "the journal records nothing");
        CollectionAssert.AreEqual(Array.Empty<string>(), deployer.Steps, "Windows installs nothing");
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
    public async Task AStartCancelledWhileTheJournalIsReadNeverStartsTheEngine()
    {
        // Windows ends the app while the start waits on the journal's resume, as at sign-out.
        var engine = new StandIn("ready");
        await using var session = new EngineSession(engine.Configuration, Quick);
        using var ending = new CancellationTokenSource();
        var commands = new RecordingCommands(() =>
        {
            ending.Cancel();
            return session.OwnsEngine;
        });

        await Assert.ThrowsAsync<OperationCanceledException>(() =>
            new UpdateCoordinator(commands, new RecordingDeployer()).StartAsync(session, ending.Token));

        CollectionAssert.AreEqual(new[] { "resume" }, commands.Calls, "the resume runs to its end");
        Assert.IsFalse(session.OwnsEngine);
        Assert.AreEqual(EngineState.Stopped, session.Snapshot.State);
        CollectionAssert.DoesNotContain(engine.Events(), "started");
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
    public async Task ANewVersionThatKeepsExitingBeforeItIsReadyMarksTheUpdateFailed()
    {
        var engine = new StandIn("exit-early");
        await using var session = new EngineSession(engine.Configuration, Quick);
        var commands = new RecordingCommands(() => session.OwnsEngine, ("resume", """{"phase": "preparing"}"""),
            ("settle", """{"phase": "failed"}"""));
        var phase = await new UpdateCoordinator(commands, new RecordingDeployer()).StartAsync(session);
        Assert.AreEqual("failed", phase);
        Assert.IsTrue(session.GaveUp);
        Assert.AreEqual(Quick.RestartLimit + 1, engine.Events().Count(line => line == "started"));
        CollectionAssert.AreEqual(new[] { "resume", "settle --prepared no" }, commands.Calls);

        // An engine that was ready once and then crashed already settled the update as prepared.
        var later = new StandIn("crash");
        await using var crashing = new EngineSession(later.Configuration, Quick);
        var settled = new RecordingCommands(() => crashing.OwnsEngine, ("resume", """{"phase": "preparing"}"""),
            ("settle", """{"phase": "complete"}"""));
        await new UpdateCoordinator(settled, new RecordingDeployer()).StartAsync(crashing);
        CollectionAssert.AreEqual(new[] { "resume", "settle --prepared yes" }, settled.Calls);
        await crashing.StopAsync();
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

    private const string Previous = @"C:\state\packages\RoleBand-0.8.0-Windows-x64.msix";

    [TestMethod]
    public async Task AFailedUpdateStaysClosedUntilItIsUndone()
    {
        var engine = new StandIn("ready");
        await using var session = new EngineSession(engine.Configuration, Quick);
        var commands = new RecordingCommands(() => session.OwnsEngine, ("resume", """{"phase": "failed", "running": "to"}"""));
        Assert.AreEqual("failed", await new UpdateCoordinator(commands, new RecordingDeployer()).StartAsync(session));
        Assert.IsFalse(session.OwnsEngine);
        Assert.AreEqual(EngineState.Stopped, session.Snapshot.State);
    }

    [TestMethod]
    public async Task UndoRegistersTheRetainedPreviousPackageAsADowngrade()
    {
        var engine = new StandIn("ready");
        await using var session = new EngineSession(engine.Configuration, Quick);
        var commands = new RecordingCommands(() => session.OwnsEngine,
            ("recover-begin", $$"""{"phase": "recovering", "package": {{JsonSerializer.Serialize(Previous)}}}"""));
        var deployer = new RecordingDeployer();
        await new UpdateCoordinator(commands, deployer).ReturnToPreviousAsync(session);
        CollectionAssert.AreEqual(new[] { Previous }, deployer.Packages);
        CollectionAssert.AreEqual(new[] { true }, deployer.Downgrades);
    }

    [TestMethod]
    public async Task UndoWithoutARetainedPackageRegistersNothing()
    {
        var engine = new StandIn("ready");
        await using var session = new EngineSession(engine.Configuration, Quick);
        var commands = new RecordingCommands(() => session.OwnsEngine,
            ("recover-begin", """{"status": "refused", "reason": "The previous version's package is not retained here."}"""));
        var deployer = new RecordingDeployer();
        var error = await Assert.ThrowsExactlyAsync<UpdateRefused>(() => new UpdateCoordinator(commands, deployer).ReturnToPreviousAsync(session));
        StringAssert.Contains(error.Message, "not retained");
        Assert.IsNull(error.Kind);
        Assert.AreEqual(0, deployer.Packages.Count);
    }

    [TestMethod]
    public async Task AnUndoRefusedForAReleaseThatIsGoneSaysSoToTheApp()
    {
        var engine = new StandIn("ready");
        await using var session = new EngineSession(engine.Configuration, Quick);
        var commands = new RecordingCommands(() => session.OwnsEngine,
            ("recover-begin", """{"status": "refused", "kind": "missing", "reason": "Version 0.1.17 is no longer published."}"""));
        var deployer = new RecordingDeployer();
        var error = await Assert.ThrowsExactlyAsync<UpdateRefused>(() => new UpdateCoordinator(commands, deployer).ReturnToPreviousAsync(session));
        Assert.AreEqual(("missing", "Version 0.1.17 is no longer published."), (error.Kind, error.Message));
        Assert.AreEqual(0, deployer.Packages.Count);
    }

    [TestMethod]
    public async Task ThePreviousVersionRestoresItsDatabaseBeforeStarting()
    {
        var engine = new StandIn("ready");
        await using var session = new EngineSession(engine.Configuration, Quick);
        var commands = new RecordingCommands(() => session.OwnsEngine,
            ("resume", """{"phase": "recovering", "running": "from"}"""), ("recover", """{"phase": "recovered"}"""));
        Assert.AreEqual("recovered", await new UpdateCoordinator(commands, new RecordingDeployer()).StartAsync(session));
        CollectionAssert.AreEqual(new[] { "resume", "recover" }, commands.Calls);
        CollectionAssert.AreEqual(new[] { false, false }, commands.EngineRunningAt, "the database is restored before the engine starts");
        await Until(() => session.Snapshot.State == EngineState.Ready, TimeSpan.FromSeconds(90), "Ready after recovery");
        await session.StopAsync();
    }

    [TestMethod]
    public async Task AFailedRestoreKeepsTheEngineStopped()
    {
        var engine = new StandIn("ready");
        await using var session = new EngineSession(engine.Configuration, Quick);
        var commands = new RecordingCommands(() => session.OwnsEngine,
            ("resume", """{"phase": "recovering", "running": "from"}"""),
            ("recover", """{"status": "refused", "reason": "Database restore is unfinished."}"""));
        var error = await Assert.ThrowsExactlyAsync<IOException>(() => new UpdateCoordinator(commands, new RecordingDeployer()).StartAsync(session));
        StringAssert.Contains(error.Message, "unfinished");
        Assert.IsFalse(session.OwnsEngine);
    }

    [TestMethod]
    public async Task TheNewVersionOffersUndoAgainWhenTheSwitchBackDidNotHappen()
    {
        var engine = new StandIn("ready");
        await using var session = new EngineSession(engine.Configuration, Quick);
        var commands = new RecordingCommands(() => session.OwnsEngine, ("resume", """{"phase": "recovering", "running": "to"}"""));
        Assert.AreEqual("recovering", await new UpdateCoordinator(commands, new RecordingDeployer()).StartAsync(session));
        CollectionAssert.AreEqual(new[] { "resume" }, commands.Calls);
        Assert.IsFalse(session.OwnsEngine);
    }
}

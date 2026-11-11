using System.Text.Json;
using Microsoft.VisualStudio.TestTools.UnitTesting;
using Windows.ApplicationModel;

namespace RoleBand.EngineHost.Tests;

[TestClass]
public sealed class SetupTests
{
    private static readonly string[] Languages = ["en", "es", "zh-Hans"];
    private static readonly EngineSnapshot Ready = new(EngineState.Ready, Preparation: Prepared());

    private static EnginePreparation Prepared(string database = "ready", string model = "ready", string service = "ready",
                                              long downloaded = 0, long total = 0, string? reason = null) =>
        new(database, model, service, downloaded, total, reason);

    private static string State()
    {
        var state = Path.Combine(Path.GetTempPath(), "roleband-setup-tests", Guid.NewGuid().ToString("N"));
        PrivateStorage.EnsureDirectory(state);
        return state;
    }

    private static EnginePreparation? Read(string json)
    {
        using var document = JsonDocument.Parse(json);
        return EnginePreparation.Read(document.RootElement);
    }

    [TestMethod]
    public void ANewAccountStartsAtWelcomeAndAnExistingDatabaseNeverWaitsThere()
    {
        var fresh = State();
        Assert.AreEqual(SetupRecord.Fresh, SetupStore.Read(fresh));
        var existing = State();
        Directory.CreateDirectory(Path.Combine(existing, "db"));
        File.WriteAllText(Path.Combine(existing, "db", "PG_VERSION"), "16\n");
        Assert.IsTrue(SetupStore.Read(existing).Complete, "an install from before setup keeps scanning");
        Assert.IsFalse(SetupFlow.EngineHeld(SetupStore.Read(existing)));
    }

    [TestMethod]
    public void TheSavedStepAndChoicesSurviveAndAnUnreadableRecordNeverHoldsAnExistingInstall()
    {
        var state = State();
        var record = new SetupRecord(SetupStep.Login, false, false, true);
        SetupStore.Write(state, record);
        Assert.AreEqual(record, SetupStore.Read(state));
        PrivateStorage.Verify(SetupStore.PathFor(state));
        SetupStore.Write(state, record with { Step = SetupStep.Done, Complete = true });
        Assert.AreEqual(record with { Step = SetupStep.Done, Complete = true }, SetupStore.Read(state));

        File.WriteAllText(SetupStore.PathFor(state), """{"format":1,"step":"elsewhere","complete":false,"login_choice":true,"deferred":false}""");
        Assert.AreEqual(SetupRecord.Fresh, SetupStore.Read(state));
        Directory.CreateDirectory(Path.Combine(state, "db"));
        File.WriteAllText(Path.Combine(state, "db", "PG_VERSION"), "16\n");
        Assert.IsTrue(SetupStore.Read(state).Complete);
        File.WriteAllText(SetupStore.PathFor(state), "{not json");
        Assert.IsTrue(SetupStore.Read(state).Complete);
    }

    [TestMethod]
    public void NothingRunsBeforeContinueOnWelcomeAndLoginOpensQuietly()
    {
        Assert.IsTrue(SetupFlow.EngineHeld(SetupRecord.Fresh));
        foreach (var step in new[] { SetupStep.Preparing, SetupStep.Login, SetupStep.Done })
            Assert.IsFalse(SetupFlow.EngineHeld(SetupRecord.Fresh with { Step = step }), step.ToString());
        Assert.IsFalse(SetupFlow.EngineHeld(SetupRecord.Finished with { Step = SetupStep.Welcome }));
        Assert.IsTrue(SetupFlow.ShowAtLaunch(SetupRecord.Fresh, atLogin: false));
        Assert.IsFalse(SetupFlow.ShowAtLaunch(SetupRecord.Fresh, atLogin: true));
        Assert.IsFalse(SetupFlow.ShowAtLaunch(SetupRecord.Fresh with { Deferred = true }, atLogin: false), "put off: the panel's card resumes it");
        Assert.IsFalse(SetupFlow.ShowAtLaunch(SetupRecord.Finished, atLogin: false));
    }

    [TestMethod]
    public void GetReadyWaitsForTheDatabaseAndServiceButNotTheModel()
    {
        Assert.AreEqual(SetupStep.Preparing, SetupFlow.Next(SetupStep.Welcome, false));
        Assert.AreEqual(SetupStep.Preparing, SetupFlow.Next(SetupStep.Preparing, false));
        Assert.AreEqual(SetupStep.Login, SetupFlow.Next(SetupStep.Preparing, true));
        Assert.AreEqual(SetupStep.Done, SetupFlow.Next(SetupStep.Login, false));
        Assert.AreEqual(SetupStep.Preparing, SetupFlow.Previous(SetupStep.Login));
        Assert.AreEqual(SetupStep.Welcome, SetupFlow.Previous(SetupStep.Preparing));
        Assert.AreEqual(SetupStep.Welcome, SetupFlow.Previous(SetupStep.Welcome));

        var downloading = new EngineSnapshot(EngineState.Ready, Preparation: Prepared(model: "downloading", downloaded: 40, total: 160));
        Assert.IsTrue(SetupFlow.PreparationReady(downloading));
        Assert.IsTrue(SetupFlow.PreparationReady(new EngineSnapshot(EngineState.Ready)), "an engine that prepares nothing");
        Assert.AreEqual("first-model-unused", SetupFlow.Page(SetupRecord.Fresh with { Step = SetupStep.Preparing },
            new EngineSnapshot(EngineState.Ready), LoginState.Off, false).Rows[1].CaptionKey, "no model was prepared, so none is claimed");
        Assert.IsFalse(SetupFlow.PreparationReady(new EngineSnapshot(EngineState.Preparing, Preparation: Prepared(service: "starting"))));
        Assert.IsFalse(SetupFlow.PreparationReady(new EngineSnapshot(EngineState.Starting)));
        Assert.IsFalse(SetupFlow.PreparationReady(new EngineSnapshot(EngineState.Ready, Preparation: Prepared(service: "starting"))),
            "an answer is not enough: the service must be ready");

        var page = SetupFlow.Page(SetupRecord.Fresh with { Step = SetupStep.Preparing }, downloading, LoginState.Off, false);
        Assert.IsTrue(page.PrimaryEnabled);
        Assert.AreEqual("continue", page.PrimaryKey);
        Assert.AreEqual("first-preparing-title", page.HeadingKey, "the model is still on its way");
        var model = page.Rows.Single(row => row.TitleKey == "first-model");
        Assert.AreEqual(("first-model-downloading", "25%", 0.25), (model.CaptionKey, model.Figure, model.Progress));

        var starting = SetupFlow.Page(SetupRecord.Fresh with { Step = SetupStep.Preparing },
            new EngineSnapshot(EngineState.Preparing, Preparation: Prepared(database: "creating", model: "waiting", service: "starting", reason: "offline")),
            LoginState.Off, false);
        Assert.IsFalse(starting.PrimaryEnabled);
        Assert.IsTrue(starting.Busy);
        Assert.AreEqual("first-busy", starting.PrimaryKey);
        Assert.AreEqual("first-model-offline", starting.Rows.Single(row => row.TitleKey == "first-model").CaptionKey);

        var offline = SetupFlow.Page(SetupRecord.Fresh with { Step = SetupStep.Preparing },
            new EngineSnapshot(EngineState.Ready, Preparation: Prepared(model: "waiting", reason: "offline")), LoginState.Off, false);
        Assert.AreEqual("first-offline-body", offline.BodyKey);
        Assert.IsTrue(offline.PrimaryEnabled, "the Radar can open while the model waits");
        Assert.AreEqual("windows-prepared-title",
            SetupFlow.Page(SetupRecord.Fresh with { Step = SetupStep.Preparing }, Ready, LoginState.Off, false).HeadingKey);
    }

    [TestMethod]
    public void AFailedPreparationSaysWhichPartFailedAndOffersRetryAndLogs()
    {
        var record = SetupRecord.Fresh with { Step = SetupStep.Preparing };
        var database = SetupFlow.Page(record, new EngineSnapshot(EngineState.Attention, Preparation: Prepared(database: "failed", model: "waiting", service: "starting")),
            LoginState.Off, false);
        Assert.AreEqual(("first-failed-title", "first-database-failed", "retry", "engine-logs"),
            (database.HeadingKey, database.BodyKey, database.PrimaryKey, database.SecondaryKey));
        Assert.IsTrue(database.Retry && database.PrimaryEnabled);
        Assert.AreEqual("failed", database.Rows[0].Mark);
        var waiting = database.Rows.Single(row => row.TitleKey == "first-service");
        Assert.AreEqual(("first-waiting", "waiting"), (waiting.CaptionKey, waiting.Mark), "a service that cannot start does not look busy");
        var service = SetupFlow.Page(record, new EngineSnapshot(EngineState.Attention, Preparation: Prepared(service: "failed")), LoginState.Off, false);
        Assert.AreEqual("first-service-failed", service.BodyKey);
    }

    [TestMethod]
    public void ThePreparationBlockIsReadOnlyInTheEnginesOwnVocabulary()
    {
        Assert.IsNull(Read("null"));
        var read = Read("""{"database":"ready","model":"downloading","service":"starting","downloaded_bytes":5,"total_bytes":10,"tier":"int8","reason":null,"format":1}""")!;
        Assert.AreEqual(Prepared("ready", "downloading", "starting", 5, 10), read);
        Assert.IsFalse(read.Ready);
        Assert.ThrowsExactly<IOException>(() => Read("""{"database":"ready","model":"ready","service":"warming","downloaded_bytes":0,"total_bytes":0,"format":1}"""));
        Assert.ThrowsExactly<IOException>(() => Read("""{"database":"ready","model":"ready","service":"ready","downloaded_bytes":11,"total_bytes":10,"format":1}"""));
        Assert.ThrowsExactly<IOException>(() => Read("""{"database":"ready","model":"ready","service":"ready","downloaded_bytes":0,"total_bytes":0,"format":2}"""));
    }

    private sealed class FakeLogin(LoginState state, bool fails = false) : ILoginItem
    {
        public LoginState State { get; private set; } = state;
        public List<bool> Sets { get; } = [];
        public Task<LoginState> ReadAsync() => Task.FromResult(State);
        public Task<LoginState> SetAsync(bool enabled)
        {
            Sets.Add(enabled);
            if (fails) throw new InvalidOperationException("Windows refused.");
            // Turned off in Startup apps stays off: only the person can turn it back on.
            if (State is LoginState.Off or LoginState.On) State = enabled ? LoginState.On : LoginState.Off;
            return Task.FromResult(State);
        }
    }

    [TestMethod]
    public async Task AtLoginRegistersOnlyOnAChangeOrContinueAndStaysWhenWindowsRefuses()
    {
        var record = SetupRecord.Fresh with { Step = SetupStep.Login };
        Assert.IsTrue(SetupFlow.SwitchOn(record, LoginState.Off), "proposed on, before anything registers");

        var item = new FakeLogin(LoginState.Off);
        var (next, state, error) = await SetupFlow.ContinueAsync(record, Ready, LoginState.Off, item);
        CollectionAssert.AreEqual(new[] { true }, item.Sets);
        Assert.AreEqual((SetupStep.Done, LoginState.On, false), (next.Step, state, error));

        var already = new FakeLogin(LoginState.On);
        await SetupFlow.ContinueAsync(record, Ready, LoginState.On, already);
        Assert.AreEqual(0, already.Sets.Count, "nothing to register");

        var refused = new FakeLogin(LoginState.Off, fails: true);
        (next, state, error) = await SetupFlow.ContinueAsync(record, Ready, LoginState.Off, refused);
        Assert.AreEqual((SetupStep.Login, true), (next.Step, error));

        var managed = new FakeLogin(LoginState.ManagedOff);
        (next, _, _) = await SetupFlow.ContinueAsync(record, Ready, LoginState.ManagedOff, managed);
        Assert.AreEqual(0, managed.Sets.Count, "a policy is not the app's to change");
        Assert.AreEqual(SetupStep.Done, next.Step);

        var choice = new FakeLogin(LoginState.On);
        (next, state, _) = await SetupFlow.ChooseLoginAsync(record, false, choice);
        Assert.AreEqual((false, LoginState.Off), (next.LoginChoice, state));
        Assert.AreEqual(SetupStep.Login, next.Step, "a switch change does not move the page");

        var userOff = new FakeLogin(LoginState.Approval);
        (_, state, error) = await SetupFlow.ChooseLoginAsync(record, true, userOff);
        Assert.AreEqual((LoginState.Approval, false), (state, error));
        var page = SetupFlow.Page(record, Ready, state, false);
        Assert.IsTrue(page.LoginSettings);
        Assert.AreEqual("windows-login-approval", page.Rows[0].CaptionKey);
    }

    [TestMethod]
    public void WindowsDecidesTheSwitchUnderPolicyAndWithoutAPackage()
    {
        var record = SetupRecord.Fresh with { Step = SetupStep.Login, LoginChoice = false };
        Assert.IsTrue(SetupFlow.SwitchOn(record, LoginState.ManagedOn));
        Assert.IsFalse(SetupFlow.SwitchOn(record with { LoginChoice = true }, LoginState.ManagedOff));
        Assert.IsFalse(SetupFlow.SwitchOn(record with { LoginChoice = true }, LoginState.Unavailable));
        foreach (var state in Enum.GetValues<LoginState>())
        {
            var page = SetupFlow.Page(record, Ready, state, false);
            Assert.AreEqual(state is LoginState.Off or LoginState.On or LoginState.Approval, page.LoginSwitchEnabled, state.ToString());
            Assert.IsFalse(SetupFlow.Page(record, Ready, state, loginBusy: true).LoginSwitchEnabled);
        }
        Assert.AreEqual(LoginState.Approval, StartupLoginItem.From(StartupTaskState.DisabledByUser));
        Assert.AreEqual(LoginState.ManagedOn, StartupLoginItem.From(StartupTaskState.EnabledByPolicy));
        Assert.AreEqual(LoginState.On, StartupLoginItem.From(StartupTaskState.Enabled));
    }

    [TestMethod]
    public async Task ACopyWithoutAPackageHasNoStartupTask()
    {
        var item = new StartupLoginItem();
        Assert.AreEqual(LoginState.Unavailable, await item.ReadAsync());
        Assert.AreEqual(LoginState.Unavailable, await item.SetAsync(true));
    }

    [TestMethod]
    public void ReadyCompletesOnlyWithAnEngineThatAnswersAndClosingKeepsTheStep()
    {
        var done = SetupRecord.Fresh with { Step = SetupStep.Done };
        Assert.AreEqual((done with { Complete = true }, true), SetupFlow.Finish(done, Ready));
        var (back, complete) = SetupFlow.Finish(done, new EngineSnapshot(EngineState.Recovering));
        Assert.AreEqual((SetupStep.Preparing, false), (back.Step, complete));

        Assert.AreEqual(SetupRecord.Fresh with { Step = SetupStep.Login, Deferred = true },
            SetupFlow.Close(SetupRecord.Fresh with { Step = SetupStep.Login }, Ready));
        Assert.IsTrue(SetupFlow.Close(done, Ready).Complete, "closing a valid Ready page completes setup");
        Assert.AreEqual(SetupRecord.Fresh with { Step = SetupStep.Preparing, Deferred = true },
            SetupFlow.Close(done, new EngineSnapshot(EngineState.Stopped)));
        Assert.AreEqual(SetupRecord.Finished, SetupFlow.Close(SetupRecord.Finished, new EngineSnapshot(EngineState.Stopped)));
        Assert.IsFalse(SetupFlow.Resume(SetupRecord.Fresh with { Deferred = true }).Deferred);
        Assert.IsFalse(SetupFlow.Page(done, new EngineSnapshot(EngineState.Starting), LoginState.Off, false).PrimaryEnabled);
    }

    [TestMethod]
    public void EveryPageHasWindowsWordsInEveryLanguage()
    {
        EngineSnapshot[] engines =
        [
            new(EngineState.Stopped), new(EngineState.Starting), Ready,
            new(EngineState.Preparing, Preparation: Prepared(database: "creating", model: "downloading", service: "starting", downloaded: 1, total: 4)),
            new(EngineState.Ready, Preparation: Prepared(model: "verifying")), new(EngineState.Ready, Preparation: Prepared(model: "failed")),
            new(EngineState.Ready, Preparation: Prepared(model: "unused")),
            new(EngineState.Attention, Preparation: Prepared(database: "failed", model: "waiting", service: "starting")),
        ];
        string[] macWords = ["Mac", "macOS", "menu bar", "Login Items", "Applications", "Finder", "barra de menús", "菜单栏", "登录项"];
        foreach (var language in Languages)
        {
            var copy = new NativeCopy(language);
            var seen = new List<string>();
            foreach (var step in Enum.GetValues<SetupStep>())
            foreach (var engine in engines)
            foreach (var login in Enum.GetValues<LoginState>())
            {
                var page = SetupFlow.Page(SetupRecord.Fresh with { Step = step }, engine, login, false);
                seen.AddRange([page.HeadingKey, page.BodyKey, page.PrimaryKey]);
                if (page.SecondaryKey is { } secondary) seen.Add(secondary);
                if (page.NoteKey is { } note) seen.Add(note);
                seen.AddRange(page.Rows.SelectMany(row => new[] { row.TitleKey, row.CaptionKey }).Where(key => key != ""));
            }
            seen.AddRange(SetupFlow.Steps.Select(step => step.Key));
            seen.AddRange(["back", "later", "windows-later-help", "windows-login-settings", "login-error", "setup-browser-error",
                "setup-pending", "setup-pending-held", "setup-finish", "windows-login-toggle", "windows-taskbar-settings"]);
            foreach (var key in seen.Distinct())
            {
                var text = copy[key];
                Assert.IsFalse(string.IsNullOrWhiteSpace(text), $"{language} {key}");
                Assert.IsFalse(macWords.Any(word => text.Contains(word, StringComparison.Ordinal)), $"{language} {key}: {text}");
            }
        }
    }

    [TestMethod]
    public void ThreeStepsEndOnOpenRadarWithTheSwitchAndWhereTheIconLives()
    {
        CollectionAssert.AreEqual(new[] { SetupStep.Welcome, SetupStep.Preparing, SetupStep.Login }, SetupFlow.Steps.Select(step => step.Step).ToArray());
        Assert.AreEqual((1, 2, 3, 3), (SetupFlow.Position(SetupStep.Welcome), SetupFlow.Position(SetupStep.Preparing),
            SetupFlow.Position(SetupStep.Login), SetupFlow.Position(SetupStep.Done)));
        Assert.AreEqual("windows-login-choice", SetupFlow.Page(SetupRecord.Fresh, Ready, LoginState.Off, false).Rows[1].TitleKey);

        var last = SetupFlow.Page(SetupRecord.Fresh with { Step = SetupStep.Login }, Ready, LoginState.Off, false);
        Assert.AreEqual(("first-open", "skip", true, false), (last.PrimaryKey, last.SecondaryKey, last.Back, last.Later),
            "Back on the left, Not now and Open Radar on the right; the close button keeps the step");
        CollectionAssert.AreEqual(new[] { "switch", "taskbar" }, last.Rows.Select(row => row.Mark).ToArray());
        Assert.AreEqual(("windows-login-toggle", "windows-tray-title"), (last.Rows[0].TitleKey, last.Rows[1].TitleKey));
        Assert.IsTrue(last.PrimaryEnabled);
        Assert.IsFalse(SetupFlow.Page(SetupRecord.Fresh with { Step = SetupStep.Login }, new EngineSnapshot(EngineState.Recovering), LoginState.Off, false).PrimaryEnabled,
            "the Radar opens only from an engine that answers");
        Assert.IsFalse(SetupFlow.Page(SetupRecord.Fresh with { Step = SetupStep.Login }, Ready, LoginState.Off, loginBusy: true).PrimaryEnabled);

        // A record saved at Done before it finished shows the last page, and Back leaves it.
        Assert.AreEqual(last with { }, SetupFlow.Page(SetupRecord.Fresh with { Step = SetupStep.Done }, Ready, LoginState.Off, false) with { Rows = last.Rows });
        Assert.AreEqual(SetupStep.Preparing, SetupFlow.Previous(SetupStep.Done));
    }
}

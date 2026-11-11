using System.Text;
using System.Text.Json;
using System.Text.Json.Nodes;
using Microsoft.VisualStudio.TestTools.UnitTesting;

namespace RoleBand.EngineHost.Tests;

[TestClass]
public sealed class ScanTests
{
    internal static readonly DateTimeOffset Now = new(2026, 11, 8, 15, 0, 0, TimeSpan.Zero);
    private static readonly string[] Languages = ["en", "es", "zh-Hans"];
    private static readonly EngineSnapshot Ready = new(EngineState.Ready);

    /// <summary>A status reply as the engine's schema writes it, with the fields the panel never reads.</summary>
    internal static JsonObject Reply(string activity = "idle", JsonObject? hold = null, string? queued = null,
                                    JsonObject? scan = null, bool running = false, bool manual = false, string[]? manualQueued = null)
    {
        scan ??= Picture();
        return new JsonObject
        {
            ["db"] = "ok",
            ["last_success_at"] = "2026-11-08T13:40:12.512301Z",
            ["running"] = running,
            ["manual_sync_running"] = manual,
            ["manual_queued"] = new JsonArray((manualQueued ?? []).Select(slug => (JsonNode)slug!).ToArray()),
            ["manual_blocked"] = new JsonArray(),
            ["stale"] = false,
            ["launcher"] = new JsonObject
            {
                ["product"] = "roleband", ["instance"] = "0123456789abcdef01234567",
                ["api_origin"] = "http://127.0.0.1:8011", ["version"] = "0.1.2", ["format"] = 1,
                ["status"] = new JsonObject
                {
                    ["observed_at"] = "2026-11-08T15:00:00.000000Z",
                    ["activity"] = activity,
                    ["activity_since"] = activity == "idle" ? null : "2026-11-08T14:57:32.000000Z",
                    ["hold"] = hold?.DeepClone(),
                    ["attention"] = new JsonArray(),
                    ["queued"] = queued,
                    ["coverage_at"] = "2026-11-08T13:40:12.512301Z",
                    ["last_scan_at"] = "2026-11-08T13:40:12.512301Z",
                    ["last_scan_outcome"] = "success",
                    ["model"] = "ready",
                },
                ["scan"] = scan.DeepClone(),
            },
        };
    }

    internal static JsonObject Picture(string? phase = null, int? percent = null, int? lastCompanies = 41, int? newRoles = 7,
                                      bool stopped = false, string scheduling = "plan", string? pausedUntil = null,
                                      string? next = "2026-11-08T18:00:00Z", JsonArray? inFlight = null,
                                      int? pending = null, int? recorded = null, int? total = null) => new()
    {
        ["phase"] = phase, ["percent"] = percent, ["companies_total"] = total,
        ["in_flight"] = inFlight ?? new JsonArray(),
        ["roles_pending"] = pending, ["roles_recorded"] = recorded,
        ["last_companies"] = lastCompanies, ["last_new_roles"] = newRoles, ["last_postings"] = 1284,
        ["last_stopped"] = stopped, ["next_scan_at"] = next, ["scheduling"] = scheduling, ["paused_until"] = pausedUntil,
    };

    internal static ScanStatus Status(JsonObject reply)
    {
        using var document = JsonDocument.Parse(reply.ToJsonString());
        return ScanStatus.Decode(document.RootElement, Now);
    }

    private static JsonObject Live(string phase = "collecting") => Picture(phase, percent: 62, total: 41,
        inFlight: new JsonArray(
            new JsonObject { ["name"] = "Acme Robotics", ["since"] = "2026-11-08T14:57:32Z" },
            new JsonObject { ["name"] = "Northwind", ["since"] = "2026-11-08T14:59:10.25Z" }),
        pending: 12, recorded: 30);

    [TestMethod]
    public void ARestingReplyReadsAsTheLastScanWithScanNowAvailable()
    {
        var status = Status(Reply());
        Assert.AreEqual(EngineActivity.Idle, status.Presentation.Activity);
        Assert.AreEqual(new DateTimeOffset(2026, 11, 8, 13, 40, 12, TimeSpan.Zero).AddTicks(5123010), status.Presentation.LastScanAt);
        Assert.AreEqual(41, status.Picture!.LastCompanies);
        Assert.AreEqual(7, status.Picture.LastNewRoles);
        Assert.AreEqual(new ScheduleState(true, true, null), status.Picture.Schedule);
        Assert.AreEqual(ScanAction.Start, status.Action);
    }

    [TestMethod]
    public void ANewerEngineActivityOrAnUnreadablePictureLeavesTheStatusUsable()
    {
        var unknown = Status(Reply(activity: "indexing"));
        Assert.AreEqual(EngineActivity.Unknown, unknown.Presentation.Activity);
        var picture = Picture();
        picture.Remove("last_stopped");
        var withoutPicture = Status(Reply(scan: picture));
        Assert.IsNull(withoutPicture.Picture);
        Assert.AreEqual(ScanAction.Start, withoutPicture.Action);
    }

    [TestMethod]
    public void AReplyWithoutItsDatabaseOrLauncherStatusIsRefused()
    {
        var failed = Reply();
        failed["db"] = "error";
        Assert.ThrowsExactly<InvalidDataException>(() => Status(failed));
        var bare = Reply();
        bare["launcher"] = null;
        Assert.ThrowsExactly<InvalidDataException>(() => Status(bare));
        var broken = Reply();
        broken["launcher"]!["status"]!.AsObject().Remove("activity");
        Assert.ThrowsExactly<InvalidDataException>(() => Status(broken));
    }

    [TestMethod]
    public void APauseThisBuildCannotReadLeavesTheScheduleUnknownNotUnpaused()
    {
        Assert.IsNull(Status(Reply(scan: Picture(pausedUntil: "tomorrow morning"))).Picture!.Schedule);
        Assert.IsNull(Status(Reply(scan: Picture(pausedUntil: "2026-11-08T18:00:00"))).Picture!.Schedule, "no offset");
        Assert.IsNull(Status(Reply(scan: Picture(scheduling: "cron"))).Picture!.Schedule);
        var paused = Status(Reply(scan: Picture(pausedUntil: "2026-11-08T16:00:00+00:00"))).Picture!.Schedule!;
        Assert.IsTrue(paused.IsPaused(Now));
        Assert.IsFalse(paused.IsPaused(Now.AddHours(2)));
    }

    [TestMethod]
    public void StopBelongsToARequestedScanAndScanNowToAnEngineWithNothingRunningHeldOrQueued()
    {
        var hold = new JsonObject { ["kind"] = "waiting", ["reason"] = "provider_backoff" };
        Assert.AreEqual(ScanAction.Stop, Status(Reply(activity: "scanning", running: true, manual: true)).Action);
        Assert.AreEqual(ScanAction.Stop, Status(Reply(manualQueued: ["acme"])).Action);
        Assert.IsNull(Status(Reply(activity: "scanning", running: true)).Action, "a scheduled scan is not the panel's to stop");
        Assert.IsNull(Status(Reply(hold: hold)).Action);
        Assert.IsNull(Status(Reply(queued: "update")).Action);
        Assert.IsNull(Status(Reply(running: true)).Action);
        var noQueue = Reply();
        noQueue.Remove("manual_queued");
        Assert.IsNull(Status(noQueue).Action, "without the queue there is no safe press");
    }

    [TestMethod]
    public void ThePhaseFollowsTheEngineAndTheRequestInFlight()
    {
        var scanning = Status(Reply(activity: "scanning", scan: Live("finishing")));
        Assert.AreEqual(ScanPhase.Stopping, ScanPanel.PhaseOf(scanning.Presentation, scanning.Picture, ScanAction.Stop));
        Assert.AreEqual(ScanPhase.Scanning, ScanPanel.PhaseOf(scanning.Presentation, scanning.Picture, null));
        Assert.AreEqual("scan-title-finishing", ScanPanel.TitleKey(ScanPhase.Scanning, scanning.Picture));
        Assert.AreEqual("scan-title-adding", ScanPanel.TitleKey(ScanPhase.Scanning, Status(Reply(scan: Live("persisting"))).Picture));
        Assert.AreEqual("scan-title-scanning", ScanPanel.TitleKey(ScanPhase.Scanning, Status(Reply(scan: Live("reticulating"))).Picture));
        var queued = Status(Reply(queued: "scan"));
        Assert.AreEqual(ScanPhase.Requesting, ScanPanel.PhaseOf(queued.Presentation, queued.Picture, null));
        var idle = Status(Reply());
        Assert.AreEqual(ScanPhase.Requesting, ScanPanel.PhaseOf(idle.Presentation, idle.Picture, ScanAction.Start));
        var stopped = Status(Reply(scan: Picture(stopped: true)));
        Assert.AreEqual(ScanPhase.Stopped, ScanPanel.PhaseOf(stopped.Presentation, stopped.Picture, null));
    }

    [TestMethod]
    public void AHoldAnEngineUpdateOrNoScanYetKeepsTheStatusCard()
    {
        var hold = new JsonObject { ["kind"] = "attention", ["reason"] = "preflight_failed" };
        Assert.IsTrue(ScanPanel.ShowsPicture(Ready, Status(Reply()), null));
        Assert.IsFalse(ScanPanel.ShowsPicture(Ready, Status(Reply(hold: hold)), null));
        Assert.IsFalse(ScanPanel.ShowsPicture(Ready, Status(Reply(activity: "updating")), null));
        Assert.IsFalse(ScanPanel.ShowsPicture(Ready, Status(Reply(scan: Picture(lastCompanies: null))), null), "a first install has no scan to draw");
        Assert.IsTrue(ScanPanel.ShowsPicture(Ready, Status(Reply(activity: "scanning", scan: Without(Live(), "last_companies"))), null));
        Assert.IsFalse(ScanPanel.ShowsPicture(new EngineSnapshot(EngineState.Recovering), Status(Reply()), null));
        var card = ScanPanel.View(new NativeCopy("en"), Ready, Status(Reply(hold: hold)), null, Now);
        Assert.IsFalse(card.Picture);
        Assert.AreEqual("needs-attention", card.TitleKey);
        Assert.AreEqual("reason-other", card.HelpKey);
    }

    private static JsonObject Without(JsonObject picture, string field)
    {
        picture[field] = null;
        return picture;
    }

    [TestMethod]
    public void AStoppedEngineTakesTheGoldPlaceAndOpenRadarWaitsForAnEngineThatAnswers()
    {
        var copy = new NativeCopy("en");
        foreach (var state in Enum.GetValues<EngineState>())
        {
            var view = ScanPanel.View(copy, new EngineSnapshot(state), state == EngineState.Ready ? Status(Reply()) : null, null, Now);
            var stopped = state is EngineState.Stopped or EngineState.Attention;
            Assert.AreEqual(stopped ? PrimaryAction.StartEngine : PrimaryAction.OpenRadar, view.Primary, state.ToString());
            Assert.AreEqual(stopped || state == EngineState.Ready, view.PrimaryEnabled, state.ToString());
            Assert.AreEqual(state == EngineState.Ready ? ScanAction.Start : null, view.Scan, state.ToString());
        }
    }

    [TestMethod]
    public void OnlyALastScanWithNewRolesMakesItsCountALinkToNew()
    {
        var copy = new NativeCopy("en");
        var withNew = ScanPanel.View(copy, Ready, Status(Reply()), null, Now);
        Assert.AreEqual(BrowserRoute.NewRoles, withNew.Facts.Single(fact => fact.Label == "new roles").Opens);
        Assert.AreEqual("7", withNew.Facts.Single(fact => fact.Label == "new roles").Figure);
        Assert.IsNull(withNew.Facts.Single(fact => fact.Label == "companies scanned").Opens);
        var none = ScanPanel.View(copy, Ready, Status(Reply(scan: Picture(newRoles: 0))), null, Now);
        Assert.IsTrue(none.Facts.All(fact => fact.Opens is null));
        var live = ScanPanel.View(copy, Ready, Status(Reply(activity: "scanning", running: true, scan: Live())), null, Now);
        Assert.IsTrue(live.Facts.All(fact => fact.Opens is null), "a live scan has no last scan's new roles to open");
    }

    [TestMethod]
    public void ALiveScanShowsItsCompaniesClocksAndTank()
    {
        var copy = new NativeCopy("en");
        var view = ScanPanel.View(copy, Ready, Status(Reply(activity: "scanning", running: true, scan: Live())), null, Now);
        Assert.AreEqual("scan-title-scanning", view.TitleKey);
        Assert.AreEqual("62%", view.Corner);
        Assert.AreEqual(62, view.Progress);
        CollectionAssert.AreEqual(new[] { "Acme Robotics", "Northwind" }, view.Companies.Select(company => company.Label).ToArray());
        CollectionAssert.AreEqual(new[] { "2:28", "0:49" }, view.Companies.Select(company => company.Figure).ToArray());
        Assert.AreEqual(new ScanFact("12", "still scanning"), view.Tank);
        Assert.AreEqual(new ScanFact("30", "finished"), view.TankFloor);
        StringAssert.Contains(view.Summary, "Acme Robotics 2:28");
        var read = ScanPanel.View(copy, Ready, Status(Reply(activity: "scanning", running: true,
            scan: Picture("persisting", percent: 100, total: 41, pending: 5, recorded: 88))), null, Now);
        Assert.AreEqual("scan-title-adding", read.TitleKey);
        Assert.AreEqual(new ScanFact("41", "companies scanned"), read.Facts.Single());
        Assert.AreEqual(new ScanFact("88", "recorded"), read.Tank);
        Assert.AreEqual(new ScanFact("5", "to add"), read.TankFloor);
        var finishing = ScanPanel.View(copy, Ready, Status(Reply(activity: "scanning", running: true,
            scan: Picture("finishing", percent: 100, total: 41, pending: 0, recorded: 93))), null, Now);
        Assert.AreEqual("2:28", finishing.Corner, "past 100 percent the scan's own clock shows it still moving");
        Assert.IsNull(finishing.TankFloor);
    }

    [TestMethod]
    public void ARequestInFlightReplacesTheScanButtonWithWhatItWaitsFor()
    {
        var copy = new NativeCopy("en");
        var starting = ScanPanel.View(copy, Ready, Status(Reply()), ScanAction.Start, Now);
        Assert.IsNull(starting.Scan);
        Assert.AreEqual("scan-sending", starting.ScanBusyKey);
        Assert.AreEqual("scan-title-requesting", starting.TitleKey);
        Assert.AreEqual("Last scan", starting.TankLabel);
        var stopping = ScanPanel.View(copy, Ready, Status(Reply(activity: "scanning", running: true, manual: true, scan: Live())), ScanAction.Stop, Now);
        Assert.AreEqual("scan-stop-requested", stopping.ScanBusyKey);
        Assert.AreEqual(ScheduleLineKind.Stopping, stopping.Schedule!.Kind);
        Assert.AreEqual("Roles found so far stay on your radar.", stopping.Schedule.Text);
        Assert.AreEqual(ScanAction.Stop,
            ScanPanel.View(copy, Ready, Status(Reply(activity: "scanning", running: true, manual: true, scan: Live())), null, Now).Scan);
    }

    [TestMethod]
    public void PauseIsOfferedOnlyWhereThePlanStartsScansAndResumeOnlyWhilePaused()
    {
        var copy = new NativeCopy("en");
        PauseControl Pause(JsonObject picture) => ScanPanel.View(copy, Ready, Status(Reply(scan: picture)), null, Now).Pause;
        Assert.AreEqual(PauseControl.Menu, Pause(Picture()));
        Assert.AreEqual(PauseControl.Resume, Pause(Picture(pausedUntil: "2026-11-08T16:00:00Z")));
        Assert.AreEqual(PauseControl.Menu, Pause(Picture(pausedUntil: "2026-11-08T14:00:00Z")), "a pause that has ended");
        Assert.AreEqual(PauseControl.None, Pause(Picture(scheduling: "timers")));
        Assert.AreEqual(PauseControl.None, Pause(Picture(scheduling: "off", next: null)));
        Assert.AreEqual(PauseControl.None, ScanPanel.View(copy, new EngineSnapshot(EngineState.Stopped), null, null, Now).Pause);
    }

    [TestMethod]
    public void TheScheduleLineSaysTheNextScanAPauseOrThatSchedulingIsOff()
    {
        var copy = new NativeCopy("en");
        ScheduleLine Line(JsonObject picture) => ScanPanel.View(copy, Ready, Status(Reply(scan: picture)), null, Now).Schedule!;
        var off = Line(Picture(scheduling: "off", next: null));
        Assert.AreEqual(ScheduleLineKind.Off, off.Kind);
        Assert.IsNull(off.LinkKey, "scheduling switched off in the engine has no switch on the Schedule page");
        Assert.AreEqual("scan-schedule-off-help", off.HelpKey);
        var paused = Line(Picture(pausedUntil: "2026-11-08T16:00:00Z"));
        Assert.AreEqual(ScheduleLineKind.Paused, paused.Kind);
        Assert.AreEqual("scan-resume", paused.LinkKey);
        StringAssert.StartsWith(paused.Text, "Paused until ");
        var next = Line(Picture());
        Assert.AreEqual("scan-change-times", next.LinkKey);
        StringAssert.StartsWith(next.Text, "Next scan at ");
        Assert.AreEqual("Next scan soon", Line(Picture(next: "2026-11-08T14:59:00Z")).Text, "a time already reached is due");
        Assert.IsNull(ScanPanel.Schedule(copy, ScanPhase.Idle, Status(Reply(scan: Picture(scheduling: "cron", next: null))).Picture, Now));
    }

    [TestMethod]
    public void EveryReasonTheEngineGivesHasWindowsWordsInEveryLanguage()
    {
        string[] reasons = ["supervisor_absent", "supervisor_stale", "schema_pending", "dependencies_pending", "build_failed",
            "preflight_failed", "model_missing", "model_preparing", "waiting_for_mains", "waiting_for_wake", "preflight_running",
            "busy_external", "maintenance", "update_queued", "provider_paused", "provider_backoff", "provider_policy_denied", "something_new"];
        foreach (var language in Languages)
        {
            var copy = new NativeCopy(language);
            foreach (var reason in reasons)
            {
                var text = copy[ScanPanel.ReasonKey(new ScanHold("waiting", reason))!];
                Assert.IsFalse(text.Contains("Mac", StringComparison.Ordinal) || text.Contains("setup.sh", StringComparison.Ordinal),
                    $"{language} {reason}: {text}");
            }
        }
        Assert.IsNull(ScanPanel.ReasonKey(null));
    }

    [TestMethod]
    public void EveryStateTheTabCanShowHasItsWordsInEveryLanguage()
    {
        var hold = new JsonObject { ["kind"] = "waiting", ["reason"] = "busy_external" };
        JsonObject[] replies =
        [
            Reply(), Reply(scan: Picture(stopped: true)), Reply(scan: Picture(scheduling: "off", next: null)),
            Reply(scan: Picture(pausedUntil: "2026-11-09T08:00:00Z")), Reply(activity: "scanning", running: true, manual: true, scan: Live()),
            Reply(activity: "scanning", running: true, scan: Live("persisting")), Reply(activity: "updating"), Reply(hold: hold),
            Reply(queued: "scan"), Reply(scan: Picture(lastCompanies: null)),
        ];
        foreach (var language in Languages)
        {
            var copy = new NativeCopy(language);
            foreach (var state in Enum.GetValues<EngineState>())
            foreach (var reply in replies)
            foreach (ScanAction? requested in new ScanAction?[] { null, ScanAction.Start, ScanAction.Stop })
            {
                var view = ScanPanel.View(copy, new EngineSnapshot(state), Status(reply), requested, Now);
                Assert.IsFalse(string.IsNullOrWhiteSpace(copy[view.TitleKey]));
                if (view.HelpKey is not null) _ = copy[view.HelpKey];
                if (view.ScanBusyKey is not null) _ = copy[view.ScanBusyKey];
                if (view.Schedule?.LinkKey is { } link) _ = copy[link];
                if (view.Schedule?.HelpKey is { } help) _ = copy[help];
                Assert.IsFalse(view.Summary.Contains('{'), $"{language}: {view.Summary}");
            }
            foreach (var action in Enum.GetValues<PauseAction>()) _ = copy[ScanControl.Key(action)];
            _ = copy.Format("scan-schedule-off-help", ("setting", "ROLEBAND_SYNC_SCHEDULER_ENABLED"));
            foreach (var key in new[] { "scan-now", "scan-stop", "scan-pause", "scan-paused", "pause-help", "scan-new-roles-open",
                "panel-open-radar-help", "panel-open-radar-waiting", "engine-start", "quit", "scan-state-changed", "scan-refused",
                "scan-unconfirmed", "pause-confirmed", "pause-resumed", "pause-state-changed", "pause-refused", "pause-unconfirmed" })
                _ = copy[key];
        }
    }

    [TestMethod]
    public void AMessageTakesExactlyItsPlaceholdersAndKeepsBracesInValues()
    {
        var copy = new NativeCopy("en");
        Assert.AreEqual("Next scan at {x}", copy.Format("scan-next", ("time", "{x}")));
        Assert.ThrowsExactly<FormatException>(() => copy.Format("scan-next"));
        Assert.ThrowsExactly<FormatException>(() => copy.Format("scan-next", ("time", "9:00"), ("day", "Monday")));
        Assert.ThrowsExactly<FormatException>(() => copy.Format("scan-next", ("when", "9:00")));
    }

    [TestMethod]
    public void TimesReadAsAStopwatchAndAsTheLocalDay()
    {
        Assert.AreEqual("2:28", ScanPanel.Running(Now.AddSeconds(-148), Now));
        Assert.AreEqual("1:02:05", ScanPanel.Running(Now.AddSeconds(-3725), Now));
        Assert.AreEqual("0:00", ScanPanel.Running(Now.AddSeconds(5), Now), "a clock ahead of this one reads as just started");
        var copy = new NativeCopy("en");
        var today = Now.ToLocalTime();
        StringAssert.StartsWith(ScanPanel.Moment(copy, today, today), "Today at ");
        Assert.IsFalse(ScanPanel.Moment(copy, today.AddDays(-2), today).StartsWith("Today", StringComparison.Ordinal));
    }

    [TestMethod]
    public void BrowserRoutesGoBetweenTheOriginAndTheTicket()
    {
        var ticket = new string('a', 64);
        var handoff = new Uri($"http://{new string('b', 32)}.localhost:51234/#roleband={ticket}");
        Assert.AreEqual($"http://{new string('b', 32)}.localhost:51234/?lens=new#roleband={ticket}",
            ScanPanel.Route(handoff, BrowserRoute.NewRoles).AbsoluteUri);
        Assert.AreEqual("/settings/schedule", ScanPanel.Route(handoff, BrowserRoute.Schedule).AbsolutePath);
        Assert.AreEqual("/settings", ScanPanel.Route(handoff, BrowserRoute.Settings).AbsolutePath);
        Assert.AreEqual(handoff, ScanPanel.Route(handoff, BrowserRoute.Radar));
        Assert.ThrowsExactly<IOException>(() => ScanPanel.Route(new Uri("http://x.localhost:1/elsewhere#roleband=" + ticket), BrowserRoute.NewRoles));
        Assert.ThrowsExactly<IOException>(() => ScanPanel.Route(new Uri("http://x.localhost:1/"), BrowserRoute.Radar));
    }

    [TestMethod]
    public void StatusReadsQuicklyOnlyWhileAScanRunsAndTheyBackOffAfterFailures()
    {
        Assert.AreEqual(TimeSpan.FromSeconds(3), ScanPanel.PollDelay(true, true, 0));
        Assert.AreEqual(TimeSpan.FromSeconds(15), ScanPanel.PollDelay(false, true, 0));
        Assert.AreEqual(TimeSpan.FromSeconds(60), ScanPanel.PollDelay(true, false, 0));
        CollectionAssert.AreEqual(new[] { 15.0, 30, 60, 120, 240, 300, 300 },
            Enumerable.Range(1, 7).Select(failures => ScanPanel.PollDelay(true, true, failures).TotalSeconds).ToArray());
    }

    private sealed class FakeEngine(Func<HttpMethod, string, string, JsonObject> answer) : IEngineRequests
    {
        public List<(HttpMethod Method, string Target, string Body, TimeSpan? Timeout)> Requests { get; } = [];

        public Task<JsonDocument> RequestAsync(HttpMethod method, string target, byte[]? body = null,
                                               CancellationToken cancellation = default, TimeSpan? timeout = null)
        {
            var text = Encoding.UTF8.GetString(body ?? []);
            Requests.Add((method, target, text, timeout));
            return Task.FromResult(JsonDocument.Parse(answer(method, target, text).ToJsonString()));
        }
    }

    [TestMethod]
    public async Task APressActsOnlyOnTheStateThePersonSaw()
    {
        var running = new FakeEngine((_, _, _) => Reply(activity: "scanning", running: true));
        await Assert.ThrowsExactlyAsync<ControlStateChangedException>(() => ScanControl.PerformAsync(running, ScanAction.Start));
        Assert.AreEqual(1, running.Requests.Count, "nothing is sent once the state moved");

        var idle = new FakeEngine((method, _, _) => method == HttpMethod.Get ? Reply() : new JsonObject { ["status"] = "started", ["dispatcher_pid"] = 4242 });
        Assert.IsNull(await ScanControl.PerformAsync(idle, ScanAction.Start));
        var sent = idle.Requests[1];
        Assert.AreEqual((HttpMethod.Post, "/api/sync", "{}", (TimeSpan?)ScanControl.MutationTimeout), sent);

        var manual = new FakeEngine((method, _, _) => method == HttpMethod.Get
            ? Reply(activity: "scanning", running: true, manual: true) : new JsonObject { ["status"] = "not_running", ["pid"] = null, ["dequeued"] = new JsonArray() });
        Assert.AreEqual("scan-not-running", await ScanControl.PerformAsync(manual, ScanAction.Stop));
        Assert.AreEqual("/api/sync/cancel", manual.Requests[1].Target);

        var garbled = new FakeEngine((method, _, _) => method == HttpMethod.Get ? Reply() : new JsonObject { ["status"] = "cancelled" });
        await Assert.ThrowsExactlyAsync<InvalidDataException>(() => ScanControl.PerformAsync(garbled, ScanAction.Start));
        Assert.AreEqual("scan-already-running", ScanControl.Outcome(JsonDocument.Parse("""{"status":"already_running","pid":7}""").RootElement, ScanAction.Start));
    }

    [TestMethod]
    public async Task APauseCarriesTheZoneAndMustLandAsAsked()
    {
        JsonObject Schedule(string? until) => new()
        {
            ["generated_at"] = "2026-11-08T15:00:01Z", ["enabled"] = true,
            ["plan"] = new JsonObject { ["enabled"] = true, ["repeat_hours"] = 3, ["paused_until"] = until },
        };
        var engine = new FakeEngine((method, _, _) => method == HttpMethod.Get ? Reply() : Schedule("2026-11-08T16:00:00.000000Z"));
        var result = await ScanControl.PauseAsync(engine, PauseAction.Hour, "Etc/GMT+5", () => Now);
        Assert.IsTrue(result.IsPaused(Now));
        Assert.AreEqual((HttpMethod.Put, "/api/schedule/plan?tz=Etc%2FGMT%2B5", """{"pause":"1h"}""", (TimeSpan?)ScanControl.MutationTimeout),
            engine.Requests[1]);

        var notPaused = new FakeEngine((method, _, _) => method == HttpMethod.Get ? Reply() : Schedule(null));
        await Assert.ThrowsExactlyAsync<InvalidDataException>(() => ScanControl.PauseAsync(notPaused, PauseAction.Tomorrow, "UTC", () => Now));

        var resumeUnpaused = new FakeEngine((_, _, _) => Reply());
        await Assert.ThrowsExactlyAsync<ControlStateChangedException>(() => ScanControl.PauseAsync(resumeUnpaused, PauseAction.Resume, "UTC", () => Now));
        var timers = new FakeEngine((_, _, _) => Reply(scan: Picture(scheduling: "timers")));
        await Assert.ThrowsExactlyAsync<ControlStateChangedException>(() => ScanControl.PauseAsync(timers, PauseAction.Hour, "UTC", () => Now));
        Assert.AreEqual(1, resumeUnpaused.Requests.Count, "a refusal sends no change");
        Assert.AreEqual(1, timers.Requests.Count, "a refusal sends no change");

        var resumed = new FakeEngine((method, _, _) => method == HttpMethod.Get
            ? Reply(scan: Picture(pausedUntil: "2026-11-08T16:00:00Z")) : Schedule(null));
        Assert.IsNull((await ScanControl.PauseAsync(resumed, PauseAction.Resume, "America/Los_Angeles", () => Now)).PausedUntil);
        Assert.AreEqual("""{"pause":"resume"}""", resumed.Requests[1].Body);
        Assert.ThrowsExactly<ArgumentException>(() => ScanControl.PlanTarget(""));
    }

    [TestMethod]
    public void TheAccountZoneIsNamedTheWayTheEngineReadsIt()
    {
        var zone = ScanControl.LocalTimezone();
        Assert.IsTrue(zone == "UTC" || zone.Contains('/'), zone);
        Assert.IsTrue(TimeZoneInfo.TryFindSystemTimeZoneById(zone, out _), zone);
    }

    [TestMethod]
    public void TheEngineIsToldTheMachinesZoneAndTzStaysUnset()
    {
        // Python has no map from Windows zone names, and the C runtime reads TZ in its own form.
        var state = Path.Combine(Path.GetTempPath(), "roleband-zone-tests", Guid.NewGuid().ToString("N"));
        var start = new EngineConfiguration(state, state, "must-not-run.exe", "must-not-run.exe", "test", true, true).EngineStart([]);
        Assert.AreEqual(ScanControl.LocalTimezone(), start.Environment["ROLEBAND_LOCAL_ZONE"]);
        Assert.IsFalse(start.Environment.ContainsKey("TZ"));
    }
}

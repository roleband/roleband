using System.Text.Json.Nodes;
using Microsoft.VisualStudio.TestTools.UnitTesting;
using static RoleBand.EngineHost.Tests.ScanTests;

namespace RoleBand.EngineHost.Tests;

[TestClass]
public sealed class CompanionTests
{
    private static readonly string[] Languages = ["en", "es", "zh-Hans"];
    private static readonly EngineSnapshot Ready = new(EngineState.Ready);
    private static readonly NativeCopy English = new("en");
    private static readonly DateTimeOffset LastScan = new(2026, 11, 8, 13, 40, 12, TimeSpan.Zero);

    private static FlyoutView View(EngineSnapshot engine, ScanStatus? status = null, ScanAction? requested = null,
                                   DateTimeOffset? lastScanAt = null, bool setupComplete = true, NativeCopy? copy = null) =>
        Companion.View(copy ?? English, engine, status, requested, lastScanAt, setupComplete, Now);

    private static JsonArray Companies(params string[] names) =>
        new(names.Select(name => (JsonNode)new JsonObject { ["name"] = name, ["since"] = "2026-11-08T14:58:00Z" }).ToArray());

    private static ScanStatus Scanning(int companies, bool manual = false) => Status(Reply("scanning", running: true, manual: manual,
        scan: Picture("collecting", percent: 38, total: 41, pending: 12, recorded: 700,
            inFlight: Companies(new[] { "Nvidia", "Apple", "Google", "Acme Robotics", "Northwind" }[..companies]))));

    [TestMethod]
    public void AScanShowsItsProgressWhatItFoundWhoItReadsAndTheNextScan()
    {
        var view = View(Ready, Scanning(5));
        Assert.AreEqual("Scanning companies", view.Title);
        Assert.AreEqual(("38%", 38.0), (view.Corner, view.Progress));
        CollectionAssert.AreEqual(new[] { "712 roles found so far", "Reading Nvidia, Apple, Google and 2 more" },
            view.Lines.Take(2).Select(line => line.Text).ToArray());
        StringAssert.StartsWith(view.Lines[2].Text, "Next scan at ");
        Assert.AreEqual((TrayBadge.Scanning, "RoleBand: Scanning companies · 38%"), (view.Badge, view.Tooltip));
        Assert.AreEqual((FlyoutPrimary.OpenRadar, true), (view.Primary, view.PrimaryEnabled));
        Assert.IsNull(view.Scan, "a scheduled scan has no Stop; only a scan someone asked for does");
        Assert.AreEqual(ScanAction.Stop, View(Ready, Scanning(5, manual: true)).Scan);

        Assert.AreEqual("Reading Nvidia, Apple, Google", View(Ready, Scanning(3)).Lines[1].Text, "three fit without a count");
        Assert.AreEqual("Reading Nvidia", View(Ready, Scanning(1)).Lines[1].Text);
    }

    [TestMethod]
    public void AtRestTheLastScanLeadsAndItsNewRolesOpenNew()
    {
        var view = View(Ready, Status(Reply()));
        StringAssert.StartsWith(view.Title, "Last scan today at ");
        Assert.AreEqual(new FlyoutLine("41 companies scanned", "7 new roles", BrowserRoute.NewRoles), view.Lines[0]);
        StringAssert.StartsWith(view.Lines[1].Text, "Next scan at ");
        Assert.AreEqual((TrayBadge.None, "RoleBand: Ready"), (view.Badge, view.Tooltip));
        Assert.AreEqual((ScanAction.Start, PauseControl.Menu, false), (view.Scan, view.Pause, view.Details));

        var none = View(Ready, Status(Reply(scan: Picture(newRoles: 0)))).Lines[0];
        Assert.AreEqual(new FlyoutLine("41 companies scanned · 0 new roles"), none, "no new roles, nothing to open");
        var never = Reply(scan: Picture(lastCompanies: null));
        never["launcher"]!["status"]!["last_scan_at"] = null;
        Assert.AreEqual("Not scanned yet", View(Ready, Status(never)).Title, "a radar that never scanned says so instead of inventing a time");
    }

    [TestMethod]
    public void APauseLeadsWithItsEndAndSaysScanNowStillWorks()
    {
        var view = View(Ready, Status(Reply(scan: Picture(pausedUntil: "2026-11-08T17:30:00Z"))));
        StringAssert.StartsWith(view.Title, "Paused until ");
        Assert.AreEqual(TrayBadge.Paused, view.Badge);
        Assert.AreEqual("RoleBand: " + view.Title, view.Tooltip);
        StringAssert.StartsWith(view.Lines[0].Text, "Last scan today at ");
        Assert.AreEqual(("7 new roles", BrowserRoute.NewRoles), (view.Lines[0].Link, view.Lines[0].Opens));
        Assert.AreEqual("Scheduled scans wait. Scan now still works.", view.Lines[^1].Text);
        Assert.AreEqual((ScanAction.Start, PauseControl.Resume), (view.Scan, view.Pause));
    }

    [TestMethod]
    public void AStoppedEngineOffersRestartAndDetailsAndTurnsTheBadgeRed()
    {
        var view = View(new EngineSnapshot(EngineState.Attention, "engine exited with code 1"), lastScanAt: LastScan);
        Assert.AreEqual("Scanning has stopped", view.Title);
        Assert.AreEqual((FlyoutPrimary.Restart, true, true), (view.Primary, view.PrimaryEnabled, view.Details));
        Assert.AreEqual((null, PauseControl.None), (view.Scan, view.Pause));
        Assert.AreEqual((TrayBadge.Stopped, "RoleBand: Scanning has stopped"), (view.Badge, view.Tooltip));
        Assert.AreEqual(English["host-attention-body"], view.Lines[0].Text);
        StringAssert.StartsWith(view.Lines[1].Text, "Last scan today at ", "the last scan the app saw stays in view");

        var stopped = View(new EngineSnapshot(EngineState.Stopped));
        Assert.AreEqual((FlyoutPrimary.Restart, TrayBadge.Stopped, 0), (stopped.Primary, stopped.Badge, stopped.Lines.Count));
        Assert.AreEqual(TrayBadge.Stopped, View(new EngineSnapshot(EngineState.Stopped), setupComplete: false).Badge,
            "a stopped engine stays red even before setup finishes");
    }

    [TestMethod]
    public void AnEngineOnItsWayWaitsWithOpenRadarOff()
    {
        foreach (var state in new[] { EngineState.Starting, EngineState.Preparing, EngineState.Recovering, EngineState.Stopping })
        {
            var view = View(new EngineSnapshot(state));
            Assert.AreEqual((false, true, "panel-open-radar-waiting"), (view.PrimaryEnabled, view.Busy, view.PrimaryHelpKey), state.ToString());
            Assert.AreEqual((null, PauseControl.None, TrayBadge.Scanning), (view.Scan, view.Pause, view.Badge), state.ToString());
        }
        Assert.AreEqual(English["host-recovering-body"], View(new EngineSnapshot(EngineState.Recovering)).Lines[0].Text);
    }

    [TestMethod]
    public void AHoldNeedsAttentionWithItsReasonAndAnUnfinishedSetupSaysSo()
    {
        var held = View(Ready, Status(Reply(hold: new JsonObject { ["kind"] = "attention", ["reason"] = "model_missing" })));
        Assert.AreEqual(("Needs attention", English["reason-model"], TrayBadge.Attention), (held.Title, held.Lines[0].Text, held.Badge));
        var waiting = View(Ready, Status(Reply(hold: new JsonObject { ["kind"] = "waiting", ["reason"] = "preflight_running" })));
        Assert.AreEqual((English["waiting"], TrayBadge.Attention), (waiting.Title, waiting.Badge));

        var unfinished = View(new EngineSnapshot(EngineState.Starting), setupComplete: false);
        Assert.AreEqual((TrayBadge.Attention, "RoleBand: Setup isn't finished"), (unfinished.Badge, unfinished.Tooltip));
    }

    [TestMethod]
    public void TheMenuPutsTheBoldDefaultFirstAndQuitLastAndLeavesOutWhatDoesNotApply()
    {
        MenuCommand?[] Commands(IReadOnlyList<MenuEntry> menu) => menu.Select(entry => entry.Command).ToArray();
        IReadOnlyList<MenuEntry> Menu(EngineSnapshot engine, ScanStatus? status = null, ScanAction? requested = null, bool setup = true) =>
            Companion.Menu(English, engine, View(engine, status, requested, setupComplete: setup), setup);

        var rest = Menu(Ready, Status(Reply()));
        CollectionAssert.AreEqual(new MenuCommand?[] { MenuCommand.OpenRadar, MenuCommand.ScanNow, null, null, MenuCommand.Settings, null, MenuCommand.Quit },
            Commands(rest));
        Assert.IsTrue(rest[0].Default);
        Assert.AreEqual(("Pause scans", false), (rest[2].Text, rest[2].Checked));
        CollectionAssert.AreEqual(new MenuCommand?[] { MenuCommand.PauseHour, MenuCommand.PauseThreeHours, MenuCommand.PauseTomorrow },
            rest[2].Items!.Select(item => item.Command).ToArray());
        Assert.AreEqual("Quit RoleBand", rest[^1].Text);

        var paused = Menu(Ready, Status(Reply(scan: Picture(pausedUntil: "2026-11-08T17:30:00Z"))));
        Assert.IsTrue(paused[2].Checked, "a pause shows as the item's checked state");
        CollectionAssert.AreEqual(new MenuCommand?[] { MenuCommand.Resume }, paused[2].Items!.Select(item => item.Command).ToArray());

        Assert.AreEqual(MenuCommand.StopScan, Menu(Ready, Scanning(2, manual: true))[1].Command);
        Assert.IsFalse(Commands(Menu(Ready, Status(Reply()), ScanAction.Start)).Contains(MenuCommand.ScanNow), "a request on its way has no second item");

        var stopped = Menu(new EngineSnapshot(EngineState.Attention));
        CollectionAssert.AreEqual(new MenuCommand?[] { MenuCommand.Settings, MenuCommand.Restart, null, MenuCommand.Quit }, Commands(stopped));
        Assert.IsTrue(stopped[0].Default);
        Assert.AreEqual("Restart scanning", stopped[1].Text);

        var starting = Menu(new EngineSnapshot(EngineState.Starting));
        CollectionAssert.AreEqual(new MenuCommand?[] { MenuCommand.Settings, null, MenuCommand.Quit }, Commands(starting));

        var setup = Menu(new EngineSnapshot(EngineState.Stopped), setup: false);
        Assert.AreEqual((MenuCommand.FinishSetup, true), (setup[0].Command, setup[0].Default));

        foreach (var menu in new[] { rest, paused, stopped, starting, setup })
        {
            Assert.IsTrue(menu.Count(entry => entry.Default) <= 1, "one bold command at most");
            Assert.AreEqual(MenuCommand.Quit, menu[^1].Command);
            Assert.IsFalse(menu[0].IsSeparator);
            for (var index = 1; index < menu.Count; index++)
                Assert.IsFalse(menu[index].IsSeparator && menu[index - 1].IsSeparator, "no empty group");
        }
    }

    [TestMethod]
    public void ADoubleClickAndStartRunTheDefaultCommand()
    {
        Assert.AreEqual(DefaultCommand.Setup, Companion.Default(Ready, setupComplete: false));
        Assert.AreEqual(DefaultCommand.OpenRadar, Companion.Default(Ready, setupComplete: true));
        Assert.AreEqual(DefaultCommand.OpenRadar, Companion.Default(new EngineSnapshot(EngineState.Starting), true),
            "an engine still starting opens the Radar once it answers");
        Assert.AreEqual(DefaultCommand.Settings, Companion.Default(new EngineSnapshot(EngineState.Attention), true));
        Assert.AreEqual(DefaultCommand.Settings, Companion.Default(new EngineSnapshot(EngineState.Stopped), true));
        Assert.AreEqual(PauseAction.ThreeHours, Companion.Pause(MenuCommand.PauseThreeHours));
        Assert.AreEqual(PauseAction.Resume, Companion.Pause(MenuCommand.Resume));
        Assert.IsNull(Companion.Pause(MenuCommand.Quit));
    }

    [TestMethod]
    public void EveryStateHasWordsAndAOneLineTooltipInEveryLanguage()
    {
        EngineSnapshot[] engines = [.. Enum.GetValues<EngineState>().Select(state => new EngineSnapshot(state))];
        ScanStatus?[] statuses =
        [
            null, Status(Reply()), Scanning(5), Scanning(5, manual: true), Status(Reply(scan: Picture(pausedUntil: "2026-11-08T17:30:00Z"))),
            Status(Reply("updating")), Status(Reply(hold: new JsonObject { ["kind"] = "attention", ["reason"] = "anything" })),
            Status(Reply(queued: "scan")), Status(Reply(scan: Picture(lastCompanies: null, next: null, scheduling: "off"))),
        ];
        foreach (var language in Languages)
        {
            var copy = new NativeCopy(language);
            foreach (var engine in engines)
            foreach (var status in statuses)
            foreach (var setup in new[] { true, false })
            {
                var view = View(engine, engine.State == EngineState.Ready ? status : null, lastScanAt: LastScan, setupComplete: setup, copy: copy);
                Assert.IsFalse(string.IsNullOrWhiteSpace(view.Title), $"{language} {engine.State}");
                Assert.IsTrue(view.Tooltip.StartsWith("RoleBand: ") && view.Tooltip.Length <= 127 && !view.Tooltip.Contains('\n'), view.Tooltip);
                Assert.IsTrue(view.Lines.Count <= 3, "a summary, not a report");
                foreach (var entry in Companion.Menu(copy, engine, view, setup).Where(entry => !entry.IsSeparator))
                    Assert.IsFalse(string.IsNullOrWhiteSpace(entry.Text));
            }
        }
    }

    [TestMethod]
    public void SettingsLeadsWithAProblemOnlyWhileThereIsOne()
    {
        Assert.AreEqual(new SettingsProblem("host-stopped", "host-attention-body", false, true),
            SettingsPanel.Problem(new EngineSnapshot(EngineState.Attention), updateFailed: false, held: false));
        Assert.AreEqual(new SettingsProblem("host-stopped", null, false, true),
            SettingsPanel.Problem(new EngineSnapshot(EngineState.Stopped), false, false));
        Assert.AreEqual(new SettingsProblem("update-stopped-title", "update-stopped-body", true, true),
            SettingsPanel.Problem(new EngineSnapshot(EngineState.Stopped), updateFailed: true, held: false));
        Assert.IsNull(SettingsPanel.Problem(Ready, updateFailed: true, held: false), "an engine that answers has nothing left to undo");
        Assert.IsNull(SettingsPanel.Problem(new EngineSnapshot(EngineState.Starting), false, false));
        Assert.IsNull(SettingsPanel.Problem(new EngineSnapshot(EngineState.Stopped), false, held: true),
            "setup holding the engine is not a stop, and Restart would start what setup holds");
        Assert.IsFalse(SettingsPanel.LaunchFailed.Restart, "an app that could not start has no engine to restart");
    }

    [TestMethod]
    public void ALaunchFromStartAsksForTheRadarOnceTheEngineAnswers()
    {
        var finished = SetupRecord.Finished;
        Assert.AreEqual(LaunchAction.RadarWhenReady, Companion.AtLaunch(finished, atLogin: false),
            "at launch the engine has not started yet, so the Radar waits rather than Settings opening");
        Assert.AreEqual(LaunchAction.Quiet, Companion.AtLaunch(finished, atLogin: true));
        Assert.AreEqual(LaunchAction.Setup, Companion.AtLaunch(SetupRecord.Fresh, atLogin: false));
        Assert.AreEqual(LaunchAction.Quiet, Companion.AtLaunch(SetupRecord.Fresh with { Deferred = true }, atLogin: false),
            "setup put off waits for the icon");

        Assert.IsNull(Companion.WhenSettled(new EngineSnapshot(EngineState.Stopped)), "not started yet: keep waiting");
        Assert.IsNull(Companion.WhenSettled(new EngineSnapshot(EngineState.Starting)));
        Assert.IsNull(Companion.WhenSettled(new EngineSnapshot(EngineState.Recovering)));
        Assert.AreEqual(DefaultCommand.OpenRadar, Companion.WhenSettled(Ready));
        Assert.AreEqual(DefaultCommand.Settings, Companion.WhenSettled(new EngineSnapshot(EngineState.Attention, "gave up")));
        Assert.AreEqual(DefaultCommand.Settings, Companion.WhenSettled(new EngineSnapshot(EngineState.Stopped, "refused")));
    }
}

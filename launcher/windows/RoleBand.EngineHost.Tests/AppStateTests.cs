using Microsoft.VisualStudio.TestTools.UnitTesting;

namespace RoleBand.EngineHost.Tests;

/// <summary>Every surface in every state: a control is shown only where pressing it does something, and every state that
/// is not on its way somewhere offers a way on. What each control needs is derived here from the raw state, apart from the
/// code under test.</summary>
[TestClass]
public sealed class AppStateTests
{
    private static readonly DateTimeOffset Now = new(2026, 11, 9, 18, 0, 0, TimeSpan.Zero);
    private const string Offer = "0.1.19", Running = "0.1.18", Previous = "0.1.17";

    private static IEnumerable<AppState> States()
    {
        EngineSnapshot?[] engines = [null, .. Enum.GetValues<EngineState>().Select(state => new EngineSnapshot(state))];
        UpdateFacts?[] facts = [null, UpdateFacts.Unavailable, new(true, false, Now, null, null), new(true, true, Now, Offer, null)];
        LastUpdate?[] lasts = [null, new("preparing", Previous, Running, "to"), new("failed", Previous, Running, "to"),
            new("recovering", Previous, Running, "to"), new("recovered", Previous, Running, "from"),
            new("complete", Previous, Running, "to"), new("applying", Previous, Running, "from")];
        UpdateRun?[] runs = [null, .. Enum.GetValues<UpdateStep>().Select(step => new UpdateRun(step, Offer))];
        foreach (var engine in engines)
        foreach (var setup in new[] { SetupRecord.Finished, SetupRecord.Fresh })
        foreach (var fact in facts)
        foreach (var last in fact is { Available: true } ? lasts : [null])
        // An update only runs where the feed answered: a build that does not update itself never downloads.
        foreach (var run in fact is { Available: true } ? runs : [null])
        foreach (var failed in new[] { false, true })
        foreach (var checking in new[] { false, true })
        // Only the feed can say a release is gone, so a refusal for that needs one that answered.
        foreach (var (returningTo, returning, undoFailure, gone) in failed
            ? new (string?, bool, string?, bool)[]
            {
                (null, false, null, false), (Previous, false, null, false), (Previous, true, null, false), (Previous, false, "refused", false),
            }.Concat(fact is { Available: true } ? [(Previous, false, "gone", true)] : [])
            : [(null, false, null, false)])
            yield return new AppState(engine, engine is null ? "The installation could not be read." : null, setup,
                new UpdateState(fact is { Available: true } ? fact with { Last = last } : fact, run, checking, null, failed,
                    returningTo, returning, undoFailure, UndoGone: gone), Now);
    }

    private static bool UpdateFailed(AppState state) => state.Update.Failed || state.Update.Facts?.Last is { Running: "to", Phase: "failed" or "recovering" };

    private static bool Switching(AppState state) =>
        state.Update.Run is { Step: UpdateStep.Downloading or UpdateStep.Paused or UpdateStep.Restarting } || state.Update.Returning;

    private static bool Downloading(AppState state) => state.Update.Run is { Step: UpdateStep.Downloading or UpdateStep.Paused };

    private static bool CanStart(AppState state) => state.Engine is { State: EngineState.Stopped or EngineState.Attention }
        && !SetupFlow.EngineHeld(state.Setup) && !UpdateFailed(state) && state.Update.ReturningTo is null && !Switching(state);

    private static bool CanUndo(AppState state) => state.Engine is not null && UpdateFailed(state) && !Switching(state) && !state.Update.UndoGone;

    /// <summary>An Undo refused before it began leaves the journal failed, which a newer release may take over.</summary>
    private static bool Refused(AppState state) => state.Update.UndoFailure is not null && !state.Update.Returning;

    private static bool CanInstall(AppState state) => state.Update.Facts?.Offer is not null && !Switching(state)
        && (state.Update.ReturningTo is null || (Refused(state) && state.Update.Facts?.Last?.Phase == "failed"));

    private static string Describe(AppState state) =>
        $"engine {state.Engine?.State.ToString() ?? "none"}, setup {(state.Setup.Complete ? "done" : "fresh")}, offer {state.Update.Facts?.Offer ?? "-"}, " +
        $"available {state.Update.Facts?.Available.ToString() ?? "-"}, last {state.Update.Facts?.Last?.Phase ?? "-"}/{state.Update.Facts?.Last?.Running ?? "-"}, " +
        $"run {state.Update.Run?.Step.ToString() ?? "-"}, failed {state.Update.Failed}, returning {state.Update.ReturningTo ?? "-"}/{state.Update.Returning}, " +
        $"refused {state.Update.UndoFailure ?? "-"}/{state.Update.UndoGone}, checking {state.Update.Checking}";

    [TestMethod]
    public void EveryShownControlCanActInItsState()
    {
        var copy = new NativeCopy("en");
        var count = 0;
        foreach (var state in States())
        {
            count++;
            var surfaces = AppSurfaces.Of(copy, state);
            var (flyout, menu, problem, row) = (surfaces.Flyout, surfaces.Menu, surfaces.Problem, surfaces.Updates);
            var where = Describe(state);
            var commands = menu.Where(entry => entry.Command is not null).Select(entry => entry.Command!.Value).ToHashSet();

            var restart = (flyout.Primary == FlyoutPrimary.Restart && flyout.PrimaryEnabled) || commands.Contains(MenuCommand.Restart)
                || problem?.Restart == true;
            if (restart) Assert.IsTrue(CanStart(state), "Restart shown where it cannot start the engine: " + where);

            var undo = (flyout.Primary == FlyoutPrimary.Undo && flyout.PrimaryEnabled) || commands.Contains(MenuCommand.Undo) || problem?.Undo == true;
            if (undo) Assert.IsTrue(CanUndo(state), "Undo shown with no failed update to undo: " + where);

            var install = flyout.Update?.Action is not null || commands.Contains(MenuCommand.Update) || problem?.Newer is not null || row.Action is not null;
            if (install) Assert.IsTrue(CanInstall(state), "Update shown with nothing it could install: " + where);

            var radar = (flyout.Primary == FlyoutPrimary.OpenRadar && flyout.PrimaryEnabled) || commands.Contains(MenuCommand.OpenRadar);
            if (radar) Assert.AreEqual(EngineState.Ready, state.Engine?.State, "Open Radar shown with no Radar to open: " + where);

            var scan = flyout.Scan is not null || flyout.Pause != PauseControl.None
                || commands.Overlaps([MenuCommand.ScanNow, MenuCommand.StopScan, MenuCommand.PauseHour, MenuCommand.Resume]);
            if (scan) Assert.AreEqual(EngineState.Ready, state.Engine?.State, "A scan control shown with no engine to ask: " + where);

            var cancel = row.Cancel || flyout.Update?.Cancel == true;
            if (cancel) Assert.IsTrue(Downloading(state), "Cancel shown with no download to stop: " + where);
            if (Downloading(state)) Assert.IsTrue(row.Cancel, "A download Settings cannot cancel: " + where);

            if (row.CanCheck) Assert.IsTrue(!state.Update.Checking && !Switching(state) && state.Update.Facts?.Last is not { Finishing: true },
                "Check for updates shown while a check or an update runs: " + where);
            if (UpdateFailed(state)) Assert.AreNotEqual(UpdateRowKind.Current, row.Kind, "A failed update called up to date: " + where);
            if (Refused(state))
                Assert.IsFalse(flyout.Title.StartsWith("Returning to", StringComparison.Ordinal)
                    || flyout.Update?.Title.StartsWith("Returning to", StringComparison.Ordinal) == true,
                    "A refused Undo still said to be returning: " + where);

            // A way on: every state that is not on its way somewhere offers something to press beyond Settings and Quit.
            var onItsWay = flyout.Busy || problem?.Busy == true || row.Busy;
            var action = (flyout.PrimaryEnabled) || flyout.Scan is not null || flyout.Update?.Action is not null || cancel
                || commands.Except([MenuCommand.Settings, MenuCommand.Quit]).Any() || problem?.Restart == true || problem?.Undo == true;
            if (!onItsWay && state.Engine is not null)
                Assert.IsTrue(action, "A state with no way on: " + where);
            if (CanStart(state)) Assert.IsTrue(restart, "The engine can start but nothing offers Restart: " + where);
            if (CanUndo(state) && state.Update.ReturningTo is null) Assert.IsTrue(undo, "A failed update with no Undo: " + where);
        }
        Assert.IsTrue(count > 10_000, $"{count} states");
    }

    [TestMethod]
    public void AFailedUpdateLeadsWithUndoEverywhereAndOffersTheNewerRelease()
    {
        var copy = new NativeCopy("en");
        var failed = new AppState(new EngineSnapshot(EngineState.Stopped), null, SetupRecord.Finished,
            new UpdateState(new UpdateFacts(true, true, Now, Offer, null, new LastUpdate("failed", Previous, Running, "to")), Failed: true), Now);
        var surfaces = AppSurfaces.Of(copy, failed);
        Assert.AreEqual(("An update couldn't finish", FlyoutPrimary.Undo, true, TrayBadge.Attention),
            (surfaces.Flyout.Title, surfaces.Flyout.Primary, surfaces.Flyout.PrimaryEnabled, surfaces.Flyout.Badge));
        Assert.AreEqual(("Version 0.1.19 is ready", "Update"), (surfaces.Flyout.Update?.Title, surfaces.Flyout.Update?.Action));
        CollectionAssert.AreEqual(new MenuCommand?[] { MenuCommand.Settings, MenuCommand.Undo, MenuCommand.Update, null, MenuCommand.Quit },
            surfaces.Menu.Select(entry => entry.Command).ToArray());
        Assert.AreEqual(("Update to 0.1.19", true), (surfaces.Menu[2].Text, surfaces.Menu[0].Default));
        Assert.AreEqual(DefaultCommand.Settings, surfaces.Default, "a double-click explains before anything is undone");
        var alone = AppSurfaces.Of(copy, failed with { Update = failed.Update with { Facts = failed.Update.Facts! with { Offer = null } } });
        Assert.IsNull(alone.Flyout.Update);
        CollectionAssert.DoesNotContain(alone.Menu.Select(entry => entry.Command).ToArray(), MenuCommand.Update);
    }

    [TestMethod]
    public void AnUndoRefusedForAReleaseThatIsGoneLeadsWithCheckForUpdatesAndTheNewerRelease()
    {
        var copy = new NativeCopy("en");
        var failed = new UpdateFacts(true, false, Now, null, null, new LastUpdate("failed", Previous, Running, "to"));
        var gone = new AppState(new EngineSnapshot(EngineState.Stopped), null, SetupRecord.Finished,
            new UpdateState(failed, Failed: true, ReturningTo: Previous, UndoFailure: "no longer published", UndoGone: true), Now);
        var surfaces = AppSurfaces.Of(copy, gone);
        Assert.AreEqual(("Couldn't return to 0.1.17", FlyoutPrimary.CheckUpdates, true), (surfaces.Flyout.Title, surfaces.Flyout.Primary,
            surfaces.Flyout.PrimaryEnabled));
        StringAssert.StartsWith(surfaces.Flyout.Lines.Single().Text, "0.1.17 is no longer available to download");
        Assert.AreEqual(("windows-update-undo-gone-body", false), (surfaces.Problem?.BodyKey, surfaces.Problem?.Undo),
            "pressing Undo again cannot bring the release back");
        CollectionAssert.DoesNotContain(surfaces.Menu.Select(entry => entry.Command).ToArray(), MenuCommand.Undo);

        var newer = AppSurfaces.Of(copy, gone with { Update = gone.Update with { Facts = failed with { Offer = Offer } } });
        Assert.AreEqual(("Version 0.1.19 is ready", "Update", "0.1.19"),
            (newer.Flyout.Update?.Title, newer.Flyout.Update?.Action, newer.Problem?.Newer), "a newer release is the way on");
        CollectionAssert.Contains(newer.Menu.Select(entry => entry.Command).ToArray(), MenuCommand.Update);

        var refused = AppSurfaces.Of(copy, gone with { Update = gone.Update with { UndoGone = false, UndoFailure = "offline" } });
        Assert.AreEqual(("Couldn't return to 0.1.17", FlyoutPrimary.Undo, true, true),
            (refused.Flyout.Title, refused.Flyout.Primary, refused.Flyout.PrimaryEnabled, refused.Problem?.Undo), "offline: Undo again");
        Assert.IsFalse(refused.Flyout.Busy, "never Returning to after a refusal");
    }

    [TestMethod]
    public void ATryAgainForAnOfferThatIsGoneIsNotShown()
    {
        var copy = new NativeCopy("en");
        var run = new UpdateRun(UpdateStep.DownloadFailed, Offer);
        Assert.AreEqual("Try again", AboutPanel.Updates(copy, new UpdateFacts(true, false, Now, Offer, null), false, null, Now, run).Action);
        Assert.IsNull(AboutPanel.Updates(copy, new UpdateFacts(true, false, Now, null, null), false, null, Now, run).Action,
            "Try again installs the offer; without one it would do nothing");
    }
}

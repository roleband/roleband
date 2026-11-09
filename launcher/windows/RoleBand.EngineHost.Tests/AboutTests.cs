using System.Text.Json;
using Microsoft.VisualStudio.TestTools.UnitTesting;

namespace RoleBand.EngineHost.Tests;

[TestClass]
public sealed class AboutTests
{
    [TestMethod]
    public void AnInstalledPackageShowsItsOwnVersionAndASourceRunTheEngines()
    {
        Assert.AreEqual("0.1.4", AboutPanel.Version("0.1.2", (0, 1, 4, 0)));
        Assert.AreEqual("0.1.1.5", AboutPanel.Version("0.1.2", (0, 1, 1, 5)));
        Assert.AreEqual("0.1.2", AboutPanel.Version("0.1.2", null));
    }

    private static readonly DateTimeOffset Now = new(2026, 11, 8, 15, 0, 0, TimeSpan.Zero);
    private static readonly double NowSeconds = Now.ToUnixTimeSeconds();
    private static readonly string[] Languages = ["en", "es", "zh-Hans"];

    private static UpdateFacts Facts(string json)
    {
        using var document = JsonDocument.Parse(json);
        return UpdateFacts.Read(document.RootElement);
    }

    [TestMethod]
    public void TheUpdateAnswersAreReadFromStatusAndFromACheck()
    {
        Assert.AreEqual(new UpdateFacts(false, false, null, null, null), Facts("""{"status":"unavailable","reason":"no identity"}"""));
        var status = Facts($$"""{"status":"ok","automatic":true,"checked_at":{{NowSeconds - 60}},"offer":"0.1.3","rate_limited_until":null}""");
        Assert.AreEqual(new UpdateFacts(true, true, Now.AddSeconds(-60), "0.1.3", null), status);
        var check = Facts($$$"""{"status":"rate-limited","until":{{{NowSeconds + 120}}},"checked_at":null,"automatic":false,"offer":{"version":"0.1.4","sha256":"ab"}}""");
        Assert.AreEqual(new UpdateFacts(true, false, null, "0.1.4", Now.AddSeconds(120)), check);
        Assert.ThrowsExactly<IOException>(() => Facts("""{"recorded":true}"""));
        Assert.ThrowsExactly<IOException>(() => Facts("[]"));
    }

    [TestMethod]
    public void UpToDateNeedsACheckTheFeedAnswered()
    {
        var copy = new NativeCopy("en");
        var never = AboutPanel.Updates(copy, new UpdateFacts(true, false, null, null, null), false, null, Now);
        Assert.AreEqual((UpdateRowKind.Never, "Not checked yet"), (never.Kind, never.Title), "an unchecked state never implies success");
        Assert.IsNull(never.Caption);
        Assert.AreEqual(UpdateRowKind.Never, AboutPanel.Updates(copy, null, false, null, Now).Kind);
        var current = AboutPanel.Updates(copy, new UpdateFacts(true, false, Now.AddMinutes(-5), null, null), false, null, Now);
        Assert.AreEqual((UpdateRowKind.Current, "Up to date"), (current.Kind, current.Title));
        StringAssert.StartsWith(current.Caption, "Checked ");
        var offered = AboutPanel.Updates(copy, new UpdateFacts(true, true, Now, "0.1.3", null), false, null, Now);
        Assert.AreEqual((UpdateRowKind.Offered, "Version 0.1.3 is ready"), (offered.Kind, offered.Title));
    }

    [TestMethod]
    public void AFailedCheckSaysSoAndCheckNowStaysOneTapAway()
    {
        var copy = new NativeCopy("en");
        var checkedBefore = new UpdateFacts(true, false, Now.AddHours(-3), null, null);
        var failed = AboutPanel.Updates(copy, checkedBefore, false, "failed", Now);
        Assert.AreEqual((UpdateRowKind.Failed, "Couldn't check", true), (failed.Kind, failed.Title, failed.CanCheck));
        StringAssert.StartsWith(failed.Caption, "Checked ", "the last success stays in view");
        var limited = AboutPanel.Updates(copy, checkedBefore with { RateLimitedUntil = Now.AddMinutes(2) }, false, null, Now);
        Assert.AreEqual((UpdateRowKind.Failed, "Please try again later."), (limited.Kind, limited.Caption));
        Assert.AreEqual(UpdateRowKind.Current,
            AboutPanel.Updates(copy, checkedBefore with { RateLimitedUntil = Now.AddMinutes(-1) }, false, null, Now).Kind, "a limit that ended");
        var checking = AboutPanel.Updates(copy, checkedBefore, true, "failed", Now);
        Assert.AreEqual((UpdateRowKind.Checking, false), (checking.Kind, checking.CanCheck));
        var unavailable = AboutPanel.Updates(copy, new UpdateFacts(false, false, null, null, null), false, "failed", Now);
        Assert.AreEqual((UpdateRowKind.Unavailable, false, false), (unavailable.Kind, unavailable.CanCheck, unavailable.AutomaticEnabled));
    }

    private static (UpdateRun Run, string? Package) Downloaded(string json)
    {
        using var document = JsonDocument.Parse(json);
        return UpdateRun.Downloaded(document.RootElement, "0.1.12");
    }

    [TestMethod]
    public void ADownloadLeadsToTheSwitchOnlyWithAVerifiedPackage()
    {
        Assert.AreEqual((new UpdateRun(UpdateStep.Restarting, "0.1.12"), @"C:\state\packages\RoleBand-0.1.12-Windows-x64.msix"),
            Downloaded("""{"status":"downloaded","package":"C:\\state\\packages\\RoleBand-0.1.12-Windows-x64.msix","offer":{"version":"0.1.12"}}"""));
        Assert.AreEqual((new UpdateRun(UpdateStep.CheckFailed, "0.1.12"), (string?)null),
            Downloaded("""{"status":"failed","kind":"check","reason":"The download is not the signed release"}"""));
        Assert.AreEqual((new UpdateRun(UpdateStep.DownloadFailed, "0.1.12"), (string?)null),
            Downloaded("""{"status":"failed","kind":"download","reason":"offline"}"""));
        Assert.AreEqual(UpdateStep.DownloadFailed, Downloaded("""{"status":"no-offer"}""").Run.Step);
        Assert.AreEqual(UpdateStep.DownloadFailed, Downloaded("""{"status":"downloaded"}""").Run.Step, "no package, nothing to install");
        Assert.AreEqual(UpdateStep.DownloadFailed, Downloaded("[]").Run.Step);
    }

    [TestMethod]
    public void ALostConnectionPausesTheDownloadAndAFullDiskSaysHowMuchRoomItNeeds()
    {
        var before = new UpdateRun(UpdateStep.Downloading, "0.1.12", Received: 120, Total: 332);
        using (var offline = JsonDocument.Parse("""{"status":"failed","kind":"offline","reason":"connection lost"}"""))
            Assert.AreEqual((new UpdateRun(UpdateStep.Paused, "0.1.12", Received: 120, Total: 332), (string?)null),
                UpdateRun.Downloaded(offline.RootElement, "0.1.12", before), "the bytes already here still count");
        var (space, package) = Downloaded("""{"status":"failed","kind":"space","needed":1073741824,"reason":"full"}""");
        Assert.AreEqual((UpdateStep.NoSpace, 1073741824L, (string?)null), (space.Step, space.Needed, package));
        Assert.IsTrue(space.Failed && !space.InProgress && !space.Cancellable);
        Assert.IsNull(Downloaded("""{"status":"failed","kind":"space","needed":"lots"}""").Run.Needed, "no size made up from a malformed one");
        var paused = new UpdateRun(UpdateStep.Paused, "0.1.12");
        Assert.IsTrue(paused.InProgress && paused.Cancellable && !paused.Failed, "a paused download is still this session's update");
        Assert.IsFalse(new UpdateRun(UpdateStep.Restarting, "0.1.12").Cancellable, "Windows' install cannot be cancelled from here");
    }

    [TestMethod]
    public void OnlyTheDownloadsOwnProgressLinesCount()
    {
        Assert.AreEqual((120L, 332L), UpdateRun.Progress("""{"received":120,"total":332}"""));
        Assert.AreEqual((332L, 332L), UpdateRun.Progress("""{"received":400,"total":332}"""), "never past the whole");
        Assert.IsNull(UpdateRun.Progress("""{"received":0,"total":0}"""), "no total, nothing to measure against");
        Assert.IsNull(UpdateRun.Progress("""{"received":-1,"total":332}"""));
        Assert.IsNull(UpdateRun.Progress("""{"received":"120","total":332}"""));
        Assert.IsNull(UpdateRun.Progress("""{"status":"downloaded"}"""));
        Assert.IsNull(UpdateRun.Progress("Traceback (most recent call last):"));
        Assert.IsNull(UpdateRun.Progress(""));
    }

    [TestMethod]
    public void ADownloadSaysHowFarItHasGotAndCanBeCancelledUntilWindowsInstalls()
    {
        var copy = new NativeCopy("en");
        var facts = new UpdateFacts(true, false, Now, "0.1.12", null);
        const long megabyte = 1024 * 1024;
        var downloading = new UpdateRun(UpdateStep.Downloading, "0.1.12", Received: 120 * megabyte, Total: 332 * megabyte);

        var row = AboutPanel.Updates(copy, facts, false, null, Now, downloading);
        Assert.AreEqual((UpdateRowKind.Downloading, "Downloading 0.1.12", "120 MB of 332 MB", true, false, (string?)null),
            (row.Kind, row.Title, row.Caption, row.Cancel, row.CanCheck, row.Action));
        var banner = AboutPanel.Flyout(copy, facts, downloading)!;
        Assert.AreEqual(("120 MB of 332 MB", 36, true, true, (string?)null), (banner.Caption, banner.Percent, banner.Cancel, banner.Busy, banner.Action));
        var starting = AboutPanel.Updates(copy, facts, false, null, Now, downloading with { Received = null, Total = null });
        Assert.IsNull(starting.Caption, "nothing counted yet: no made-up progress");

        var paused = downloading with { Step = UpdateStep.Paused };
        row = AboutPanel.Updates(copy, facts, false, null, Now, paused);
        Assert.AreEqual((UpdateRowKind.Paused, "Download paused", "120 MB of 332 MB · Resumes once you're online.", true, false, false),
            (row.Kind, row.Title, row.Caption, row.Cancel, row.CanCheck, row.Busy));
        banner = AboutPanel.Flyout(copy, facts, paused)!;
        Assert.AreEqual((true, false, (string?)null), (banner.Cancel, banner.Busy, banner.Action), "waiting, not working: no spinner");

        var installing = AboutPanel.Updates(copy, facts, false, null, Now, new UpdateRun(UpdateStep.Restarting, "0.1.12", Percent: 40));
        Assert.IsFalse(installing.Cancel, "once Windows installs, Cancel would only lie");
        Assert.IsFalse(AboutPanel.Flyout(copy, facts, new UpdateRun(UpdateStep.Restarting, "0.1.12"))!.Cancel);
    }

    [TestMethod]
    public void AFullDiskSaysHowMuchRoomTheUpdateNeedsAndOffersTryAgain()
    {
        var copy = new NativeCopy("en");
        var facts = new UpdateFacts(true, false, Now, "0.1.12", null);
        var row = AboutPanel.Updates(copy, facts, false, null, Now, new UpdateRun(UpdateStep.NoSpace, "0.1.12", Needed: 1_288_490_189));
        Assert.AreEqual((UpdateRowKind.UpdateFailed, "Not enough space", "Needs 1.2 GB free.", "Try again", "update-no-space-help", false),
            (row.Kind, row.Title, row.Caption, row.Action, row.HelpKey, row.Cancel));
        var banner = AboutPanel.Flyout(copy, facts, new UpdateRun(UpdateStep.NoSpace, "0.1.12", Needed: 1_288_490_189))!;
        Assert.AreEqual(("Not enough space", "Needs 1.2 GB free.", "Try again", true), (banner.Title, banner.Caption, banner.Action, banner.Failed));
        var unknown = AboutPanel.Updates(copy, facts, false, null, Now, new UpdateRun(UpdateStep.NoSpace, "0.1.12"));
        Assert.AreEqual("Nothing was installed.", unknown.Caption, "no size made up when the command gave none");
    }

    [TestMethod]
    public void SizesReadAsFileExplorerGivesThemInTheCopysLanguage()
    {
        var english = new NativeCopy("en");
        Assert.AreEqual("0 MB", AboutPanel.Size(english, 0));
        Assert.AreEqual("1 MB", AboutPanel.Size(english, 1), "a few bytes are not nothing");
        Assert.AreEqual("332 MB", AboutPanel.Size(english, 332L * 1024 * 1024));
        Assert.AreEqual("999 MB", AboutPanel.Size(english, 999L * 1024 * 1024));
        Assert.AreEqual("1.0 GB", AboutPanel.Size(english, 1000L * 1024 * 1024), "four digits of megabytes read as gigabytes");
        Assert.AreEqual("1.0 GB", AboutPanel.Size(english, 1024L * 1024 * 1024));
        Assert.AreEqual("1.5 GB", AboutPanel.Size(english, 1536L * 1024 * 1024));
        Assert.AreEqual("1,5 GB", AboutPanel.Size(new NativeCopy("es"), 1536L * 1024 * 1024));
    }

    [TestMethod]
    public async Task APausedDownloadWaitsLongerEachTimeAndStopsWaitingOnCancel()
    {
        Assert.AreEqual(TimeSpan.FromSeconds(15), Reconnection.Delay(0));
        Assert.IsTrue(Reconnection.Delay(1) > Reconnection.Delay(0) && Reconnection.Delay(3) > Reconnection.Delay(2));
        Assert.AreEqual(TimeSpan.FromMinutes(5), Reconnection.Delay(100), "a long time offline settles at a few attempts an hour");
        var clock = System.Diagnostics.Stopwatch.StartNew();
        await Reconnection.WaitAsync(TimeSpan.FromMilliseconds(50), CancellationToken.None);
        Assert.IsTrue(clock.Elapsed < TimeSpan.FromSeconds(5));
        using var cancel = new CancellationTokenSource(TimeSpan.FromMilliseconds(50));
        clock.Restart();
        await Assert.ThrowsAsync<OperationCanceledException>(() => Reconnection.WaitAsync(TimeSpan.FromMinutes(5), cancel.Token));
        Assert.IsTrue(clock.Elapsed < TimeSpan.FromSeconds(5), "Cancel does not wait out the delay");
    }

    [TestMethod]
    public async Task TheDownloadPassesOnlyItsProgressLinesToTheApp()
    {
        var commands = new Commands(_ => """{"status":"downloaded","package":"C:\\state\\packages\\update.msix"}""")
        {
            Lines = ["""{"received":10,"total":20}""", "a warning", """{"received":20,"total":20}"""],
        };
        var seen = new List<(long, long)>();
        var coordinator = new UpdateCoordinator(commands, new NoDeployer());
        await coordinator.DownloadAsync(new Inline(value => seen.Add(value)));
        CollectionAssert.AreEqual(new[] { (10L, 20L), (20L, 20L) }, seen);
    }

    [TestMethod]
    public void OnlyASourceRunPlaysASimulatedUpdate()
    {
        var source = new EngineConfiguration("C:\\checkout", "C:\\state", "python.exe", "python.exe", "0.1.2", true, true);
        Assert.IsNotNull(SimulatedUpdate.For(source, "downloading"));
        Assert.IsNull(SimulatedUpdate.For(source with { Development = false }, "downloading"), "a packaged app never simulates");
        Assert.IsNull(SimulatedUpdate.For(source, "no-such-scenario"));
        Assert.IsNull(SimulatedUpdate.For(source, null));
    }

    [TestMethod]
    public async Task EachSimulatedDownloadEndsInTheStateItIsNamedFor()
    {
        var source = new EngineConfiguration("C:\\checkout", "C:\\state", "python.exe", "python.exe", "0.1.2", true, true);
        var expected = new Dictionary<string, UpdateStep>
        {
            ["paused"] = UpdateStep.Paused, ["space"] = UpdateStep.NoSpace, ["check"] = UpdateStep.CheckFailed,
            ["missing"] = UpdateStep.DownloadFailed, ["offer"] = UpdateStep.Restarting,
        };
        foreach (var (scenario, step) in expected)
        {
            var simulation = SimulatedUpdate.For(source, scenario)!;
            var coordinator = new UpdateCoordinator(simulation, simulation);
            var facts = await coordinator.StatusAsync();
            Assert.AreEqual("0.1.3", facts.Offer, scenario);
            var counted = new List<(long, long)>();
            var reply = await coordinator.DownloadAsync(new Inline(value => counted.Add(value)));
            Assert.AreEqual(step, UpdateRun.Downloaded(reply, "0.1.3").Run.Step, scenario);
            Assert.IsTrue(counted.All(value => value.Item2 == SimulatedUpdate.Size), scenario);
        }
    }

    [TestMethod]
    public async Task SimulatedStartsReachTheStatesTheyAreNamedFor()
    {
        var source = new EngineConfiguration("C:\\checkout", "C:\\state", "python.exe", "python.exe", "0.1.2", true, true);
        async Task<UpdateFacts> Facts(string scenario) => await new UpdateCoordinator(SimulatedUpdate.For(source, scenario)!,
            SimulatedUpdate.For(source, scenario)!).StatusAsync();
        Assert.AreEqual((true, "0.1.2"), ((await Facts("finishing")).Last!.Finishing, (await Facts("finishing")).Last!.To));
        Assert.IsTrue((await Facts("failed")).Last!.Unfinished);
        Assert.AreEqual("0.1.3", (await Facts("failed")).Offer, "a newer release beside Undo");
        Assert.IsNull((await Facts("failed-alone")).Offer);
        Assert.AreEqual(new UpdateRun(UpdateStep.Updated, "0.1.2"), (await Facts("updated")).Last!.Result);
        Assert.AreEqual(new UpdateRun(UpdateStep.RolledBack, "0.1.2", "0.1.3"), (await Facts("rolled-back")).Last!.Result);
        var gone = SimulatedUpdate.For(source, "undo-gone")!;
        Assert.AreEqual("undo", gone.Press);
        var answer = await gone.RunAsync(["recover-begin"], CancellationToken.None);
        Assert.AreEqual("missing", answer.GetProperty("kind").GetString());
    }

    private sealed class Inline(Action<(long, long)> report) : IProgress<(long Received, long Total)>
    {
        public void Report((long Received, long Total) value) => report(value);
    }

    [TestMethod]
    public void UpdateIsThePressThatInstallsTheOfferAndItsStepsReplaceIt()
    {
        var copy = new NativeCopy("en");
        var offer = new UpdateFacts(true, false, Now.AddMinutes(-1), "0.1.12", null);
        var offered = AboutPanel.Updates(copy, offer, false, null, Now);
        Assert.AreEqual((UpdateRowKind.Offered, "Update", true), (offered.Kind, offered.Action, offered.CanCheck));
        Assert.IsNull(AboutPanel.Updates(copy, offer with { Offer = null }, false, null, Now).Action, "no offer, nothing to install");

        var downloading = AboutPanel.Updates(copy, offer, false, null, Now, new UpdateRun(UpdateStep.Downloading, "0.1.12"));
        Assert.AreEqual((UpdateRowKind.Downloading, "Downloading 0.1.12", (string?)null, false, true),
            (downloading.Kind, downloading.Title, downloading.Action, downloading.CanCheck, downloading.Busy));
        var installing = AboutPanel.Updates(copy, offer, true, null, Now, new UpdateRun(UpdateStep.Restarting, "0.1.12"));
        Assert.AreEqual((UpdateRowKind.Restarting, "Installing 0.1.12", "RoleBand opens again on 0.1.12 when Windows is done.", (string?)null, false),
            (installing.Kind, installing.Title, installing.Caption, installing.Action, installing.CanCheck), "a switch under way outranks a check");
        var counting = AboutPanel.Updates(copy, offer, false, null, Now, new UpdateRun(UpdateStep.Restarting, "0.1.12", Percent: 45));
        Assert.AreEqual(("Installing 0.1.12", "45% · RoleBand opens again on 0.1.12 when Windows is done."), (counting.Title, counting.Caption),
            "Windows' own percentage while this version stays open");
        Assert.AreEqual("Restarting to update",
            AboutPanel.Updates(copy, offer, false, null, Now, new UpdateRun(UpdateStep.Restarting, "0.1.12", Percent: 100)).Title,
            "at the end Windows closes this version and opens the new one");
    }

    [TestMethod]
    public void AFailedUpdateSaysWhichStepFailedAndOffersToTryAgain()
    {
        var copy = new NativeCopy("en");
        var offer = new UpdateFacts(true, false, Now.AddMinutes(-1), "0.1.12", null);
        var download = AboutPanel.Updates(copy, offer, false, null, Now, new UpdateRun(UpdateStep.DownloadFailed, "0.1.12"));
        Assert.AreEqual((UpdateRowKind.UpdateFailed, "Couldn't download 0.1.12", "The server didn't answer.", "Try again", true),
            (download.Kind, download.Title, download.Caption, download.Action, download.CanCheck));
        var check = AboutPanel.Updates(copy, offer, false, null, Now, new UpdateRun(UpdateStep.CheckFailed, "0.1.12"));
        Assert.AreEqual(("0.1.12 failed its check", "Nothing was installed."), (check.Title, check.Caption));
        var install = AboutPanel.Updates(copy, offer, false, null, Now, new UpdateRun(UpdateStep.RestartFailed, "0.1.12"));
        Assert.AreEqual(("Couldn't install 0.1.12", "Nothing was installed.", "Try again"), (install.Title, install.Caption, install.Action),
            "Windows refused the package: it was never a restart that failed");
        var why = AboutPanel.Updates(copy, offer, false, null, Now,
            new UpdateRun(UpdateStep.RestartFailed, "0.1.12", Reason: "The package could not be installed because there is not enough space."));
        Assert.AreEqual("Nothing was installed. The package could not be installed because there is not enough space.", why.Caption,
            "Windows' own reason follows");
        var newer = AboutPanel.Updates(copy, offer with { Offer = "0.1.13" }, false, null, Now, new UpdateRun(UpdateStep.DownloadFailed, "0.1.12"));
        Assert.AreEqual((UpdateRowKind.Offered, "Version 0.1.13 is ready"), (newer.Kind, newer.Title), "a newer offer replaces the failure");
    }

    [TestMethod]
    public void TheNextOpenSaysHowTheUpdateEndedUntilANewerOfferArrives()
    {
        var copy = new NativeCopy("en");
        var current = new UpdateFacts(true, false, Now.AddMinutes(-1), null, null);
        var updated = AboutPanel.Updates(copy, current, false, null, Now, new UpdateRun(UpdateStep.Updated, "0.1.12"));
        Assert.AreEqual((UpdateRowKind.Updated, "Updated to 0.1.12", (string?)null), (updated.Kind, updated.Title, updated.Action));
        StringAssert.StartsWith(updated.Caption, "Checked ");
        var back = AboutPanel.Updates(copy, current, false, null, Now, new UpdateRun(UpdateStep.RolledBack, "0.1.11"));
        Assert.AreEqual("Back on 0.1.11", back.Title);
        Assert.AreEqual(UpdateRowKind.Offered,
            AboutPanel.Updates(copy, current with { Offer = "0.1.13" }, false, null, Now, new UpdateRun(UpdateStep.Updated, "0.1.12")).Kind);
        Assert.AreEqual(UpdateRowKind.Failed, AboutPanel.Updates(copy, current, false, "failed", Now, new UpdateRun(UpdateStep.Updated, "0.1.12")).Kind,
            "a failed check after the update is said");
    }

    [TestMethod]
    public void HowTheLastUpdateEndedComesFromItsJournalAndHoldsAcrossRestarts()
    {
        var copy = new NativeCopy("en");
        var undone = Facts("""{"status":"ok","automatic":true,"checked_at":null,"offer":null,"rate_limited_until":null,"update":{"phase":"recovered","from":"0.1.13","to":"0.1.14","running":"from"}}""");
        Assert.AreEqual(new LastUpdate("recovered", "0.1.13", "0.1.14", "from"), undone.Last);
        var back = AboutPanel.Updates(copy, undone, false, null, Now);
        Assert.AreEqual((UpdateRowKind.Updated, "Back on 0.1.13", "0.1.14 didn't start. Nothing was lost."), (back.Kind, back.Title, back.Caption),
            "no check since the undo, and still it says how it ended");
        var updated = Facts("""{"status":"ok","automatic":false,"checked_at":null,"offer":null,"update":{"phase":"complete","from":"0.1.12","to":"0.1.13","running":"to"}}""");
        Assert.AreEqual("Updated to 0.1.13", AboutPanel.Updates(copy, updated, false, null, Now).Title);
        Assert.AreEqual("Version 0.1.15 is ready", AboutPanel.Updates(copy, undone with { Offer = "0.1.15" }, false, null, Now).Title,
            "a newer offer replaces the result");
        foreach (var (phase, running) in new[] { ("recovered", "to"), ("complete", "from"), ("failed", "to"), ("recovering", "to"), ("complete", (string?)null) })
            Assert.IsNull(new LastUpdate(phase, "0.1.13", "0.1.14", running).Result, $"{phase} as {running} is no result");
        Assert.IsNull(Facts("""{"status":"ok","update":{"phase":"complete"}}""").Last, "a half answer is no update");
    }

    private static LastUpdate Last(string phase, string? running = "to") => new(phase, "0.1.17", "0.1.18", running);

    [TestMethod]
    public void TheVersionWindowsJustInstalledSaysItIsFinishingTheUpdate()
    {
        var copy = new NativeCopy("en");
        foreach (var phase in new[] { "applying", "preparing" })
        {
            var facts = new UpdateFacts(true, false, Now, null, null, Last(phase));
            var row = AboutPanel.Updates(copy, facts, false, null, Now);
            Assert.AreEqual((UpdateRowKind.Finishing, "Finishing the update to 0.1.18", false, true), (row.Kind, row.Title, row.CanCheck, row.Busy), phase);
            Assert.AreEqual(new FlyoutUpdate("Finishing the update to 0.1.18", null, null, "0.1.18", true, false, true),
                AboutPanel.Flyout(copy, facts, null), "the flyout's whole state, not an engine that is merely starting");
        }
        Assert.AreNotEqual(UpdateRowKind.Finishing,
            AboutPanel.Updates(copy, new UpdateFacts(true, false, Now, null, null, Last("preparing", "from")), false, null, Now).Kind,
            "the previous version starting again is not finishing anything");
    }

    [TestMethod]
    public void AFailedUpdateIsNeverUpToDate()
    {
        var copy = new NativeCopy("en");
        foreach (var phase in new[] { "failed", "recovering" })
        {
            var row = AboutPanel.Updates(copy, new UpdateFacts(true, true, Now, null, null, Last(phase)), false, "up-to-date", Now);
            Assert.AreEqual((UpdateRowKind.Unfinished, "0.1.18 couldn't finish", "Undo it above, or check for a newer version.", true),
                (row.Kind, row.Title, row.Caption, row.CanCheck), phase);
        }
        var newer = AboutPanel.Updates(copy, new UpdateFacts(true, true, Now, "0.1.19", null, Last("failed")), false, null, Now);
        Assert.AreEqual((UpdateRowKind.Offered, "Update"), (newer.Kind, newer.Action), "a newer release can replace it");
    }

    [TestMethod]
    public void AnUndoUnderWayIsTheFlyoutsWholeState()
    {
        var copy = new NativeCopy("en");
        Assert.AreEqual(new FlyoutUpdate("Returning to 0.1.13", null, null, "0.1.13", true, false, true),
            AboutPanel.Flyout(copy, new UpdateFacts(true, false, Now, "0.1.15", null), null, "0.1.13"), "an offer waits until the undo ends");
    }

    [TestMethod]
    public void TheFlyoutBannerCarriesTheOfferAndItsStepsButNotTheResult()
    {
        var copy = new NativeCopy("en");
        var offer = new UpdateFacts(true, false, Now, "0.1.12", null);
        Assert.AreEqual(new FlyoutUpdate("Version 0.1.12 is ready", null, "Update", "0.1.12", false, false, false),
            AboutPanel.Flyout(copy, offer, null));
        Assert.AreEqual(new FlyoutUpdate("Downloading 0.1.12", null, null, "0.1.12", true, false, false, Cancel: true),
            AboutPanel.Flyout(copy, offer, new UpdateRun(UpdateStep.Downloading, "0.1.12")), "no Update while it downloads, only Cancel");
        Assert.AreEqual(new FlyoutUpdate("Installing 0.1.12", null, null, "0.1.12", true, false, true, 45),
            AboutPanel.Flyout(copy, offer, new UpdateRun(UpdateStep.Restarting, "0.1.12", Percent: 45)));
        Assert.AreEqual(new FlyoutUpdate("Returning to 0.1.11", null, null, "0.1.11", true, false, true, 30),
            AboutPanel.Flyout(copy, offer, null, "0.1.11", 30), "putting the previous version back shows Windows' percentage too");
        Assert.AreEqual(new FlyoutUpdate("Couldn't download 0.1.12", "The server didn't answer.", "Try again", "0.1.12", false, true, false),
            AboutPanel.Flyout(copy, offer, new UpdateRun(UpdateStep.DownloadFailed, "0.1.12")));
        Assert.IsNull(AboutPanel.Flyout(copy, offer with { Offer = null }, new UpdateRun(UpdateStep.Updated, "0.1.12")));
        Assert.IsNull(AboutPanel.Flyout(copy, offer with { Offer = null }, null));
        Assert.IsNull(AboutPanel.Flyout(copy, UpdateFacts.Unavailable, null), "a build that does not update itself says nothing");
        Assert.IsNull(AboutPanel.Flyout(copy, null, null));
    }

    [TestMethod]
    public void TheChoiceIsRecordedInItsPinnedEnglishWordsWhateverTheLanguage()
    {
        Assert.AreEqual("Check for updates automatically", AboutPanel.ConsentText());
        Assert.AreEqual("en", AboutPanel.ConsentLanguage);
        foreach (var language in Languages) Assert.AreEqual(AboutPanel.ConsentText(), new NativeCopy(language)[AboutPanel.ConsentKey]);
        Assert.AreEqual(AboutPanel.ConsentText(), AboutPanel.AutomaticLabel, "the switch shows the words its choice records");
    }

    [TestMethod]
    public void SettingsShowsOpenAtLoginAsWindowsHasIt()
    {
        Assert.AreEqual(new LoginRow(true, true, "first-login-caption", false, true), AboutPanel.Login(LoginState.On, false));
        Assert.AreEqual(new LoginRow(false, false, "first-login-caption", false, true), AboutPanel.Login(LoginState.Off, true));
        Assert.AreEqual(new LoginRow(false, true, "windows-login-approval", true, true), AboutPanel.Login(LoginState.Approval, false));
        Assert.AreEqual(new LoginRow(true, false, "windows-login-managed", false, true), AboutPanel.Login(LoginState.ManagedOn, false));
        Assert.IsFalse(AboutPanel.Login(LoginState.ManagedOff, false).Enabled);
        Assert.IsFalse(AboutPanel.Login(LoginState.Unavailable, false).Visible, "a copy without a package has no startup task");
    }

    [TestMethod]
    public void EveryRowHasWindowsWordsInEveryLanguage()
    {
        UpdateFacts?[] facts = [null, new(false, false, null, null, null), new(true, true, Now, null, null), new(true, false, Now, "0.1.3", null),
            new(true, false, null, null, Now.AddMinutes(1))];
        string[] macWords = ["Mac", "macOS", "menu bar", "System Settings", "Finder"];
        foreach (var language in Languages)
        {
            var copy = new NativeCopy(language);
            var texts = new List<string>();
            UpdateRun?[] runs = [null, .. Enum.GetValues<UpdateStep>().Select(step => new UpdateRun(step, "0.1.3"))];
            foreach (var fact in facts)
            foreach (var result in new[] { null, "failed", "rate-limited" })
            foreach (var checking in new[] { false, true })
            foreach (var run in runs)
            {
                var row = AboutPanel.Updates(copy, fact, checking, result, Now, run);
                texts.Add(row.Title);
                if (row.Caption is { } caption) texts.Add(caption);
                if (row.Action is { } action) texts.Add(action);
            }
            foreach (var state in Enum.GetValues<LoginState>()) texts.Add(copy[AboutPanel.Login(state, false).CaptionKey]);
            foreach (var key in new[] { "panel-scan", "panel-settings", "panel-about", "windows-on-pc", "panel-in-browser", "first-login-toggle",
                "windows-login-settings", "panel-scan-times", "panel-all-settings", "panel-opens-browser", "panel-updates", "update-check-now",
                "panel-check-automatically", "panel-check-automatically-caption", "panel-licences", "login-error" })
                texts.Add(copy[key]);
            texts.Add(copy.Format("panel-version", ("version", "0.1.2")));
            foreach (var text in texts)
            {
                Assert.IsFalse(string.IsNullOrWhiteSpace(text), language);
                Assert.IsFalse(text.Contains('{'), $"{language}: {text}");
                Assert.IsFalse(macWords.Any(word => text.Contains(word, StringComparison.Ordinal)), $"{language}: {text}");
            }
        }
    }

    private sealed class Commands(Func<IReadOnlyList<string>, string> answer) : IUpdateCommands
    {
        public List<string[]> Runs { get; } = [];
        public string[] Lines { get; init; } = [];
        public Task<JsonElement> RunAsync(IReadOnlyList<string> arguments, CancellationToken cancellation, Action<string>? lines = null)
        {
            Runs.Add([.. arguments]);
            foreach (var line in Lines) lines?.Invoke(line);
            using var document = JsonDocument.Parse(answer(arguments));
            return Task.FromResult(document.RootElement.Clone());
        }
    }

    private sealed class NoDeployer : IPackageDeployer
    {
        public Task AddAsync(string package, bool downgrade, IProgress<int>? progress, CancellationToken cancellation) =>
            throw new AssertFailedException("Settings and About never install a package.");
    }

    [TestMethod]
    public async Task TheCoordinatorAsksOnlyWhatItIsAskedAndRefusesAnUnrecordedChoice()
    {
        var commands = new Commands(arguments => arguments[0] switch
        {
            "status" => """{"status":"ok","automatic":false,"checked_at":null,"offer":null,"rate_limited_until":null}""",
            "consent" => """{"recorded":true}""",
            _ => """{"status":"up-to-date","until":null,"checked_at":1800000000,"automatic":false,"offer":null}""",
        });
        var coordinator = new UpdateCoordinator(commands, new NoDeployer());
        Assert.IsTrue((await coordinator.StatusAsync()).Available);
        var (facts, status) = await coordinator.CheckNowAsync(manual: true);
        Assert.AreEqual(("up-to-date", DateTimeOffset.FromUnixTimeSeconds(1_800_000_000)), (status, facts.CheckedAt));
        await coordinator.ConsentAsync(true, "Check for updates automatically", "en");
        CollectionAssert.AreEqual(new[] { "status" }, commands.Runs[0]);
        CollectionAssert.AreEqual(new[] { "check", "--manual" }, commands.Runs[1]);
        CollectionAssert.AreEqual(new[] { "consent", "--automatic", "on", "--text", "Check for updates automatically", "--language", "en" },
            commands.Runs[2]);

        var refused = new UpdateCoordinator(new Commands(_ => """{"status":"refused","reason":"no"}"""), new NoDeployer());
        await Assert.ThrowsExactlyAsync<IOException>(() => refused.ConsentAsync(false, "Check for updates automatically", "en"));
    }

    [TestMethod]
    public async Task TheEnginesOwnCommandsRecordTheChoiceAndReportABuildWithoutUpdates()
    {
        var checkout = new DirectoryInfo(AppContext.BaseDirectory);
        while (!File.Exists(Path.Combine(checkout.FullName, "backend", "desktop.py")))
            checkout = checkout.Parent ?? throw new IOException("Source checkout not found.");
        var state = Path.Combine(Path.GetTempPath(), "roleband-about-tests", Guid.NewGuid().ToString("N"));
        PrivateStorage.EnsureDirectory(state);
        var coordinator = UpdateCoordinator.For(EngineConfiguration.Source(checkout.FullName, state, fixture: true));
        await coordinator.ConsentAsync(true, AboutPanel.ConsentText(), AboutPanel.ConsentLanguage);
        using (var record = JsonDocument.Parse(File.ReadAllText(Path.Combine(state, "launcher", "update-consent.json"))))
        {
            Assert.IsTrue(record.RootElement.GetProperty("automatic").GetBoolean());
            Assert.AreEqual("Check for updates automatically", record.RootElement.GetProperty("text").GetString());
            Assert.AreEqual("en", record.RootElement.GetProperty("language").GetString());
        }
        // A source checkout carries no release identity, so updates are unavailable and nothing is asked of the feed.
        Assert.IsFalse((await coordinator.StatusAsync()).Available);
        var (facts, status) = await coordinator.CheckNowAsync(manual: true);
        Assert.AreEqual(("unavailable", false), (status, facts.Available));
        Assert.IsFalse(File.Exists(Path.Combine(state, "launcher", "update-check.json")));
    }
}

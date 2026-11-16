using System.Runtime.InteropServices;
using Microsoft.VisualStudio.TestTools.UnitTesting;
using static RoleBand.EngineHost.UpdateWindowChoice;
using static RoleBand.EngineHost.UpdateWindowDecision;

namespace RoleBand.EngineHost.Tests;

/// <summary>The window that opens by itself for a release an automatic check finds: when it opens, Later, what it shows
/// from the offer to Windows' install, and that it never takes the keyboard.</summary>
[TestClass]
public sealed class UpdateWindowTests
{
    private static readonly DateTimeOffset Now = new(2026, 11, 16, 9, 0, 0, TimeSpan.Zero);
    private static readonly NativeCopy Copy = new("en");
    private const string Page = "https://github.com/roleband/roleband/releases/tag/v0.2.3";
    private static readonly UpdateFacts Offer = new(true, true, Now, "0.2.3", null, Page: Page);
    private const long Megabyte = 1024 * 1024;

    private static AppState State(UpdateState? update = null, SetupRecord? setup = null, DateTimeOffset? now = null) =>
        new(null, null, setup ?? SetupRecord.Finished, update ?? new UpdateState(Offer), now ?? Now);

    private static UpdateState Running(UpdateRun run, UpdateFacts? facts = null) => new(facts ?? Offer, run);

    private static UpdateWindowDecision Decide(AppState state, UpdateWindowRecord? record = null, bool setupOpen = false) =>
        UpdateWindowRules.Decide(state, record ?? new UpdateWindowRecord(), "0.2.3", setupOpen);

    private static UpdateWindowView View(AppState state) =>
        UpdateWindowRules.View(Copy, state) ?? throw new AssertFailedException("The window has nothing to show.");

    [TestMethod]
    public void OnlyAnAutomaticCheckThatFoundAReleaseOpensTheWindow()
    {
        Assert.AreEqual("0.2.3", UpdateWindowRules.Found(false, "offered", Offer));
        Assert.IsNull(UpdateWindowRules.Found(true, "offered", Offer), "Check for updates answers in Settings");
        Assert.IsNull(UpdateWindowRules.Found(false, "throttled", Offer), "a check the day already had found nothing new");
        Assert.IsNull(UpdateWindowRules.Found(false, "up-to-date", Offer with { Offer = null }));
    }

    [TestMethod]
    public void AFoundReleaseOpensUnlessSetupOrAnUpdateHoldsItOrItsSwitchIsOff()
    {
        Assert.AreEqual(Open, Decide(State()));
        Assert.AreEqual(Hold, Decide(State(setup: SetupRecord.Fresh)), "setup is unfinished");
        Assert.AreEqual(Hold, Decide(State(), setupOpen: true), "setup is open");
        Assert.AreEqual(Hold, Decide(State(Running(new UpdateRun(UpdateStep.Downloading, "0.2.3")))), "an update is on its way");
        Assert.AreEqual(Hold, Decide(State(new UpdateState(Offer, ReturningTo: "0.2.2", Returning: true))), "an Undo is on its way");
        Assert.AreEqual(Open, Decide(State(Running(new UpdateRun(UpdateStep.DownloadFailed, "0.2.3")))),
            "a failed update leaves its offer standing");
        Assert.AreEqual(Drop, Decide(State(), new UpdateWindowRecord(Shows: false)), "its switch is off");
        Assert.AreEqual(Drop, Decide(State(new UpdateState(Offer with { Offer = "0.2.4" }))), "a newer offer took its place");
        Assert.AreEqual(Drop, Decide(State(new UpdateState(UpdateFacts.Unavailable))), "this build does not update itself");
    }

    [TestMethod]
    public void LaterKeepsAVersionAwayForThreeDaysAndTheThirdLeavesItToTheBadge()
    {
        var once = new UpdateWindowRecord().Later("0.2.3", Now);
        Assert.AreEqual(Drop, Decide(State(now: Now.AddDays(3).AddMinutes(-1)), once));
        Assert.AreEqual(Open, Decide(State(now: Now.AddDays(3)), once));
        var thrice = once.Later("0.2.3", Now.AddDays(3)).Later("0.2.3", Now.AddDays(6));
        Assert.AreEqual(3, thrice.LaterCount);
        Assert.AreEqual(Drop, Decide(State(now: Now.AddDays(60)), thrice), "after the third Later only the icon's badge carries it");
        Assert.IsTrue(thrice.Allows("0.2.4", Now.AddDays(6)), "a newer version starts again");
        Assert.AreEqual(1, thrice.Later("0.2.4", Now.AddDays(7)).LaterCount);
    }

    [TestMethod]
    public void TheRecordKeepsTheSwitchAndTheLatersAcrossOpens()
    {
        var state = Path.Combine(Path.GetTempPath(), "roleband-update-window", Guid.NewGuid().ToString("N"));
        try
        {
            Assert.AreEqual(new UpdateWindowRecord(), UpdateWindowStore.Read(state), "a new install opens the window");
            var record = new UpdateWindowRecord(Shows: false).Later("0.2.3", Now);
            UpdateWindowStore.Write(state, record);
            Assert.AreEqual(record, UpdateWindowStore.Read(state));
            PrivateStorage.Write(UpdateWindowStore.PathFor(state), "{"u8.ToArray());
            Assert.AreEqual(new UpdateWindowRecord(), UpdateWindowStore.Read(state), "a record that cannot be read opens the window");
            PrivateStorage.Write(UpdateWindowStore.PathFor(state),
                """{"format":1,"shows":false,"later_version":"0.2.3","later_count":1,"later_until":9223372036854775807}"""u8.ToArray());
            Assert.AreEqual(new UpdateWindowRecord(), UpdateWindowStore.Read(state), "nor can one whose time is out of range");
        }
        finally
        {
            if (Directory.Exists(state)) Directory.Delete(state, recursive: true);
        }
    }

    [TestMethod]
    public void TheWindowOffersTheReleaseThenCarriesItsUpdateToWindowsInstall()
    {
        var offer = View(State());
        Assert.AreEqual("Version 0.2.3 is ready", offer.Heading);
        Assert.AreEqual(Copy["update-window-body"], offer.Body);
        Assert.AreEqual(Page, offer.Page, "What's new opens the release's page");
        Assert.IsNull(offer.Step);
        CollectionAssert.AreEqual(new[] { Later, Update }, offer.Choices.ToArray());

        var downloading = View(State(Running(new UpdateRun(UpdateStep.Downloading, "0.2.3", Received: 50 * Megabyte, Total: 200 * Megabyte))));
        Assert.AreEqual(Copy.Format("update-downloading", ("version", "0.2.3")), downloading.Step);
        Assert.AreEqual(25, downloading.Percent);
        CollectionAssert.AreEqual(new[] { Cancel }, downloading.Choices.ToArray());

        var paused = View(State(Running(new UpdateRun(UpdateStep.Paused, "0.2.3", Received: 50 * Megabyte, Total: 200 * Megabyte))));
        Assert.AreEqual(Copy["update-paused"], paused.Step);
        CollectionAssert.AreEqual(new[] { Cancel }, paused.Choices.ToArray());

        var installing = View(State(Running(new UpdateRun(UpdateStep.Installing, "0.2.3"))));
        Assert.IsTrue(installing.Working, "Windows has not said how far it is");
        CollectionAssert.AreEqual(Array.Empty<UpdateWindowChoice>(), installing.Choices.ToArray(), "nothing is left to choose");
        Assert.AreEqual(Copy["update-restarting"], View(State(Running(new UpdateRun(UpdateStep.Installing, "0.2.3", Percent: 100)))).Step);

        var failed = View(State(Running(new UpdateRun(UpdateStep.DownloadFailed, "0.2.3"))));
        Assert.IsTrue(failed.Failed);
        Assert.AreEqual(Copy.Format("update-download-failed", ("version", "0.2.3")), failed.Step);
        CollectionAssert.AreEqual(new[] { Later, Retry }, failed.Choices.ToArray());
        CollectionAssert.AreEqual(new[] { Later }, View(State(Running(new UpdateRun(UpdateStep.Unpublished, "0.2.3")))).Choices.ToArray(),
            "trying again cannot bring back a release the feed no longer has");
    }

    [TestMethod]
    public void ANewerOfferReplacesAFailureButNotAnUpdateUnderWay()
    {
        var newer = Offer with { Offer = "0.2.4", Page = "https://github.com/roleband/roleband/releases/tag/v0.2.4" };
        var replaced = View(State(Running(new UpdateRun(UpdateStep.DownloadFailed, "0.2.3"), newer)));
        Assert.AreEqual("Version 0.2.4 is ready", replaced.Heading);
        Assert.AreEqual(newer.Page, replaced.Page);
        CollectionAssert.AreEqual(new[] { Later, Update }, replaced.Choices.ToArray());

        var installing = View(State(Running(new UpdateRun(UpdateStep.Installing, "0.2.3"), newer)));
        Assert.AreEqual("Version 0.2.3 is ready", installing.Heading, "the window names the version Windows installs");
        Assert.IsNull(installing.Page, "only the offer's page is known");
    }

    [TestMethod]
    public void AnOpenWindowGoesOnceItHasNothingToShowOrItsSwitchIsOff()
    {
        var record = new UpdateWindowRecord();
        var off = record with { Shows = false };
        Assert.IsFalse(UpdateWindowRules.Stale(Copy, State(), record));
        Assert.IsTrue(UpdateWindowRules.Stale(Copy, State(new UpdateState(Offer with { Offer = null })), record), "installed or withdrawn");
        Assert.IsTrue(UpdateWindowRules.Stale(Copy, State(), off));
        Assert.IsTrue(UpdateWindowRules.Stale(Copy, State(new UpdateState(Offer, ReturningTo: "0.2.2", Returning: true)), record), "an Undo");
        Assert.IsTrue(UpdateWindowRules.Stale(Copy, State(new UpdateState(Offer, new UpdateRun(UpdateStep.DownloadFailed, "0.2.3"),
            ReturningTo: "0.2.2", Returning: true)), record), "an Undo from the failure it shows");
        Assert.IsFalse(UpdateWindowRules.Stale(Copy, State(Running(new UpdateRun(UpdateStep.Downloading, "0.2.3"))), off),
            "its own update keeps it");
        Assert.IsFalse(UpdateWindowRules.Stale(Copy, State(Running(new UpdateRun(UpdateStep.CheckFailed, "0.2.3"))), off),
            "a failure stays in view");
        var newer = Offer with { Offer = "0.2.4" };
        Assert.IsTrue(UpdateWindowRules.Stale(Copy, State(Running(new UpdateRun(UpdateStep.CheckFailed, "0.2.3"), newer)), off),
            "a newer offer in place of its failed update is not its own");
    }

    [TestMethod]
    public void TheWindowShowsOnTopWithoutTakingTheKeyboardAndAClickDoesNotActivateIt()
    {
        const int ExtendedStyle = -20;
        const long TopMost = 0x8, NoActivate = 0x08000000;
        const uint MouseActivate = 0x0021, LeftButtonDown = 0x0201, Client = 1;
        using var window = new WindowThread();
        var foreground = GetForegroundWindow();
        window.Run(() =>
        {
            var quiet = new QuietWindow(window.Window);
            window.OnDispose(quiet.Dispose);
            quiet.Show();
        });
        Assert.IsTrue(IsWindowVisible(window.Window));
        var style = (long)GetWindowLongPtr(window.Window, ExtendedStyle);
        if ((style & TopMost) == 0) Assert.Fail($"it shows above other windows; {Desktop(foreground)}");
        Assert.AreNotEqual(0L, style & NoActivate, "Windows never makes it the active window");
        Assert.AreNotEqual(window.Window, window.Run(() => GetActiveWindow()), "showing it did not activate it");
        Assert.AreEqual(foreground, GetForegroundWindow(), "the keyboard stays where it was");
        Assert.AreEqual((nint)3, window.Send(MouseActivate, window.Window, (nint)((LeftButtonDown << 16) | Client)),
            "a click on it does not activate it");
    }

    /// <summary>What the desktop allows a plain window, for a failure's message: the foreground window, and whether a window
    /// with no quiet style becomes topmost with and without activation.</summary>
    private static string Desktop(nint foreground)
    {
        const uint NoSize = 0x0001, NoMove = 0x0002, NoActivate = 0x0010, ShowWindowFlag = 0x0040;
        string Plain(uint flags)
        {
            using var plain = new WindowThread();
            var (moved, error) = plain.Run(() => (SetWindowPos(plain.Window, -1, 0, 0, 0, 0, flags), Marshal.GetLastPInvokeError()));
            return $"moved={moved} error={error} topmost={((long)GetWindowLongPtr(plain.Window, -20) & 0x8) != 0}";
        }
        var desktop = OpenInputDesktop(0, false, 0x0001);
        if (desktop != 0) CloseDesktop(desktop);
        return $"foreground=0x{foreground:X} input desktop={desktop != 0}; " +
               $"plain without activation: {Plain(NoSize | NoMove | NoActivate | ShowWindowFlag)}; " +
               $"plain with activation: {Plain(NoSize | NoMove | ShowWindowFlag)}";
    }

    [DllImport("user32.dll", SetLastError = true)]
    private static extern bool SetWindowPos(nint window, nint after, int x, int y, int width, int height, uint flags);
    [DllImport("user32.dll", SetLastError = true)]
    private static extern nint OpenInputDesktop(uint flags, bool inherit, uint access);
    [DllImport("user32.dll")]
    private static extern bool CloseDesktop(nint desktop);
    [DllImport("user32.dll")]
    private static extern nint GetForegroundWindow();
    [DllImport("user32.dll")]
    private static extern nint GetActiveWindow();
    [DllImport("user32.dll")]
    private static extern bool IsWindowVisible(nint window);
    [DllImport("user32.dll", EntryPoint = "GetWindowLongPtrW")]
    private static extern nint GetWindowLongPtr(nint window, int index);
}

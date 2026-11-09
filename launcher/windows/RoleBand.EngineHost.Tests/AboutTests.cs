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
        var restarting = AboutPanel.Updates(copy, offer, true, null, Now, new UpdateRun(UpdateStep.Restarting, "0.1.12"));
        Assert.AreEqual((UpdateRowKind.Restarting, "Restarting to update", (string?)null, false),
            (restarting.Kind, restarting.Title, restarting.Action, restarting.CanCheck), "a switch under way outranks a check");
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
        var restart = AboutPanel.Updates(copy, offer, false, null, Now, new UpdateRun(UpdateStep.RestartFailed, "0.1.12"));
        Assert.AreEqual(("Couldn't restart", "Nothing was installed.", "Try again"), (restart.Title, restart.Caption, restart.Action));
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
    public void TheFlyoutCarriesTheOfferAndItsStepsButNotTheResult()
    {
        var copy = new NativeCopy("en");
        var offer = new UpdateFacts(true, false, Now, "0.1.12", null);
        Assert.AreEqual(new FlyoutUpdate(new FlyoutLine("Version 0.1.12 is ready", "Update", Updates: true), false),
            AboutPanel.Flyout(copy, offer, null));
        Assert.AreEqual(new FlyoutUpdate(new FlyoutLine("Downloading 0.1.12"), false),
            AboutPanel.Flyout(copy, offer, new UpdateRun(UpdateStep.Downloading, "0.1.12")));
        Assert.AreEqual(new FlyoutUpdate(new FlyoutLine("Restarting to update"), true),
            AboutPanel.Flyout(copy, offer, new UpdateRun(UpdateStep.Restarting, "0.1.12")));
        Assert.AreEqual(new FlyoutUpdate(new FlyoutLine("Couldn't download 0.1.12", "Try again", Updates: true), false),
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
        public Task<JsonElement> RunAsync(IReadOnlyList<string> arguments, CancellationToken cancellation)
        {
            Runs.Add([.. arguments]);
            using var document = JsonDocument.Parse(answer(arguments));
            return Task.FromResult(document.RootElement.Clone());
        }
    }

    private sealed class NoDeployer : IPackageDeployer
    {
        public Task AddAsync(string package, bool downgrade, CancellationToken cancellation) =>
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

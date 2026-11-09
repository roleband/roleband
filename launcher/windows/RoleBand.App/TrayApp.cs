using Microsoft.UI.Dispatching;
using Microsoft.UI.Xaml;
using RoleBand.EngineHost;
using System.Diagnostics;

namespace RoleBand.App;

/// <summary>
/// The app without a main window. The icon by the clock, its flyout and its menu are the everyday surfaces;
/// the Settings and setup windows open on demand. Closing a window never quits: Quit does, and stops the engine.
/// The engine's state and every rule live in the engine host (<see cref="Companion"/>, <see cref="SetupFlow"/>,
/// <see cref="AboutPanel"/>, <see cref="SettingsPanel"/>); this class only reads, acts and draws.
/// </summary>
internal sealed class TrayApp
{
    private readonly NativeCopy copy;
    private readonly FlyoutWindow flyout;
    private readonly DispatcherQueue dispatcher;
    private TrayIcon? tray;
    private SettingsWindow? settings;
    private SetupWindow? setupWindow;
    private EngineSession? engine;
    private UpdateCoordinator? updates;
    private EngineConfiguration? configuration;
    private string? launchFailure;
    private bool quitting;

    // The scan: read on the app's own schedule, quickly while a scan runs and the flyout is open.
    private ScanStatus? scanStatus;
    private ScanAction? requested;
    private bool controlBusy;
    private string? controlMessage;
    private int failures;
    private CancellationTokenSource? polling;
    private readonly SemaphoreSlim wake = new(0);
    private FlyoutView? view;
    private DateTimeOffset? lastScanAt;
    private bool updateFailed;
    private bool radarWhenReady;

    // First open: the record lives in the account's state; the setup window only draws it.
    private string? statePath;
    private SetupRecord setup = SetupRecord.Finished;
    private readonly ILoginItem loginItem = new StartupLoginItem();
    private LoginState login = LoginState.Unavailable;
    private bool loginBusy, loginError, openFailed;

    // Settings.
    private UpdateFacts? updateFacts;
    private UpdateRun? updateRun;
    // An undo returning to this version: pressed in this session, or found unfinished when the app opened.
    private string? returningTo;
    private bool returning;
    private bool updateChecking, updateChoosing, settingsLoginError;
    private string? lastUpdateResult, settingsError;
    private DateTimeOffset nextAutomaticCheck = DateTimeOffset.MinValue;

    public TrayApp(Exception? failure, bool atLogin)
    {
        copy = new NativeCopy(Native.Option("--language"));
        flyout = new FlyoutWindow(copy);
        dispatcher = flyout.DispatcherQueue;
        flyout.OpenRadar += async () => { flyout.Hide(); await OpenRadarAsync(BrowserRoute.Radar); };
        flyout.Open += async route => { flyout.Hide(); await OpenRadarAsync(route); };
        flyout.Restart += async () => await StartAsync();
        flyout.OpenSettings += () => { flyout.Hide(); OpenSettings(); };
        flyout.Scan += async action => await ScanAsync(action);
        flyout.Pause += async action => await PauseAsync(action);
        flyout.QuitRequested += async () => await QuitAsync();
        flyout.UpdateRequested += async () => await UpdateNowAsync();
        try
        {
            tray = new TrayIcon(flyout.Handle, Menu);
            tray.Selected += Selected;
            tray.DoubleClicked += () => { flyout.Hide(); RunDefault(); };
            tray.Chosen += async command => await ChooseAsync(command);
        }
        catch (Exception error)
        {
            // Without the icon the flyout keeps a frame and stays open, and closing it quits.
            tray = null;
            Debug.WriteLine(error);
        }
        // The summary's clocks move while the flyout is open; nothing is read from the engine here.
        var clock = dispatcher.CreateTimer();
        clock.Interval = TimeSpan.FromSeconds(1);
        clock.Tick += (_, _) => { if (flyout.IsOpen) RenderFlyout(); };
        clock.Start();

        try
        {
            if (failure is not null) throw failure;
            var source = Native.Option("--source-root");
            var state = Native.Option("--state");
            var fixture = Native.Flag("--synthetic-fixture");
            if (source is not null && state is null) throw new IOException("Source trials require an explicit synthetic state directory.");
            configuration = source is null
                ? EngineConfiguration.Packaged(Path.Combine(AppContext.BaseDirectory, "Resources"), state, fixture)
                : EngineConfiguration.Source(source, state!, fixture);
            engine = new EngineSession(configuration);
            updates = UpdateCoordinator.For(configuration);
            engine.Changed += snapshot => dispatcher.TryEnqueue(() => Render(snapshot));
            statePath = configuration.State;
            setup = SetupStore.Read(configuration.State);
            Render(engine.Snapshot);
            // Nothing runs before Continue on Welcome; after that the engine starts at every open.
            if (!SetupFlow.EngineHeld(setup)) _ = StartAsync();
            switch (Companion.AtLaunch(setup, atLogin))
            {
                case LaunchAction.Setup: _ = OpenSetupAsync(); break;
                case LaunchAction.RadarWhenReady: radarWhenReady = true; break;
            }
        }
        catch (Exception error)
        {
            launchFailure = error.Message;
            RenderFlyout();
            OpenSettings();
        }
        if (tray is null) flyout.ShowStandalone();
    }

    /// <summary>A second start of the app, redirected here: Start and the icon's default command do the same.</summary>
    public void Reactivated(bool atLogin)
    {
        if (!atLogin) RunDefault();
    }

    private IReadOnlyList<MenuEntry> Menu()
    {
        if (engine is null) return [new MenuEntry(MenuCommand.Settings, copy["settings"], Default: true), MenuEntry.Separator,
            new MenuEntry(MenuCommand.Quit, copy["windows-quit"])];
        return Companion.Menu(copy, engine.Snapshot, view ?? CurrentView(), setup.Complete);
    }

    private void Selected(int x, int y)
    {
        if (engine is not null && !setup.Complete)
        {
            _ = OpenSetupAsync();
            return;
        }
        if (flyout.IsOpen || flyout.JustHid)
        {
            flyout.Hide();
            return;
        }
        // A request's outcome belongs to the moment it was made; a new look starts clean.
        if (!controlBusy) controlMessage = null;
        RenderFlyout();
        flyout.ShowNear(x, y);
        Wake();
    }

    private void RunDefault()
    {
        if (engine is null) { OpenSettings(); return; }
        switch (Companion.Default(engine.Snapshot, setup.Complete))
        {
            case DefaultCommand.Setup:
                _ = OpenSetupAsync();
                break;
            case DefaultCommand.Settings:
                OpenSettings();
                break;
            default:
                if (TrayModel.For(engine.Snapshot).CanOpenRadar) _ = OpenRadarAsync(BrowserRoute.Radar);
                else radarWhenReady = true;
                break;
        }
    }

    private async Task ChooseAsync(MenuCommand command)
    {
        switch (command)
        {
            case MenuCommand.OpenRadar: await OpenRadarAsync(BrowserRoute.Radar); break;
            case MenuCommand.ScanNow: await ScanAsync(ScanAction.Start); break;
            case MenuCommand.StopScan: await ScanAsync(ScanAction.Stop); break;
            case MenuCommand.Settings: OpenSettings(); break;
            case MenuCommand.Restart: await StartAsync(); break;
            case MenuCommand.FinishSetup: await OpenSetupAsync(); break;
            case MenuCommand.Quit: await QuitAsync(); break;
            case MenuCommand.Update: await UpdateNowAsync(); break;
            default:
                if (Companion.Pause(command) is { } pause) await PauseAsync(pause);
                break;
        }
    }

    private FlyoutView CurrentView()
    {
        if (engine is null)
        {
            var title = copy["invalid"];
            return new FlyoutView(title, null, null, null, false, launchFailure is null ? [] : [new FlyoutLine(launchFailure)],
                FlyoutPrimary.Restart, false, null, null, null, PauseControl.None, true, TrayBadge.Stopped, Companion.Tip(title));
        }
        return Companion.View(copy, engine.Snapshot, scanStatus, requested, lastScanAt, setup.Complete, DateTimeOffset.Now,
            AboutPanel.Flyout(copy, updates is null ? UpdateFacts.Unavailable : updateFacts, updateRun, returningTo));
    }

    private void Render(EngineSnapshot snapshot)
    {
        if (snapshot.State == EngineState.Ready)
        {
            if (polling is null)
            {
                polling = new CancellationTokenSource();
                _ = PollAsync(polling.Token);
            }
        }
        else
        {
            polling?.Cancel();
            polling = null;
            scanStatus = null;
            failures = 0;
        }
        RenderFlyout();
        RenderSetup();
        RenderSettings();
        if (radarWhenReady && setup.Complete && Companion.WhenSettled(snapshot) is { } settled)
        {
            radarWhenReady = false;
            if (settled == DefaultCommand.OpenRadar) _ = OpenRadarAsync(BrowserRoute.Radar);
            else OpenSettings();
        }
        // Automatic checks go through the engine's own rules: none without the choice, at most one a day.
        if (snapshot.State == EngineState.Ready && DateTimeOffset.Now >= nextAutomaticCheck)
        {
            nextAutomaticCheck = DateTimeOffset.Now + AboutPanel.AutomaticInterval;
            _ = CheckUpdatesAsync(manual: false);
        }
    }

    private void RenderFlyout()
    {
        if (scanStatus?.Presentation.LastScanAt is { } last) lastScanAt = last;
        view = CurrentView();
        tray?.Show(view.Badge, view.Tooltip);
        flyout.Render(view, controlMessage is null ? null : copy[controlMessage]);
    }

    // Settings.

    private void OpenSettings()
    {
        flyout.Hide();
        if (settings is null)
        {
            var history = statePath ?? "";
            var licence = configuration is null ? null : Path.Combine(configuration.Resources, "LICENSE");
            var window = new SettingsWindow(copy, AboutPanel.Version(configuration?.Version ?? "", Native.PackageVersion()), history,
                                            licence is not null && File.Exists(licence));
            window.Restart += async () => await StartAsync();
            window.Undo += async () => await UndoUpdateAsync();
            window.OpenLogs += () => OpenFolder(statePath is null ? null : Path.Combine(statePath, "logs"));
            window.OpenHistory += () => OpenFolder(statePath);
            window.OpenLicences += () => { if (licence is not null) Launch(licence); };
            window.OpenStartupApps += () => Launch("ms-settings:startupapps");
            window.CheckUpdates += async () => await CheckUpdatesAsync(manual: true);
            window.UpdateNow += async () => await UpdateNowAsync();
            window.AutomaticChanged += async automatic => await ChooseAutomaticAsync(automatic);
            window.LoginChanged += async enabled => await SetLoginAsync(enabled);
            window.Open += async route => await OpenRadarAsync(route);
            window.Closed += (_, _) => settings = null;
            settings = window;
            _ = RefreshSettingsAsync();
        }
        RenderSettings();
        settings.Activate();
    }

    private async Task RefreshSettingsAsync()
    {
        login = await loginItem.ReadAsync();
        if (updates is not null)
        {
            try { updateFacts = await updates.StatusAsync(); }
            catch (Exception error) { Debug.WriteLine(error); }
        }
        RenderSettings();
    }

    private void RenderSettings()
    {
        if (settings is null) return;
        var snapshot = engine?.Snapshot;
        var facts = updates is null ? UpdateFacts.Unavailable : updateFacts;
        settings.Render(new SettingsState(
            snapshot is null ? SettingsPanel.LaunchFailed
                : SettingsPanel.Problem(snapshot, updateFailed, SetupFlow.EngineHeld(setup), updateRun is { Step: UpdateStep.Restarting },
                    returningTo, returning),
            snapshot?.Diagnostic ?? launchFailure,
            AboutPanel.Updates(copy, facts, updateChecking, lastUpdateResult, DateTimeOffset.Now, updateRun),
            AboutPanel.Login(login, loginBusy),
            settingsLoginError,
            snapshot is not null && TrayModel.For(snapshot).CanOpenRadar,
            updateChoosing,
            settingsError is null ? null : copy[settingsError]));
    }

    private async Task SetLoginAsync(bool enabled)
    {
        loginBusy = true;
        settingsLoginError = false;
        RenderSettings();
        try { login = await loginItem.SetAsync(enabled); }
        catch (Exception error)
        {
            settingsLoginError = true;
            login = await loginItem.ReadAsync();
            Debug.WriteLine(error);
        }
        loginBusy = false;
        RenderSettings();
    }

    private async Task CheckUpdatesAsync(bool manual)
    {
        if (updates is null || updateChecking || updateRun is { InProgress: true }) return;
        // A check asked for by hand starts a new look: the last update's result or failure gives way to what it finds.
        if (manual) updateRun = null;
        if (!manual)
        {
            // Without the choice, an automatic check would only be refused; read the kept state instead.
            try { updateFacts ??= await updates.StatusAsync(); }
            catch (Exception error) { Debug.WriteLine(error); return; }
            if (updateFacts is not { Available: true, Automatic: true }) { RenderSettings(); return; }
        }
        updateChecking = manual;
        RenderSettings();
        try
        {
            var (facts, status) = await updates.CheckNowAsync(manual);
            updateFacts = facts;
            if (status is "up-to-date" or "offered" or "failed" or "rate-limited") lastUpdateResult = status;
        }
        catch (Exception error)
        {
            if (manual) lastUpdateResult = "failed";
            Debug.WriteLine(error);
        }
        updateChecking = false;
        RenderSettings();
    }

    private async Task ChooseAutomaticAsync(bool automatic)
    {
        if (updates is null) return;
        updateChoosing = true;
        RenderSettings();
        try
        {
            await updates.ConsentAsync(automatic, AboutPanel.ConsentText(), AboutPanel.ConsentLanguage);
            updateFacts = await updates.StatusAsync();
        }
        catch (Exception error) { Debug.WriteLine(error); }
        updateChoosing = false;
        RenderSettings();
        if (automatic && updateFacts is { Automatic: true }) await CheckUpdatesAsync(manual: false);
    }

    /// <summary>Update, the only press an update needs: download and verify the offered version, then let Windows replace
    /// this version with it and open it again. A download or a switch that fails leaves this version running.</summary>
    private async Task UpdateNowAsync()
    {
        if (engine is null || updates is null || updateRun is { InProgress: true } || updateFacts?.Offer is not { } version) return;
        updateRun = new UpdateRun(UpdateStep.Downloading, version);
        RenderUpdate();
        string? package;
        try { (updateRun, package) = UpdateRun.Downloaded(await updates.DownloadAsync(), version); }
        catch (Exception error)
        {
            Debug.WriteLine(error);
            (updateRun, package) = (new UpdateRun(UpdateStep.DownloadFailed, version), null);
        }
        RenderUpdate();
        if (package is null) return;
        try
        {
            // Windows closes this version once the new one is in place, and opens it again.
            await updates.ApplyAsync(engine, package);
        }
        catch (Exception error)
        {
            Debug.WriteLine(error);
            updateRun = new UpdateRun(UpdateStep.RestartFailed, version);
            RenderUpdate();
            // The switch stopped the engine first; nothing was installed, so this version carries on.
            await StartAsync();
        }
    }

    private void RenderUpdate()
    {
        RenderFlyout();
        RenderSettings();
    }

    private async Task UndoUpdateAsync()
    {
        if (engine is null || updates is null || returning) return;
        try { updateFacts = await updates.StatusAsync(); }
        catch (Exception error) { Debug.WriteLine(error); }
        // The press is answered at once: Windows takes a while to put the previous package back, then closes this
        // version and opens that one, whose start restores the database.
        returningTo = updateFacts?.Last?.From ?? returningTo;
        returning = returningTo is not null;
        settingsError = null;
        RenderUpdate();
        try { await updates.ReturnToPreviousAsync(engine); }
        catch (Exception error)
        {
            returning = false;
            settingsError = "engine-refused";
            Debug.WriteLine(error);
            RenderUpdate();
        }
    }

    // First open.

    private void SaveSetup(SetupRecord record)
    {
        var held = SetupFlow.EngineHeld(setup);
        setup = record;
        try { if (statePath is not null) SetupStore.Write(statePath, record); }
        catch (Exception error) { Debug.WriteLine(error); }
        if (held && !SetupFlow.EngineHeld(record)) _ = StartAsync();
        RenderSetup();
        RenderFlyout();
    }

    private async Task OpenSetupAsync()
    {
        if (engine is null) return;
        flyout.Hide();
        if (setupWindow is null)
        {
            var window = new SetupWindow(copy);
            window.Primary += async () => await SetupPrimaryAsync();
            window.Secondary += async () => await SetupSecondaryAsync();
            window.Back += () => SaveSetup(setup with { Step = SetupFlow.Previous(setup.Step) });
            window.Later += () => setupWindow?.Close();
            window.LoginChanged += async enabled => await ChooseLoginAsync(enabled);
            window.OpenLoginSettings += () => Launch("ms-settings:startupapps");
            window.OpenTaskbarSettings += () => Launch("ms-settings:taskbar");
            window.Closed += (_, _) =>
            {
                setupWindow = null;
                if (engine is not null) SaveSetup(SetupFlow.Close(setup, engine.Snapshot));
            };
            setupWindow = window;
        }
        SaveSetup(SetupFlow.Resume(setup));
        setupWindow.Activate();
        login = await loginItem.ReadAsync();
        RenderSetup();
    }

    private void RenderSetup()
    {
        if (setupWindow is null || engine is null) return;
        setupWindow.Render(SetupFlow.Page(setup, engine.Snapshot, login, loginBusy),
            SetupFlow.SwitchOn(setup, login), loginError, openFailed);
    }

    private async Task SetupPrimaryAsync()
    {
        if (engine is null) return;
        if (setup.Step == SetupStep.Preparing && engine.Snapshot.State == EngineState.Attention)
        {
            await StartAsync();
            return;
        }
        if (setup.Step is SetupStep.Login or SetupStep.Done)
        {
            await LeaveSetupAsync(openRadar: true);
            return;
        }
        loginBusy = true;
        RenderSetup();
        var (record, state, failed) = await SetupFlow.ContinueAsync(setup, engine.Snapshot, login, loginItem);
        loginBusy = false;
        login = state;
        loginError = failed;
        SaveSetup(record);
    }

    private async Task SetupSecondaryAsync()
    {
        if (setup.Step == SetupStep.Preparing)
        {
            OpenFolder(statePath is null ? null : Path.Combine(statePath, "logs"));
            return;
        }
        await LeaveSetupAsync(openRadar: false);
    }

    /// <summary>Open Radar or Not now on the last page: the start-with-Windows choice registers first, and a refusal
    /// keeps the page. Completion comes before the browser, so a browser that does not open leaves setup complete and
    /// offers another try.</summary>
    private async Task LeaveSetupAsync(bool openRadar)
    {
        if (engine is null) return;
        loginBusy = true;
        openFailed = false;
        RenderSetup();
        var (record, state, failed) = await SetupFlow.ContinueAsync(setup with { Step = SetupStep.Login }, engine.Snapshot, login, loginItem);
        loginBusy = false;
        login = state;
        loginError = failed;
        if (failed) { SaveSetup(setup); return; }
        var (finished, complete) = SetupFlow.Finish(record, engine.Snapshot);
        SaveSetup(finished);
        if (!complete) return;
        if (!openRadar) { setupWindow?.Close(); return; }
        try
        {
            Launch((await engine.BrowserUriAsync(BrowserRoute.Radar)).AbsoluteUri);
            setupWindow?.Close();
        }
        catch (Exception error)
        {
            openFailed = true;
            Debug.WriteLine(error);
            RenderSetup();
        }
    }

    private async Task ChooseLoginAsync(bool enabled)
    {
        loginBusy = true;
        RenderSetup();
        var (record, state, failed) = await SetupFlow.ChooseLoginAsync(setup, enabled, loginItem);
        loginBusy = false;
        login = state;
        loginError = failed;
        SaveSetup(record);
    }

    // The engine and the scan.

    private async Task StartAsync()
    {
        if (engine is null || updates is null) return;
        // Settles an update the previous run began before anything opens the database.
        try
        {
            var phase = await updates.StartAsync(engine);
            if (phase is "failed" or "recovering" or "complete" or "recovered")
            {
                // How the update ended, or the undo under way, comes from its journal, as every later open reads it.
                try { updateFacts = await updates.StatusAsync(); }
                catch (Exception error) { Debug.WriteLine(error); }
            }
            if (phase is "failed" or "recovering")
            {
                updateFailed = true;
                // Opened while Windows puts the previous version back: say so, rather than ask for Undo again.
                if (phase == "recovering") returningTo = updateFacts?.Last?.From;
                OpenSettings();
            }
            RenderUpdate();
        }
        catch (Exception error)
        {
            controlMessage = "engine-refused";
            settingsError = "engine-refused";
            Debug.WriteLine(error);
            // A Radar asked for at launch would wait for an engine that is not coming; Settings says why instead.
            if (radarWhenReady) { radarWhenReady = false; OpenSettings(); }
            RenderFlyout();
            RenderSettings();
        }
    }

    /// <summary>Reads the status quickly while a scan runs and the flyout is open, slowly otherwise; opening the
    /// flyout reads it at once.</summary>
    private async Task PollAsync(CancellationToken stop)
    {
        while (!stop.IsCancellationRequested)
        {
            await RefreshAsync(stop);
            var active = scanStatus?.Presentation.Activity is EngineActivity.Scanning or EngineActivity.Updating
                || scanStatus?.Presentation.Queued is not null;
            try { await wake.WaitAsync(ScanPanel.PollDelay(flyout.IsOpen, active, failures), stop); }
            catch (OperationCanceledException) { return; }
        }
    }

    private async Task RefreshAsync(CancellationToken stop = default)
    {
        if (engine?.Snapshot.State != EngineState.Ready) return;
        try
        {
            using var client = engine.Connect();
            var status = await ScanStatus.ReadAsync(client, stop);
            if (stop.IsCancellationRequested) return;
            scanStatus = status;
            failures = 0;
        }
        catch (Exception error) when (!stop.IsCancellationRequested)
        {
            failures++;
            scanStatus = null;
            Debug.WriteLine(error);
        }
        RenderFlyout();
    }

    private async Task ScanAsync(ScanAction action)
    {
        if (engine is null || controlBusy) return;
        controlBusy = true;
        requested = action;
        controlMessage = null;
        RenderFlyout();
        try
        {
            using var client = engine.Connect();
            controlMessage = await ScanControl.PerformAsync(client, action);
        }
        catch (ControlStateChangedException) { controlMessage = "scan-state-changed"; }
        catch (EngineConflictException) { controlMessage = "scan-refused"; }
        catch (Exception error) { controlMessage = "scan-unconfirmed"; Debug.WriteLine(error); }
        // The request stays on the button until the engine's own state is read back.
        await RefreshAsync();
        controlBusy = false;
        requested = null;
        RenderFlyout();
        Wake();
    }

    private async Task PauseAsync(PauseAction action)
    {
        if (engine is null || controlBusy) return;
        controlBusy = true;
        controlMessage = "scan-sending";
        RenderFlyout();
        try
        {
            using var client = engine.Connect();
            await ScanControl.PauseAsync(client, action, ScanControl.LocalTimezone(), () => DateTimeOffset.UtcNow);
            controlMessage = action == PauseAction.Resume ? "pause-resumed" : "pause-confirmed";
        }
        catch (ControlStateChangedException) { controlMessage = "pause-state-changed"; }
        catch (EngineConflictException) { controlMessage = "pause-refused"; }
        catch (Exception error) { controlMessage = "pause-unconfirmed"; Debug.WriteLine(error); }
        await RefreshAsync();
        controlBusy = false;
        RenderFlyout();
    }

    private void Wake()
    {
        if (wake.CurrentCount == 0) wake.Release();
    }

    private async Task OpenRadarAsync(BrowserRoute route)
    {
        try
        {
            if (engine is not null) Launch((await engine.BrowserUriAsync(route)).AbsoluteUri);
        }
        catch (Exception error)
        {
            controlMessage = "setup-browser-error";
            settingsError = "setup-browser-error";
            Debug.WriteLine(error);
            RenderFlyout();
            RenderSettings();
        }
    }

    private void OpenFolder(string? folder)
    {
        if (folder is null) return;
        // Logs appear with the engine's first run; until then the state folder is the nearest real place.
        Launch(Directory.Exists(folder) ? folder : statePath ?? folder);
    }

    private static void Launch(string target)
    {
        try { Process.Start(new ProcessStartInfo(target) { UseShellExecute = true }); }
        catch (Exception error) { Debug.WriteLine(error); }
    }

    /// <summary>Quit stops the engine; the app stays if the engine did not stop, with the reason in Settings.</summary>
    private async Task QuitAsync()
    {
        if (quitting) return;
        quitting = true;
        try { if (engine is not null) await engine.StopAsync(); }
        catch (Exception error) { Debug.WriteLine(error); }
        if (engine?.OwnsEngine == true)
        {
            quitting = false;
            settingsError = "host-stop-failed";
            OpenSettings();
            return;
        }
        polling?.Cancel();
        setupWindow?.Close();
        settings?.Close();
        tray?.Dispose();
        tray = null;
        flyout.CloseForQuit();
        Application.Current.Exit();
    }
}

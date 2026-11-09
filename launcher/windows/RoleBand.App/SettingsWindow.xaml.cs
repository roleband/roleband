using Microsoft.UI.Windowing;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Automation;
using Microsoft.UI.Xaml.Controls;
using RoleBand.EngineHost;
using Windows.Graphics;

namespace RoleBand.App;

/// <summary>What the Settings window shows at one moment.</summary>
internal sealed record SettingsState(
    SettingsProblem? Problem,
    string? Diagnostic,
    UpdateRow Update,
    LoginRow Login,
    bool LoginError,
    bool CanOpenRadar,
    bool Choosing,
    string? Error);

/// <summary>The Settings window: resizable, opened from the flyout's gear, the menu, or Details. Closing it
/// never quits. It draws <see cref="SettingsState"/> and reports presses.</summary>
public sealed partial class SettingsWindow : Window
{
    private readonly NativeCopy copy;
    private bool rendering;
    // The problem last shown, so only a new one moves focus or is announced; and a press to focus once the window is
    // active, for a problem shown before it was.
    private string? renderedProblem;
    private Control? focusOnActivate;

    public event Action? Restart, Undo, OpenLogs, OpenHistory, CheckUpdates, UpdateNow, CancelUpdate, OpenStartupApps, OpenLicences;
    public event Action<bool>? AutomaticChanged, LoginChanged;
    public event Action<BrowserRoute>? Open;

    internal SettingsWindow(NativeCopy copy, string version, string history, bool licences)
    {
        InitializeComponent();
        this.copy = copy;
        Title = copy["windows-settings-title"];
        Native.Dress(this, AppMark);
        var scale = Native.ScaleOf(WinRT.Interop.WindowNative.GetWindowHandle(this));
        var size = new SizeInt32((int)(720 * scale), (int)(820 * scale));
        var work = DisplayArea.GetFromWindowId(AppWindow.Id, DisplayAreaFallback.Primary).WorkArea;
        size = new SizeInt32(Math.Min(size.Width, work.Width), Math.Min(size.Height, work.Height));
        AppWindow.MoveAndResize(new RectInt32(work.X + (work.Width - size.Width) / 2, work.Y + (work.Height - size.Height) / 2, size.Width, size.Height));

        Activated += (_, args) =>
        {
            if (args.WindowActivationState == WindowActivationState.Deactivated || focusOnActivate is not { } target) return;
            focusOnActivate = null;
            target.Focus(FocusState.Programmatic);
        };

        Heading.Text = copy["settings"];
        RestartButton.Content = copy["engine-restart"];
        UndoButton.Content = copy["update-undo"];
        ProblemLogsButton.Content = copy["windows-open-logs"];
        LastLines.Header = copy["windows-last-lines"];
        CheckButton.Content = copy["windows-check-updates"];
        AutomaticTitle.Text = AboutPanel.AutomaticLabel;
        AutomaticCaption.Text = copy["panel-check-automatically-caption"];
        AutomationProperties.SetName(AutomaticSwitch, AboutPanel.AutomaticLabel);
        OnPcLabel.Text = copy["windows-on-pc"];
        LoginTitle.Text = copy["windows-login-toggle"];
        AutomationProperties.SetName(LoginSwitch, copy["windows-login-toggle"]);
        StartupAppsLink.Content = copy["windows-login-settings"];
        InBrowserLabel.Text = copy["panel-in-browser"];
        ScanTimesTitle.Text = copy["panel-scan-times"];
        ScanTimesCaption.Text = copy["scan-opens-schedule"];
        AutomationProperties.SetName(ScanTimesCard, copy["panel-scan-times"]);
        AutomationProperties.SetHelpText(ScanTimesCard, copy["scan-opens-schedule"]);
        AllSettingsTitle.Text = copy["panel-all-settings"];
        AllSettingsCaption.Text = copy["panel-opens-browser"];
        AutomationProperties.SetName(AllSettingsCard, copy["panel-all-settings"]);
        AutomationProperties.SetHelpText(AllSettingsCard, copy["panel-opens-browser"]);
        AboutLabel.Text = copy["panel-about"];
        HistoryTitle.Text = copy["windows-history"];
        HistoryCaption.Text = copy.Format("windows-history-kept", ("path", history));
        HistoryButton.Content = copy["windows-open-folder"];
        VersionText.Text = copy.Format("panel-version", ("version", version));
        LicencesLink.Content = copy["panel-licences"];
        LicencesLink.Visibility = licences ? Visibility.Visible : Visibility.Collapsed;
        LogsLink.Content = copy["windows-open-logs"];

        RestartButton.Click += (_, _) => Restart?.Invoke();
        UndoButton.Click += (_, _) => Undo?.Invoke();
        NewerButton.Click += (_, _) => UpdateNow?.Invoke();
        ProblemLogsButton.Click += (_, _) => OpenLogs?.Invoke();
        LogsLink.Click += (_, _) => OpenLogs?.Invoke();
        CheckButton.Click += (_, _) => CheckUpdates?.Invoke();
        UpdateButton.Click += (_, _) => UpdateNow?.Invoke();
        CancelUpdateButton.Content = copy["update-cancel"];
        CancelUpdateButton.Click += (_, _) => CancelUpdate?.Invoke();
        AutomaticSwitch.Toggled += (_, _) => { if (!rendering) AutomaticChanged?.Invoke(AutomaticSwitch.IsOn); };
        LoginSwitch.Toggled += (_, _) => { if (!rendering) LoginChanged?.Invoke(LoginSwitch.IsOn); };
        StartupAppsLink.Click += (_, _) => OpenStartupApps?.Invoke();
        ScanTimesCard.Click += (_, _) => Open?.Invoke(BrowserRoute.Schedule);
        AllSettingsCard.Click += (_, _) => Open?.Invoke(BrowserRoute.Settings);
        HistoryButton.Click += (_, _) => OpenHistory?.Invoke();
        LicencesLink.Click += (_, _) => OpenLicences?.Invoke();
    }

    internal void Render(SettingsState state)
    {
        rendering = true;
        try
        {
            var problem = state.Problem;
            string Words(string key) => problem?.Version is { } version ? copy.Format(key, ("version", version)) : copy[key];
            var wasOpen = ProblemBar.IsOpen;
            // An undo under way is news, not a fault; a failed update or a refused Undo waits on Undo; anything else is an error.
            // The bar announces itself as it opens, with the words it has then: they are set first.
            ProblemBar.Severity = problem?.Notice == true ? InfoBarSeverity.Informational
                : problem?.Undo == true ? InfoBarSeverity.Warning : InfoBarSeverity.Error;
            ProblemBar.Title = problem is not null ? Words(problem.TitleKey) : "";
            ProblemBar.Message = problem?.BodyKey is { } body ? Words(body) : "";
            ProblemBar.IsOpen = problem is not null;
            ProblemProgress.Visibility = problem?.Busy == true ? Visibility.Visible : Visibility.Collapsed;
            ProblemProgress.IsIndeterminate = problem?.Percent is null;
            ProblemProgress.Value = problem?.Percent ?? 0;
            RestartButton.Visibility = problem?.Restart == true ? Visibility.Visible : Visibility.Collapsed;
            UndoButton.Visibility = problem?.Undo == true ? Visibility.Visible : Visibility.Collapsed;
            // While an undo is already returning to a version, the same press asks Windows again.
            UndoButton.Content = copy[problem?.Version is not null ? "retry" : "update-undo"];
            NewerButton.Visibility = problem?.Newer is null ? Visibility.Collapsed : Visibility.Visible;
            NewerButton.Content = problem?.Newer is { } newer ? copy.Format("windows-update-to", ("version", newer)) : "";
            ProblemLogsButton.Visibility = problem?.Busy == true ? Visibility.Collapsed : Visibility.Visible;
            var shown = problem is null ? null : $"{problem.TitleKey}|{problem.BodyKey}|{problem.Version}";
            if (shown != renderedProblem)
            {
                renderedProblem = shown;
                // A bar already open that now says something else does not announce itself.
                if (wasOpen && problem is not null) Native.Announce(ProblemBar, $"{ProblemBar.Title}. {ProblemBar.Message}", "SettingsProblem");
                // A failure moves focus to the press that fixes it; a notice of work under way does not take it.
                Control? fix = problem is { Notice: false }
                    ? problem.Undo ? UndoButton : problem.Newer is not null ? NewerButton : problem.Restart ? RestartButton : null
                    : null;
                if (fix is not null)
                    DispatcherQueue.TryEnqueue(Microsoft.UI.Dispatching.DispatcherQueuePriority.Low, () =>
                    {
                        if (!fix.Focus(FocusState.Programmatic)) focusOnActivate = fix;
                    });
            }
            LastLines.Visibility = ProblemBar.IsOpen && !string.IsNullOrWhiteSpace(state.Diagnostic) ? Visibility.Visible : Visibility.Collapsed;
            LastLinesText.Text = state.Diagnostic ?? "";

            var update = state.Update;
            var announce = UpdateTitle.Text != update.Title;
            UpdateTitle.Text = update.Title;
            if (announce) Native.Announce(UpdateTitle);
            UpdateCaption.Text = update.Caption is null ? VersionText.Text : $"{VersionText.Text} · {update.Caption}";
            UpdateBusy.IsActive = update.Busy;
            UpdateBusy.Visibility = update.Busy ? Visibility.Visible : Visibility.Collapsed;
            UpdateButton.Content = update.Action ?? "";
            UpdateButton.Visibility = update.Action is null ? Visibility.Collapsed : Visibility.Visible;
            var help = update.HelpKey is { } helpKey ? copy[helpKey] : null;
            ToolTipService.SetToolTip(UpdateButton, help);
            AutomationProperties.SetHelpText(UpdateButton, help ?? "");
            CancelUpdateButton.Visibility = update.Cancel ? Visibility.Visible : Visibility.Collapsed;
            var available = update.Kind != UpdateRowKind.Unavailable;
            CheckButton.Visibility = available ? Visibility.Visible : Visibility.Collapsed;
            CheckButton.IsEnabled = update.CanCheck;
            AutomaticRow.Visibility = available ? Visibility.Visible : Visibility.Collapsed;
            AutomaticDivider.Visibility = available ? Visibility.Visible : Visibility.Collapsed;
            AutomaticSwitch.IsOn = update.Automatic;
            AutomaticSwitch.IsEnabled = update.AutomaticEnabled && !state.Choosing;

            var login = state.Login;
            OnPcLabel.Visibility = login.Visible ? Visibility.Visible : Visibility.Collapsed;
            LoginCard.Visibility = login.Visible ? Visibility.Visible : Visibility.Collapsed;
            LoginSwitch.IsOn = login.On;
            LoginSwitch.IsEnabled = login.Enabled;
            LoginCaption.Text = copy[state.LoginError ? "login-error" : login.CaptionKey];
            StartupAppsLink.Visibility = login.Settings ? Visibility.Visible : Visibility.Collapsed;

            ScanTimesCard.IsEnabled = state.CanOpenRadar;
            AllSettingsCard.IsEnabled = state.CanOpenRadar;
            var error = state.Error is not null && ErrorText.Text != state.Error;
            ErrorText.Text = state.Error ?? "";
            ErrorText.Visibility = state.Error is null ? Visibility.Collapsed : Visibility.Visible;
            if (error) Native.Announce(ErrorText);
        }
        finally { rendering = false; }
    }
}

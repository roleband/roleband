using Microsoft.UI;
using Microsoft.UI.Windowing;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Automation;
using Microsoft.UI.Xaml.Controls;
using Microsoft.UI.Xaml.Documents;
using Microsoft.UI.Xaml.Input;
using Microsoft.UI.Xaml.Media;
using RoleBand.EngineHost;
using System.Runtime.InteropServices;
using Windows.Graphics;
using Windows.System;

namespace RoleBand.App;

/// <summary>The flyout by the icon. Windows has no control for a tray flyout, so this is a borderless window that
/// closes when it loses focus or on Esc. It draws <see cref="FlyoutView"/> and reports presses. Without an icon it
/// keeps a frame and stays open, and closing it quits.</summary>
public sealed partial class FlyoutWindow : Window
{
    private const int FlyoutWidth = 360, Margin = 12;
    private readonly NativeCopy copy;
    private bool standalone;
    private readonly OverlappedPresenter presenter = OverlappedPresenter.Create();
    private FlyoutView? current;
    private string renderedLines = "";
    private PauseControl renderedPause = PauseControl.None;
    private (int X, int Y)? anchor;
    private long hiddenAt;
    private bool closing;
    private bool focused;

    public event Action? OpenRadar, Restart, OpenSettings, QuitRequested, UpdateRequested, CancelUpdateRequested, Undo, CheckUpdates;
    public event Action<ScanAction>? Scan;
    public event Action<PauseAction>? Pause;
    public event Action<BrowserRoute>? Open;

    public nint Handle { get; }

    /// <summary>The flyout hid itself a moment ago, as it does when a click on the icon takes its focus: that click
    /// closes the flyout rather than opening it again.</summary>
    public bool JustHid => Environment.TickCount64 - hiddenAt < 300;

    /// <summary>A flyout closed for Quit has no window left to ask.</summary>
    public bool IsOpen => !closing && AppWindow.IsVisible;

    public FlyoutWindow(NativeCopy copy)
    {
        InitializeComponent();
        this.copy = copy;
        Title = "RoleBand";
        Handle = WinRT.Interop.WindowNative.GetWindowHandle(this);
        presenter.IsResizable = false;
        presenter.IsMaximizable = false;
        presenter.IsMinimizable = false;
        // A window without a border still gets a square light frame inside Windows' rounded corners; with one, Windows
        // draws only its rounded edge, in the colour Native.Dress gives it.
        presenter.SetBorderAndTitleBar(true, false);
        presenter.IsAlwaysOnTop = true;
        AppWindow.SetPresenter(presenter);
        AppWindow.IsShownInSwitchers = false;
        var round = 2;
        DwmSetWindowAttribute(Handle, 33, ref round, sizeof(int));
        Native.Dress(this, AppMark, ownEdge: true);

        AppName.Text = copy["guide-app"];
        AutomationProperties.SetName(SettingsButton, copy["settings"]);
        ToolTipService.SetToolTip(SettingsButton, copy["settings"]);
        DetailsButton.Content = copy["windows-details"];
        PauseText.Text = copy["scan-pause"];
        AutomationProperties.SetName(PauseButton, copy["pause-menu"]);
        ToolTipService.SetToolTip(PauseButton, copy["pause-help"]);
        ResumeText.Text = copy["scan-resume"];
        AutomationProperties.SetName(ResumeButton, copy["pause-resume"]);
        ToolTipService.SetToolTip(ResumeButton, copy["scan-resume-help"]);
        SettingsButton.Click += (_, _) => OpenSettings?.Invoke();
        UpdateButton.Click += (_, _) => UpdateRequested?.Invoke();
        UpdateCancelButton.Content = copy["update-cancel"];
        UpdateCancelButton.Click += (_, _) => CancelUpdateRequested?.Invoke();
        PrimaryButton.Click += (_, _) =>
        {
            switch (current?.Primary)
            {
                case FlyoutPrimary.Restart: Restart?.Invoke(); break;
                case FlyoutPrimary.Undo: Undo?.Invoke(); break;
                case FlyoutPrimary.CheckUpdates: CheckUpdates?.Invoke(); break;
                default: OpenRadar?.Invoke(); break;
            }
        };
        ScanButton.Click += (_, _) => { if (current is { ScanBusyKey: null, Scan: { } action }) Scan?.Invoke(action); };
        DetailsButton.Click += (_, _) => OpenSettings?.Invoke();
        ResumeButton.Click += (_, _) => Pause?.Invoke(PauseAction.Resume);
        foreach (var action in new[] { PauseAction.Hour, PauseAction.ThreeHours, PauseAction.Tomorrow })
        {
            var item = new MenuFlyoutItem { Text = copy[ScanControl.Key(action)] };
            item.Click += (_, _) => Pause?.Invoke(action);
            PauseMenu.Items.Add(item);
        }
        // The pause menu is a window of its own. Focus that moves there keeps the flyout open, so when the menu closes
        // with focus gone elsewhere, the flyout closes too.
        PauseMenu.Closed += (_, _) => DispatcherQueue.TryEnqueue(Microsoft.UI.Dispatching.DispatcherQueuePriority.Low, HideIfFocusLeft);

        var escape = new KeyboardAccelerator { Key = VirtualKey.Escape };
        escape.Invoked += (_, args) =>
        {
            args.Handled = true;
            if (standalone) QuitRequested?.Invoke();
            else Hide();
        };
        Root.KeyboardAccelerators.Add(escape);
        // Esc closes a flyout by convention; WinUI would otherwise float an "Esc" hint over the content on hover.
        Root.KeyboardAcceleratorPlacementMode = KeyboardAcceleratorPlacementMode.Hidden;
        Activated += (_, args) =>
        {
            // Windows reports a refused activation as an activation too, so focus counts only once the flyout is
            // really the foreground window.
            if (args.WindowActivationState != WindowActivationState.Deactivated) { focused = Native.IsForeground(Handle); return; }
            // Only focus the flyout had can leave it.
            if (focused) DispatcherQueue.TryEnqueue(Microsoft.UI.Dispatching.DispatcherQueuePriority.Low, HideIfFocusLeft);
        };
        AppWindow.Closing += (_, args) =>
        {
            if (closing) return;
            args.Cancel = true;
            if (standalone) QuitRequested?.Invoke();
            else Hide();
        };
        // The content's size drives the window's: a line more or less refits it, and nothing else does.
        Root.SizeChanged += (_, _) => { if (IsOpen) Fit(); };
    }

    private void HideIfFocusLeft()
    {
        if (standalone || !IsOpen || Native.ForegroundIsOurs()) return;
        focused = false;
        Hide();
    }

    /// <summary>Opens next to the point Windows reports for the icon, on that point's display.</summary>
    public void ShowNear(int x, int y)
    {
        anchor = (x, y);
        focused = false;
        Fit();
        AppWindow.Show(true);
        Activate();
        Native.BringForward(Handle);
        PrimaryButton.Focus(FocusState.Programmatic);
    }

    /// <summary>Without an icon: a framed window near the bottom right of the primary display, which stays open and
    /// whose close button quits.</summary>
    public void ShowStandalone()
    {
        standalone = true;
        presenter.SetBorderAndTitleBar(true, true);
        presenter.IsAlwaysOnTop = false;
        presenter.IsMinimizable = true;
        AppWindow.IsShownInSwitchers = true;
        var work = DisplayArea.Primary.WorkArea;
        anchor = (work.X + work.Width, work.Y + work.Height);
        Fit();
        AppWindow.Show(true);
        Activate();
    }

    /// <summary>Back to the icon's flyout once the icon is there: no title bar, above other windows, out of the task
    /// switchers, and hidden until the icon opens it.</summary>
    public void Dock()
    {
        if (!standalone || closing) return;
        standalone = false;
        if (presenter.State == OverlappedPresenterState.Minimized) presenter.Restore();
        presenter.SetBorderAndTitleBar(true, false);
        presenter.IsAlwaysOnTop = true;
        presenter.IsMinimizable = false;
        AppWindow.IsShownInSwitchers = false;
        Hide();
    }

    public void Hide()
    {
        if (!IsOpen) return;
        AppWindow.Hide();
        hiddenAt = Environment.TickCount64;
    }

    public void CloseForQuit()
    {
        closing = true;
        Close();
    }

    /// <summary>Sizes the window to its content and places it against the taskbar, in the display's own pixels. A
    /// framed window, once shown, keeps where the person put it and only changes height.</summary>
    private void Fit()
    {
        if (anchor is not { } point) return;
        var area = DisplayArea.GetFromPoint(new PointInt32(point.X, point.Y), DisplayAreaFallback.Nearest);
        var scale = standalone && IsOpen ? Native.ScaleOf(Handle) : Native.ScaleAt(point.X, point.Y);
        Root.Measure(new Windows.Foundation.Size(FlyoutWidth, double.PositiveInfinity));
        var frame = standalone ? 40 : 0;
        var width = (int)Math.Ceiling(FlyoutWidth * scale);
        var height = (int)Math.Ceiling((Root.DesiredSize.Height + frame) * scale);
        if (!standalone)
        {
            // The border Windows draws belongs to the window, so the window is that much larger than its content.
            width += AppWindow.Size.Width - AppWindow.ClientSize.Width;
            height += AppWindow.Size.Height - AppWindow.ClientSize.Height;
        }
        if (standalone && IsOpen)
        {
            AppWindow.Resize(new SizeInt32(Math.Max(width, AppWindow.Size.Width), height));
            return;
        }
        var display = new Box(area.OuterBounds.X, area.OuterBounds.Y, area.OuterBounds.Width, area.OuterBounds.Height);
        var work = new Box(area.WorkArea.X, area.WorkArea.Y, area.WorkArea.Width, area.WorkArea.Height);
        var (left, top) = FlyoutPlacement.Place(display, work, point.X, point.Y, width, height, (int)(Margin * scale),
                                                Native.Taskbar());
        AppWindow.MoveAndResize(new RectInt32(left, top, width, height));
    }

    public void Render(FlyoutView view, string? message)
    {
        current = view;
        // Narrator hears what the state is now, not every figure: the title, the banner's title and a message.
        var announce = IsOpen && TitleText.Text != view.Title;
        TitleText.Text = view.Title;
        CornerText.Text = view.Corner ?? "";
        var (glyph, brush) = view.Badge switch
        {
            TrayBadge.Stopped => ("", "SystemFillColorCriticalBrush"),
            TrayBadge.Attention => ("", "SystemFillColorCautionBrush"),
            _ => ((string?)null, (string?)null),
        };
        StateIcon.Visibility = glyph is null ? Visibility.Collapsed : Visibility.Visible;
        if (glyph is not null) { StateIcon.Glyph = glyph; StateIcon.Foreground = Brush(brush!); }
        ScanProgress.Visibility = view.Progress is not null || view.Busy ? Visibility.Visible : Visibility.Collapsed;
        ScanProgress.IsIndeterminate = view.Progress is null && view.Busy;
        ScanProgress.Value = view.Progress ?? 0;
        AutomationProperties.SetName(ScanProgress, view.ProgressLabel ?? view.Title);
        RenderLines(view.Lines);
        var said = IsOpen && message is not null && MessageText.Text != message;
        MessageText.Text = message ?? "";
        MessageText.Visibility = message is null ? Visibility.Collapsed : Visibility.Visible;
        if (announce) Native.Announce(TitleText);
        if (said) Native.Announce(MessageText);

        PrimaryButton.Content = copy[view.Primary switch
        {
            FlyoutPrimary.Restart => "engine-restart",
            FlyoutPrimary.Undo => "update-undo",
            FlyoutPrimary.CheckUpdates => "windows-check-updates",
            _ => "first-open",
        }];
        PrimaryButton.IsEnabled = view.PrimaryEnabled;
        ToolTipService.SetToolTip(PrimaryButton, view.PrimaryHelpKey is { } help ? copy[help] : null);
        // After the gold press, which takes focus from a banner that goes away.
        RenderUpdate(view.Update);

        DetailsButton.Visibility = view.Details ? Visibility.Visible : Visibility.Collapsed;
        if (view.Details) ScanButton.Visibility = Visibility.Collapsed;
        else if (view.ScanBusyKey is { } busy)
        {
            ScanGlyph.Glyph = "";
            ScanText.Text = copy[busy];
            ScanButton.IsEnabled = false;
            ScanButton.Visibility = Visibility.Visible;
        }
        else if (view.Scan is { } action)
        {
            ScanGlyph.Glyph = action == ScanAction.Start ? "" : "";
            ScanText.Text = copy[action == ScanAction.Start ? "scan-now" : "scan-stop"];
            AutomationProperties.SetName(ScanButton, ScanText.Text);
            ToolTipService.SetToolTip(ScanButton, action == ScanAction.Stop ? copy["scan-kept"] : null);
            ScanButton.IsEnabled = true;
            ScanButton.Visibility = Visibility.Visible;
        }
        else ScanButton.Visibility = Visibility.Collapsed;

        // Without a pause control the gold press takes two columns, so its longer words (Undo the update) fit.
        var wide = view.Pause == PauseControl.None;
        Grid.SetColumnSpan(PrimaryButton, wide ? 2 : 1);
        Grid.SetColumn(ScanButton, wide ? 2 : 1);
        Grid.SetColumn(DetailsButton, wide ? 2 : 1);
        PauseButton.Visibility = view.Pause == PauseControl.Menu ? Visibility.Visible : Visibility.Collapsed;
        ResumeButton.Visibility = view.Pause == PauseControl.Resume ? Visibility.Visible : Visibility.Collapsed;
        // A pause that just took effect moves focus from the button that was pressed to the one that undoes it.
        if (renderedPause != view.Pause && IsOpen)
        {
            if (view.Pause == PauseControl.Resume) ResumeButton.Focus(FocusState.Programmatic);
            else if (view.Pause == PauseControl.Menu && renderedPause == PauseControl.Resume) PauseButton.Focus(FocusState.Programmatic);
        }
        renderedPause = view.Pause;
    }

    /// <summary>The lines are rebuilt only when their words change, so a link keeps keyboard focus while the
    /// summary's clock moves.</summary>
    private void RenderLines(IReadOnlyList<FlyoutLine> lines)
    {
        var key = string.Join('\n', lines);
        if (key == renderedLines) return;
        renderedLines = key;
        Lines.Children.Clear();
        for (var index = 0; index < lines.Count; index++)
        {
            var line = lines[index];
            var text = new TextBlock { TextWrapping = TextWrapping.Wrap };
            if (index > 0)
            {
                text.FontSize = 12;
                text.Foreground = Brush("TextFillColorSecondaryBrush");
            }
            if (line.Link is { } words && line.Opens is { } route)
            {
                text.Inlines.Add(new Run { Text = line.Text + " · " });
                var link = new Hyperlink();
                link.Inlines.Add(new Run { Text = words });
                link.Click += (_, _) => Open?.Invoke(route);
                ToolTipService.SetToolTip(text, copy["scan-new-roles-open"]);
                text.Inlines.Add(link);
            }
            else text.Text = line.Text;
            Lines.Children.Add(text);
        }
    }

    /// <summary>The update banner: a download glyph in gold for an offer or a download, a caution glyph for a failure.
    /// Update and Cancel replace each other as a download starts and stops; a press that hides its own button hands
    /// focus to the one now in its place, or to the gold press when the banner goes, before it hides.</summary>
    private void RenderUpdate(FlyoutUpdate? update)
    {
        var pressed = IsOpen && Content.XamlRoot is { } root ? FocusManager.GetFocusedElement(root) as Button : null;
        var install = update?.Action is not null;
        var cancel = update is { Cancel: true, Action: null };
        if (update is not null) UpdateBanner.Visibility = Visibility.Visible;
        if (install) UpdateButton.Visibility = Visibility.Visible;
        if (cancel) UpdateCancelButton.Visibility = Visibility.Visible;
        if ((pressed == UpdateButton && !install) || (pressed == UpdateCancelButton && !cancel))
            (cancel ? UpdateCancelButton : install ? UpdateButton : PrimaryButton.IsEnabled ? PrimaryButton : SettingsButton)
                .Focus(FocusState.Programmatic);
        if (!install) UpdateButton.Visibility = Visibility.Collapsed;
        if (!cancel) UpdateCancelButton.Visibility = Visibility.Collapsed;
        if (update is null)
        {
            UpdateBanner.Visibility = Visibility.Collapsed;
            return;
        }
        UpdateGlyph.Glyph = update.Failed ? "" : "";
        UpdateGlyph.Foreground = Brush(update.Failed ? "SystemFillColorCautionBrush" : "RoleBandGold");
        var announce = IsOpen && UpdateTitle.Text != update.Title;
        UpdateTitle.Text = update.Title;
        UpdateCaption.Text = update.Caption ?? "";
        UpdateCaption.Visibility = update.Caption is null ? Visibility.Collapsed : Visibility.Visible;
        UpdateButton.Content = update.Action ?? "";
        UpdateProgress.Visibility = update.Busy ? Visibility.Visible : Visibility.Collapsed;
        UpdateProgress.IsIndeterminate = update.Percent is null;
        UpdateProgress.Value = update.Percent ?? 0;
        AutomationProperties.SetName(UpdateBanner, update.Caption is null ? update.Title : $"{update.Title}. {update.Caption}");
        if (announce) Native.Announce(UpdateBanner);
    }

    private static Brush Brush(string key) => (Brush)Application.Current.Resources[key];

    [DllImport("dwmapi.dll")]
    private static extern int DwmSetWindowAttribute(nint window, int attribute, ref int value, int size);
}

using Microsoft.UI.Text;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Automation;
using Microsoft.UI.Xaml.Controls;
using Microsoft.UI.Xaml.Input;
using Microsoft.UI.Xaml.Media;
using Microsoft.UI.Xaml.Shapes;
using RoleBand.EngineHost;
using System.Runtime.InteropServices;
using Windows.Graphics;
using Windows.System;

namespace RoleBand.App;

/// <summary>First open. The window draws <see cref="SetupFlow"/>'s page and reports presses; the panel owns
/// the record, the engine and the login item. Rows are built once per step and updated in place, so the
/// engine's once-a-second updates never take keyboard focus away.</summary>
public sealed partial class SetupWindow : Window
{
    private readonly NativeCopy copy;
    private readonly List<RowView> rows = [];
    private readonly List<Rectangle> steps = [];
    private readonly ToggleSwitch loginSwitch = new() { OnContent = "", OffContent = "", MinWidth = 0 };
    private SetupStep? built;
    private bool rendering;

    public event Action? Primary, Secondary, Back, Later, OpenLoginSettings, OpenTaskbarSettings;
    public event Action<bool>? LoginChanged;

    public SetupWindow(NativeCopy copy)
    {
        InitializeComponent();
        this.copy = copy;
        Title = "RoleBand";
        var scale = Math.Max(96, GetDpiForWindow(WinRT.Interop.WindowNative.GetWindowHandle(this))) / 96.0;
        AppWindow.Resize(new SizeInt32((int)(560 * scale), (int)(520 * scale)));
        BackButton.Content = copy["back"];
        LaterButton.Content = copy["later"];
        ToolTipService.SetToolTip(LaterButton, copy["windows-later-help"]);
        LoginSettings.Content = copy["windows-login-settings"];
        AutomationProperties.SetName(loginSwitch, copy["windows-login-toggle"]);
        var icon = System.IO.Path.Combine(AppContext.BaseDirectory, "RoleBand.ico");
        if (File.Exists(icon)) AppWindow.SetIcon(icon);
        SystemBackdrop = new MicaBackdrop();
        PrimaryButton.Click += (_, _) => Primary?.Invoke();
        SecondaryButton.Click += (_, _) => Secondary?.Invoke();
        BackButton.Click += (_, _) => Back?.Invoke();
        LaterButton.Click += (_, _) => Later?.Invoke();
        LoginSettings.Click += (_, _) => OpenLoginSettings?.Invoke();
        loginSwitch.Toggled += (_, _) => { if (!rendering) LoginChanged?.Invoke(loginSwitch.IsOn); };
        // Enter continues, as the page's one primary action.
        var enter = new KeyboardAccelerator { Key = VirtualKey.Enter };
        enter.Invoked += (_, args) =>
        {
            if (PrimaryButton.IsEnabled && FocusManager.GetFocusedElement(Root.XamlRoot) is not Button and not HyperlinkButton and not ToggleSwitch)
            {
                Primary?.Invoke();
                args.Handled = true;
            }
        };
        Root.KeyboardAccelerators.Add(enter);
        foreach (var _ in SetupFlow.Steps)
        {
            var bar = new Rectangle { Height = 3, RadiusX = 1.5, RadiusY = 1.5 };
            Grid.SetColumn(bar, steps.Count);
            StepStrip.Children.Add(bar);
            steps.Add(bar);
        }
    }

    public void Render(SetupPage page, bool switchOn, bool loginError, bool openFailed)
    {
        rendering = true;
        try
        {
            var position = SetupFlow.Position(page.Step);
            for (var index = 0; index < steps.Count; index++)
                steps[index].Fill = index < position ? Brush("RoleBandGold") : Brush("ControlStrokeColorDefaultBrush");
            StepLabel.Text = copy.Format("windows-step", ("step", position.ToString(copy.Culture)), ("total", SetupFlow.Steps.Count.ToString(copy.Culture)));
            Heading.Text = copy[page.HeadingKey];
            Body.Text = copy[page.BodyKey];
            if (built != page.Step) Build(page);
            for (var index = 0; index < rows.Count && index < page.Rows.Count; index++) Update(rows[index], page.Rows[index]);
            loginSwitch.IsOn = switchOn;
            loginSwitch.IsEnabled = page.LoginSwitchEnabled;
            LoginSettings.Visibility = page.LoginSettings ? Visibility.Visible : Visibility.Collapsed;
            var problem = loginError && page.Step == SetupStep.Login ? "login-error"
                : openFailed && page.Step == SetupStep.Login ? "setup-browser-error" : null;
            Problem.Text = problem is null ? "" : copy[problem];
            Problem.Visibility = problem is null ? Visibility.Collapsed : Visibility.Visible;
            Note.Text = page.NoteKey is null ? "" : copy[page.NoteKey];
            Note.Visibility = page.NoteKey is null ? Visibility.Collapsed : Visibility.Visible;

            BackButton.Visibility = page.Back ? Visibility.Visible : Visibility.Collapsed;
            LaterButton.Visibility = page.Later ? Visibility.Visible : Visibility.Collapsed;
            SecondaryButton.Visibility = page.SecondaryKey is null ? Visibility.Collapsed : Visibility.Visible;
            if (page.SecondaryKey is { } secondary) SecondaryButton.Content = copy[secondary];
            PrimaryText.Text = copy[page.PrimaryKey];
            AutomationProperties.SetName(PrimaryButton, copy[page.PrimaryKey]);
            PrimaryButton.IsEnabled = page.PrimaryEnabled;
            PrimaryBusy.IsActive = page.Busy;
            PrimaryBusy.Visibility = page.Busy ? Visibility.Visible : Visibility.Collapsed;
        }
        finally { rendering = false; }
    }

    private void Build(SetupPage page)
    {
        built = page.Step;
        Rows.Children.Clear();
        rows.Clear();
        if (loginSwitch.Parent is Panel parent) parent.Children.Remove(loginSwitch);
        for (var index = 0; index < page.Rows.Count; index++)
        {
            if (index > 0) Rows.Children.Add(new Rectangle { Height = 1, Margin = new Thickness(12, 0, 12, 0), Fill = Brush("DividerStrokeColorDefaultBrush") });
            var title = new TextBlock { FontWeight = FontWeights.SemiBold, TextWrapping = TextWrapping.Wrap };
            var caption = new TextBlock { FontSize = 12, TextWrapping = TextWrapping.Wrap, Foreground = Brush("TextFillColorSecondaryBrush") };
            var icon = new FontIcon { FontSize = 16, Visibility = Visibility.Collapsed };
            var ring = new ProgressRing { Width = 16, Height = 16, IsActive = false, Visibility = Visibility.Collapsed };
            var figure = new TextBlock { FontFamily = new FontFamily("Consolas"), Visibility = Visibility.Collapsed,
                Foreground = Brush("AccentTextFillColorPrimaryBrush"), VerticalAlignment = VerticalAlignment.Center };
            var bar = new ProgressBar { Maximum = 1, Visibility = Visibility.Collapsed, Margin = new Thickness(0, 6, 0, 0) };
            var text = new StackPanel { Spacing = 2, Children = { title, caption, bar } };
            var trailing = new Grid { VerticalAlignment = VerticalAlignment.Center, Children = { icon, ring, figure } };
            if (page.Rows[index].Mark == "switch") trailing.Children.Add(loginSwitch);
            if (page.Rows[index].Mark == "taskbar")
            {
                var taskbar = new Button { Content = copy["windows-taskbar-settings"] };
                AutomationProperties.SetAutomationId(taskbar, "TaskbarSettings");
                taskbar.Click += (_, _) => OpenTaskbarSettings?.Invoke();
                trailing.Children.Add(taskbar);
            }
            var row = new Grid { Padding = new Thickness(12, 10, 12, 10), ColumnSpacing = 12 };
            row.ColumnDefinitions.Add(new ColumnDefinition { Width = new GridLength(1, GridUnitType.Star) });
            row.ColumnDefinitions.Add(new ColumnDefinition { Width = GridLength.Auto });
            Grid.SetColumn(trailing, 1);
            row.Children.Add(text);
            row.Children.Add(trailing);
            Rows.Children.Add(row);
            rows.Add(new RowView(row, title, caption, icon, ring, figure, bar));
        }
    }

    private void Update(RowView view, SetupRow row)
    {
        view.Title.Text = copy[row.TitleKey];
        view.Caption.Text = row.CaptionKey == "" ? "" : copy[row.CaptionKey];
        view.Caption.Visibility = row.CaptionKey == "" ? Visibility.Collapsed : Visibility.Visible;
        var (glyph, brush) = row.Mark switch
        {
            "done" => ("", "AccentTextFillColorPrimaryBrush"),
            "failed" => ("", "SystemFillColorCautionBrush"),
            "waiting" => ("", "TextFillColorTertiaryBrush"),
            _ => ((string?)null, (string?)null),
        };
        view.Icon.Visibility = glyph is null ? Visibility.Collapsed : Visibility.Visible;
        if (glyph is not null) { view.Icon.Glyph = glyph; view.Icon.Foreground = Brush(brush!); }
        view.Ring.IsActive = row.Mark == "busy";
        view.Ring.Visibility = row.Mark == "busy" ? Visibility.Visible : Visibility.Collapsed;
        view.Figure.Text = row.Figure ?? "";
        view.Figure.Visibility = row.Figure is null ? Visibility.Collapsed : Visibility.Visible;
        view.Bar.Value = row.Progress ?? 0;
        view.Bar.Visibility = row.Progress is null ? Visibility.Collapsed : Visibility.Visible;
        // The mark is drawn, so the row says its state in words to a screen reader.
        AutomationProperties.SetName(view.Row, row.CaptionKey == "" ? copy[row.TitleKey]
            : $"{copy[row.TitleKey]}, {copy[row.CaptionKey]}{(row.Figure is null ? "" : ", " + row.Figure)}");
    }

    private sealed record RowView(Grid Row, TextBlock Title, TextBlock Caption, FontIcon Icon, ProgressRing Ring, TextBlock Figure, ProgressBar Bar);

    private static Brush Brush(string key) => (Brush)Application.Current.Resources[key];

    [DllImport("user32.dll")]
    private static extern uint GetDpiForWindow(nint window);
}

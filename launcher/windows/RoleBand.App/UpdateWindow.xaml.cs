using System.Runtime.InteropServices;
using Microsoft.UI.Windowing;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Automation;
using Microsoft.UI.Xaml.Controls;
using RoleBand.EngineHost;
using Windows.Graphics;

namespace RoleBand.App;

/// <summary>
/// The window that opens by itself for a release an automatic check found, in the middle of the primary display and above
/// other windows. It never takes focus, so whatever the person is typing keeps going, and it has neither a close button
/// nor Escape: Later is its way out. It draws <see cref="UpdateWindowView"/> and reports presses.
/// </summary>
public sealed partial class UpdateWindow : Window
{
    private const double ContentWidth = 400;
    private readonly NativeCopy copy;
    private readonly OverlappedPresenter presenter = OverlappedPresenter.Create();
    private readonly QuietWindow quiet;
    private UpdateWindowView? current;
    private bool shown;

    public event Action? Later, Update, Cancel, Notes;

    public nint Handle { get; }

    internal UpdateWindow(NativeCopy copy)
    {
        InitializeComponent();
        this.copy = copy;
        Handle = WinRT.Interop.WindowNative.GetWindowHandle(this);
        presenter.IsResizable = false;
        presenter.IsMaximizable = false;
        presenter.IsMinimizable = false;
        // As the flyout: with a border and no title bar, Windows draws only its rounded edge, in Native.Dress's colour.
        presenter.SetBorderAndTitleBar(true, false);
        presenter.IsAlwaysOnTop = true;
        AppWindow.SetPresenter(presenter);
        AppWindow.IsShownInSwitchers = false;
        var round = 2;
        DwmSetWindowAttribute(Handle, 33, ref round, sizeof(int));
        Native.Dress(this, AppMark, ownEdge: true);
        quiet = new QuietWindow(Handle);

        NotesLink.Content = copy["notes-title"];
        NotesLink.Click += (_, _) => Notes?.Invoke();
        SecondButton.Click += (_, _) => Press(Secondary(current));
        PrimaryButton.Click += (_, _) => Press(Primary(current));
        Closed += (_, _) => quiet.Dispose();
    }

    private static UpdateWindowChoice? Secondary(UpdateWindowView? view) =>
        view?.Choices.Where(choice => choice is UpdateWindowChoice.Later or UpdateWindowChoice.Cancel)
            .Select(choice => (UpdateWindowChoice?)choice).FirstOrDefault();

    private static UpdateWindowChoice? Primary(UpdateWindowView? view) =>
        view?.Choices.Where(choice => choice is UpdateWindowChoice.Update or UpdateWindowChoice.Retry)
            .Select(choice => (UpdateWindowChoice?)choice).FirstOrDefault();

    private void Press(UpdateWindowChoice? choice)
    {
        switch (choice)
        {
            case UpdateWindowChoice.Later: Later?.Invoke(); break;
            case UpdateWindowChoice.Cancel: Cancel?.Invoke(); break;
            case UpdateWindowChoice.Update or UpdateWindowChoice.Retry: Update?.Invoke(); break;
        }
    }

    public void Render(UpdateWindowView view)
    {
        current = view;
        // Narrator hears a change of step, not every figure of a download.
        var announce = shown && (Heading.Text != view.Heading || StepTitle.Text != (view.Step ?? ""));
        Title = view.Heading;
        Heading.Text = view.Heading;
        Body.Text = view.Body;
        NotesLink.Visibility = view.Page is null ? Visibility.Collapsed : Visibility.Visible;
        StepPanel.Visibility = view.Step is null ? Visibility.Collapsed : Visibility.Visible;
        StepTitle.Text = view.Step ?? "";
        StepDetail.Text = view.Detail ?? "";
        StepDetail.Visibility = view.Detail is null ? Visibility.Collapsed : Visibility.Visible;
        ToolTipService.SetToolTip(StepDetail, view.Detail ?? "");
        StepGlyph.Visibility = view.Failed ? Visibility.Visible : Visibility.Collapsed;
        StepProgress.Visibility = view.Failed ? Visibility.Collapsed : Visibility.Visible;
        StepProgress.IsIndeterminate = view.Working;
        StepProgress.Value = view.Percent ?? 0;
        AutomationProperties.SetName(StepPanel, view.Detail is null ? view.Step ?? "" : $"{view.Step}. {view.Detail}");
        var secondary = Secondary(view);
        SecondButton.Content = secondary == UpdateWindowChoice.Cancel ? copy["update-cancel"] : copy["update-later"];
        SecondButton.Visibility = secondary is null ? Visibility.Collapsed : Visibility.Visible;
        var primary = Primary(view);
        PrimaryButton.Content = primary == UpdateWindowChoice.Retry ? copy["retry"] : copy["update-install"];
        PrimaryButton.Visibility = primary is null ? Visibility.Collapsed : Visibility.Visible;
        Fit(place: false);
        if (announce) Native.Announce(StepPanel);
    }

    /// <summary>Shows the window in the middle of the primary display's work area, without taking focus.</summary>
    public void Present()
    {
        Fit(place: true);
        AppWindow.Show(false);
        quiet.Show();
        shown = true;
    }

    /// <summary>Sizes the window to its content in the display's own pixels; placing it centres it. Once shown it keeps its
    /// place and only changes height.</summary>
    private void Fit(bool place)
    {
        var scale = shown ? Native.ScaleOf(Handle) : Math.Max(96u, Native.PrimaryDpi()) / 96.0;
        Root.Measure(new Windows.Foundation.Size(ContentWidth, double.PositiveInfinity));
        // The border Windows draws belongs to the window, so the window is that much larger than its content.
        var width = (int)Math.Ceiling(ContentWidth * scale) + AppWindow.Size.Width - AppWindow.ClientSize.Width;
        var height = (int)Math.Ceiling(Root.DesiredSize.Height * scale) + AppWindow.Size.Height - AppWindow.ClientSize.Height;
        if (!place)
        {
            if (shown) AppWindow.Resize(new SizeInt32(width, height));
            return;
        }
        var work = DisplayArea.Primary.WorkArea;
        AppWindow.MoveAndResize(new RectInt32(work.X + (work.Width - width) / 2, work.Y + (work.Height - height) / 2, width, height));
    }

    [DllImport("dwmapi.dll")]
    private static extern int DwmSetWindowAttribute(nint window, int attribute, ref int value, int size);
}

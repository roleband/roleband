using Microsoft.UI.Xaml;
using RoleBand.EngineHost;
using System.Diagnostics;
using Microsoft.UI.Windowing;
using Windows.Graphics;
using System.Runtime.InteropServices;

namespace RoleBand.App;

public sealed partial class MainWindow : Window
{
    private readonly NativeCopy copy;
    private EngineSession? engine;
    private UpdateCoordinator? updates;
    private bool closing;
    private bool quitting;
    private TrayIcon? tray;
    private const int OpenRadarCommand = 1, ShowPanelCommand = 2, QuitCommand = 3;
    private string diagnosticLocation = "";

    public MainWindow(Exception? launchFailure = null)
    {
        InitializeComponent();
        Title = "RoleBand";
        // AppWindow sizes physical pixels; XAML layout uses device-independent pixels.
        var scale = Math.Max(96, GetDpiForWindow(WinRT.Interop.WindowNative.GetWindowHandle(this))) / 96.0;
        AppWindow.Resize(new SizeInt32((int)(640 * scale), (int)(540 * scale)));
        var args = Environment.GetCommandLineArgs().Skip(1).ToArray();
        string? Option(string name)
        {
            var index = Array.IndexOf(args, name);
            return index >= 0 && index + 1 < args.Length ? args[index + 1] : null;
        }
        copy = new NativeCopy(Option("--language"));
        StartButton.Content = copy["engine-start"];
        StopButton.Content = copy["engine-stop"];
        OpenButton.Content = copy["open"];
        Diagnostics.Header = copy["engine-diagnostics"];
        UndoButton.Content = copy["update-undo"];
        StartButton.Click += async (_, _) =>
        {
            if (engine is null || updates is null) return;
            // Settles an update the previous run began before anything opens the database.
            try
            {
                var phase = await updates.StartAsync(engine);
                if (phase is "failed" or "recovering") ShowFailedUpdate();
            }
            catch (Exception error) { StatusText.Text = copy["host-attention"]; DiagnosticsText.Text = error.Message; }
        };
        UndoButton.Click += async (_, _) =>
        {
            if (engine is null || updates is null) return;
            UndoButton.IsEnabled = false;
            // Windows closes this version and opens the previous one, whose Start restores the database.
            try { await updates.ReturnToPreviousAsync(engine); }
            catch (Exception error) { ShowFailedUpdate(); DiagnosticsText.Text = error.Message; }
            finally { UndoButton.IsEnabled = true; }
        };
        StopButton.Click += async (_, _) => { if (engine is not null) await StopAsync(); };
        OpenButton.Click += async (_, _) => await OpenRadarAsync();
        AppWindow.Closing += Closing;
        try
        {
            using var mark = typeof(MainWindow).Assembly.GetManifestResourceStream("RoleBand.TrayIcon.png")
                ?? throw new IOException("The notification-area mark is missing.");
            using var bytes = new MemoryStream();
            mark.CopyTo(bytes);
            tray = new TrayIcon(WinRT.Interop.WindowNative.GetWindowHandle(this), bytes.ToArray(), () =>
            [
                new(OpenRadarCommand, copy["first-open"], engine is not null && TrayModel.For(engine.Snapshot).CanOpenRadar),
                new(ShowPanelCommand, copy["open"], true),
                null,
                new(QuitCommand, copy["quit"], true),
            ]);
            tray.Opened += ShowPanel;
            tray.Chosen += async command =>
            {
                if (command == OpenRadarCommand) await OpenRadarAsync();
                else if (command == ShowPanelCommand) ShowPanel();
                else if (command == QuitCommand) await QuitAsync();
            };
        }
        catch (Exception error)
        {
            // Without the icon there is no way back to a hidden window, so closing keeps its old meaning.
            tray = null;
            Debug.WriteLine(error);
        }
        try
        {
            if (launchFailure is not null) throw launchFailure;
            var source = Option("--source-root");
            var state = Option("--state");
            if (source is not null && state is null) throw new IOException("Source trials require an explicit synthetic state directory.");
            var configuration = source is null
                ? EngineConfiguration.Packaged(Path.Combine(AppContext.BaseDirectory, "Resources"), state, args.Contains("--synthetic-fixture"))
                : EngineConfiguration.Source(source, state!, args.Contains("--synthetic-fixture"));
            engine = new EngineSession(configuration);
            updates = UpdateCoordinator.For(configuration);
            engine.Changed += snapshot => DispatcherQueue.TryEnqueue(() => Render(snapshot));
            diagnosticLocation = $"{configuration.Resources}{Environment.NewLine}{configuration.State}";
            Render(engine.Snapshot);
        }
        catch (Exception error)
        {
            StatusText.Text = copy["invalid"];
            DiagnosticsText.Text = error.Message;
            StartButton.IsEnabled = false;
        }
    }

    private void ShowFailedUpdate()
    {
        StatusText.Text = copy["update-stopped-title"];
        DiagnosticsText.Text = copy["update-stopped-body"];
        UndoButton.Visibility = Visibility.Visible;
    }

    private void Render(EngineSnapshot snapshot)
    {
        var state = TrayModel.For(snapshot);
        StatusText.Text = copy[state.StatusKey];
        OpenButton.IsEnabled = state.CanOpenRadar;
        StartButton.IsEnabled = engine is not null && !engine.OwnsEngine;
        StopButton.IsEnabled = engine?.OwnsEngine == true && snapshot.State != EngineState.Stopping;
        BusyIndicator.Visibility = state.Busy ? Visibility.Visible : Visibility.Collapsed;
        DiagnosticsText.Text = snapshot.Diagnostic ?? diagnosticLocation;
        tray?.SetTooltip(TrayModel.Tooltip(copy, snapshot));
    }

    private async Task OpenRadarAsync()
    {
        try
        {
            if (engine is not null)
                Process.Start(new ProcessStartInfo((await engine.BrowserUriAsync()).AbsoluteUri) { UseShellExecute = true });
        }
        catch (Exception error) { ShowPanel(); StatusText.Text = copy["setup-browser-error"]; DiagnosticsText.Text = error.Message; }
    }

    private void ShowPanel()
    {
        AppWindow.Show();
        Activate();
    }

    /// <summary>Quit stops the engine; closing the panel only hides it while the icon remains.</summary>
    private async Task QuitAsync()
    {
        quitting = true;
        await StopAsync();
        if (engine?.OwnsEngine == true)
        {
            quitting = false;
            ShowPanel();
            return;
        }
        tray?.Dispose();
        tray = null;
        closing = true;
        Close();
        Application.Current.Exit();
    }

    private async Task StopAsync()
    {
        try { if (engine is not null) await engine.StopAsync(); }
        catch (Exception error) { StatusText.Text = copy["host-stop-failed"]; DiagnosticsText.Text = error.Message; }
    }

    private async void Closing(AppWindow sender, AppWindowClosingEventArgs args)
    {
        if (tray is not null && !quitting && !closing)
        {
            args.Cancel = true;
            AppWindow.Hide();
            return;
        }
        if (closing || engine?.OwnsEngine != true) return;
        args.Cancel = true;
        await StopAsync();
        if (engine?.OwnsEngine != true)
        {
            closing = true;
            Close();
        }
    }

    [DllImport("user32.dll")]
    private static extern uint GetDpiForWindow(nint window);
}

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
        OpenButton.Click += async (_, _) =>
        {
            try
            {
                if (engine is not null)
                    Process.Start(new ProcessStartInfo((await engine.BrowserUriAsync()).AbsoluteUri) { UseShellExecute = true });
            }
            catch (Exception error) { StatusText.Text = copy["setup-browser-error"]; DiagnosticsText.Text = error.Message; }
        };
        AppWindow.Closing += Closing;
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
        StatusText.Text = copy[snapshot.State switch
        {
            EngineState.Starting => "host-starting",
            EngineState.Preparing => "first-busy",
            EngineState.Ready => "first-part-ready",
            EngineState.Recovering => "host-recovering",
            EngineState.Stopping => "scan-title-stopping",
            EngineState.Attention => "host-attention",
            _ => "host-stopped",
        }];
        OpenButton.IsEnabled = snapshot.State == EngineState.Ready;
        StartButton.IsEnabled = engine is not null && !engine.OwnsEngine;
        StopButton.IsEnabled = engine?.OwnsEngine == true && snapshot.State != EngineState.Stopping;
        BusyIndicator.Visibility = snapshot.State is EngineState.Starting or EngineState.Preparing or EngineState.Stopping or EngineState.Recovering
            ? Visibility.Visible : Visibility.Collapsed;
        DiagnosticsText.Text = snapshot.Diagnostic ?? diagnosticLocation;
    }

    private async Task StopAsync()
    {
        try { if (engine is not null) await engine.StopAsync(); }
        catch (Exception error) { StatusText.Text = copy["host-stop-failed"]; DiagnosticsText.Text = error.Message; }
    }

    private async void Closing(AppWindow sender, AppWindowClosingEventArgs args)
    {
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

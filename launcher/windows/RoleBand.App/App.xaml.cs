using Microsoft.UI.Xaml;
using RoleBand.EngineHost;

namespace RoleBand.App;

public partial class App : Application
{
    private Window? window;

    public App() => InitializeComponent();

    protected override void OnLaunched(LaunchActivatedEventArgs args)
    {
        Exception? failure = null;
        try
        {
            if (PackageProcess.RelaunchIfNeeded()) { Exit(); return; }
        }
        catch (Exception error) { failure = error; }
        window = new MainWindow(failure);
        window.Activate();
    }
}

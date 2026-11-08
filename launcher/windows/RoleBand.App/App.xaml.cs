using Microsoft.UI.Xaml;
using Microsoft.Windows.AppLifecycle;
using RoleBand.EngineHost;
using System.Security.Cryptography;
using System.Text;

namespace RoleBand.App;

public partial class App : Application
{
    /// <summary>Windows opened the app at sign-in, which opens quietly in the notification area.</summary>
    public const string AtLoginArgument = "--at-login";
    private TrayApp? app;

    public App()
    {
        InitializeComponent();
        // The app lives in the notification area with no window open; only Quit ends it.
        DispatcherShutdownMode = DispatcherShutdownMode.OnExplicitShutdown;
    }

    protected override async void OnLaunched(LaunchActivatedEventArgs args)
    {
        Exception? failure = null;
        var atLogin = Environment.GetCommandLineArgs().Contains(AtLoginArgument);
        try
        {
            var activation = AppInstance.GetCurrent().GetActivatedEventArgs();
            atLogin |= activation.Kind == ExtendedActivationKind.StartupTask;
            // One copy runs per data folder. A second start hands its activation to the running copy, which
            // does what Start means while it runs; it must find that copy before the package relaunch below.
            var key = InstanceKey();
            var running = AppInstance.GetInstances().FirstOrDefault(instance => instance.Key == key && !instance.IsCurrent);
            if (running is not null)
            {
                await running.RedirectActivationToAsync(activation);
                Exit();
                return;
            }
            if (PackageProcess.RelaunchIfNeeded(atLogin ? [AtLoginArgument] : [])) { Exit(); return; }
            var owner = AppInstance.FindOrRegisterForKey(key);
            if (!owner.IsCurrent)
            {
                await owner.RedirectActivationToAsync(activation);
                Exit();
                return;
            }
            owner.Activated += (_, redirected) =>
            {
                var quietly = redirected.Kind == ExtendedActivationKind.StartupTask;
                app?.Dispatcher.TryEnqueue(() => app.Reactivated(quietly));
            };
        }
        catch (Exception error) { failure = error; }
        app = new TrayApp(failure, atLogin);
    }

    /// <summary>The data folder names the instance, so a trial with its own state runs beside the everyday copy.</summary>
    private static string InstanceKey()
    {
        var args = Environment.GetCommandLineArgs();
        var index = Array.IndexOf(args, "--state");
        var state = index >= 0 && index + 1 < args.Length ? Path.GetFullPath(args[index + 1]).ToLowerInvariant() : "";
        return "RoleBand-" + Convert.ToHexString(SHA256.HashData(Encoding.UTF8.GetBytes(state)))[..16];
    }
}

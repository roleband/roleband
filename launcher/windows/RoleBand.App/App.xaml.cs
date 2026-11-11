using Microsoft.UI.Dispatching;
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
        // A source run may draw in a set theme, so the state lab captures both without changing Windows' own.
        if (Native.Option("--source-root") is not null && Native.Option("--theme") is { } theme)
            RequestedTheme = theme == "light" ? ApplicationTheme.Light : ApplicationTheme.Dark;
        // The app lives in the notification area with no window open; only Quit ends it.
        DispatcherShutdownMode = DispatcherShutdownMode.OnExplicitShutdown;
    }

    protected override async void OnLaunched(LaunchActivatedEventArgs args)
    {
        Exception? failure = null;
        var atLogin = Native.Flag(AtLoginArgument);
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
            // Redirected starts arrive on another thread. Queued on this one, they run after the app below is built,
            // so a second start during the first one's startup is not lost.
            var ui = DispatcherQueue.GetForCurrentThread();
            owner.Activated += (_, redirected) =>
            {
                var quietly = redirected.Kind == ExtendedActivationKind.StartupTask;
                ui.TryEnqueue(() => app?.Reactivated(quietly));
            };
        }
        catch (Exception error) { failure = error; }
        app = new TrayApp(failure, atLogin);
    }

    /// <summary>The data folder names the instance, so a trial with its own state runs beside the everyday copy.</summary>
    private static string InstanceKey()
    {
        var state = Native.Option("--state") is { } folder ? Path.GetFullPath(folder).ToLowerInvariant() : "";
        return "RoleBand-" + Convert.ToHexString(SHA256.HashData(Encoding.UTF8.GetBytes(state)))[..16];
    }
}

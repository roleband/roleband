using RoleBand.EngineHost;
using System.Diagnostics;
using Windows.Data.Xml.Dom;
using Windows.UI.Notifications;

namespace RoleBand.App;

/// <summary>
/// Shows the engine's alerts as Windows notifications, under the package's own name and icon. Pressing one opens the
/// app again, which a running app takes as its default command. A source run has no package identity, so Windows has
/// no app to show them under: they are taken and written to the debug output instead.
/// </summary>
internal sealed class Alerts(string folder)
{
    private ToastNotifier? notifier;
    private bool unavailable;

    public void ShowWaiting()
    {
        foreach (var alert in EngineAlerts.Take(folder, DateTimeOffset.Now))
        {
            if (Notifier() is not { } shown)
            {
                Debug.WriteLine($"Alert not shown: {alert.Title}: {alert.Message}");
                continue;
            }
            try
            {
                var content = new XmlDocument();
                content.LoadXml(EngineAlerts.ToastXml(alert));
                shown.Show(new ToastNotification(content));
            }
            catch (Exception error)
            {
                Debug.WriteLine($"Alert not shown ({error.Message}): {alert.Title}: {alert.Message}");
            }
        }
    }

    private ToastNotifier? Notifier()
    {
        if (notifier is not null || unavailable) return notifier;
        try
        {
            notifier = ToastNotificationManager.CreateToastNotifier();
        }
        catch (Exception error)
        {
            unavailable = true;
            Debug.WriteLine($"Windows notifications are unavailable: {error.Message}");
        }
        return notifier;
    }
}

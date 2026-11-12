using System.Runtime.InteropServices;

namespace RoleBand.EngineHost;

/// <summary>
/// Keeps a notification-area icon on a window. The icon is added once the window is hooked, and again whenever Explorer
/// creates its taskbar, which it announces to every top-level window with the registered TaskbarCreated message: at
/// sign-in the app can start before the notification area takes icons, and an Explorer restart forgets them all. An add
/// that fails is also tried again on a timer, for a taskbar that is there but did not answer in time. A failed add never
/// ends the app: the icon is missing until an add succeeds, and <see cref="Shown"/> says so.
/// </summary>
public sealed class TrayHook : IDisposable
{
    /// <summary>The wait between tries of an add that failed.</summary>
    public static readonly TimeSpan DefaultRetry = TimeSpan.FromSeconds(2);

    /// <summary>How many times the timer tries an add again before it leaves the icon to the next TaskbarCreated.</summary>
    public const int Retries = 30;

    private const uint Timer = 0x0113;
    // Timer identifiers belong to the window; this one is unlikely to meet another user of the same window.
    private const nuint RetryTimer = 0x5242_0001;
    private readonly WindowHook hook;
    private readonly Func<bool> add;
    private readonly WindowHook.Handler handler;
    private readonly Action<Exception>? failed;
    private readonly uint taskbarCreated;
    private readonly uint interval;
    private int tries;
    // The icon was shown before the taskbar it was on went away.
    private bool lost;

    /// <summary>The icon is in the notification area.</summary>
    public bool Shown { get; private set; }

    /// <summary>An icon that was missing has been added.</summary>
    public event Action? Appeared;

    /// <summary>The icon is missing and the app has no other surface: an icon that was shown could not be added to a new
    /// taskbar, or the timer's tries are spent. Tries go on after the first; <see cref="Appeared"/> follows a later
    /// success.</summary>
    public event Action? Missing;

    /// <param name="window">A top-level window owned by the calling thread, which must run its messages.</param>
    /// <param name="add">Adds the icon, or updates it when the shell still has it; false, or an exception, when the shell
    /// refused it.</param>
    /// <param name="handler">Sees the window's other messages, such as the icon's own.</param>
    /// <param name="failed">Told of an exception from <paramref name="add"/> or a handler.</param>
    /// <param name="retry">The wait between tries; <see cref="DefaultRetry"/> unless a test shortens it.</param>
    public TrayHook(nint window, Func<bool> add, WindowHook.Handler handler, Action<Exception>? failed = null, TimeSpan? retry = null)
    {
        this.add = add;
        this.handler = handler;
        this.failed = failed;
        interval = (uint)Math.Max(1, (retry ?? DefaultRetry).TotalMilliseconds);
        taskbarCreated = RegisterWindowMessage("TaskbarCreated");
        // An app running with administrator rights would otherwise not hear the taskbar, which runs without them.
        const uint Allow = 1;
        if (taskbarCreated != 0) ChangeWindowMessageFilterEx(window, taskbarCreated, Allow, 0);
        hook = new WindowHook(window, Procedure, failed);
        try
        {
            Show();
        }
        catch
        {
            hook.Dispose();
            throw;
        }
    }

    private bool Procedure(uint message, nint wParam, nint lParam, out nint result)
    {
        result = 0;
        if (message == taskbarCreated && taskbarCreated != 0)
        {
            // A new taskbar has none of the old one's icons.
            lost = Shown;
            Shown = false;
            tries = 0;
            Show();
            return false;
        }
        if (message == Timer && (nuint)wParam == RetryTimer)
        {
            Show();
            return true;
        }
        return handler(message, wParam, lParam, out result);
    }

    private void Show()
    {
        if (Shown)
        {
            KillTimer(hook.Window, RetryTimer);
            return;
        }
        bool added;
        try
        {
            added = add();
        }
        catch (Exception error)
        {
            Report(error);
            added = false;
        }
        if (!added)
        {
            if (lost)
            {
                lost = false;
                Raise(Missing);
            }
            // Setting the timer again keeps it running; it stops once its tries are spent.
            if (tries++ < Retries)
            {
                SetTimer(hook.Window, RetryTimer, interval, 0);
                return;
            }
            KillTimer(hook.Window, RetryTimer);
            Raise(Missing);
            return;
        }
        KillTimer(hook.Window, RetryTimer);
        lost = false;
        Shown = true;
        Raise(Appeared);
    }

    private void Raise(Action? handlers)
    {
        try
        {
            handlers?.Invoke();
        }
        catch (Exception error)
        {
            Report(error);
        }
    }

    private void Report(Exception error)
    {
        try { failed?.Invoke(error); }
        catch (Exception) { }
    }

    /// <summary>Call on the window's own thread, after the icon is deleted.</summary>
    public void Dispose()
    {
        KillTimer(hook.Window, RetryTimer);
        hook.Dispose();
    }

    [DllImport("user32.dll", CharSet = CharSet.Unicode, EntryPoint = "RegisterWindowMessageW")]
    private static extern uint RegisterWindowMessage(string name);
    [DllImport("user32.dll")]
    private static extern bool ChangeWindowMessageFilterEx(nint window, uint message, uint action, nint status);
    [DllImport("user32.dll")]
    private static extern nuint SetTimer(nint window, nuint id, uint elapse, nint callback);
    [DllImport("user32.dll")]
    private static extern bool KillTimer(nint window, nuint id);
}

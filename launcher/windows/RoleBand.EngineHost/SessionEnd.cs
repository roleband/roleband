using System.ComponentModel;
using System.Runtime.InteropServices;

namespace RoleBand.EngineHost;

/// <summary>
/// Ends the app when Windows ends it. Windows asks each top-level window with WM_QUERYENDSESSION and then confirms with
/// WM_ENDSESSION, at sign-out and also when it installs a new version of the package while the app runs (with
/// ENDSESSION_CLOSEAPP). A window's default handling agrees and carries on, so an app that does nothing else stays open:
/// Windows then waits about thirty seconds, terminates it and records a hang. The query alone changes nothing, since another
/// program may still refuse it.
/// <para>Once Windows confirms, it may end the process at any moment after the window answers, and with it the engine's
/// processes. So the engine stops while the confirmation is still unanswered, for at most the patience, with the thread's
/// messages still running, since the stop's own steps arrive as messages. <see cref="Ending"/> is raised after the answer,
/// for the app to close itself, which destroys the window the confirmation came to.</para>
/// </summary>
public sealed class SessionEnd : IDisposable
{
    public const uint QueryEndSession = 0x0011, EndSession = 0x0016;

    /// <summary>The flag Windows sets when it closes the app to replace files it uses, such as its package.</summary>
    public const nint CloseApp = 0x1;

    /// <summary>How long the confirmation waits for the engine to stop. At sign-out Windows shows that the app is still
    /// closing after a few seconds, and the person may sign out without waiting; the engine's supervisor also stops by
    /// itself when the app's process is gone.</summary>
    public static readonly TimeSpan DefaultPatience = TimeSpan.FromSeconds(15);

    /// <summary>The app's place in the order Windows ends processes at sign-out: the top of the range for applications
    /// that end first, ahead of every process left at the default level, the engine's among them.</summary>
    public const uint ShutdownLevel = 0x3FF;

    private const uint Quit = 0x0012;
    private readonly WindowHook hook;
    private readonly Func<Task> stop;
    private readonly TimeSpan patience;
    private readonly uint ended;
    private readonly TaskCompletionSource confirmed = new(TaskCreationOptions.RunContinuationsAsynchronously);
    private readonly TaskCompletionSource answered = new(TaskCreationOptions.RunContinuationsAsynchronously);

    /// <summary>Raised once, after Windows' confirmation is answered, for the app to close.</summary>
    public event Action? Ending;

    /// <summary>Windows has confirmed that it is ending the app.</summary>
    public bool Confirmed => confirmed.Task.IsCompleted;

    /// <param name="window">A top-level window of the app, owned by the calling thread, which must run its messages.</param>
    /// <param name="stop">Stops the engine; called on the window's thread when Windows confirms the end.</param>
    /// <param name="patience">How long the confirmation waits for that stop.</param>
    public SessionEnd(nint window, Func<Task> stop, TimeSpan? patience = null)
    {
        this.stop = stop;
        this.patience = patience ?? DefaultPatience;
        ended = RegisterWindowMessage("RoleBand.SessionEnded");
        if (ended == 0) throw new Win32Exception(Marshal.GetLastWin32Error());
        // Otherwise Windows can end the engine's processes before it asks the app, which stops them cleanly.
        SetProcessShutdownParameters(ShutdownLevel, 0);
        hook = new WindowHook(window, Procedure);
    }

    /// <summary>Waits for a quit's engine stop. Once Windows has confirmed the end, the wait ends when the confirmation is
    /// answered, whether or not the engine has stopped by then, and never earlier: the quit closes the window the
    /// confirmation came to.</summary>
    public async Task AwaitStopAsync(Task stop)
    {
        await Task.WhenAny(stop, answered.Task);
        if (Confirmed) await answered.Task;
        if (stop.IsCompleted) await stop;
    }

    /// <summary>Whether a quit closes the app: an engine that did not stop keeps it open with the reason shown, unless
    /// Windows is ending the app, which ends what is left of the package itself.</summary>
    public bool Closes(bool engineStillRunning) => !engineStillRunning || Confirmed;

    private bool Procedure(uint message, nint wParam, nint lParam, out nint result)
    {
        result = 0;
        if (message == ended)
        {
            Ending?.Invoke();
            return true;
        }
        // A false wParam means the end was called off, because another program refused it.
        if (message != EndSession || wParam == 0 || !confirmed.TrySetResult()) return false;
        try
        {
            Wait(Stop());
        }
        finally
        {
            answered.TrySetResult();
            if (!PostMessage(hook.Window, ended, 0, 0)) Ask();
        }
        return false;
    }

    /// <summary>Raises <see cref="Ending"/> through the thread's synchronization context, after the current message, or at
    /// once without one.</summary>
    private void Ask()
    {
        if (SynchronizationContext.Current is { } context) context.Post(_ => Ending?.Invoke(), null);
        else Ending?.Invoke();
    }

    private Task Stop()
    {
        try
        {
            return stop();
        }
        catch (Exception error)
        {
            return Task.FromException(error);
        }
    }

    /// <summary>Runs the thread's messages until the stop ends or the patience runs out.</summary>
    private void Wait(Task stopping)
    {
        const uint AllInput = 0x04FF, InputAvailable = 0x0004, Remove = 0x0001;
        var deadline = Environment.TickCount64 + (long)patience.TotalMilliseconds;
        while (!stopping.IsCompleted)
        {
            var left = deadline - Environment.TickCount64;
            if (left <= 0) return;
            // Wakes for a message at once; the stop's end is noticed within the poll.
            MsgWaitForMultipleObjectsEx(0, 0, (uint)Math.Min(left, 50), AllInput, InputAvailable);
            while (!stopping.IsCompleted && Environment.TickCount64 < deadline && PeekMessage(out var message, 0, 0, 0, Remove))
            {
                if (message.Message == Quit)
                {
                    // The thread's own loop ends on it once this wait is over.
                    PostQuitMessage((int)message.WParam);
                    return;
                }
                TranslateMessage(ref message);
                DispatchMessage(ref message);
            }
        }
    }

    /// <summary>Call on the window's own thread, before the window is destroyed.</summary>
    public void Dispose() => hook.Dispose();

    [StructLayout(LayoutKind.Sequential)]
    private struct WindowMessage
    {
        public nint Window;
        public uint Message;
        public nint WParam;
        public nint LParam;
        public uint Time;
        public int X, Y;
        public uint Private;
    }

    [DllImport("user32.dll", CharSet = CharSet.Unicode, EntryPoint = "RegisterWindowMessageW", SetLastError = true)]
    private static extern uint RegisterWindowMessage(string name);
    [DllImport("user32.dll")]
    private static extern bool PostMessage(nint window, uint message, nint wParam, nint lParam);
    [DllImport("user32.dll")]
    private static extern uint MsgWaitForMultipleObjectsEx(uint count, nint handles, uint milliseconds, uint wake, uint flags);
    [DllImport("user32.dll", EntryPoint = "PeekMessageW")]
    private static extern bool PeekMessage(out WindowMessage message, nint window, uint first, uint last, uint remove);
    [DllImport("user32.dll")]
    private static extern bool TranslateMessage(ref WindowMessage message);
    [DllImport("user32.dll", EntryPoint = "DispatchMessageW")]
    private static extern nint DispatchMessage(ref WindowMessage message);
    [DllImport("user32.dll")]
    private static extern void PostQuitMessage(int exitCode);
    [DllImport("kernel32.dll")]
    private static extern bool SetProcessShutdownParameters(uint level, uint flags);
}

using System.ComponentModel;
using System.Runtime.InteropServices;

namespace RoleBand.EngineHost;

/// <summary>
/// Tells the app when Windows ends it. Windows asks each top-level window with WM_QUERYENDSESSION and then confirms with
/// WM_ENDSESSION, at sign-out and also when it installs a new version of the package while the app runs (with
/// ENDSESSION_CLOSEAPP). A window's default handling agrees and carries on, so an app that does nothing else stays open:
/// Windows then waits about thirty seconds, terminates it and records a hang. <see cref="Ending"/> is raised once, when
/// Windows confirms the end, for the app to close itself; the query alone changes nothing, since another program may
/// still refuse it.
/// </summary>
public sealed class SessionEnd : IDisposable
{
    public const uint QueryEndSession = 0x0011, EndSession = 0x0016;

    /// <summary>The flag Windows sets when it closes the app to replace files it uses, such as its package.</summary>
    public const nint CloseApp = 0x1;

    /// <summary>How long a quit waits for the engine once Windows has confirmed the end: well inside the time Windows
    /// gives the app. The engine's supervisor stops by itself when the app's process is gone.</summary>
    public static readonly TimeSpan DefaultPatience = TimeSpan.FromSeconds(15);

    private readonly nint window;
    private readonly SubclassProcedure procedure;
    private readonly TimeSpan patience;
    private readonly TaskCompletionSource confirmed = new(TaskCreationOptions.RunContinuationsAsynchronously);
    private bool disposed;

    public event Action? Ending;

    /// <summary>Windows has confirmed that it is ending the app.</summary>
    public bool Confirmed => confirmed.Task.IsCompleted;

    /// <param name="window">A top-level window of the app, owned by the calling thread, which must run its messages.</param>
    /// <param name="patience">How long a quit waits for the engine after Windows confirms the end.</param>
    public SessionEnd(nint window, TimeSpan? patience = null)
    {
        this.window = window;
        this.patience = patience ?? DefaultPatience;
        procedure = Procedure;
        if (!SetWindowSubclass(window, procedure, 1, 0)) throw new Win32Exception(Marshal.GetLastWin32Error());
    }

    /// <summary>Waits for a quit's engine stop. Once Windows has confirmed the end, whether before or during the wait, it
    /// waits at most the patience after that, so the app closes before Windows terminates it.</summary>
    public async Task AwaitStopAsync(Task stop)
    {
        await Task.WhenAny(stop, CutoffAsync());
        if (stop.IsCompleted) await stop;
    }

    /// <summary>Whether a quit closes the app: an engine that did not stop keeps it open with the reason shown, unless
    /// Windows is ending the app, which ends what is left of the package itself.</summary>
    public bool Closes(bool engineStillRunning) => !engineStillRunning || Confirmed;

    private async Task CutoffAsync()
    {
        await confirmed.Task;
        await Task.Delay(patience);
    }

    private nint Procedure(nint hwnd, uint message, nint wParam, nint lParam, nuint id, nuint data)
    {
        // A false wParam means the end was called off, because another program refused it.
        if (message == EndSession && wParam != 0 && confirmed.TrySetResult()) Ending?.Invoke();
        return DefSubclassProc(hwnd, message, wParam, lParam);
    }

    /// <summary>Call on the window's own thread, before the window is destroyed.</summary>
    public void Dispose()
    {
        if (disposed) return;
        disposed = true;
        RemoveWindowSubclass(window, procedure, 1);
    }

    private delegate nint SubclassProcedure(nint hwnd, uint message, nint wParam, nint lParam, nuint id, nuint data);

    [DllImport("comctl32.dll", SetLastError = true)]
    private static extern bool SetWindowSubclass(nint window, SubclassProcedure procedure, nuint id, nuint data);
    [DllImport("comctl32.dll")]
    private static extern bool RemoveWindowSubclass(nint window, SubclassProcedure procedure, nuint id);
    [DllImport("comctl32.dll")]
    private static extern nint DefSubclassProc(nint window, uint message, nint wParam, nint lParam);
}

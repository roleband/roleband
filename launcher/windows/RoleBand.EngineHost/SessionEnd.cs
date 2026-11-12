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

    private readonly nint window;
    private readonly SubclassProcedure procedure;
    private bool raised, disposed;

    public event Action? Ending;

    /// <param name="window">A top-level window of the app, owned by the calling thread, which must run its messages.</param>
    public SessionEnd(nint window)
    {
        this.window = window;
        procedure = Procedure;
        if (!SetWindowSubclass(window, procedure, 1, 0)) throw new Win32Exception(Marshal.GetLastWin32Error());
    }

    private nint Procedure(nint hwnd, uint message, nint wParam, nint lParam, nuint id, nuint data)
    {
        // A false wParam means the end was called off, because another program refused it.
        if (message == EndSession && wParam != 0 && !raised)
        {
            raised = true;
            Ending?.Invoke();
        }
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

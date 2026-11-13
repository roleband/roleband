using System.ComponentModel;
using System.Diagnostics;
using System.Runtime.InteropServices;

namespace RoleBand.EngineHost;

/// <summary>
/// Handles a window's messages in the app's own code, through a subclass of the window. An exception never leaves the
/// handler: one that crossed back into Windows would end the process, so it is reported and the message gets the window's
/// default handling. Windows calls the hook until it is removed, so the hook keeps itself alive until then, even when its
/// owner lets go of it; it is removed by <see cref="Dispose"/>, or when the window is destroyed. Dispose may be called
/// from inside the handler: the subclass is then removed once the handler returns.
/// </summary>
public sealed class WindowHook : IDisposable
{
    /// <summary>True when the message is handled, with the window's answer in <paramref name="result"/>; false passes it
    /// on to the window.</summary>
    public delegate bool Handler(uint message, nint wParam, nint lParam, out nint result);

    private const uint NcDestroy = 0x0082;
    private static long lastId;
    private readonly nuint id;
    private readonly SubclassProcedure procedure;
    private readonly Handler handler;
    private readonly Action<Exception> failed;
    private GCHandle alive;
    private int depth;
    private bool disposed, removed;

    /// <summary>The hooked window.</summary>
    public nint Window { get; }

    /// <param name="window">A window owned by the calling thread; a hook can be installed only from that thread.</param>
    /// <param name="handler">Sees every message before the window does.</param>
    /// <param name="failed">Told of an exception the handler raised; it is written to the debug output otherwise.</param>
    public WindowHook(nint window, Handler handler, Action<Exception>? failed = null)
    {
        Window = window;
        this.handler = handler;
        this.failed = failed ?? (error => Debug.WriteLine(error));
        id = (nuint)Interlocked.Increment(ref lastId);
        procedure = Procedure;
        if (!SetWindowSubclass(window, procedure, id, 0)) throw new Win32Exception(Marshal.GetLastWin32Error());
        alive = GCHandle.Alloc(this);
    }

    private nint Procedure(nint hwnd, uint message, nint wParam, nint lParam, nuint subclass, nuint data)
    {
        if (disposed || removed) return DefSubclassProc(hwnd, message, wParam, lParam);
        depth++;
        try
        {
            if (message != NcDestroy && Handle(message, wParam, lParam, out var result)) return result;
            return DefSubclassProc(hwnd, message, wParam, lParam);
        }
        finally
        {
            depth--;
            // A destroyed window sends nothing more; a hook disposed inside its own handler goes once that returns.
            if (message == NcDestroy || (disposed && depth == 0)) Remove();
        }
    }

    private bool Handle(uint message, nint wParam, nint lParam, out nint result)
    {
        try
        {
            return handler(message, wParam, lParam, out result);
        }
        catch (Exception error)
        {
            try { failed(error); }
            catch (Exception) { }
            result = 0;
            return false;
        }
    }

    private void Remove()
    {
        if (removed) return;
        removed = true;
        RemoveWindowSubclass(Window, procedure, id);
        if (alive.IsAllocated) alive.Free();
    }

    /// <summary>Call on the window's own thread.</summary>
    public void Dispose()
    {
        if (disposed) return;
        disposed = true;
        if (depth == 0) Remove();
    }

    private delegate nint SubclassProcedure(nint hwnd, uint message, nint wParam, nint lParam, nuint id, nuint data);

    [DllImport("comctl32.dll", SetLastError = true)]
    private static extern bool SetWindowSubclass(nint window, SubclassProcedure procedure, nuint id, nuint data);
    [DllImport("comctl32.dll")]
    private static extern bool RemoveWindowSubclass(nint window, SubclassProcedure procedure, nuint id);
    [DllImport("comctl32.dll")]
    private static extern nint DefSubclassProc(nint window, uint message, nint wParam, nint lParam);
}

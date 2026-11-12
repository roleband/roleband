using System.Collections.Concurrent;
using System.ComponentModel;
using System.Runtime.InteropServices;

namespace RoleBand.EngineHost.Tests;

/// <summary>
/// A hidden top-level window on a thread of its own that runs its messages until disposed, as the app's flyout does. Work
/// posted to the thread's synchronization context arrives as a message to the window, as the app's dispatcher's does, so
/// it also runs in a message loop nested inside one of the window's own messages.
/// </summary>
internal sealed class WindowThread : IDisposable
{
    public const string Title = "RoleBand test window";
    private const uint Work = 0x8000 + 7, Quit = 0x0012;
    private static readonly WindowProcedure Procedure = Dispatch;
    private static readonly ConcurrentDictionary<nint, WindowThread> Owners = new();
    private static readonly Lazy<string> ClassName = new(Register);
    private readonly Thread thread;
    private readonly ConcurrentQueue<Action> work = new();
    private readonly List<Action> cleanup = [];
    private readonly uint threadId;
    private nint window;

    public nint Window => window;

    public WindowThread()
    {
        var ready = new TaskCompletionSource<uint>(TaskCreationOptions.RunContinuationsAsynchronously);
        thread = new Thread(() => Loop(ready)) { IsBackground = true };
        thread.Start();
        threadId = ready.Task.WaitAsync(TimeSpan.FromSeconds(10)).GetAwaiter().GetResult();
    }

    /// <summary>Runs <paramref name="action"/> on the window's thread and waits for it. Work posted earlier, such as a
    /// message the window posted to itself, has run by then.</summary>
    public void Run(Action action) => Run(() => { action(); return 0; });

    public T Run<T>(Func<T> function)
    {
        var done = new TaskCompletionSource<T>(TaskCreationOptions.RunContinuationsAsynchronously);
        Post(() =>
        {
            try { done.SetResult(function()); }
            catch (Exception error) { done.SetException(error); }
        });
        return done.Task.WaitAsync(TimeSpan.FromSeconds(10)).GetAwaiter().GetResult();
    }

    /// <summary>Runs on the window's thread before the window is destroyed, as the app disposes what hooks its window.</summary>
    public void OnDispose(Action action) => cleanup.Add(action);

    /// <summary>The window's answer; a window that does not answer in time fails the test rather than hanging the run.</summary>
    public nint Send(uint message, nint wParam, nint lParam, int timeout = 10_000)
    {
        const uint AbortIfHung = 0x2;
        if (SendMessageTimeout(window, message, wParam, lParam, AbortIfHung, (uint)timeout, out var result) == 0)
            throw new TimeoutException($"The window did not answer message 0x{message:X4}.");
        return result;
    }

    /// <summary>Whether the calling window procedure handles a message another thread sent, as Windows sends its end of
    /// the session.</summary>
    public static bool InsideSentMessage() => InSendMessage();

    public static uint Message(string name) =>
        RegisterWindowMessage(name) is var message and not 0 ? message : throw new Win32Exception(Marshal.GetLastWin32Error());

    private void Post(Action action)
    {
        work.Enqueue(action);
        if (!PostMessage(window, Work, 0, 0)) throw new InvalidOperationException("The window is gone.");
    }

    private void Loop(TaskCompletionSource<uint> ready)
    {
        const uint Popup = 0x80000000;
        var created = CreateWindowEx(0, ClassName.Value, Title, Popup, 0, 0, 10, 10, 0, 0, GetModuleHandle(null), 0);
        if (created == 0)
        {
            ready.SetException(new Win32Exception(Marshal.GetLastWin32Error()));
            return;
        }
        window = created;
        Owners[created] = this;
        SynchronizationContext.SetSynchronizationContext(new Context(this));
        ready.SetResult(GetCurrentThreadId());
        while (GetMessage(out var message, 0, 0, 0) > 0)
        {
            TranslateMessage(ref message);
            DispatchMessage(ref message);
        }
        foreach (var action in cleanup) action();
        DestroyWindow(created);
        Owners.TryRemove(created, out _);
    }

    private static nint Dispatch(nint hwnd, uint message, nint wParam, nint lParam)
    {
        if (message != Work || !Owners.TryGetValue(hwnd, out var owner)) return DefWindowProc(hwnd, message, wParam, lParam);
        while (owner.work.TryDequeue(out var action)) action();
        return 0;
    }

    private static string Register()
    {
        const string name = "RoleBandTestWindow";
        var type = new WindowClass
        {
            Size = (uint)Marshal.SizeOf<WindowClass>(), Procedure = Marshal.GetFunctionPointerForDelegate(Procedure),
            Instance = GetModuleHandle(null), ClassName = name,
        };
        if (RegisterClassEx(ref type) == 0) throw new Win32Exception(Marshal.GetLastWin32Error());
        return name;
    }

    public void Dispose()
    {
        PostThreadMessage(threadId, Quit, 0, 0);
        thread.Join(TimeSpan.FromSeconds(10));
    }

    private sealed class Context(WindowThread owner) : SynchronizationContext
    {
        public override void Post(SendOrPostCallback callback, object? state) => owner.Post(() => callback(state));
        public override void Send(SendOrPostCallback callback, object? state) => throw new NotSupportedException();
        public override SynchronizationContext CreateCopy() => this;
    }

    private delegate nint WindowProcedure(nint window, uint message, nint wParam, nint lParam);

    [StructLayout(LayoutKind.Sequential, CharSet = CharSet.Unicode)]
    private struct WindowClass
    {
        public uint Size;
        public uint Style;
        public nint Procedure;
        public int ClassExtra;
        public int WindowExtra;
        public nint Instance;
        public nint Icon;
        public nint Cursor;
        public nint Background;
        public string? MenuName;
        public string ClassName;
        public nint SmallIcon;
    }

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

    [DllImport("user32.dll", CharSet = CharSet.Unicode, EntryPoint = "RegisterClassExW", SetLastError = true)]
    private static extern ushort RegisterClassEx(ref WindowClass type);
    [DllImport("user32.dll", CharSet = CharSet.Unicode, EntryPoint = "CreateWindowExW", SetLastError = true)]
    private static extern nint CreateWindowEx(uint exStyle, string className, string title, uint style, int x, int y, int width,
                                              int height, nint parent, nint menu, nint instance, nint parameter);
    [DllImport("user32.dll", EntryPoint = "DefWindowProcW")]
    private static extern nint DefWindowProc(nint window, uint message, nint wParam, nint lParam);
    [DllImport("user32.dll")]
    private static extern bool DestroyWindow(nint window);
    [DllImport("user32.dll", EntryPoint = "GetMessageW")]
    private static extern int GetMessage(out WindowMessage message, nint window, uint first, uint last);
    [DllImport("user32.dll")]
    private static extern bool TranslateMessage(ref WindowMessage message);
    [DllImport("user32.dll", EntryPoint = "DispatchMessageW")]
    private static extern nint DispatchMessage(ref WindowMessage message);
    [DllImport("user32.dll", EntryPoint = "PostMessageW")]
    private static extern bool PostMessage(nint window, uint message, nint wParam, nint lParam);
    [DllImport("user32.dll", EntryPoint = "PostThreadMessageW")]
    private static extern bool PostThreadMessage(uint thread, uint message, nint wParam, nint lParam);
    [DllImport("user32.dll", EntryPoint = "SendMessageTimeoutW")]
    private static extern nint SendMessageTimeout(nint window, uint message, nint wParam, nint lParam, uint flags, uint timeout,
                                                  out nint result);
    [DllImport("user32.dll")]
    private static extern bool InSendMessage();
    [DllImport("user32.dll", CharSet = CharSet.Unicode, EntryPoint = "RegisterWindowMessageW", SetLastError = true)]
    private static extern uint RegisterWindowMessage(string name);
    [DllImport("kernel32.dll", CharSet = CharSet.Unicode, EntryPoint = "GetModuleHandleW")]
    private static extern nint GetModuleHandle(string? name);
    [DllImport("kernel32.dll")]
    private static extern uint GetCurrentThreadId();
}

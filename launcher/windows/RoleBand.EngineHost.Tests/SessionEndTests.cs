using System.Collections.Concurrent;
using System.Runtime.InteropServices;
using RoleBand.EngineHost;

namespace RoleBand.EngineHost.Tests;

/// <summary>
/// Windows ends the app by sending its windows WM_QUERYENDSESSION and then WM_ENDSESSION, at sign-out and when it installs
/// a new version of the package. These tests send the same messages to a real top-level window running its own message
/// loop, as the app's flyout does, and hold the app to closing only once Windows confirms the end.
/// </summary>
[TestClass]
public sealed class SessionEndTests
{
    [TestMethod]
    public void ConfirmedEndAsksTheAppToCloseOnce()
    {
        using var window = new WindowThread();
        var endings = 0;
        window.Attach(() => endings++);

        Assert.AreNotEqual(0, window.Send(SessionEnd.QueryEndSession, 0, SessionEnd.CloseApp), "the app must agree to end");
        Assert.AreEqual(0, endings, "a query alone must not close the app: another program may still refuse");
        window.Send(SessionEnd.EndSession, 1, SessionEnd.CloseApp);
        Assert.AreEqual(1, endings);
        window.Send(SessionEnd.EndSession, 1, SessionEnd.CloseApp);
        Assert.AreEqual(1, endings, "a second confirmation must not start a second quit");
    }

    [TestMethod]
    public void SignOutClosesTheAppToo()
    {
        using var window = new WindowThread();
        var endings = 0;
        window.Attach(() => endings++);

        var logOff = unchecked((nint)0x80000000);
        Assert.AreNotEqual(0, window.Send(SessionEnd.QueryEndSession, 0, logOff));
        window.Send(SessionEnd.EndSession, 1, logOff);
        Assert.AreEqual(1, endings);
    }

    [TestMethod]
    public void AnEndCalledOffLeavesTheAppOpen()
    {
        using var window = new WindowThread();
        var endings = 0;
        window.Attach(() => endings++);

        window.Send(SessionEnd.QueryEndSession, 0, SessionEnd.CloseApp);
        window.Send(SessionEnd.EndSession, 0, SessionEnd.CloseApp);
        Assert.AreEqual(0, endings, "Windows called the end off, so the app carries on");
    }

    [TestMethod]
    public void ADisposedListenerNoLongerClosesTheApp()
    {
        using var window = new WindowThread();
        var endings = 0;
        window.Attach(() => endings++);
        window.Detach();

        window.Send(SessionEnd.EndSession, 1, SessionEnd.CloseApp);
        Assert.AreEqual(0, endings);
    }

    /// <summary>A hidden top-level window on a thread of its own that runs its messages until disposed.</summary>
    private sealed class WindowThread : IDisposable
    {
        private const uint Run = 0x8000 + 7, Quit = 0x0012;
        private readonly Thread thread;
        private readonly BlockingCollection<Action> work = [];
        private readonly TaskCompletionSource<(nint Window, uint Thread)> ready = new(TaskCreationOptions.RunContinuationsAsynchronously);
        private nint window;
        private uint threadId;
        private SessionEnd? listener;

        public WindowThread()
        {
            thread = new Thread(Loop) { IsBackground = true };
            thread.Start();
            (window, threadId) = ready.Task.WaitAsync(TimeSpan.FromSeconds(10)).GetAwaiter().GetResult();
        }

        public void Attach(Action ending) => OnThread(() =>
        {
            listener = new SessionEnd(window);
            listener.Ending += ending;
        });

        public void Detach() => OnThread(() => listener?.Dispose());

        public nint Send(uint message, nint wParam, nint lParam) => SendMessage(window, message, wParam, lParam);

        private void OnThread(Action action)
        {
            var done = new TaskCompletionSource(TaskCreationOptions.RunContinuationsAsynchronously);
            work.Add(() =>
            {
                try { action(); done.SetResult(); }
                catch (Exception error) { done.SetException(error); }
            });
            if (!PostThreadMessage(threadId, Run, 0, 0)) throw new InvalidOperationException("The window thread is gone.");
            done.Task.WaitAsync(TimeSpan.FromSeconds(10)).GetAwaiter().GetResult();
        }

        private void Loop()
        {
            const uint Popup = 0x80000000;
            var created = CreateWindowEx(0, "STATIC", "RoleBand session test", Popup, 0, 0, 10, 10, 0, 0, 0, 0);
            if (created == 0) { ready.SetException(new InvalidOperationException("No window was created.")); return; }
            ready.SetResult((created, GetCurrentThreadId()));
            while (GetMessage(out var message, 0, 0, 0) > 0)
            {
                if (message.Window == 0 && message.Message == Run)
                {
                    while (work.TryTake(out var action)) action();
                    continue;
                }
                TranslateMessage(ref message);
                DispatchMessage(ref message);
            }
            listener?.Dispose();
            DestroyWindow(created);
        }

        public void Dispose()
        {
            PostThreadMessage(threadId, Quit, 0, 0);
            thread.Join(TimeSpan.FromSeconds(10));
        }
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

    [DllImport("user32.dll", CharSet = CharSet.Unicode, EntryPoint = "CreateWindowExW", SetLastError = true)]
    private static extern nint CreateWindowEx(uint exStyle, string className, string title, uint style, int x, int y, int width,
                                              int height, nint parent, nint menu, nint instance, nint parameter);
    [DllImport("user32.dll")]
    private static extern bool DestroyWindow(nint window);
    [DllImport("user32.dll", EntryPoint = "GetMessageW")]
    private static extern int GetMessage(out WindowMessage message, nint window, uint first, uint last);
    [DllImport("user32.dll")]
    private static extern bool TranslateMessage(ref WindowMessage message);
    [DllImport("user32.dll", EntryPoint = "DispatchMessageW")]
    private static extern nint DispatchMessage(ref WindowMessage message);
    [DllImport("user32.dll", EntryPoint = "PostThreadMessageW")]
    private static extern bool PostThreadMessage(uint thread, uint message, nint wParam, nint lParam);
    [DllImport("user32.dll", EntryPoint = "SendMessageW")]
    private static extern nint SendMessage(nint window, uint message, nint wParam, nint lParam);
    [DllImport("kernel32.dll")]
    private static extern uint GetCurrentThreadId();
}

using System.Diagnostics;
using System.Runtime.InteropServices;
using RoleBand.EngineHost;

namespace RoleBand.EngineHost.Tests;

/// <summary>
/// Windows ends the app by sending its windows WM_QUERYENDSESSION and then WM_ENDSESSION, at sign-out and when it installs
/// a new version of the package, and may end the process, and the engine's, as soon as WM_ENDSESSION is answered. These
/// tests send the same messages to a real top-level window running its own message loop, as the app's flyout does, with
/// an engine stop whose steps come back to the window's thread as messages, as the app's dispatcher delivers them. They
/// hold the app to stopping the engine before it answers, within its patience, and to closing only after the answer.
/// </summary>
[TestClass]
public sealed class SessionEndTests
{
    private static readonly nint LogOff = unchecked((nint)0x80000000);

    /// <summary>The listener on the window's thread, as the app makes it.</summary>
    private static SessionEnd Listen(WindowThread window, Action ending, Func<Task>? stop = null, TimeSpan? patience = null) =>
        window.Run(() =>
        {
            var listener = new SessionEnd(window.Window, stop ?? (() => Task.CompletedTask), patience);
            listener.Ending += ending;
            window.OnDispose(listener.Dispose);
            return listener;
        });

    [TestMethod]
    public void ConfirmedEndAsksTheAppToCloseOnce()
    {
        using var window = new WindowThread();
        var endings = 0;
        var stops = 0;
        Listen(window, () => endings++, () => { stops++; return Task.CompletedTask; });

        Assert.AreNotEqual(0, window.Send(SessionEnd.QueryEndSession, 0, SessionEnd.CloseApp), "the app must agree to end");
        Assert.AreEqual((0, 0), window.Run(() => (endings, stops)), "a query alone must not close the app: another program may still refuse");
        window.Send(SessionEnd.EndSession, 1, SessionEnd.CloseApp);
        Assert.AreEqual((1, 1), window.Run(() => (endings, stops)));
        window.Send(SessionEnd.EndSession, 1, SessionEnd.CloseApp);
        Assert.AreEqual((1, 1), window.Run(() => (endings, stops)), "a second confirmation must not start a second quit");
    }

    [TestMethod]
    public void SignOutClosesTheAppToo()
    {
        using var window = new WindowThread();
        var endings = 0;
        Listen(window, () => endings++);

        Assert.AreNotEqual(0, window.Send(SessionEnd.QueryEndSession, 0, LogOff));
        window.Send(SessionEnd.EndSession, 1, LogOff);
        Assert.AreEqual(1, window.Run(() => endings));
    }

    [TestMethod]
    public void AnEndCalledOffLeavesTheAppAndTheEngineRunning()
    {
        using var window = new WindowThread();
        var endings = 0;
        var stops = 0;
        Listen(window, () => endings++, () => { stops++; return Task.CompletedTask; });

        window.Send(SessionEnd.QueryEndSession, 0, SessionEnd.CloseApp);
        window.Send(SessionEnd.EndSession, 0, SessionEnd.CloseApp);
        Assert.AreEqual((0, 0), window.Run(() => (endings, stops)), "Windows called the end off, so the app carries on");
    }

    [TestMethod]
    public void ADisposedListenerNoLongerClosesTheApp()
    {
        using var window = new WindowThread();
        var endings = 0;
        var stops = 0;
        var listener = Listen(window, () => endings++, () => { stops++; return Task.CompletedTask; });
        window.Run(listener.Dispose);

        window.Send(SessionEnd.EndSession, 1, SessionEnd.CloseApp);
        Assert.AreEqual((0, 0), window.Run(() => (endings, stops)));
    }

    [TestMethod]
    public void TheEngineStopsBeforeWindowsIsAnswered()
    {
        using var window = new WindowThread();
        var stopped = false;
        Listen(window, () => { }, async () =>
        {
            // Each step resumes on the window's thread through a message, which arrives only while messages run.
            await Task.Delay(200);
            await Task.Delay(100);
            stopped = true;
        }, patience: TimeSpan.FromSeconds(8));

        var clock = Stopwatch.StartNew();
        window.Send(SessionEnd.EndSession, 1, LogOff);
        var answeredAfter = clock.Elapsed;

        Assert.IsTrue(window.Run(() => stopped), "Windows may end the engine as soon as it is answered");
        Assert.IsTrue(answeredAfter >= TimeSpan.FromMilliseconds(250), $"answered after {answeredAfter}");
        Assert.IsTrue(answeredAfter < TimeSpan.FromSeconds(5), $"a stop that needs the window's thread waited out the patience: {answeredAfter}");
    }

    [TestMethod]
    public void AnEngineThatDoesNotStopHoldsWindowsOnlyForThePatience()
    {
        using var window = new WindowThread();
        var endings = 0;
        var never = new TaskCompletionSource();
        Listen(window, () => endings++, () => never.Task, patience: TimeSpan.FromMilliseconds(300));

        var clock = Stopwatch.StartNew();
        window.Send(SessionEnd.EndSession, 1, LogOff);

        Assert.IsTrue(clock.Elapsed >= TimeSpan.FromMilliseconds(250), "the engine gets the patience to stop cleanly");
        Assert.IsTrue(clock.Elapsed < TimeSpan.FromSeconds(5), $"answered after {clock.Elapsed}");
        Assert.AreEqual(1, window.Run(() => endings), "the app still closes");
    }

    [TestMethod]
    public void AStopThatFailsHoldsNothingAndTheAppStillCloses()
    {
        foreach (var stop in new Func<Task>[] { () => throw new IOException("No engine."), () => Task.FromException(new IOException("No engine.")) })
        {
            using var window = new WindowThread();
            var endings = 0;
            Listen(window, () => endings++, stop, patience: TimeSpan.FromSeconds(8));

            var clock = Stopwatch.StartNew();
            window.Send(SessionEnd.EndSession, 1, SessionEnd.CloseApp);
            Assert.IsTrue(clock.Elapsed < TimeSpan.FromSeconds(4), $"answered after {clock.Elapsed}");
            Assert.AreEqual(1, window.Run(() => endings));
        }
    }

    [TestMethod]
    public void TheAppClosesOnlyAfterWindowsIsAnswered()
    {
        using var window = new WindowThread();
        bool? insideEnd = null;
        var stopped = false;
        var stoppedAtEnding = false;
        Listen(window, () =>
        {
            insideEnd = WindowThread.InsideSentMessage();
            stoppedAtEnding = stopped;
        }, async () =>
        {
            await Task.Delay(100);
            stopped = true;
        });

        window.Send(SessionEnd.EndSession, 1, SessionEnd.CloseApp);

        Assert.AreEqual(((bool?)false, true), window.Run(() => (insideEnd, stoppedAtEnding)),
            "closing destroys the window Windows' message came to, so it waits for the answer, and finds the engine stopped");
    }

    [TestMethod]
    public void AnEngineThatDidNotStopKeepsAnOrdinaryQuitOpenButNotWindowsEnd()
    {
        using var window = new WindowThread();
        var listener = Listen(window, () => { });

        Assert.IsTrue(listener.Closes(engineStillRunning: false));
        Assert.IsFalse(listener.Closes(engineStillRunning: true), "Quit keeps the app open to say the engine did not stop");
        window.Send(SessionEnd.EndSession, 1, SessionEnd.CloseApp);
        Assert.IsTrue(listener.Closes(engineStillRunning: true), "Windows is ending the app; it closes regardless");
    }

    [TestMethod]
    public async Task AnOrdinaryQuitWaitsForTheEngineToStop()
    {
        using var window = new WindowThread();
        var listener = Listen(window, () => { }, patience: TimeSpan.FromMilliseconds(100));
        var stop = new TaskCompletionSource(TaskCreationOptions.RunContinuationsAsynchronously);

        var waiting = listener.AwaitStopAsync(stop.Task);
        await Task.Delay(500);
        Assert.IsFalse(waiting.IsCompleted, "without Windows ending the app, nothing cuts the engine's stop short");
        stop.SetResult();
        await waiting.WaitAsync(TimeSpan.FromSeconds(5));
    }

    [TestMethod]
    public async Task WindowsEndingTheAppBoundsAQuitAlreadyWaitingForTheEngine()
    {
        using var window = new WindowThread();
        var engine = new TaskCompletionSource(TaskCreationOptions.RunContinuationsAsynchronously);
        var listener = Listen(window, () => { }, () => engine.Task, patience: TimeSpan.FromMilliseconds(200));

        var waiting = listener.AwaitStopAsync(engine.Task);
        await Task.Delay(100);
        Assert.IsFalse(waiting.IsCompleted);
        var clock = Stopwatch.StartNew();
        window.Send(SessionEnd.EndSession, 1, SessionEnd.CloseApp);
        await waiting.WaitAsync(TimeSpan.FromSeconds(5));
        Assert.IsTrue(clock.Elapsed >= TimeSpan.FromMilliseconds(150), "the engine still gets the patience to stop cleanly");
        Assert.IsFalse(engine.Task.IsCompleted, "the quit went on without the engine's stop");
    }

    [TestMethod]
    public async Task AQuitUnderWayWhenWindowsEndsTheAppGoesOnOnlyAfterTheAnswer()
    {
        using var window = new WindowThread();
        var engine = new TaskCompletionSource(TaskCreationOptions.RunContinuationsAsynchronously);
        bool? insideEnd = null;
        var listener = Listen(window, () => { }, async () =>
        {
            // The engine stops while Windows waits for its answer.
            await Task.Delay(100);
            engine.TrySetResult();
        }, patience: TimeSpan.FromSeconds(8));

        // A Quit the person chose a moment earlier, waiting on the window's thread as the app's does.
        var quit = window.Run(async () =>
        {
            await listener.AwaitStopAsync(engine.Task);
            insideEnd = WindowThread.InsideSentMessage();
        });
        window.Send(SessionEnd.EndSession, 1, SessionEnd.CloseApp);
        await quit.WaitAsync(TimeSpan.FromSeconds(5));

        Assert.AreEqual<bool?>(false, window.Run(() => insideEnd), "the quit closes the window, so it must not go on inside Windows' message");
    }

    [TestMethod]
    public async Task AFailedStopStillReportsItsErrorWhenItEndsFirst()
    {
        using var window = new WindowThread();
        var listener = Listen(window, () => { });

        await Assert.ThrowsExactlyAsync<IOException>(() =>
            listener.AwaitStopAsync(Task.FromException(new IOException("The engine did not stop."))));
    }

    [TestMethod]
    public void TheAppIsAskedToEndBeforeTheEnginesProcesses()
    {
        using var window = new WindowThread();
        Listen(window, () => { });

        Assert.IsTrue(GetProcessShutdownParameters(out var level, out _));
        Assert.AreEqual(SessionEnd.ShutdownLevel, level);
        Assert.IsTrue(level > 0x280, "a process Windows was not told otherwise about ends at 0x280, after this one");
    }

    [DllImport("kernel32.dll")]
    private static extern bool GetProcessShutdownParameters(out uint level, out uint flags);
}

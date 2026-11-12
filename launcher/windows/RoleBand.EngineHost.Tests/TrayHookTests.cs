using System.ComponentModel;
using RoleBand.EngineHost;

namespace RoleBand.EngineHost.Tests;

/// <summary>
/// The notification-area icon's hook on a real top-level window with its own message loop, as the app's flyout has, with
/// the shell's add standing in: one the shell refuses, as it does at sign-in while Explorer starts, and one that throws.
/// An exception that left a window procedure would end the test run, as it ends the app.
/// </summary>
[TestClass]
public sealed class TrayHookTests
{
    private const uint Probe = 0x8000 + 21, GetTextLength = 0x000E;
    private static readonly uint TaskbarCreated = WindowThread.Message("TaskbarCreated");

    private static TrayHook Hook(WindowThread window, Func<bool> add, List<Exception>? failures = null, TimeSpan? retry = null) =>
        window.Run(() =>
        {
            var hook = new TrayHook(window.Window, add, Pass, failures is null ? null : new Action<Exception>(failures.Add), retry ?? TimeSpan.FromHours(1));
            window.OnDispose(hook.Dispose);
            return hook;
        });

    private static bool Pass(uint message, nint wParam, nint lParam, out nint result)
    {
        result = 0;
        return false;
    }

    private static async Task Until(Func<bool> condition, string what)
    {
        var clock = System.Diagnostics.Stopwatch.StartNew();
        while (!condition())
        {
            if (clock.Elapsed > TimeSpan.FromSeconds(10)) Assert.Fail($"Waited 10 seconds for {what}.");
            await Task.Delay(20);
        }
    }

    [TestMethod]
    public void AnIconTheShellRefusesAtSignInIsAddedWhenTheTaskbarIsCreated()
    {
        using var window = new WindowThread();
        var taskbar = false;
        var adds = 0;
        var appeared = 0;
        var hook = Hook(window, () => { adds++; return taskbar; });
        window.Run(() => hook.Appeared += () => appeared++);

        Assert.AreEqual((false, 1, 0), window.Run(() => (hook.Shown, adds, appeared)), "the app carries on without the icon");
        window.Run(() => taskbar = true);
        window.Send(TaskbarCreated, 0, 0);
        Assert.AreEqual((true, 2, 1), window.Run(() => (hook.Shown, adds, appeared)));

        // Explorer restarts and its new taskbar has no icons.
        window.Send(TaskbarCreated, 0, 0);
        Assert.AreEqual((true, 3, 2), window.Run(() => (hook.Shown, adds, appeared)));
    }

    [TestMethod]
    public async Task AnAddThatFailsIsTriedAgainUntilTheShellTakesIt()
    {
        using var window = new WindowThread();
        var adds = 0;
        var hook = Hook(window, () => ++adds >= 4, retry: TimeSpan.FromMilliseconds(20));

        await Until(() => window.Run(() => hook.Shown), "the fourth add");
        await Task.Delay(300);
        Assert.AreEqual(4, window.Run(() => adds), "the tries stop once the icon is there");
    }

    [TestMethod]
    public async Task TheTriesStopAfterTheirNumberAndTheTaskbarCanStillBringTheIcon()
    {
        using var window = new WindowThread();
        var taskbar = false;
        var adds = 0;
        var missing = 0;
        var hook = Hook(window, () => { adds++; return taskbar; }, retry: TimeSpan.FromMilliseconds(10));
        window.Run(() => hook.Missing += () => missing++);

        await Until(() => window.Run(() => adds) == 1 + TrayHook.Retries, "every try");
        await Task.Delay(300);
        Assert.AreEqual((false, 1 + TrayHook.Retries, 1), window.Run(() => (hook.Shown, adds, missing)),
            "the app hears once that the icon is gone for good, to show a window of its own");

        window.Run(() => taskbar = true);
        window.Send(TaskbarCreated, 0, 0);
        Assert.AreEqual((true, 1), window.Run(() => (hook.Shown, missing)));
    }

    [TestMethod]
    public void AnAddThatThrowsIsReportedAndNeverLeavesTheWindow()
    {
        using var window = new WindowThread();
        var failures = new List<Exception>();
        var refusing = true;
        var hook = Hook(window, () => refusing ? throw new Win32Exception(1460, "The shell did not answer in time.") : true, failures);

        Assert.AreEqual((false, 1), window.Run(() => (hook.Shown, failures.Count)));
        window.Send(TaskbarCreated, 0, 0);
        Assert.AreEqual((false, 2), window.Run(() => (hook.Shown, failures.Count)), "the window answered and the app runs on");

        window.Run(() => refusing = false);
        window.Send(TaskbarCreated, 0, 0);
        Assert.IsTrue(window.Run(() => hook.Shown));
    }

    [TestMethod]
    public void AHandlerThatThrowsLeavesTheMessageToTheWindow()
    {
        using var window = new WindowThread();
        var failures = new List<Exception>();
        window.Run(() =>
        {
            var hook = new WindowHook(window.Window, (uint message, nint wParam, nint lParam, out nint result) =>
            {
                result = 0;
                if (message == GetTextLength) throw new InvalidOperationException("A handler's own bug.");
                return false;
            }, failures.Add);
            window.OnDispose(hook.Dispose);
        });

        Assert.AreEqual(WindowThread.Title.Length, (int)window.Send(GetTextLength, 0, 0), "the window's own answer");
        Assert.AreEqual(1, window.Run(() => failures.Count));
    }

    [TestMethod]
    public void AHookNothingHoldsStillAnswersUntilItIsRemoved()
    {
        using var window = new WindowThread();
        var seen = 0;
        // As an owner that dropped its hook without disposing it: Windows still calls it.
        window.Run(() =>
        {
            _ = new WindowHook(window.Window, (uint message, nint wParam, nint lParam, out nint result) =>
            {
                result = 0;
                if (message == Probe) seen++;
                return false;
            });
        });
        for (var collection = 0; collection < 3; collection++)
        {
            GC.Collect();
            GC.WaitForPendingFinalizers();
        }

        window.Send(Probe, 0, 0);
        Assert.AreEqual(1, window.Run(() => seen));
    }

    [TestMethod]
    public void AHookDisposedInsideItsOwnHandlerSeesNothingMore()
    {
        using var window = new WindowThread();
        var seen = 0;
        WindowHook? hook = null;
        window.Run(() => hook = new WindowHook(window.Window, (uint message, nint wParam, nint lParam, out nint result) =>
        {
            result = 0;
            if (message != Probe) return false;
            seen++;
            hook!.Dispose();
            return false;
        }));

        window.Send(Probe, 0, 0);
        window.Send(Probe, 0, 0);
        GC.Collect();
        GC.WaitForPendingFinalizers();
        window.Send(Probe, 0, 0);
        Assert.AreEqual(1, window.Run(() => seen));
    }

    [TestMethod]
    public void NoIconIsAddedForAWindowTheHookCannotHear()
    {
        var adds = 0;

        Assert.ThrowsExactly<Win32Exception>(() => new TrayHook(0, () => { adds++; return true; }, Pass));
        Assert.AreEqual(0, adds, "an icon whose clicks reach no window would only mislead");
    }
}

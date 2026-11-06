using System.Diagnostics;
using Microsoft.VisualStudio.TestTools.UnitTesting;

namespace RoleBand.EngineHost.Tests;

// The native host's lease and the engine's Python leases exclude each other in both directions.
[TestClass]
public sealed class LeaseTests
{
    private static string Checkout()
    {
        var checkout = new DirectoryInfo(AppContext.BaseDirectory);
        while (!File.Exists(Path.Combine(checkout.FullName, "backend", "desktop.py")))
            checkout = checkout.Parent ?? throw new IOException("Source checkout not found.");
        return checkout.FullName;
    }

    private static Process Python(string checkout, params string[] arguments)
    {
        var start = new ProcessStartInfo(Path.Combine(checkout, "backend", ".venv", "Scripts", "python.exe"))
        {
            UseShellExecute = false, CreateNoWindow = true,
            RedirectStandardInput = true, RedirectStandardOutput = true, RedirectStandardError = true,
        };
        start.Environment["PYTHONPATH"] = Path.Combine(checkout, "backend");
        start.Environment["PYTHONDONTWRITEBYTECODE"] = "1";
        foreach (var argument in arguments) start.ArgumentList.Add(argument);
        return Process.Start(start) ?? throw new IOException("Python did not start.");
    }

    private static string State()
    {
        var state = Path.Combine(Path.GetTempPath(), "roleband-lease-tests", Guid.NewGuid().ToString("N"));
        PrivateStorage.EnsureDirectory(state);
        return state;
    }

    [TestMethod]
    public async Task HostRefusesToStartWhileAnOperatorCommandHoldsTheLeases()
    {
        var checkout = Checkout();
        var state = State();
        using var holder = Python(checkout, "-c",
            "import sys\nfrom pathlib import Path\nfrom tracker.platform.windows_leases import lifecycle_leases\n"
            + "with lifecycle_leases(Path(sys.argv[1])):\n    print('held', flush=True)\n    sys.stdin.read()\n", state);
        try
        {
            var ready = await holder.StandardOutput.ReadLineAsync();
            if (ready != "held")
            {
                holder.StandardInput.Close();
                Assert.Fail(await holder.StandardError.ReadToEndAsync());
            }
            await using var session = new EngineSession(new EngineConfiguration(state, state, "must-not-run.exe",
                "must-not-run.exe", "test", true, true));
            await session.StartAsync();
            Assert.AreEqual(EngineState.Attention, session.Snapshot.State);
            Assert.IsFalse(session.OwnsEngine);
            Assert.IsNull(session.Snapshot.ProcessId);
        }
        finally
        {
            holder.StandardInput.Close();
            await holder.WaitForExitAsync();
        }
        using var released = PrivateStorage.Lease(state, "desktop.lock");
    }

    [TestMethod]
    public async Task OperatorCommandRefusesWhileTheHostHoldsItsLease()
    {
        var checkout = Checkout();
        var state = State();
        var checkpoint = Path.Combine(Path.GetTempPath(), "roleband-lease-tests", Guid.NewGuid().ToString("N"));
        using (PrivateStorage.Lease(state, "desktop.lock"))
        {
            using var command = Python(checkout, "-I", "-B", Path.Combine(checkout, "backend", "desktop.py"), "--source",
                "recovery", "begin", "--state", state, "--checkpoint", checkpoint);
            command.StandardInput.Close();
            var errors = await command.StandardError.ReadToEndAsync();
            await command.WaitForExitAsync();
            Assert.AreNotEqual(0, command.ExitCode);
            StringAssert.Contains(errors, "desktop.lock is held by the RoleBand app");
        }
        Assert.IsFalse(Path.Exists(Path.Combine(state, "recovery")));
    }
}

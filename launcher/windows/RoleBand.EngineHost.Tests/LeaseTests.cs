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

    private readonly List<string> scratch = [];

    private string State()
    {
        var state = Scratch();
        PrivateStorage.EnsureDirectory(state);
        return state;
    }

    private string Scratch()
    {
        var path = Path.Combine(Path.GetTempPath(), "roleband-lease-tests", Guid.NewGuid().ToString("N"));
        scratch.Add(path);
        return path;
    }

    [TestCleanup]
    public void RemoveScratch()
    {
        foreach (var path in scratch)
            try { if (Directory.Exists(path)) Directory.Delete(path, recursive: true); }
            catch (Exception error) when (error is IOException or UnauthorizedAccessException) { }
    }

    /// <summary>The holder's first line, or a failure within a minute: a Python that hangs before printing fails the
    /// test instead of the job.</summary>
    private static async Task<string?> FirstLine(Process process) =>
        await process.StandardOutput.ReadLineAsync().WaitAsync(TimeSpan.FromMinutes(1));

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
            var ready = await FirstLine(holder);
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
            if (!holder.WaitForExit(TimeSpan.FromMinutes(1))) holder.Kill(entireProcessTree: true);
        }
        using var released = PrivateStorage.Lease(state, "desktop.lock");
    }

    [TestMethod]
    public async Task OperatorCommandRefusesWhileTheHostHoldsItsLease()
    {
        var checkout = Checkout();
        var state = State();
        var checkpoint = Scratch();
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

    [TestMethod]
    public void PrivateStateIsOwnedByTheAccountOrTheOwnerThisProcessGivesWhatItCreates()
    {
        var account = new System.Security.Principal.SecurityIdentifier("S-1-5-21-1-2-3-1001");
        var administrators = new System.Security.Principal.SecurityIdentifier(System.Security.Principal.WellKnownSidType.BuiltinAdministratorsSid, null);
        var stranger = new System.Security.Principal.SecurityIdentifier("S-1-5-21-1-2-3-1002");
        Assert.IsTrue(PrivateStorage.OwnedHere(account, account, account));
        Assert.IsTrue(PrivateStorage.OwnedHere(administrators, account, administrators), "elevated: what this process makes is the Administrators group's");
        Assert.IsFalse(PrivateStorage.OwnedHere(administrators, account, account), "not elevated: the Administrators group is someone else");
        Assert.IsFalse(PrivateStorage.OwnedHere(stranger, account, administrators));
        Assert.IsFalse(PrivateStorage.OwnedHere(null, account, account));
        var own = PrivateStorage.DefaultOwner;
        Assert.IsTrue(own.Equals(PrivateStorage.AccountSid) || own.Equals(administrators), own.Value);
    }

    [TestMethod]
    public void AJunctionIntoInstalledDataStillLeadsThere()
    {
        var root = Scratch();
        var installed = Path.Combine(root, "installed");
        Directory.CreateDirectory(installed);
        var trial = Junction(Path.Combine(root, "trial"), installed);
        try
        {
            Assert.IsTrue(EngineConfiguration.LeadsInto(Path.Combine(trial, "state", "not-yet"), installed), "the junction is followed");
            Assert.IsTrue(EngineConfiguration.LeadsInto(installed, installed));
            Assert.IsFalse(EngineConfiguration.LeadsInto(Path.Combine(root, "elsewhere", "state"), installed));
            Assert.IsFalse(EngineConfiguration.LeadsInto(Path.Combine(root, "installed-trials"), installed), "a shared name prefix is not inside");
        }
        finally
        {
            // Removing the junction itself leaves the folder it points to alone.
            Directory.Delete(trial);
        }
    }

    [TestMethod]
    public void ALongPathThroughAJunctionIsResolvedInFull()
    {
        var root = Scratch();
        var installed = Path.Combine(root, "installed");
        // Past MAX_PATH and past the first buffer GetFinalPathNameByHandle is offered.
        var deep = Path.Combine(Enumerable.Repeat(new string('d', 120), 10).ToArray());
        Directory.CreateDirectory(Path.Combine(installed, deep));
        var trial = Junction(Path.Combine(root, "trial"), installed);
        try
        {
            Assert.IsTrue(EngineConfiguration.LeadsInto(Path.Combine(trial, deep, "state"), installed));
            Assert.IsFalse(EngineConfiguration.LeadsInto(Path.Combine(trial, deep, "state"), Path.Combine(root, "elsewhere")));
        }
        finally
        {
            Directory.Delete(trial);
        }
    }

    [TestMethod]
    public void AJunctionThatLeadsNowhereIsRefusedRatherThanTakenAsWritten()
    {
        var root = Scratch();
        Directory.CreateDirectory(root);
        var installed = Path.Combine(root, "installed");
        var trial = Junction(Path.Combine(root, "trial"), installed);
        try
        {
            Assert.ThrowsExactly<IOException>(() => EngineConfiguration.LeadsInto(Path.Combine(trial, "state"), installed));
        }
        finally
        {
            Directory.Delete(trial);
        }
    }

    private static string Junction(string link, string target)
    {
        var mklink = new ProcessStartInfo("cmd.exe") { UseShellExecute = false, CreateNoWindow = true, RedirectStandardOutput = true };
        foreach (var argument in new[] { "/c", "mklink", "/J", link, target }) mklink.ArgumentList.Add(argument);
        using var made = Process.Start(mklink) ?? throw new IOException("mklink did not start.");
        made.WaitForExit();
        Assert.AreEqual(0, made.ExitCode, "the junction was made");
        return link;
    }
}

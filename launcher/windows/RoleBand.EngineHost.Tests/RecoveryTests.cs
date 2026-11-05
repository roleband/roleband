using System.Text.Json;
using Microsoft.VisualStudio.TestTools.UnitTesting;

namespace RoleBand.EngineHost.Tests;

[TestClass]
public sealed class RecoveryTests
{
    private static string Journal(string phase)
    {
        var state = Path.Combine(Path.GetTempPath(), "roleband-recovery-tests", Guid.NewGuid().ToString("N"));
        PrivateStorage.EnsureDirectory(state);
        PrivateStorage.EnsureDirectory(Path.Combine(state, "recovery"));
        File.WriteAllText(Path.Combine(state, "recovery", "check.json"), JsonSerializer.Serialize(new
        {
            format = 1, kind = "checkpoint-drill", state, phase,
            checkpoint = Path.Combine(state, "separate-checkpoint"),
            manifest_sha256 = new string('a', 64), archive_sha256 = new string('b', 64),
            attempts = new[] { Guid.NewGuid().ToString("N") },
        }));
        return state;
    }

    [TestMethod]
    [DataRow("verifying")]
    [DataRow("failed")]
    public async Task UnfinishedDrillStopsBeforeSpawningAndReleasesTheDesktopLease(string phase)
    {
        var state = Journal(phase);
        var config = new EngineConfiguration(state, state, "must-not-run.exe", "must-not-run.exe", "test", true, true);
        await using var session = new EngineSession(config);
        await session.StartAsync();
        Assert.AreEqual(EngineState.Attention, session.Snapshot.State);
        StringAssert.Contains(session.Snapshot.Diagnostic!, "recovery check is unfinished");
        Assert.IsNull(session.Snapshot.ProcessId);
        Assert.IsFalse(session.OwnsEngine);
        using var lease = PrivateStorage.Lease(state, "desktop.lock");
    }

    [TestMethod]
    [DataRow("verified")]
    [DataRow("abandoned")]
    public void ExplicitResolutionAllowsLaunchWithoutDeletingTheJournal(string phase)
    {
        var state = Journal(phase);
        RecoveryGuard.RequireLaunchable(state);
        Assert.IsTrue(File.Exists(Path.Combine(state, "recovery", "check.json")));
    }

    [TestMethod]
    [DataRow("{", false)]
    [DataRow("{}", false)]
    [DataRow("null", false)]
    [DataRow("[]", false)]
    [DataRow("unknown", true)]
    public void DamagedOrUnknownJournalCannotAuthorizeLaunch(string value, bool phase)
    {
        var state = Journal(value);
        if (!phase) File.WriteAllText(Path.Combine(state, "recovery", "check.json"), value);
        Assert.ThrowsExactly<IOException>(() => RecoveryGuard.RequireLaunchable(state));
        Assert.IsTrue(File.Exists(Path.Combine(state, "recovery", "check.json")));
    }
}

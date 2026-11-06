using System.Text.Json;
using Microsoft.VisualStudio.TestTools.UnitTesting;

namespace RoleBand.EngineHost.Tests;

[TestClass]
public sealed class RestoreTests
{
    private static string State()
    {
        var state = Path.Combine(Path.GetTempPath(), "roleband-restore-tests", Guid.NewGuid().ToString("N"));
        PrivateStorage.EnsureDirectory(state);
        return state;
    }

    private static object Metadata(string state, int minimum = 1) => new
    { format = 2, pgdata = Path.Combine(state, "db"), version = 16, minimum_reader = minimum };

    private static void Journal(string state, string phase)
    {
        PrivateStorage.EnsureDirectory(Path.Combine(state, "recovery"));
        File.WriteAllText(Path.Combine(state, "recovery", "restore.json"), JsonSerializer.Serialize(new
        {
            format = 1, kind = "checkpoint-restore", id = Guid.NewGuid().ToString("N"), state, phase,
            checkpoint = Path.Combine(Path.GetTempPath(), "retained-checkpoint"),
            manifest_sha256 = new string('a', 64), archive_sha256 = new string('b', 64),
            profile = new { owner = new string('c', 64), password = new string('d', 64), key = new string('e', 64) },
            original_metadata = Metadata(state, 2), original_directory = new[] { 1, 2 }, restored_directory = new[] { 1, 3 },
            attempts = new[] { Guid.NewGuid().ToString("N") },
        }));
    }

    [TestMethod]
    [DataRow("preparing")]
    [DataRow("prepared")]
    [DataRow("retaining")]
    [DataRow("installing")]
    [DataRow("checking")]
    public async Task IncompleteRestoreNeverSpawnsAnEngineAndReleasesTheLease(string phase)
    {
        var state = State();
        Journal(state, phase);
        await using var session = new EngineSession(new EngineConfiguration(state, state, "must-not-run.exe", "must-not-run.exe", "test", true, true));
        await session.StartAsync();
        Assert.AreEqual(EngineState.Attention, session.Snapshot.State);
        StringAssert.Contains(session.Snapshot.Diagnostic!, "restore is unfinished");
        Assert.IsNull(session.Snapshot.ProcessId);
        using var lease = PrivateStorage.Lease(state, "desktop.lock");
    }

    [TestMethod]
    [DataRow("complete")]
    [DataRow("aborted")]
    public void ResolvedRestoreAllowsLaunchAndRetainsEvidence(string phase)
    {
        var state = State();
        Journal(state, phase);
        RecoveryGuard.RequireLaunchable(state);
        Assert.IsTrue(File.Exists(Path.Combine(state, "recovery", "restore.json")));
    }

    [TestMethod]
    [DataRow("{")]
    [DataRow("{}")]
    [DataRow("null")]
    [DataRow("[]")]
    public void InvalidRestoreJournalCannotAuthorizeStartup(string payload)
    {
        var state = State();
        Journal(state, "complete");
        File.WriteAllText(Path.Combine(state, "recovery", "restore.json"), payload);
        Assert.ThrowsExactly<IOException>(() => RecoveryGuard.RequireLaunchable(state));
    }

    [TestMethod]
    public async Task NewerStorageIsRejectedBeforeEngineSpawnWithoutARecoveryJournal()
    {
        var state = State();
        PrivateStorage.EnsureDirectory(Path.Combine(state, "db.auth"));
        var marker = Path.Combine(state, "db.auth", "cluster.json");
        File.WriteAllText(marker, JsonSerializer.Serialize(Metadata(state, 2)));
        await using var session = new EngineSession(new EngineConfiguration(state, state, "must-not-run.exe", "must-not-run.exe", "test", true, true));
        await session.StartAsync();
        Assert.AreEqual(EngineState.Attention, session.Snapshot.State);
        StringAssert.Contains(session.Snapshot.Diagnostic!, "requires Windows reader contract 2");
        Assert.IsNull(session.Snapshot.ProcessId);
        File.WriteAllText(marker, JsonSerializer.Serialize(Metadata(state)));
        RecoveryGuard.RequireLaunchable(state);
    }
}

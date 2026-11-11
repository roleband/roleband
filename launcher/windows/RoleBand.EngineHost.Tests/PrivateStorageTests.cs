using Microsoft.VisualStudio.TestTools.UnitTesting;

namespace RoleBand.EngineHost.Tests;

// The engine publishes a record by renaming a finished file into place through a handle with write access, and
// keeps that handle until the rename is flushed. The native host can see the new name in that moment.
[TestClass]
public sealed class PrivateStorageTests
{
    private readonly List<string> scratch = [];

    [TestCleanup]
    public void Cleanup()
    {
        foreach (var folder in scratch)
            try { Directory.Delete(folder, recursive: true); }
            catch (IOException) { }
    }

    private string State()
    {
        var state = Path.Combine(Path.GetTempPath(), "roleband-private-tests", Guid.NewGuid().ToString("N"));
        scratch.Add(state);
        PrivateStorage.EnsureDirectory(state);
        return state;
    }

    [TestMethod]
    public void ARecordReadsWhileItsPublisherStillHoldsIt()
    {
        var record = Path.Combine(State(), "http-engine.json");
        PrivateStorage.Write(record, "{\"port\":1}"u8.ToArray());

        using (new FileStream(record, FileMode.Open, FileAccess.Write, FileShare.ReadWrite | FileShare.Delete))
            CollectionAssert.AreEqual("{\"port\":1}"u8.ToArray(), PrivateStorage.Read(record));
    }
}

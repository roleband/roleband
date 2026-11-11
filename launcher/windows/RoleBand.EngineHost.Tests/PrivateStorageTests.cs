using System.ComponentModel;
using System.Runtime.InteropServices;
using Microsoft.VisualStudio.TestTools.UnitTesting;
using Microsoft.Win32.SafeHandles;

namespace RoleBand.EngineHost.Tests;

// The engine publishes a record by renaming a finished file into place through a handle with write and delete
// access, and keeps that handle until the rename is flushed. The native host can see the new name in that moment.
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

        using (PublishersHandle(record))
            CollectionAssert.AreEqual("{\"port\":1}"u8.ToArray(), PrivateStorage.Read(record));
    }

    /// <summary>The handle the engine's publication keeps: write and delete access, sharing everything, as
    /// windows_fs._replace opens it. A reader must share both writing and deletion to open the record.</summary>
    private static SafeFileHandle PublishersHandle(string path)
    {
        const uint writeDelete = 0x40010000, shareAll = 0x7, openExisting = 3, normal = 0x80;
        var handle = CreateFile(path, writeDelete, shareAll, 0, openExisting, normal, 0);
        if (handle.IsInvalid) throw new Win32Exception(Marshal.GetLastWin32Error());
        return handle;
    }

    [DllImport("kernel32.dll", EntryPoint = "CreateFileW", CharSet = CharSet.Unicode, SetLastError = true)]
    private static extern SafeFileHandle CreateFile(string name, uint access, uint share, nint security, uint disposition,
        uint attributes, nint template);
}

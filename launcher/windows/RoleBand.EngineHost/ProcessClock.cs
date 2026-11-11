using System.Runtime.InteropServices;

namespace RoleBand.EngineHost;

public static class ProcessClock
{
    private const uint QueryLimitedInformation = 0x1000;
    private const uint Synchronize = 0x00100000;
    private const uint WaitTimeout = 0x102;

    /// <summary>
    /// A running process's start in Unix seconds, read from its UTC creation time, or null when
    /// it has exited or this account cannot query it. Local-time conversion is ambiguous for an
    /// hour each autumn; the creation FILETIME is not.
    /// </summary>
    public static double? RunningSince(int pid)
    {
        var handle = OpenProcess(QueryLimitedInformation | Synchronize, false, pid);
        if (handle == 0) return null;
        try
        {
            if (WaitForSingleObject(handle, 0) != WaitTimeout) return null;
            if (!GetProcessTimes(handle, out var created, out _, out _, out _)) return null;
            return (DateTime.FromFileTimeUtc(created) - DateTime.UnixEpoch).TotalSeconds;
        }
        finally { CloseHandle(handle); }
    }

    [DllImport("kernel32.dll", SetLastError = true)]
    private static extern nint OpenProcess(uint access, [MarshalAs(UnmanagedType.Bool)] bool inherit, int pid);
    [DllImport("kernel32.dll", SetLastError = true)]
    private static extern uint WaitForSingleObject(nint handle, uint milliseconds);
    [DllImport("kernel32.dll", SetLastError = true)]
    [return: MarshalAs(UnmanagedType.Bool)]
    private static extern bool GetProcessTimes(nint handle, out long created, out long exited, out long kernel, out long user);
    [DllImport("kernel32.dll")]
    [return: MarshalAs(UnmanagedType.Bool)]
    private static extern bool CloseHandle(nint handle);
}

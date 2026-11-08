using System.ComponentModel;
using System.Runtime.InteropServices;
using System.Text;

namespace RoleBand.EngineHost;

public static class PackageProcess
{
    private const string ContextArgument = "--package-process-tree";
    private const int NoPackage = 15700;
    private const int InsufficientBuffer = 122;
    private const nuint DesktopAppPolicy = 0x00020012;
    private const int PreservePackageTree = 2;
    private const uint ExtendedStartupInfoPresent = 0x00080000;

    /// <param name="extra">Arguments the relaunched process needs that its command line does not carry,
    /// such as how this one was activated.</param>
    public static bool RelaunchIfNeeded(params string[] extra)
    {
        uint length = 0;
        var identity = GetCurrentPackageFullName(ref length, 0);
        if (identity == NoPackage) return false;
        if (identity != InsufficientBuffer) throw new Win32Exception(identity);
        if (Environment.GetCommandLineArgs().Contains(ContextArgument)) return false;

        nuint size = 0;
        InitializeProcThreadAttributeList(0, 1, 0, ref size);
        var attributes = Marshal.AllocHGlobal(checked((int)size));
        var policy = Marshal.AllocHGlobal(sizeof(uint));
        var initialized = false;
        try
        {
            if (!InitializeProcThreadAttributeList(attributes, 1, 0, ref size)) throw Error();
            initialized = true;
            // Child processes otherwise break away and cannot execute files
            // protected by the package identity's conditional ACL.
            Marshal.WriteInt32(policy, PreservePackageTree);
            if (!UpdateProcThreadAttribute(attributes, 0, DesktopAppPolicy, policy, sizeof(uint), 0, 0)) throw Error();
            var startup = new StartupInfoEx
            {
                Info = new StartupInfo { Size = (uint)Marshal.SizeOf<StartupInfoEx>() },
                Attributes = attributes,
            };
            var command = new StringBuilder(Environment.CommandLine + " " + string.Join(" ", [.. extra, ContextArgument]));
            if (!CreateProcess(Environment.ProcessPath!, command, 0, 0, false, ExtendedStartupInfoPresent, 0, null, ref startup, out var process))
                throw Error();
            CloseHandle(process.Thread);
            CloseHandle(process.Process);
            return true;
        }
        finally
        {
            if (initialized) DeleteProcThreadAttributeList(attributes);
            Marshal.FreeHGlobal(policy);
            Marshal.FreeHGlobal(attributes);
        }
    }

    private static Win32Exception Error() => new(Marshal.GetLastWin32Error());

    [StructLayout(LayoutKind.Sequential)]
    private struct StartupInfo
    {
        public uint Size;
        public nint Reserved, Desktop, Title;
        public uint X, Y, Width, Height, XChars, YChars, Fill, Flags;
        public ushort ShowWindow, ReservedLength;
        public nint ReservedBytes, Input, Output, Error;
    }

    [StructLayout(LayoutKind.Sequential)]
    private struct StartupInfoEx { public StartupInfo Info; public nint Attributes; }

    [StructLayout(LayoutKind.Sequential)]
    private struct ProcessInfo { public nint Process, Thread; public uint ProcessId, ThreadId; }

    [DllImport("kernel32.dll", ExactSpelling = true)]
    private static extern int GetCurrentPackageFullName(ref uint length, nint name);
    [DllImport("kernel32.dll", SetLastError = true)]
    [return: MarshalAs(UnmanagedType.Bool)]
    private static extern bool InitializeProcThreadAttributeList(nint list, int count, uint flags, ref nuint size);
    [DllImport("kernel32.dll", SetLastError = true)]
    [return: MarshalAs(UnmanagedType.Bool)]
    private static extern bool UpdateProcThreadAttribute(nint list, uint flags, nuint attribute, nint value, nuint size, nint previous, nint returned);
    [DllImport("kernel32.dll")]
    private static extern void DeleteProcThreadAttributeList(nint list);
    [DllImport("kernel32.dll", EntryPoint = "CreateProcessW", CharSet = CharSet.Unicode, SetLastError = true)]
    [return: MarshalAs(UnmanagedType.Bool)]
    private static extern bool CreateProcess(string application, StringBuilder command, nint processAttributes, nint threadAttributes,
        [MarshalAs(UnmanagedType.Bool)] bool inherit, uint flags, nint environment, string? directory, ref StartupInfoEx startup, out ProcessInfo process);
    [DllImport("kernel32.dll")]
    [return: MarshalAs(UnmanagedType.Bool)]
    private static extern bool CloseHandle(nint handle);
}

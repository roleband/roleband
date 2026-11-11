using System.ComponentModel;
using System.Runtime.InteropServices;
using System.Security.AccessControl;
using System.Security.Principal;

namespace RoleBand.EngineHost;

public static class PrivateStorage
{
    public static SecurityIdentifier AccountSid
    {
        get
        {
            using var identity = WindowsIdentity.GetCurrent();
            return identity.User ?? throw new IOException("No Windows account identity is available.");
        }
    }

    /// <summary>The owner this process's token gives what it creates without naming an owner: the account itself,
    /// or the Administrators group for a token running elevated.</summary>
    public static SecurityIdentifier DefaultOwner
    {
        get
        {
            using var identity = WindowsIdentity.GetCurrent();
            return identity.Owner ?? AccountSid;
        }
    }

    /// <summary>Private state is owned by this account, or by the owner this process gives what it creates. An
    /// elevated administrator's files are owned by the Administrators group, which only administrators can act as;
    /// the access rules still admit no one but the account and SYSTEM.</summary>
    public static bool OwnedHere(SecurityIdentifier? owner, SecurityIdentifier account, SecurityIdentifier defaultOwner) =>
        owner is not null && (owner.Equals(account) || owner.Equals(defaultOwner));

    /// <summary>A private folder: created with access for this account and SYSTEM only, or checked to have no more.
    /// A missing parent is created private too; one made with inherited access would fail its own check later.</summary>
    public static void EnsureDirectory(string path)
    {
        path = Path.GetFullPath(path);
        var parent = Path.GetDirectoryName(path);
        if (parent is not null && !Directory.Exists(parent)) EnsureDirectory(parent);
        if (Directory.Exists(path)) { Verify(path, true); return; }
        var sddl = $"O:{AccountSid.Value}D:P(A;OICI;FA;;;{AccountSid.Value})(A;OICI;FA;;;SY)";
        if (!ConvertStringSecurityDescriptorToSecurityDescriptor(sddl, 1, out var descriptor, out _))
            throw new Win32Exception(Marshal.GetLastWin32Error());
        try
        {
            var attributes = new SecurityAttributes { Length = Marshal.SizeOf<SecurityAttributes>(), Descriptor = descriptor };
            if (!CreateDirectory(path, ref attributes) && Marshal.GetLastWin32Error() != 183)
                throw new Win32Exception(Marshal.GetLastWin32Error());
        }
        finally { LocalFree(descriptor); }
        Verify(path, true);
    }

    public static void Verify(string path, bool directory = false)
    {
        var attributes = File.GetAttributes(path);
        if ((attributes & FileAttributes.ReparsePoint) != 0 || ((attributes & FileAttributes.Directory) != 0) != directory)
            throw new IOException("Private state is not an ordinary file or directory.");
        FileSystemSecurity security = directory
            ? new DirectoryInfo(path).GetAccessControl(AccessControlSections.Owner | AccessControlSections.Access)
            : new FileInfo(path).GetAccessControl(AccessControlSections.Owner | AccessControlSections.Access);
        if (!OwnedHere(security.GetOwner(typeof(SecurityIdentifier)) as SecurityIdentifier, AccountSid, DefaultOwner))
            throw new IOException("Private state belongs to another account.");
        var rules = security.GetAccessRules(true, true, typeof(SecurityIdentifier));
        if (rules.Count == 0) throw new IOException("Private state has no restrictive ACL.");
        var system = new SecurityIdentifier(WellKnownSidType.LocalSystemSid, null);
        foreach (FileSystemAccessRule rule in rules)
            if (rule.AccessControlType != AccessControlType.Allow
                || (!AccountSid.Equals(rule.IdentityReference) && !system.Equals(rule.IdentityReference)))
                throw new IOException("Private state grants access to another account.");
    }

    public static byte[] Read(string path, int maximum = 8192)
    {
        Verify(Path.GetDirectoryName(path)!, true);
        Verify(path);
        using var file = new FileStream(path, FileMode.Open, FileAccess.Read, FileShare.Read | FileShare.Delete);
        if (file.Length > maximum) throw new IOException("Private state exceeds its size limit.");
        var bytes = new byte[checked((int)file.Length)];
        file.ReadExactly(bytes);
        return bytes;
    }

    /// <summary>Replaces a private file whole: the bytes go to a sibling first, which inherits the folder's
    /// restrictive ACL, and then take the file's name, so a reader never sees half a record.</summary>
    public static void Write(string path, byte[] bytes)
    {
        var folder = Path.GetDirectoryName(path)!;
        Verify(folder, true);
        if (File.Exists(path)) Verify(path);
        var temporary = path + ".new";
        File.WriteAllBytes(temporary, bytes);
        Verify(temporary);
        File.Move(temporary, path, overwrite: true);
    }

    public static FileStream Lease(string state, string name)
    {
        EnsureDirectory(state);
        var folder = Path.Combine(state, "launcher");
        EnsureDirectory(folder);
        var path = Path.Combine(folder, name);
        if (File.Exists(path)) Verify(path);
        return new FileStream(path, FileMode.OpenOrCreate, FileAccess.ReadWrite, FileShare.None);
    }

    [StructLayout(LayoutKind.Sequential)]
    private struct SecurityAttributes
    {
        public int Length;
        public nint Descriptor;
        public int Inherit;
    }

    [DllImport("advapi32.dll", EntryPoint = "ConvertStringSecurityDescriptorToSecurityDescriptorW", CharSet = CharSet.Unicode, SetLastError = true)]
    [return: MarshalAs(UnmanagedType.Bool)]
    private static extern bool ConvertStringSecurityDescriptorToSecurityDescriptor(string text, uint revision, out nint descriptor, out uint size);

    [DllImport("kernel32.dll", EntryPoint = "CreateDirectoryW", CharSet = CharSet.Unicode, SetLastError = true)]
    [return: MarshalAs(UnmanagedType.Bool)]
    private static extern bool CreateDirectory(string path, ref SecurityAttributes attributes);

    [DllImport("kernel32.dll")]
    private static extern nint LocalFree(nint memory);
}

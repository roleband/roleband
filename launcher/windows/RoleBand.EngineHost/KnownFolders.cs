using System.Runtime.InteropServices;

namespace RoleBand.EngineHost;

public static class KnownFolders
{
    private const uint NoPackageRedirection = 0x00010000;
    public static string LocalAppData
    {
        get
        {
            var folder = new Guid("F1B32785-6FBA-4FCF-9D55-7B8E7F157091");
            var result = SHGetKnownFolderPath(ref folder, NoPackageRedirection, 0, out var value);
            try
            {
                Marshal.ThrowExceptionForHR(result);
                var path = Marshal.PtrToStringUni(value);
                if (path is null || !Path.IsPathFullyQualified(path)) throw new IOException("LocalAppData lookup failed.");
                return path;
            }
            finally { Marshal.FreeCoTaskMem(value); }
        }
    }

    [DllImport("shell32.dll", ExactSpelling = true)]
    private static extern int SHGetKnownFolderPath(ref Guid folder, uint flags, nint token, out nint path);
}

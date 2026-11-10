using System.IO.Compression;
using System.Runtime.InteropServices;
using System.Security.Cryptography;
using System.Security.Cryptography.X509Certificates;
using System.Security.Principal;
using System.Text.Json;
using System.Xml.Linq;
using Microsoft.Win32;

namespace RoleBand.EngineHost;

/// <summary>The release a Setup program installs: its version, the feed it comes from, RoleBand's package name and
/// publisher, and the certificate that signs it. Setup carries all of it, compiled in.</summary>
public sealed record InstallRelease(string Version, string Feed, string PackageName, string Publisher, byte[] Certificate)
{
    public string PackageFile => $"RoleBand-{Version}-Windows-x64.msix";
    public string MetadataFile => $"RoleBand-{Version}-Windows-x64.json";

    /// <summary>Where a file of this release is downloaded from.</summary>
    public Uri Download(string file) => new($"https://github.com/{Feed}/releases/download/v{Version}/{file}");

    /// <summary>The release named by an update identity (<c>release-identity.json</c>) and the certificate beside it.</summary>
    public static InstallRelease Read(string version, string identity, byte[] certificate)
    {
        using var document = JsonDocument.Parse(identity);
        var root = document.RootElement;
        string Field(string name) =>
            root.TryGetProperty(name, out var value) && value.ValueKind == JsonValueKind.String && value.GetString() is { Length: > 0 } text
                ? text : throw new InvalidDataException($"The release identity names no {name}.");
        if (!System.Text.RegularExpressions.Regex.IsMatch(version, @"^\d+\.\d+\.\d+$"))
            throw new InvalidDataException($"{version} is not a release version.");
        return new InstallRelease(version, Field("feed"), Field("package_name"), Field("publisher"), certificate);
    }
}

/// <summary>Why Setup cannot install RoleBand on this PC.</summary>
public enum InstallStop
{
    /// <summary>Windows before Windows 11, which RoleBand does not run on.</summary>
    NeedsWindows11,
    /// <summary>Setup was started with administrator rights as an account other than the one signed in: RoleBand would be
    /// installed for that account.</summary>
    OtherAccount,
    /// <summary>A policy lets this PC install only Microsoft Store apps.</summary>
    StoreOnly,
}

/// <summary>What Setup reads about this PC before it asks for anything.</summary>
/// <param name="Build">Windows' build number.</param>
/// <param name="OtherAccount">Setup runs with administrator rights as an account other than the one signed in.</param>
/// <param name="StoreOnly">A policy turns off installing apps from outside the Microsoft Store.</param>
public sealed record InstallFacts(int Build, bool OtherAccount, bool StoreOnly)
{
    /// <summary>The first Windows 11 build, the oldest RoleBand's package installs on.</summary>
    public const int Windows11 = 22000;

    public InstallStop? Stop =>
        Build < Windows11 ? InstallStop.NeedsWindows11
        : OtherAccount ? InstallStop.OtherAccount
        : StoreOnly ? InstallStop.StoreOnly
        : null;

    public static InstallFacts Read() => new(Environment.OSVersion.Version.Build, RunsAsOtherAccount(), StoreAppsOnly());

    /// <summary>Whether this process runs as an account other than the owner of the signed-in desktop's shell, which is
    /// what Run as administrator with another account's password gives.</summary>
    private static bool RunsAsOtherAccount()
    {
        var shell = GetShellWindow();
        if (shell == 0 || GetWindowThreadProcessId(shell, out var pid) == 0) return false;
        using var process = System.Diagnostics.Process.GetProcessById((int)pid);
        if (!OpenProcessToken(process.Handle, TokenQuery, out var token)) return false;
        try
        {
            using var owner = new WindowsIdentity(token);
            using var current = WindowsIdentity.GetCurrent();
            return owner.User is { } desktop && current.User is { } running && desktop != running;
        }
        finally { CloseHandle(token); }
    }

    /// <summary>The "Allow all trusted apps to install" policy turned off: only Store apps install.</summary>
    private static bool StoreAppsOnly()
    {
        using var policy = Registry.LocalMachine.OpenSubKey(@"SOFTWARE\Policies\Microsoft\Windows\Appx");
        return policy?.GetValue("AllowAllTrustedApps") is int allowed && allowed == 0;
    }

    private const uint TokenQuery = 0x0008;

    [DllImport("user32.dll")]
    private static extern nint GetShellWindow();

    [DllImport("user32.dll")]
    private static extern uint GetWindowThreadProcessId(nint window, out uint processId);

    [DllImport("advapi32.dll", SetLastError = true)]
    [return: MarshalAs(UnmanagedType.Bool)]
    private static extern bool OpenProcessToken(nint process, uint access, out nint token);

    [DllImport("kernel32.dll")]
    [return: MarshalAs(UnmanagedType.Bool)]
    private static extern bool CloseHandle(nint handle);
}

/// <summary>Trusting RoleBand's publisher: its certificate in Trusted People, where Windows looks for the signer of a
/// package it installs.</summary>
public static class PublisherTrust
{
    private const string CodeSigning = "1.3.6.1.5.5.7.3.3";

    /// <summary>The release's certificate, once it is one that may be trusted this way: the release's publisher, for code
    /// signing only, and no certificate authority, so it vouches for nothing it did not sign itself.</summary>
    public static X509Certificate2 Certificate(InstallRelease release)
    {
        var certificate = X509CertificateLoader.LoadCertificate(release.Certificate);
        var authority = certificate.Extensions.OfType<X509BasicConstraintsExtension>().Any(constraints => constraints.CertificateAuthority);
        var usage = certificate.Extensions.OfType<X509EnhancedKeyUsageExtension>().SingleOrDefault();
        var signsCode = usage is not null && usage.EnhancedKeyUsages.Count == 1 && usage.EnhancedKeyUsages[0].Value == CodeSigning;
        if (certificate.Subject != release.Publisher || authority || !signsCode)
            throw new InvalidDataException("The certificate is not RoleBand's code-signing certificate.");
        return certificate;
    }

    /// <summary>Adds the certificate to <paramref name="store"/>, which Setup opens as the machine's Trusted People; false
    /// when it is already there.</summary>
    public static bool Trust(X509Store store, X509Certificate2 certificate)
    {
        store.Open(OpenFlags.ReadWrite);
        if (store.Certificates.Find(X509FindType.FindByThumbprint, certificate.Thumbprint, false).Count > 0) return false;
        store.Add(certificate);
        return true;
    }
}

/// <summary>A release file that is not what Setup was built to install.</summary>
public sealed class NotTheRelease(string reason) : IOException(reason);

/// <summary>Downloads a release's package and refuses it unless it is that release's: its size and SHA-256 those of
/// the release's metadata, its manifest naming the release's package, publisher and version.</summary>
/// <param name="handler">Sends the requests; redirects are followed here, only to GitHub's own hosts.</param>
public sealed class ReleaseDownload(HttpMessageHandler handler)
{
    /// <summary>The hosts a release file is read from: the release page and GitHub's file host it redirects to.</summary>
    private static readonly string[] Hosts = ["github.com", "release-assets.githubusercontent.com"];
    private const int RedirectLimit = 5, MetadataLimit = 64 * 1024;
    private const long PackageLimit = 2L * 1024 * 1024 * 1024;

    /// <summary>The verified package, downloaded into <paramref name="folder"/>.</summary>
    /// <param name="progress">Told the bytes received and the package's size.</param>
    public async Task<string> PackageAsync(InstallRelease release, string folder, IProgress<(long Received, long Total)>? progress,
                                           CancellationToken cancellation)
    {
        using var client = new HttpClient(handler, disposeHandler: false) { Timeout = Timeout.InfiniteTimeSpan };
        client.DefaultRequestHeaders.UserAgent.ParseAdd("RoleBand-Setup");
        var (size, sha256) = Metadata(release, await ReadAsync(client, release.Download(release.MetadataFile), MetadataLimit, cancellation));
        Directory.CreateDirectory(folder);
        var package = Path.Combine(folder, release.PackageFile);
        var partial = package + ".partial";
        using (var response = await FollowAsync(client, release.Download(release.PackageFile), cancellation))
        await using (var source = await response.Content.ReadAsStreamAsync(cancellation))
        await using (var target = File.Create(partial))
        {
            using var hash = IncrementalHash.CreateHash(HashAlgorithmName.SHA256);
            var buffer = new byte[1 << 16];
            long received = 0;
            int read;
            while ((read = await source.ReadAsync(buffer, cancellation)) > 0)
            {
                received += read;
                if (received > size) throw new NotTheRelease("The package is larger than its release says.");
                hash.AppendData(buffer, 0, read);
                await target.WriteAsync(buffer.AsMemory(0, read), cancellation);
                progress?.Report((received, size));
            }
            if (received != size || Convert.ToHexStringLower(hash.GetHashAndReset()) != sha256)
                throw new NotTheRelease("The package is not the one its release names.");
        }
        Manifest(release, partial);
        File.Move(partial, package, overwrite: true);
        return package;
    }

    /// <summary>The package's size and SHA-256, from a release metadata file that names this release.</summary>
    public static (long Size, string Sha256) Metadata(InstallRelease release, byte[] metadata)
    {
        try
        {
            using var document = JsonDocument.Parse(metadata);
            var root = document.RootElement;
            string? Text(string name) => root.TryGetProperty(name, out var value) && value.ValueKind == JsonValueKind.String ? value.GetString() : null;
            var expected = new Dictionary<string, string>
            {
                ["platform"] = "windows", ["version"] = release.Version, ["feed"] = release.Feed, ["package"] = release.PackageFile,
                ["package_name"] = release.PackageName, ["publisher"] = release.Publisher,
            };
            var differs = expected.FirstOrDefault(field => Text(field.Key) != field.Value);
            if (differs.Key is not null) throw new NotTheRelease($"The release's metadata names another {differs.Key}.");
            var sha256 = Text("sha256");
            if (sha256 is null || !System.Text.RegularExpressions.Regex.IsMatch(sha256, "^[0-9a-f]{64}$")
                || !root.TryGetProperty("bytes", out var bytes) || !bytes.TryGetInt64(out var size) || size <= 0 || size > PackageLimit)
                throw new NotTheRelease("The release's metadata gives no package size or SHA-256.");
            return (size, sha256);
        }
        catch (JsonException error) { throw new NotTheRelease("The release's metadata is not readable: " + error.Message); }
    }

    /// <summary>Refuses a package whose manifest is not the release's package, by its name, publisher and version.</summary>
    public static void Manifest(InstallRelease release, string package)
    {
        try
        {
            using var archive = ZipFile.OpenRead(package);
            var entry = archive.GetEntry("AppxManifest.xml") ?? throw new NotTheRelease("The package has no manifest.");
            using var stream = entry.Open();
            var identity = XDocument.Load(stream).Root?.Elements().FirstOrDefault(element => element.Name.LocalName == "Identity");
            if (identity?.Attribute("Name")?.Value != release.PackageName || identity.Attribute("Publisher")?.Value != release.Publisher
                || identity.Attribute("Version")?.Value != release.Version + ".0")
                throw new NotTheRelease("The package states another name, publisher or version.");
        }
        catch (InvalidDataException) { throw new NotTheRelease("The package is not readable."); }
        catch (System.Xml.XmlException) { throw new NotTheRelease("The package's manifest is not readable."); }
    }

    private static async Task<byte[]> ReadAsync(HttpClient client, Uri uri, int limit, CancellationToken cancellation)
    {
        using var response = await FollowAsync(client, uri, cancellation);
        await using var stream = await response.Content.ReadAsStreamAsync(cancellation);
        using var memory = new MemoryStream();
        var buffer = new byte[8192];
        int read;
        while ((read = await stream.ReadAsync(buffer, cancellation)) > 0)
        {
            if (memory.Length + read > limit) throw new NotTheRelease("The release's metadata is too large.");
            memory.Write(buffer, 0, read);
        }
        return memory.ToArray();
    }

    /// <summary>The response for <paramref name="uri"/>, following redirects only over HTTPS to GitHub's own hosts. A
    /// release file that is not there is <see cref="HttpRequestException"/> with its status.</summary>
    private static async Task<HttpResponseMessage> FollowAsync(HttpClient client, Uri uri, CancellationToken cancellation)
    {
        for (var hop = 0; hop <= RedirectLimit; hop++)
        {
            if (uri.Scheme != Uri.UriSchemeHttps || !Hosts.Contains(uri.Host, StringComparer.OrdinalIgnoreCase))
                throw new NotTheRelease($"A release file is served from {uri.Host}, not GitHub.");
            var response = await client.GetAsync(uri, HttpCompletionOption.ResponseHeadersRead, cancellation);
            if ((int)response.StatusCode is >= 300 and < 400 && response.Headers.Location is { } next)
            {
                response.Dispose();
                uri = next.IsAbsoluteUri ? next : new Uri(uri, next);
                continue;
            }
            if (!response.IsSuccessStatusCode)
            {
                var status = response.StatusCode;
                response.Dispose();
                throw new HttpRequestException($"A release file answered {(int)status}.", null, status);
            }
            return response;
        }
        throw new HttpRequestException("A release file redirected too many times.");
    }
}

/// <summary>Windows' own verdict on a signed file: the signer's certificate when the signature is valid and its signer
/// trusted on this PC, otherwise null.</summary>
public static class WindowsSignature
{
    public static byte[]? Signer(string path)
    {
        var action = new Guid("00AAC56B-CD44-11d0-8CC2-00C04FC295EE");
        var file = new FileInfo { Size = (uint)Marshal.SizeOf<FileInfo>(), Path = Marshal.StringToHGlobalUni(path) };
        var fileInfo = Marshal.AllocHGlobal(Marshal.SizeOf<FileInfo>());
        var data = new TrustData { Size = (uint)Marshal.SizeOf<TrustData>(), UiChoice = 2, UnionChoice = 1, StateAction = 1 };
        try
        {
            Marshal.StructureToPtr(file, fileInfo, false);
            data.File = fileInfo;
            var verdict = WinVerifyTrust(-1, ref action, ref data);
            try
            {
                if (verdict != 0) return null;
                var provider = WTHelperProvDataFromStateData(data.State);
                var signer = provider == 0 ? 0 : WTHelperGetProvSignerFromChain(provider, 0, false, 0);
                if (signer == 0) return null;
                // CRYPT_PROVIDER_SGNR: the chain's count at 12 and its first certificate's entry at 16 on x64;
                // CRYPT_PROVIDER_CERT: the CERT_CONTEXT at 8; CERT_CONTEXT: the encoded certificate at 8, its length at 16.
                if (Marshal.ReadInt32(signer, 12) < 1) return null;
                var chain = Marshal.ReadIntPtr(signer, 16);
                var context = Marshal.ReadIntPtr(chain, 8);
                var encoded = Marshal.ReadIntPtr(context, 8);
                var length = Marshal.ReadInt32(context, 16);
                var certificate = new byte[length];
                Marshal.Copy(encoded, certificate, 0, length);
                return certificate;
            }
            finally
            {
                data.StateAction = 2;
                _ = WinVerifyTrust(-1, ref action, ref data);
            }
        }
        finally
        {
            Marshal.FreeHGlobal(fileInfo);
            Marshal.FreeHGlobal(file.Path);
        }
    }

    [StructLayout(LayoutKind.Sequential)]
    private struct FileInfo
    {
        public uint Size;
        public nint Path;
        public nint Handle;
        public nint KnownSubject;
    }

    [StructLayout(LayoutKind.Sequential)]
    private struct TrustData
    {
        public uint Size;
        public nint PolicyCallbackData;
        public nint SipClientData;
        public uint UiChoice;
        public uint RevocationChecks;
        public uint UnionChoice;
        public nint File;
        public uint StateAction;
        public nint State;
        public nint UrlReference;
        public uint ProviderFlags;
        public uint UiContext;
        public nint SignatureSettings;
    }

    [DllImport("wintrust.dll", CharSet = CharSet.Unicode)]
    private static extern int WinVerifyTrust(nint window, ref Guid action, ref TrustData data);

    [DllImport("wintrust.dll")]
    private static extern nint WTHelperProvDataFromStateData(nint state);

    [DllImport("wintrust.dll")]
    private static extern nint WTHelperGetProvSignerFromChain(nint provider, uint signer, [MarshalAs(UnmanagedType.Bool)] bool counterSigner,
                                                              uint counterSignerIndex);
}

/// <summary>RoleBand as Windows has it installed for this person.</summary>
public static class InstalledRoleBand
{
    /// <summary>The installed version, "major.minor.build", or null when RoleBand is not installed for this person.</summary>
    public static string? Version(InstallRelease release)
    {
        var package = Find(release);
        return package is null ? null : $"{package.Id.Version.Major}.{package.Id.Version.Minor}.{package.Id.Version.Build}";
    }

    /// <summary>Opens the installed RoleBand; false when it is not installed.</summary>
    public static async Task<bool> OpenAsync(InstallRelease release)
    {
        var entry = Find(release)?.GetAppListEntries().FirstOrDefault();
        return entry is not null && await entry.LaunchAsync();
    }

    private static Windows.ApplicationModel.Package? Find(InstallRelease release) =>
        new Windows.Management.Deployment.PackageManager().FindPackagesForUser(string.Empty, release.PackageName, release.Publisher)
            .OrderByDescending(package => package.Id.Version.Major).ThenByDescending(package => package.Id.Version.Minor)
            .ThenByDescending(package => package.Id.Version.Build).FirstOrDefault();

    /// <summary>Whether <paramref name="installed"/> is <paramref name="version"/> or newer.</summary>
    public static bool AtLeast(string installed, string version) =>
        System.Version.Parse(installed) >= System.Version.Parse(version);
}

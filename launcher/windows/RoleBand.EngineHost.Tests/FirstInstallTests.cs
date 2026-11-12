using System.IO.Compression;
using System.Net;
using System.Security.Cryptography;
using System.Security.Cryptography.X509Certificates;
using System.Text;
using System.Text.Json;
using Microsoft.VisualStudio.TestTools.UnitTesting;

namespace RoleBand.EngineHost.Tests;

/// <summary>A first install through Setup: what stops it, which certificate it may trust, and that it installs only the
/// release it was built for.</summary>
[TestClass]
public sealed class FirstInstallTests
{
    private const string Publisher = "CN=RoleBand, O=RoleBand, DC=roleband, DC=com";

    private static X509Certificate2 Signing(string subject = Publisher, bool authority = false, string usage = "1.3.6.1.5.5.7.3.3")
    {
        using var key = RSA.Create(2048);
        var request = new CertificateRequest(subject, key, HashAlgorithmName.SHA256, RSASignaturePadding.Pkcs1);
        request.CertificateExtensions.Add(new X509BasicConstraintsExtension(authority, false, 0, true));
        request.CertificateExtensions.Add(new X509EnhancedKeyUsageExtension([new Oid(usage)], false));
        return request.CreateSelfSigned(DateTimeOffset.UtcNow.AddDays(-1), DateTimeOffset.UtcNow.AddYears(1));
    }

    private static InstallRelease Release(byte[]? certificate = null) =>
        new("0.1.25", "roleband/roleband", "RoleBand.RoleBand", Publisher, certificate ?? Signing().RawData);

    [TestMethod]
    public void SetupStopsWhereRoleBandCannotBeInstalledForThePersonAndNowhereElse()
    {
        Assert.AreEqual(InstallStop.NeedsWindows11, new InstallFacts(19045, false, false).Stop, "Windows 10 22H2");
        Assert.AreEqual(InstallStop.NeedsWindows11, new InstallFacts(21999, true, true).Stop);
        Assert.AreEqual(InstallStop.OtherAccount, new InstallFacts(26200, true, false).Stop);
        Assert.AreEqual(InstallStop.StoreOnly, new InstallFacts(22000, false, true).Stop);
        Assert.IsNull(new InstallFacts(InstallFacts.Windows11, false, false).Stop);
        Assert.IsNull(new InstallFacts(26200, false, false).Stop);
    }

    [TestMethod]
    public void TheReleaseComesFromTheIdentitySetupWasBuiltWith()
    {
        var identity = """{"format": 1, "feed": "roleband/roleband", "release_public_key": "x", "package_name": "RoleBand.RoleBand", "publisher": "CN=RoleBand, O=RoleBand, DC=roleband, DC=com"}""";
        var release = InstallRelease.Read("0.1.25", identity, [1, 2]);
        Assert.AreEqual("roleband/roleband", release.Feed);
        Assert.AreEqual("RoleBand.RoleBand", release.PackageName);
        Assert.AreEqual(Publisher, release.Publisher);
        Assert.AreEqual(new Uri("https://github.com/roleband/roleband/releases/download/v0.1.25/RoleBand-0.1.25-Windows-x64.msix"),
            release.Download(release.PackageFile));
        Assert.ThrowsExactly<InvalidDataException>(() => InstallRelease.Read("0.2.0-dev", identity, [1]));
        Assert.ThrowsExactly<InvalidDataException>(() => InstallRelease.Read("0.1.25", """{"feed": "roleband/roleband"}""", [1]));
    }

    [TestMethod]
    public void OnlyRoleBandsOwnCodeSigningCertificateIsTrusted()
    {
        using var good = Signing();
        Assert.AreEqual(good.Thumbprint, PublisherTrust.Certificate(Release(good.RawData)).Thumbprint);
        using var authority = Signing(authority: true);
        using var other = Signing("CN=Someone Else");
        using var server = Signing(usage: "1.3.6.1.5.5.7.3.1");
        foreach (var refused in new[] { authority, other, server })
            Assert.ThrowsExactly<InvalidDataException>(() => PublisherTrust.Certificate(Release(refused.RawData)), refused.Subject);
    }

    [TestMethod]
    public void TrustingAddsTheCertificateOnceAndAgainChangesNothing()
    {
        using var certificate = Signing();
        // A store of the tests' own, never one Windows reads for trust.
        using var store = new X509Store("RoleBandFirstInstallTests", StoreLocation.CurrentUser);
        try
        {
            Assert.IsTrue(PublisherTrust.Trust(store, certificate));
            Assert.IsFalse(PublisherTrust.Trust(store, certificate));
            Assert.AreEqual(1, store.Certificates.Find(X509FindType.FindByThumbprint, certificate.Thumbprint, false).Count);
        }
        finally
        {
            store.Open(OpenFlags.ReadWrite);
            store.RemoveRange(store.Certificates);
        }
    }

    /// <summary>GitHub's release download: the page redirects to the file host, which serves the file.</summary>
    private sealed class Feed(Dictionary<string, byte[]> files, string fileHost = "release-assets.githubusercontent.com") : HttpMessageHandler
    {
        public List<Uri> Asked { get; } = [];

        protected override Task<HttpResponseMessage> SendAsync(HttpRequestMessage request, CancellationToken cancellation)
        {
            var uri = request.RequestUri!;
            Asked.Add(uri);
            var name = uri.Segments[^1];
            if (uri.Host == "github.com")
            {
                var moved = new HttpResponseMessage(HttpStatusCode.Found);
                moved.Headers.Location = new Uri($"https://{fileHost}/files/{name}");
                return Task.FromResult(moved);
            }
            return Task.FromResult(files.TryGetValue(name, out var bytes)
                ? new HttpResponseMessage(HttpStatusCode.OK) { Content = new ByteArrayContent(bytes) }
                : new HttpResponseMessage(HttpStatusCode.NotFound));
        }
    }

    private static byte[] Package(string version = "0.1.25.0", string name = "RoleBand.RoleBand")
    {
        using var memory = new MemoryStream();
        using (var archive = new ZipArchive(memory, ZipArchiveMode.Create, leaveOpen: true))
        {
            using var writer = new StreamWriter(archive.CreateEntry("AppxManifest.xml").Open());
            writer.Write($"""<Package xmlns="http://schemas.microsoft.com/appx/manifest/foundation/windows10"><Identity Name="{name}" Publisher="{Publisher}" Version="{version}" ProcessorArchitecture="x64" /></Package>""");
        }
        return memory.ToArray();
    }

    private static byte[] Metadata(InstallRelease release, byte[] package, Action<Dictionary<string, object>>? change = null)
    {
        var fields = new Dictionary<string, object>
        {
            ["format"] = 1, ["platform"] = "windows", ["version"] = release.Version, ["feed"] = release.Feed,
            ["package"] = release.PackageFile, ["package_name"] = release.PackageName, ["publisher"] = release.Publisher,
            ["sha256"] = Convert.ToHexStringLower(SHA256.HashData(package)), ["bytes"] = package.LongLength,
        };
        change?.Invoke(fields);
        return Encoding.UTF8.GetBytes(JsonSerializer.Serialize(fields));
    }

    private static string Folder() => Path.Combine(Path.GetTempPath(), "roleband-first-install", Guid.NewGuid().ToString("N"));

    private static async Task<string> DownloadAsync(InstallRelease release, Dictionary<string, byte[]> files, string folder,
                                                    string fileHost = "release-assets.githubusercontent.com")
    {
        using var feed = new Feed(files, fileHost);
        return await new ReleaseDownload(feed).PackageAsync(release, folder, null, CancellationToken.None);
    }

    [TestMethod]
    public async Task TheReleasesOwnPackageIsDownloadedThroughGitHubsFileHostAndKept()
    {
        var release = Release();
        var package = Package();
        var folder = Folder();
        try
        {
            var seen = new List<(long, long)>();
            using var feed = new Feed(new() { [release.MetadataFile] = Metadata(release, package), [release.PackageFile] = package });
            var path = await new ReleaseDownload(feed).PackageAsync(release, folder, new Synchronous(seen.Add), CancellationToken.None);
            CollectionAssert.AreEqual(package, File.ReadAllBytes(path));
            Assert.AreEqual(release.PackageFile, Path.GetFileName(path));
            Assert.AreEqual(1, Directory.GetFiles(folder).Length, "no partial file is left beside it");
            Assert.AreEqual((package.LongLength, package.LongLength), seen[^1]);
            Assert.IsTrue(feed.Asked.Any(uri => uri.Host == "release-assets.githubusercontent.com"));
        }
        finally { if (Directory.Exists(folder)) Directory.Delete(folder, true); }
    }

    [TestMethod]
    public async Task APackageThatIsNotTheReleasesIsNeverKept()
    {
        var release = Release();
        var package = Package();
        var cases = new (string Why, Dictionary<string, byte[]> Files)[]
        {
            ("another file than the metadata names", new() { [release.MetadataFile] = Metadata(release, package), [release.PackageFile] = Package("0.1.24.0") }),
            ("metadata for another version", new() { [release.MetadataFile] = Metadata(release, package, fields => fields["version"] = "0.1.24"), [release.PackageFile] = package }),
            ("metadata for another feed", new() { [release.MetadataFile] = Metadata(release, package, fields => fields["feed"] = "someone/else"), [release.PackageFile] = package }),
            ("a package larger than its metadata says", new() { [release.MetadataFile] = Metadata(release, package, fields => fields["bytes"] = 10L), [release.PackageFile] = package }),
            ("a manifest naming another version", new() { [release.MetadataFile] = Metadata(release, Package("0.1.24.0")), [release.PackageFile] = Package("0.1.24.0") }),
            ("a manifest naming another package", new() { [release.MetadataFile] = Metadata(release, Package(name: "RoleBand.Windows.Trial")), [release.PackageFile] = Package(name: "RoleBand.Windows.Trial") }),
            ("a file that is no package", new() { [release.MetadataFile] = Metadata(release, [1, 2, 3]), [release.PackageFile] = [1, 2, 3] }),
            ("unreadable metadata", new() { [release.MetadataFile] = "not json"u8.ToArray(), [release.PackageFile] = package }),
        };
        foreach (var (why, files) in cases)
        {
            var folder = Folder();
            try
            {
                await Assert.ThrowsExactlyAsync<NotTheRelease>(() => DownloadAsync(release, files, folder), why);
                CollectionAssert.AreEqual(Array.Empty<string>(), Directory.Exists(folder) ? Directory.GetFiles(folder) : [],
                    $"{why}: neither the package nor its partial download is left");
            }
            finally { if (Directory.Exists(folder)) Directory.Delete(folder, true); }
        }
    }

    [TestMethod]
    public async Task ACancelledDownloadLeavesNothingBehind()
    {
        var release = Release();
        // Larger than one read, so the cancellation lands while the file is half written.
        var package = new byte[1 << 20];
        var folder = Folder();
        try
        {
            using var feed = new Feed(new() { [release.MetadataFile] = Metadata(release, package), [release.PackageFile] = package });
            using var cancel = new CancellationTokenSource();
            var download = new ReleaseDownload(feed);
            var file = await download.MetadataAsync(release, CancellationToken.None);
            var reported = 0;
            await Assert.ThrowsAsync<OperationCanceledException>(() => download.PackageAsync(release, file, folder,
                new Synchronous(_ => { if (++reported == 1) cancel.Cancel(); }), cancel.Token));
            Assert.AreEqual(1, reported, "the download stopped after its first part");
            CollectionAssert.AreEqual(Array.Empty<string>(), Directory.GetFiles(folder));
        }
        finally { if (Directory.Exists(folder)) Directory.Delete(folder, true); }
    }

    [TestMethod]
    public async Task ReleaseFilesAreReadOnlyFromGitHub()
    {
        var release = Release();
        var package = Package();
        var files = new Dictionary<string, byte[]> { [release.MetadataFile] = Metadata(release, package), [release.PackageFile] = package };
        var folder = Folder();
        try
        {
            await Assert.ThrowsExactlyAsync<NotTheRelease>(() => DownloadAsync(release, files, folder, fileHost: "example.com"));
            await Assert.ThrowsExactlyAsync<HttpRequestException>(() => DownloadAsync(release, new() { [release.MetadataFile] = files[release.MetadataFile] }, folder));
        }
        finally { if (Directory.Exists(folder)) Directory.Delete(folder, true); }
    }

    [TestMethod]
    public void WindowsNamesTheSignerOfASignedFileAndNoneForAnUnsignedOne()
    {
        // The runtime's own library carries Microsoft's Authenticode signature on every machine the tests run on.
        var signed = typeof(object).Assembly.Location;
        var signer = WindowsSignature.Signer(signed);
        Assert.IsNotNull(signer, signed);
        StringAssert.Contains(X509CertificateLoader.LoadCertificate(signer).Subject, "Microsoft");
        var unsigned = Path.Combine(Path.GetTempPath(), $"roleband-unsigned-{Guid.NewGuid():N}.exe");
        File.WriteAllBytes(unsigned, [0x4D, 0x5A, 0, 0]);
        try { Assert.IsNull(WindowsSignature.Signer(unsigned)); }
        finally { File.Delete(unsigned); }
    }

    [TestMethod]
    public void AnInstalledVersionAtOrAboveTheReleaseNeedsNoInstall()
    {
        Assert.IsTrue(InstalledRoleBand.AtLeast("0.1.25", "0.1.25"));
        Assert.IsTrue(InstalledRoleBand.AtLeast("0.2.0", "0.1.25"));
        Assert.IsFalse(InstalledRoleBand.AtLeast("0.1.24", "0.1.25"));
        Assert.IsFalse(InstalledRoleBand.AtLeast("0.1.9", "0.1.25"));
    }

    /// <summary>Setup's folder in a fresh scratch place, with an attempt's download in it as Setup leaves it.</summary>
    private static (string Setup, string Folder, string Package) Downloaded()
    {
        var setup = Path.Combine(Path.GetTempPath(), "roleband-download-tests", Guid.NewGuid().ToString("N"), "RoleBand-Setup");
        var folder = Path.Combine(setup, "0.2.1");
        Directory.CreateDirectory(folder);
        var package = Path.Combine(folder, "RoleBand-0.2.1-Windows-x64.msix");
        File.WriteAllBytes(package, new byte[64 * 1024]);
        return (setup, folder, package);
    }

    /// <summary>Holds the package as a virus scanner reading the new file can: open, without sharing deletion.</summary>
    private static FileStream Scanning(string package) => new(package, FileMode.Open, FileAccess.Read, FileShare.Read);

    [TestMethod]
    public async Task AnInstallsOutcomeArrivesOnlyOnceItsDownloadIsGone()
    {
        var (setup, folder, _) = Downloaded();
        bool? seenDuring = null;

        var installed = await DownloadFolder.UsingAsync(folder, () =>
        {
            seenDuring = Directory.Exists(folder);
            return Task.FromResult(true);
        });

        // Setup closes, and its process ends, the moment it has this outcome: nothing may be left to remove then.
        Assert.IsTrue(installed);
        Assert.IsTrue(seenDuring, "the attempt downloads into its folder");
        Assert.IsFalse(Directory.Exists(folder), "no empty version folder is left");
        Assert.IsFalse(Directory.Exists(setup), "Setup's own folder goes with its last download");
        Directory.Delete(Path.GetDirectoryName(setup)!);
    }

    [TestMethod]
    public async Task AFailedAttemptsDownloadIsRemovedBeforeItsErrorArrives()
    {
        var (setup, folder, _) = Downloaded();

        await Assert.ThrowsExactlyAsync<HttpRequestException>(() =>
            DownloadFolder.UsingAsync<bool>(folder, () => throw new HttpRequestException("offline")));

        Assert.IsFalse(Directory.Exists(setup));
        Directory.Delete(Path.GetDirectoryName(setup)!);
    }

    [TestMethod]
    public async Task OneTryWhileAScannerHoldsThePackageLeavesIt()
    {
        var (setup, folder, package) = Downloaded();
        using (Scanning(package))
            Assert.IsFalse(await DownloadFolder.RemoveAsync(folder, TimeSpan.Zero));

        Assert.IsTrue(File.Exists(package), "a file nobody may delete is left whole, without an error");
        Directory.Delete(Path.GetDirectoryName(setup)!, recursive: true);
    }

    [TestMethod]
    public async Task ADownloadAScannerLetsGoOfAMomentLaterIsStillRemoved()
    {
        var (setup, folder, package) = Downloaded();
        var scanner = Scanning(package);
        var release = Task.Run(async () =>
        {
            await Task.Delay(TimeSpan.FromMilliseconds(600));
            await scanner.DisposeAsync();
        });

        Assert.IsTrue(await DownloadFolder.RemoveAsync(folder, DownloadFolder.Patience));
        await release;

        Assert.IsFalse(Directory.Exists(setup));
        Directory.Delete(Path.GetDirectoryName(setup)!);
    }

    [TestMethod]
    public async Task RemovingADownloadKeepsWhateverElseIsInSetupsFolder()
    {
        var (setup, folder, _) = Downloaded();
        var other = Path.Combine(setup, "0.2.0");
        Directory.CreateDirectory(other);

        Assert.IsTrue(await DownloadFolder.RemoveAsync(folder, DownloadFolder.Patience));

        Assert.IsFalse(Directory.Exists(folder));
        Assert.IsTrue(Directory.Exists(other), "another attempt's folder is not this one's to remove");
        Assert.IsTrue(await DownloadFolder.RemoveAsync(Path.Combine(setup, "0.1.0"), TimeSpan.Zero), "a folder never made is already gone");
        Directory.Delete(Path.GetDirectoryName(setup)!, recursive: true);
    }

    /// <summary>Records each report as it is made, unlike <see cref="Progress{T}"/>, which posts it later.</summary>
    private sealed class Synchronous(Action<(long, long)> report) : IProgress<(long Received, long Total)>
    {
        public void Report((long Received, long Total) value) => report(value);
    }
}

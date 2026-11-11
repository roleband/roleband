using System.Reflection;
using System.Runtime.InteropServices;
using System.Security.Cryptography;
using System.Security.Cryptography.X509Certificates;
using System.Security.Principal;
using RoleBand.EngineHost;

namespace RoleBand.Setup;

/// <summary>RoleBand Setup: trusts RoleBand's publisher with an administrator's approval, then downloads, checks and
/// installs the release it was built for, for the person who started it, and opens RoleBand.</summary>
internal static class Program
{
    /// <summary>The argument of the second Setup, started through Windows' administrator prompt, that only trusts the
    /// publisher.</summary>
    private const string TrustStep = "--trust";

    [STAThread]
    private static int Main(string[] args)
    {
        if (args is [TrustStep]) return Trust();
        var release = Embedded();
        var copy = new NativeCopy();
        return new Installer(copy, release).Run();
    }

    /// <summary>The release this Setup was built for: the version, update identity and certificate the build embeds; null
    /// for a build without RoleBand's identity.</summary>
    internal static InstallRelease? Embedded()
    {
        var assembly = typeof(Program).Assembly;
        var version = assembly.GetCustomAttributes<AssemblyMetadataAttribute>().FirstOrDefault(item => item.Key == "RoleBandVersion")?.Value;
        using var identity = assembly.GetManifestResourceStream("RoleBand.Setup.release-identity.json");
        using var certificate = assembly.GetManifestResourceStream("RoleBand.Setup.RoleBand.cer");
        if (string.IsNullOrEmpty(version) || identity is null || certificate is null) return null;
        using var bytes = new MemoryStream();
        certificate.CopyTo(bytes);
        return InstallRelease.Read(version, new StreamReader(identity).ReadToEnd(), bytes.ToArray());
    }

    /// <summary>The step that runs as an administrator: the compiled-in certificate into the machine's Trusted People.
    /// It takes nothing from its caller, so the prompt approves exactly this.</summary>
    private static int Trust()
    {
        try
        {
            using var identity = WindowsIdentity.GetCurrent();
            if (!new WindowsPrincipal(identity).IsInRole(WindowsBuiltInRole.Administrator)) return TrustExit.NotAdministrator;
            var release = Embedded();
            if (release is null) return TrustExit.NoRelease;
            using var certificate = PublisherTrust.Certificate(release);
            using var store = new X509Store(StoreName.TrustedPeople, StoreLocation.LocalMachine);
            PublisherTrust.Trust(store, certificate);
            return TrustExit.Trusted;
        }
        catch (Exception error) when (error is IOException or CryptographicException or UnauthorizedAccessException)
        {
            return TrustExit.Failed;
        }
    }
}

internal static class TrustExit
{
    public const int Trusted = 0, Failed = 1, NotAdministrator = 3, NoRelease = 4;
}

/// <summary>Setup's pages and the work between them.</summary>
internal sealed class Installer(NativeCopy copy, InstallRelease? release)
{
    private const int Install = 100, Open = 101, Retry = 102, Close = 103;

    private CancellationTokenSource? download;
    private int busy;

    private SetupWindow Window => windowField ??= new SetupWindow(copy["windows-setup-title"], Pressed);
    private SetupWindow? windowField;

    public int Run()
    {
        Window.Show(First());
        return 0;
    }

    private Page First()
    {
        if (release is null) return Stopped("windows-setup-no-release", "windows-setup-no-release-body", PageIcon.Error);
        switch (InstallFacts.Read().Stop)
        {
            case InstallStop.NeedsWindows11: return Stopped("windows-setup-needs-windows-11", "windows-setup-needs-windows-11-body", PageIcon.Warning);
            case InstallStop.OtherAccount: return Stopped("windows-setup-other-account", "windows-setup-other-account-body", PageIcon.Warning);
            case InstallStop.StoreOnly: return Stopped("windows-setup-store-only", "windows-setup-store-only-body", PageIcon.Warning);
        }
        if (InstalledRoleBand.Version(release) is { } installed && InstalledRoleBand.AtLeast(installed, release.Version))
            return new Page(copy["windows-setup-installed"], copy.Format("windows-setup-installed-body", ("version", installed)), PageIcon.App,
                [new PageButton(Open, copy["open"]), new PageButton(Close, copy["menu-close"])]);
        return Welcome();
    }

    private Page Welcome() =>
        new(copy.Format("windows-setup-heading", ("version", release!.Version)), copy["windows-setup-body"], PageIcon.App,
            [new PageButton(Install, copy["windows-setup-install"], Elevates: true), new PageButton(SetupWindow.Cancel, copy["update-cancel"])]);

    private Page Stopped(string heading, string body, PageIcon icon, string? detail = null, bool retry = false) =>
        new(copy[heading], copy[body], icon,
            retry ? [new PageButton(Retry, copy["retry"]), new PageButton(Close, copy["menu-close"])] : [new PageButton(Close, copy["menu-close"])],
            Detail: detail);

    private Page DownloadFailed(string? detail) =>
        Stopped("windows-setup-download-failed", "windows-setup-download-failed-body", PageIcon.Error, detail, retry: true);

    /// <summary>A press: true closes the window.</summary>
    private bool Pressed(int button)
    {
        switch (button)
        {
            case Install or Retry:
                if (Interlocked.Exchange(ref busy, 1) == 0) _ = Task.Run(InstallAsync);
                return false;
            case Open:
                _ = Task.Run(async () =>
                {
                    await InstalledRoleBand.OpenAsync(release!);
                    Window.Press(Close);
                });
                return false;
            case SetupWindow.Cancel when Volatile.Read(ref busy) == 1:
                // Only a download stops when asked; trusting and Windows' install run to their end. A download that
                // has just ended may have disposed its source, and nothing may escape the dialog's callback.
                try { Volatile.Read(ref download)?.Cancel(); }
                catch (ObjectDisposedException) { }
                return false;
            default:
                return true;
        }
    }

    private async Task InstallAsync()
    {
        // No cookies: a release host that sets one never gets it back, so a request says no more than SECURITY.md lists.
        using var handler = new SocketsHttpHandler { AllowAutoRedirect = false, UseCookies = false };
        var feed = new ReleaseDownload(handler);
        var folder = Path.Combine(Path.GetTempPath(), Scratch, release!.Version);
        try
        {
            ReleaseFile file;
            // The release's small metadata file first, so a PC without a connection hears so before anyone is asked for
            // permission, and the download's size is known from its first byte.
            using (download = new CancellationTokenSource())
                file = await feed.MetadataAsync(release, download.Token);
            Volatile.Write(ref download, null);
            Window.Navigate(new Page(copy["windows-setup-approving"], null, PageIcon.App, [], Waiting: true));
            if (!await ApproveAsync())
            {
                Window.Navigate(Stopped("windows-setup-not-approved", "windows-setup-not-approved-body", PageIcon.Warning, retry: true));
                return;
            }
            string package;
            using (download = new CancellationTokenSource())
            {
                Window.Navigate(new Page(copy["windows-setup-downloading"], Received(0, file.Size), PageIcon.App,
                    [new PageButton(SetupWindow.Cancel, copy["update-cancel"])], Progress: true));
                var progress = new Immediate<(long Received, long Total)>(value =>
                {
                    Window.SetProgress((int)(value.Received * 100 / value.Total));
                    Window.SetBody(Received(value.Received, value.Total));
                });
                package = await feed.PackageAsync(release, file, folder, progress, download.Token);
            }
            Volatile.Write(ref download, null);
            // Windows' own check of the signature, whose signer must be the certificate this Setup trusted.
            if (WindowsSignature.Signer(package) is not { } signer || !signer.AsSpan().SequenceEqual(release.Certificate))
                throw new NotTheRelease("The package is not signed with RoleBand's certificate.");
            Window.Navigate(new Page(copy["windows-setup-installing"], null, PageIcon.App, [], Progress: true));
            try
            {
                await new WindowsPackageDeployer().AddAsync(package, downgrade: false, new Immediate<int>(Window.SetProgress), CancellationToken.None);
            }
            catch (Exception error) when (error is IOException or COMException)
            {
                // Windows' own reason, in Windows' language.
                Window.Navigate(new Page(copy["windows-setup-failed"], error.Message, PageIcon.Error, [new PageButton(Close, copy["menu-close"])]));
                return;
            }
            TryDelete(folder);
            await InstalledRoleBand.OpenAsync(release);
            Window.Press(Close);
        }
        catch (OperationCanceledException)
        {
            Window.Navigate(Welcome());
        }
        catch (NotTheRelease error)
        {
            Window.Navigate(Stopped("windows-setup-failed", "windows-setup-not-genuine-body", PageIcon.Error, error.Message));
        }
        catch (Exception error) when (error is HttpRequestException or IOException)
        {
            Window.Navigate(DownloadFailed(error.Message));
        }
        finally
        {
            Volatile.Write(ref busy, 0);
        }
    }

    /// <summary>"120 MB of 350 MB".</summary>
    private string Received(long received, long total) =>
        copy.Format("update-progress", ("received", AboutPanel.Size(copy, received)), ("total", AboutPanel.Size(copy, total)));

    /// <summary>Starts this Setup again through Windows' administrator prompt, for the trust step only; false when the
    /// prompt was refused or the step failed.</summary>
    private static async Task<bool> ApproveAsync()
    {
        var start = new System.Diagnostics.ProcessStartInfo(Environment.ProcessPath!, "--trust") { UseShellExecute = true, Verb = "runas" };
        try
        {
            using var process = System.Diagnostics.Process.Start(start);
            if (process is null) return false;
            await process.WaitForExitAsync();
            return process.ExitCode == TrustExit.Trusted;
        }
        catch (System.ComponentModel.Win32Exception)
        {
            // 1223: the person chose No, or no administrator approved.
            return false;
        }
    }

    /// <summary>The folder under the temporary folder that holds Setup's downloads.</summary>
    private const string Scratch = "RoleBand-Setup";

    /// <summary>Removes a finished download, and Setup's folder with it when nothing else is in it.</summary>
    private static void TryDelete(string folder)
    {
        try
        {
            Directory.Delete(folder, recursive: true);
            var parent = Path.GetDirectoryName(folder);
            if (parent is not null && !Directory.EnumerateFileSystemEntries(parent).Any()) Directory.Delete(parent);
        }
        catch (IOException) { }
        catch (UnauthorizedAccessException) { }
    }

    /// <summary>Reports at once, on the reporting thread; the window takes its updates from any thread.</summary>
    private sealed class Immediate<T>(Action<T> report) : IProgress<T>
    {
        public void Report(T value) => report(value);
    }
}

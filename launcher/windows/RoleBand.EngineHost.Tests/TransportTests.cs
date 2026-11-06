using System.Net;
using System.Net.Sockets;
using System.Security.AccessControl;
using System.Security.Cryptography;
using System.Security.Principal;
using System.Text;
using System.Text.Json;
using Microsoft.VisualStudio.TestTools.UnitTesting;

namespace RoleBand.EngineHost.Tests;

[TestClass]
public sealed class TransportTests
{
    [TestMethod]
    public void IncompleteTrialCannotFallThroughToProductionState()
    {
        var resources = Path.Combine(Path.GetTempPath(), "roleband-incomplete-trial", Guid.NewGuid().ToString("N"));
        Directory.CreateDirectory(Path.Combine(resources, "engine"));
        Directory.CreateDirectory(Path.Combine(resources, "runtime"));
        File.WriteAllText(Path.Combine(resources, "engine", "release.json"), "{\"version\":\"0.1.1\"}");
        File.WriteAllText(Path.Combine(resources, "engine", "desktop.py"), "");
        File.WriteAllText(Path.Combine(resources, "runtime", "python.exe"), "");
        Assert.ThrowsExactly<IOException>(() => EngineConfiguration.Packaged(resources));
        File.WriteAllText(Path.Combine(resources, "trial.json"), JsonSerializer.Serialize(new { trial_only = false, trial_id = Guid.NewGuid().ToString("N") }));
        Assert.ThrowsExactly<IOException>(() => EngineConfiguration.Packaged(resources));
    }

    [TestMethod]
    public void TrialStateCannotBeAnInstalledDataRoot()
    {
        var resources = Path.Combine(Path.GetTempPath(), "roleband-root-trial", Guid.NewGuid().ToString("N"));
        Directory.CreateDirectory(Path.Combine(resources, "engine"));
        Directory.CreateDirectory(Path.Combine(resources, "runtime"));
        File.WriteAllText(Path.Combine(resources, "engine", "release.json"), "{\"version\":\"0.1.1\"}");
        File.WriteAllText(Path.Combine(resources, "engine", "desktop.py"), "");
        File.WriteAllText(Path.Combine(resources, "runtime", "python.exe"), "");
        File.WriteAllText(Path.Combine(resources, "trial.json"), JsonSerializer.Serialize(new { trial_only = true, trial_id = Guid.NewGuid().ToString("N") }));
        var checkout = new DirectoryInfo(AppContext.BaseDirectory);
        while (!File.Exists(Path.Combine(checkout.FullName, "backend", "desktop.py")))
            checkout = checkout.Parent ?? throw new IOException("Source checkout not found.");
        var installed = Path.Combine(KnownFolders.LocalAppData, "RoleBand");
        var legacy = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.UserProfile), ".roleband");
        foreach (var state in new[] { installed, Path.Combine(installed, "db"), legacy, Path.Combine(legacy, "trial") })
        {
            var existed = Path.Exists(state);
            Assert.ThrowsExactly<IOException>(() => EngineConfiguration.Packaged(resources, state));
            Assert.ThrowsExactly<IOException>(() => EngineConfiguration.Source(checkout.FullName, state));
            Assert.AreEqual(existed, Path.Exists(state));
        }
        // A sibling whose name merely starts with an installed root's name is a trial root.
        var sibling = Path.Combine(KnownFolders.LocalAppData, "RoleBandTrials", Guid.NewGuid().ToString("N"));
        Assert.AreEqual(sibling, EngineConfiguration.Packaged(resources, sibling).State);
        Assert.AreEqual(sibling, EngineConfiguration.Source(checkout.FullName, sibling).State);
        Assert.IsFalse(Path.Exists(sibling));
    }

    [TestMethod]
    [DataRow(0)]
    [DataRow(1)]
    [DataRow(2)]
    public async Task ForeignListenerCannotAuthenticateOrCaptureReusableCredentials(int mode)
    {
        var state = Path.Combine(Path.GetTempPath(), "roleband-transport-tests", Guid.NewGuid().ToString("N"));
        PrivateStorage.EnsureDirectory(state);
        PrivateStorage.EnsureDirectory(Path.Combine(state, "launcher"));
        using var listener = new TcpListener(IPAddress.Loopback, 0);
        listener.Start();
        var port = ((IPEndPoint)listener.LocalEndpoint).Port;
        var secret = Convert.ToHexStringLower(RandomNumberGenerator.GetBytes(32));
        var instance = Guid.NewGuid().ToString("N");
        var origin = $"http://{instance}.localhost:{port}";
        File.WriteAllText(Path.Combine(state, "launcher", "http-engine.json"),
            JsonSerializer.Serialize(new { format = 1, instance, secret, origin }));
        var server = Task.Run(async () =>
        {
            using var timeout = new CancellationTokenSource(TimeSpan.FromSeconds(10));
            using var peer = await listener.AcceptTcpClientAsync(timeout.Token);
            using var stream = peer.GetStream();
            using var reader = new StreamReader(stream, Encoding.ASCII, leaveOpen: true);
            var lines = new List<string>();
            while (await reader.ReadLineAsync(timeout.Token) is { Length: > 0 } line) lines.Add(line);
            var authorization = lines.Single(line => line.StartsWith("Authorization: ", StringComparison.Ordinal))[15..];
            var proof = Convert.ToHexStringLower(HMACSHA256.HashData(Convert.FromHexString(secret),
                Encoding.UTF8.GetBytes($"response-v1\n{authorization}\n200\n{Convert.ToHexStringLower(SHA256.HashData("{}"u8))}")));
            var header = mode == 1 ? $"X-RoleBand-Proof: {proof}\r\n" : "";
            var content = mode == 1 ? "{\"forged\":true}" : "{}";
            var reply = $"HTTP/1.1 200 OK\r\nContent-Length: {Encoding.UTF8.GetByteCount(content)}\r\n{header}Connection: close\r\n\r\n{content}";
            if (mode == 2) reply = "HTTP/1.1 200 OK\r\nContent-Length: 100\r\nConnection: close\r\n\r\n";
            await stream.WriteAsync(Encoding.UTF8.GetBytes(reply), timeout.Token);
            if (mode == 2)
            {
                var probe = new byte[1];
                Assert.AreEqual(0, await stream.ReadAsync(probe, timeout.Token));
            }
            return lines;
        });
        using var client = new EngineClient(state);
        if (mode == 2)
            await Assert.ThrowsAsync<OperationCanceledException>(() => client.RequestAsync(HttpMethod.Get, "/api/launcher-health"));
        else
            await Assert.ThrowsAsync<IOException>(() => client.RequestAsync(HttpMethod.Get, "/api/launcher-health"));
        var wire = await server;
        Assert.IsTrue(wire.Contains($"Host: {instance}.localhost:{port}"));
        Assert.IsFalse(string.Join('\n', wire).Contains(secret, StringComparison.Ordinal));
        Assert.IsFalse(wire.Any(line => line.StartsWith("Cookie:", StringComparison.OrdinalIgnoreCase)));
    }

    [TestMethod]
    public void StorageRejectsForeignAclWithoutRepairingItAndLeaseIsExclusive()
    {
        var state = Path.Combine(Path.GetTempPath(), "roleband-storage-tests", Guid.NewGuid().ToString("N"));
        using (var lease = PrivateStorage.Lease(state, "desktop.lock"))
            Assert.ThrowsExactly<IOException>(() => PrivateStorage.Lease(state, "desktop.lock"));
        using (PrivateStorage.Lease(state, "desktop.lock")) { }
        var directory = new DirectoryInfo(state);
        var security = directory.GetAccessControl();
        var everyone = new SecurityIdentifier(WellKnownSidType.WorldSid, null);
        security.AddAccessRule(new FileSystemAccessRule(everyone, FileSystemRights.Read, AccessControlType.Allow));
        directory.SetAccessControl(security);
        Assert.ThrowsExactly<IOException>(() => PrivateStorage.EnsureDirectory(state));
        Assert.IsTrue(directory.GetAccessControl().GetAccessRules(true, true, typeof(SecurityIdentifier))
            .Cast<FileSystemAccessRule>().Any(rule => everyone.Equals(rule.IdentityReference)));
    }
}

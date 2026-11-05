using System.Globalization;
using System.Net;
using System.Net.Sockets;
using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using System.Text.RegularExpressions;

namespace RoleBand.EngineHost;

public sealed class EngineClient : IDisposable
{
    private const int MaximumBody = 16 * 1024 * 1024;
    private readonly byte[] secret;
    private readonly HttpClient http;
    public Uri Origin { get; }

    public EngineClient(string state)
    {
        PrivateStorage.Verify(state, true);
        using var record = JsonDocument.Parse(PrivateStorage.Read(Path.Combine(state, "launcher", "http-engine.json")));
        var root = record.RootElement;
        if (root.GetProperty("format").GetInt32() != 1) throw new IOException("Unknown HTTP discovery format.");
        var instance = root.GetProperty("instance").GetString() ?? "";
        var value = root.GetProperty("secret").GetString() ?? "";
        var endpoint = root.GetProperty("origin").GetString() ?? "";
        if (!Regex.IsMatch(instance, "\\A[0-9a-f]{32}\\z") || !Regex.IsMatch(value, "\\A[0-9a-f]{64}\\z")
            || !Uri.TryCreate(endpoint, UriKind.Absolute, out var uri) || uri.Scheme != "http"
            || uri.Host != instance + ".localhost" || uri.UserInfo != "" || uri.Port is < 1 or > 65535
            || endpoint != $"http://{instance}.localhost:{uri.Port}")
            throw new IOException("Invalid private HTTP discovery.");
        Origin = uri;
        secret = Convert.FromHexString(value);
        var handler = new SocketsHttpHandler { AllowAutoRedirect = false, UseProxy = false, UseCookies = false };
        handler.ConnectCallback = async (context, cancellation) =>
        {
            if (context.DnsEndPoint.Host != Origin.Host || context.DnsEndPoint.Port != Origin.Port)
                throw new IOException("Engine connection changed origin.");
            var socket = new Socket(AddressFamily.InterNetwork, SocketType.Stream, ProtocolType.Tcp);
            try
            {
                await socket.ConnectAsync(new IPEndPoint(IPAddress.Loopback, Origin.Port), cancellation);
                return new NetworkStream(socket, ownsSocket: true);
            }
            catch { socket.Dispose(); throw; }
        };
        http = new HttpClient(handler) { BaseAddress = Origin, Timeout = TimeSpan.FromSeconds(3) };
    }

    public static string Sign(ReadOnlySpan<byte> key, string keyId, string stamp, string nonce,
                              string method, string origin, string target, ReadOnlySpan<byte> body)
    {
        var hash = Convert.ToHexStringLower(SHA256.HashData(body));
        var message = string.Join('\n', "request-v1", keyId, stamp, nonce, method, origin, target, hash);
        return Convert.ToHexStringLower(HMACSHA256.HashData(key, Encoding.UTF8.GetBytes(message)));
    }

    public async Task<JsonDocument> RequestAsync(HttpMethod method, string target, byte[]? body = null, CancellationToken cancellation = default)
    {
        if (!target.StartsWith('/') || target.StartsWith("//", StringComparison.Ordinal) || target.Contains('\r') || target.Contains('\n'))
            throw new IOException("Engine target must be origin-relative.");
        var uri = new Uri(Origin, target);
        if (uri.GetLeftPart(UriPartial.Authority) != Origin.GetLeftPart(UriPartial.Authority) || uri.PathAndQuery != target || uri.Fragment != "")
            throw new IOException("Engine target was normalized or changed origin.");
        var endpoint = Origin.GetLeftPart(UriPartial.Authority);
        var stamp = DateTimeOffset.UtcNow.ToUnixTimeSeconds().ToString(CultureInfo.InvariantCulture);
        var nonce = Convert.ToHexStringLower(RandomNumberGenerator.GetBytes(16));
        var payload = body ?? [];
        var signature = Sign(secret, "control", stamp, nonce, method.Method, endpoint, target, payload);
        var authorization = $"RoleBand control:{stamp}:{nonce}:{signature}";
        using var request = new HttpRequestMessage(method, uri);
        request.Headers.TryAddWithoutValidation("Authorization", authorization);
        request.Content = new ByteArrayContent(payload);
        request.Content.Headers.ContentType = new("application/json");
        using var deadline = CancellationTokenSource.CreateLinkedTokenSource(cancellation);
        deadline.CancelAfter(http.Timeout);
        cancellation = deadline.Token;
        using var response = await http.SendAsync(request, HttpCompletionOption.ResponseHeadersRead, cancellation);
        using var stream = await response.Content.ReadAsStreamAsync(cancellation);
        using var bytes = new MemoryStream();
        var buffer = new byte[65536];
        int read;
        while ((read = await stream.ReadAsync(buffer, cancellation)) != 0)
        {
            if (bytes.Length + read > MaximumBody) throw new IOException("Engine response exceeds its size limit.");
            bytes.Write(buffer, 0, read);
        }
        var content = bytes.ToArray();
        var expected = HMACSHA256.HashData(secret, Encoding.UTF8.GetBytes(
            $"response-v1\n{authorization}\n{(int)response.StatusCode}\n{Convert.ToHexStringLower(SHA256.HashData(content))}"));
        var proof = response.Headers.TryGetValues("X-RoleBand-Proof", out var values) ? values.ToArray() : [];
        if (proof.Length != 1 || !Regex.IsMatch(proof[0], "\\A[0-9a-f]{64}\\z")
            || !CryptographicOperations.FixedTimeEquals(expected, Convert.FromHexString(proof[0])))
            throw new IOException("The listener did not authenticate as this engine.");
        if (!response.IsSuccessStatusCode) throw new IOException($"Authenticated engine request refused ({(int)response.StatusCode}).");
        return JsonDocument.Parse(content);
    }

    public async Task<Uri> BrowserUriAsync(CancellationToken cancellation = default)
    {
        using var response = await RequestAsync(HttpMethod.Post, "/api/local-auth/browser-ticket", "{}"u8.ToArray(), cancellation);
        var value = response.RootElement.GetProperty("url").GetString() ?? "";
        var prefix = Origin.GetLeftPart(UriPartial.Authority) + "/#roleband=";
        if (!value.StartsWith(prefix, StringComparison.Ordinal) || !Regex.IsMatch(value[prefix.Length..], "\\A[0-9a-f]{64}\\z"))
            throw new IOException("Invalid browser handoff.");
        return new Uri(value);
    }

    public void Dispose()
    {
        http.Dispose();
        CryptographicOperations.ZeroMemory(secret);
    }
}

using System.Text.Json;
using System.Text.RegularExpressions;

namespace RoleBand.EngineHost;

public static class RecoveryGuard
{
    public static void RequireLaunchable(string state)
    {
        var directory = Path.Combine(state, "recovery");
        if (!Path.Exists(directory)) return;
        PrivateStorage.Verify(directory, true);
        var path = Path.Combine(directory, "check.json");
        if (!Path.Exists(path)) return;
        try
        {
            using var document = JsonDocument.Parse(PrivateStorage.Read(path, 128 * 1024));
            var root = document.RootElement;
            var phase = root.GetProperty("phase").GetString();
            var attempts = root.GetProperty("attempts").EnumerateArray().Select(item => item.GetString()).ToArray();
            if (root.GetProperty("format").GetInt32() != 1 || root.GetProperty("kind").GetString() != "checkpoint-drill"
                || root.GetProperty("state").GetString() != state
                || phase is not ("verifying" or "failed" or "verified" or "abandoned")
                || !Path.IsPathFullyQualified(root.GetProperty("checkpoint").GetString()!)
                || !Hex(root.GetProperty("manifest_sha256").GetString(), 64)
                || !Hex(root.GetProperty("archive_sha256").GetString(), 64)
                || attempts.Length is < 1 or > 256 || attempts.Any(item => !Hex(item, 32))
                || attempts.Distinct().Count() != attempts.Length)
                throw new IOException("The recovery journal is damaged or unsupported. Preserve it for repair.");
            if (phase is not ("verified" or "abandoned"))
                throw new IOException("A recovery check is unfinished. The current database has not been replaced. "
                    + "Use the recovery retry command, or recovery abandon to keep the current database. "
                    + $"Retained state: {state}");
        }
        catch (Exception error) when (error is JsonException or KeyNotFoundException or InvalidOperationException or ArgumentException or FormatException)
        {
            throw new IOException("The recovery journal is damaged or unsupported. Preserve it for repair.", error);
        }
    }

    private static bool Hex(string? value, int length) => value is not null
        && value.Length == length && Regex.IsMatch(value, "\\A[0-9a-f]+\\z");
}

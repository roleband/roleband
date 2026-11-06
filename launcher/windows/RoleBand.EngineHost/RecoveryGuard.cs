using System.Text.Json;
using System.Text.RegularExpressions;
using System.Numerics;

namespace RoleBand.EngineHost;

public static class RecoveryGuard
{
    private const int ReaderContract = 1;
    public static void RequireLaunchable(string state)
    {
        RequireRestoreResolved(state);
        var marker = Path.Combine(state, "db.auth", "cluster.json");
        if (Path.Exists(marker))
        {
            using var document = Parse(marker);
            Storage(document.RootElement, state, true);
        }
        RequireDrillResolved(state);
    }

    private static void RequireDrillResolved(string state)
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

    private static void RequireRestoreResolved(string state)
    {
        var directory = Path.Combine(state, "recovery");
        if (!Path.Exists(directory)) return;
        PrivateStorage.Verify(directory, true);
        var path = Path.Combine(directory, "restore.json");
        if (!Path.Exists(path)) return;
        try
        {
            using var document = Parse(path);
            var root = document.RootElement;
            var phase = root.GetProperty("phase").GetString();
            var attempts = root.GetProperty("attempts").EnumerateArray().Select(item => item.GetString()).ToArray();
            var profile = root.GetProperty("profile");
            if (root.GetProperty("format").GetInt32() != 1 || root.GetProperty("kind").GetString() != "checkpoint-restore"
                || root.GetProperty("state").GetString() != state || !Hex(root.GetProperty("id").GetString(), 32)
                || phase is not ("preparing" or "prepared" or "retaining" or "installing" or "checking" or "complete" or "aborted")
                || !Path.IsPathFullyQualified(root.GetProperty("checkpoint").GetString()!)
                || !Hex(root.GetProperty("manifest_sha256").GetString(), 64) || !Hex(root.GetProperty("archive_sha256").GetString(), 64)
                || attempts.Length > 256 || attempts.Any(item => !Hex(item, 32)) || attempts.Distinct().Count() != attempts.Length
                || (phase is not ("preparing" or "aborted") && attempts.Length == 0)
                || profile.EnumerateObject().Count() != 3 || !Hex(profile.GetProperty("owner").GetString(), 64)
                || !Hex(profile.GetProperty("password").GetString(), 64)
                || (profile.GetProperty("key").ValueKind != JsonValueKind.Null && !Hex(profile.GetProperty("key").GetString(), 64)))
                throw new IOException("The restore journal is damaged or unsupported. Preserve it for repair.");
            Storage(root.GetProperty("original_metadata"), state, false);
            Identity(root.GetProperty("original_directory"));
            if (phase is not ("preparing" or "aborted")) Identity(root.GetProperty("restored_directory"));
            if (phase is not ("complete" or "aborted"))
                throw new IOException("Database restore is unfinished. Use restore resume with a compatible signed repair package.");
        }
        catch (Exception error) when (error is JsonException or KeyNotFoundException or InvalidOperationException or ArgumentException or FormatException or OverflowException)
        {
            throw new IOException("The restore journal is damaged or unsupported. Preserve it for repair.", error);
        }
    }

    private static JsonDocument Parse(string path)
    {
        try { return JsonDocument.Parse(PrivateStorage.Read(path, 128 * 1024)); }
        catch (JsonException error) { throw new IOException("Retained Windows metadata is damaged. Preserve it for repair.", error); }
    }

    private static void Storage(JsonElement root, string state, bool requireReader)
    {
        try
        {
            var format = root.GetProperty("format").GetInt32();
            if (format is not (1 or 2) || root.EnumerateObject().Count() != (format == 1 ? 3 : 4)
                || root.GetProperty("pgdata").GetString() != Path.Combine(state, "db") || root.GetProperty("version").GetInt32() != 16)
                throw new IOException("Windows storage metadata is damaged or names another cluster.");
            var minimum = format == 1 ? 1 : root.GetProperty("minimum_reader").GetInt32();
            if (minimum is < 1 or > 65535) throw new IOException("Windows storage reader contract is invalid.");
            if (requireReader && minimum > ReaderContract)
                throw new IOException($"This database requires Windows reader contract {minimum}; this engine supports {ReaderContract}. Install a compatible signed package or use a compatible recovery checkpoint.");
        }
        catch (Exception error) when (error is KeyNotFoundException or InvalidOperationException or FormatException or OverflowException)
        { throw new IOException("Windows storage metadata is damaged. Preserve it for repair.", error); }
    }

    private static void Identity(JsonElement value)
    {
        var items = value.EnumerateArray().ToArray();
        if (items.Length != 2 || items.Any(item => item.ValueKind != JsonValueKind.Number
            || !BigInteger.TryParse(item.GetRawText(), out var number) || number < 0) || items[1].GetRawText() == "0")
            throw new IOException("The restore directory identity is invalid. Preserve it for repair.");
    }

    private static bool Hex(string? value, int length) => value is not null
        && value.Length == length && Regex.IsMatch(value, "\\A[0-9a-f]+\\z");
}

using System.Text.Json;
using System.Xml.Linq;

namespace RoleBand.EngineHost;

/// <summary>An engine alert, which the app shows as a Windows notification.</summary>
public sealed record EngineAlert(string Title, string Message, string? Subtitle);

/// <summary>
/// Alerts the engine leaves for the app: the app names a folder in the engine's environment, and every engine process
/// writes one JSON file there per alert (<c>backend/tracker/osnotify.py</c>), whole and under a name that sorts by
/// when it was written. The app takes them on its own clock, so an alert reaches the screen even while the engine's
/// API does not answer, which is one of the things an alert reports. The format is
/// <c>launcher/windows/contracts/engine-alerts.json</c>.
/// </summary>
public static class EngineAlerts
{
    public const string Variable = "ROLEBAND_ALERTS_DIR";
    public const int Format = 1;

    /// <summary>An alert older than this is from an engine that stopped before the app took it, and is dropped.</summary>
    public static readonly TimeSpan MaxAge = TimeSpan.FromHours(1);

    /// <summary>At most this many alerts are shown from one look; the rest are dropped rather than stacked.</summary>
    public const int MaxShown = 3;

    /// <summary>The largest alert file read; a larger one is dropped unshown. The engine keeps its alerts within it.</summary>
    public const long MaxBytes = 16 * 1024;

    public static string Folder(string state) => Path.Combine(state, "alerts");

    /// <summary>
    /// Takes every alert waiting in <paramref name="folder"/>, oldest first, and deletes its file. An alert whose file
    /// cannot be deleted is not shown, so it is not shown again on every look; a malformed or stale one is deleted
    /// unshown.
    /// </summary>
    public static IReadOnlyList<EngineAlert> Take(string folder, DateTimeOffset now)
    {
        string[] files;
        try
        {
            files = Directory.GetFiles(folder)
                .Where(path => Path.GetExtension(path) == ".json" && !Path.GetFileName(path).StartsWith('.'))
                .Order(StringComparer.Ordinal)
                .ToArray();
        }
        catch (Exception error) when (error is IOException or UnauthorizedAccessException)
        {
            return [];
        }
        var shown = new List<EngineAlert>();
        foreach (var file in files)
        {
            var text = Read(file);
            try
            {
                File.Delete(file);
            }
            catch (Exception error) when (error is IOException or UnauthorizedAccessException)
            {
                continue;
            }
            if (shown.Count < MaxShown && text is not null && Parse(text, now) is { } alert) shown.Add(alert);
        }
        return shown;
    }

    private static string? Read(string file)
    {
        try
        {
            var info = new FileInfo(file);
            return info.Length > MaxBytes ? null : File.ReadAllText(file);
        }
        catch (Exception error) when (error is IOException or UnauthorizedAccessException)
        {
            return null;
        }
    }

    /// <summary>The alert a file holds, or null for one in another format, without words, or stale.</summary>
    public static EngineAlert? Parse(string text, DateTimeOffset now)
    {
        try
        {
            using var document = JsonDocument.Parse(text);
            var root = document.RootElement;
            if (root.ValueKind != JsonValueKind.Object
                || !root.TryGetProperty("format", out var format) || format.ValueKind != JsonValueKind.Number
                || !format.TryGetInt32(out var number) || number != Format)
                return null;
            var title = Text(root, "title");
            var message = Text(root, "message");
            if (string.IsNullOrWhiteSpace(title) || string.IsNullOrWhiteSpace(message)) return null;
            if (Text(root, "created_at") is not { } created
                || !DateTimeOffset.TryParse(created, System.Globalization.CultureInfo.InvariantCulture,
                    System.Globalization.DateTimeStyles.None, out var at)
                || now - at > MaxAge)
                return null;
            var subtitle = Text(root, "subtitle");
            return new EngineAlert(title, message, string.IsNullOrWhiteSpace(subtitle) ? null : subtitle);
        }
        catch (JsonException)
        {
            return null;
        }
    }

    /// <summary>A string field, or null when it is missing, not a string, or not text: JSON accepts a lone surrogate
    /// escape such as <c>\uD800</c>, which only fails when the string is read.</summary>
    private static string? Text(JsonElement root, string name)
    {
        if (!root.TryGetProperty(name, out var value) || value.ValueKind != JsonValueKind.String) return null;
        try
        {
            return value.GetString();
        }
        catch (InvalidOperationException)
        {
            return null;
        }
    }

    /// <summary>The notification Windows shows for an alert: its title, then the subtitle when there is one, then the
    /// message, each as text Windows never reads as markup.</summary>
    public static string ToastXml(EngineAlert alert)
    {
        var binding = new XElement("binding", new XAttribute("template", "ToastGeneric"));
        foreach (var line in new[] { alert.Title, alert.Subtitle, alert.Message })
            if (!string.IsNullOrWhiteSpace(line)) binding.Add(new XElement("text", line));
        return new XElement("toast", new XElement("visual", binding)).ToString(SaveOptions.DisableFormatting);
    }
}

using System.Globalization;
using System.Text.Json;

namespace RoleBand.EngineHost;

public sealed class NativeCopy
{
    private readonly Dictionary<string, string> messages;

    public NativeCopy(string? language = null)
    {
        language ??= CultureInfo.CurrentUICulture.Name;
        var selected = language.StartsWith("es", StringComparison.OrdinalIgnoreCase) ? "es"
            : language.StartsWith("zh", StringComparison.OrdinalIgnoreCase) ? "zh-Hans" : "en";
        using var stream = typeof(NativeCopy).Assembly.GetManifestResourceStream($"RoleBand.Copy.copy.{selected}.json")
            ?? throw new IOException("Native language resources are missing.");
        messages = JsonSerializer.Deserialize<Dictionary<string, string>>(stream) ?? throw new IOException("Native language resources are invalid.");
    }

    public string this[string key] => messages.TryGetValue(key, out var value) ? value : throw new KeyNotFoundException(key);
}

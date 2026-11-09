using System.Globalization;
using System.Text.Json;
using System.Text.RegularExpressions;

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
        // Times and numbers follow the person's own regional format when it is in the copy's language.
        var current = CultureInfo.CurrentCulture;
        Culture = current.Name.StartsWith(selected[..2], StringComparison.OrdinalIgnoreCase) ? current : CultureInfo.GetCultureInfo(selected);
    }

    /// <summary>The culture times and numbers are written in, matching the copy's language.</summary>
    public CultureInfo Culture { get; }

    public string this[string key] => messages.TryGetValue(key, out var value) ? value : throw new KeyNotFoundException(key);

    /// <summary>The message with each <c>{name}</c> replaced; a placeholder left unfilled is an error, not text.</summary>
    /// <summary>Whether the message has a {name} placeholder to fill.</summary>
    public bool Takes(string key, string name) => this[key].Contains("{" + name + "}", StringComparison.Ordinal);

    public string Format(string key, params (string Name, string Value)[] values)
    {
        var text = this[key];
        var expected = Regex.Matches(text, @"\{([a-z]+)\}").Select(match => match.Groups[1].Value).ToHashSet();
        if (!expected.SetEquals(values.Select(value => value.Name)))
            throw new FormatException($"{key} takes {string.Join(", ", expected.Order())}.");
        // One pass, so a value that happens to contain braces is never read as a placeholder.
        var given = values.ToDictionary(value => value.Name, value => value.Value);
        return Regex.Replace(text, @"\{([a-z]+)\}", match => given[match.Groups[1].Value]);
    }
}

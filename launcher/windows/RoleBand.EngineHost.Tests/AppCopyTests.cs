using System.Text.RegularExpressions;
using Microsoft.VisualStudio.TestTools.UnitTesting;

namespace RoleBand.EngineHost.Tests;

/// <summary>Every word the app's windows show is a catalogued message (docs/copy.md): none is written into the
/// markup, and every message the code reads exists in every language.</summary>
[TestClass]
public sealed class AppCopyTests
{
    private static readonly string[] Languages = ["en", "es", "zh-Hans"];

    private static string AppFolder()
    {
        for (var folder = new DirectoryInfo(AppContext.BaseDirectory); folder is not null; folder = folder.Parent)
        {
            var app = Path.Combine(folder.FullName, "RoleBand.App");
            if (File.Exists(Path.Combine(app, "FlyoutWindow.xaml"))) return app;
        }
        throw new DirectoryNotFoundException("RoleBand.App");
    }

    /// <summary>Words in a text attribute; a binding, a resource and an icon glyph are not words.</summary>
    internal static IEnumerable<string> Literals(string markup) =>
        Regex.Matches(markup, @"\b(Text|Content|Title|Header|PlaceholderText|ToolTipService\.ToolTip|AutomationProperties\.Name)=""([^""{&][^""]*)""")
            .Select(match => $"{match.Groups[1].Value}=\"{match.Groups[2].Value}\"");

    [TestMethod]
    public void NoWindowWritesItsWordsIntoItsMarkup()
    {
        var found = Directory.EnumerateFiles(AppFolder(), "*.xaml")
            .SelectMany(file => Literals(File.ReadAllText(file)).Select(literal => $"{Path.GetFileName(file)}: {literal}"))
            .ToList();
        CollectionAssert.AreEqual(Array.Empty<string>(), found);
    }

    [TestMethod]
    public void TheCheckFindsAWordInMarkupAndPassesBindingsAndGlyphs()
    {
        CollectionAssert.AreEqual(new[] { "Text=\"RoleBand\"" },
            Literals("<TextBlock Text=\"RoleBand\" /><TextBlock Text=\"{x:Bind Name}\" /><FontIcon Glyph=\"&#xE713;\" />").ToArray());
    }

    /// <summary>The engine's update-status words, which the app compares and never shows.</summary>
    private static readonly HashSet<string> NotMessages = ["up-to-date", "rate-limited"];

    [TestMethod]
    public void EveryMessageTheAppReadsExistsInEveryLanguage()
    {
        // Every hyphenated name in the app's code, not only those written inside copy[...]: many reach it through a
        // variable or a condition (a settings error, a control message, a button's two labels).
        var keys = Directory.EnumerateFiles(AppFolder(), "*.cs")
            .SelectMany(file => Regex.Matches(File.ReadAllText(file), @"""([a-z][a-z0-9]*(?:-[a-z0-9]+)+)""").Select(match => match.Groups[1].Value))
            .Where(key => !NotMessages.Contains(key))
            .ToHashSet();
        foreach (var key in new[] { "guide-app", "host-stop-failed", "engine-refused", "update-undo" })
            Assert.IsTrue(keys.Contains(key), $"{key} is read through the app's code");
        foreach (var language in Languages)
        {
            var copy = new NativeCopy(language);
            var missing = keys.Where(key => !Exists(copy, key)).Order().ToList();
            CollectionAssert.AreEqual(Array.Empty<string>(), missing, language);
        }
    }

    private static bool Exists(NativeCopy copy, string key)
    {
        try
        {
            _ = copy[key];
            return true;
        }
        catch (KeyNotFoundException)
        {
            return false;
        }
    }
}

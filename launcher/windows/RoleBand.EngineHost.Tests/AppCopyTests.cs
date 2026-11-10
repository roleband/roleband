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

    [TestMethod]
    public void EveryMessageTheAppReadsExistsInEveryLanguage()
    {
        var keys = Directory.EnumerateFiles(AppFolder(), "*.cs")
            .SelectMany(file => Regex.Matches(File.ReadAllText(file), @"copy\[""([a-z0-9-]+)""\]").Select(match => match.Groups[1].Value))
            .ToHashSet();
        Assert.IsTrue(keys.Contains("guide-app"), "the flyout names the app from the catalog");
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

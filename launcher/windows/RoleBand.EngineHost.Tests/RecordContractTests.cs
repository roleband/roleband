using System.Text.Json;
using System.Text.Json.Nodes;
using Microsoft.VisualStudio.TestTools.UnitTesting;

namespace RoleBand.EngineHost.Tests;

// The native host reaches the same startup verdict as the engine on every case in
// launcher/windows/contracts/retained-records.json, which backend/tests/test_windows_records.py reads too.
[TestClass]
public sealed class RecordContractTests
{
    private static readonly JsonObject Corpus = LoadCorpus();

    private static JsonObject LoadCorpus()
    {
        var checkout = new DirectoryInfo(AppContext.BaseDirectory);
        while (!File.Exists(Path.Combine(checkout.FullName, "backend", "desktop.py")))
            checkout = checkout.Parent ?? throw new IOException("Source checkout not found.");
        var path = Path.Combine(checkout.FullName, "launcher", "windows", "contracts", "retained-records.json");
        return JsonNode.Parse(File.ReadAllText(path))!.AsObject();
    }

    public static IEnumerable<object[]> Cases() =>
        Corpus["cases"]!.AsArray().Select(item => new object[] { item!["name"]!.GetValue<string>() });

    [TestMethod]
    [DynamicData(nameof(Cases))]
    public void HostStartupVerdictMatchesTheSharedCase(string name)
    {
        var item = Corpus["cases"]!.AsArray().Single(entry => entry!["name"]!.GetValue<string>() == name)!.AsObject();
        var file = item["file"]!.GetValue<string>();
        var state = Path.Combine(Path.GetTempPath(), "roleband-record-tests", Guid.NewGuid().ToString("N"), "state");
        var record = Path.Combine(state, Corpus["files"]![file]!.GetValue<string>().Replace('/', Path.DirectorySeparatorChar));
        PrivateStorage.EnsureDirectory(state);
        PrivateStorage.EnsureDirectory(Path.GetDirectoryName(record)!);
        File.WriteAllText(record, Materialize(item, state));
        string verdict;
        try
        {
            RecoveryGuard.RequireLaunchable(state);
            verdict = "accepted";
        }
        catch (IOException error)
        {
            verdict = Verdict(error.Message);
        }
        Assert.AreEqual(item["verdict"]!.GetValue<string>(), verdict, name);
        Assert.IsFalse(Path.Exists(Path.Combine(state, "db")));
    }

    private static string Materialize(JsonObject item, string state)
    {
        var places = new Dictionary<string, string>
        {
            ["{state}"] = state,
            ["{pgdata}"] = Path.Combine(state, "db"),
            ["{checkpoint}"] = Path.Combine(Path.GetDirectoryName(state)!, "checkpoint"),
        };
        if (item["raw"] is { } raw)
        {
            var text = raw.GetValue<string>();
            foreach (var (placeholder, value) in places)
                text = text.Replace(placeholder, JsonSerializer.Serialize(value)[1..^1]);
            return text;
        }
        var document = Corpus["bases"]![item["file"]!.GetValue<string>()]!.DeepClone().AsObject();
        if (item["set"] is JsonObject changes)
            foreach (var (key, value) in changes)
                document[key] = value?.DeepClone();
        if (item["remove"] is JsonArray removed)
            foreach (var key in removed)
                document.Remove(key!.GetValue<string>());
        return Substitute(document, places)!.ToJsonString();
    }

    private static JsonNode? Substitute(JsonNode? node, IReadOnlyDictionary<string, string> places) => node switch
    {
        JsonObject value => new JsonObject(value.Select(pair => KeyValuePair.Create(pair.Key, Substitute(pair.Value, places)))),
        JsonArray value => new JsonArray(value.Select(entry => Substitute(entry, places)).ToArray()),
        JsonValue value when value.GetValueKind() == JsonValueKind.String && places.TryGetValue(value.GetValue<string>(), out var path)
            => JsonValue.Create(path),
        _ => node?.DeepClone(),
    };

    private static string Verdict(string message) =>
        message.Contains("requires Windows reader contract", StringComparison.Ordinal) ? "newer-reader"
        : message.Contains("unfinished", StringComparison.Ordinal) ? "unfinished"
        : message.Contains("damaged", StringComparison.Ordinal) ? "damaged"
        : "unclassified: " + message;
}

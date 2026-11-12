using System.Text.Json.Nodes;
using System.Xml.Linq;
using Microsoft.VisualStudio.TestTools.UnitTesting;

namespace RoleBand.EngineHost.Tests;

// The engine writes alerts in the format of launcher/windows/contracts/engine-alerts.json
// (backend/tests/test_osnotify.py); these hold the app's side of it.
[TestClass]
public sealed class EngineAlertTests
{
    private static readonly JsonObject Contract = LoadContract();
    private static readonly DateTimeOffset Now = new(2026, 1, 1, 9, 30, 0, TimeSpan.Zero);
    private string folder = "";

    private static JsonObject LoadContract()
    {
        var checkout = new DirectoryInfo(AppContext.BaseDirectory);
        while (!File.Exists(Path.Combine(checkout.FullName, "backend", "desktop.py")))
            checkout = checkout.Parent ?? throw new IOException("Source checkout not found.");
        var path = Path.Combine(checkout.FullName, "launcher", "windows", "contracts", "engine-alerts.json");
        return JsonNode.Parse(File.ReadAllText(path))!.AsObject();
    }

    [TestInitialize]
    public void Prepare()
    {
        folder = Path.Combine(Path.GetTempPath(), "roleband-alert-tests", Guid.NewGuid().ToString("N"), "alerts");
        Directory.CreateDirectory(folder);
    }

    [TestCleanup]
    public void Clean() => Directory.Delete(Path.GetDirectoryName(folder)!, recursive: true);

    private static JsonObject Example(Action<JsonObject>? change = null)
    {
        var record = Contract["example"]!.DeepClone().AsObject();
        change?.Invoke(record);
        return record;
    }

    private void Leave(string name, JsonObject record) => File.WriteAllText(Path.Combine(folder, name), record.ToJsonString());

    [TestMethod]
    public void TheEngineIsToldTheFolderTheAppReads()
    {
        var state = Path.GetDirectoryName(folder)!;
        var start = new EngineConfiguration(state, state, "must-not-run.exe", "must-not-run.exe", "test", true, true).EngineStart([]);

        Assert.AreEqual(EngineAlerts.Variable, Contract["environment"]!.GetValue<string>());
        Assert.AreEqual(Path.Combine(state, Contract["folder"]!.GetValue<string>()), start.Environment[EngineAlerts.Variable]);
        Assert.AreEqual(EngineAlerts.Folder(state), start.Environment[EngineAlerts.Variable]);
        Assert.AreEqual(EngineAlerts.Format, Contract["format"]!.GetValue<int>());
    }

    [TestMethod]
    public void TheContractsExampleIsShownOnceAndItsFileIsGone()
    {
        Leave("00000000000000000001-10.json", Example());

        var taken = EngineAlerts.Take(folder, Now);

        Assert.AreEqual(1, taken.Count);
        Assert.AreEqual(Contract["example"]!["title"]!.GetValue<string>(), taken[0].Title);
        Assert.AreEqual(Contract["example"]!["message"]!.GetValue<string>(), taken[0].Message);
        Assert.IsNull(taken[0].Subtitle);
        Assert.AreEqual(0, Directory.GetFiles(folder).Length);
        Assert.AreEqual(0, EngineAlerts.Take(folder, Now).Count, "a taken alert is never shown again");
    }

    [TestMethod]
    public void AlertsComeInTheOrderTheyWereWritten()
    {
        Leave("00000000000000000300-7.json", Example(record => record["message"] = "third"));
        Leave("00000000000000000100-7.json", Example(record => record["message"] = "first"));
        Leave("00000000000000000200-9.json", Example(record => record["message"] = "second"));

        CollectionAssert.AreEqual(new[] { "first", "second", "third" }, EngineAlerts.Take(folder, Now).Select(alert => alert.Message).ToArray());
    }

    [TestMethod]
    public void AFileStillBeingWrittenIsLeftForTheEngineToFinish()
    {
        File.WriteAllText(Path.Combine(folder, ".00000000000000000001-10.json.tmp"), "{\"format\": 1, \"title\": \"Role");

        Assert.AreEqual(0, EngineAlerts.Take(folder, Now).Count);
        Assert.AreEqual(1, Directory.GetFiles(folder).Length);
    }

    [TestMethod]
    public void MalformedStaleOrForeignAlertsAreDroppedUnshown()
    {
        Leave("1.json", Example(record => record["format"] = 2));
        Leave("2.json", Example(record => record["message"] = " "));
        Leave("3.json", Example(record => record.Remove("title")));
        Leave("4.json", Example(record => record["created_at"] = (Now - EngineAlerts.MaxAge - TimeSpan.FromMinutes(1)).ToString("o")));
        Leave("5.json", Example(record => record["created_at"] = "yesterday"));
        File.WriteAllText(Path.Combine(folder, "6.json"), "not json");
        File.WriteAllText(Path.Combine(folder, "7.json"), new string(' ', 20_000) + Example().ToJsonString());
        Leave("8.json", Example(record => record["created_at"] = (Now - EngineAlerts.MaxAge + TimeSpan.FromMinutes(1)).ToString("o")));

        var taken = EngineAlerts.Take(folder, Now);

        Assert.AreEqual(1, taken.Count, "only the alert inside the age limit is shown");
        Assert.AreEqual(0, Directory.GetFiles(folder).Length, "a dropped alert does not wait to be looked at again");
    }

    [TestMethod]
    public void ABurstShowsOnlyTheFirstFew()
    {
        for (var index = 0; index < EngineAlerts.MaxShown + 4; index++)
            Leave($"{index:D20}-1.json", Example(record => record["message"] = $"alert {index}"));

        var taken = EngineAlerts.Take(folder, Now);

        CollectionAssert.AreEqual(Enumerable.Range(0, EngineAlerts.MaxShown).Select(index => $"alert {index}").ToArray(),
            taken.Select(alert => alert.Message).ToArray());
        Assert.AreEqual(0, Directory.GetFiles(folder).Length);
    }

    [TestMethod]
    public void AnAlertWhoseFileCannotBeDeletedIsNotShown()
    {
        Leave("1.json", Example());
        using (new FileStream(Path.Combine(folder, "1.json"), FileMode.Open, FileAccess.Read, FileShare.Read))
            Assert.AreEqual(0, EngineAlerts.Take(folder, Now).Count, "shown now, it would be shown again on every look");

        Assert.AreEqual(1, EngineAlerts.Take(folder, Now).Count, "once it can be deleted it is shown");
    }

    [TestMethod]
    public void NoFolderMeansNoAlerts()
    {
        Assert.AreEqual(0, EngineAlerts.Take(Path.Combine(folder, "missing"), Now).Count);
    }

    [TestMethod]
    public void TheNotificationCarriesTheWordsAsTextNotMarkup()
    {
        var xml = EngineAlerts.ToastXml(new EngineAlert("RoleBand", "Scan <failed> & \"stopped\"", "Today"));
        var texts = XElement.Parse(xml).Descendants("text").Select(text => text.Value).ToArray();

        CollectionAssert.AreEqual(new[] { "RoleBand", "Today", "Scan <failed> & \"stopped\"" }, texts);
        Assert.AreEqual("ToastGeneric", XElement.Parse(xml).Descendants("binding").Single().Attribute("template")!.Value);
        Assert.AreEqual(2, XElement.Parse(EngineAlerts.ToastXml(new EngineAlert("RoleBand", "body", null))).Descendants("text").Count());
    }
}

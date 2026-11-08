using Microsoft.VisualStudio.TestTools.UnitTesting;

namespace RoleBand.EngineHost.Tests;

[TestClass]
public sealed class TrayTests
{
    [TestMethod]
    public void EveryEngineStateIsNamedInEveryLanguage()
    {
        foreach (var language in new[] { "en", "es", "zh-Hans" })
        {
            var copy = new NativeCopy(language);
            foreach (var state in Enum.GetValues<EngineState>())
            {
                var text = copy[TrayModel.For(new EngineSnapshot(state)).StatusKey];
                Assert.IsFalse(string.IsNullOrWhiteSpace(text), $"{language} {state}");
            }
            _ = copy["first-open"];
            _ = copy["open"];
            _ = copy["quit"];
        }
    }

    [TestMethod]
    public void OpenRadarWaitsForAnEngineThatAnswers()
    {
        foreach (var state in Enum.GetValues<EngineState>())
            Assert.AreEqual(state == EngineState.Ready, TrayModel.For(new EngineSnapshot(state)).CanOpenRadar, state.ToString());
    }

    [TestMethod]
    public void StatesOnTheirWayElsewhereAreBusy()
    {
        var busy = Enum.GetValues<EngineState>().Where(state => TrayModel.For(new EngineSnapshot(state)).Busy).ToHashSet();
        CollectionAssert.AreEquivalent(
            new[] { EngineState.Starting, EngineState.Preparing, EngineState.Recovering, EngineState.Stopping }, busy.ToArray());
    }

    [TestMethod]
    public void TheTooltipNamesTheProductAndStateOnOneLineWithinTheShellLimit()
    {
        foreach (var language in new[] { "en", "es", "zh-Hans" })
        {
            var copy = new NativeCopy(language);
            foreach (var state in Enum.GetValues<EngineState>())
            {
                var tip = TrayModel.Tooltip(copy, new EngineSnapshot(state));
                Assert.IsTrue(tip.StartsWith("RoleBand: ", StringComparison.Ordinal), tip);
                Assert.IsFalse(tip.Contains('\n'), tip);
                Assert.IsLessThanOrEqualTo(127, tip.Length, tip);
            }
        }
    }
}

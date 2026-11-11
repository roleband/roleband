using Microsoft.VisualStudio.TestTools.UnitTesting;

namespace RoleBand.EngineHost.Tests;

/// <summary>An app opened while Windows still installs its update learns that from Windows' deployment log, in the shape
/// Windows writes it.</summary>
[TestClass]
public sealed class WindowsDeploymentsTests
{
    private const string Name = "RoleBand.Windows.Trial", File = "RoleBand-0.1.19-Windows-x64.msix";
    private static readonly DateTimeOffset Began = new(2026, 11, 9, 17, 20, 0, TimeSpan.Zero);

    private static string Event(int id, string activity, DateTimeOffset time, string? package = null, string? error = null, string message = "")
    {
        var data = (package is null ? "" : $"<Data Name='PackageFullName'>{package}</Data>")
            + (error is null ? "" : $"<Data Name='SummaryError'>{error}</Data>");
        return "<Event xmlns='http://schemas.microsoft.com/win/2004/08/events/event'><System>"
            + $"<Provider Name='Microsoft-Windows-AppXDeployment-Server'/><EventID>{id}</EventID>"
            + $"<TimeCreated SystemTime='{time.UtcDateTime:yyyy-MM-ddTHH:mm:ss.fffffff}Z'/><Correlation ActivityID='{{{activity}}}'/>"
            + $"</System><EventData>{data}</EventData><RenderingInfo Culture='en-US'><Message>{message}</Message></RenderingInfo></Event>";
    }

    private static InstallFinding Find(string rendered, DateTimeOffset? now = null) =>
        WindowsDeployments.Find(WindowsDeployments.Parse(rendered), Name, "0.1.19", File, Began, now ?? Began.AddMinutes(1));

    private const string Ours = "RoleBand.Windows.Trial_0.1.19.0_x64__fb8mmsge3dnhj";

    [TestMethod]
    public void AnInstallThatHasStartedAndNotEndedIsStillRunning()
    {
        var started = Event(603, "ed59580b-6ddc-0010-91d0-4129dd6ddd01", Began.AddSeconds(5),
            message: $"Started deployment Add operation on a package with main parameter {File} and Options ForceApplicationShutdownOption");
        Assert.AreEqual(InstallProgress.Running, Find(started).State, "queued, before Windows names the package");
        var running = started + Event(607, "ed59580b-6ddc-0010-91d0-4129dd6ddd01", Began.AddSeconds(7), Ours);
        Assert.AreEqual(InstallProgress.Running, Find(running).State);
        Assert.AreEqual(InstallProgress.None, Find(running, Began.AddHours(1)).State, "an install that never ends is not waited on for ever");
    }

    [TestMethod]
    public void TheInstallsOwnEndSaysWhetherItFinishedOrFailed()
    {
        var running = Event(607, "a1", Began.AddSeconds(7), Ours);
        Assert.AreEqual(InstallProgress.Finished, Find(running + Event(400, "a1", Began.AddSeconds(90), Ours)).State);
        var failed = Find(running + Event(401, "a1", Began.AddSeconds(30), Ours)
            + Event(404, "a1", Began.AddSeconds(30), Ours, "Windows cannot install package because the disk is full."));
        Assert.AreEqual(new InstallFinding(InstallProgress.Failed, "Windows cannot install package because the disk is full."), failed);
        Assert.AreEqual(InstallProgress.Running, Find(running + Event(400, "other", Began.AddSeconds(90), Ours)).State,
            "another install's end is not this one's");
    }

    [TestMethod]
    public void OnlyThisPackagesInstallSinceTheUpdateBeganCounts()
    {
        Assert.AreEqual(InstallProgress.None, Find(Event(607, "b1", Began.AddSeconds(7), "RoleBand.Windows.Trial_0.1.190.0_x64__fb8mmsge3dnhj")).State,
            "0.1.190 is not 0.1.19");
        Assert.AreEqual(InstallProgress.None, Find(Event(607, "b2", Began.AddSeconds(7), "Other.App_0.1.19.0_x64__x")).State);
        Assert.AreEqual(InstallProgress.None, Find(Event(607, "b3", Began.AddMinutes(-10), Ours)).State, "an install from before the update");
        var retried = Event(607, "c1", Began.AddSeconds(5), Ours) + Event(404, "c1", Began.AddSeconds(9), Ours, "busy")
            + Event(607, "c2", Began.AddSeconds(20), Ours);
        Assert.AreEqual(InstallProgress.Running, Find(retried).State, "the latest attempt counts");
        Assert.AreEqual(InstallProgress.None, Find("").State);
    }

    [TestMethod]
    public async Task WindowsAnswersTheQueryOnThisMachine()
    {
        var (code, output) = await WindowsDeployments.QueryAsync(TimeSpan.FromDays(7));
        Assert.AreEqual(0, code, "the query is valid for wevtutil and the log is readable without administrator rights");
        foreach (var item in WindowsDeployments.Parse(output))
            CollectionAssert.Contains(new[] { 603, 607, 400, 401, 404 }, item.Id);
    }
}

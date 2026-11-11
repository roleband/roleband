using System.Diagnostics;
using System.Globalization;
using System.Xml.Linq;

namespace RoleBand.EngineHost;

/// <summary>Where Windows' install of one package stands.</summary>
public enum InstallProgress { None, Running, Finished, Failed }

/// <param name="Reason">For a failed install, Windows' own words.</param>
public sealed record InstallFinding(InstallProgress State, string? Reason = null);

/// <summary>One event of Windows' package deployment log.</summary>
public sealed record DeploymentEvent(int Id, string Activity, DateTimeOffset Time, string? PackageFullName, string? Error, string Message);

/// <summary>
/// Asks Windows whether it is still installing a package. The app may be opened again while Windows installs its
/// update, and the version that opens is the one being replaced: only Windows' deployment log says whether that
/// update is still on its way, finished, or failed. Each install's events share an activity: 603 when it starts
/// (naming the file), 607 when it runs (naming the package), 400 when it finishes, 401 and 404 when it fails.
/// </summary>
public static class WindowsDeployments
{
    public const string Log = "Microsoft-Windows-AppXDeploymentServer/Operational";
    private static readonly int[] Ids = [603, 607, 400, 401, 404];

    /// <summary>An install still unfinished this long after it began is no longer waited for.</summary>
    public static readonly TimeSpan Patience = TimeSpan.FromMinutes(30);

    /// <param name="packageName">The package's name, without version or publisher.</param>
    /// <param name="version">The release version being installed; its package version starts with it.</param>
    /// <param name="file">The release file Windows was given.</param>
    /// <param name="since">When the update began; earlier installs are not this one.</param>
    public static InstallFinding Find(IEnumerable<DeploymentEvent> events, string packageName, string version, string file,
                                      DateTimeOffset since, DateTimeOffset now)
    {
        var prefix = $"{packageName}_{version}.";
        var all = events.Where(item => item.Time >= since - TimeSpan.FromMinutes(1)).ToList();
        var mine = all.Where(item =>
                (item.Id == 607 && item.PackageFullName?.StartsWith(prefix, StringComparison.OrdinalIgnoreCase) == true)
                || (item.Id == 603 && item.Message.Contains(file, StringComparison.OrdinalIgnoreCase)))
            .OrderByDescending(item => item.Time).FirstOrDefault();
        if (mine is null) return new InstallFinding(InstallProgress.None);
        var same = all.Where(item => item.Activity == mine.Activity).ToList();
        if (same.Any(item => item.Id == 400)) return new InstallFinding(InstallProgress.Finished);
        if (same.FirstOrDefault(item => item.Id is 401 or 404) is { } failure)
            return new InstallFinding(InstallProgress.Failed,
                same.FirstOrDefault(item => item.Id == 404)?.Error ?? failure.Error ?? failure.Message);
        return now - mine.Time > Patience ? new InstallFinding(InstallProgress.None) : new InstallFinding(InstallProgress.Running);
    }

    /// <summary>The log's events as <c>wevtutil</c> renders them: one &lt;Event&gt; after another, without a root.</summary>
    public static IReadOnlyList<DeploymentEvent> Parse(string rendered)
    {
        XNamespace ns = "http://schemas.microsoft.com/win/2004/08/events/event";
        var root = XElement.Parse("<Events>" + rendered + "</Events>", LoadOptions.None);
        var found = new List<DeploymentEvent>();
        foreach (var item in root.Elements(ns + "Event"))
        {
            var system = item.Element(ns + "System");
            if (system is null || !int.TryParse(system.Element(ns + "EventID")?.Value, out var id)) continue;
            var activity = system.Element(ns + "Correlation")?.Attribute("ActivityID")?.Value ?? "";
            if (!DateTimeOffset.TryParse(system.Element(ns + "TimeCreated")?.Attribute("SystemTime")?.Value, CultureInfo.InvariantCulture,
                    DateTimeStyles.AssumeUniversal, out var time)) continue;
            string? Data(string name) => item.Element(ns + "EventData")?.Elements(ns + "Data")
                .FirstOrDefault(data => (string?)data.Attribute("Name") == name)?.Value;
            var message = item.Element(ns + "RenderingInfo")?.Element(ns + "Message")?.Value ?? "";
            found.Add(new DeploymentEvent(id, activity, time, Data("PackageFullName"), Data("SummaryError"), message));
        }
        return found;
    }

    /// <summary>The log's start, run, finish and failure events of the last <paramref name="span"/>, newest first; none when
    /// the log cannot be read, which leaves an unfinished update for the version that began it to settle.</summary>
    public static async Task<IReadOnlyList<DeploymentEvent>> ReadAsync(TimeSpan span, CancellationToken cancellation = default)
    {
        try
        {
            var (code, output) = await QueryAsync(span, cancellation);
            return code == 0 ? Parse(output) : [];
        }
        catch (Exception error) when (error is IOException or System.ComponentModel.Win32Exception or System.Xml.XmlException)
        {
            return [];
        }
    }

    /// <summary>The raw query: <c>wevtutil</c>'s exit code and its rendered events.</summary>
    public static async Task<(int Code, string Output)> QueryAsync(TimeSpan span, CancellationToken cancellation = default)
    {
        var ids = string.Join(" or ", Ids.Select(id => $"EventID={id}"));
        var query = $"*[System[({ids}) and TimeCreated[timediff(@SystemTime) <= {(long)span.TotalMilliseconds}]]]";
        var start = new ProcessStartInfo(Path.Combine(Environment.SystemDirectory, "wevtutil.exe"))
        {
            UseShellExecute = false, CreateNoWindow = true, RedirectStandardOutput = true, RedirectStandardError = true,
            StandardOutputEncoding = System.Text.Encoding.UTF8,
        };
        foreach (var argument in new[] { "qe", Log, "/q:" + query, "/f:RenderedXml", "/rd:true", "/c:500" }) start.ArgumentList.Add(argument);
        using var process = Process.Start(start) ?? throw new IOException("wevtutil did not start.");
        var output = process.StandardOutput.ReadToEndAsync(cancellation);
        var errors = process.StandardError.ReadToEndAsync(cancellation);
        await process.WaitForExitAsync(cancellation);
        await errors;
        return (process.ExitCode, await output);
    }
}

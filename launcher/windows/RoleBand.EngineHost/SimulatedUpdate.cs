using System.Globalization;
using System.Text.Json;

namespace RoleBand.EngineHost;

/// <summary>
/// The update commands and Windows' installer, played for source runs only, so every update state can be reached and
/// looked at without a signed build. Nothing in it asks the feed, writes the journal or touches Windows' packages. A
/// scenario either holds at one state until Cancel or Quit, or walks a whole update at a person's pace.
/// </summary>
public sealed class SimulatedUpdate : IUpdateCommands, IPackageDeployer
{
    /// <summary>The update's size, close to a real release's.</summary>
    public const long Size = 332L * 1024 * 1024;

    public static readonly IReadOnlyList<string> Scenarios =
    [
        "offer", "downloading", "paused", "space", "check", "missing", "installing", "restarting", "refused",
        "finishing", "updated", "failed", "failed-alone", "undoing", "undo-gone", "undo-offline", "returning", "rolled-back",
    ];

    private static readonly TimeSpan Step = TimeSpan.FromMilliseconds(400);
    private readonly string scenario, running, previous, newer;
    private string? phase, from, to;

    private SimulatedUpdate(string scenario, string running)
    {
        this.scenario = scenario;
        this.running = running;
        var parts = running.Split('.').Select(part => int.Parse(part, CultureInfo.InvariantCulture)).ToArray();
        previous = parts[2] > 0 ? $"{parts[0]}.{parts[1]}.{parts[2] - 1}" : $"{parts[0]}.{Math.Max(parts[1] - 1, 0)}.9";
        newer = $"{parts[0]}.{parts[1]}.{parts[2] + 1}";
        (phase, from, to) = scenario switch
        {
            "finishing" => ("preparing", previous, running),
            "updated" => ("complete", previous, running),
            "failed" or "failed-alone" or "undoing" or "undo-gone" or "undo-offline" => ("failed", previous, running),
            "returning" => ("recovering", previous, running),
            "rolled-back" => ("recovered", running, newer),
            _ => ((string?)null, (string?)null, (string?)null),
        };
    }

    /// <summary>The simulation a source run asked for; none for a packaged app, whatever its command line says, and none
    /// for a scenario this build does not know.</summary>
    public static SimulatedUpdate? For(EngineConfiguration configuration, string? scenario) =>
        configuration.Development && scenario is not null && Scenarios.Contains(scenario) ? new(scenario, configuration.Version) : null;

    /// <summary>What the app presses by itself once it has started, so a state that follows a press is reached without one.</summary>
    public string? Press => scenario switch
    {
        "downloading" or "paused" or "space" or "check" or "missing" or "installing" or "restarting" or "refused" => "update",
        "undoing" or "undo-gone" or "undo-offline" => "undo",
        _ => null,
    };

    private string? Offer => scenario is "failed-alone" or "undo-gone" or "updated" or "finishing" or "returning" or "rolled-back" ? null : newer;

    public async Task<JsonElement> RunAsync(IReadOnlyList<string> arguments, CancellationToken cancellation, Action<string>? lines = null)
    {
        object answer = arguments[0] switch
        {
            "status" => Facts("ok"),
            "check" => Facts(Offer is null ? "up-to-date" : "offered"),
            "consent" => new { recorded = true },
            "resume" => Resume(),
            "settle" => Settle(arguments.Contains("yes")),
            "download" => await DownloadAsync(lines, cancellation),
            "begin" => Begin(),
            "recover-begin" => RecoverBegin(),
            "recover" => new { phase = phase = "recovered" },
            _ => new { status = "refused", reason = "The simulation has no such command." },
        };
        return JsonSerializer.SerializeToElement(answer);
    }

    private object Facts(string status) => new
    {
        status,
        automatic = false,
        checked_at = DateTimeOffset.Now.ToUnixTimeSeconds(),
        offer = phase is "applying" or "recovering" ? null : Offer,
        rate_limited_until = (double?)null,
        update = phase is null ? null : new
        {
            phase,
            from,
            to,
            running = running == to ? "to" : running == from ? "from" : null,
            since = DateTimeOffset.Now.ToUnixTimeSeconds(),
            package = $"RoleBand-{to}-Windows-x64.msix",
        },
    };

    private object Resume()
    {
        // The journal rules for the cases the scenarios reach: Windows never switched, so the version that began is back.
        if (phase == "applying" && running == from) phase = "aborted";
        return new { phase, running = phase is null ? null : running == to ? "to" : running == from ? "from" : null };
    }

    private object Settle(bool prepared)
    {
        phase = prepared ? "complete" : "failed";
        return new { phase };
    }

    private object Begin()
    {
        // A newer release taking over a failed update keeps the version from before it, as the journal does.
        (phase, from, to) = ("applying", phase == "failed" ? from : running, newer);
        return new { phase };
    }

    private object RecoverBegin() => scenario switch
    {
        "undo-gone" => new { status = "refused", kind = "missing",
            reason = $"Version {previous} is no longer published, so this update can't be undone. (A release file is not published)" },
        "undo-offline" => new { status = "refused", kind = "offline",
            reason = $"Undo downloads version {previous} first, and the connection was lost. (simulated)" },
        _ => Recovering(),
    };

    private object Recovering()
    {
        phase = "recovering";
        return new { phase, package = $@"C:\simulated\packages\RoleBand-{previous}-Windows-x64.msix" };
    }

    private async Task<object> DownloadAsync(Action<string>? lines, CancellationToken cancellation)
    {
        void Report(long received) => lines?.Invoke(JsonSerializer.Serialize(new { received, total = Size }));
        switch (scenario)
        {
            case "space":
                return new { status = "failed", kind = "space", needed = 1_288_490_189L, reason = "There is not enough free space. (simulated)" };
            case "downloading":
                Report(120L * 1024 * 1024);
                await Task.Delay(Timeout.Infinite, cancellation);
                break;
            case "paused":
                Report(Size * 2 / 5);
                return new { status = "failed", kind = "offline", reason = "The connection was lost. (simulated)" };
        }
        for (var part = 0; part <= 10; part++)
        {
            Report(Size * part / 10);
            await Task.Delay(Step, cancellation);
        }
        return scenario switch
        {
            "check" => new { status = "failed", kind = "check", reason = "The download is not the signed release. (simulated)" },
            "missing" => new { status = "failed", kind = "missing", reason = "The package is not published. (simulated)" },
            _ => new { status = "downloaded", package = $@"C:\simulated\packages\RoleBand-{newer}-Windows-x64.msix" },
        };
    }

    public async Task AddAsync(string package, bool downgrade, IProgress<int>? progress, CancellationToken cancellation)
    {
        // Windows' install: it holds where a scenario looks at it, refuses where one is about a refusal, and otherwise
        // reaches the end, where Windows would close this version.
        var stop = scenario switch { "installing" => 45, "undoing" => 30, "refused" => 60, _ => 100 };
        for (var percent = 0; percent <= stop; percent += 5)
        {
            progress?.Report(percent);
            await Task.Delay(Step, cancellation);
        }
        if (scenario == "refused")
            throw new IOException("The package could not be installed because a higher version of this package is already installed. (simulated)");
        if (stop < 100) await Task.Delay(Timeout.Infinite, cancellation);
    }

    /// <summary>Windows' log holds no install of a simulated package.</summary>
    public Task<InstallFinding> FindAsync(string packageName, string version, string file, DateTimeOffset since,
                                          CancellationToken cancellation) =>
        Task.FromResult(new InstallFinding(InstallProgress.None));

    public void ReopenWhenReplaced() { }
}

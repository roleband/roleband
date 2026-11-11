using System.Globalization;
using System.Text.Json;

namespace RoleBand.EngineHost;

public enum ScanAction { Start, Stop }

/// <summary>What the engine is doing. A value this build does not know reads as Unknown, so a newer
/// engine leaves the rest of the panel working.</summary>
public enum EngineActivity { Idle, Scanning, Updating, Unknown }

public sealed record ScanHold(string Kind, string Reason);

/// <summary>The engine's own account of itself, from the status reply's <c>launcher.status</c>.</summary>
public sealed record ScanPresentation(EngineActivity Activity, DateTimeOffset? ActivitySince, ScanHold? Hold,
                                      string? Queued, DateTimeOffset? LastScanAt, DateTimeOffset? CoverageAt);

public sealed record ScanCompany(string Name, DateTimeOffset? Since);

/// <param name="Enabled">Scans start on their own.</param>
/// <param name="Pausable">The schedule plan starts them, so a pause holds them.</param>
public sealed record ScheduleState(bool Enabled, bool Pausable, DateTimeOffset? PausedUntil)
{
    public bool IsPaused(DateTimeOffset now) => PausedUntil is { } until && until > now;
}

/// <summary>The scan picture. Live fields are present only while a scan executes; the <c>Last</c>
/// ones describe the newest finished scan.</summary>
public sealed record ScanPicture(
    string? Phase, int? Percent, int? CompaniesTotal, IReadOnlyList<ScanCompany> InFlight,
    int? RolesPending, int? RolesRecorded, int? LastCompanies, int? LastNewRoles, int? LastPostings,
    bool LastStopped, DateTimeOffset? NextScanAt, ScheduleState? Schedule)
{
    /// <summary>A live scan reported its companies; before its first heartbeat it has none.</summary>
    public bool Live => Percent is not null;

    /// <summary>Every company is read; the scan is adding the last roles or running the passes after it.</summary>
    public bool EveryCompanyRead => Phase is "persisting" or "finishing";

    /// <summary>When the next scan starts, while that is still after <paramref name="now"/>; a time already reached is due.</summary>
    public DateTimeOffset? NextScan(DateTimeOffset now) => NextScanAt is { } next && next > now ? next : null;
}

/// <summary>The scan queue as the header's Sync control reads it.</summary>
public sealed record ScanQueue(bool Running, bool ManualRunning, IReadOnlyList<string> ManualQueued)
{
    /// <summary>Stop belongs to a scan someone asked for; Scan now only to an engine with nothing running,
    /// held or queued.</summary>
    public ScanAction? ActionFor(ScanPresentation status)
    {
        if (ManualRunning || ManualQueued.Count > 0) return ScanAction.Stop;
        if (Running || status.Activity == EngineActivity.Scanning || status.Hold is not null || status.Queued is not null) return null;
        return ScanAction.Start;
    }
}

public sealed record ScanStatus(ScanPresentation Presentation, ScanPicture? Picture, ScanQueue? Queue, DateTimeOffset ReceivedAt)
{
    public ScanAction? Action => Queue?.ActionFor(Presentation);

    public static async Task<ScanStatus> ReadAsync(IEngineRequests engine, CancellationToken cancellation = default)
    {
        using var reply = await engine.RequestAsync(HttpMethod.Get, "/api/status", cancellation: cancellation);
        return Decode(reply.RootElement, DateTimeOffset.UtcNow);
    }

    /// <summary>Reads the status reply. The presentation is required; the picture is decoration, and a
    /// block this build cannot read leaves the status usable.</summary>
    public static ScanStatus Decode(JsonElement root, DateTimeOffset receivedAt)
    {
        try
        {
            if (root.GetProperty("db").GetString() != "ok") throw new InvalidDataException("The engine's database is not answering.");
            var launcher = root.GetProperty("launcher");
            if (launcher.ValueKind != JsonValueKind.Object) throw new InvalidDataException("The engine sent no launcher status.");
            var status = launcher.GetProperty("status");
            var presentation = new ScanPresentation(
                status.GetProperty("activity").GetString() switch
                {
                    "idle" => EngineActivity.Idle,
                    "scanning" => EngineActivity.Scanning,
                    "updating" => EngineActivity.Updating,
                    _ => EngineActivity.Unknown,
                },
                Stamp(status, "activity_since"),
                status.GetProperty("hold") is { ValueKind: JsonValueKind.Object } hold
                    ? new ScanHold(hold.GetProperty("kind").GetString() ?? "", hold.GetProperty("reason").GetString() ?? "")
                    : null,
                Text(status, "queued"),
                Stamp(status, "last_scan_at"),
                Stamp(status, "coverage_at"));
            ScanPicture? picture = null;
            if (launcher.TryGetProperty("scan", out var scan) && scan.ValueKind == JsonValueKind.Object)
            {
                try { picture = ReadPicture(scan); }
                catch (Exception error) when (error is InvalidOperationException or KeyNotFoundException or FormatException or InvalidDataException) { }
            }
            ScanQueue? queue = null;
            if (root.TryGetProperty("running", out var running) && root.TryGetProperty("manual_sync_running", out var manual)
                && root.TryGetProperty("manual_queued", out var queued) && queued.ValueKind == JsonValueKind.Array)
                queue = new ScanQueue(running.GetBoolean(), manual.GetBoolean(),
                    queued.EnumerateArray().Select(item => item.GetString() ?? throw new InvalidDataException("Invalid queue.")).ToArray());
            return new ScanStatus(presentation, picture, queue, receivedAt);
        }
        catch (Exception error) when (error is InvalidOperationException or KeyNotFoundException or FormatException)
        {
            throw new InvalidDataException("The engine's status reply could not be read.", error);
        }
    }

    private static ScanPicture ReadPicture(JsonElement scan)
    {
        var scheduling = Text(scan, "scheduling");
        ScheduleState? schedule = null;
        if (scheduling is "plan" or "timers" or "off")
        {
            // A pause this build cannot read leaves the schedule unknown rather than unpaused.
            var raw = Text(scan, "paused_until");
            var until = Stamp(scan, "paused_until");
            if (raw is null || until is not null)
                schedule = new ScheduleState(scheduling != "off", scheduling == "plan", until);
        }
        return new ScanPicture(
            Text(scan, "phase"), Number(scan, "percent"), Number(scan, "companies_total"),
            scan.GetProperty("in_flight").EnumerateArray()
                .Select(company => new ScanCompany(company.GetProperty("name").GetString() ?? "", Stamp(company, "since")))
                .ToArray(),
            Number(scan, "roles_pending"), Number(scan, "roles_recorded"), Number(scan, "last_companies"),
            Number(scan, "last_new_roles"), Number(scan, "last_postings"), scan.GetProperty("last_stopped").GetBoolean(),
            Stamp(scan, "next_scan_at"), schedule);
    }

    private static string? Text(JsonElement element, string name) =>
        element.TryGetProperty(name, out var value) && value.ValueKind == JsonValueKind.String ? value.GetString() : null;

    private static int? Number(JsonElement element, string name) =>
        element.TryGetProperty(name, out var value) && value.ValueKind == JsonValueKind.Number ? value.GetInt32() : null;

    /// <summary>An engine timestamp carries its offset; one without is not this engine's and reads as absent.</summary>
    public static DateTimeOffset? Stamp(JsonElement element, string name)
    {
        var text = Text(element, name);
        return text is not null && DateTimeOffset.TryParseExact(text, ["yyyy-MM-dd'T'HH:mm:ss.FFFFFFzzz", "yyyy-MM-dd'T'HH:mm:ss.FFFFFF'Z'"],
            CultureInfo.InvariantCulture, DateTimeStyles.AssumeUniversal, out var value) ? value : null;
    }
}

using System.Globalization;

namespace RoleBand.EngineHost;

/// <summary>What the scan picture is about. A stop finishes the run inside its own request, so Stopping
/// lasts exactly as long as that request; Requesting covers a start request and a scan the engine has
/// queued but not begun.</summary>
public enum ScanPhase { Scanning, Stopping, Requesting, Idle, Stopped }

public enum PrimaryAction { OpenRadar, StartEngine }

public enum PauseControl { None, Menu, Resume }

public enum ScheduleLineKind { Stopping, Off, Paused, Next, Unknown }

public enum BrowserRoute { Radar, NewRoles, Schedule, Settings }

/// <summary>One line under the picture: the next scan, a pause with its end, or scheduling off. While a
/// stop waits for the engine it says what the stop keeps instead.</summary>
public sealed record ScheduleLine(ScheduleLineKind Kind, string Text, string? LinkKey, string? HelpKey);

/// <summary>One figure with its words: companies scanned, new roles, roles in the tank.</summary>
public sealed record ScanFact(string Figure, string Label, BrowserRoute? Opens = null);

/// <summary>Everything the Scan tab draws, so the window has no rules of its own.</summary>
public sealed record ScanView(
    bool Picture,
    string TitleKey,
    string? HelpKey,
    string? Corner,
    double Progress,
    string ProgressLabel,
    IReadOnlyList<ScanFact> Companies,
    IReadOnlyList<ScanFact> Facts,
    string TankLabel,
    ScanFact Tank,
    ScanFact? TankFloor,
    ScheduleLine? Schedule,
    string Summary,
    PrimaryAction Primary,
    bool PrimaryEnabled,
    ScanAction? Scan,
    string? ScanBusyKey,
    PauseControl Pause);

public static class ScanPanel
{
    public static ScanPhase PhaseOf(ScanPresentation status, ScanPicture? picture, ScanAction? requested)
    {
        if (status.Activity == EngineActivity.Scanning) return requested == ScanAction.Stop ? ScanPhase.Stopping : ScanPhase.Scanning;
        if (requested == ScanAction.Start || status.Queued == "scan") return ScanPhase.Requesting;
        return picture?.LastStopped == true ? ScanPhase.Stopped : ScanPhase.Idle;
    }

    /// <summary>A scan past its reading names which of the Radar's two closing steps it is in.</summary>
    public static string TitleKey(ScanPhase phase, ScanPicture? picture) => phase switch
    {
        ScanPhase.Scanning => picture?.Phase switch
        {
            "persisting" => "scan-title-adding",
            "finishing" => "scan-title-finishing",
            _ => "scan-title-scanning",
        },
        ScanPhase.Stopping => "scan-title-stopping",
        ScanPhase.Requesting => "scan-title-requesting",
        ScanPhase.Idle => "scan-title-idle",
        _ => "scan-title-stopped",
    };

    /// <summary>The picture needs an engine that answers, no hold or engine update, and a scan to draw.</summary>
    public static bool ShowsPicture(EngineSnapshot engine, ScanStatus? status, ScanAction? requested)
    {
        if (engine.State != EngineState.Ready || status?.Picture is not { } picture) return false;
        if (status.Presentation.Hold is not null || status.Presentation.Activity == EngineActivity.Updating) return false;
        var phase = PhaseOf(status.Presentation, picture, requested);
        return phase is ScanPhase.Scanning or ScanPhase.Stopping || picture.LastCompanies is not null;
    }

    /// <summary>The status card's title when there is no picture: the engine's own state first, then
    /// what the engine says about itself.</summary>
    public static string CardTitleKey(EngineSnapshot engine, ScanStatus? status)
    {
        if (engine.State != EngineState.Ready || status is null) return TrayModel.For(engine).StatusKey;
        var presentation = status.Presentation;
        if (presentation.Activity == EngineActivity.Scanning) return "scanning";
        if (presentation.Activity == EngineActivity.Updating) return "updating";
        if (presentation.Hold is { } hold) return hold.Kind == "attention" ? "needs-attention" : "waiting";
        return presentation.Queued == "scan" ? "queued" : "ready";
    }

    /// <summary>Why the engine holds scans. Reasons whose words name the Mac or its source setup read as
    /// the general one here, and so does a reason this build does not know.</summary>
    public static string? ReasonKey(ScanHold? hold) => hold?.Reason switch
    {
        null => null,
        "supervisor_absent" or "supervisor_stale" => "reason-supervisor",
        "model_missing" => "reason-model",
        "model_preparing" => "reason-preparing",
        "preflight_running" => "reason-preflight",
        "busy_external" => "reason-busy",
        "maintenance" => "reason-maintenance",
        "update_queued" => "reason-queued",
        "provider_paused" or "provider_backoff" or "provider_policy_denied" => "reason-provider",
        _ => "reason-other",
    };

    public static ScheduleLine? Schedule(NativeCopy copy, ScanPhase phase, ScanPicture? picture, DateTimeOffset now)
    {
        if (phase == ScanPhase.Stopping) return new(ScheduleLineKind.Stopping, copy["scan-kept"], null, null);
        var schedule = picture?.Schedule;
        if (schedule is { Enabled: false })
            return new(ScheduleLineKind.Off, copy["scan-schedule-off"], null, "scan-schedule-off-help");
        if (schedule is { PausedUntil: { } until } && schedule.IsPaused(now))
            return new(ScheduleLineKind.Paused, copy.Format("scan-paused-until", ("time", Clock(copy, until, now))), "scan-resume", "scan-resume-help");
        if (schedule is not null || picture?.NextScanAt is not null)
            return new(ScheduleLineKind.Next, picture?.NextScan(now) is { } next
                ? copy.Format("scan-next", ("time", Clock(copy, next, now)))
                : copy["scan-next-soon"], "scan-change-times", "scan-opens-schedule");
        return null;
    }

    public static ScanView View(NativeCopy copy, EngineSnapshot engine, ScanStatus? status, ScanAction? requested, DateTimeOffset now)
    {
        var stopped = engine.State is EngineState.Stopped or EngineState.Attention;
        var primary = stopped ? PrimaryAction.StartEngine : PrimaryAction.OpenRadar;
        var primaryEnabled = stopped || TrayModel.For(engine).CanOpenRadar;
        var ready = engine.State == EngineState.Ready && status is not null;
        var scan = ready && requested is null ? status!.Action : null;
        var busyKey = requested switch { ScanAction.Start => "scan-sending", ScanAction.Stop => "scan-stop-requested", _ => null };
        var plan = ready ? status!.Picture?.Schedule : null;
        var pause = plan is null ? PauseControl.None
            : plan.IsPaused(now) ? PauseControl.Resume
            : plan.Pausable ? PauseControl.Menu : PauseControl.None;

        if (!ShowsPicture(engine, status, requested))
        {
            var title = CardTitleKey(engine, status);
            var help = engine.State switch
            {
                EngineState.Recovering => "host-recovering-body",
                EngineState.Attention => "host-attention-body",
                _ => ready ? ReasonKey(status!.Presentation.Hold) : null,
            };
            var corner = ready && status!.Presentation.Activity is EngineActivity.Scanning or EngineActivity.Updating
                && status.Presentation.ActivitySince is { } since ? Running(since, now) : null;
            var facts = ready
                ? new[]
                {
                    new ScanFact(status!.Presentation.LastScanAt is { } last ? Moment(copy, last, now) : copy["not-scanned"], copy["last-scan"]),
                    new ScanFact(status.Presentation.CoverageAt is { } coverage ? Moment(copy, coverage, now) : copy["not-scanned"], copy["coverage"]),
                }
                : [];
            return new ScanView(false, title, help, corner, 0, copy[title], [], facts, "", new ScanFact("", ""), null,
                null, copy[title], primary, primaryEnabled, scan, busyKey, pause);
        }

        var picture = status!.Picture!;
        var phase = PhaseOf(status.Presentation, picture, requested);
        var live = phase is ScanPhase.Scanning or ScanPhase.Stopping;
        var titleKey = TitleKey(phase, picture);
        var percent = Math.Clamp(picture.Percent ?? 0, 0, 100);
        string? cornerText = requested is not null ? null
            : live && picture.Phase == "finishing" && status.Presentation.ActivitySince is { } start ? Running(start, now)
            : live ? (picture.Percent is null ? null : $"{percent}%")
            : status.Presentation.LastScanAt is { } lastScan ? Moment(copy, lastScan, now) : null;
        var progressLabel = live ? copy.Format("scan-progress", ("percent", Number(copy, percent))) : copy[titleKey];
        var read = live && picture.EveryCompanyRead;
        var held = live ? picture.RolesPending ?? 0 : 0;
        var written = live ? picture.RolesRecorded ?? 0 : picture.LastPostings ?? 0;

        IReadOnlyList<ScanFact> companies = [];
        IReadOnlyList<ScanFact> lastFacts = [];
        string summary;
        if (live && picture.InFlight.Count == 0 && read)
        {
            var total = picture.CompaniesTotal ?? 0;
            lastFacts = [new ScanFact(Number(copy, total), copy["scan-companies-read"])];
            summary = copy.Format("scan-summary-read", ("companies", Number(copy, total)),
                ("recorded", Number(copy, picture.RolesRecorded ?? 0)), ("pending", Number(copy, picture.RolesPending ?? 0)));
        }
        else if (live)
        {
            companies = picture.InFlight.Select(company => new ScanFact(company.Since is { } since ? Running(since, now) : "", company.Name)).ToArray();
            var names = picture.InFlight.Select(company => company.Since is { } since ? $"{company.Name} {Running(since, now)}" : company.Name);
            summary = copy.Format("scan-summary-live", ("companies", string.Join(", ", names)),
                ("pending", Number(copy, picture.RolesPending ?? 0)), ("recorded", Number(copy, picture.RolesRecorded ?? 0)));
        }
        else
        {
            var newRoles = picture.LastNewRoles ?? 0;
            // The count opens the Radar on New, as the Radar's own New count does; with none it stays plain.
            lastFacts =
            [
                new ScanFact(Number(copy, picture.LastCompanies ?? 0), copy["scan-companies-read"]),
                new ScanFact(Number(copy, newRoles), copy["scan-new-roles"], newRoles > 0 ? BrowserRoute.NewRoles : null),
            ];
            summary = copy.Format(phase == ScanPhase.Stopped ? "scan-summary-stopped" : "scan-summary-last",
                ("companies", Number(copy, picture.LastCompanies ?? 0)), ("roles", Number(copy, newRoles)),
                ("postings", Number(copy, picture.LastPostings ?? 0)));
        }
        var tankLabel = copy[live ? "scan-roles-found" : phase == ScanPhase.Requesting ? "last-scan" : "scan-postings"];
        var tank = new ScanFact(Number(copy, live && !read ? held : written), copy[live && !read ? "scan-still-scanning" : "scan-recorded"]);
        var floor = read && held > 0 ? new ScanFact(Number(copy, held), copy["scan-to-add"])
            : live && !read ? new ScanFact(Number(copy, written), copy["scan-finished"])
            : null;
        return new ScanView(true, titleKey, null, cornerText, live ? percent : 0, progressLabel, companies, lastFacts, tankLabel,
            tank, floor, Schedule(copy, phase, picture, now), summary, primary, primaryEnabled, scan, busyKey, pause);
    }

    /// <summary>How long a scan or company has run, as a stopwatch reads, in any language.</summary>
    public static string Running(DateTimeOffset since, DateTimeOffset now)
    {
        var elapsed = now - since;
        if (elapsed < TimeSpan.Zero) elapsed = TimeSpan.Zero;
        return elapsed.TotalHours >= 1
            ? $"{(int)elapsed.TotalHours}:{elapsed.Minutes:00}:{elapsed.Seconds:00}"
            : $"{elapsed.Minutes}:{elapsed.Seconds:00}";
    }

    /// <summary>The time alone on the same local day, the date and time otherwise.</summary>
    public static string Clock(NativeCopy copy, DateTimeOffset moment, DateTimeOffset now)
    {
        var local = moment.ToLocalTime();
        var format = copy.Culture.DateTimeFormat;
        return local.Date == now.ToLocalTime().Date
            ? local.ToString(format.ShortTimePattern, copy.Culture)
            : local.ToString(format.MonthDayPattern, copy.Culture) + " " + local.ToString(format.ShortTimePattern, copy.Culture);
    }

    public static string Moment(NativeCopy copy, DateTimeOffset moment, DateTimeOffset now) =>
        moment.ToLocalTime().Date == now.ToLocalTime().Date
            ? copy.Format("scan-today-at", ("time", Clock(copy, moment, now)))
            : Clock(copy, moment, now);

    public static string Number(NativeCopy copy, int value) => value.ToString("N0", copy.Culture);

    /// <summary>How long until the next status read: quick while a scan runs and the panel is open, slow
    /// at rest, and backing off after failures.</summary>
    public static TimeSpan PollDelay(bool panelOpen, bool active, int failures)
    {
        if (failures > 0) return TimeSpan.FromSeconds(Math.Min(300, 15 * Math.Pow(2, Math.Min(failures - 1, 5))));
        return TimeSpan.FromSeconds(active ? (panelOpen ? 3 : 15) : 60);
    }

    /// <summary>The page a browser handoff opens. The dashboard reads its ticket from the fragment and
    /// keeps the path and query, so the route goes between the origin and the ticket.</summary>
    public static Uri Route(Uri handoff, BrowserRoute route)
    {
        if (handoff.AbsolutePath != "/" || handoff.Query != "" || !handoff.Fragment.StartsWith("#roleband=", StringComparison.Ordinal))
            throw new IOException("Invalid browser handoff.");
        var path = route switch
        {
            BrowserRoute.NewRoles => "/?lens=new",
            BrowserRoute.Schedule => "/settings/schedule",
            BrowserRoute.Settings => "/settings",
            _ => "/",
        };
        return new Uri(handoff.GetLeftPart(UriPartial.Authority) + path + handoff.Fragment);
    }
}

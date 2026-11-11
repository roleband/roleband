namespace RoleBand.EngineHost;

/// <summary>The badge drawn into the notification-area icon. Its glyph, not its colour, carries the state.</summary>
public enum TrayBadge { None, Scanning, Paused, Attention, Stopped }

/// <summary>What the menu's bold command does, and with it a double-click on the icon and a second start.</summary>
public enum DefaultCommand { OpenRadar, Settings, Setup }

/// <summary>What a launch does by itself: open setup, ask for the Radar once the engine answers, or nothing.</summary>
public enum LaunchAction { Quiet, Setup, RadarWhenReady }

public enum MenuCommand { OpenRadar = 1, ScanNow, StopScan, PauseHour, PauseThreeHours, PauseTomorrow, Resume, Settings, Restart, FinishSetup, Quit, Update, Undo }

/// <summary>One item of the icon's menu. An entry with neither a command nor items is a separator.</summary>
public sealed record MenuEntry(MenuCommand? Command, string Text, bool Default = false, bool Checked = false, IReadOnlyList<MenuEntry>? Items = null)
{
    public static MenuEntry Separator { get; } = new(null, "");
    public bool IsSeparator => Command is null && Items is null;
}

/// <summary>One summary line. A line with a link ends with it, after a middle dot.</summary>
public sealed record FlyoutLine(string Text, string? Link = null, BrowserRoute? Opens = null);

public enum FlyoutPrimary { OpenRadar, Restart, Undo, CheckUpdates }

/// <summary>Everything the flyout and the icon say for one moment, so the windows have no rules of their own.</summary>
/// <param name="Corner">The percent of a live scan, or its stopwatch while it finishes.</param>
/// <param name="Progress">The scan's progress, present only while a scan runs.</param>
/// <param name="Busy">The state is on its way somewhere else and has no figure to show.</param>
/// <param name="Details">A stopped engine offers Details, which opens Settings with the logs.</param>
/// <param name="Update">The update banner, under the summary while scanning runs.</param>
public sealed record FlyoutView(
    string Title,
    string? Corner,
    double? Progress,
    string? ProgressLabel,
    bool Busy,
    IReadOnlyList<FlyoutLine> Lines,
    FlyoutPrimary Primary,
    bool PrimaryEnabled,
    string? PrimaryHelpKey,
    ScanAction? Scan,
    string? ScanBusyKey,
    PauseControl Pause,
    bool Details,
    TrayBadge Badge,
    string Tooltip,
    FlyoutUpdate? Update = null);

/// <summary>The companion's rules: the flyout's summary and tasks, the icon's badge and tooltip, the menu and
/// its default command. The flyout keeps three parts in every state (summary, tasks, the Settings link); a
/// state changes their words, never their places.</summary>
public static class Companion
{
    /// <summary>The flyout lists this many companies in flight by name; the rest are counted.</summary>
    public const int NamedCompanies = 3;

    /// <param name="update">The update banner: an offer, a download or a failure follows the summary while scanning runs,
    /// and an idle icon's tooltip names the offer; a download keeps its banner, with Cancel, under any summary. While
    /// Windows replaces the app, the stopped engine is that replacement, not a problem.</param>
    public static FlyoutView View(NativeCopy copy, EngineSnapshot engine, ScanStatus? status, ScanAction? requested,
                                  DateTimeOffset? lastScanAt, bool setupComplete, DateTimeOffset now, FlyoutUpdate? update = null)
    {
        if (update is { WholeState: true })
            return new FlyoutView(update.Title, update.Percent is { } percent ? AboutPanel.Percentage(copy, percent) : null, update.Percent, null,
                update.Percent is null, [], FlyoutPrimary.OpenRadar, false, null, null, null, PauseControl.None, false, TrayBadge.Scanning,
                Tip(update.Title));
        var view = Summary(copy, engine, status, requested, lastScanAt, now);
        if (update is not null && (engine.State == EngineState.Ready || update.Cancel))
            view = view with { Update = update, Tooltip = view.Badge == TrayBadge.None ? Tip(update.Title) : view.Tooltip };
        if (!setupComplete && view.Badge != TrayBadge.Stopped)
            view = view with { Badge = TrayBadge.Attention, Tooltip = Tip(copy["setup-pending"]) };
        return view;
    }

    private static FlyoutView Summary(NativeCopy copy, EngineSnapshot engine, ScanStatus? status, ScanAction? requested,
                                      DateTimeOffset? lastScanAt, DateTimeOffset now)
    {
        var last = status?.Presentation.LastScanAt ?? lastScanAt;
        var lastLine = last is { } at ? new FlyoutLine(LastScan(copy, at, now)) : null;
        switch (engine.State)
        {
            case EngineState.Stopped or EngineState.Attention:
            {
                var title = copy["host-stopped"];
                var lines = new List<FlyoutLine>();
                if (engine.State == EngineState.Attention) lines.Add(new FlyoutLine(copy["host-attention-body"]));
                if (lastLine is not null) lines.Add(lastLine);
                return new FlyoutView(title, null, null, null, false, lines, FlyoutPrimary.Restart, true, null,
                    null, null, PauseControl.None, true, TrayBadge.Stopped, Tip(title));
            }
            case not EngineState.Ready:
            {
                var title = copy[TrayModel.For(engine).StatusKey];
                var lines = new List<FlyoutLine>();
                if (engine.State == EngineState.Recovering) lines.Add(new FlyoutLine(copy["host-recovering-body"]));
                if (lastLine is not null) lines.Add(lastLine);
                return new FlyoutView(title, null, null, null, true, lines, FlyoutPrimary.OpenRadar, false, "panel-open-radar-waiting",
                    null, null, PauseControl.None, false, TrayBadge.Scanning, Tip(title));
            }
        }

        var scan = ScanPanel.View(copy, engine, status, requested, now);
        FlyoutView Ready(string title, IReadOnlyList<FlyoutLine> lines, TrayBadge badge, bool busy = false, string? corner = null,
                         double? progress = null, string? progressLabel = null, string? tip = null) =>
            new(title, corner, progress, progressLabel, busy, lines, FlyoutPrimary.OpenRadar, true, "panel-open-radar-help",
                scan.Scan, scan.ScanBusyKey, scan.Pause, false, badge, Tip(tip ?? title));

        if (status is null) return Ready(copy["ready"], lastLine is null ? [] : [lastLine], TrayBadge.None);
        var presentation = status.Presentation;
        if (presentation.Activity == EngineActivity.Updating) return Ready(copy["updating"], [], TrayBadge.Scanning, busy: true);
        if (presentation.Hold is { } hold)
        {
            var reason = ScanPanel.ReasonKey(hold);
            var lines = new List<FlyoutLine>();
            if (reason is not null) lines.Add(new FlyoutLine(copy[reason]));
            if (lastLine is not null) lines.Add(lastLine);
            return Ready(copy[hold.Kind == "attention" ? "needs-attention" : "waiting"], lines, TrayBadge.Attention);
        }

        var picture = status.Picture;
        var phase = ScanPanel.PhaseOf(presentation, picture, requested);
        var schedule = ScanPanel.Schedule(copy, phase, picture, now);
        if (phase is ScanPhase.Scanning or ScanPhase.Stopping)
        {
            var title = copy[ScanPanel.TitleKey(phase, picture)];
            var lines = new List<FlyoutLine>();
            if (phase == ScanPhase.Scanning && picture is not null)
            {
                lines.Add(new FlyoutLine(copy.Format("windows-roles-so-far",
                    ("count", ScanPanel.Number(copy, (picture.RolesPending ?? 0) + (picture.RolesRecorded ?? 0))))));
                if (picture.EveryCompanyRead)
                    lines.Add(new FlyoutLine($"{ScanPanel.Number(copy, picture.CompaniesTotal ?? 0)} {copy["scan-companies-read"]}"));
                else if (picture.InFlight.Count > 0)
                    lines.Add(new FlyoutLine(copy.Format("windows-reading", ("companies", Names(copy, picture.InFlight)))));
            }
            if (schedule is not null) lines.Add(new FlyoutLine(schedule.Text));
            var percent = picture?.Percent is { } value ? Math.Clamp(value, 0, 100) : (int?)null;
            var corner = requested is null ? scan.Corner : null;
            return Ready(title, lines, TrayBadge.Scanning, busy: percent is null, corner: corner, progress: percent,
                progressLabel: percent is null ? null : scan.ProgressLabel,
                tip: percent is { } shown && phase == ScanPhase.Scanning ? $"{title} · {shown}%" : title);
        }
        if (phase == ScanPhase.Requesting)
            return Ready(copy["scan-title-requesting"], schedule is null ? [] : [new FlyoutLine(schedule.Text)], TrayBadge.Scanning, busy: true);

        var facts = Facts(copy, picture);
        if (schedule?.Kind == ScheduleLineKind.Paused)
        {
            // Paused: the pause leads, the last scan and its new roles follow, then what a pause means.
            var lines = new List<FlyoutLine>();
            if (lastLine is not null)
                lines.Add(facts?.Link is { } link ? lastLine with { Link = link, Opens = facts.Opens } : lastLine);
            lines.Add(new FlyoutLine(copy["windows-paused-body"]));
            return Ready(schedule.Text, lines, TrayBadge.Paused);
        }
        var rest = new List<FlyoutLine>();
        if (facts is not null) rest.Add(facts);
        if (schedule is not null) rest.Add(new FlyoutLine(schedule.Text));
        return Ready(lastLine?.Text ?? copy["not-scanned"], rest, TrayBadge.None, tip: copy["ready"]);
    }

    /// <summary>Companies scanned and new roles from the newest finished scan. New roles open the Radar on New, as the
    /// Radar's own New count does; with none the count stays plain.</summary>
    private static FlyoutLine? Facts(NativeCopy copy, ScanPicture? picture)
    {
        if (picture?.LastCompanies is not { } companies) return null;
        var read = $"{ScanPanel.Number(copy, companies)} {copy["scan-companies-read"]}";
        var roles = $"{ScanPanel.Number(copy, picture.LastNewRoles ?? 0)} {copy["scan-new-roles"]}";
        return picture.LastNewRoles > 0 ? new FlyoutLine(read, roles, BrowserRoute.NewRoles) : new FlyoutLine($"{read} · {roles}");
    }

    /// <summary>The first companies in flight by name, then how many more.</summary>
    public static string Names(NativeCopy copy, IReadOnlyList<ScanCompany> companies)
    {
        var named = string.Join(", ", companies.Take(NamedCompanies).Select(company => company.Name));
        return companies.Count <= NamedCompanies ? named
            : copy.Format("windows-and-more", ("names", named), ("count", ScanPanel.Number(copy, companies.Count - NamedCompanies)));
    }

    public static string LastScan(NativeCopy copy, DateTimeOffset moment, DateTimeOffset now)
    {
        var local = moment.ToLocalTime();
        var time = local.ToString(copy.Culture.DateTimeFormat.ShortTimePattern, copy.Culture);
        return local.Date == now.ToLocalTime().Date
            ? copy.Format("windows-last-scan-today", ("time", time))
            : copy.Format("windows-last-scan-on", ("date", local.ToString(copy.Culture.DateTimeFormat.MonthDayPattern, copy.Culture)), ("time", time));
    }

    /// <summary>The icon's tooltip: product name and state on one line, within the shell's 127-character limit.</summary>
    public static string Tip(string state)
    {
        var text = "RoleBand: " + state.Replace('\n', ' ');
        return text.Length <= 127 ? text : text[..126] + "…";
    }

    /// <summary>Setup while it is unfinished; Settings, which holds the problem and Restart, while scanning has
    /// stopped; otherwise the Radar, which an engine still starting opens once it answers.</summary>
    public static DefaultCommand Default(EngineSnapshot engine, bool setupComplete) =>
        !setupComplete ? DefaultCommand.Setup
        : engine.State is EngineState.Stopped or EngineState.Attention ? DefaultCommand.Settings
        : DefaultCommand.OpenRadar;

    /// <summary>A launch from Start does what Start means while the app runs. The engine has not started yet at that
    /// moment, so the Radar waits for it to answer; unfinished setup comes first, and a start at sign-in stays quiet.</summary>
    public static LaunchAction AtLaunch(SetupRecord setup, bool atLogin) =>
        SetupFlow.ShowAtLaunch(setup, atLogin) ? LaunchAction.Setup
        : !atLogin && setup.Complete ? LaunchAction.RadarWhenReady
        : LaunchAction.Quiet;

    /// <summary>Where a Radar asked for before the engine answered goes once the engine settles: the Radar when it
    /// answers, Settings with the reason when it stopped with one; null while it is still on its way.</summary>
    public static DefaultCommand? WhenSettled(EngineSnapshot engine) => engine.State switch
    {
        EngineState.Ready => DefaultCommand.OpenRadar,
        EngineState.Attention => DefaultCommand.Settings,
        EngineState.Stopped when engine.Diagnostic is not null => DefaultCommand.Settings,
        _ => null,
    };

    /// <summary>The icon's menu, in the order Windows gives tray menus: the default command first and bold, the
    /// scan's tasks, a pause shown as a checked state, then Settings, and Quit last. Items that don't apply are left
    /// out rather than greyed; whether an update keeps Restart out is <see cref="AppSurfaces"/>' rule.</summary>
    public static IReadOnlyList<MenuEntry> Menu(NativeCopy copy, EngineSnapshot engine, FlyoutView view, bool setupComplete)
    {
        var quit = new MenuEntry(MenuCommand.Quit, copy["windows-quit"]);
        var settings = new MenuEntry(MenuCommand.Settings, copy["settings"]);
        switch (Default(engine, setupComplete))
        {
            case DefaultCommand.Setup:
                return [new MenuEntry(MenuCommand.FinishSetup, copy["setup-finish"], Default: true), settings, MenuEntry.Separator, quit];
            case DefaultCommand.Settings:
                return [settings with { Default = true }, new MenuEntry(MenuCommand.Restart, copy["windows-restart-scanning"]), MenuEntry.Separator, quit];
        }
        // Before the engine first answers, Open Radar has nothing to open yet.
        if (!TrayModel.For(engine).CanOpenRadar) return [settings, MenuEntry.Separator, quit];
        var items = new List<MenuEntry> { new(MenuCommand.OpenRadar, copy["first-open"], Default: true) };
        if (view.ScanBusyKey is null && view.Scan is { } action)
            items.Add(action == ScanAction.Start ? new MenuEntry(MenuCommand.ScanNow, copy["scan-now"]) : new MenuEntry(MenuCommand.StopScan, copy["scan-stop"]));
        // A pause can only be lifted, not changed, so a paused menu offers Resume alone.
        if (view.Pause == PauseControl.Resume)
            items.Add(new MenuEntry(null, copy["pause-menu"], Checked: true, Items: [new MenuEntry(MenuCommand.Resume, copy["pause-resume"])]));
        else if (view.Pause == PauseControl.Menu)
            items.Add(new MenuEntry(null, copy["pause-menu"], Items:
            [
                new MenuEntry(MenuCommand.PauseHour, copy["pause-hour"]),
                new MenuEntry(MenuCommand.PauseThreeHours, copy["pause-three-hours"]),
                new MenuEntry(MenuCommand.PauseTomorrow, copy["pause-tomorrow"]),
            ]));
        // An update ready to install is one press here too, named by its version; a download under way has no item.
        if (view.Update is { Action: not null } update)
            items.AddRange([MenuEntry.Separator, new MenuEntry(MenuCommand.Update, copy.Format("windows-update-to", ("version", update.Version)))]);
        items.AddRange([MenuEntry.Separator, settings, MenuEntry.Separator, quit]);
        return items;
    }

    public static PauseAction? Pause(MenuCommand command) => command switch
    {
        MenuCommand.PauseHour => PauseAction.Hour,
        MenuCommand.PauseThreeHours => PauseAction.ThreeHours,
        MenuCommand.PauseTomorrow => PauseAction.Tomorrow,
        MenuCommand.Resume => PauseAction.Resume,
        _ => null,
    };
}

/// <summary>The Settings window's problem banner: a stopped engine with Restart and its logs, an update the
/// previous run could not finish with Undo, or an app that could not start at all.</summary>
/// <param name="Restart">The banner offers Restart, which starts the engine again.</param>
/// <param name="Version">The version its title and body name; an undo under way names the version it returns to.</param>
/// <param name="Busy">Something is under way that ends with Windows closing the app, so the banner shows progress.</param>
/// <param name="Notice">News, not a fault: an undo under way.</param>
/// <param name="Newer">A newer release that can replace a failed update, offered beside Undo.</param>
/// <param name="Percent">Windows' percentage of what is under way, when it reports one.</param>
public sealed record SettingsProblem(string TitleKey, string? BodyKey, bool Undo, bool Restart, string? Version = null, bool Busy = false,
                                     bool Notice = false, string? Newer = null, int? Percent = null)
{
    /// <summary>The banner's title and message in the copy's words, the version filled in where the words name it: a
    /// message that names none would refuse it, and one that names it without a version to fill is an error.</summary>
    public (string Title, string? Message) Words(NativeCopy copy) => (Say(copy, TitleKey), BodyKey is { } body ? Say(copy, body) : null);

    private string Say(NativeCopy copy, string key) =>
        !copy.Takes(key, "version") ? copy[key] : copy.Format(key, Version is { } version ? [("version", version)] : []);
}

public static class SettingsPanel
{
    /// <summary>The installation could not be read, so there is no engine to restart.</summary>
    public static SettingsProblem LaunchFailed { get; } = new("invalid", null, false, false);

    /// <param name="held">Setup holds the engine until Welcome's Continue: that is not a stop, and Restart would
    /// start what setup holds.</param>
    /// <param name="installing">Windows is replacing the app for an update, which stops the engine on purpose.</param>
    /// <param name="returningTo">An Undo returns to this version: Windows replaces the app and opens it again.</param>
    /// <param name="returning">This session pressed Undo and is waiting for Windows. Otherwise the Undo is not on its way:
    /// it was refused, or the app opened with it unfinished, and it couldn't return, with Undo one press away.</param>
    /// <param name="undoFailure">Why the last Undo was refused; the banner says so, with Try again and the reason below.</param>
    /// <param name="newer">A newer release offered while an update has failed: it can replace the failed version.</param>
    public static SettingsProblem? Problem(EngineSnapshot engine, bool updateFailed, bool held, bool installing = false,
                                           string? returningTo = null, bool returning = false, string? undoFailure = null,
                                           string? newer = null, bool undoGone = false)
    {
        if (held || installing) return null;
        if (returningTo is not null && !returning)
            return undoGone ? new("windows-update-undo-failed", "windows-update-undo-gone-body", false, false, returningTo, Newer: newer)
                // Without a reason, the body names none below it.
                : new("windows-update-undo-failed", undoFailure is null ? "update-stopped-body" : "windows-update-undo-failed-body", true, false,
                    returningTo, Newer: newer);
        if (returningTo is not null)
            return new("windows-update-undoing", "windows-update-undoing-body", false, false, returningTo, true, Notice: true);
        // A failed update keeps the engine closed until it is undone or replaced, so Restart would do nothing.
        if (updateFailed && engine.State != EngineState.Ready)
            return new("update-stopped-title", "update-stopped-body", true, false, Newer: newer);
        return engine.State switch
        {
            EngineState.Attention => new("host-stopped", "host-attention-body", false, true),
            EngineState.Stopped => new("host-stopped", null, false, true),
            _ => null,
        };
    }
}

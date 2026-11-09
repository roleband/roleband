namespace RoleBand.EngineHost;

/// <summary>The update side of the app at one moment: what the update commands report, this session's own update,
/// and an Undo under way.</summary>
/// <param name="Failed">The coordinator found this version's update unfinished or failed when the app opened.</param>
/// <param name="ReturningTo">An Undo is returning to this version.</param>
/// <param name="Returning">This session pressed Undo and waits for Windows.</param>
/// <param name="UndoFailure">Why the last Undo was refused.</param>
public sealed record UpdateState(
    UpdateFacts? Facts = null,
    UpdateRun? Run = null,
    bool Checking = false,
    string? LastResult = null,
    bool Failed = false,
    string? ReturningTo = null,
    bool Returning = false,
    string? UndoFailure = null)
{
    /// <summary>This version is an update that could not prepare, as the coordinator or the journal says.</summary>
    public bool UpdateFailed => Failed || Facts?.Last is { Unfinished: true };

    /// <summary>An Update or an Undo is in Windows' hands: nothing else may start.</summary>
    public bool Switching => Run is { InProgress: true } || Returning;

    /// <summary>The release an Update press installs, when one can be pressed.</summary>
    public string? Installable => Switching || ReturningTo is not null ? null : Facts?.Offer;
}

/// <summary>Everything the app's surfaces are drawn from, so the panel, the menu and Settings cannot disagree.</summary>
/// <param name="Engine">Null when the installation could not be read, with the reason in <paramref name="LaunchFailure"/>.</param>
public sealed record AppState(
    EngineSnapshot? Engine,
    string? LaunchFailure,
    SetupRecord Setup,
    UpdateState Update,
    DateTimeOffset Now,
    ScanStatus? Scan = null,
    ScanAction? Requested = null,
    DateTimeOffset? LastScanAt = null)
{
    public bool SetupHeld => SetupFlow.EngineHeld(Setup);

    /// <summary>Restart can start the engine: it is stopped, nothing holds it, and no update keeps it closed.</summary>
    public bool CanStart => Engine is { State: EngineState.Stopped or EngineState.Attention } && !SetupHeld
        && !Update.UpdateFailed && Update.ReturningTo is null && !Update.Switching;

    /// <summary>Undo can return to the version before a failed update, unless Windows is already installing something.</summary>
    public bool CanUndo => Engine is not null && Update.UpdateFailed && !Update.Switching;
}

/// <summary>The app's surfaces for one state: the flyout, the icon's menu and its default command, Settings' problem
/// banner and its updates card.</summary>
public sealed record Surfaces(FlyoutView Flyout, IReadOnlyList<MenuEntry> Menu, DefaultCommand Default, SettingsProblem? Problem,
                              UpdateRow Updates);

/// <summary>Draws every surface from one <see cref="AppState"/>. A control appears only in a state where pressing it
/// does something: the rules for that live here, once.</summary>
public static class AppSurfaces
{
    public static Surfaces Of(NativeCopy copy, AppState state)
    {
        var update = state.Update;
        var facts = update.Facts;
        var row = AboutPanel.Updates(copy, facts, update.Checking, update.LastResult, state.Now, update.Run);
        // A failed update is never up to date or a finished result, even before the journal has been read.
        if (update.UpdateFailed && row.Kind is UpdateRowKind.Current or UpdateRowKind.Never or UpdateRowKind.Updated)
            row = row with
            {
                Kind = UpdateRowKind.Unfinished,
                Title = facts?.Last?.To is { } failedVersion ? copy.Format("windows-update-unfinished", ("version", failedVersion))
                    : copy["update-stopped-title"],
                Caption = copy["windows-update-unfinished-caption"],
            };
        // An Undo under way is in Windows' hands: nothing to check, and nothing to install over it.
        if (update.ReturningTo is not null) row = row with { CanCheck = row.CanCheck && !update.Returning, Action = null };
        else if (update.Installable is null) row = row with { Action = null };
        if (state.Engine is not { } engine)
        {
            var title = copy["invalid"];
            var view = new FlyoutView(title, null, null, null, false, state.LaunchFailure is null ? [] : [new FlyoutLine(state.LaunchFailure)],
                FlyoutPrimary.Restart, false, null, null, null, PauseControl.None, true, TrayBadge.Stopped, Companion.Tip(title));
            return new Surfaces(view, [Settings(copy) with { Default = true }, MenuEntry.Separator, Quit(copy)], DefaultCommand.Settings,
                SettingsPanel.LaunchFailed, row);
        }
        var banner = AboutPanel.Flyout(copy, facts, update.Run, update.ReturningTo);
        // With no running engine to summarise, an update under way is the flyout's whole state.
        if (banner is { Busy: true } && engine.State != EngineState.Ready) banner = banner with { Restarting = true };
        var problem = SettingsPanel.Problem(engine, update.UpdateFailed, state.SetupHeld, update.Run is { Step: UpdateStep.Restarting },
            update.ReturningTo, update.Returning, update.UndoFailure, update.Installable);
        if (update.UpdateFailed && update.ReturningTo is null && !update.Switching)
            return FailedUpdate(copy, state, banner, problem, row);
        var flyout = Companion.View(copy, engine, state.Scan, state.Requested, state.LastScanAt, state.Setup.Complete, state.Now, banner);
        var menu = Companion.Menu(copy, engine, flyout, state.Setup.Complete);
        // Restart only where it can start the engine: not while setup holds it, nor while an update or an Undo is under way.
        if (!state.CanStart)
        {
            if (flyout.Primary == FlyoutPrimary.Restart) flyout = flyout with { PrimaryEnabled = false };
            menu = [.. menu.Where(entry => entry.Command != MenuCommand.Restart)];
            if (problem is { Restart: true }) problem = problem with { Restart = false };
        }
        // Undo only where it can run: never over a download or an install already in Windows' hands.
        if (!state.CanUndo && problem is { Undo: true }) problem = problem with { Undo = false };
        return new Surfaces(flyout, menu, Companion.Default(engine, state.Setup.Complete), problem, row);
    }

    /// <summary>A failed update keeps the engine closed until it is undone or replaced: the flyout and the menu lead with
    /// Undo, offer a newer release beside it, and never Restart, which would do nothing.</summary>
    private static Surfaces FailedUpdate(NativeCopy copy, AppState state, FlyoutUpdate? banner, SettingsProblem? problem, UpdateRow row)
    {
        var title = copy["update-stopped-title"];
        var newer = state.Update.Installable;
        var flyout = new FlyoutView(title, null, null, null, false, [new FlyoutLine(copy["update-stopped-body"])], FlyoutPrimary.Undo, true,
            null, null, null, PauseControl.None, true, TrayBadge.Attention, Companion.Tip(title),
            banner is { Action: not null } && newer is not null ? banner : null);
        var menu = new List<MenuEntry> { Settings(copy) with { Default = true }, new(MenuCommand.Undo, copy["update-undo"]) };
        if (newer is not null) menu.Add(new MenuEntry(MenuCommand.Update, copy.Format("windows-update-to", ("version", newer))));
        menu.AddRange([MenuEntry.Separator, Quit(copy)]);
        return new Surfaces(flyout, menu, DefaultCommand.Settings, problem, row);
    }

    private static MenuEntry Settings(NativeCopy copy) => new(MenuCommand.Settings, copy["settings"]);

    private static MenuEntry Quit(NativeCopy copy) => new(MenuCommand.Quit, copy["windows-quit"]);
}

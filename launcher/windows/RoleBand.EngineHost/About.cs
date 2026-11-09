using System.Text.Json;

namespace RoleBand.EngineHost;

/// <summary>The last package update as the running version sees it, from the update journal.</summary>
/// <param name="Running">"from" or "to" when this version is one end of it; null otherwise.</param>
public sealed record LastUpdate(string Phase, string From, string To, string? Running)
{
    /// <summary>How it ended, for this version to say: Updated to the new version, or Back on the previous one.</summary>
    public UpdateRun? Result => (Phase, Running) switch
    {
        ("complete", "to") => new UpdateRun(UpdateStep.Updated, To),
        ("recovered", "from") => new UpdateRun(UpdateStep.RolledBack, From, To),
        _ => null,
    };
}

/// <summary>What the update commands report: whether this build updates itself, the person's choice,
/// the last check the feed answered, a verified offer and a rate limit. Read from <c>update status</c>,
/// which asks nothing of the network, or from a check's own answer.</summary>
/// <param name="Last">The last package update, which says how it ended or that it is being undone.</param>
public sealed record UpdateFacts(bool Available, bool Automatic, DateTimeOffset? CheckedAt, string? Offer, DateTimeOffset? RateLimitedUntil,
                                 LastUpdate? Last = null)
{
    /// <summary>A build that does not update itself, or an app without an engine to ask.</summary>
    public static UpdateFacts Unavailable { get; } = new(false, false, null, null, null);

    public static UpdateFacts Read(JsonElement reply)
    {
        if (reply.ValueKind != JsonValueKind.Object || !reply.TryGetProperty("status", out var status) || status.ValueKind != JsonValueKind.String)
            throw new IOException("The update command's answer could not be read.");
        if (status.GetString() == "unavailable") return Unavailable;
        var offer = reply.TryGetProperty("offer", out var value) ? value.ValueKind switch
        {
            JsonValueKind.String => value.GetString(),
            JsonValueKind.Object when value.TryGetProperty("version", out var version) => version.GetString(),
            _ => null,
        } : null;
        return new UpdateFacts(true,
            reply.TryGetProperty("automatic", out var automatic) && automatic.ValueKind == JsonValueKind.True,
            Moment(reply, "checked_at"), offer, Moment(reply, "rate_limited_until") ?? Moment(reply, "until"), ReadLast(reply));
    }

    private static LastUpdate? ReadLast(JsonElement reply)
    {
        if (!reply.TryGetProperty("update", out var update) || update.ValueKind != JsonValueKind.Object) return null;
        static string? Text(JsonElement value, string name) =>
            value.TryGetProperty(name, out var field) && field.ValueKind == JsonValueKind.String ? field.GetString() : null;
        return Text(update, "phase") is { } phase && Text(update, "from") is { } from && Text(update, "to") is { } to
            ? new LastUpdate(phase, from, to, Text(update, "running")) : null;
    }

    private static DateTimeOffset? Moment(JsonElement reply, string name) =>
        reply.TryGetProperty(name, out var value) && value.ValueKind == JsonValueKind.Number
            ? DateTimeOffset.FromUnixTimeMilliseconds((long)(value.GetDouble() * 1000)) : null;
}

/// <summary>Where this session's own update stands, from the press of Update to the result the next version shows.</summary>
public enum UpdateStep { Downloading, Restarting, DownloadFailed, CheckFailed, RestartFailed, Updated, RolledBack }

/// <param name="Version">The version being installed; for a result, the version now running.</param>
/// <param name="Undone">For Back on, the version that was undone.</param>
public sealed record UpdateRun(UpdateStep Step, string Version, string? Undone = null)
{
    public bool InProgress => Step is UpdateStep.Downloading or UpdateStep.Restarting;

    public bool Failed => Step is UpdateStep.DownloadFailed or UpdateStep.CheckFailed or UpdateStep.RestartFailed;

    /// <summary>What a download's answer leads to: the verified package to install, or the failure it reports. A
    /// package that is not the signed release failed its check; anything else is a download that did not finish.</summary>
    public static (UpdateRun Run, string? Package) Downloaded(JsonElement reply, string version)
    {
        static string? Text(JsonElement reply, string name) =>
            reply.ValueKind == JsonValueKind.Object && reply.TryGetProperty(name, out var value) && value.ValueKind == JsonValueKind.String
                ? value.GetString() : null;
        if (Text(reply, "status") == "downloaded" && Text(reply, "package") is { Length: > 0 } package)
            return (new UpdateRun(UpdateStep.Restarting, version), package);
        return (new UpdateRun(Text(reply, "kind") == "check" ? UpdateStep.CheckFailed : UpdateStep.DownloadFailed, version), null);
    }
}

public enum UpdateRowKind { Unavailable, Checking, Failed, Never, Offered, Current, Downloading, Restarting, UpdateFailed, Updated }

/// <param name="CanCheck">Check now stays on every state but a check or an update already running, so a failure is one
/// press from a retry.</param>
/// <param name="Action">The words of the Update press, which installs the offered version; null when there is none.</param>
public sealed record UpdateRow(UpdateRowKind Kind, string Title, string? Caption, bool CanCheck, bool Automatic, bool AutomaticEnabled,
                               string? Action = null)
{
    public bool Busy => Kind is UpdateRowKind.Checking or UpdateRowKind.Downloading or UpdateRowKind.Restarting;
}

/// <summary>The flyout's update banner: an offer with Update, the download, or a failure with Try again; and whether
/// Windows is replacing the app, which stops the engine on purpose.</summary>
/// <param name="Version">The version the banner is about, which the menu's Update names.</param>
/// <param name="Action">The words of its press; null while the download runs.</param>
public sealed record FlyoutUpdate(string Title, string? Caption, string? Action, string Version, bool Busy, bool Failed, bool Restarting);

/// <param name="On">Windows' own state; Settings shows what is registered, not a proposal.</param>
public sealed record LoginRow(bool On, bool Enabled, string CaptionKey, bool Settings, bool Visible);

public static class AboutPanel
{
    /// <summary>The choice's words are pinned in English and recorded as shown, with their language.</summary>
    public const string ConsentLanguage = "en";
    public const string ConsentKey = "update-automatic";

    public static string ConsentText() => new NativeCopy(ConsentLanguage)[ConsentKey];

    /// <summary>The automatic-check switch is labelled with the words its choice records, in every language: what the
    /// person agreed to is what they read.</summary>
    public static string AutomaticLabel => ConsentText();

    /// <param name="lastResult">The status of this session's last check, if any.</param>
    /// <summary>The version Settings shows: an installed package's own, else the engine's. A release package is its
    /// release version with a zero revision and shows as that release, like the update offers; a trial's package
    /// version counts its builds and differs from the engine's.</summary>
    public static string Version(string engineVersion, (ushort Major, ushort Minor, ushort Build, ushort Revision)? package) =>
        package is not { } v ? engineVersion
        : v.Revision == 0 ? $"{v.Major}.{v.Minor}.{v.Build}" : $"{v.Major}.{v.Minor}.{v.Build}.{v.Revision}";

    /// <param name="run">This session's own update, if Update was pressed or the app opened as the result of one.</param>
    public static UpdateRow Updates(NativeCopy copy, UpdateFacts? facts, bool checking, string? lastResult, DateTimeOffset now,
                                    UpdateRun? run = null)
    {
        if (facts is { Available: false }) return new UpdateRow(UpdateRowKind.Unavailable, copy["windows-updates-unavailable"], null, false, false, false);
        var automatic = facts?.Automatic ?? false;
        var checkedCaption = facts?.CheckedAt is { } at ? copy.Format("panel-checked", ("time", ScanPanel.Clock(copy, at, now))) : null;
        if (run is { Step: UpdateStep.Downloading })
            return new UpdateRow(UpdateRowKind.Downloading, copy.Format("update-downloading", ("version", run.Version)), checkedCaption, false, automatic, true);
        if (run is { Step: UpdateStep.Restarting })
            return new UpdateRow(UpdateRowKind.Restarting, copy["update-restarting"], null, false, automatic, true);
        if (checking) return new UpdateRow(UpdateRowKind.Checking, copy["panel-status-checking"], checkedCaption, false, automatic, true);
        // A newer offer replaces the last update's result; the same offer keeps its failure and Try again.
        if (run is { Failed: true } && (facts?.Offer is null || facts.Offer == run.Version))
        {
            var (title, caption) = run.Step switch
            {
                UpdateStep.CheckFailed => (copy.Format("update-check-failed", ("version", run.Version)), copy["update-nothing-installed"]),
                UpdateStep.RestartFailed => (copy["update-restart-failed"], copy["update-nothing-installed"]),
                _ => (copy.Format("update-download-failed", ("version", run.Version)), copy["update-download-failed-caption"]),
            };
            return new UpdateRow(UpdateRowKind.UpdateFailed, title, caption, true, automatic, true, copy["retry"]);
        }
        var limited = facts?.RateLimitedUntil is { } until && until > now;
        if (limited || lastResult is "failed" or "rate-limited")
            return new UpdateRow(UpdateRowKind.Failed, copy["panel-status-failed"],
                limited || lastResult == "rate-limited" ? copy["update-rate-limited"] : checkedCaption, true, automatic, true);
        if (facts?.Offer is { } version)
            return new UpdateRow(UpdateRowKind.Offered, copy.Format("update-ready", ("version", version)), checkedCaption, true, automatic, true,
                copy["update-install"]);
        // How the last update ended, as its journal says, so it holds across restarts until a newer offer.
        if ((run is { Step: UpdateStep.Updated or UpdateStep.RolledBack } ? run : facts?.Last?.Result) is { } result)
            return new UpdateRow(UpdateRowKind.Updated,
                copy.Format(result.Step == UpdateStep.Updated ? "update-updated" : "update-rolled-back", ("version", result.Version)),
                result.Undone is { } undone ? copy.Format("update-rolled-back-caption", ("version", undone)) : checkedCaption,
                true, automatic, true);
        if (facts?.CheckedAt is not null)
            return new UpdateRow(UpdateRowKind.Current, copy["panel-status-up-to-date"], checkedCaption, true, automatic, true);
        return new UpdateRow(UpdateRowKind.Never, copy["update-idle"], null, true, automatic, true);
    }

    /// <summary>The flyout's banner for an update: the offer with Update, the download, the switch, or a failure with Try
    /// again. Results stay in Settings.</summary>
    /// <param name="returningTo">The version an Undo under way returns to: Windows is replacing the app.</param>
    public static FlyoutUpdate? Flyout(NativeCopy copy, UpdateFacts? facts, UpdateRun? run, string? returningTo = null)
    {
        if (returningTo is not null)
            return new FlyoutUpdate(copy.Format("windows-update-undoing", ("version", returningTo)), null, null, returningTo, true, false, true);
        if (facts is { Available: false }) return null;
        var row = Updates(copy, facts, false, null, DateTimeOffset.MinValue, run);
        return row.Kind switch
        {
            UpdateRowKind.Downloading or UpdateRowKind.Restarting =>
                new FlyoutUpdate(row.Title, null, null, run!.Version, true, false, row.Kind == UpdateRowKind.Restarting),
            UpdateRowKind.Offered => new FlyoutUpdate(row.Title, null, row.Action, facts!.Offer!, false, false, false),
            UpdateRowKind.UpdateFailed => new FlyoutUpdate(row.Title, row.Caption, row.Action, run!.Version, false, true, false),
            _ => null,
        };
    }

    /// <summary>Open at login in its real states. A copy without a package has no startup task, so the row is hidden.</summary>
    public static LoginRow Login(LoginState state, bool busy) => state switch
    {
        LoginState.Unavailable => new LoginRow(false, false, "first-login-caption", false, false),
        LoginState.Approval => new LoginRow(false, !busy, "windows-login-approval", true, true),
        LoginState.ManagedOn => new LoginRow(true, false, "windows-login-managed", false, true),
        LoginState.ManagedOff => new LoginRow(false, false, "windows-login-managed", false, true),
        _ => new LoginRow(state == LoginState.On, !busy, "first-login-caption", false, true),
    };

    /// <summary>How often the app asks the engine to run an automatic check; the engine itself allows one a day
    /// and none without the person's choice.</summary>
    public static readonly TimeSpan AutomaticInterval = TimeSpan.FromHours(6);
}

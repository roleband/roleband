using System.Text.Json;

namespace RoleBand.EngineHost;

/// <summary>The last package update as the running version sees it, from the update journal.</summary>
/// <param name="Running">"from" or "to" when this version is one end of it; null otherwise.</param>
/// <param name="Since">When the journal last changed: for an update still applying, when it began.</param>
/// <param name="Package">The release file Windows was given to install.</param>
public sealed record LastUpdate(string Phase, string From, string To, string? Running, DateTimeOffset? Since = null, string? Package = null)
{
    /// <summary>This version is the update's new one and is still preparing: the person waits on the update, not on a fault.</summary>
    public bool Finishing => Running == "to" && Phase is "applying" or "preparing";

    /// <summary>This version is the update's new one and could not prepare: Undo, or a newer release, is the way on.</summary>
    public bool Unfinished => Running == "to" && Phase is "failed" or "recovering";

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
            ? new LastUpdate(phase, from, to, Text(update, "running"), Moment(update, "since"), Text(update, "package")) : null;
    }

    private static DateTimeOffset? Moment(JsonElement reply, string name) =>
        reply.TryGetProperty(name, out var value) && value.ValueKind == JsonValueKind.Number
            ? DateTimeOffset.FromUnixTimeMilliseconds((long)(value.GetDouble() * 1000)) : null;
}

/// <summary>Where this session's own update stands, from the press of Update to the result the next version shows.</summary>
/// <remarks>Paused is a download that lost its connection: it resumes by itself, and Cancel stops it.</remarks>
public enum UpdateStep { Downloading, Paused, Restarting, DownloadFailed, CheckFailed, NoSpace, RestartFailed, Updated, RolledBack }

/// <param name="Version">The version being installed; for a result, the version now running.</param>
/// <param name="Undone">For Back on, the version that was undone.</param>
/// <param name="Percent">While Windows installs, its own percentage of the install.</param>
/// <param name="Reason">Why Windows did not install it, in Windows' words.</param>
/// <param name="Received">The bytes downloaded so far, of <paramref name="Total"/>.</param>
/// <param name="Needed">For Not enough space, the free space the download and its install need.</param>
public sealed record UpdateRun(UpdateStep Step, string Version, string? Undone = null, int? Percent = null, string? Reason = null,
                               long? Received = null, long? Total = null, long? Needed = null)
{
    public bool InProgress => Step is UpdateStep.Downloading or UpdateStep.Paused or UpdateStep.Restarting;

    public bool Failed => Step is UpdateStep.DownloadFailed or UpdateStep.CheckFailed or UpdateStep.NoSpace or UpdateStep.RestartFailed;

    /// <summary>A download Cancel can stop: one running, or one waiting for the connection.</summary>
    public bool Cancellable => Step is UpdateStep.Downloading or UpdateStep.Paused;

    /// <summary>What a download's answer leads to: the verified package to install, or the failure it reports. A
    /// package that is not the signed release failed its check; a lost connection pauses the download; a full disk
    /// says how much room it needs; anything else is a download that did not finish. Progress so far is kept.</summary>
    public static (UpdateRun Run, string? Package) Downloaded(JsonElement reply, string version, UpdateRun? before = null)
    {
        static string? Text(JsonElement reply, string name) =>
            reply.ValueKind == JsonValueKind.Object && reply.TryGetProperty(name, out var value) && value.ValueKind == JsonValueKind.String
                ? value.GetString() : null;
        if (Text(reply, "status") == "downloaded" && Text(reply, "package") is { Length: > 0 } package)
            return (new UpdateRun(UpdateStep.Restarting, version), package);
        var run = new UpdateRun(UpdateStep.DownloadFailed, version, Received: before?.Received, Total: before?.Total);
        return (Text(reply, "kind") switch
        {
            "check" => run with { Step = UpdateStep.CheckFailed },
            "offline" => run with { Step = UpdateStep.Paused },
            "space" => run with
            {
                Step = UpdateStep.NoSpace,
                Needed = Count(reply, "needed"),
            },
            _ => run,
        }, null);
    }

    private static long? Count(JsonElement value, string name) =>
        value.ValueKind == JsonValueKind.Object && value.TryGetProperty(name, out var field) && field.ValueKind == JsonValueKind.Number
        && field.TryGetInt64(out var count) ? count : null;

    /// <summary>The download's progress from one line the download command writes while it runs; null for any other line.</summary>
    public static (long Received, long Total)? Progress(string line)
    {
        try
        {
            using var document = JsonDocument.Parse(line);
            var root = document.RootElement;
            return root.ValueKind == JsonValueKind.Object && Count(root, "received") is { } got && Count(root, "total") is { } of
                && of > 0 && got >= 0
                ? (Math.Min(got, of), of) : null;
        }
        catch (JsonException) { return null; }
    }
}

public enum UpdateRowKind
{
    Unavailable, Checking, Failed, Never, Offered, Current, Downloading, Paused, Restarting, UpdateFailed, Updated, Finishing, Unfinished,
}

/// <param name="CanCheck">Check now stays on every state but a check or an update already running, so a failure is one
/// press from a retry.</param>
/// <param name="Action">The words of the Update press, which installs the offered version; null when there is none.</param>
/// <param name="Cancel">A download under way, or waiting for the connection, that Cancel stops.</param>
/// <param name="HelpKey">Copy for a tooltip that says more than the caption.</param>
public sealed record UpdateRow(UpdateRowKind Kind, string Title, string? Caption, bool CanCheck, bool Automatic, bool AutomaticEnabled,
                               string? Action = null, bool Cancel = false, string? HelpKey = null)
{
    public bool Busy => Kind is UpdateRowKind.Checking or UpdateRowKind.Downloading or UpdateRowKind.Restarting or UpdateRowKind.Finishing;
}

/// <summary>The flyout's update banner: an offer with Update, the download with Cancel, or a failure with Try again; and
/// whether Windows is replacing the app, which stops the engine on purpose.</summary>
/// <param name="Version">The version the banner is about, which the menu's Update names.</param>
/// <param name="Action">The words of its press; null while the download runs.</param>
/// <param name="Percent">How far the download, or Windows' install, has got.</param>
/// <param name="Cancel">The download can be stopped from the banner.</param>
public sealed record FlyoutUpdate(string Title, string? Caption, string? Action, string Version, bool Busy, bool Failed, bool Restarting,
                                  int? Percent = null, bool Cancel = false);

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
            return new UpdateRow(UpdateRowKind.Downloading, copy.Format("update-downloading", ("version", run.Version)), Received(copy, run),
                false, automatic, true, Cancel: true);
        // A lost connection pauses the download, which tries again by itself; the bytes it has stay.
        if (run is { Step: UpdateStep.Paused })
            return new UpdateRow(UpdateRowKind.Paused, copy["update-paused"],
                Received(copy, run) is { } received ? $"{received} · {copy["update-paused-caption"]}" : copy["update-paused-caption"],
                false, automatic, true, Cancel: true);
        // Windows installs while this version stays open; it closes it at the very end and opens the new one.
        if (run is { Step: UpdateStep.Restarting })
        {
            var reopens = copy.Format("windows-update-installing-body", ("version", run.Version));
            return run.Percent is 100
                ? new UpdateRow(UpdateRowKind.Restarting, copy["update-restarting"], reopens, false, automatic, true)
                : new UpdateRow(UpdateRowKind.Restarting, copy.Format("windows-update-installing", ("version", run.Version)),
                    run.Percent is { } percent ? $"{Percentage(copy, percent)} · {reopens}" : reopens, false, automatic, true);
        }
        // The version Windows just installed is still preparing: say what the wait is for.
        if (facts?.Last is { Finishing: true } finishing)
            return new UpdateRow(UpdateRowKind.Finishing, copy.Format("windows-update-finishing", ("version", finishing.To)), null, false,
                automatic, true);
        if (checking) return new UpdateRow(UpdateRowKind.Checking, copy["panel-status-checking"], checkedCaption, false, automatic, true);
        // The same offer keeps its failure and Try again; a newer offer, or none any more, replaces it, since Try again
        // installs the offer.
        if (run is { Failed: true } && facts?.Offer == run.Version)
        {
            var (title, caption) = run.Step switch
            {
                UpdateStep.CheckFailed => (copy.Format("update-check-failed", ("version", run.Version)), copy["update-nothing-installed"]),
                UpdateStep.NoSpace => (copy["update-no-space"],
                    run.Needed is { } needed ? copy.Format("update-no-space-caption", ("size", Size(copy, needed))) : copy["update-nothing-installed"]),
                UpdateStep.RestartFailed => (copy.Format("windows-update-install-failed", ("version", run.Version)),
                    run.Reason is { Length: > 0 } reason ? $"{copy["update-nothing-installed"]} {reason}" : copy["update-nothing-installed"]),
                _ => (copy.Format("update-download-failed", ("version", run.Version)), copy["update-download-failed-caption"]),
            };
            return new UpdateRow(UpdateRowKind.UpdateFailed, title, caption, true, automatic, true, copy["retry"],
                HelpKey: run.Step switch
                {
                    UpdateStep.NoSpace => "update-no-space-help",
                    UpdateStep.CheckFailed => "update-check-failed-help",
                    _ => null,
                });
        }
        var limited = facts?.RateLimitedUntil is { } until && until > now;
        if (limited || lastResult is "failed" or "rate-limited")
            return new UpdateRow(UpdateRowKind.Failed, copy["panel-status-failed"],
                limited || lastResult == "rate-limited" ? copy["update-rate-limited"] : checkedCaption, true, automatic, true);
        if (facts?.Offer is { } version)
            return new UpdateRow(UpdateRowKind.Offered, copy.Format("update-ready", ("version", version)), checkedCaption, true, automatic, true,
                copy["update-install"]);
        // This version is an update that could not prepare: never "up to date", whatever the feed says.
        if (facts?.Last is { Unfinished: true } unfinished)
            return new UpdateRow(UpdateRowKind.Unfinished, copy.Format("windows-update-unfinished", ("version", unfinished.To)),
                copy["windows-update-unfinished-caption"], true, automatic, true);
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
    /// <param name="returnPercent">Windows' percentage of putting that version back.</param>
    public static FlyoutUpdate? Flyout(NativeCopy copy, UpdateFacts? facts, UpdateRun? run, string? returningTo = null, int? returnPercent = null)
    {
        if (returningTo is not null)
            return new FlyoutUpdate(copy.Format("windows-update-undoing", ("version", returningTo)), null, null, returningTo, true, false, true,
                returnPercent);
        if (facts is { Available: false }) return null;
        // While the new version prepares, the update is the flyout's whole state, as it was while Windows switched.
        if (run is null && facts?.Last is { Finishing: true } finishing)
            return new FlyoutUpdate(copy.Format("windows-update-finishing", ("version", finishing.To)), null, null, finishing.To, true, false, true);
        var row = Updates(copy, facts, false, null, DateTimeOffset.MinValue, run);
        return row.Kind switch
        {
            UpdateRowKind.Downloading => new FlyoutUpdate(row.Title, row.Caption, null, run!.Version, true, false, false,
                run.Received is { } received && run.Total is { } total && total > 0 ? (int)(received * 100 / total) : null, Cancel: true),
            UpdateRowKind.Paused => new FlyoutUpdate(row.Title, row.Caption, null, run!.Version, false, false, false, Cancel: true),
            UpdateRowKind.Restarting => new FlyoutUpdate(row.Title, null, null, run!.Version, true, false, true, run.Percent),
            UpdateRowKind.Offered => new FlyoutUpdate(row.Title, null, row.Action, facts!.Offer!, false, false, false),
            UpdateRowKind.UpdateFailed => new FlyoutUpdate(row.Title, row.Caption, row.Action, run!.Version, false, true, false),
            _ => null,
        };
    }

    /// <summary>A download's bytes so far, "120 MB of 332 MB"; null until the first are counted.</summary>
    private static string? Received(NativeCopy copy, UpdateRun run) =>
        run.Received is { } received && run.Total is { } total
            ? copy.Format("update-progress", ("received", Size(copy, received)), ("total", Size(copy, total))) : null;

    /// <summary>A size as Windows' File Explorer gives it, in 1024-byte units: whole megabytes below a thousand, else
    /// gigabytes to one decimal, in the copy's culture. Anything above nothing is at least 1 MB.</summary>
    public static string Size(NativeCopy copy, long bytes)
    {
        const double megabyte = 1024 * 1024, gigabyte = megabyte * 1024;
        var megabytes = bytes <= 0 ? 0 : Math.Max(1, Math.Round(bytes / megabyte));
        return megabytes < 1000 ? megabytes.ToString("0", copy.Culture) + " MB" : (bytes / gigabyte).ToString("0.0", copy.Culture) + " GB";
    }

    /// <summary>A percentage in the copy's culture.</summary>
    public static string Percentage(NativeCopy copy, int percent) => (percent / 100.0).ToString("P0", copy.Culture);

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

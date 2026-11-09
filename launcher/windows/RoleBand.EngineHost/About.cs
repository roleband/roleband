using System.Text.Json;

namespace RoleBand.EngineHost;

/// <summary>What the update commands report: whether this build updates itself, the person's choice,
/// the last check the feed answered, a verified offer and a rate limit. Read from <c>update status</c>,
/// which asks nothing of the network, or from a check's own answer.</summary>
public sealed record UpdateFacts(bool Available, bool Automatic, DateTimeOffset? CheckedAt, string? Offer, DateTimeOffset? RateLimitedUntil)
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
            Moment(reply, "checked_at"), offer, Moment(reply, "rate_limited_until") ?? Moment(reply, "until"));
    }

    private static DateTimeOffset? Moment(JsonElement reply, string name) =>
        reply.TryGetProperty(name, out var value) && value.ValueKind == JsonValueKind.Number
            ? DateTimeOffset.FromUnixTimeMilliseconds((long)(value.GetDouble() * 1000)) : null;
}

/// <summary>Where this session's own update stands, from the press of Update to the result the next version shows.</summary>
public enum UpdateStep { Downloading, Restarting, DownloadFailed, CheckFailed, RestartFailed, Updated, RolledBack }

/// <param name="Version">The version being installed; for a result, the version now running.</param>
public sealed record UpdateRun(UpdateStep Step, string Version)
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

/// <summary>The flyout's update line, and whether Windows is replacing the app, which stops the engine on purpose.</summary>
public sealed record FlyoutUpdate(FlyoutLine Line, bool Restarting);

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
        if (run is { Step: UpdateStep.Updated or UpdateStep.RolledBack })
            return new UpdateRow(UpdateRowKind.Updated,
                copy.Format(run.Step == UpdateStep.Updated ? "update-updated" : "update-rolled-back", ("version", run.Version)),
                checkedCaption, true, automatic, true);
        if (facts?.CheckedAt is not null)
            return new UpdateRow(UpdateRowKind.Current, copy["panel-status-up-to-date"], checkedCaption, true, automatic, true);
        return new UpdateRow(UpdateRowKind.Never, copy["update-idle"], null, true, automatic, true);
    }

    /// <summary>The flyout's line for an update: the offer with Update, the download, the switch, or a failure with Try
    /// again. Results stay in Settings.</summary>
    public static FlyoutUpdate? Flyout(NativeCopy copy, UpdateFacts? facts, UpdateRun? run)
    {
        if (facts is { Available: false }) return null;
        var row = Updates(copy, facts, false, null, DateTimeOffset.MinValue, run);
        return row.Kind switch
        {
            UpdateRowKind.Downloading => new FlyoutUpdate(new FlyoutLine(row.Title), false),
            UpdateRowKind.Restarting => new FlyoutUpdate(new FlyoutLine(row.Title), true),
            UpdateRowKind.Offered or UpdateRowKind.UpdateFailed => new FlyoutUpdate(new FlyoutLine(row.Title, row.Action, Updates: true), false),
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

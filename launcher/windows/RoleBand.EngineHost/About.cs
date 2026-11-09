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

public enum UpdateRowKind { Unavailable, Checking, Failed, Never, Offered, Current }

/// <param name="CanCheck">Check now stays on every state but a check already running, so a failure is one press from a retry.</param>
public sealed record UpdateRow(UpdateRowKind Kind, string Title, string? Caption, bool CanCheck, bool Automatic, bool AutomaticEnabled);

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
    /// <summary>The version Settings shows: an installed package's own, as Windows' installer and Apps settings
    /// show it, else the engine's. A trial's package version counts its builds and differs from the engine's.</summary>
    public static string Version(string engineVersion, (ushort Major, ushort Minor, ushort Build, ushort Revision)? package) =>
        package is { } v ? $"{v.Major}.{v.Minor}.{v.Build}.{v.Revision}" : engineVersion;

    public static UpdateRow Updates(NativeCopy copy, UpdateFacts? facts, bool checking, string? lastResult, DateTimeOffset now)
    {
        if (facts is { Available: false }) return new UpdateRow(UpdateRowKind.Unavailable, copy["windows-updates-unavailable"], null, false, false, false);
        var automatic = facts?.Automatic ?? false;
        var checkedCaption = facts?.CheckedAt is { } at ? copy.Format("panel-checked", ("time", ScanPanel.Clock(copy, at, now))) : null;
        if (checking) return new UpdateRow(UpdateRowKind.Checking, copy["panel-status-checking"], checkedCaption, false, automatic, true);
        var limited = facts?.RateLimitedUntil is { } until && until > now;
        if (limited || lastResult is "failed" or "rate-limited")
            return new UpdateRow(UpdateRowKind.Failed, copy["panel-status-failed"],
                limited || lastResult == "rate-limited" ? copy["update-rate-limited"] : checkedCaption, true, automatic, true);
        if (facts?.Offer is { } version)
            return new UpdateRow(UpdateRowKind.Offered, copy.Format("update-ready", ("version", version)), checkedCaption, true, automatic, true);
        if (facts?.CheckedAt is not null)
            return new UpdateRow(UpdateRowKind.Current, copy["panel-status-up-to-date"], checkedCaption, true, automatic, true);
        return new UpdateRow(UpdateRowKind.Never, copy["update-idle"], null, true, automatic, true);
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

using System.Text;
using System.Text.Json;

namespace RoleBand.EngineHost;

public enum PauseAction { Hour, ThreeHours, Tomorrow, Resume }

/// <summary>The button no longer matches the engine: the state moved since the panel last read it.</summary>
public sealed class ControlStateChangedException() : Exception("The engine's state changed before the request.");

/// <summary>Scan now, Stop scan and Pause, each checked against a fresh status read first, so a press acts
/// only on the state the person saw.</summary>
public static class ScanControl
{
    /// <summary>A stop waits for the run to end, then writes its results, before it answers.</summary>
    public static readonly TimeSpan MutationTimeout = TimeSpan.FromSeconds(20);

    /// <returns>The line to show once the engine answers, or null when the picture and button already say it.</returns>
    public static async Task<string?> PerformAsync(IEngineRequests engine, ScanAction action, CancellationToken cancellation = default)
    {
        var status = await ScanStatus.ReadAsync(engine, cancellation);
        if (status.Action != action) throw new ControlStateChangedException();
        // A timed-out mutation may have committed, so only another press sends another request.
        using var reply = await engine.RequestAsync(HttpMethod.Post, action == ScanAction.Start ? "/api/sync" : "/api/sync/cancel",
            "{}"u8.ToArray(), cancellation, MutationTimeout);
        return Outcome(reply.RootElement, action);
    }

    public static string? Outcome(JsonElement reply, ScanAction action)
    {
        var status = reply.ValueKind == JsonValueKind.Object && reply.TryGetProperty("status", out var value)
            && value.ValueKind == JsonValueKind.String ? value.GetString() : null;
        return (action, status) switch
        {
            (ScanAction.Start, "started") => null,
            (ScanAction.Start, "already_running") => "scan-already-running",
            (ScanAction.Stop, "cancelled") => null,
            (ScanAction.Stop, "not_running") => "scan-not-running",
            _ => throw new InvalidDataException("The engine's reply to the scan request could not be read."),
        };
    }

    public static string Wire(PauseAction action) => action switch
    {
        PauseAction.Hour => "1h",
        PauseAction.ThreeHours => "3h",
        PauseAction.Tomorrow => "tomorrow",
        _ => "resume",
    };

    public static string Key(PauseAction action) => action switch
    {
        PauseAction.Hour => "pause-hour",
        PauseAction.ThreeHours => "pause-three-hours",
        PauseAction.Tomorrow => "pause-tomorrow",
        _ => "pause-resume",
    };

    /// <summary>The schedule request. The zone travels with it, so Until tomorrow means the person's own
    /// morning; the engine reads a bare "+" as a space, so the zone is escaped whole.</summary>
    public static string PlanTarget(string timezone)
    {
        if (string.IsNullOrEmpty(timezone) || timezone.Length > 64) throw new ArgumentException("Invalid time zone.", nameof(timezone));
        return "/api/schedule/plan?tz=" + Uri.EscapeDataString(timezone);
    }

    /// <summary>The account's zone by its IANA name, which the engine reads.</summary>
    public static string LocalTimezone()
    {
        var local = TimeZoneInfo.Local;
        if (local.HasIanaId) return local.Id;
        return TimeZoneInfo.TryConvertWindowsIdToIanaId(local.Id, out var iana) ? iana : "UTC";
    }

    public static async Task<ScheduleState> PauseAsync(IEngineRequests engine, PauseAction action, string timezone,
                                                       Func<DateTimeOffset> clock, CancellationToken cancellation = default)
    {
        var target = PlanTarget(timezone);
        var status = await ScanStatus.ReadAsync(engine, cancellation);
        var plan = status.Picture?.Schedule ?? throw new ControlStateChangedException();
        if ((action == PauseAction.Resume) != plan.IsPaused(clock())) throw new ControlStateChangedException();
        if (action != PauseAction.Resume && !plan.Pausable) throw new ControlStateChangedException();
        var body = Encoding.UTF8.GetBytes(JsonSerializer.Serialize(new Dictionary<string, string> { ["pause"] = Wire(action) }));
        using var reply = await engine.RequestAsync(HttpMethod.Put, target, body, cancellation, MutationTimeout);
        var result = Plan(reply.RootElement);
        if (action == PauseAction.Resume ? result.PausedUntil is not null : !result.IsPaused(clock()))
            throw new InvalidDataException("The engine's schedule did not change as asked.");
        return result;
    }

    /// <summary>The schedule reply: its <c>enabled</c> is the scheduler switch, and its plan's is the schedule plan.</summary>
    public static ScheduleState Plan(JsonElement reply)
    {
        try
        {
            var plan = reply.GetProperty("plan");
            var enabled = reply.GetProperty("enabled").GetBoolean();
            var raw = plan.GetProperty("paused_until");
            DateTimeOffset? until = raw.ValueKind == JsonValueKind.Null ? null
                : ScanStatus.Stamp(plan, "paused_until") ?? throw new InvalidDataException("Invalid pause.");
            return new ScheduleState(enabled, enabled && plan.GetProperty("enabled").GetBoolean(), until);
        }
        catch (Exception error) when (error is InvalidOperationException or KeyNotFoundException)
        {
            throw new InvalidDataException("The engine's schedule reply could not be read.", error);
        }
    }
}

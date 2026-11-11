namespace RoleBand.EngineHost;

/// <summary>What the notification-area icon and the panel say for one engine state.</summary>
/// <param name="StatusKey">The native copy key that names the state in words.</param>
/// <param name="CanOpenRadar">Open Radar waits for an engine that answers.</param>
/// <param name="Busy">The state is on its way somewhere else.</param>
public sealed record TrayState(string StatusKey, bool CanOpenRadar, bool Busy);

public static class TrayModel
{
    public static TrayState For(EngineSnapshot snapshot) => snapshot.State switch
    {
        EngineState.Starting => new("host-starting", false, true),
        EngineState.Preparing => new("first-busy", false, true),
        EngineState.Ready => new("first-part-ready", true, false),
        EngineState.Recovering => new("host-recovering", false, true),
        EngineState.Stopping => new("scan-title-stopping", false, true),
        EngineState.Attention => new("host-attention", false, false),
        _ => new("host-stopped", false, false),
    };

}

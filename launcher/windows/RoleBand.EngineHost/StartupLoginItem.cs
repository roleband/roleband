using System.Runtime.InteropServices;
using Windows.ApplicationModel;

namespace RoleBand.EngineHost;

/// <summary>Open at login through the package's startup task. A copy without package identity, such as a
/// source run, has no startup task and reads as unavailable.</summary>
public sealed class StartupLoginItem : ILoginItem
{
    public const string TaskId = "RoleBandAtLogin";

    public static LoginState From(StartupTaskState state) => state switch
    {
        StartupTaskState.Enabled => LoginState.On,
        StartupTaskState.DisabledByUser => LoginState.Approval,
        StartupTaskState.DisabledByPolicy => LoginState.ManagedOff,
        StartupTaskState.EnabledByPolicy => LoginState.ManagedOn,
        _ => LoginState.Off,
    };

    public async Task<LoginState> ReadAsync()
    {
        try { return From((await StartupTask.GetAsync(TaskId)).State); }
        catch (Exception error) when (error is InvalidOperationException or ArgumentException or COMException) { return LoginState.Unavailable; }
    }

    public async Task<LoginState> SetAsync(bool enabled)
    {
        StartupTask task;
        try { task = await StartupTask.GetAsync(TaskId); }
        catch (Exception error) when (error is InvalidOperationException or ArgumentException or COMException) { return LoginState.Unavailable; }
        if (!enabled)
        {
            // Turning off never needs the person's approval, and a policy setting stays as it is.
            if (task.State == StartupTaskState.Enabled) task.Disable();
            return From(task.State);
        }
        // Turned off in Startup apps, only the person can turn it back on there.
        return From(task.State is StartupTaskState.Disabled ? await task.RequestEnableAsync() : task.State);
    }
}

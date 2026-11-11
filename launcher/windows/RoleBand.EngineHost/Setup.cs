using System.Text;
using System.Text.Json;

namespace RoleBand.EngineHost;

/// <summary>The engine's first preparation, from <c>/api/launcher-health</c>: the database, the ranking
/// model and the service. Scanning needs the database and the service; the model may still wait.</summary>
public sealed record EnginePreparation(string Database, string Model, string Service, long DownloadedBytes, long TotalBytes, string? Reason)
{
    public bool Ready => Database == "ready" && Service == "ready";
    public bool Failed => Database == "failed" || Service == "failed";
    public bool ModelComplete => Model is "ready" or "unused";
    public double Fraction => TotalBytes > 0 ? (double)DownloadedBytes / TotalBytes : 0;

    /// <summary>Null for an engine that prepares nothing; a block outside the engine's own vocabulary is refused.</summary>
    public static EnginePreparation? Read(JsonElement element)
    {
        if (element.ValueKind == JsonValueKind.Null) return null;
        var preparation = new EnginePreparation(
            element.GetProperty("database").GetString() ?? "", element.GetProperty("model").GetString() ?? "",
            element.GetProperty("service").GetString() ?? "", element.GetProperty("downloaded_bytes").GetInt64(),
            element.GetProperty("total_bytes").GetInt64(),
            element.TryGetProperty("reason", out var reason) && reason.ValueKind == JsonValueKind.String ? reason.GetString() : null);
        if (element.GetProperty("format").GetInt32() != 1
            || preparation.Database is not ("waiting" or "creating" or "ready" or "failed")
            || preparation.Model is not ("waiting" or "downloading" or "verifying" or "ready" or "unused" or "failed")
            || preparation.Service is not ("starting" or "ready" or "failed")
            || preparation.DownloadedBytes < 0 || preparation.TotalBytes < preparation.DownloadedBytes)
            throw new IOException("The engine's preparation could not be read.");
        return preparation;
    }
}

/// <summary>First open: Welcome, Get ready, then At login, which ends on Open Radar. Done is the finished record.</summary>
public enum SetupStep { Welcome, Preparing, Login, Done }

/// <summary>Open at login as Windows reports it. Approval: turned off in Startup apps, which only the
/// person can turn back on. Managed: set by an organization's policy.</summary>
public enum LoginState { Off, On, Approval, ManagedOff, ManagedOn, Unavailable }

/// <param name="LoginChoice">The At login switch during setup, initially on; registered only on a change or Continue.</param>
/// <param name="Deferred">Setup was closed before it finished; the next open starts at the panel, not the setup window.</param>
public sealed record SetupRecord(SetupStep Step, bool Complete, bool LoginChoice, bool Deferred)
{
    public static SetupRecord Fresh { get; } = new(SetupStep.Welcome, false, true, false);
    public static SetupRecord Finished { get; } = new(SetupStep.Done, true, false, false);
}

public static class SetupStore
{
    public static string PathFor(string state) => Path.Combine(state, "launcher", "setup.json");

    /// <summary>The saved setup. A state that already holds a database predates setup and counts as finished,
    /// so an existing install never waits at Welcome; so does one whose record cannot be read.</summary>
    public static SetupRecord Read(string state)
    {
        var path = PathFor(state);
        var existing = File.Exists(Path.Combine(state, "db", "PG_VERSION"));
        if (!File.Exists(path)) return existing ? SetupRecord.Finished : SetupRecord.Fresh;
        try
        {
            using var document = JsonDocument.Parse(PrivateStorage.Read(path));
            var root = document.RootElement;
            if (root.GetProperty("format").GetInt32() != 1) throw new IOException("Unknown setup format.");
            var step = root.GetProperty("step").GetString() switch
            {
                "welcome" => SetupStep.Welcome,
                "preparing" => SetupStep.Preparing,
                "login" => SetupStep.Login,
                "done" => SetupStep.Done,
                _ => throw new IOException("Unknown setup step."),
            };
            return new SetupRecord(step, root.GetProperty("complete").GetBoolean(), root.GetProperty("login_choice").GetBoolean(),
                root.GetProperty("deferred").GetBoolean());
        }
        catch (Exception error) when (error is IOException or JsonException or KeyNotFoundException or InvalidOperationException)
        {
            return existing ? SetupRecord.Finished : SetupRecord.Fresh;
        }
    }

    public static void Write(string state, SetupRecord record)
    {
        PrivateStorage.EnsureDirectory(state);
        PrivateStorage.EnsureDirectory(Path.Combine(state, "launcher"));
        var json = JsonSerializer.Serialize(new Dictionary<string, object>
        {
            ["format"] = 1, ["step"] = record.Step.ToString().ToLowerInvariant(), ["complete"] = record.Complete,
            ["login_choice"] = record.LoginChoice, ["deferred"] = record.Deferred,
        });
        PrivateStorage.Write(PathFor(state), Encoding.UTF8.GetBytes(json));
    }
}

/// <summary>Open at login, behind an interface so the rules can be tested without a package.</summary>
public interface ILoginItem
{
    Task<LoginState> ReadAsync();
    /// <returns>The state Windows reports after the change.</returns>
    Task<LoginState> SetAsync(bool enabled);
}

/// <summary>One row of a setup page: what it is, its caption, and its mark.</summary>
public sealed record SetupRow(string TitleKey, string CaptionKey, string Mark, string? Figure = null, double? Progress = null);

public sealed record SetupPage(
    SetupStep Step,
    string HeadingKey,
    string BodyKey,
    IReadOnlyList<SetupRow> Rows,
    bool Back,
    bool Later,
    string PrimaryKey,
    bool PrimaryEnabled,
    bool Busy,
    bool Retry,
    string? SecondaryKey,
    bool LoginSwitch,
    bool LoginSwitchEnabled,
    bool LoginSettings,
    string? NoteKey);

public static class SetupFlow
{
    public static readonly IReadOnlyList<(SetupStep Step, string Key)> Steps =
    [
        (SetupStep.Welcome, "step-welcome"), (SetupStep.Preparing, "first-step-preparing"), (SetupStep.Login, "step-login"),
    ];

    /// <summary>The page's place among the steps; a record left at Done before it finished shows the last page.</summary>
    public static int Position(SetupStep step) => step == SetupStep.Done ? Steps.Count : Steps.ToList().FindIndex(entry => entry.Step == step) + 1;

    /// <summary>Nothing runs before Continue on Welcome: the engine, and with it the first scan, waits.</summary>
    public static bool EngineHeld(SetupRecord record) => !record.Complete && record.Step == SetupStep.Welcome;

    /// <summary>The setup window opens by itself only for unfinished setup that was not put off, and never
    /// at login, which opens quietly.</summary>
    public static bool ShowAtLaunch(SetupRecord record, bool atLogin) => !record.Complete && !record.Deferred && !atLogin;

    /// <summary>Get ready lets the person on once the database and service answer, even while the model waits.</summary>
    public static bool PreparationReady(EngineSnapshot engine) =>
        engine.State == EngineState.Ready && (engine.Preparation?.Ready ?? true);

    public static SetupStep Next(SetupStep step, bool ready) => step switch
    {
        SetupStep.Welcome => SetupStep.Preparing,
        SetupStep.Preparing => ready ? SetupStep.Login : SetupStep.Preparing,
        _ => SetupStep.Done,
    };

    public static SetupStep Previous(SetupStep step) => step switch
    {
        SetupStep.Login or SetupStep.Done => SetupStep.Preparing,
        SetupStep.Preparing => SetupStep.Welcome,
        _ => step,
    };

    public static bool Registered(LoginState state) => state is LoginState.On or LoginState.Approval or LoginState.ManagedOn;

    /// <summary>A change of the At login switch registers at once; Windows has the last word.</summary>
    public static async Task<(SetupRecord Record, LoginState Login, bool Error)> ChooseLoginAsync(
        SetupRecord record, bool enabled, ILoginItem item)
    {
        var chosen = record with { LoginChoice = enabled };
        try { return (chosen, await item.SetAsync(enabled), false); }
        catch (Exception) { return (chosen, await item.ReadAsync(), true); }
    }

    /// <summary>Continue, and on At login both ways out (Open Radar and Not now). At login registers the choice first
    /// when Windows does not have it yet, and stays on the page if that fails; Get ready waits for a database and
    /// service that answer.</summary>
    public static async Task<(SetupRecord Record, LoginState Login, bool Error)> ContinueAsync(
        SetupRecord record, EngineSnapshot engine, LoginState login, ILoginItem item)
    {
        if (record.Step == SetupStep.Login && login is (LoginState.Off or LoginState.On or LoginState.Approval)
            && Registered(login) != record.LoginChoice)
        {
            try { login = await item.SetAsync(record.LoginChoice); }
            catch (Exception) { return (record, await item.ReadAsync(), true); }
        }
        return (record with { Step = Next(record.Step, PreparationReady(engine)) }, login, false);
    }

    /// <summary>Leaving At login completes setup. Without an engine that answers it goes back to Get ready instead.</summary>
    public static (SetupRecord Record, bool Complete) Finish(SetupRecord record, EngineSnapshot engine) =>
        engine.State == EngineState.Ready
            ? (record with { Step = SetupStep.Done, Complete = true, Deferred = false }, true)
            : (record with { Step = SetupStep.Preparing }, false);

    /// <summary>Closing setup keeps the step and leaves preparation running; the panel's card resumes it.</summary>
    public static SetupRecord Close(SetupRecord record, EngineSnapshot engine)
    {
        if (record.Complete) return record;
        if (record.Step == SetupStep.Done)
        {
            var (finished, complete) = Finish(record, engine);
            if (complete) return finished;
            return finished with { Deferred = true };
        }
        return record with { Deferred = true };
    }

    /// <summary>Finish setup from the panel reopens the window at the saved step.</summary>
    public static SetupRecord Resume(SetupRecord record) => record with { Deferred = false };

    /// <summary>What the At login switch shows: the person's choice, unless Windows decides it.</summary>
    public static bool SwitchOn(SetupRecord record, LoginState state) => state switch
    {
        LoginState.ManagedOn => true,
        LoginState.ManagedOff or LoginState.Unavailable => false,
        _ => record.LoginChoice,
    };

    public static SetupPage Page(SetupRecord record, EngineSnapshot engine, LoginState login, bool loginBusy)
    {
        var preparation = engine.Preparation;
        var ready = PreparationReady(engine);
        var failed = engine.State == EngineState.Attention;
        switch (record.Step)
        {
            case SetupStep.Welcome:
                return new SetupPage(SetupStep.Welcome, "first-welcome-title", "windows-welcome-body",
                [
                    new("windows-prepare", "first-prepare-caption", "none"),
                    new("windows-login-choice", "first-login-caption", "none"),
                    new("first-open", "first-open-caption", "none"),
                ], Back: false, Later: true, "continue", true, false, false, null, false, false, false, null);
            case SetupStep.Preparing:
            {
                // Before the engine's first answer, the database is on its way and the rest waits. An engine
                // that answers without a preparation block prepares no model.
                var database = preparation?.Database ?? (ready ? "ready" : failed ? "failed" : "creating");
                var model = preparation?.Model ?? (ready ? "unused" : "waiting");
                var service = preparation?.Service ?? (ready ? "ready" : failed ? "failed" : "starting");
                // The service never starts after its database failed: it waits, rather than looking busy beside the failure.
                if (database == "failed" && service == "starting") service = "waiting";
                var heading = failed ? "first-failed-title"
                    : ready && (preparation?.ModelComplete ?? true) ? "windows-prepared-title" : "first-preparing-title";
                var body = failed ? (database == "failed" ? "first-database-failed" : "first-service-failed")
                    : ready && preparation?.Reason == "offline" ? "first-offline-body"
                    : ready && (preparation?.ModelComplete ?? true) ? "windows-prepared-body" : "first-preparing-body";
                var downloading = preparation is { Model: "downloading", TotalBytes: > 0 };
                return new SetupPage(SetupStep.Preparing, heading, body,
                [
                    new("first-database", PartCaption(database, "first-database-creating"), Mark(database)),
                    new("first-model", ModelCaption(model, preparation?.Reason), downloading ? "progress" : Mark(model),
                        downloading ? $"{(int)(preparation!.Fraction * 100)}%" : null, downloading ? preparation!.Fraction : null),
                    new("first-service", PartCaption(service, "first-service-starting"), Mark(service)),
                ], Back: true, Later: true, failed ? "retry" : ready ? "continue" : "first-busy", failed || ready, !failed && !ready,
                    Retry: failed, failed ? "engine-logs" : null, false, false, false, null);
            }
            default:
                // The last page keeps the Mac's At login and Ready together: the switch, where the icon lives, and
                // Open Radar, which ends setup in the browser.
                return new SetupPage(SetupStep.Login, "first-login-title", "windows-login-body",
                [
                    new("windows-login-toggle", login switch
                    {
                        LoginState.Approval => "windows-login-approval",
                        LoginState.ManagedOff or LoginState.ManagedOn => "windows-login-managed",
                        _ => "first-login-caption",
                    }, "switch"),
                    new("windows-tray-title", "windows-tray-body", "taskbar"),
                ], Back: true, Later: false, "first-open", !loginBusy && engine.State == EngineState.Ready, loginBusy, false, "skip",
                    LoginSwitch: true, LoginSwitchEnabled: !loginBusy && login is (LoginState.Off or LoginState.On or LoginState.Approval),
                    LoginSettings: login == LoginState.Approval, "windows-settings-note");
        }
    }

    private static string Mark(string state) => state switch
    {
        "ready" or "unused" => "done",
        "failed" => "failed",
        "waiting" => "waiting",
        _ => "busy",
    };

    private static string PartCaption(string state, string working) => state switch
    {
        "ready" => "first-part-ready",
        "failed" => "first-part-failed",
        "waiting" => "first-waiting",
        _ => working,
    };

    private static string ModelCaption(string model, string? reason) => model switch
    {
        "ready" => "first-model-ready",
        "unused" => "first-model-unused",
        "verifying" => "first-model-verifying",
        "downloading" => "first-model-downloading",
        "failed" => "first-model-failed",
        _ => reason == "offline" ? "first-model-offline" : "first-waiting",
    };
}

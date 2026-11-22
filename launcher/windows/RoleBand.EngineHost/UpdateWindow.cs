using System.ComponentModel;
using System.Runtime.InteropServices;
using System.Text;
using System.Text.Json;

namespace RoleBand.EngineHost;

/// <summary>The person's answers to the update window: its switch in Settings, and their Laters for one version.</summary>
/// <param name="Shows">The window opens by itself for a release an automatic check finds.</param>
/// <param name="LaterVersion">The version the Laters are counted for; a newer version starts its own count.</param>
/// <param name="LaterUntil">Until when the last Later keeps that version's window away.</param>
public sealed record UpdateWindowRecord(bool Shows = true, string? LaterVersion = null, int LaterCount = 0,
                                        DateTimeOffset? LaterUntil = null)
{
    /// <summary>How long Later keeps the window away, and how many Laters leave a version to the icon's badge alone. An
    /// important release comes back a day after any number of Laters.</summary>
    public static readonly TimeSpan LaterInterval = TimeSpan.FromDays(3);
    public static readonly TimeSpan ImportantLaterInterval = TimeSpan.FromDays(1);
    public const int LaterLimit = 3;

    public UpdateWindowRecord Later(string version, DateTimeOffset now) => this with
    {
        LaterVersion = version,
        LaterCount = (LaterVersion == version ? LaterCount : 0) + 1,
        LaterUntil = now + LaterInterval,
    };

    /// <summary>Whether the person's Laters still let the window open for <paramref name="version"/>. The wait is
    /// measured from the last Later, so a mark that arrives during a three-day wait shortens it to a day.</summary>
    public bool Allows(string version, DateTimeOffset now, bool important = false) =>
        LaterVersion != version || LaterUntil is not { } until
        || (important ? now >= until - LaterInterval + ImportantLaterInterval : LaterCount < LaterLimit && now >= until);
}

/// <summary>The update window's record in the account's state. One that is missing or cannot be read is a window that
/// opens and no Laters.</summary>
public static class UpdateWindowStore
{
    public static string PathFor(string state) => Path.Combine(state, "launcher", "update-window.json");

    public static UpdateWindowRecord Read(string state)
    {
        var path = PathFor(state);
        if (!File.Exists(path)) return new UpdateWindowRecord();
        try
        {
            using var document = JsonDocument.Parse(PrivateStorage.Read(path));
            var root = document.RootElement;
            if (root.GetProperty("format").GetInt32() != 1) return new UpdateWindowRecord();
            var version = root.GetProperty("later_version");
            var until = root.GetProperty("later_until");
            return new UpdateWindowRecord(
                root.GetProperty("shows").GetBoolean(),
                version.ValueKind == JsonValueKind.String ? version.GetString() : null,
                root.GetProperty("later_count").GetInt32(),
                until.ValueKind == JsonValueKind.Number ? DateTimeOffset.FromUnixTimeMilliseconds(until.GetInt64()) : null);
        }
        catch (Exception error) when (error is IOException or JsonException or KeyNotFoundException or InvalidOperationException
                                          or FormatException or UnauthorizedAccessException or ArgumentOutOfRangeException)
        {
            return new UpdateWindowRecord();
        }
    }

    public static void Write(string state, UpdateWindowRecord record)
    {
        PrivateStorage.EnsureDirectory(state);
        PrivateStorage.EnsureDirectory(Path.Combine(state, "launcher"));
        var json = JsonSerializer.Serialize(new Dictionary<string, object?>
        {
            ["format"] = 1, ["shows"] = record.Shows, ["later_version"] = record.LaterVersion, ["later_count"] = record.LaterCount,
            ["later_until"] = record.LaterUntil?.ToUnixTimeMilliseconds(),
        });
        PrivateStorage.Write(PathFor(state), Encoding.UTF8.GetBytes(json));
    }
}

/// <summary>What happens to a release a check found: its window opens now, waits for what holds it back, or does not
/// open.</summary>
public enum UpdateWindowDecision { Open, Hold, Drop }

/// <summary>The window's buttons, beside What's new.</summary>
public enum UpdateWindowChoice { Later, Update, Retry, Cancel }

/// <summary>What the update window shows at one moment.</summary>
/// <param name="Version">The version it acts on: the one an update in progress installs, else the offer.</param>
/// <param name="Page">The release's page, which What's new opens; only the offer's is known.</param>
/// <param name="Step">The update's progress or failure, in place of nothing while it is only an offer.</param>
/// <param name="Detail">The bytes so far, what the wait is for, or what a failure means.</param>
/// <param name="Percent">How far the download or Windows' install has got; null while it says nothing of how far.</param>
public sealed record UpdateWindowView(string Heading, string Body, string Version, string? Page, string? Step, string? Detail,
                                      int? Percent, bool Working, bool Failed, IReadOnlyList<UpdateWindowChoice> Choices);

/// <summary>
/// The window that opens by itself when an automatic check finds a release. It carries the update from the offer to the
/// switch, since the person it is for may never open the flyout, and it never takes focus: Later is its way out.
/// </summary>
public static class UpdateWindowRules
{
    /// <summary>The version a check's answer puts to the window: an offer an automatic check found. Check for updates
    /// never opens it; its answer stays in Settings.</summary>
    public static string? Found(bool manual, string status, UpdateFacts facts) => !manual && status == "offered" ? facts.Offer : null;

    /// <summary>Whether a found version's window opens. Setup, unfinished or open, and an update or Undo under way hold it
    /// until they end. Its switch turned off, the person's Laters, and an offer that is gone or cannot be installed let
    /// it go; the icon's badge still marks the offer.</summary>
    /// <param name="setupOpen">The setup window is open.</param>
    public static UpdateWindowDecision Decide(AppState state, UpdateWindowRecord record, string version, bool setupOpen)
    {
        var update = state.Update;
        if (update.Facts is not { Available: true } facts || facts.Offer != version || !record.Shows) return UpdateWindowDecision.Drop;
        if (!state.Setup.Complete || setupOpen || update.Switching) return UpdateWindowDecision.Hold;
        if (update.Installable != version) return UpdateWindowDecision.Drop;
        return record.Allows(version, state.Now, facts.Important) ? UpdateWindowDecision.Open : UpdateWindowDecision.Drop;
    }

    /// <summary>An open window goes once it has nothing to show (the version was installed, withdrawn or held back, or an
    /// Undo is under way) or its switch is turned off. With its switch off, only the update it shows, running or failed,
    /// keeps it, so that update's result stays in view; a newer offer in its place does not.</summary>
    public static bool Stale(NativeCopy copy, AppState state, UpdateWindowRecord record) =>
        state.Update.Returning || View(copy, state) is not { } view
        || (!record.Shows && (state.Update.Run is not { } run || view.Version != run.Version));

    /// <summary>The window for the state: the offer with Later and Update; the download with Cancel; Windows' install with
    /// nothing left to choose; a failure with Later and Try again. A failure of an older version gives way to a newer
    /// offer, which the person has not tried yet.</summary>
    public static UpdateWindowView? View(NativeCopy copy, AppState state)
    {
        var update = state.Update;
        var facts = update.Facts;
        var run = update.Run;
        var row = AboutPanel.Updates(copy, facts, false, null, state.Now, run);
        return row.Kind switch
        {
            UpdateRowKind.Downloading => Window(copy, facts, run!.Version, row.Title, row.Caption, Percent(run!), false, false,
                [UpdateWindowChoice.Cancel]),
            UpdateRowKind.Paused => Window(copy, facts, run!.Version, row.Title, row.Caption, Percent(run!), false, false,
                [UpdateWindowChoice.Cancel]),
            UpdateRowKind.Installing => Window(copy, facts, run!.Version, row.Title, row.Caption, run!.Percent, run!.Percent is null, false, []),
            UpdateRowKind.UpdateFailed => Window(copy, facts, run!.Version, row.Title, row.Caption, null, false, true,
                row.Action is null ? [UpdateWindowChoice.Later] : [UpdateWindowChoice.Later, UpdateWindowChoice.Retry]),
            _ => facts?.Offer is { } offer && update.Installable == offer
                ? Window(copy, facts, offer, null, null, null, false, false, [UpdateWindowChoice.Later, UpdateWindowChoice.Update])
                : null,
        };
    }

    /// <summary>The page and an important release's line speak for the offer only, so an older version still
    /// installing keeps the plain line.</summary>
    private static UpdateWindowView Window(NativeCopy copy, UpdateFacts? facts, string version, string? step, string? detail, int? percent,
                                           bool working, bool failed, IReadOnlyList<UpdateWindowChoice> choices)
    {
        var offer = facts is { } known && known.Offer == version ? known : null;
        return new(copy.Format("update-ready", ("version", version)),
            copy[offer is { Important: true } ? "update-window-body-important" : "update-window-body"], version, offer?.Page, step, detail,
            percent, working, failed, choices);
    }

    private static int? Percent(UpdateRun run) =>
        run.Received is { } received && run.Total is { } total && total > 0 ? (int)(received * 100 / total) : null;
}

/// <summary>
/// Shows a top-level window above the others without taking the foreground, and keeps a click on it from activating it:
/// whatever the person is typing in keeps the keyboard, and the window's buttons answer the first click. Create, show and
/// dispose it on the window's own thread.
/// </summary>
public sealed class QuietWindow : IDisposable
{
    private const int ExtendedStyle = -20;
    private const long NoActivate = 0x08000000;
    private const uint MouseActivate = 0x0021;
    private const nint NoActivateAnswer = 3;
    private const uint NoSize = 0x0001, NoMove = 0x0002, NoActivateFlag = 0x0010, ShowFlag = 0x0040;
    private const int ShowNoActivate = 4;
    private static readonly nint TopMost = -1;
    private readonly WindowHook hook;

    public nint Window { get; }

    public QuietWindow(nint window)
    {
        Window = window;
        SetWindowLongPtr(window, ExtendedStyle, (nint)((long)GetWindowLongPtr(window, ExtendedStyle) | NoActivate));
        hook = new WindowHook(window, Answer);
    }

    private static bool Answer(uint message, nint wParam, nint lParam, out nint result)
    {
        result = message == MouseActivate ? NoActivateAnswer : 0;
        return message == MouseActivate;
    }

    /// <summary>Shows the window on top, where it is, at the size it has.</summary>
    public void Show()
    {
        ShowWindow(Window, ShowNoActivate);
        if (!SetWindowPos(Window, TopMost, 0, 0, 0, 0, NoSize | NoMove | NoActivateFlag | ShowFlag))
            throw new Win32Exception(Marshal.GetLastWin32Error());
    }

    public void Dispose() => hook.Dispose();

    [DllImport("user32.dll", EntryPoint = "GetWindowLongPtrW")]
    private static extern nint GetWindowLongPtr(nint window, int index);
    [DllImport("user32.dll", EntryPoint = "SetWindowLongPtrW")]
    private static extern nint SetWindowLongPtr(nint window, int index, nint value);
    [DllImport("user32.dll")]
    private static extern bool ShowWindow(nint window, int command);
    [DllImport("user32.dll", SetLastError = true)]
    private static extern bool SetWindowPos(nint window, nint after, int x, int y, int width, int height, uint flags);
}

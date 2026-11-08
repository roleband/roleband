using System.Diagnostics;
using System.Net;
using System.Net.Sockets;
using System.Runtime.InteropServices;
using System.Text;
using Microsoft.Win32.SafeHandles;
using System.Text.Json;

namespace RoleBand.EngineHost;

public sealed record EngineConfiguration(string Resources, string State, string Python, string NativePython,
                                         string Version, bool Development, bool SyntheticFixture)
{
    public string EngineDirectory => Path.Combine(Resources, Development ? "backend" : "engine");
    public string Bootstrap => Path.Combine(EngineDirectory, "desktop.py");

    public static EngineConfiguration Source(string checkout, string state, bool fixture = false)
    {
        checkout = Path.GetFullPath(checkout);
        state = Path.GetFullPath(state);
        var python = Path.Combine(checkout, "backend", ".venv", "Scripts", "python.exe");
        var config = Path.Combine(checkout, "backend", ".venv", "pyvenv.cfg");
        if (!File.Exists(python) || !File.Exists(config) || !File.Exists(Path.Combine(checkout, "backend", "desktop.py")))
            throw new IOException("The source engine is incomplete.");
        var values = File.ReadAllLines(config).Where(line => line.Contains('=')).Select(line => line.Split('=', 2))
            .ToDictionary(parts => parts[0].Trim(), parts => parts[1].Trim(), StringComparer.OrdinalIgnoreCase);
        if (!values.TryGetValue("executable", out var native) || !File.Exists(native))
            throw new IOException("The source interpreter has no native executable.");
        using var metadata = JsonDocument.Parse(File.ReadAllBytes(Path.Combine(checkout, "dashboard", "package.json")));
        return new(checkout, ValidateState(checkout, state), python, native,
                   metadata.RootElement.GetProperty("version").GetString()!, true, fixture);
    }

    public static EngineConfiguration Packaged(string resources, string? state = null, bool fixture = false)
    {
        resources = Path.GetFullPath(resources);
        var metadataPath = Path.Combine(resources, "engine", "release.json");
        var python = Path.Combine(resources, "runtime", "python.exe");
        if (!File.Exists(metadataPath) || !File.Exists(python) || !File.Exists(Path.Combine(resources, "engine", "desktop.py")))
            throw new IOException("The packaged engine is incomplete.");
        using var metadata = JsonDocument.Parse(File.ReadAllBytes(metadataPath));
        var trial = Path.Combine(resources, "trial.json");
        if (!File.Exists(trial)) throw new IOException("The development app requires its synthetic trial identity.");
        using var trialMetadata = JsonDocument.Parse(File.ReadAllBytes(trial));
        if (!trialMetadata.RootElement.GetProperty("trial_only").GetBoolean()
            || !Guid.TryParseExact(trialMetadata.RootElement.GetProperty("trial_id").GetString(), "N", out var trialId))
            throw new IOException("Invalid trial identity.");
        state ??= Path.Combine(KnownFolders.LocalAppData, "RoleBandTrials", trialId.ToString("N"));
        fixture = true;
        return new(resources, ValidateState(resources, Path.GetFullPath(state)), python, python,
                   metadata.RootElement.GetProperty("version").GetString()!, false, fixture);
    }

    // Default state roots of installed RoleBand apps, which development and trial engines never open.
    private static IReadOnlyList<string> InstalledDataRoots() =>
    [
        Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.UserProfile), ".roleband"),
        Path.Combine(KnownFolders.LocalAppData, "RoleBand"),
    ];

    private static string ValidateState(string resources, string state)
    {
        if (LeadsInto(state, resources) || InstalledDataRoots().Any(root => LeadsInto(state, root)))
            throw new IOException("Engine state must be separate from resources and installed RoleBand data.");
        return state;
    }

    /// <summary>Whether a path is <paramref name="root"/> or inside it, by where each really leads: a junction or
    /// link on the way is followed, so it cannot lead an engine into installed data under another name.</summary>
    public static bool LeadsInto(string path, string root) => Within(FinalPath(path), FinalPath(root));

    /// <summary>The path with its longest existing part resolved through junctions and links by Windows itself, and
    /// the parts that do not exist yet appended as written. An existing part Windows cannot resolve is an
    /// <see cref="IOException"/>: its text as written could hide where it leads.</summary>
    public static string FinalPath(string path)
    {
        var full = Path.GetFullPath(path);
        var existing = full;
        while (!Directory.Exists(existing) && !File.Exists(existing))
        {
            var parent = Path.GetDirectoryName(existing);
            if (parent is null) return full;
            existing = parent;
        }
        var resolved = Resolved(existing) ?? throw new IOException($"Where {existing} leads could not be resolved.");
        return Path.Join(resolved, full[existing.Length..]);
    }

    private static string? Resolved(string existing)
    {
        // Zero access with backup semantics opens a directory just to name it; the extended form opens one past
        // MAX_PATH whether or not long paths are enabled.
        using var handle = CreateFile(Extended(existing), 0, 7, 0, 3, 0x02000000, 0);
        if (handle.IsInvalid) return null;
        // A buffer too small is answered with the size the name needs, which can change before the next call.
        uint size = 1024;
        for (var attempt = 0; attempt < 3; attempt++)
        {
            var buffer = new StringBuilder((int)size);
            var length = GetFinalPathNameByHandle(handle, buffer, size, 0);
            if (length == 0) return null;
            if (length < size) return Plain(buffer.ToString());
            size = length;
        }
        return null;
    }

    private static string Extended(string path) =>
        path.StartsWith(@"\\?\", StringComparison.Ordinal) || path.StartsWith(@"\\.\", StringComparison.Ordinal) ? path
        : path.StartsWith(@"\\", StringComparison.Ordinal) ? @"\\?\UNC\" + path[2..]
        : @"\\?\" + path;

    private static string Plain(string path) =>
        path.StartsWith(@"\\?\UNC\", StringComparison.Ordinal) ? @"\\" + path[8..]
        : path.StartsWith(@"\\?\", StringComparison.Ordinal) ? path[4..] : path;

    [DllImport("kernel32.dll", EntryPoint = "CreateFileW", CharSet = CharSet.Unicode, SetLastError = true)]
    private static extern SafeFileHandle CreateFile(string name, uint access, uint share, nint security, uint disposition, uint flags, nint template);
    [DllImport("kernel32.dll", EntryPoint = "GetFinalPathNameByHandleW", CharSet = CharSet.Unicode, SetLastError = true)]
    private static extern uint GetFinalPathNameByHandle(SafeFileHandle file, StringBuilder path, uint size, uint flags);

    private static bool Within(string path, string root) =>
        path.Equals(root, StringComparison.OrdinalIgnoreCase)
        || path.StartsWith(root.TrimEnd(Path.DirectorySeparatorChar) + Path.DirectorySeparatorChar, StringComparison.OrdinalIgnoreCase);

    /// <summary>A desktop.py command in this engine's interpreter, environment and retained state.</summary>
    public ProcessStartInfo EngineStart(IEnumerable<string> arguments)
    {
        var start = new ProcessStartInfo(NativePython)
        {
            WorkingDirectory = EngineDirectory,
            UseShellExecute = false,
            CreateNoWindow = true,
            RedirectStandardOutput = true,
            RedirectStandardError = true,
            StandardOutputEncoding = Encoding.UTF8,
            StandardErrorEncoding = Encoding.UTF8,
        };
        start.Environment.Clear();
        foreach (var name in new[] { "SystemRoot", "WINDIR", "TEMP", "TMP", "USERPROFILE", "LOCALAPPDATA", "APPDATA", "SYSTEMDRIVE" })
            if (Environment.GetEnvironmentVariable(name) is { } value) start.Environment[name] = value;
        var system = Environment.GetFolderPath(Environment.SpecialFolder.System);
        start.Environment["PATH"] = Path.GetDirectoryName(NativePython) + ";" + system;
        if (Development) start.Environment["__PYVENV_LAUNCHER__"] = Python;
        foreach (var (name, value) in new Dictionary<string, string>
        {
            ["ROLEBAND_STATE_DIR"] = State, ["ROLEBAND_PGDATA"] = Path.Combine(State, "db"),
            ["ROLEBAND_CACHE_DIR"] = Path.Combine(State, "cache"), ["ROLEBAND_PLUGINS_DIR"] = Path.Combine(State, "plugins"),
            ["ROLEBAND_SECRET_KEY_FILE"] = Path.Combine(State, "secret.key"), ["ROLEBAND_DATABASE_URL"] = "",
            ["ROLEBAND_DB_EMBEDDED"] = "true", ["ROLEBAND_API_HOST"] = "127.0.0.1",
            ["ROLEBAND_API_PORT"] = AvailablePort().ToString(System.Globalization.CultureInfo.InvariantCulture),
            ["ROLEBAND_LOCAL_AUTH"] = "1", ["PYTHONUTF8"] = "1", ["PYTHONNOUSERSITE"] = "1",
            ["PYTHONDONTWRITEBYTECODE"] = "1",
            // Python cannot map Windows' own zone names to IANA ones, and TZ is read by the C runtime in its own
            // form, so the engine's daily slots and plans read the zone from here.
            ["ROLEBAND_LOCAL_ZONE"] = ScanControl.LocalTimezone(),
        }) start.Environment[name] = value;
        if (Development || SyntheticFixture)
        {
            start.Environment["ROLEBAND_NO_USAGE_STATS"] = "1";
            start.Environment["ROLEBAND_SEARCH_SEMANTIC_ENABLED"] = "false";
            start.Environment["ROLEBAND_SEARCH_WARM_MODEL_ON_STARTUP"] = "false";
        }
        start.ArgumentList.Add("-I");
        start.ArgumentList.Add("-B");
        start.ArgumentList.Add(Bootstrap);
        if (Development) start.ArgumentList.Add("--source");
        foreach (var argument in arguments) start.ArgumentList.Add(argument);
        return start;
    }

    public static int AvailablePort()
    {
        using var socket = new Socket(AddressFamily.InterNetwork, SocketType.Stream, ProtocolType.Tcp);
        socket.Bind(new IPEndPoint(IPAddress.Loopback, 0));
        return ((IPEndPoint)socket.LocalEndPoint!).Port;
    }
}

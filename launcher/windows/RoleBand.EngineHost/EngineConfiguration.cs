using System.Diagnostics;
using System.Net;
using System.Net.Sockets;
using System.Text;
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
        if (Within(state, resources) || InstalledDataRoots().Any(root => Within(state, root)))
            throw new IOException("Engine state must be separate from resources and installed RoleBand data.");
        return state;
    }

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

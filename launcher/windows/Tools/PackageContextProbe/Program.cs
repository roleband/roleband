using System.Diagnostics;
using System.Text.Json;
using RoleBand.EngineHost;

string Required(string option)
{
    var index = Array.IndexOf(args, option);
    if (index < 0 || index + 1 == args.Length) throw new ArgumentException($"Missing {option}");
    return Path.GetFullPath(args[index + 1]);
}

var report = Required("--report");
try
{
    var resources = Required("--resources");
    var state = Required("--state");
    if (Directory.Exists(state)) throw new IOException("Choose a fresh synthetic state directory.");
    if (PackageProcess.RelaunchIfNeeded()) return;
    var configuration = EngineConfiguration.Packaged(resources, state, fixture: true);
    await using var session = new EngineSession(configuration);
    async Task<int> StartAndRead()
    {
        await session.StartAsync();
        var deadline = Stopwatch.StartNew();
        while (session.Snapshot.State != EngineState.Ready && deadline.Elapsed < TimeSpan.FromSeconds(120))
        {
            if (session.Snapshot.State == EngineState.Attention) throw new IOException(session.Snapshot.Diagnostic);
            await Task.Delay(100);
        }
        if (session.Snapshot.State != EngineState.Ready) throw new TimeoutException("Engine did not become ready.");
        using var client = new EngineClient(state);
        using var jobs = await client.RequestAsync(HttpMethod.Get, "/api/jobs?limit=20");
        return jobs.RootElement.GetProperty("total").GetInt32();
    }
    var total = await StartAndRead();
    if (total <= 0) throw new IOException("Synthetic fixture is empty.");
    await session.StopAsync();
    if (File.Exists(Path.Combine(state, "db", "postmaster.pid"))) throw new IOException("PostgreSQL did not stop.");
    var retained = await StartAndRead();
    if (total != retained) throw new IOException("Fixture changed across restart.");
    await session.StopAsync();
    foreach (var file in new[] { "db/postmaster.pid", "launcher/http-engine.json", "launcher/owned-engine.json" })
        if (File.Exists(Path.Combine(state, file))) throw new IOException($"Shutdown left {file}.");
    if (!File.Exists(Path.Combine(state, "db", "PG_VERSION"))) throw new IOException("Database was not retained.");
    File.WriteAllText(report, JsonSerializer.Serialize(new { passed = true, total, retained, state, resources }));
}
catch (Exception error)
{
    File.WriteAllText(report, JsonSerializer.Serialize(new { passed = false, error = error.ToString() }));
    Environment.ExitCode = 1;
}

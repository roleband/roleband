using System.Text;

namespace RoleBand.EngineHost;

// The native host's own log: every line timestamped, and the file rotated to one
// previous copy, so it never takes more than about twice its limit.
internal sealed class DesktopLog(string path, long limit)
{
    private static readonly Encoding Utf8 = new UTF8Encoding(false);
    private readonly Lock gate = new();

    public void Append(string line)
    {
        var stamped = $"{DateTimeOffset.Now:yyyy-MM-ddTHH:mm:ss.fffzzz} {line}{Environment.NewLine}";
        lock (gate)
        {
            var current = new FileInfo(path);
            if (current.Exists && current.Length + stamped.Length > limit)
                File.Move(path, path + ".1", overwrite: true);
            File.AppendAllText(path, stamped, Utf8);
        }
    }
}

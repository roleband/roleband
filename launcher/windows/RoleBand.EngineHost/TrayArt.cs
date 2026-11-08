namespace RoleBand.EngineHost;

/// <summary>The notification-area icon's files: one .ico per taskbar theme and state, each holding frames drawn
/// for 16, 20, 24 and 32 pixels.</summary>
public static class TrayArt
{
    public static string File(TrayBadge badge, bool lightTaskbar) =>
        $"tray-{(lightTaskbar ? "light" : "dark")}-{badge switch
        {
            TrayBadge.Scanning => "scanning",
            TrayBadge.Paused => "paused",
            TrayBadge.Attention => "attention",
            TrayBadge.Stopped => "stopped",
            _ => "ready",
        }}.ico";

    /// <summary>The name the app embeds the file under.</summary>
    public static string Resource(TrayBadge badge, bool lightTaskbar) => "RoleBand.Tray." + File(badge, lightTaskbar);

    /// <summary>The frame drawn for <paramref name="size"/> pixels, or else the smallest larger one, or the largest:
    /// a frame drawn for its size stays on whole pixels, where a scaled one blurs.</summary>
    /// <returns>The frame's image bytes, as an icon resource or PNG, and its size.</returns>
    public static (byte[] Image, int Size) Frame(byte[] ico, int size)
    {
        if (ico.Length < 6 || BitConverter.ToUInt16(ico, 0) != 0 || BitConverter.ToUInt16(ico, 2) != 1)
            throw new InvalidDataException("Not an icon file.");
        var count = BitConverter.ToUInt16(ico, 4);
        if (count == 0 || ico.Length < 6 + 16 * count) throw new InvalidDataException("The icon file has no frames.");
        var frames = Enumerable.Range(0, count).Select(index =>
        {
            var entry = 6 + 16 * index;
            var width = ico[entry] == 0 ? 256 : ico[entry];
            var length = BitConverter.ToInt32(ico, entry + 8);
            var offset = BitConverter.ToInt32(ico, entry + 12);
            if (length <= 0 || offset < 0 || (long)offset + length > ico.Length) throw new InvalidDataException("An icon frame lies outside the file.");
            return (Width: width, Offset: offset, Length: length);
        }).OrderBy(frame => frame.Width).ToList();
        var chosen = frames.FirstOrDefault(frame => frame.Width >= size, frames[^1]);
        return (ico.AsSpan(chosen.Offset, chosen.Length).ToArray(), chosen.Width);
    }
}

/// <summary>A rectangle in physical pixels.</summary>
public readonly record struct Box(int Left, int Top, int Width, int Height)
{
    public int Right => Left + Width;
    public int Bottom => Top + Height;
}

public enum TaskbarEdge { Bottom, Top, Left, Right }

/// <summary>Where the flyout opens: next to the point Windows reports for the icon, a margin off the taskbar,
/// inside the work area of the icon's display, whichever edge the taskbar is on.</summary>
public static class FlyoutPlacement
{
    /// <summary>The taskbar's edge is where the work area stops short of the display. An auto-hidden taskbar
    /// leaves the two equal, so the edge nearest the icon is taken instead.</summary>
    public static TaskbarEdge Edge(Box display, Box work, int anchorX, int anchorY)
    {
        if (work.Bottom < display.Bottom) return TaskbarEdge.Bottom;
        if (work.Top > display.Top) return TaskbarEdge.Top;
        if (work.Left > display.Left) return TaskbarEdge.Left;
        if (work.Right < display.Right) return TaskbarEdge.Right;
        (TaskbarEdge Edge, int Distance)[] distances =
        [
            (TaskbarEdge.Bottom, display.Bottom - anchorY), (TaskbarEdge.Top, anchorY - display.Top),
            (TaskbarEdge.Left, anchorX - display.Left), (TaskbarEdge.Right, display.Right - anchorX),
        ];
        return distances.MinBy(entry => entry.Distance).Edge;
    }

    /// <returns>The flyout's top-left corner.</returns>
    public static (int X, int Y) Place(Box display, Box work, int anchorX, int anchorY, int width, int height, int margin)
    {
        static int Clamp(int value, int low, int high) => high < low ? low : Math.Clamp(value, low, high);
        var x = Clamp(anchorX - width / 2, work.Left + margin, work.Right - margin - width);
        var y = Clamp(anchorY - height / 2, work.Top + margin, work.Bottom - margin - height);
        return Edge(display, work, anchorX, anchorY) switch
        {
            TaskbarEdge.Bottom => (x, Math.Max(work.Top, work.Bottom - margin - height)),
            TaskbarEdge.Top => (x, work.Top + margin),
            TaskbarEdge.Left => (work.Left + margin, y),
            _ => (Math.Max(work.Left, work.Right - margin - width), y),
        };
    }
}

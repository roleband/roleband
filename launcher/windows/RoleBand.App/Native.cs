using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;
using Microsoft.UI.Xaml.Media.Imaging;
using System.Runtime.InteropServices;

namespace RoleBand.App;

/// <summary>What every window of the app shares: the command line, display scale, focus, and the product's icon.</summary>
internal static class Native
{
    /// <summary>The value after <paramref name="name"/> on the command line, if any.</summary>
    public static string? Option(string name)
    {
        var args = Environment.GetCommandLineArgs();
        var index = Array.IndexOf(args, name, 1);
        return index >= 1 && index + 1 < args.Length ? args[index + 1] : null;
    }

    public static bool Flag(string name) => Array.IndexOf(Environment.GetCommandLineArgs(), name, 1) >= 1;

    /// <summary>The scale of the display holding a point, in physical pixels per device-independent pixel.</summary>
    public static double ScaleAt(int x, int y) => DpiOf(MonitorFromPoint(new ScreenPoint { X = x, Y = y }, 2)) / 96.0;

    /// <summary>The primary display's DPI, where the notification area is drawn.</summary>
    public static uint PrimaryDpi() => DpiOf(MonitorFromPoint(new ScreenPoint(), 1));

    public static double ScaleOf(nint window) => Math.Max(96, GetDpiForWindow(window)) / 96.0;

    public static bool ForegroundIsOurs()
    {
        GetWindowThreadProcessId(GetForegroundWindow(), out var owner);
        return owner == (uint)Environment.ProcessId;
    }

    public static bool IsForeground(nint window) => GetForegroundWindow() == window;

    public static void BringForward(nint window) => SetForegroundWindow(window);

    /// <summary>The primary taskbar's rectangle in physical pixels, or null when Windows does not report one.</summary>
    public static RoleBand.EngineHost.Box? Taskbar()
    {
        var data = new AppBarData { Size = (uint)Marshal.SizeOf<AppBarData>() };
        const uint GetTaskbarPosition = 5;
        if (SHAppBarMessage(GetTaskbarPosition, ref data) == 0) return null;
        return data.Right > data.Left && data.Bottom > data.Top
            ? new RoleBand.EngineHost.Box(data.Left, data.Top, data.Right - data.Left, data.Bottom - data.Top)
            : null;
    }

    /// <summary>The product's icon in the title bar and the taskbar, and its mark beside the product's name.</summary>
    public static void Dress(Window window, Image? mark = null)
    {
        var icon = Path.Combine(AppContext.BaseDirectory, "RoleBand.ico");
        if (File.Exists(icon)) window.AppWindow.SetIcon(icon);
        if (mark is null) return;
        var image = Path.Combine(AppContext.BaseDirectory, "Images", "AppMark.png");
        if (File.Exists(image)) mark.Source = new BitmapImage(new Uri(image));
        else mark.Visibility = Visibility.Collapsed;
    }

    private static uint DpiOf(nint monitor) => GetDpiForMonitor(monitor, 0, out var dpi, out _) == 0 ? dpi : 96;

    [StructLayout(LayoutKind.Sequential)]
    private struct ScreenPoint { public int X, Y; }

    [StructLayout(LayoutKind.Sequential)]
    private struct AppBarData
    {
        public uint Size;
        public nint Window;
        public uint CallbackMessage, Edge;
        public int Left, Top, Right, Bottom;
        public nint Param;
    }

    [DllImport("shell32.dll")]
    private static extern nuint SHAppBarMessage(uint message, ref AppBarData data);
    [DllImport("user32.dll")]
    private static extern nint MonitorFromPoint(ScreenPoint point, uint flags);
    [DllImport("shcore.dll")]
    private static extern int GetDpiForMonitor(nint monitor, int type, out uint x, out uint y);
    [DllImport("user32.dll")]
    private static extern uint GetDpiForWindow(nint window);
    [DllImport("user32.dll")]
    private static extern nint GetForegroundWindow();
    [DllImport("user32.dll")]
    private static extern bool SetForegroundWindow(nint window);
    [DllImport("user32.dll")]
    private static extern uint GetWindowThreadProcessId(nint window, out uint process);
}

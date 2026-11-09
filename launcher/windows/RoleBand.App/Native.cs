using Microsoft.UI.Windowing;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Automation.Peers;
using Microsoft.UI.Xaml.Controls;
using Microsoft.UI.Xaml.Media;
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

    /// <summary>Tells Narrator a live region changed. It reads a live region when this event is raised, so text set in
    /// one is not heard without it.</summary>
    public static void Announce(UIElement element) => Peer(element)?.RaiseAutomationEvent(AutomationEvents.LiveRegionChanged);

    private static AutomationPeer? Peer(UIElement element) =>
        FrameworkElementAutomationPeer.FromElement(element) ?? FrameworkElementAutomationPeer.CreatePeerForElement(element);

    public static void BringForward(nint window) => SetForegroundWindow(window);

    /// <summary>The installed package's version, or null for an app run without a package.</summary>
    /// <summary>The installed package's name, or null for a copy without a package.</summary>
    public static string? PackageName()
    {
        try { return Windows.ApplicationModel.Package.Current.Id.Name; }
        catch (InvalidOperationException) { return null; }
    }

    public static (ushort, ushort, ushort, ushort)? PackageVersion()
    {
        try
        {
            var version = Windows.ApplicationModel.Package.Current.Id.Version;
            return (version.Major, version.Minor, version.Build, version.Revision);
        }
        catch (InvalidOperationException)
        {
            return null;
        }
    }

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

    /// <summary>The product's icon in the title bar and the taskbar, its mark beside the product's name, and the
    /// window frame in the content's theme.</summary>
    /// <param name="ownEdge">Draw the edge in the palette's divider colour. A framed window keeps the edge Windows
    /// gives every app; the flyout, which has no title bar, needs its own.</param>
    public static void Dress(Window window, Image? mark = null, bool ownEdge = false)
    {
        var icon = Path.Combine(AppContext.BaseDirectory, "RoleBand.ico");
        if (File.Exists(icon)) window.AppWindow.SetIcon(icon);
        if (window.Content is FrameworkElement root)
        {
            // Windows draws the title bar and the border of a window as light unless the window says it is dark.
            var handle = WinRT.Interop.WindowNative.GetWindowHandle(window);
            void Frame()
            {
                var dark = root.ActualTheme == ElementTheme.Dark;
                var immersiveDark = dark ? 1 : 0;
                DwmSetWindowAttribute(handle, ImmersiveDarkMode, ref immersiveDark, sizeof(int));
                // A contrast theme's colours are the person's choice, so Windows keeps drawing that frame.
                var contrast = HighContrast();
                var edge = contrast || !ownEdge ? DefaultColour : ColourRef(Palette("DividerStrokeColorDefaultBrush", dark));
                DwmSetWindowAttribute(handle, BorderColour, ref edge, sizeof(int));
                if (!AppWindowTitleBar.IsCustomizationSupported()) return;
                var title = window.AppWindow.TitleBar;
                if (contrast)
                {
                    title.ResetToDefault();
                    return;
                }
                var bar = Palette("RoleBandFrame", dark);
                var ink = Palette("RoleBandFrameInk", dark);
                var inactive = Palette("RoleBandFrameInactiveInk", dark);
                title.BackgroundColor = title.InactiveBackgroundColor = bar;
                title.ButtonBackgroundColor = title.ButtonInactiveBackgroundColor = bar;
                title.ForegroundColor = title.ButtonForegroundColor = title.ButtonHoverForegroundColor = title.ButtonPressedForegroundColor = ink;
                title.InactiveForegroundColor = title.ButtonInactiveForegroundColor = inactive;
                title.ButtonHoverBackgroundColor = Palette("RoleBandFrameHover", dark);
                title.ButtonPressedBackgroundColor = Palette("RoleBandFramePressed", dark);
            }
            Frame();
            root.ActualThemeChanged += (_, _) => Frame();
        }
        if (mark is null) return;
        var image = Path.Combine(AppContext.BaseDirectory, "Images", "AppMark.png");
        if (File.Exists(image)) mark.Source = new BitmapImage(new Uri(image));
        else mark.Visibility = Visibility.Collapsed;
    }

    private const int ImmersiveDarkMode = 20, BorderColour = 34;
    /// <summary>DWMWA_COLOR_DEFAULT: Windows chooses the edge.</summary>
    private const int DefaultColour = unchecked((int)0xFFFFFFFF);

    /// <summary>A colour of App.xaml's light or dark theme dictionary, the one palette the windows and their frames share.
    /// The last merged dictionary wins, as it does in XAML: RoleBand's palette overrides WinUI's own brushes, some of
    /// which are translucent, and a frame colour has no alpha.</summary>
    private static Windows.UI.Color Palette(string key, bool dark)
    {
        foreach (var dictionary in Application.Current.Resources.MergedDictionaries.Reverse())
        {
            if (dictionary.ThemeDictionaries.TryGetValue(dark ? "Default" : "Light", out var theme)
                && ((ResourceDictionary)theme).TryGetValue(key, out var brush))
                return ((SolidColorBrush)brush).Color;
        }
        throw new KeyNotFoundException($"App.xaml has no {key} brush.");
    }

    /// <summary>Whether a contrast theme is on. WinRT's AccessibilitySettings cannot be created in a desktop app.</summary>
    private static bool HighContrast()
    {
        var info = new HighContrastInfo { Size = (uint)Marshal.SizeOf<HighContrastInfo>() };
        const uint GetHighContrast = 0x42, HighContrastOn = 0x1;
        return SystemParametersInfo(GetHighContrast, info.Size, ref info, 0) && (info.Flags & HighContrastOn) != 0;
    }

    /// <summary>A colour as DWM's COLORREF, 0x00BBGGRR.</summary>
    private static int ColourRef(Windows.UI.Color colour) => colour.R | colour.G << 8 | colour.B << 16;

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
    [StructLayout(LayoutKind.Sequential)]
    private struct HighContrastInfo
    {
        public uint Size, Flags;
        public nint Scheme;
    }

    [DllImport("user32.dll")]
    private static extern bool SystemParametersInfo(uint action, uint parameter, ref HighContrastInfo info, uint update);
    [DllImport("dwmapi.dll")]
    private static extern int DwmSetWindowAttribute(nint window, int attribute, ref int value, int size);
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

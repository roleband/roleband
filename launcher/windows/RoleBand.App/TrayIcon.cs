using System.ComponentModel;
using System.Runtime.InteropServices;
using RoleBand.EngineHost;

namespace RoleBand.App;

/// <summary>
/// The notification-area icon, on a window's own message loop. Version-4 notifications deliver a click or
/// Enter as select, with the icon's anchor point, a double-click as itself, and a right click or Shift+F10
/// as the context menu, so the icon works from the keyboard as well as the mouse.
/// </summary>
internal sealed class TrayIcon : IDisposable
{
    private const uint Callback = 0x8000 + 1;
    private const uint IconId = 1;
    private const uint Add = 0, Modify = 1, Delete = 2, SetVersion = 4;
    private const uint MessageFlag = 0x1, IconFlag = 0x2, TipFlag = 0x4, ShowTipFlag = 0x80;
    private const int Select = 0x400, KeySelect = 0x401, ContextMenu = 0x7B, DoubleClick = 0x203;
    private const uint SettingChange = 0x001A, DisplayChange = 0x007E, DpiChanged = 0x02E0;
    private readonly nint window;
    private readonly SubclassProcedure procedure;
    private readonly uint taskbarCreated;
    private readonly Func<IReadOnlyList<MenuEntry>> menu;
    private nint icon;
    private (bool Light, int Size) drawn;
    private TrayBadge badge = TrayBadge.None;
    private string tooltip = "RoleBand";
    private long lastKeySelect;
    private bool disposed;

    /// <summary>A click or Enter, with the point Windows anchors the icon at, in physical pixels.</summary>
    public event Action<int, int>? Selected;
    public event Action? DoubleClicked;
    public event Action<MenuCommand>? Chosen;

    /// <param name="menu">The menu, read when it opens.</param>
    public TrayIcon(nint window, Func<IReadOnlyList<MenuEntry>> menu)
    {
        this.window = window;
        this.menu = menu;
        icon = LoadIcon(badge);
        procedure = Procedure;
        if (!SetWindowSubclass(window, procedure, 1, 0)) throw new Win32Exception(Marshal.GetLastWin32Error());
        taskbarCreated = RegisterWindowMessage("TaskbarCreated");
        Register();
    }

    public void Show(TrayBadge state, string text)
    {
        var flags = 0u;
        if (state != badge)
        {
            badge = state;
            Replace();
            flags |= IconFlag;
        }
        if (text != tooltip)
        {
            tooltip = text;
            flags |= TipFlag | ShowTipFlag;
        }
        if (flags == 0) return;
        var data = Data(flags);
        Shell_NotifyIcon(Modify, ref data);
    }

    private void Register()
    {
        var data = Data(MessageFlag | IconFlag | TipFlag | ShowTipFlag);
        if (!Shell_NotifyIcon(Add, ref data)) throw new Win32Exception("The notification-area icon could not be added.");
        data.Version = 4;
        Shell_NotifyIcon(SetVersion, ref data);
    }

    /// <summary>Draws the icon again for the taskbar's theme and scale, which can change while the app runs.</summary>
    private void Replace()
    {
        var previous = icon;
        icon = LoadIcon(badge);
        if (previous != 0) DestroyIcon(previous);
    }

    private NotifyIconData Data(uint flags) => new()
    {
        Size = (uint)Marshal.SizeOf<NotifyIconData>(), Window = window, Id = IconId, Flags = flags,
        CallbackMessage = Callback, Icon = icon, Tip = tooltip,
    };

    private nint Procedure(nint hwnd, uint message, nint wParam, nint lParam, nuint id, nuint data)
    {
        if (message == Callback)
        {
            var x = (short)(wParam.ToInt64() & 0xFFFF);
            var y = (short)((wParam.ToInt64() >> 16) & 0xFFFF);
            switch ((int)(lParam.ToInt64() & 0xFFFF))
            {
                case Select:
                    Selected?.Invoke(x, y);
                    break;
                case KeySelect:
                    // The shell reports one press of Enter or Space as two key selects.
                    var now = Environment.TickCount64;
                    if (now - lastKeySelect > 300) Selected?.Invoke(x, y);
                    lastKeySelect = now;
                    break;
                case DoubleClick:
                    DoubleClicked?.Invoke();
                    break;
                case ContextMenu:
                    ShowMenu(x, y);
                    break;
            }
            return 0;
        }
        if (message == taskbarCreated)
        {
            // Explorer restarted and forgot every icon.
            Replace();
            Register();
        }
        // Settings broadcasts are frequent; the icon is drawn again only when its theme or size really changed.
        else if ((message is SettingChange or DisplayChange or DpiChanged) && Look() != drawn)
        {
            Replace();
            var update = Data(IconFlag);
            Shell_NotifyIcon(Modify, ref update);
        }
        return DefSubclassProc(hwnd, message, wParam, lParam);
    }

    private void ShowMenu(int x, int y)
    {
        var root = Build(menu());
        try
        {
            // The menu closes when focus leaves it only if its owner is the foreground window.
            SetForegroundWindow(window);
            var chosen = TrackPopupMenuEx(root, 0x100 | 0x80 | 0x2, x, y, window, 0);
            PostMessage(window, 0, 0, 0);
            if (chosen != 0) Chosen?.Invoke((MenuCommand)chosen);
        }
        finally
        {
            // Destroying the root destroys the submenus attached to it.
            DestroyMenu(root);
        }
    }

    private static nint Build(IReadOnlyList<MenuEntry> entries)
    {
        var menu = CreatePopupMenu();
        foreach (var entry in entries)
        {
            if (entry.IsSeparator) { AppendMenu(menu, 0x800, 0, null); continue; }
            var check = entry.Checked ? 0x8u : 0u;
            if (entry.Items is { } items) AppendMenu(menu, 0x10 | check, (nuint)Build(items), entry.Text);
            else AppendMenu(menu, check, (nuint)(int)entry.Command!.Value, entry.Text);
            if (entry.Default && entry.Command is { } command) SetMenuDefaultItem(menu, (uint)command, 0);
        }
        return menu;
    }

    /// <summary>The frame drawn for the notification area's size on the primary display, from the set for the
    /// taskbar's theme. A contrast theme takes the set whose ink stands out on its window colour.</summary>
    private nint LoadIcon(TrayBadge state)
    {
        drawn = Look();
        var name = TrayArt.Resource(state, drawn.Light);
        using var stream = typeof(TrayIcon).Assembly.GetManifestResourceStream(name)
            ?? throw new IOException("The notification-area icon is missing.");
        using var copy = new MemoryStream();
        stream.CopyTo(copy);
        var (bytes, frame) = TrayArt.Frame(copy.ToArray(), drawn.Size);
        var handle = CreateIconFromResourceEx(bytes, bytes.Length, true, 0x00030000, frame, frame, 0);
        if (handle == 0) throw new Win32Exception(Marshal.GetLastWin32Error());
        return handle;
    }

    /// <summary>The taskbar's theme and the notification area's icon size on the primary display.</summary>
    private static (bool Light, int Size) Look() => (LightTaskbar(), GetSystemMetricsForDpi(49, Native.PrimaryDpi()));

    private static bool LightTaskbar()
    {
        var contrast = new HighContrast { Size = (uint)Marshal.SizeOf<HighContrast>() };
        if (SystemParametersInfo(0x0042, contrast.Size, ref contrast, 0) && (contrast.Flags & 0x1) != 0)
        {
            var window = GetSysColor(5);
            return (window & 0xFF) * 299 + ((window >> 8) & 0xFF) * 587 + ((window >> 16) & 0xFF) * 114 > 128_000;
        }
        using var key = Microsoft.Win32.Registry.CurrentUser.OpenSubKey(@"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize");
        return key?.GetValue("SystemUsesLightTheme") is int light && light != 0;
    }

    public void Dispose()
    {
        if (disposed) return;
        disposed = true;
        var data = Data(0);
        Shell_NotifyIcon(Delete, ref data);
        RemoveWindowSubclass(window, procedure, 1);
        DestroyIcon(icon);
    }

    private delegate nint SubclassProcedure(nint hwnd, uint message, nint wParam, nint lParam, nuint id, nuint data);

    [StructLayout(LayoutKind.Sequential, CharSet = CharSet.Unicode)]
    private struct NotifyIconData
    {
        public uint Size;
        public nint Window;
        public uint Id;
        public uint Flags;
        public uint CallbackMessage;
        public nint Icon;
        [MarshalAs(UnmanagedType.ByValTStr, SizeConst = 128)] public string Tip;
        public uint State;
        public uint StateMask;
        [MarshalAs(UnmanagedType.ByValTStr, SizeConst = 256)] public string Info;
        public uint Version;
        [MarshalAs(UnmanagedType.ByValTStr, SizeConst = 64)] public string InfoTitle;
        public uint InfoFlags;
        public Guid Item;
        public nint BalloonIcon;
    }

    [StructLayout(LayoutKind.Sequential)]
    private struct HighContrast { public uint Size; public uint Flags; public nint Scheme; }

    [DllImport("shell32.dll", CharSet = CharSet.Unicode, EntryPoint = "Shell_NotifyIconW")]
    private static extern bool Shell_NotifyIcon(uint message, ref NotifyIconData data);
    [DllImport("comctl32.dll", SetLastError = true)]
    private static extern bool SetWindowSubclass(nint window, SubclassProcedure procedure, nuint id, nuint data);
    [DllImport("comctl32.dll")]
    private static extern bool RemoveWindowSubclass(nint window, SubclassProcedure procedure, nuint id);
    [DllImport("comctl32.dll")]
    private static extern nint DefSubclassProc(nint window, uint message, nint wParam, nint lParam);
    [DllImport("user32.dll", CharSet = CharSet.Unicode)]
    private static extern uint RegisterWindowMessage(string name);
    [DllImport("user32.dll", SetLastError = true)]
    private static extern nint CreateIconFromResourceEx(byte[] data, int size, bool icon, uint version, int width, int height, uint flags);
    [DllImport("user32.dll")]
    private static extern bool DestroyIcon(nint icon);
    [DllImport("user32.dll")]
    private static extern int GetSystemMetricsForDpi(int index, uint dpi);
    [DllImport("user32.dll")]
    private static extern uint GetSysColor(int index);
    [DllImport("user32.dll", EntryPoint = "SystemParametersInfoW")]
    private static extern bool SystemParametersInfo(uint action, uint parameter, ref HighContrast value, uint flags);
    [DllImport("user32.dll")]
    private static extern nint CreatePopupMenu();
    [DllImport("user32.dll", CharSet = CharSet.Unicode, EntryPoint = "AppendMenuW")]
    private static extern bool AppendMenu(nint menu, uint flags, nuint id, string? text);
    [DllImport("user32.dll")]
    private static extern bool SetMenuDefaultItem(nint menu, uint item, uint byPosition);
    [DllImport("user32.dll")]
    private static extern int TrackPopupMenuEx(nint menu, uint flags, int x, int y, nint window, nint parameters);
    [DllImport("user32.dll")]
    private static extern bool DestroyMenu(nint menu);
    [DllImport("user32.dll")]
    private static extern bool SetForegroundWindow(nint window);
    [DllImport("user32.dll")]
    private static extern bool PostMessage(nint window, uint message, nint wParam, nint lParam);
}

using System.ComponentModel;
using System.Runtime.InteropServices;

namespace RoleBand.App;

/// <summary>
/// The notification-area icon, on the window's own message loop. Version-4 notifications
/// deliver a click or Enter as select and a right click or Shift+F10 as the context menu,
/// so the icon works from the keyboard as well as the mouse.
/// </summary>
internal sealed class TrayIcon : IDisposable
{
    public sealed record Item(int Command, string Text, bool Enabled);

    private const uint Callback = 0x8000 + 1;
    private const uint IconId = 1;
    private const uint Add = 0, Modify = 1, Delete = 2, SetVersion = 4;
    private const uint MessageFlag = 0x1, IconFlag = 0x2, TipFlag = 0x4, ShowTipFlag = 0x80;
    private const int Select = 0x400, KeySelect = 0x401, ContextMenu = 0x7B;
    private readonly nint window;
    private readonly SubclassProcedure procedure;
    private readonly uint taskbarCreated;
    private readonly nint icon;
    private readonly Func<IReadOnlyList<Item?>> items;
    private string tooltip = "RoleBand";
    private bool disposed;

    public event Action? Opened;
    public event Action<int>? Chosen;

    /// <param name="items">The menu, read when it opens; null draws a separator.</param>
    public TrayIcon(nint window, byte[] png, Func<IReadOnlyList<Item?>> items)
    {
        this.window = window;
        this.items = items;
        var size = GetSystemMetrics(49);
        icon = CreateIconFromResourceEx(png, png.Length, true, 0x00030000, size, size, 0);
        if (icon == 0) throw new Win32Exception(Marshal.GetLastWin32Error());
        procedure = Procedure;
        if (!SetWindowSubclass(window, procedure, 1, 0)) throw new Win32Exception(Marshal.GetLastWin32Error());
        taskbarCreated = RegisterWindowMessage("TaskbarCreated");
        Register();
    }

    public void SetTooltip(string text)
    {
        tooltip = text;
        var data = Data(TipFlag | ShowTipFlag);
        Shell_NotifyIcon(Modify, ref data);
    }

    private void Register()
    {
        var data = Data(MessageFlag | IconFlag | TipFlag | ShowTipFlag);
        if (!Shell_NotifyIcon(Add, ref data)) throw new Win32Exception("The notification-area icon could not be added.");
        data.Version = 4;
        Shell_NotifyIcon(SetVersion, ref data);
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
            switch ((int)(lParam.ToInt64() & 0xFFFF))
            {
                case Select or KeySelect:
                    Opened?.Invoke();
                    break;
                case ContextMenu:
                    ShowMenu((short)(wParam.ToInt64() & 0xFFFF), (short)((wParam.ToInt64() >> 16) & 0xFFFF));
                    break;
            }
            return 0;
        }
        // Explorer restarted and forgot every icon.
        if (message == taskbarCreated) Register();
        return DefSubclassProc(hwnd, message, wParam, lParam);
    }

    private void ShowMenu(int x, int y)
    {
        var menu = CreatePopupMenu();
        try
        {
            foreach (var item in items())
            {
                if (item is null) AppendMenu(menu, 0x800, 0, null);
                else AppendMenu(menu, item.Enabled ? 0u : 0x1u, (nuint)item.Command, item.Text);
            }
            // The menu closes when focus leaves it only if its owner is the foreground window.
            SetForegroundWindow(window);
            var chosen = TrackPopupMenuEx(menu, 0x100 | 0x80 | 0x2, x, y, window, 0);
            PostMessage(window, 0, 0, 0);
            if (chosen != 0) Chosen?.Invoke(chosen);
        }
        finally
        {
            DestroyMenu(menu);
        }
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
    private static extern int GetSystemMetrics(int index);
    [DllImport("user32.dll")]
    private static extern nint CreatePopupMenu();
    [DllImport("user32.dll", CharSet = CharSet.Unicode, EntryPoint = "AppendMenuW")]
    private static extern bool AppendMenu(nint menu, uint flags, nuint id, string? text);
    [DllImport("user32.dll")]
    private static extern int TrackPopupMenuEx(nint menu, uint flags, int x, int y, nint window, nint parameters);
    [DllImport("user32.dll")]
    private static extern bool DestroyMenu(nint menu);
    [DllImport("user32.dll")]
    private static extern bool SetForegroundWindow(nint window);
    [DllImport("user32.dll")]
    private static extern bool PostMessage(nint window, uint message, nint wParam, nint lParam);
}

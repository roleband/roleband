using System.Runtime.CompilerServices;
using System.Runtime.InteropServices;

namespace RoleBand.Setup;

internal enum PageIcon { App, Warning, Error }

/// <summary>A button of a page, and what pressing it does.</summary>
internal sealed record PageButton(int Id, string Text, bool Elevates = false);

/// <summary>One page of Setup's window.</summary>
/// <param name="Progress">A progress bar: a percentage set while the page shows, or, when <paramref name="Waiting"/>, one
/// that moves without a figure.</param>
/// <param name="Detail">Shown under the body, behind Windows' own "See details" control.</param>
internal sealed record Page(string Heading, string? Body, PageIcon Icon, IReadOnlyList<PageButton> Buttons, bool Progress = false,
                            bool Waiting = false, string? Detail = null);

/// <summary>Setup's window: Windows' own task dialog, moved from page to page. It runs on the thread that shows it; the
/// other methods may be called from any thread while it shows.</summary>
internal sealed unsafe class SetupWindow(string title, Func<int, bool> pressed)
{
    /// <summary>The id Windows gives Escape and the title bar's close button.</summary>
    public const int Cancel = 2;

    private const uint UserMessage = 0x0400;
    private const uint NavigatePage = UserMessage + 101, ClickButton = UserMessage + 102, SetProgressPosition = UserMessage + 106,
        SetMarquee = UserMessage + 107, SetElementText = UserMessage + 108, SetElevationRequired = UserMessage + 115;
    private const int Created = 0, Navigated = 1, ButtonClicked = 2, Destroyed = 5;
    private const int AllowCancellation = 0x0008, ShowProgress = 0x0200, ShowMarquee = 0x0400, ExpandFooterArea = 0x0040;
    private const int ContentElement = 0;
    /// <summary>The icon Windows takes from Setup's own resources: the application icon the build embeds.</summary>
    private const int ApplicationIcon = 32512;

    private readonly Func<int, bool> onPress = pressed;
    private readonly List<nint> allocated = [];
    private readonly object gate = new();
    private nint handle, self;
    private Page? shown;

    /// <summary>Shows the window on <paramref name="first"/> until a press closes it.</summary>
    public void Show(Page first)
    {
        var pinned = GCHandle.Alloc(this);
        self = GCHandle.ToIntPtr(pinned);
        try
        {
            var config = Build(first);
            if (TaskDialogIndirect(config, out _, out _, out _) is var result and not 0)
                throw new COMException("Windows could not show Setup's window.", result);
        }
        finally
        {
            pinned.Free();
            lock (gate)
            {
                foreach (var memory in allocated) Marshal.FreeHGlobal(memory);
                allocated.Clear();
            }
        }
    }

    public void Navigate(Page page) => Send(NavigatePage, 0, Build(page));

    public void SetProgress(int percent) => Send(SetProgressPosition, Math.Clamp(percent, 0, 100), 0);

    public void SetBody(string text) => Send(SetElementText, ContentElement, Text(text));

    /// <summary>Closes the window, as though <paramref name="button"/> were pressed.</summary>
    public void Press(int button) => Send(ClickButton, button, 0);

    private void Send(uint message, nint wParam, nint lParam)
    {
        if (handle != 0) _ = SendMessage(handle, message, wParam, lParam);
    }

    private nint Text(string? text)
    {
        if (text is null) return 0;
        var memory = Marshal.StringToHGlobalUni(text);
        lock (gate) allocated.Add(memory);
        return memory;
    }

    private nint Allocate(int size)
    {
        var memory = Marshal.AllocHGlobal(size);
        lock (gate) allocated.Add(memory);
        return memory;
    }

    private nint Build(Page page)
    {
        var buttons = Allocate(page.Buttons.Count * sizeof(Button));
        for (var index = 0; index < page.Buttons.Count; index++)
            ((Button*)buttons)[index] = new Button { Id = page.Buttons[index].Id, Text = Text(page.Buttons[index].Text) };
        var flags = AllowCancellation | (page.Waiting ? ShowMarquee : page.Progress ? ShowProgress : 0) | (page.Detail is null ? 0 : ExpandFooterArea);
        var config = (Config*)Allocate(sizeof(Config));
        *config = new Config
        {
            Size = (uint)sizeof(Config),
            Instance = GetModuleHandle(0),
            Flags = flags,
            WindowTitle = Text(title),
            MainIcon = page.Icon switch { PageIcon.Warning => 0xFFFF, PageIcon.Error => 0xFFFE, _ => ApplicationIcon },
            MainInstruction = Text(page.Heading),
            Content = Text(page.Body),
            ButtonCount = (uint)page.Buttons.Count,
            Buttons = buttons,
            DefaultButton = page.Buttons.Count > 0 ? page.Buttons[0].Id : 0,
            // Windows labels the control that shows it in its own language.
            ExpandedInformation = Text(page.Detail),
            Callback = (nint)(delegate* unmanaged<nint, uint, nint, nint, nint, int>)&Notify,
            CallbackData = self,
        };
        lock (gate) shown = page;
        return (nint)config;
    }

    [UnmanagedCallersOnly]
    private static int Notify(nint window, uint notification, nint wParam, nint lParam, nint data)
    {
        if (GCHandle.FromIntPtr(data).Target is not SetupWindow setup) return 0;
        switch ((int)notification)
        {
            case Created:
            case Navigated:
                setup.handle = window;
                Page? page;
                lock (setup.gate) page = setup.shown;
                if (page is null) return 0;
                if (page.Waiting) _ = SendMessage(window, SetMarquee, 1, 30);
                foreach (var button in page.Buttons.Where(button => button.Elevates))
                    _ = SendMessage(window, SetElevationRequired, button.Id, 1);
                return 0;
            case ButtonClicked:
                // S_OK closes the window; S_FALSE keeps it, for a press that moves to another page.
                return setup.onPress((int)wParam) ? 0 : 1;
            case Destroyed:
                setup.handle = 0;
                return 0;
            default:
                return 0;
        }
    }

    [StructLayout(LayoutKind.Sequential, Pack = 1)]
    private struct Button
    {
        public int Id;
        public nint Text;
    }

    /// <summary>TASKDIALOGCONFIG, which Windows packs to one byte.</summary>
    [StructLayout(LayoutKind.Sequential, Pack = 1)]
    private struct Config
    {
        public uint Size;
        public nint Parent;
        public nint Instance;
        public int Flags;
        public int CommonButtons;
        public nint WindowTitle;
        public nint MainIcon;
        public nint MainInstruction;
        public nint Content;
        public uint ButtonCount;
        public nint Buttons;
        public int DefaultButton;
        public uint RadioButtonCount;
        public nint RadioButtons;
        public int DefaultRadioButton;
        public nint VerificationText;
        public nint ExpandedInformation;
        public nint ExpandedControlText;
        public nint CollapsedControlText;
        public nint FooterIcon;
        public nint Footer;
        public nint Callback;
        public nint CallbackData;
        public uint Width;
    }

    [DllImport("comctl32.dll", ExactSpelling = true)]
    private static extern int TaskDialogIndirect(nint config, out int button, out int radio, out int verified);

    [DllImport("user32.dll", EntryPoint = "SendMessageW")]
    private static extern nint SendMessage(nint window, uint message, nint wParam, nint lParam);

    [DllImport("kernel32.dll", EntryPoint = "GetModuleHandleW")]
    private static extern nint GetModuleHandle(nint name);
}

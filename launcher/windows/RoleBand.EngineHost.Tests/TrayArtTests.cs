using Microsoft.VisualStudio.TestTools.UnitTesting;

namespace RoleBand.EngineHost.Tests;

[TestClass]
public sealed class TrayArtTests
{
    private static string TrayFolder()
    {
        for (var folder = new DirectoryInfo(AppContext.BaseDirectory); folder is not null; folder = folder.Parent)
        {
            var tray = Path.Combine(folder.FullName, "RoleBand.App", "Tray");
            if (Directory.Exists(tray)) return tray;
        }
        throw new DirectoryNotFoundException("RoleBand.App/Tray");
    }

    [TestMethod]
    public void EveryStateHasItsOwnIconForEachTaskbarTheme()
    {
        var names = new HashSet<string>();
        foreach (var badge in Enum.GetValues<TrayBadge>())
        foreach (var light in new[] { true, false })
        {
            var file = TrayArt.File(badge, light);
            Assert.IsTrue(names.Add(file), file);
            Assert.IsTrue(File.Exists(Path.Combine(TrayFolder(), file)), file);
            Assert.AreEqual("RoleBand.Tray." + file, TrayArt.Resource(badge, light));
        }
        Assert.AreEqual(10, names.Count);
    }

    [TestMethod]
    public void TheFrameDrawnForTheSizeIsTakenNeverAScaledOne()
    {
        var ico = File.ReadAllBytes(Path.Combine(TrayFolder(), TrayArt.File(TrayBadge.Scanning, lightTaskbar: false)));
        foreach (var size in new[] { 16, 20, 24, 32 })
        {
            var (image, frame) = TrayArt.Frame(ico, size);
            Assert.AreEqual(size, frame);
            CollectionAssert.AreEqual(new byte[] { 0x89, (byte)'P', (byte)'N', (byte)'G' }, image[..4]);
            Assert.AreEqual(size, (image[16] << 24) | (image[17] << 16) | (image[18] << 8) | image[19], "the PNG is as wide as its entry says");
        }
        Assert.AreEqual(32, TrayArt.Frame(ico, 28).Size, "175% takes the next larger drawing");
        Assert.AreEqual(32, TrayArt.Frame(ico, 40).Size, "past the largest, the largest");
        Assert.AreEqual(16, TrayArt.Frame(ico, 12).Size);
    }

    [TestMethod]
    public void AFileThatIsNotAnIconOrPointsOutsideItselfIsRefused()
    {
        Assert.ThrowsExactly<InvalidDataException>(() => TrayArt.Frame([0x89, 0x50, 0x4E, 0x47, 0, 0], 16));
        byte[] broken = [0, 0, 1, 0, 1, 0, 16, 16, 0, 0, 1, 0, 32, 0, 0xFF, 0, 0, 0, 22, 0, 0, 0];
        Assert.ThrowsExactly<InvalidDataException>(() => TrayArt.Frame(broken, 16));
    }

    private static readonly Box Display = new(0, 0, 1920, 1080);

    [TestMethod]
    public void TheFlyoutOpensAMarginOffTheTaskbarOnWhicheverEdgeItIs()
    {
        // Bottom: right-aligned inside the work area, above the taskbar.
        Assert.AreEqual((1362, 614), FlyoutPlacement.Place(Display, new Box(0, 0, 1920, 1032), 1800, 1060, 540, 400, 18));
        // Top: below the taskbar.
        Assert.AreEqual((1362, 66), FlyoutPlacement.Place(Display, new Box(0, 48, 1920, 1032), 1800, 20, 540, 400, 18));
        // Left: beside the taskbar, centred on the icon and kept inside the work area.
        Assert.AreEqual((66, 662), FlyoutPlacement.Place(Display, new Box(48, 0, 1872, 1080), 20, 1040, 540, 400, 18));
        Assert.AreEqual((66, 300), FlyoutPlacement.Place(Display, new Box(48, 0, 1872, 1080), 20, 500, 540, 400, 18));
        // Right.
        Assert.AreEqual((1314, 662), FlyoutPlacement.Place(Display, new Box(0, 0, 1872, 1080), 1900, 1040, 540, 400, 18));
    }

    [TestMethod]
    public void AnAutoHiddenTaskbarIsFoundFromTheIconAndASecondDisplayKeepsItsOwnBounds()
    {
        Assert.AreEqual(TaskbarEdge.Bottom, FlyoutPlacement.Edge(Display, Display, 1800, 1075));
        Assert.AreEqual(TaskbarEdge.Left, FlyoutPlacement.Edge(Display, Display, 3, 600));
        Assert.AreEqual(TaskbarEdge.Top, FlyoutPlacement.Edge(Display, Display, 900, 2));
        Assert.AreEqual((1362, 662), FlyoutPlacement.Place(Display, Display, 1800, 1075, 540, 400, 18));

        var second = new Box(1920, -200, 2560, 1440);
        var (x, y) = FlyoutPlacement.Place(second, new Box(1920, -200, 2560, 1392), 4400, 1220, 540, 400, 18);
        Assert.AreEqual((3922, 774), (x, y));
        // Taller than the work area: the top stays on screen.
        Assert.AreEqual(0, FlyoutPlacement.Place(Display, new Box(0, 0, 1920, 1032), 1800, 1060, 540, 1200, 18).Y);
    }

    [TestMethod]
    public void TheFlyoutClearsAnAutoHiddenTaskbarThatShowsBesideIt()
    {
        // The work area is the whole display; the taskbar shows while the flyout is open.
        var shown = new Box(0, 1032, 1920, 48);
        Assert.AreEqual((1362, 614), FlyoutPlacement.Place(Display, Display, 1800, 1060, 540, 400, 18, shown));
        // Slid away, Windows reports it mostly off the display: its full thickness still counts.
        var hidden = new Box(0, 1078, 1920, 48);
        Assert.AreEqual((1362, 614), FlyoutPlacement.Place(Display, Display, 1800, 1079, 540, 400, 18, hidden));
        var away = new Box(0, 1080, 1920, 48);
        Assert.AreEqual((1362, 614), FlyoutPlacement.Place(Display, Display, 1800, 1079, 540, 400, 18, away));
        Assert.AreEqual((66, 662), FlyoutPlacement.Place(Display, Display, 3, 1040, 540, 400, 18, new Box(0, 0, 48, 1080)));
        Assert.AreEqual((1362, 66), FlyoutPlacement.Place(Display, Display, 1800, 3, 540, 400, 18, new Box(0, 0, 1920, 48)));
        Assert.AreEqual((1314, 662), FlyoutPlacement.Place(Display, Display, 1917, 1040, 540, 400, 18, new Box(1872, 0, 48, 1080)));
        // A taskbar that already shapes the work area changes nothing, nor does one on another display.
        Assert.AreEqual((1362, 614), FlyoutPlacement.Place(Display, new Box(0, 0, 1920, 1032), 1800, 1060, 540, 400, 18, shown));
        var second = new Box(1920, -200, 2560, 1440);
        Assert.AreEqual((3922, 822), FlyoutPlacement.Place(second, second, 4400, 1235, 540, 400, 18, shown));
    }
}

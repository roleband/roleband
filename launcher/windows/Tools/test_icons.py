import math
import random
import struct
import unittest
import zlib
from collections import Counter
from pathlib import Path
from xml.etree import ElementTree

from icons import badge_geometry
from make_icons import read_png, write_png

WINDOWS = Path(__file__).resolve().parents[1]
ASSETS = WINDOWS / "Assets"
TRAY = WINDOWS / "RoleBand.App/Tray"
SIGNATURE = b"\x89PNG\r\n\x1a\n"

TARGET_SIZES = (16, 20, 24, 30, 32, 36, 40, 48, 60, 64, 72, 80, 96, 256)
SCALED = {
    "Square44x44Logo": {100: 44, 125: 55, 150: 66, 200: 88, 400: 176},
    "Square150x150Logo": {100: 150, 125: 188, 150: 225, 200: 300, 400: 600},
    "StoreLogo": {100: 50, 125: 63, 150: 75, 200: 100, 400: 200},
}
TRAY_SIZES = [16, 20, 24, 32]
APP_ICO_SIZES = [16, 20, 24, 32, 40, 48, 64, 256]
THEMES = ("light", "dark")
BADGES = {"scanning": {"light": "08607D", "dark": "6FC9E6"}, "paused": {"light": "5A5A5A", "dark": "D0D0D0"},
          "attention": {"light": "9D5D00", "dark": "EFA85E"}, "stopped": {"light": "C42B1C", "dark": "FF99A4"}}


def png_size(data):
    if data[:8] != SIGNATURE or data[12:16] != b"IHDR":
        raise AssertionError("not a PNG")
    return struct.unpack(">II", data[16:24])


def ico_entries(path):
    """[(directory width, directory height, bit count, PNG bytes)] in file order."""
    data = path.read_bytes()
    reserved, kind, count = struct.unpack("<HHH", data[:6])
    assert (reserved, kind) == (0, 1), f"{path.name} is not an icon file"
    entries = []
    for index in range(count):
        width, height, _, _, planes, bits, size, offset = struct.unpack("<BBBBHHII", data[6 + 16 * index:22 + 16 * index])
        assert planes == 1, f"{path.name} entry {index} has {planes} planes"
        entries.append((width or 256, height or 256, bits, data[offset:offset + size]))
    return entries


def tray_frame(theme, state, px):
    for width, _, _, png in ico_entries(TRAY / f"tray-{theme}-{state}.ico"):
        if width == px:
            return read_png(png)[2]
    raise AssertionError(f"tray-{theme}-{state}.ico has no {px} px frame")


def gap_pixels(px):
    """Pixels whose centre lies in the badge's cut-out gap at least 0.35 px from both of its
    edges, where anti-aliasing of the badge and the cut-out cannot reach full coverage."""
    br, k, bc = badge_geometry(px)
    return [(x, y) for y in range(px) for x in range(px)
            if br + 0.35 <= math.hypot(x + 0.5 - bc, y + 0.5 - bc) <= k - 0.35]


class PackageAssetTests(unittest.TestCase):
    def assertPng(self, path, px):
        self.assertTrue(path.is_file(), f"{path.name} is missing")
        self.assertEqual(png_size(path.read_bytes()), (px, px), path.name)

    def test_every_target_size_and_unplated_form_exists_at_its_size(self):
        for px in TARGET_SIZES:
            for form in ("", "_altform-unplated", "_altform-lightunplated"):
                with self.subTest(px=px, form=form):
                    self.assertPng(ASSETS / f"Square44x44Logo.targetsize-{px}{form}.png", px)

    def test_every_scaled_logo_and_its_fallback_exists_at_its_size(self):
        for name, scales in SCALED.items():
            for scale, px in scales.items():
                with self.subTest(name=name, scale=scale):
                    self.assertPng(ASSETS / f"{name}.scale-{scale}.png", px)
            with self.subTest(name=name, scale="fallback"):
                self.assertPng(ASSETS / f"{name}.png", scales[100])

    def test_the_app_icon_file_holds_each_size_as_a_png(self):
        entries = ico_entries(WINDOWS / "RoleBand.App/RoleBand.ico")
        self.assertEqual([width for width, *_ in entries], APP_ICO_SIZES)
        for width, height, bits, png in entries:
            with self.subTest(px=width):
                self.assertEqual((height, bits), (width, 32))
                self.assertEqual(png_size(png), (width, width))

    def test_the_store_logo_is_opaque_to_every_edge(self):
        """App Installer shows the package logo on the accent colour, which shows through any transparency."""
        manifest = ElementTree.parse(WINDOWS / "AppxManifest.xml").getroot()
        logo = manifest.find("{http://schemas.microsoft.com/appx/manifest/foundation/windows10}Properties/"
                             "{http://schemas.microsoft.com/appx/manifest/foundation/windows10}Logo").text
        self.assertEqual(logo, r"Assets\StoreLogo.png")
        for path in sorted(ASSETS.glob("StoreLogo*.png")):
            with self.subTest(asset=path.name):
                width, height, pixels = read_png(path.read_bytes())
                for x, y in ((0, 0), (width - 1, 0), (0, height - 1), (width - 1, height - 1), (width // 2, 0)):
                    self.assertEqual(pixels[(y * width + x) * 4 + 3], 255, f"({x}, {y})")

    def test_icons_are_transparent_outside_the_plate(self):
        for px in (16, 32, 256):
            with self.subTest(px=px):
                _, _, pixels = read_png((ASSETS / f"Square44x44Logo.targetsize-{px}.png").read_bytes())
                self.assertEqual(pixels[3], 0, "corner")
                middle = (px // 2 * px + px // 2) * 4
                self.assertEqual(pixels[middle + 3], 255, "centre of the plate")


class TrayIconTests(unittest.TestCase):
    def test_every_tray_icon_holds_exactly_the_four_tray_sizes_as_pngs(self):
        for theme in THEMES:
            for state in ("ready", *BADGES):
                with self.subTest(theme=theme, state=state):
                    entries = ico_entries(TRAY / f"tray-{theme}-{state}.ico")
                    self.assertEqual([width for width, *_ in entries], TRAY_SIZES)
                    for width, height, bits, png in entries:
                        self.assertEqual((height, bits), (width, 32))
                        self.assertEqual(png_size(png), (width, width))

    def test_badges_are_cut_out_of_the_mark_not_painted_around_it(self):
        # A ring painted in a taskbar colour would be opaque here; a cut-out leaves at most
        # the anti-aliased fringe of its edges.
        for theme in THEMES:
            for px in TRAY_SIZES:
                ready = tray_frame(theme, "ready", px)
                inked = [(x, y) for x, y in gap_pixels(px) if ready[(y * px + x) * 4 + 3] >= 128]
                self.assertGreaterEqual(len(inked), 2, f"the mark crosses the badge gap at {px} px")
                for state in BADGES:
                    with self.subTest(theme=theme, state=state, px=px):
                        badged = tray_frame(theme, state, px)
                        alphas = [badged[(y * px + x) * 4 + 3] for x, y in inked]
                        self.assertLessEqual(max(alphas), 32, alphas)

    def test_cut_out_pixels_well_inside_the_gap_are_fully_transparent(self):
        for theme in THEMES:
            for state in BADGES:
                with self.subTest(theme=theme, state=state):
                    ready, badged = tray_frame(theme, "ready", 32), tray_frame(theme, state, 32)
                    br, k, bc = badge_geometry(32)
                    clear = [(x, y) for y in range(32) for x in range(32)
                             if br + 0.75 <= math.hypot(x + 0.5 - bc, y + 0.5 - bc) <= k - 1.0
                             and ready[(y * 32 + x) * 4 + 3] == 255]
                    self.assertTrue(clear)
                    self.assertEqual({badged[(y * 32 + x) * 4 + 3] for x, y in clear}, {0})

    def test_light_taskbar_icons_have_dark_ink_and_dark_taskbar_icons_light_ink(self):
        # Every solid pixel of the ready icon is the theme's ink, so it carries no badge either.
        # Where two anti-aliased strokes overlap the rasteriser may round one step off.
        for px in TRAY_SIZES:
            for theme, ink in (("light", 0x1A), ("dark", 0xFF)):
                with self.subTest(theme=theme, px=px):
                    pixels = tray_frame(theme, "ready", px)
                    solid = [pixels[i:i + 3] for i in range(0, len(pixels), 4) if pixels[i + 3] == 255]
                    self.assertTrue(solid, "the mark has no solid pixel")
                    for rgb in solid:
                        self.assertLessEqual(max(abs(channel - ink) for channel in rgb), 2, rgb.hex())

    def test_each_state_shows_its_own_badge_colour(self):
        for theme in THEMES:
            for state, colours in BADGES.items():
                for px in TRAY_SIZES:
                    with self.subTest(theme=theme, state=state, px=px):
                        pixels = tray_frame(theme, state, px)
                        br, _, bc = badge_geometry(px)
                        inside = Counter(bytes(pixels[(y * px + x) * 4:(y * px + x) * 4 + 3]).hex().upper()
                                         for y in range(px) for x in range(px)
                                         if math.hypot(x + 0.5 - bc, y + 0.5 - bc) <= br - 0.75
                                         and pixels[(y * px + x) * 4 + 3] == 255)
                        self.assertEqual(inside.most_common(1)[0][0], colours[theme])


def reference_filter(kind, line, prev, bpp=4):
    """The PNG specification's row filters, written out byte by byte."""
    out = []
    for i, value in enumerate(line):
        a = line[i - bpp] if i >= bpp else 0
        b = prev[i]
        c = prev[i - bpp] if i >= bpp else 0
        if kind == 0:
            predictor = 0
        elif kind == 1:
            predictor = a
        elif kind == 2:
            predictor = b
        elif kind == 3:
            predictor = (a + b) // 2
        else:
            p = a + b - c
            pa, pb, pc = abs(p - a), abs(p - b), abs(p - c)
            predictor = a if pa <= pb and pa <= pc else b if pb <= pc else c
        out.append((value - predictor) % 256)
    return bytes([kind, *out])


def png(width, height, rows, colour=6):
    def chunk(kind, body):
        return struct.pack(">I", len(body)) + kind + body + struct.pack(">I", zlib.crc32(kind + body))
    header = struct.pack(">IIBBBBB", width, height, 8, colour, 0, 0, 0)
    return SIGNATURE + chunk(b"IHDR", header) + chunk(b"IDAT", zlib.compress(b"".join(rows))) + chunk(b"IEND", b"")


class PngCodecTests(unittest.TestCase):
    PIXELS = [bytes([200, 10, 255, 255, 30, 240, 7, 128, 90, 90, 90, 0]),
              bytes([10, 250, 3, 255, 255, 0, 128, 64, 1, 2, 3, 4]),
              bytes([128, 128, 128, 128, 0, 0, 0, 0, 255, 255, 255, 255])]

    def test_each_row_filter_decodes_to_the_same_pixels(self):
        for kind in range(5):
            with self.subTest(filter=kind):
                rows, prev = [], bytes(12)
                for line in self.PIXELS:
                    rows.append(reference_filter(kind, line, prev))
                    prev = line
                self.assertEqual(read_png(png(3, 3, rows)), (3, 3, bytearray(b"".join(self.PIXELS))))

    def test_rows_may_mix_filters(self):
        rows, prev = [], bytes(12)
        for kind, line in zip((4, 3, 1), self.PIXELS, strict=True):
            rows.append(reference_filter(kind, line, prev))
            prev = line
        self.assertEqual(read_png(png(3, 3, rows))[2], bytearray(b"".join(self.PIXELS)))

    def test_paeth_prefers_left_then_up_then_upper_left(self):
        # The second row's first red byte has only an upper neighbour (110), so a stored 246
        # decodes to 100. The next red byte sees left 100, up 120 and upper-left 110: p = 110 is
        # nearest the upper-left byte, so a stored 5 decodes to 115 (105 or 125 from the others).
        first = bytes([110, 0, 0, 255, 120, 0, 0, 255])
        rows = [b"\0" + first, bytes([4, 246, 0, 0, 0, 5, 0, 0, 0])]
        pixels = read_png(png(2, 2, rows))[2]
        self.assertEqual(pixels[8:], bytearray([100, 0, 0, 255, 115, 0, 0, 255]))

    def test_unknown_filters_and_other_formats_are_refused(self):
        with self.assertRaisesRegex(ValueError, "row filter 5"):
            read_png(png(3, 1, [bytes([5]) + self.PIXELS[0]]))
        with self.assertRaisesRegex(ValueError, "colour type 2"):
            read_png(png(1, 1, [b"\0\0\0\0"], colour=2))

    def test_written_pngs_read_back_unchanged(self):
        generator = random.Random(7)
        for width, height in ((1, 1), (5, 3), (17, 9)):
            with self.subTest(size=(width, height)):
                smooth = bytes((x * 9 + y * 5 + c * 40) % 256 for y in range(height) for x in range(width) for c in range(4))
                noisy = bytes(generator.randrange(256) for _ in range(width * height * 4))
                for pixels in (smooth, noisy):
                    self.assertEqual(read_png(write_png(width, height, pixels)), (width, height, bytearray(pixels)))


if __name__ == "__main__":
    unittest.main()

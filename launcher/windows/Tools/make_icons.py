"""Render RoleBand's Windows icons from icons.py into package assets and .ico files.

Usage (from anywhere):
    python launcher/windows/Tools/make_icons.py [--browser PATH]

Every frame is drawn at its own size and rendered by a headless Chromium browser (Microsoft
Edge by default) on one transparent sheet in one screenshot, then cut out of it. Standard
library only. The output depends only on the drawings and the browser's rasteriser: rerun
with the same browser and every file is byte for byte the same.
"""

import argparse
import shutil
import struct
import subprocess
import tempfile
import time
import zlib
from pathlib import Path

import icons

WINDOWS = Path(__file__).resolve().parents[1]
ASSETS = WINDOWS / "Assets"
TRAY = WINDOWS / "RoleBand.App/Tray"
APP_ICO = WINDOWS / "RoleBand.App/RoleBand.ico"

#: Square44x44Logo target sizes Windows asks for in the taskbar, Start, Alt+Tab and Settings.
TARGET_SIZES = (16, 20, 24, 30, 32, 36, 40, 48, 60, 64, 72, 80, 96, 256)
#: Each unplated variant shows the same drawing, because the icon carries its own plate.
TARGET_FORMS = ("", "_altform-unplated", "_altform-lightunplated")
SCALES = (100, 125, 150, 200, 400)
#: Asset name and its size at scale 100.
LOGOS = {"Square44x44Logo": 44, "Square150x150Logo": 150, "StoreLogo": 50}
#: The package logo App Installer shows, drawn full bleed (icons.app_icon).
STORE_LOGO = "StoreLogo"
TRAY_SIZES = (16, 20, 24, 32)
APP_ICO_SIZES = (16, 20, 24, 32, 40, 48, 64, 256)

#: Tray state file name -> badge name in icons.tray_svg.
STATES = {"ready": None, "scanning": "play", "paused": "pause", "attention": "attention", "stopped": "stopped"}
#: Taskbar theme -> ink, badge glyph and badge fills. "light" is a light taskbar, so dark ink.
THEMES = {
    "light": ("#1A1A1A", "#FFFFFF", {"play": "#08607D", "pause": "#5A5A5A", "attention": "#9D5D00", "stopped": "#C42B1C"}),
    "dark": ("#FFFFFF", "#1C1C1C", {"play": "#6FC9E6", "pause": "#D0D0D0", "attention": "#EFA85E", "stopped": "#FF99A4"}),
}

EDGE = Path(r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe")
OTHER_BROWSERS = ("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome", "google-chrome", "chromium", "chrome")
SHEET_WIDTH = 1280
#: Transparent space around every frame, so one frame's edge never reaches its neighbour.
GAP = 4


def scaled(size, scale):
    """Pixel size of an asset at a scale, rounding halves up as Windows' asset tables do."""
    return (size * scale + 50) // 100


def app_sizes():
    sizes = set(TARGET_SIZES) | set(APP_ICO_SIZES)
    sizes |= {scaled(size, scale) for name, size in LOGOS.items() if name != STORE_LOGO for scale in SCALES}
    return sorted(sizes)


def store_sizes():
    size = LOGOS[STORE_LOGO]
    return sorted({size} | {scaled(size, scale) for scale in SCALES})


def frames():
    """Every frame to render, as (key, px, svg); a key names what the frame becomes."""
    out = [(("app", px), px, icons.app_icon(px, f"a{px}")) for px in app_sizes()]
    out += [(("store", px), px, icons.app_icon(px, f"s{px}", bleed=True)) for px in store_sizes()]
    for theme, (ink, glyph, fills) in THEMES.items():
        for state, badge in STATES.items():
            for px in TRAY_SIZES:
                svg = icons.tray_svg(px, px, ink, badge, fills.get(badge or "", None), glyph, uid=f"t{theme}{state}{px}")
                out.append((("tray", theme, state, px), px, svg))
    return out


def layout(items, width=SHEET_WIDTH):
    """Shelf-pack square frames, largest first; returns ({key: (x, y)}, sheet height)."""
    positions = {}
    x = y = GAP
    shelf = 0
    for key, px, _ in sorted(items, key=lambda item: (-item[1], item[0])):
        if px + 2 * GAP > width:
            raise ValueError(f"A {px} px frame does not fit a {width} px sheet")
        if x + px + GAP > width:
            x, y, shelf = GAP, y + shelf + GAP, 0
        positions[key] = (x, y)
        x += px + GAP
        shelf = max(shelf, px)
    return positions, y + shelf + GAP


def sheet_html(items, positions):
    cells = "".join(f'<div style="position:absolute;left:{positions[key][0]}px;top:{positions[key][1]}px;'
                    f'width:{px}px;height:{px}px;line-height:0">{svg}</div>' for key, px, svg in items)
    return ("<!doctype html><html><head><meta charset=\"utf-8\"><style>"
            "html,body{margin:0;padding:0;background:transparent;overflow:hidden}"
            "svg{display:block}</style></head><body>" + cells + "</body></html>")


def find_browser(path=None):
    if path:
        return Path(path)
    if EDGE.is_file():
        return EDGE
    for name in OTHER_BROWSERS:
        found = shutil.which(name) or (name if Path(name).is_file() else None)
        if found:
            return Path(found)
    raise SystemExit("No Chromium browser found. Pass --browser with the path of Edge or Chrome.")


def screenshot(html, width, height, browser):
    """Render a page with a headless browser and a throwaway profile; returns the PNG bytes."""
    with tempfile.TemporaryDirectory(prefix="rb-icons-", ignore_cleanup_errors=True) as scratch:
        scratch = Path(scratch)
        page, shot = scratch / "sheet.html", scratch / "sheet.png"
        page.write_text(html, encoding="utf-8")
        command = [
            str(browser), "--headless", "--disable-gpu", "--hide-scrollbars", "--force-device-scale-factor=1",
            "--default-background-color=00000000", "--force-color-profile=srgb",
            f"--user-data-dir={scratch / 'profile'}", "--no-first-run", "--no-default-browser-check",
            "--disable-extensions", "--disable-sync", "--disable-background-networking",
            "--disable-component-update", "--disable-default-apps", "--disable-domain-reliability",
            "--no-pings", "--disable-breakpad", f"--window-size={width},{height}",
            f"--screenshot={shot}", page.as_uri(),
        ]
        result = subprocess.run(command, capture_output=True, text=True, timeout=180, check=False)
        # Edge's launcher can return before the browser it started has drawn anything. The
        # browser holds `lockfile` in its profile until it exits, after writing the screenshot.
        deadline = time.monotonic() + 180
        while not shot.is_file() or (scratch / "profile/lockfile").exists():
            if time.monotonic() > deadline:
                raise SystemExit(f"{browser} wrote no screenshot (exit {result.returncode}):\n{result.stderr[-2000:]}")
            time.sleep(0.2)
        return shot.read_bytes()


def paeth(a, b, c):
    p = a + b - c
    pa, pb, pc = abs(p - a), abs(p - b), abs(p - c)
    if pa <= pb and pa <= pc:
        return a
    return b if pb <= pc else c


def read_png(data):
    """Decode an 8-bit RGBA, non-interlaced PNG; returns (width, height, RGBA bytearray)."""
    if data[:8] != b"\x89PNG\r\n\x1a\n":
        raise ValueError("Not a PNG")
    pos, idat, header = 8, [], None
    while pos < len(data):
        length, kind = struct.unpack(">I4s", data[pos:pos + 8])
        body = data[pos + 8:pos + 8 + length]
        if zlib.crc32(kind + body) != struct.unpack(">I", data[pos + 8 + length:pos + 12 + length])[0]:
            raise ValueError(f"PNG chunk {kind!r} fails its CRC")
        if kind == b"IHDR":
            header = struct.unpack(">IIBBBBB", body)
        elif kind == b"IDAT":
            idat.append(body)
        elif kind == b"IEND":
            break
        pos += 12 + length
    if header is None:
        raise ValueError("PNG has no IHDR")
    width, height, depth, colour, _, _, interlace = header
    if (depth, colour, interlace) != (8, 6, 0):
        raise ValueError(f"Expected 8-bit RGBA without interlace, got depth {depth}, colour type {colour}, "
                         f"interlace {interlace}")
    raw = zlib.decompress(b"".join(idat))
    stride, bpp = width * 4, 4
    if len(raw) != height * (stride + 1):
        raise ValueError("PNG image data has the wrong length")
    out = bytearray(height * stride)
    prev = bytearray(stride)
    for y in range(height):
        start = y * (stride + 1)
        kind, line = raw[start], bytearray(raw[start + 1:start + 1 + stride])
        if kind == 1:
            for i in range(bpp, stride):
                line[i] = (line[i] + line[i - bpp]) & 255
        elif kind == 2:
            line = bytearray((v + u) & 255 for v, u in zip(line, prev, strict=True))
        elif kind == 3:
            for i in range(stride):
                left = line[i - bpp] if i >= bpp else 0
                line[i] = (line[i] + ((left + prev[i]) >> 1)) & 255
        elif kind == 4:
            for i in range(stride):
                left, upleft = (line[i - bpp], prev[i - bpp]) if i >= bpp else (0, 0)
                line[i] = (line[i] + paeth(left, prev[i], upleft)) & 255
        elif kind != 0:
            raise ValueError(f"Unknown PNG row filter {kind}")
        out[y * stride:(y + 1) * stride] = line
        prev = line
    return width, height, out


def chunk(kind, body):
    return struct.pack(">I", len(body)) + kind + body + struct.pack(">I", zlib.crc32(kind + body))


def write_png(width, height, rgba):
    """Encode RGBA pixels as a PNG with no ancillary chunks, so equal pixels give equal bytes.

    Each row takes whichever of the None, Sub and Up filters leaves the smallest residuals."""
    stride = width * 4
    rows, prev = [], bytes(stride)
    for y in range(height):
        line = bytes(rgba[y * stride:(y + 1) * stride])
        sub = line[:4] + bytes((line[i] - line[i - 4]) & 255 for i in range(4, stride))
        up = bytes((v - u) & 255 for v, u in zip(line, prev, strict=True))
        choices = ((0, line), (1, sub), (2, up))
        kind, best = min(choices, key=lambda choice: sum(v if v < 128 else 256 - v for v in choice[1]))
        rows.append(bytes([kind]) + best)
        prev = line
    header = struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0)
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", header)
            + chunk(b"IDAT", zlib.compress(b"".join(rows), 9)) + chunk(b"IEND", b""))


def crop(sheet, sheet_width, x, y, px):
    stride = sheet_width * 4
    out = bytearray()
    for row in range(y, y + px):
        out += sheet[row * stride + x * 4:row * stride + (x + px) * 4]
    return out


def write_ico(pngs):
    """An .ico of PNG entries, smallest first; `pngs` maps pixel size to PNG bytes."""
    sizes = sorted(pngs)
    directory = struct.pack("<HHH", 0, 1, len(sizes))
    offset = 6 + 16 * len(sizes)
    images = b""
    for px in sizes:
        data = pngs[px]
        # An entry stores 256 as 0, because its width and height are single bytes.
        directory += struct.pack("<BBBBHHII", px % 256, px % 256, 0, 0, 1, 32, len(data), offset + len(images))
        images += data
    return directory + images


def render(browser):
    """Render every frame; returns {key: PNG bytes}."""
    items = frames()
    positions, height = layout(items)
    shot = screenshot(sheet_html(items, positions), SHEET_WIDTH, height, browser)
    width, shot_height, pixels = read_png(shot)
    if (width, shot_height) != (SHEET_WIDTH, height):
        raise SystemExit(f"The browser rendered {width} x {shot_height} px, not the {SHEET_WIDTH} x {height} px sheet")
    # The sheet's corners lie in the gap around the frames; an opaque corner means the browser
    # painted a page background, and every icon would carry it.
    for x, y in ((0, 0), (width - 1, 0), (0, height - 1), (width - 1, height - 1)):
        if pixels[(y * width + x) * 4 + 3] != 0:
            raise SystemExit(f"The screenshot is not transparent at ({x}, {y}); "
                             "the browser ignored --default-background-color")
    out = {}
    for key, px, _ in items:
        x, y = positions[key]
        frame = crop(pixels, width, x, y, px)
        if not any(frame[3::4]):
            raise SystemExit(f"Frame {key} rendered empty")
        out[key] = write_png(px, px, frame)
    return out


def outputs(rendered):
    """Every file to write, as {path: bytes}."""
    files = {}
    for px in TARGET_SIZES:
        for form in TARGET_FORMS:
            files[ASSETS / f"Square44x44Logo.targetsize-{px}{form}.png"] = rendered[("app", px)]
    for name, size in LOGOS.items():
        kind = "store" if name == STORE_LOGO else "app"
        files[ASSETS / f"{name}.png"] = rendered[(kind, size)]
        for scale in SCALES:
            files[ASSETS / f"{name}.scale-{scale}.png"] = rendered[(kind, scaled(size, scale))]
    for theme in THEMES:
        for state in STATES:
            files[TRAY / f"tray-{theme}-{state}.ico"] = write_ico(
                {px: rendered[("tray", theme, state, px)] for px in TRAY_SIZES})
    files[APP_ICO] = write_ico({px: rendered[("app", px)] for px in APP_ICO_SIZES})
    return files


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--browser", help="Edge or Chrome executable (default: the installed Microsoft Edge)")
    args = parser.parse_args()
    files = outputs(render(find_browser(args.browser)))
    for path in sorted(files):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(files[path])
    print(f"Wrote {len(files)} files")


if __name__ == "__main__":
    main()

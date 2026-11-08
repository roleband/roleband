"""RoleBand's Windows icon drawings as SVG: the app icon and the notification-area icon.

The mark keeps the brand geometry of launcher/macos/Tools/Icon.swift: rings at radius
43.9, 28.6 and 13.2 of a 100 box, the sweep from the centre to the outer ring at 45
degrees, the role dot at (69.37, 30.63). Only the drawing changes with size.
make_icons.py renders these into the package assets and .ico files.
"""

import math

GOLD = "#DBCB90"
GOLD_HI = "#EADFB6"
GOLD_LO = "#C9B776"

#: Brand optical profiles: rings as (radius, width, alpha), sweep width, dot radius, share of plate.
PROFILES = {
    "master": ([(43.9, 3.0, 0.45), (28.6, 3.0, 0.45), (13.2, 3.0, 0.45)], 3.4, 5.0, 0.78),
    "mid": ([(43.9, 6.0, 1), (28.6, 6.0, 1), (13.2, 6.0, 1)], 7.0, 6.5, 0.84),
    "small": ([(43.9, 7.0, 1), (28.6, 7.0, 1)], 7.0, 7.0, 0.84),
}


def profile_for(px):
    """Windows shows app icons at 16-48 physical px in the title bar, taskbar and Start, where
    the master profile's 45% rings fade; the mid drawing carries up to 64 px."""
    return "small" if px <= 24 else "mid" if px <= 64 else "master"


def f(v):
    return f"{v:.2f}".rstrip("0").rstrip(".")


def mark(cx, cy, size, profile, color):
    rings, sweep, dot, _ = PROFILES[profile]
    s = size / 100
    out = []
    for r, w, a in rings:
        out.append(f'<circle cx="{f(cx)}" cy="{f(cy)}" r="{f(r * s)}" fill="none" stroke="{color}" '
                   f'stroke-width="{f(w * s)}" opacity="{f(a)}"></circle>')
    end = 43.9 * s * math.cos(math.pi / 4)
    out.append(f'<path d="M{f(cx)} {f(cy)}L{f(cx + end)} {f(cy - end)}" stroke="{color}" '
               f'stroke-width="{f(sweep * s)}" stroke-linecap="round" fill="none"></path>')
    out.append(f'<circle cx="{f(cx + 19.37 * s)}" cy="{f(cy - 19.37 * s)}" r="{f(dot * s)}" fill="{color}"></circle>')
    return "".join(out)


def app_icon(px, uid):
    """The app icon at `px` square on the 48 grid: a 40 x 40 plate with Windows' 2 px exterior
    corner, a one-step 120 degree gradient lit from the top left, a 1 px inner edge so the dark
    plate still separates from a dark Start menu, and the mark with a soft shadow from 32 px up.

    `uid` prefixes the gradient and filter ids, so it must be unique within one document."""
    prof = profile_for(px)
    m = 40 * PROFILES[prof][3]
    defs = (f'<defs><linearGradient id="{uid}p" x1="0" y1="0" x2="1" y2="1">'
            f'<stop offset="0" stop-color="#323A31"></stop><stop offset="1" stop-color="#171A17"></stop></linearGradient>')
    gold = GOLD
    if px >= 40:
        defs += (f'<linearGradient id="{uid}g" x1="0" y1="0" x2="1" y2="1">'
                 f'<stop offset="0" stop-color="{GOLD_HI}"></stop><stop offset="1" stop-color="{GOLD_LO}"></stop></linearGradient>')
        gold = f"url(#{uid}g)"
    shadow = ""
    if px >= 32:
        defs += (f'<filter id="{uid}s" x="-10%" y="-10%" width="120%" height="120%">'
                 f'<feDropShadow dx="0" dy="0.5" stdDeviation="0.5" flood-color="#000" flood-opacity="0.45"></feDropShadow></filter>')
        shadow = f' filter="url(#{uid}s)"'
    defs += "</defs>"
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 48 48" width="{px}" height="{px}">{defs}'
            f'<rect x="4" y="4" width="40" height="40" rx="2" fill="url(#{uid}p)"></rect>'
            f'<rect x="4.5" y="4.5" width="39" height="39" rx="1.6" fill="none" stroke="#FFFFFF" stroke-opacity="0.1"></rect>'
            f'<g{shadow}>{mark(24, 24, m, prof, gold)}</g></svg>')


#: Tray geometry per physical size: centre, outer ring radius, ring stroke, sweep stroke, dot
#: radius. The centre and outer ring sit on whole pixels so the 1 px class strokes stay sharp.
TRAY = {16: (8, 6.5, 1.0, 1.25, 1.25), 20: (10, 8.5, 1.25, 1.5, 1.5), 24: (12, 10, 1.5, 1.75, 1.75),
        32: (16, 13.5, 2.0, 2.25, 2.25)}


def badge_geometry(px):
    """Badge radius, cut-out radius and badge centre (both coordinates) for a `px` tray icon.

    The cut-out is wider than the badge by px/16, so a transparent gap separates the badge
    from the mark on any taskbar colour."""
    br = px * 0.22
    return br, br + px / 16, px - br


def tray_inner(px, ink, badge=None, bfill=None, gfill=None, uid="t"):
    c, R, w, sw, dr = TRAY[px]
    ri = R * 28.6 / 43.9
    dx = R * 19.37 / 43.9
    end = R * math.cos(math.pi / 4)
    body = (f'<circle cx="{c}" cy="{c}" r="{f(R)}" fill="none" stroke="{ink}" stroke-width="{f(w)}"></circle>'
            f'<circle cx="{c}" cy="{c}" r="{f(ri)}" fill="none" stroke="{ink}" stroke-width="{f(w)}"></circle>'
            f'<path d="M{c} {c}L{f(c + end)} {f(c - end)}" stroke="{ink}" stroke-width="{f(sw)}" stroke-linecap="round"></path>'
            f'<circle cx="{f(c + dx)}" cy="{f(c - dx)}" r="{f(dr)}" fill="{ink}"></circle>')
    if not badge:
        return body
    br, k, bc = badge_geometry(px)
    # The badge's surround is cut out of the mark with a mask rather than painted in a
    # background colour, because the taskbar's colour is not known when the icon is drawn.
    mask = (f'<mask id="{uid}" maskUnits="userSpaceOnUse" x="0" y="0" width="{px}" height="{px}">'
            f'<rect width="{px}" height="{px}" fill="#FFFFFF"></rect><circle cx="{f(bc)}" cy="{f(bc)}" r="{f(k)}" fill="#000000"></circle></mask>')
    g = gfill
    if badge == "play":
        glyph = f'<path d="M{f(bc - .32 * br)} {f(bc - .52 * br)}V{f(bc + .52 * br)}L{f(bc + .55 * br)} {f(bc)}Z" fill="{g}"></path>'
    elif badge == "pause":
        glyph = (f'<path d="M{f(bc - .3 * br)} {f(bc - .48 * br)}V{f(bc + .48 * br)}M{f(bc + .3 * br)} {f(bc - .48 * br)}V{f(bc + .48 * br)}" '
                 f'stroke="{g}" stroke-width="{f(.28 * br)}" stroke-linecap="round"></path>')
    elif badge == "attention":
        glyph = (f'<path d="M{f(bc)} {f(bc - .55 * br)}V{f(bc + .08 * br)}" stroke="{g}" stroke-width="{f(.3 * br)}" stroke-linecap="round"></path>'
                 f'<circle cx="{f(bc)}" cy="{f(bc + .5 * br)}" r="{f(.17 * br)}" fill="{g}"></circle>')
    else:
        glyph = f'<path d="M{f(bc - .5 * br)} {f(bc)}H{f(bc + .5 * br)}" stroke="{g}" stroke-width="{f(.3 * br)}" stroke-linecap="round"></path>'
    return (f'<defs>{mask}</defs><g mask="url(#{uid})">{body}</g>'
            f'<circle cx="{f(bc)}" cy="{f(bc)}" r="{f(br)}" fill="{bfill}"></circle>{glyph}')


def tray_svg(px, display, ink, badge=None, bfill=None, gfill=None, uid="t"):
    """The tray icon drawn on a `px` grid and shown at `display` px.

    `badge` is None (ready), "play", "pause", "attention", or anything else for the stopped
    dash. `uid` names the cut-out mask, so it must be unique within one document."""
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {px} {px}" width="{display}" height="{display}">'
            f'{tray_inner(px, ink, badge, bfill, gfill, uid)}</svg>')

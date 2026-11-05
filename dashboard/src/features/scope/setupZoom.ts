import { useLayoutEffect } from "react";
import "./setupZoom.css";

/* First-run setup, magnified on a large window (docs/ui.md, "First-run setup
   magnification"). The whole page is drawn larger by one factor, CSS `zoom` on
   the root element, so every block keeps its size and its place against every
   other: the screens are the 1440 x 900 design, larger, never a re-layout.

   The factor lives in `--setup-zoom` on the root element and takes effect only
   under `.app.in-setup` (setupZoom.css), so it is left in place when a setup
   screen unmounts: the welcome hands over to the walk, and a route that loads
   in between, without a frame at the plain size. Outside setup it does
   nothing. */

/** The layout never sees a window narrower than this: the width the setup
    screens are designed and tested at. */
export const DESIGN_WIDTH = 1440;
/** The height the fixed steps need, with Back and Continue in the window and
    room below them. */
export const DESIGN_HEIGHT = 760;
export const MAX_FACTOR = 1.3;
/** The share of the window's spare room setup grows into. Taking all of it
    makes the long steps (Discipline, World, Companies) lose rows above the
    fold that the size gives nothing back for; the short ones still grow. */
const GROWTH = 0.6;

/** The factor for a window in CSS pixels: `GROWTH` of the room the window has
    beyond the design, up to the cap, never below 1, so never more than the
    window has room for. Not rounded: the person's own browser zoom shrinks the
    window in CSS pixels, and any rounding would let turning it up make setup
    smaller. */
export function setupFactor(width: number, height: number): number {
  const room = Math.min(width / DESIGN_WIDTH, height / DESIGN_HEIGHT);
  return Math.max(1, Math.min(1 + GROWTH * (room - 1), MAX_FACTOR));
}

/** How far magnified text may stray from proportional before setup stays at
    its plain size. An engine that rounds each letter to whole pixels (Chrome
    on Linux, with font hinting) strays by several percent, enough to rewrap a
    line and move one card's title out of line with its neighbours; the
    engines that draw text in proportion stray by a tenth of that. */
const STRAY = 0.005;

/** Every letter and digit, twice: no words, so nothing here is copy. */
const SAMPLE = (() => {
  const run = (from: number, count: number) => Array.from({ length: count }, (_, i) => String.fromCharCode(from + i)).join("");
  const line = `${run(97, 26)} ${run(65, 26)} ${run(48, 10)}`;
  return `${line} ${line}`;
})();

/** The typeface the check measures. Plex Sans is loaded before any setup
    words are drawn; Plex Mono is loaded only once something uses it. */
function sans(): string {
  return getComputedStyle(document.documentElement).getPropertyValue("--app-font-sans").trim();
}

/** The widths of the sample at 12 and 13 px, drawn at `zoom` times the page's
    own zoom, in screen pixels. Each call measures new elements: an element that
    already has a zoom transitions to a new one (the reduced-motion rule gives
    every property a short transition), and would be read at the old value. */
function sampleWidths(family: string, zoom: number): number[] {
  const host = document.createElement("div");
  host.setAttribute("aria-hidden", "true");
  host.style.cssText = `position:absolute;left:0;top:0;visibility:hidden;pointer-events:none;white-space:nowrap;zoom:${zoom}`;
  for (const size of [12, 13]) {
    const line = document.createElement("div");
    line.style.cssText = `width:max-content;font-family:${family};font-size:${size}px;font-weight:400`;
    line.textContent = SAMPLE;
    host.appendChild(line);
  }
  document.body.appendChild(host);
  const widths = [...host.children].map((line) => line.getBoundingClientRect().width);
  host.remove();
  return widths;
}

const verdicts = new Map<string, boolean>();

/** Whether this browser draws text in proportion at `factor`: measured once
    per factor and screen density, and at the cap, so a factor where
    whole-pixel rounding happens to cancel out cannot pass an engine that
    rounds. The browser's own zoom changes the density, and with it the
    rounding. */
function textScales(factor: number): boolean {
  const key = `${Math.round(factor * 1000)}@${devicePixelRatio}`;
  const known = verdicts.get(key);
  if (known !== undefined) return known;
  const family = sans();
  const page = pageZoom();
  const plain = sampleWidths(family, 1 / page);
  const verdict = [factor, MAX_FACTOR].every((at) => {
    const larger = sampleWidths(family, at / page);
    return plain.every((width, i) => width > 0 && Math.abs(larger[i] / (width * at) - 1) <= STRAY);
  });
  verdicts.set(key, verdict);
  return verdict;
}

/** The zoom the page is drawn at now, measured rather than read. */
function pageZoom(): number {
  const box = document.createElement("div");
  box.style.cssText = "position:absolute;left:0;top:0;width:100px;height:1px;visibility:hidden;pointer-events:none";
  document.body.appendChild(box);
  const zoom = box.getBoundingClientRect().width / 100 || 1;
  box.remove();
  return zoom;
}

/** Fired on the window when setup's zoom changes. A late font can change it
    with no resize, and a canvas that sizes its backing store by the zoom
    listens for it. */
export const SETUP_ZOOM_CHANGE = "setupzoomchange";

/** Magnifies first-run setup while `active`, following the window's size. */
export function useSetupZoom(active: boolean): void {
  useLayoutEffect(() => {
    if (!active || typeof CSS === "undefined" || !CSS.supports("zoom", "1")) return;
    const root = document.documentElement;
    const family = sans();
    const query = `13px ${family}`;
    let fonts = !family || document.fonts.check(query, SAMPLE);
    const apply = () => {
      const wanted = setupFactor(window.innerWidth, window.innerHeight);
      const factor = String(wanted > 1 && fonts && textScales(wanted) ? wanted : 1);
      if (root.style.getPropertyValue("--setup-zoom") === factor) return;
      root.style.setProperty("--setup-zoom", factor);
      window.dispatchEvent(new Event(SETUP_ZOOM_CHANGE));
    };
    apply();
    let live = true;
    if (!fonts) {
      void document.fonts.load(query, SAMPLE).then(() => {
        if (!live) return;
        fonts = true;
        apply();
      }, () => undefined);
    }
    window.addEventListener("resize", apply);
    return () => {
      live = false;
      window.removeEventListener("resize", apply);
    };
  }, [active]);
}

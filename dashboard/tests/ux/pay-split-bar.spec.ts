/* The pay card's split bar, as it is painted: base, bonus and equity side by
   side, solid where the employer stated the figure and hatched where it is
   estimated.

   The hatch is measured on the pixels the browser draws, in both themes,
   because its strength is the product of the stripe recipe and each theme's
   hues: one recipe can be quiet on the pale dark-theme hues and glaring on the
   mid-dark light-theme ones. Dense high-contrast stripes across the card's
   width are hard to look at, so each estimated part's stripe contrast has a
   ceiling; a stated part must still read as solid next to it, so the hatch
   also has a floor. */

import type { Locator, Page } from "@playwright/test";
import type { CompComponent, JobCompPackage } from "../../src/api";
import { msg } from "../../src/test/msg";
import { expect, mockGet, test } from "./fixtures";
import { compPackageFixture, jobFixture } from "../../src/test/fixtures";
import { installBoardRoutes } from "./boardHarness";

/** Michelson contrast, (Lmax - Lmin) / (Lmax + Lmin), on relative luminance. */
const HATCH_CEILING = 0.22;
const HATCH_FLOOR = 0.06;
const SOLID_CEILING = 0.02;

const part = (kind: CompComponent["kind"], low: number, high: number, provenance: CompComponent["provenance"]): CompComponent =>
  ({ kind, low, high, provenance });

/** No posted range: every part is our estimate. */
const nothingPosted: JobCompPackage = compPackageFixture({
  state: "none_stated",
  currency: "USD",
  components: [
    part("base", 165_000, 247_000, "estimated"),
    part("bonus", 46_000, 69_000, "estimated"),
    part("equity", 172_000, 259_000, "estimated"),
  ],
  total: { low: 383_000, high: 575_000, provenance: "estimated" },
  estimate: { low: 383_000, median: 479_000, high: 575_000, provenance: "Google L6 reported median" },
});

/** A posted base band: the base is stated, bonus and equity are estimated. */
const basePosted: JobCompPackage = compPackageFixture({
  state: "band",
  basis: "base",
  currency: "USD",
  pay_period: "year",
  stated: { low: 165_000, high: 247_000 },
  components: [
    part("base", 165_000, 247_000, "stated"),
    part("bonus", 46_000, 69_000, "estimated"),
    part("equity", 172_000, 259_000, "estimated"),
  ],
  total: { low: 383_000, high: 575_000, provenance: "estimated" },
  estimate: { low: 383_000, median: 479_000, high: 575_000, provenance: "Google L6 reported median" },
  split_source: "measured",
});

async function openPayCard(page: Page, theme: "light" | "dark", pkg: JobCompPackage): Promise<Locator> {
  await page.addInitScript((value) => localStorage.setItem("theme", value), theme);
  await installBoardRoutes(page);
  await mockGet(page, "/api/jobs/101", (route) => route.fulfill({ json: { ...jobFixture, comp_package: pkg } }));
  await page.goto("/job/101");
  await expect(page.locator("html")).toHaveAttribute("data-theme", theme);
  // The panel's own bar: its small copy in the side column draws the bar again.
  const bar = page.locator(".pkg-panel .pkg-bar");
  await expect(bar.locator(".pkg-seg")).toHaveCount(3);
  await bar.scrollIntoViewIfNeeded();
  return bar;
}

type Rgb = [number, number, number];

/** Decodes a screenshot in the page and returns each pixel's sRGB channels. */
async function pixels(page: Page, png: Buffer): Promise<Rgb[]> {
  return page.evaluate(async (bytes) => {
    const bitmap = await createImageBitmap(new Blob([new Uint8Array(bytes)], { type: "image/png" }));
    const canvas = new OffscreenCanvas(bitmap.width, bitmap.height);
    const context = canvas.getContext("2d")!;
    context.drawImage(bitmap, 0, 0);
    const { data } = context.getImageData(0, 0, bitmap.width, bitmap.height);
    const out: [number, number, number][] = [];
    for (let i = 0; i < data.length; i += 4) out.push([data[i], data[i + 1], data[i + 2]]);
    return out;
  }, [...png]);
}

/** WCAG relative luminance. */
function luminance([r, g, b]: Rgb): number {
  const channel = (c: number) => {
    const v = c / 255;
    return v <= 0.04045 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4;
  };
  return 0.2126 * channel(r) + 0.7152 * channel(g) + 0.0722 * channel(b);
}

/** WCAG contrast ratio between two luminances. */
const ratio = (a: number, b: number) => (Math.max(a, b) + 0.05) / (Math.min(a, b) + 0.05);

/** The one pixel at a point of the page. */
async function pixelAt(page: Page, x: number, y: number): Promise<Rgb> {
  const [rgb] = await pixels(page, await page.screenshot({ clip: { x, y, width: 1, height: 1 } }));
  return rgb;
}

/** The card's own ground: a point in its top padding, clear of its border and corners. */
async function cardGround(page: Page): Promise<Rgb> {
  const box = (await page.locator(".pkg-panel").boundingBox())!;
  return pixelAt(page, Math.round(box.x + box.width / 2), Math.round(box.y + 8));
}

/** The pixels inside one part, read away from its ends so the bar's rounded
 *  corners and the gaps beside it are not counted. */
async function inside(page: Page, segment: Locator): Promise<Rgb[]> {
  const box = (await segment.boundingBox())!;
  return pixels(page, await page.screenshot({
    clip: { x: box.x + 8, y: box.y + 4, width: box.width - 16, height: box.height - 8 },
  }));
}

/** The stripe contrast inside one part. */
async function stripeContrast(page: Page, segment: Locator): Promise<number> {
  const sorted = (await inside(page, segment)).map(luminance).sort((a, b) => a - b);
  const low = sorted[Math.floor(sorted.length * 0.02)];
  const high = sorted[Math.floor(sorted.length * 0.98)];
  return (high - low) / (high + low);
}

for (const theme of ["light", "dark"] as const) {
  test(`every estimated part carries a quiet hatch (${theme})`, async ({ page }) => {
    const bar = await openPayCard(page, theme, nothingPosted);
    for (const kind of ["base", "bonus", "equity"] as const) {
      const contrast = await stripeContrast(page, bar.locator(`.pkg-${kind}`));
      expect(contrast, `${kind} hatch is too loud`).toBeLessThanOrEqual(HATCH_CEILING);
      expect(contrast, `${kind} hatch cannot be seen`).toBeGreaterThanOrEqual(HATCH_FLOOR);
    }
  });

  test(`a stated part stays solid beside estimated ones (${theme})`, async ({ page }) => {
    const bar = await openPayCard(page, theme, basePosted);
    const base = bar.locator(".pkg-base");
    expect(await stripeContrast(page, base)).toBeLessThanOrEqual(SOLID_CEILING);
    // A solid part is still a shape on the card: the 3:1 WCAG asks of a graphical object.
    const fill = luminance((await inside(page, base))[0]);
    expect(ratio(fill, luminance(await cardGround(page))), "the stated part fades into the card")
      .toBeGreaterThanOrEqual(3);
    for (const kind of ["bonus", "equity"] as const) {
      expect(await stripeContrast(page, bar.locator(`.pkg-${kind}`))).toBeGreaterThanOrEqual(HATCH_FLOOR);
    }
  });

  /* Base and bonus share a lightness, so an edge drawn by hue alone flickers
     and, to a deuteranope, is not there. The parts are parted by the card. */
  test(`neighbouring parts are parted by the card's own ground (${theme})`, async ({ page }) => {
    const bar = await openPayCard(page, theme, nothingPosted);
    const ground = await cardGround(page);
    const boxes = await bar.locator(".pkg-seg").evaluateAll((els) =>
      els.map((el) => el.getBoundingClientRect()).map((r) => ({ left: r.left, right: r.right, top: r.top, height: r.height })));
    for (let i = 1; i < boxes.length; i++) {
      const gap = boxes[i].left - boxes[i - 1].right;
      expect(gap, `no gap after part ${i}`).toBeGreaterThanOrEqual(2 - 0.01);
      // The first whole pixel column after the earlier part lies inside the gap.
      const x = Math.floor(boxes[i - 1].right) + 1;
      const painted = await pixelAt(page, x, Math.round(boxes[i].top + boxes[i].height / 2));
      // Every channel, so a gap painted in another hue of the same lightness fails too.
      const drift = Math.max(...painted.map((c, k) => Math.abs(c - ground[k])));
      expect(drift, `the gap after part ${i} is rgb(${painted}), the card rgb(${ground})`).toBeLessThanOrEqual(3);
    }
  });
}

/* Where the split came from is said in a short label, and why in a sentence.
   A hover-only title reaches neither a keyboard nor a finger, so the sentence
   sits behind a help mark: a real button the label's tooltip describes. */
/** The same split, with the line saying who supplied it beside the label. */
const suppliedSplit: JobCompPackage = { ...basePosted, split_provider: "builtin", split_as_of: "2026-10-01" };

for (const [width, pkg, header] of [
  [1280, basePosted, "label alone"],
  [360, basePosted, "label alone"],
  [1280, suppliedSplit, "label and source line"],
  [360, suppliedSplit, "label and source line"],
] as const) {
  test(`the split label explains itself to a keyboard and a tap (${width}px, ${header})`, async ({ page }) => {
    await page.setViewportSize({ width, height: 900 });
    await openPayCard(page, "light", pkg);
    const head = page.locator(".pkg-head");
    if (pkg.split_provider) await expect(head.getByTestId("comp-split-from")).toBeVisible();
    const why = msg("role-job-comp-panel-this-company-s-real-base");
    // The label alone no longer carries the sentence: a title would stack a
    // second, mouse-only tooltip on the help mark's.
    await expect(head.locator(".split-src")).not.toHaveAttribute("title");

    const help = head.getByRole("button", { name: msg("role-job-comp-panel-about-the-split") });
    await expect(help).toHaveAccessibleDescription(why);
    const tip = head.getByRole("tooltip");
    await expect(tip).toBeHidden();

    await help.focus();
    await expect(help).toBeFocused();
    expect(await help.evaluate((el) => (el as HTMLElement).tabIndex), "the help mark is in the tab order").toBe(0);
    await expect(tip).toBeVisible();
    await expect(tip).toHaveText(why);
    // The label sits at the card's right edge: the sentence opens inward and
    // stays on screen without widening the page.
    const box = (await tip.boundingBox())!;
    const label = (await head.locator(".pkg-split").boundingBox())!;
    expect(box.y, "the sentence covers the label it explains").toBeGreaterThanOrEqual(label.y + label.height);
    expect(box.x, "the sentence starts off screen").toBeGreaterThanOrEqual(0);
    expect(box.x + box.width, "the sentence runs off screen").toBeLessThanOrEqual(width);
    expect(await page.evaluate(() => document.documentElement.scrollWidth), "the page scrolls sideways").toBeLessThanOrEqual(width);

    await help.blur();
    await expect(tip).toBeHidden();
    await help.click();
    await expect(tip).toBeVisible();
  });
}

/* Under forced colours (Windows contrast themes) the browser repaints every
   background with the person's own Canvas, so fills alone leave a blank
   band. The bar and its swatches draw in system colours there: a stated part
   in solid ink, an estimated one as an outline with ink lines. */
const INK = 3;

/** The share of a region's pixels that stand 3:1 off the card's ground. */
function inked(region: Rgb[], ground: Rgb): number {
  const g = luminance(ground);
  return region.filter((px) => ratio(luminance(px), g) >= INK).length / region.length;
}

for (const theme of ["light", "dark"] as const) {
  test(`forced colours keep the bar and its swatches, stated apart from estimated (${theme})`, async ({ page }) => {
    await page.emulateMedia({ forcedColors: "active" });
    const bar = await openPayCard(page, theme, basePosted);
    const ground = await cardGround(page);

    const stated = inked(await inside(page, bar.locator(".pkg-base")), ground);
    expect(stated, "the stated base is not drawn solid").toBeGreaterThanOrEqual(0.95);
    for (const kind of ["bonus", "equity"] as const) {
      const segment = bar.locator(`.pkg-${kind}`);
      const share = inked(await inside(page, segment), ground);
      expect(share, `the estimated ${kind} cannot be seen`).toBeGreaterThanOrEqual(0.12);
      expect(share, `the estimated ${kind} reads as solid as the stated base`).toBeLessThanOrEqual(0.6);
      // The outline: the part's own edge is ink, so its extent shows where the lines stop.
      // Read two CSS pixel rows at the top, one image pixel per CSS pixel: a
      // part may start on a fractional pixel, and the 1px outline then lands
      // in either row or across both. Every column must carry ink in one of them.
      const box = (await segment.boundingBox())!;
      const width = Math.floor(box.width - 8);
      const strip = await pixels(page, await page.screenshot({
        clip: { x: Math.ceil(box.x + 4), y: box.y, width, height: 2 },
        scale: "css",
      }));
      expect(strip, "the edge strip is not one pixel per CSS pixel").toHaveLength(width * 2);
      const columns = Array.from({ length: width }, (_, x) => inked([strip[x]], ground) + inked([strip[width + x]], ground) > 0);
      const edged = columns.filter(Boolean).length / width;
      expect(edged, `the estimated ${kind} has no edge`).toBeGreaterThanOrEqual(0.9);
    }

    for (const kind of ["base", "bonus", "equity"] as const) {
      const swatch = page.locator(`.pkg-legend .pkg-sw.pkg-${kind}`);
      const share = inked(await pixels(page, await swatch.screenshot()), ground);
      expect(share, `the ${kind} swatch is blank`).toBeGreaterThanOrEqual(0.3);
    }
  });
}

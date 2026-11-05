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
  const bar = page.locator(".pkg-bar");
  await expect(bar.locator(".pkg-seg")).toHaveCount(3);
  await bar.scrollIntoViewIfNeeded();
  return bar;
}

/** Decodes a screenshot in the page and returns each pixel's relative luminance. */
async function luminances(page: Page, png: Buffer): Promise<number[]> {
  return page.evaluate(async (bytes) => {
    const bitmap = await createImageBitmap(new Blob([new Uint8Array(bytes)], { type: "image/png" }));
    const canvas = new OffscreenCanvas(bitmap.width, bitmap.height);
    const context = canvas.getContext("2d")!;
    context.drawImage(bitmap, 0, 0);
    const { data } = context.getImageData(0, 0, bitmap.width, bitmap.height);
    const channel = (c: number) => {
      const v = c / 255;
      return v <= 0.04045 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4;
    };
    const out: number[] = [];
    for (let i = 0; i < data.length; i += 4) {
      out.push(0.2126 * channel(data[i]) + 0.7152 * channel(data[i + 1]) + 0.0722 * channel(data[i + 2]));
    }
    return out;
  }, [...png]);
}

/** The stripe contrast inside one part, read away from its ends so the bar's
 *  rounded corners and the gaps beside it are not counted. */
async function stripeContrast(page: Page, segment: Locator): Promise<number> {
  const box = (await segment.boundingBox())!;
  const png = await page.screenshot({
    clip: { x: box.x + 8, y: box.y + 4, width: box.width - 16, height: box.height - 8 },
  });
  const sorted = (await luminances(page, png)).sort((a, b) => a - b);
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
    expect(await stripeContrast(page, bar.locator(".pkg-base"))).toBeLessThanOrEqual(SOLID_CEILING);
    for (const kind of ["bonus", "equity"] as const) {
      expect(await stripeContrast(page, bar.locator(`.pkg-${kind}`))).toBeGreaterThanOrEqual(HATCH_FLOOR);
    }
  });

  /* Base and bonus share a lightness, so an edge drawn by hue alone flickers
     and, to a deuteranope, is not there. The parts are parted by the card. */
  test(`neighbouring parts are parted by the card's own ground (${theme})`, async ({ page }) => {
    const bar = await openPayCard(page, theme, nothingPosted);
    const panel = page.locator(".pkg-panel");
    const card = await panel.evaluate((el) => getComputedStyle(el).backgroundColor);
    // A point in the card's top padding, clear of its border and corners.
    const inside = (await panel.boundingBox())!;
    const [ground] = await luminances(page, await page.screenshot({
      clip: { x: Math.round(inside.x + inside.width / 2), y: Math.round(inside.y + 8), width: 1, height: 1 },
    }));
    const boxes = await bar.locator(".pkg-seg").evaluateAll((els) =>
      els.map((el) => el.getBoundingClientRect()).map((r) => ({ left: r.left, right: r.right, top: r.top, height: r.height })));
    for (let i = 1; i < boxes.length; i++) {
      const gap = boxes[i].left - boxes[i - 1].right;
      expect(gap, `no gap after part ${i}`).toBeGreaterThanOrEqual(2 - 0.01);
      // The first whole pixel column after the earlier part lies inside the gap.
      const x = Math.floor(boxes[i - 1].right) + 1;
      const [painted] = await luminances(page, await page.screenshot({
        clip: { x, y: Math.round(boxes[i].top + boxes[i].height / 2), width: 1, height: 1 },
      }));
      const ratio = (Math.max(painted, ground) + 0.05) / (Math.min(painted, ground) + 0.05);
      expect(ratio, `the gap after part ${i} is not the card (${card})`).toBeLessThan(1.03);
    }
  });
}

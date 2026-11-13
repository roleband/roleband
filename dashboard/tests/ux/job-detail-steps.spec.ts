import AxeBuilder from "@axe-core/playwright";
import { expect, mockGet, test, type Page } from "./fixtures";
import { applicationCardFixture, applicationDetailFixture, compPackageFixture, jobFixture } from "../../src/test/fixtures";
import { detail, installBoardRoutes } from "./boardHarness";

/* A posting on a wider window steps up (docs/ui.md, "Cover"): at set widths of
   its scroll box the frame, its gaps and the posting's type grow together, and
   the bar, menus and pop-ups keep their size. A step depends on the width
   alone, never on the window's height. Widths here stay clear of the steps'
   edges by more than a classic scrollbar, which narrows the box. */

const SENTENCE = "You will set the direction for a platform that many teams build on, weigh what to ship against what to leave out, and explain both to the people who depend on it.";
const paragraphs = (count: number) => Array.from({ length: count }, (_, i) => `${SENTENCE} ${SENTENCE} (${i + 1})`).join("\n\n");

const PURSUIT = {
  id: 10, job_id: 404, stage: "applied", priority: 3, notes: null, next_action: "Email the recruiter",
  next_action_due: null, created_at: "2026-10-20T09:00:00Z", updated_at: "2026-10-29T09:00:00Z",
};

const READING = {
  ...jobFixture,
  id: 404,
  company: "apple",
  title: "Head of Product, Global AI Learning Platform",
  url: "https://example.test/jobs/404",
  is_favorite: true,
  pursuit: PURSUIT,
  comp_package: compPackageFixture({
    state: "band", basis: "base", currency: "USD", pay_period: "year",
    stated: { low: 240000, high: 334000 }, bonus_pct: 0.25,
    components: [
      { kind: "base", low: 240000, high: 334000, provenance: "stated" },
      { kind: "bonus", low: 60000, high: 83500, provenance: "stated" },
      { kind: "equity", low: 292289, high: 406769, provenance: "estimated" },
    ],
    total: { low: 592289, high: 824269, provenance: "estimated" },
    split_source: "measured",
  }),
  description_sections: [
    { key: "summary", title: "Summary", content: paragraphs(3) },
    { key: "responsibilities", title: "Responsibilities", content: paragraphs(4) },
  ],
};

const SIMILAR = { scope: "cross", items: [202, 203, 204].map((id, i) => ({
  ...jobFixture, id, company: "openai", title: `Principal Product Manager, Platform ${i + 1}`, score: 0.9 - i * 0.05,
})) };

async function installPosting(page: Page) {
  await installBoardRoutes(page);
  await mockGet(page, "/api/jobs/404", (route) => route.fulfill({ json: READING }));
  await mockGet(page, "/api/jobs/404/similar**", (route) => route.fulfill({ json: SIMILAR }));
  await mockGet(page, "/api/applications/404", (route) => route.fulfill({ json: applicationDetailFixture({
    application: applicationCardFixture({ job_id: 404, pursuit_id: 10, stage: "applied", company: "apple", title: READING.title, stage_since: "2026-11-01T09:00:00Z" }),
  }) }));
}

async function openPosting(page: Page, size: { width: number; height: number }) {
  await page.setViewportSize(size);
  await page.emulateMedia({ reducedMotion: "reduce" });
  await page.goto("/company/apple/job/404");
  await expect(detail(page).getByRole("heading", { name: "Responsibilities" })).toBeVisible();
  await page.evaluate(() => document.fonts.ready);
  await page.evaluate(() => { for (const animation of document.getAnimations()) animation.finish(); });
}

/** What a step decides, read from the page. */
function readStep(page: Page) {
  return page.evaluate(() => {
    const box = (selector: string) => {
      const b = document.querySelector(selector)!.getBoundingClientRect();
      return { x: Math.round(b.left), width: Math.round(b.width) };
    };
    const text = document.querySelector<HTMLElement>(".jd-section p, .jd-section li")!;
    const read = parseFloat(getComputedStyle(text).fontSize);
    const scroll = document.querySelector<HTMLElement>(".cover-scroll")!;
    return {
      room: scroll.clientWidth,
      frame: box(".jd-hero"),
      main: box(".jd-main"),
      text: box(".jd-sections"),
      read,
      title: parseFloat(getComputedStyle(document.querySelector(".jd-hero h1")!).fontSize),
      figure: parseFloat(getComputedStyle(document.querySelector(".jd-main .comp-panel .big")!).fontSize),
      meta: parseFloat(getComputedStyle(document.querySelector(".jd-aside .kv")!).fontSize),
      sideways: [scroll.scrollWidth - scroll.clientWidth, document.documentElement.scrollWidth - document.documentElement.clientWidth],
      zooms: [...new Set([...document.querySelectorAll(".cover, .cover *")].map((el) => getComputedStyle(el).zoom))],
    };
  });
}

/** The bar's controls as drawn: size, distance from the window's nearer edge, type. */
function readBar(page: Page) {
  return page.evaluate(() => {
    const bar = document.querySelector<HTMLElement>(".cover-bar")!;
    const width = window.innerWidth;
    return {
      height: Math.round(bar.getBoundingClientRect().height),
      controls: Array.from(bar.querySelectorAll<HTMLElement>(".ui-btn, a"), (el) => {
        const b = el.getBoundingClientRect();
        return {
          name: el.getAttribute("aria-label") ?? el.textContent?.trim() ?? "",
          width: Math.round(b.width),
          height: Math.round(b.height),
          fromEdge: Math.round(b.left < width / 2 ? b.left : width - b.right),
          font: getComputedStyle(el).fontSize,
        };
      }),
    };
  });
}

/* Each window: the frame's content width (the hero spans it), the reading
   size, and the posting's title size. */
const STEPS = [
  { width: 1440, height: 900, frame: 1120, read: 17, title: 24 },
  { width: 1480, height: 900, frame: 1120, read: 17, title: 24 },
  { width: 1540, height: 900, frame: 1248, read: 18, title: 26 },
  { width: 1728, height: 837, frame: 1248, read: 18, title: 26 },
  { width: 1728, height: 1117, frame: 1248, read: 18, title: 26 },
  { width: 1860, height: 1000, frame: 1248, read: 18, title: 26 },
  { width: 1940, height: 1000, frame: 1392, read: 20, title: 28 },
  { width: 2160, height: 1350, frame: 1392, read: 20, title: 28 },
  { width: 2360, height: 1300, frame: 1392, read: 20, title: 28 },
  { width: 2440, height: 1300, frame: 1536, read: 22, title: 30 },
  { width: 2560, height: 1440, frame: 1536, read: 22, title: 30 },
] as const;

test.describe("posting steps", () => {
  test.skip(({ isMobile }) => isMobile, "a phone window is one column; the desktop windows carry these");

  test.beforeEach(async ({ page }) => {
    await installPosting(page);
  });

  test("each width sets the frame, the columns and the type together, with no zoom", async ({ page }) => {
    test.setTimeout(120_000);
    let before: Awaited<ReturnType<typeof readStep>> | null = null;
    for (const step of STEPS) {
      await openPosting(page, step);
      const seen = await readStep(page);
      const at = `${step.width} x ${step.height}`;
      expect(seen.frame.width, `${at} frame`).toBe(step.frame);
      expect(Math.abs(seen.frame.x - (seen.room - step.frame) / 2), `${at} centred`).toBeLessThanOrEqual(1);
      expect([seen.read, seen.title], `${at} reading and title sizes`).toEqual([step.read, step.title]);
      // The description spans its column, and the column holds about 40 ems
      // of the reading size, so a line stays a comfortable length at every step.
      expect(seen.text, `${at} text spans the column`).toEqual(seen.main);
      expect(seen.main.width / seen.read, `${at} column in ems`).toBeGreaterThan(38);
      expect(seen.main.width / seen.read, `${at} column in ems`).toBeLessThan(42);
      expect(seen.sideways, `${at} nothing to scroll sideways`).toEqual([0, 0]);
      expect(seen.zooms, `${at} nothing zoomed`).toEqual(["1"]);
      // The supporting type steps with the text: a wider step is never smaller.
      if (before) {
        for (const key of ["read", "title", "figure", "meta"] as const) {
          expect(seen[key], `${at} ${key}`).toBeGreaterThanOrEqual(before[key]);
        }
      }
      before = seen;
    }
  });

  /* The owner's window: a wide, short one. The step is the width's alone. */
  test("a short window and a tall one of the same width draw the same posting", async ({ page }) => {
    await openPosting(page, { width: 1728, height: 837 });
    const short = await readStep(page);
    await openPosting(page, { width: 1728, height: 1117 });
    const tall = await readStep(page);
    expect(short).toEqual(tall);
    // The installed app's own frame at this width: content 1248 px from x 240.
    expect(short.frame).toEqual({ x: 240, width: 1248 });
  });

  test("the bar keeps its size and place at every step", async ({ page }) => {
    await openPosting(page, { width: 1440, height: 900 });
    const plain = await readBar(page);
    expect(plain.controls.length, "the bar's controls").toBeGreaterThan(2);
    for (const size of [{ width: 1728, height: 837 }, { width: 2160, height: 1350 }, { width: 2560, height: 1440 }]) {
      await openPosting(page, size);
      expect(await readBar(page), `${size.width} x ${size.height}`).toEqual(plain);
    }
  });

  test("the side column stops under the bar at the page's top inset on a wide step", async ({ page }) => {
    await openPosting(page, { width: 2160, height: 1350 });
    await page.locator(".cover-scroll").evaluate(async (box) => {
      box.scrollTop = 1400;
      await new Promise<void>((done) => requestAnimationFrame(() => requestAnimationFrame(() => done())));
      for (const animation of document.getAnimations()) animation.finish();
    });
    const scroll = (await page.locator(".cover-scroll").boundingBox())!;
    const column = (await page.locator(".jd-aside").boundingBox())!;
    expect(column.y - scroll.y).toBeCloseTo(40, 0);
    await expect(detail(page).locator(".jd-aside .section-title").first()).toBeInViewport({ ratio: 1 });
  });

  test("the stage menu opens under its button at its own size on a wide step", async ({ page }) => {
    const menuWidth = async () => {
      await detail(page).getByRole("button", { name: /^Applied/ }).click();
      const menu = page.getByRole("dialog", { name: /^Change the stage of / });
      await expect(menu).toBeVisible();
      await page.evaluate(() => { for (const animation of document.getAnimations()) animation.finish(); });
      const button = (await page.locator(".jd-stage").boundingBox())!;
      const panel = (await menu.locator(".ui-popover-inner").boundingBox())!;
      expect(panel.y - (button.y + button.height), "6px under the button").toBeCloseTo(6, 0);
      expect(panel.x + panel.width, "right edges meet").toBeCloseTo(button.x + button.width, 0);
      return Math.round(panel.width);
    };
    await openPosting(page, { width: 1440, height: 900 });
    const plain = await menuWidth();
    await openPosting(page, { width: 2560, height: 1440 });
    expect(await menuWidth()).toBe(plain);
  });

  test("the widest step passes the accessibility scan", async ({ page }) => {
    test.setTimeout(90_000);
    await openPosting(page, { width: 2560, height: 1440 });
    const { violations } = await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21aa", "wcag22aa"]).analyze();
    expect(violations.map((v) => `${v.id} (${v.nodes.length})`)).toEqual([]);
  });
});

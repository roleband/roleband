import { facetsFixture, picksStateFixture } from "../../src/test/fixtures";
import { msg } from "../../src/test/msg";
import { expect, mockGet, test, type Page } from "./fixtures";
import { installEveryRoute } from "./routesHarness";
import { healthyState, installPassedOverRoutes, picksList } from "./topPicksHarness";

/* ONE PAGE HEADER. Every tab of the rail names itself with the same h1, at the
   same height and the same left edge, so switching tabs moves nothing but the
   content. Measured through the rail, the way a jump is seen.

   A tab shows its title unless its first row is its own views: only the
   Pipeline's is, and it leaves its name to the top bar and the rail. Its h1
   is still the page's one heading, by the same name, and is not drawn. Top
   picks is measured set up, as the Radar's twin; its onboarding has a test of
   its own. */
const OFF_SCREEN = new Set([msg("shell-nav-pipeline")]);

const TABS = [
  { rail: msg("shell-nav-radar"), path: "/" },
  { rail: msg("shell-nav-top-picks"), path: "/top-picks" },
  { rail: msg("shell-nav-pipeline"), path: "/pipeline" },
  { rail: msg("shell-nav-profile"), path: "/profile" },
  { rail: msg("shell-nav-insights"), path: "/statistics" },
  { rail: msg("shell-nav-companies"), path: "/company" },
  { rail: msg("shell-nav-duplicates"), path: "/review" },
  { rail: msg("shell-nav-notifications"), path: "/notifications" },
  { rail: msg("shell-nav-settings"), path: "/settings" },
];

test.beforeEach(async ({ page }) => {
  await installEveryRoute(page);
  await mockGet(page, "/api/picks/state", (route) => route.fulfill({ json: healthyState() }));
  // Set up, Top picks reads its own list and facets.
  const picks = (url: string) => new URL(url).searchParams.get("top_picks") === "true";
  await mockGet(page, "/api/jobs?**", (route) =>
    picks(route.request().url()) ? route.fulfill({ json: picksList() }) : route.fallback());
  await mockGet(page, "/api/facets**", (route) =>
    picks(route.request().url()) ? route.fulfill({ json: facetsFixture }) : route.fallback());
});

/* Before setup, Top picks is its onboarding, which leads with a headline of
   its own: the tab's title stays the page's one h1 and is not drawn, so the
   screen shows one title, not two. */
test("Top picks' onboarding shows its own headline and keeps the title off screen", async ({ page }) => {
  await mockGet(page, "/api/picks/state", (route) => route.fulfill({ json: picksStateFixture() }));
  await page.goto("/top-picks");
  const main = page.getByRole("main").first();
  await expect(main.getByRole("heading", { level: 2, name: msg("picks-onboard-headline") })).toBeVisible();
  const title = main.getByRole("heading", { level: 1 });
  await expect(title).toHaveText(msg("shell-nav-top-picks"));
  await expect(page.getByRole("heading", { level: 1 })).toHaveCount(1);
  const box = (await title.boundingBox())!;
  expect(box.width * box.height, "the title takes no room").toBeLessThanOrEqual(1);
  await expect(main.locator(".page-hero"), "no title block").toHaveCount(0);
});

test("every tab's title is its rail label, in one place, at one size", async ({ page, isMobile }) => {
  test.slow();
  // 1440 on a desktop: wide enough that a screen capping its content at the
  // app's 1200 measure centres it, and its title drifts right of the others.
  if (!isMobile) await page.setViewportSize({ width: 1440, height: 900 });
  const seen: string[] = [];
  for (const tab of TABS) {
    await page.goto(tab.path);
    const title = page.getByRole("main").first().getByRole("heading", { level: 1 });
    await expect(title).toHaveText(tab.rail);
    // One h1 per screen: a panel's own title is an h2 under it.
    await expect(page.getByRole("heading", { level: 1 })).toHaveCount(1);
    if (OFF_SCREEN.has(tab.rail)) {
      const box = (await title.boundingBox())!;
      expect(box.width * box.height, `${tab.rail}'s title takes no room`).toBeLessThanOrEqual(1);
      await expect(page.getByRole("main").first().locator(".page-hero"), "no title block").toHaveCount(0);
      continue;
    }
    await expect(title).toBeVisible();
    seen.push(`${tab.rail}: ${await title.evaluate((node) => {
      const box = node.getBoundingClientRect();
      const style = getComputedStyle(node);
      return `${Math.round(box.top)}/${Math.round(box.left)} ${style.fontSize}/${style.fontWeight}`;
    })}`);
  }
  const places = new Set(seen.map((line) => line.split(": ")[1]));
  expect(places.size, seen.join("\n")).toBe(1);
});

/* ONE PAGE FRAME (docs/ui.md "The app shell"). Every screen but the
   Pipeline lays its title, its toolbar and its content in one frame, the page
   measure, so switching tabs moves no edge at any window width. At 1440 the
   measure is wider than the room and every screen passes whatever it sets;
   the wide windows are where a screen's own width shows. A page under a tab
   (Activity under Settings, Passed over under Top picks) keeps its tab's
   frame. The source half is `src/design/page-measure.test.ts`. */
const FRAMED = [
  ...TABS.filter((tab) => !OFF_SCREEN.has(tab.rail)).map((tab) => tab.path),
  "/settings/intelligence/activity",
  "/top-picks/passed",
];

/** The frame (the widest block of the page), the title's left edge when it
 *  is drawn, and every block that leaves the frame. */
async function frameOf(page: Page) {
  const main = page.getByRole("main").first();
  await expect(main.getByRole("heading", { level: 1 })).toHaveCount(1);
  return main.evaluate((root) => {
    const blocks = [...root.children].filter((node) => {
      const style = getComputedStyle(node);
      const box = node.getBoundingClientRect();
      return style.position !== "absolute" && style.position !== "fixed" && box.width > 1 && box.height > 1;
    });
    const frame = blocks.map((node) => node.getBoundingClientRect()).sort((a, b) => b.width - a.width)[0];
    const title = root.querySelector("h1")!.getBoundingClientRect();
    const escapes = blocks.filter((node) => {
      const box = node.getBoundingClientRect();
      return box.left < frame.left - 0.5 || box.right > frame.right + 0.5;
    }).map((node) => node.className);
    return {
      frame: `${Math.round(frame.left)}-${Math.round(frame.right)}`,
      title: title.width * title.height > 1 ? Math.round(title.left) : null,
      escapes,
    };
  });
}

for (const width of [1440, 1920, 2560]) {
  test(`every screen but the Pipeline keeps one frame at ${width}`, async ({ page, isMobile }) => {
    test.skip(isMobile, "a phone has one width; the claim is about wide windows");
    test.slow();
    await installPassedOverRoutes(page);
    await page.setViewportSize({ width, height: 900 });
    const seen: string[] = [];
    for (const path of FRAMED) {
      await page.goto(path);
      const { frame, title, escapes } = await frameOf(page);
      expect(escapes, `${path}: blocks outside its frame`).toEqual([]);
      seen.push(`${path}: ${frame}`);
      // A drawn title starts where the frame does.
      if (title !== null) expect(title, `${path}: the title against the frame ${frame}`).toBe(Number(frame.split("-")[0]));
    }
    const frames = new Set(seen.map((line) => line.split(": ")[1]));
    expect(frames.size, seen.join("\n")).toBe(1);
  });
}

test("the Pipeline alone runs past the page frame", async ({ page, isMobile }) => {
  test.skip(isMobile, "the claim is about a wide window");
  await page.setViewportSize({ width: 2560, height: 900 });
  await page.goto("/");
  const radar = await frameOf(page);
  await page.goto("/pipeline/board");
  const pipeline = await frameOf(page);
  const span = (frame: string) => { const [left, right] = frame.split("-").map(Number); return right - left; };
  expect(span(pipeline.frame)).toBeGreaterThan(span(radar.frame));
});

/* The check above, refusing a screen that takes its own width: it passes at
   1440, where no cap applies, and fails at 1920, which is how screens with
   six widths of their own all passed the 1440 check. A block that resets its
   side margins leaves the frame at any width the measure caps. */
test("the frame check refuses a screen with a width of its own", async ({ page, isMobile }) => {
  test.skip(isMobile, "the claim is about wide windows");
  const companiesWider = ".main.prof-main > * { max-width: 1520px !important; }";
  const measure = async (width: number) => {
    await page.setViewportSize({ width, height: 900 });
    await page.goto("/");
    const radar = await frameOf(page);
    await page.goto("/company");
    await page.addStyleTag({ content: companiesWider });
    const companies = await frameOf(page);
    return { radar: radar.frame, companies: companies.frame };
  };
  const narrow = await measure(1440);
  expect(narrow.companies).toBe(narrow.radar);
  const wide = await measure(1920);
  expect(wide.companies).not.toBe(wide.radar);

  await page.goto("/statistics");
  await page.addStyleTag({ content: ".main > .page-hero + * { margin: 0 !important; }" });
  expect((await frameOf(page)).escapes).not.toEqual([]);
});

/* ONE TAB ROW. The screens whose parts are ui/TabBar show it the same way:
   the tabs at one height and one left edge under the title, the content 20px
   below them, and NO line in between. The tabs are filled pills and need no
   baseline: a line under the row, above a panel's own border, reads as two
   lines. Duplicates wears a band only while its row is pinned, which a
   second test scrolls to. */
const TABBED = [
  { rail: msg("shell-nav-profile"), path: "/profile" },
  { rail: msg("shell-nav-insights"), path: "/statistics" },
  { rail: msg("shell-nav-duplicates"), path: "/review" },
  { rail: msg("shell-nav-settings"), path: "/settings" },
];

test("every tab row sits in one place, with the content 20px below and no line between", async ({ page, isMobile }) => {
  test.skip(isMobile, "the rows scroll sideways on a phone; one desktop geometry is the claim");
  await page.setViewportSize({ width: 1440, height: 900 });
  const seen: string[] = [];
  for (const tab of TABBED) {
    await page.goto(tab.path);
    const tabs = page.getByRole("main").first().getByRole("tablist").first();
    await expect(tabs).toBeVisible();
    const measured = await tabs.evaluate((bar) => {
      const row = bar.getBoundingClientRect();
      const main = bar.closest("main")!;
      // The content: the highest PAINTED box below the tab row (its own
      // text, a border or a fill), not a layout wrapper around it. A fill in
      // the page's own canvas is not paint: it is how a sticky toolbar
      // (Settings' search row) covers what scrolls under it, unseen at rest.
      const probe = document.createElement("div");
      probe.style.background = "var(--app-canvas)";
      main.append(probe);
      const canvas = getComputedStyle(probe).backgroundColor;
      probe.remove();
      const painted = (node: HTMLElement) => {
        const style = getComputedStyle(node);
        const text = [...node.childNodes].some((child) => child.nodeType === 3 && child.textContent!.trim() !== "");
        const border = ["top", "right", "bottom", "left"].some((side) => parseFloat(style.getPropertyValue(`border-${side}-width`)) > 0 && style.getPropertyValue(`border-${side}-style`) !== "none");
        const fill = !/rgba\(.*, 0\)$|transparent/.test(style.backgroundColor) && style.backgroundColor !== canvas;
        return text || border || fill;
      };
      let contentTop = Infinity;
      for (const node of main.querySelectorAll<HTMLElement>("*")) {
        if (node.contains(bar) || bar.contains(node)) continue;
        const box = node.getBoundingClientRect();
        if (box.height > 0 && box.width > 0 && box.top >= row.bottom - 0.5 && painted(node)) contentTop = Math.min(contentTop, box.top);
      }
      // A line in the gap: a painted top or bottom border on a wide element.
      const lines: string[] = [];
      for (const node of main.querySelectorAll<HTMLElement>("*")) {
        const style = getComputedStyle(node);
        const box = node.getBoundingClientRect();
        if (box.width < main.clientWidth / 3) continue;
        for (const [side, y] of [["bottom", box.bottom], ["top", box.top]] as const) {
          const width = parseFloat(style.getPropertyValue(`border-${side}-width`));
          const painted = width > 0 && style.getPropertyValue(`border-${side}-style`) !== "none" && !/rgba\(.*, 0\)$|transparent/.test(style.getPropertyValue(`border-${side}-color`));
          if (painted && y > row.bottom + 0.5 && y < contentTop - 0.5) lines.push(`${node.className} ${side}@${Math.round(y)}`);
        }
      }
      return { top: Math.round(row.top), left: Math.round(row.left), gap: Math.round(contentTop - row.bottom), lines };
    });
    seen.push(`${tab.rail}: ${measured.top}/${measured.left} gap ${measured.gap}${measured.lines.length ? ` lines ${measured.lines.join(", ")}` : ""}`);
  }
  const report = seen.join("\n");
  expect(new Set(seen.map((line) => line.split(": ")[1])).size, report).toBe(1);
  expect(report).toContain("gap 20");
  expect(report).not.toContain("lines");
});

test("the Duplicates tab row takes a surface only while it is pinned", async ({ page, isMobile }) => {
  test.skip(isMobile, "one geometry");
  await page.setViewportSize({ width: 1280, height: 420 });
  await page.goto("/review");
  const toolbar = page.locator(".review-toolbar");
  await expect(page.getByRole("tablist", { name: "Duplicate review views" })).toBeVisible();
  const band = () => toolbar.evaluate((node) => getComputedStyle(node, "::before").opacity);
  await expect(toolbar).not.toHaveAttribute("data-stuck");
  expect(await band()).toBe("0");
  // The fixture queue is one pair, too short to scroll: give the page room,
  // then scroll it, so the row pins as it does over a real queue.
  await page.locator(".review").evaluate((review) => {
    const room = document.createElement("div");
    room.style.height = "2000px";
    review.append(room);
  });
  await page.getByRole("main").first().evaluate((main) => main.scrollTo({ top: 400 }));
  await expect(toolbar).toHaveAttribute("data-stuck", "true");
  await expect.poll(band).toBe("1");
});

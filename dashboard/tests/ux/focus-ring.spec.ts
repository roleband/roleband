/* ONE FOCUS RING (docs/ui.md "One focus ring"). Wherever
   the keyboard lands, the same ring says so: a solid outline of
   `--app-ring-width` in `--app-action`, the action colour of the surface it
   sits on (the rail's own `--rail-accent`). Other looks fail: a
   soft halo or a tinted outline falls under the 3:1 a focus indicator needs
   (1.4.11), and a left bar on a Board row is the same mark as a row picked
   for Compare.

   Name-blind on purpose: the sweep Tabs through every screen family and judges
   whatever takes focus, so a control added next month is covered without being
   listed. A ring may be drawn somewhere other than the focused element in
   exactly two ways, both named here: by a CARRIER (an ancestor that IS the
   control the user sees, because the focused element is hidden or is only its
   text) and, for SVG marks, as a STROKE on the shape (an outline on an SVG `g`
   draws its bounding box). The source half is `src/design/focus-ring.test.ts`.

   A field has an edge of its own, and its ring is drawn over that edge: one
   line where the border was, never the border and a ring outside it with a gap
   between, which reads as two or three lines. */

import { applicationCardFixture, applicationDetailFixture, jobFixture } from "../../src/test/fixtures";
import { msg } from "../../src/test/msg";
import { expect, mockGet, test, type Page } from "./fixtures";
import { installEveryRoute } from "./routesHarness";
import { installSettingsRoutes } from "./settingsHarness";

const SCREENS = [
  "/",
  "/favorites",
  "/statistics/overview",
  "/profile/direction",
  "/settings/companies",
  "/settings/intelligence",
  "/settings/schedule",
  "/settings/plugins",
  "/company",
  "/review",
  "/notifications",
  "/welcome",
  "/pipeline/list",
  "/pipeline/board",
  "/pipeline/up-next",
  // A role's page: its posting, then its Workspace with the notes page and
  // the next steps' fields.
  "/company/openai/job/101",
  "/company/openai/job/101?tab=workspace",
];

/** The dialogs a person opens most, each judged stop by stop like a screen:
 *  where it opens, and how. */
const DIALOGS: { name: string; path: string; open: (page: Page) => Promise<unknown> }[] = [
  { name: "the interview form", path: "/company/openai/job/101?tab=workspace",
    open: (page) => page.getByRole("button", { name: msg("applications-interview-add") }).click() },
  { name: "the notes' earlier versions", path: "/company/openai/job/101?tab=workspace",
    open: (page) => page.getByRole("button", { name: msg("applications-notes-versions") }).click() },
  { name: "the stage menu", path: "/company/openai/job/101",
    open: async (page) => {
      // M answers once the role's card has loaded and drawn its stage button.
      await expect(page.locator('[aria-keyshortcuts="m"]')).toBeVisible();
      await page.keyboard.press("m");
    } },
  { name: "the command palette", path: "/", open: (page) => page.keyboard.press("ControlOrMeta+k") },
  { name: "the keyboard shortcuts", path: "/", open: (page) => page.keyboard.press("?") },
];

/** Focused element -> the element that draws its ring. Kept in step with the
 *  carrier list in `src/design/focus-ring.test.ts`. Most are an ancestor; the
 *  palette's field never loses focus while the palette is open, so its
 *  highlighted option, where Enter acts, wears the ring instead. */
const CARRIERS: [string, string][] = [
  [".ui-search-input", ".ui-search"],
  [".filter-search-row input", ".filter-search-row"],
  [".ui-timefield-framed input", ".ui-timefield-framed"],
  [".palette-input input", ".palette-item.is-cursor"],
];

async function focusedRing(page: Page) {
  return page.evaluate(async (carriers) => {
    const el = document.activeElement as HTMLElement | SVGElement | null;
    if (!el || el === document.body) return null;
    const box = el.getBoundingClientRect();
    if (box.width === 0 && box.height === 0) return null;
    const owners = carriers.flatMap(([focused, carrier]) => {
      const owner = el.matches(focused)
        ? el.closest(carrier) ?? el.closest('[role="dialog"]')?.querySelector(carrier) ?? null
        : null;
      return owner ? [owner] : [];
    });
    // Computed styles flush pending transitions before their completion is awaited.
    const shapes = el instanceof SVGElement ? Array.from(el.querySelectorAll("*")) : [];
    const transitions = [el, ...owners, ...shapes].flatMap((node) => {
      getComputedStyle(node).outlineColor;
      return node.getAnimations().filter((animation) => animation instanceof CSSTransition);
    });
    await Promise.all(transitions.map((animation) => animation.finished.catch(() => {})));
    const sig = `${el.tagName.toLowerCase()}${el.classList.length ? "." + Array.from(el.classList).slice(0, 2).join(".") : ""}`;

    // The gold of the surface the ring sits on.
    const rail = el.closest(".nav-rail");
    const probe = document.createElement("span");
    probe.style.color = rail ? "var(--rail-accent)" : "var(--app-action)";
    (rail ?? document.body).appendChild(probe);
    const gold = getComputedStyle(probe).color;
    probe.remove();

    // Judged as drawn: under CSS zoom (the interview form, magnified setup) the
    // engine snaps the ring to whole pixels and reports it divided by the zoom.
    const rings = (node: Element) => {
      const cs = getComputedStyle(node);
      const zoom = (node as Element & { currentCSSZoom?: number }).currentCSSZoom ?? 1;
      return cs.outlineStyle === "solid" && parseFloat(cs.outlineWidth) * zoom >= 1.99 && cs.outlineColor === gold;
    };
    const describe = (node: Element) => {
      const cs = getComputedStyle(node);
      return `outline ${cs.outlineStyle} ${cs.outlineWidth} ${cs.outlineColor}; shadow ${cs.boxShadow.slice(0, 60)}`;
    };

    // A field's ring, on the field or on the carrier that is the field, covers
    // the field's border: the outline spans [offset, offset + width] outward
    // from the border box, the border [-border, 0]. The fields are listed
    // here, not read from shell.css, so a field dropped from that rule is
    // still checked. An editable page is a field: a `div` the person types in.
    const FIELD = 'input:not([type="checkbox"], [type="radio"], [type="range"], [type="color"], [type="file"], [type="button"], [type="submit"], [type="reset"], [type="image"]), select, textarea, [contenteditable="true"]';
    const onEdge = (node: Element) => {
      const cs = getComputedStyle(node);
      const border = parseFloat(cs.borderTopWidth);
      if (!el.matches(FIELD) || border === 0) return true;
      const offset = parseFloat(cs.outlineOffset);
      return offset <= -border && offset + parseFloat(cs.outlineWidth) >= 0;
    };
    // A carrier draws the ring in place of the focused element, never beside it.
    if (rings(el) && owners.some(rings)) return { sig, ok: false, what: `two rings, on the focused element and on its carrier: ${describe(el)}` };
    const painter = rings(el) ? el : owners.find(rings);
    if (painter && !onEdge(painter)) return { sig, ok: false, what: `a field ringed outside its own edge: ${describe(painter)} offset ${getComputedStyle(painter).outlineOffset}` };
    if (painter) return { sig, ok: true };
    if (el instanceof SVGElement) {
      const stroked = Array.from(el.querySelectorAll("*")).some((shape) => {
        const cs = getComputedStyle(shape);
        return cs.stroke === gold && parseFloat(cs.strokeWidth) >= 2;
      });
      if (stroked) return { sig, ok: true };
    }
    return { sig, ok: false, what: describe(el) };
  }, CARRIERS);
}

/** Role 101 on the board as interviewing: the posting carries its pursuit, so
 *  the role's page draws its stage button and its Workspace, with one earlier
 *  version of the notes to offer back. */
async function routeRoleOnBoard(page: Page) {
  const card = applicationCardFixture({ job_id: 101, pursuit_id: 7, stage: "interviewing" });
  await mockGet(page, "/api/jobs/101", (route) => route.fulfill({ json: {
    ...jobFixture, is_favorite: true,
    pursuit: { id: 7, job_id: 101, stage: card.stage, priority: card.priority, notes: null,
      next_action: null, next_action_due: null, created_at: "2026-10-20T09:00:00Z", updated_at: "2026-11-04T12:00:00Z" },
  } }));
  await mockGet(page, "/api/applications/101", (route) => route.fulfill({
    json: applicationDetailFixture({ application: card }),
  }));
  await mockGet(page, "/api/applications", (route) => route.fulfill({ json: { applications: [card] } }));
  await mockGet(page, "/api/applications/101/notes/versions", (route) => route.fulfill({
    json: { versions: [{ actor: "user", at: "2026-11-20T10:00:00Z", text: "Ask Sam" }] },
  }));
}
const isRolePage = (path: string) => path.startsWith("/company/") && path.includes("/job/");

const STOPS = 60;
/** A role's page holds the most stops: the rail, its bar, then the page. */
const stopsOn = (path: string) => (isRolePage(path) ? 110 : STOPS);

test.use({ reducedMotion: "reduce" });

test.beforeEach(async ({ page }) => {
  await installEveryRoute(page);
  await installSettingsRoutes(page);
});

for (const theme of ["light", "dark"] as const) {
  for (const path of SCREENS) {
    test(`every keyboard stop on ${path} wears the one ring (${theme})`, async ({ page, isMobile }) => {
      test.skip(isMobile, "Tab order is a desktop keyboard contract; WebKit's Tab skips links by default");
      test.setTimeout(60_000);
      if (isRolePage(path)) await routeRoleOnBoard(page);
      await page.addInitScript((t) => localStorage.setItem("theme", t), theme);
      await page.setViewportSize({ width: 1440, height: 900 });
      await page.goto(path);
      await expect(page.locator("h1").first()).toBeVisible();
      if (path.includes("tab=workspace")) await expect(page.locator('[contenteditable="true"]').first()).toBeVisible();

      const failures = new Map<string, string>();
      let judged = 0;
      for (let i = 0; i < stopsOn(path); i++) {
        await page.keyboard.press("Tab");
        // Read on the rendering frame; reduced motion removes transition-duration waits.
        await page.evaluate(() => new Promise<void>((resolve) => requestAnimationFrame(() => resolve())));
        const verdict = await focusedRing(page);
        if (!verdict) continue;
        judged++;
        if (!verdict.ok && !failures.has(verdict.sig)) failures.set(verdict.sig, verdict.what!);
      }

      // A sweep that judged nothing would pass every screen.
      expect(judged, `${path}: the keyboard reached nothing`).toBeGreaterThan(5);
      expect([...failures].map(([sig, what]) => `${sig}: ${what}`), `${path} (${theme})`).toEqual([]);
    });
  }
}

for (const theme of ["light", "dark"] as const) {
  for (const dialog of DIALOGS) {
    test(`every keyboard stop in ${dialog.name} wears the one ring (${theme})`, async ({ page, isMobile }) => {
      test.skip(isMobile, "Tab order is a desktop keyboard contract; WebKit's Tab skips links by default");
      test.setTimeout(60_000);
      await routeRoleOnBoard(page);
      await page.addInitScript((t) => localStorage.setItem("theme", t), theme);
      await page.setViewportSize({ width: 1440, height: 900 });
      await page.goto(dialog.path);
      await expect(page.locator("h1").first()).toBeVisible();
      await dialog.open(page);
      const opened = page.getByRole("dialog").last();
      await expect(opened).toBeVisible();

      const failures = new Map<string, string>();
      let judged = 0;
      // The first stop is where the dialog puts the keyboard as it opens.
      for (let i = 0; i < 30; i++) {
        if (i > 0) await page.keyboard.press("Tab");
        await page.evaluate(() => new Promise<void>((resolve) => requestAnimationFrame(() => resolve())));
        const where = await opened.evaluate((box) => (box.contains(document.activeElement)
          ? document.activeElement === box || document.activeElement?.getAttribute("role") === "dialog" ? "box" : "inside"
          : "out")).catch(() => "out");
        if (where === "out") break;
        // The dialog's own box holds the keyboard as it opens; it is not a control.
        if (where === "box") continue;
        const verdict = await focusedRing(page);
        if (!verdict) continue;
        judged++;
        if (!verdict.ok && !failures.has(verdict.sig)) failures.set(verdict.sig, verdict.what!);
      }

      expect(judged, `${dialog.name}: the keyboard reached nothing in it`).toBeGreaterThan(0);
      expect([...failures].map(([sig, what]) => `${sig}: ${what}`), `${dialog.name} (${theme})`).toEqual([]);
    });
  }
}

for (const theme of ["light", "dark"] as const) {
  test(`a focused button paints its ring with normal motion (${theme})`, async ({ page }) => {
    await page.emulateMedia({ reducedMotion: "no-preference" });
    await page.addInitScript((value) => localStorage.setItem("theme", value), theme);
    await page.goto("/");
    await expect(page.getByRole("heading", { level: 1 })).toBeVisible();
    await page.keyboard.press("Tab");
    await page.getByRole("button").first().focus();
    await expect.poll(async () => (await focusedRing(page))?.ok ?? false).toBe(true);
  });
}

test("the ring verifier refuses a field ringed outside its own edge", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByRole("heading", { level: 1 })).toBeVisible();
  const search = page.locator(".ui-search-input").first();
  await search.focus();
  await expect.poll(async () => (await focusedRing(page))?.ok ?? false).toBe(true);
  await page.addStyleTag({ content: ".ui-search:focus-within { outline-offset: var(--app-ring-offset) !important; }" });
  const verdict = await focusedRing(page);
  expect(verdict?.ok).toBe(false);
  expect(verdict?.what).toContain("outside its own edge");
});

test("the ring verifier refuses a control whose painted ring is removed", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByRole("heading", { level: 1 })).toBeVisible();
  await page.keyboard.press("Tab");
  await page.getByRole("button").first().focus();
  await expect.poll(async () => (await focusedRing(page))?.ok ?? false).toBe(true);
  await page.addStyleTag({ content: "button:focus-visible { outline: none !important; box-shadow: none !important; }" });
  expect((await focusedRing(page))?.ok).toBe(false);
});

// One test per theme: init scripts pile up on a page, so a second theme's
// script set on the same page would run beside the first.
for (const theme of ["light", "dark"] as const) {
  test(`a click into a field rings it on its own edge, in the ${theme} theme`, async ({ page, isMobile }) => {
    test.skip(isMobile, "the pane's fields are judged at desktop width; the sweep owns the rest");
    await page.setViewportSize({ width: 1440, height: 900 });
    await page.addInitScript((t) => localStorage.setItem("theme", t), theme);
    for (const path of ["/", "/pipeline/list"]) {
      await page.goto(path);
      await expect(page.locator("html")).toHaveAttribute("data-theme", theme);
      await expect(page.locator("h1").first()).toBeVisible();
      await page.getByRole("searchbox").first().click();
      const ring = await focusedRing(page);
      expect(ring, `${path} ${theme}: the click focused nothing`).not.toBeNull();
      expect(ring!.ok, `${path} ${theme}: ${ring!.what}`).toBe(true);
    }
  });
}

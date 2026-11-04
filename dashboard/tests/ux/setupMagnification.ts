import AxeBuilder from "@axe-core/playwright";
import { expect, test, type Page } from "./fixtures";
import {
  facetsFixture, jobListFixture, notificationsFixture, settingsSaveFixture, statsFixture, statusFixture,
  usageStateFixture,
} from "../../src/test/fixtures";
import type { ScopeSettingsPayload } from "../../src/api";
import { place } from "../../src/features/scope/welcome/globeView";
import { installEveryRoute } from "./routesHarness";
import { scopeCatalog, scopePreview } from "./scopeFixtures";
import { installCompanyRegisterRoutes } from "./settingsHarness";

/* First-run setup magnified on a large window must be the 1440 x 900 design,
   larger (docs/ui.md, "First-run setup magnification"): every element the same
   size and in the same place against every other, every text on the same
   number of lines. These tests walk the ten setup screens and hold a magnified
   run against the design element by element, in page pixels. The factor is
   measured from a 100 px box, never read from the code under test, and whether
   this engine draws text in proportion is measured here too, independently of
   the code's own check.

   Each engine has its own spec file (Playwright picks the browser per file):
   `setup-magnification.spec.ts` for the suite's Chromium, which on Linux rounds
   letters to whole pixels and must therefore stay at 1, and one file each for
   WebKit and for Chromium without font hinting, which must magnify. */

const FRESH = { profile: null, scope_configured: false, intent_statement: "" };

async function installSetup(page: Page) {
  await page.route("/api/profile", (route) => route.fulfill({ json: FRESH }));
  await page.route("/api/stats", (route) => route.fulfill({ json: statsFixture }));
  await page.route("/api/status", (route) => route.fulfill({ json: statusFixture }));
  await page.route("/api/facets", (route) => route.fulfill({ json: facetsFixture }));
  await page.route("/api/notifications**", (route) => route.fulfill({ json: notificationsFixture }));
  await page.route("/api/jobs?**", (route) => route.fulfill({ json: { ...jobListFixture, items: [], total: 0 } }));
  await page.route("/api/scope/catalog", (route) => route.fulfill({ json: scopeCatalog }));
  await page.route("/api/scope/preview", (route) => route.fulfill({ json: scopePreview }));
  await page.route("/api/scope/rules", (route) => route.fulfill({ json: { rules: [] } }));
  await page.route("/api/scope/places?**", (route) => route.fulfill({ json: { places: [], unions: [] } }));
  await page.route("/api/companies", (route) => route.fulfill({ json: { companies: [] } }));
  await page.route("/api/profile/suggestions", (route) => route.fulfill({ json: { suggestions: [] } }));
  await page.route("/api/profile/pay-floor", (route) => route.fulfill({ json: { pay_floor: null } }));
  await page.route("/api/settings", async (route) => {
    if (route.request().method() !== "PUT") return route.fallback();
    const body = route.request().postDataJSON() as ScopeSettingsPayload;
    await route.fulfill({ json: settingsSaveFixture(body, { in_scope_changed: 0, on_board: 0 }) });
  });
  await installCompanyRegisterRoutes(page);
  await page.route("/api/usage", (route) => route.request().method() === "GET"
    ? route.fulfill({ json: usageStateFixture("undecided") }) : route.fallback());
  await page.route("/api/usage/consent", (route) => route.fulfill({ json: usageStateFixture("declined") }));
}

/** The zoom the page is drawn at, from a 100 px box made for the reading. */
function measuredZoom(page: Page): Promise<number> {
  return page.evaluate(() => {
    const box = document.createElement("div");
    box.style.cssText = "position:fixed;left:0;top:0;width:100px;height:1px;visibility:hidden;pointer-events:none";
    document.body.appendChild(box);
    const zoom = box.getBoundingClientRect().width / 100;
    box.remove();
    return zoom;
  });
}

/** The zoom once the window's size has been taken up: two frames, because
    under reduced motion every property change is a short transition. */
async function settledZoom(page: Page): Promise<number> {
  await page.evaluate(() => new Promise((done) => requestAnimationFrame(() => requestAnimationFrame(() => done(null)))));
  await page.waitForTimeout(50);
  return measuredZoom(page);
}

/** Whether this engine draws the app's typefaces in proportion at `factor`,
    within half a percent, measured on new elements. */
function textInProportion(page: Page, factor: number): Promise<boolean> {
  return page.evaluate((f) => {
    const widths = (zoom: number) => {
      const host = document.createElement("div");
      host.style.cssText = `position:absolute;left:0;top:0;visibility:hidden;white-space:nowrap;zoom:${zoom}`;
      for (const family of ["var(--app-font-sans)", "var(--app-font-mono)"]) {
        for (const size of [10, 12, 13, 14]) {
          const line = document.createElement("div");
          line.style.cssText = `width:max-content;font-family:${family};font-size:${size}px`;
          line.textContent = "The quick brown fox jumps over the lazy dog, 0123456789 times.";
          host.appendChild(line);
        }
      }
      document.body.appendChild(host);
      const out = [...host.children].map((line) => line.getBoundingClientRect().width);
      host.remove();
      return out;
    };
    const plain = widths(1);
    const larger = widths(f);
    return plain.every((width, i) => Math.abs(larger[i] / (width * f) - 1) <= 0.005);
  }, factor);
}

type Layout = {
  zoom: number;
  boxes: Record<string, [number, number, number, number]>;
  lines: Record<string, number>;
};

/** Every visible element's box and every text's line count, in page pixels,
    keyed by its place in the page. */
function layout(page: Page): Promise<Layout> {
  return page.evaluate(() => {
    const probe = document.createElement("div");
    probe.style.cssText = "position:fixed;left:0;top:0;width:100px;height:1px;visibility:hidden;pointer-events:none";
    document.body.appendChild(probe);
    const k = probe.getBoundingClientRect().width / 100;
    probe.remove();
    const path = (el: Element) => {
      const parts: string[] = [];
      for (let e: Element | null = el; e && e !== document.body; e = e.parentElement) {
        const parent: Element | null = e.parentElement;
        const index = parent ? Array.prototype.indexOf.call(parent.children, e) : 0;
        const cls = typeof e.className === "string" && e.className ? `.${e.className.split(" ")[0]}` : "";
        parts.push(`${e.tagName.toLowerCase()}${cls}:${index}`);
      }
      return parts.reverse().join(">");
    };
    const inWindow = (r: DOMRect) => r.right > 0 && r.bottom > 0 && r.left < innerWidth && r.top < innerHeight;
    const boxes: Layout["boxes"] = {};
    for (const el of document.body.querySelectorAll("*")) {
      if (el.closest("script, style")) continue;
      const r = el.getBoundingClientRect();
      if ((r.width === 0 && r.height === 0) || !inWindow(r)) continue;
      if (getComputedStyle(el).display === "none") continue;
      boxes[path(el)] = [r.x / k, r.y / k, r.width / k, r.height / k];
    }
    const lines: Layout["lines"] = {};
    const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
    let i = 0;
    for (let node = walker.nextNode(); node; node = walker.nextNode()) {
      const parent = node.parentElement;
      if (!(node.textContent ?? "").trim() || !parent || parent.closest("script, style")) continue;
      const range = document.createRange();
      range.selectNodeContents(node);
      const rects = [...range.getClientRects()].filter((c) => c.width > 0 && inWindow(c));
      if (rects.length === 0) continue;
      const tops: number[] = [];
      for (const c of rects) if (!tops.some((top) => Math.abs(top - c.top / k) < 3)) tops.push(c.top / k);
      lines[`${path(parent)}#${i++}`] = tops.length;
    }
    return { zoom: k, boxes, lines };
  });
}

/** What differs between the design and a magnified run beyond `tolerance`
    page pixels, each as a line naming the element. */
function differences(design: Layout, run: Layout, tolerance = 2): string[] {
  const out: string[] = [];
  const edges = ["x", "y", "width", "height"];
  for (const [key, box] of Object.entries(design.boxes)) {
    const other = run.boxes[key];
    if (!other) { out.push(`missing ${key}`); continue; }
    box.forEach((value, n) => {
      const off = Math.abs(other[n] - value);
      if (off > tolerance) out.push(`${key} ${edges[n]} ${value.toFixed(1)} -> ${other[n].toFixed(1)} (${off.toFixed(1)} px)`);
    });
  }
  for (const key of Object.keys(run.boxes)) if (!design.boxes[key]) out.push(`extra ${key}`);
  for (const [key, count] of Object.entries(design.lines)) {
    if (run.lines[key] !== undefined && run.lines[key] !== count) out.push(`${key} wraps onto ${run.lines[key]} lines, not ${count}`);
  }
  return out;
}

const SCREENS = ["intro", "sharing", "track", "level", "where", "roles", "world", "summary", "companies", "follow-all"] as const;
type Screen = (typeof SCREENS)[number];
const FIXED: readonly Screen[] = ["track", "level", "where", "summary", "companies"];

/** Walks first-run setup from the welcome to the follow confirmation, calling
    `at` on each screen once it has settled. `plain` draws it without the
    magnification at any window size: the design a magnified run is held
    against. The walk never reloads, so the style lasts until the next one. */
async function walkSetup(page: Page, at: (screen: Screen) => Promise<void>, { plain = false } = {}) {
  // Entry animations are taken to their end (a dialog grows in from 0.985): on
  // a still page WebKit may not advance one until something asks for a frame.
  const finish = () => page.evaluate(() => {
    for (const animation of document.getAnimations()) {
      if (animation.effect?.getComputedTiming().iterations !== Infinity) animation.finish();
    }
  });
  const boxes = () => page.evaluate(() => [...document.body.querySelectorAll("*")].map((el) => {
    const r = el.getBoundingClientRect();
    return `${Math.round(r.x)},${Math.round(r.y)},${Math.round(r.width)},${Math.round(r.height)}`;
  }).join(" "));
  // A screen has settled once a crossfade has let its old phase go (it fades
  // at a fixed size, on its own clock, later on a busy machine) and its layout
  // holds still.
  const settle = async (screen: Screen) => {
    await page.evaluate(() => document.fonts.ready);
    await finish();
    await page.waitForFunction(() => [...document.querySelectorAll(".phase-stack")]
      .every((stack) => stack.querySelectorAll(":scope > .phase-layer").length <= 1), null, { timeout: 10_000 });
    let before = await boxes();
    for (let tries = 0; tries < 30; tries++) {
      await page.waitForTimeout(200);
      await finish();
      const now = await boxes();
      if (now === before) break;
      before = now;
    }
    await at(screen);
  };
  await page.emulateMedia({ reducedMotion: "reduce" });
  await page.goto("/welcome");
  if (plain) await page.addStyleTag({ content: "html { zoom: 1 !important; --page-zoom: 1 !important; }" });
  await expect(page.getByRole("button", { name: "Tune the radar" })).toBeVisible();
  await page.mouse.move(1, 1);
  await settle("intro");
  await page.getByRole("button", { name: "Tune the radar" }).click();
  await expect(page.getByRole("region", { name: "Help us improve" })).toBeVisible();
  await settle("sharing");
  await page.getByRole("button", { name: "No thanks" }).click();
  await expect(page.getByRole("heading", { name: "What kind of role are you looking for?" })).toBeVisible();
  await page.getByLabel("Hands-on, as the expert").check();
  await settle("track");
  await page.getByRole("button", { name: "Continue" }).click();
  await expect(page.getByRole("heading", { name: "Your level" })).toBeVisible();
  await page.locator(".stage-cell").filter({ hasText: "Staff" }).click();
  await page.locator(".stage-cell").filter({ hasText: "Staff" }).click();
  await settle("level");
  await page.getByRole("button", { name: "Continue" }).click();
  await expect(page.getByRole("heading", { name: "Where do you want to work?" })).toBeVisible();
  await page.getByLabel("Where are you based?").fill("silicon");
  await page.getByRole("button", { name: "Add Silicon Valley" }).click();
  await settle("where");
  await page.getByRole("button", { name: "Continue" }).click();
  await expect(page.getByRole("heading", { name: "Any particular roles?" })).toBeVisible();
  await settle("roles");
  await page.getByRole("button", { name: "Skip" }).click();
  await expect(page.getByRole("heading", { name: "Anything you care about, or want to avoid?" })).toBeVisible();
  await settle("world");
  await page.getByRole("button", { name: "Skip" }).click();
  await expect(page.getByRole("heading", { name: "Summary" })).toBeVisible();
  await settle("summary");
  await page.getByRole("button", { name: "Continue" }).click();
  await expect(page.getByRole("heading", { name: "Where should your radar look?" })).toBeVisible();
  await settle("companies");
  await page.getByRole("radio", { name: /^Every listed company/ }).check();
  await page.getByRole("button", { name: "Start the radar" }).click();
  await expect(page.getByRole("dialog", { name: "Follow the whole list?" })).toBeVisible();
  await settle("follow-all");
}

/** Back to a new visitor: the walk keeps its answers for the tab. */
async function forget(page: Page) {
  await page.evaluate(() => { sessionStorage.clear(); });
}

type Engine = {
  browser: "chromium" | "webkit";
  /** Whether this engine must draw text in proportion, and so magnify. */
  magnifies: boolean;
};

/** The magnification's tests, for the engine the calling file runs. */
export function magnificationTests({ browser, magnifies }: Engine) {
  test.skip(({ isMobile }) => isMobile, "a phone window is never magnified; the desktop engines carry these");

  test(`runs in ${browser}`, ({ browserName }) => {
    expect(browserName).toBe(browser);
  });

  test("this engine magnifies only if it draws text in proportion", async ({ page }) => {
    await installSetup(page);
    await page.setViewportSize({ width: 2160, height: 1350 });
    await page.goto("/welcome");
    await expect(page.getByRole("button", { name: "Tune the radar" })).toBeVisible();
    expect(await textInProportion(page, 1.3)).toBe(magnifies);
    expect(await settledZoom(page)).toBeCloseTo(magnifies ? 1.3 : 1, 3);
  });

  /* Each window is walked twice: at its factor, and plain at the window that
     factor divides it to, so both lay out the same page; the design is that
     window to the nearest pixel. */
  const CASES = ([
    { name: "1.06", run: { width: 1584, height: 990 }, factor: 1.06 },
    { name: "1.12", run: { width: 1728, height: 1080 }, factor: 1.12 },
    { name: "1.18", run: { width: 1872, height: 1170 }, factor: 1.18 },
    { name: "1.23 in a 2000 x 1100 window", run: { width: 2000, height: 1100 }, factor: 1 + 0.6 * (2000 / 1440 - 1) },
    { name: "1.3", run: { width: 2160, height: 1350 }, factor: 1.3 },
  ]).map((c) => ({ ...c, design: { width: Math.round(c.run.width / c.factor), height: Math.round(c.run.height / c.factor) } }));
  // Where text is not in proportion, one walk at the cap shows that no screen magnifies.
  for (const c of magnifies ? CASES : CASES.filter((one) => one.name === "1.3")) {
    test(`magnified ${c.name}, every setup screen is the design, larger`, async ({ page }) => {
      test.setTimeout(180_000);
      // One tab for both walks: a tab behind another runs no animations in WebKit.
      await installSetup(page);
      await page.setViewportSize(c.design);
      const design = new Map<Screen, Layout>();
      await walkSetup(page, async (screen) => {
        const seen = await layout(page);
        expect(seen.zoom, `${screen} at the design's own size`).toBe(1);
        design.set(screen, seen);
      }, { plain: true });
      await forget(page);
      await page.setViewportSize(c.run);
      const problems: string[] = [];
      await walkSetup(page, async (screen) => {
        const run = await layout(page);
        expect.soft(run.zoom, screen).toBeCloseTo(magnifies ? c.factor : 1, 3);
        if (magnifies) for (const d of differences(design.get(screen)!, run)) problems.push(`${screen}: ${d}`);
      });
      expect(problems.slice(0, 30), `${problems.length} elements differ from the design`).toEqual([]);
    });
  }

  if (!magnifies) return;

  test("the factor takes six tenths of the window's room, bound by its width, its height and the cap", async ({ page }) => {
    await installSetup(page);
    await page.goto("/welcome");
    await expect(page.getByRole("button", { name: "Tune the radar" })).toBeVisible();
    for (const [width, height, factor] of [
      [1440, 1100, 1], [2000, 760, 1], [1280, 800, 1], [1600, 900, 1 + 0.6 * (1600 / 1440 - 1)],
      [2000, 900, 1 + 0.6 * (900 / 760 - 1)], [1728, 1000, 1.12], [1872, 1170, 1.18],
      [2160, 1350, 1.3], [2560, 1440, 1.3], [1440, 900, 1],
    ] as const) {
      await page.setViewportSize({ width, height });
      expect(await settledZoom(page), `${width} x ${height}`).toBeCloseTo(factor, 3);
    }
  });

  test("the fixed steps fit the smallest window of each factor, Back and Continue in view", async ({ page }) => {
    test.setTimeout(120_000);
    await installSetup(page);
    for (const factor of [1.1, 1.2, 1.3]) {
      // The smallest window with the room for this factor.
      const room = 1 + (factor - 1) / 0.6;
      await page.setViewportSize({ width: Math.ceil(1440 * room), height: Math.ceil(760 * room) });
      await walkSetup(page, async (screen) => {
        if (screen === "intro" || screen === "sharing" || screen === "follow-all") return;
        const head = await page.locator(".walk-card-head").first().boundingBox();
        expect(head, `${screen} at ${factor}`).not.toBeNull();
        expect(head!.y, `${screen}'s header is in the window at ${factor}`).toBeGreaterThanOrEqual(0);
        if (!FIXED.includes(screen)) return;
        const scroller = await page.locator(".main").evaluate((main) => [main.scrollHeight, main.clientHeight]);
        expect(scroller[0], `${screen} does not scroll at ${factor}`).toBeLessThanOrEqual(scroller[1]);
        const window = page.viewportSize()!;
        for (const name of ["Back", /^(Continue|Start the radar)$/]) {
          const button = page.locator(".walk-step-foot").getByRole("button", { name }).first();
          if (await button.count() === 0) continue;
          const box = (await button.boundingBox())!;
          expect(box.y + box.height, `${screen}'s ${String(name)} is in the window at ${factor}`).toBeLessThanOrEqual(window.height);
        }
      });
      await forget(page);
    }
  });

  test("the planet answers a press anywhere it is drawn, and nowhere else", async ({ page }) => {
    await installSetup(page);
    for (const [width, height] of [[1440, 900], [2160, 1350]] as const) {
      await page.setViewportSize({ width, height });
      await page.emulateMedia({ reducedMotion: "reduce" });
      await page.goto("/welcome");
      await expect(page.getByRole("button", { name: "Tune the radar" })).toBeVisible();
      const zoom = await settledZoom(page);
      const globe = page.locator("canvas.welcome-globe");
      const box = (await globe.boundingBox())!;
      const [clientWidth, clientHeight] = await globe.evaluate((el) => [el.clientWidth, el.clientHeight]);
      const at = place(clientWidth, clientHeight);
      // A point on the planet's own layout, in window pixels; kept only where
      // the planet is what the pointer reaches (the words cover its west).
      const point = async (share: number, angle: number) => {
        const x = box.x + (at.cx + Math.cos(angle) * at.r * share) * zoom;
        const y = box.y + (at.cy + Math.sin(angle) * at.r * share) * zoom;
        const reached = await page.evaluate(([px, py]) =>
          document.elementFromPoint(px, py)?.classList.contains("welcome-globe") ?? false, [x, y]);
        return reached ? { x, y } : null;
      };
      const cursor = async ({ x, y }: { x: number; y: number }) => {
        await page.mouse.move(x, y);
        return globe.evaluate((el) => (el as HTMLElement).style.cursor);
      };
      const on: { x: number; y: number }[] = [];
      for (const share of [0, 0.5, 0.9]) {
        for (const angle of [0, Math.PI / 4, Math.PI / 2, -Math.PI / 4, -Math.PI / 2]) {
          const p = await point(share, angle);
          if (p) on.push(p);
        }
      }
      const off: { x: number; y: number }[] = [];
      for (const angle of [Math.PI / 4, -Math.PI / 4, 0]) {
        const p = await point(1.08, angle);
        if (p) off.push(p);
      }
      expect(on.length, `points on the planet at ${width} x ${height}`).toBeGreaterThanOrEqual(8);
      expect(off.length, `points beside the planet at ${width} x ${height}`).toBeGreaterThanOrEqual(1);
      for (const p of on) expect(await cursor(p), `on the planet at ${width} x ${height}`).toBe("grab");
      for (const p of off) {
        await cursor(on[0]);
        expect(await cursor(p), `beside the planet at ${width} x ${height}`).toBe("");
      }
      await page.mouse.move(1, 1);
    }
  });

  test.describe("on a high-density screen", () => {
    test.use({ deviceScaleFactor: 2 });
    test("the planet is drawn at the screen's own density, magnified", async ({ page }) => {
      await installSetup(page);
      await page.setViewportSize({ width: 2160, height: 1350 });
      await page.goto("/welcome");
      await expect(page.getByRole("button", { name: "Tune the radar" })).toBeVisible();
      // One backing pixel per screen pixel: the page's density times its zoom.
      const sharp = async (factor: number, when: string) => {
        const zoom = await settledZoom(page);
        expect(zoom, when).toBeCloseTo(factor, 3);
        const off = () => page.locator("canvas.welcome-globe").evaluate((el: HTMLCanvasElement, z) => {
          if (devicePixelRatio !== 2) return Infinity;
          return Math.max(Math.abs(el.width - el.clientWidth * 2 * z), Math.abs(el.height - el.clientHeight * 2 * z));
        }, zoom);
        // The canvas's page size is read in whole pixels, so its backing size is
        // known to half a page pixel at the screen's density, and a pixel more
        // for the backing store's own rounding.
        await expect.poll(off, { message: when, timeout: 2_000 }).toBeLessThanOrEqual(zoom + 1);
      };
      await sharp(1.3, "opened magnified");
      // In proportion: the canvas keeps its own size and only the zoom changes.
      await page.setViewportSize({ width: 1440, height: 900 });
      await sharp(1, "made smaller in proportion");
      await page.setViewportSize({ width: 2160, height: 1350 });
      await sharp(1.3, "made larger in proportion");
    });
  });

  test("leaving setup draws the app at its plain size, the window's own height", async ({ page }) => {
    await installEveryRoute(page);
    await page.setViewportSize({ width: 2560, height: 1440 });
    for (const path of ["/", "/profile", "/settings"]) {
      await page.goto(path);
      await expect(page.locator(".app")).toBeVisible();
      await expect(page.locator(".app.in-setup")).toHaveCount(0);
      expect(await settledZoom(page), path).toBe(1);
    }
  });

  test("setup's answer, once given, leaves the board at its plain size", async ({ page }) => {
    await installSetup(page);
    await page.setViewportSize({ width: 2560, height: 1440 });
    await page.emulateMedia({ reducedMotion: "reduce" });
    await page.goto("/welcome");
    await page.getByRole("button", { name: "Tune the radar" }).click();
    await page.getByRole("button", { name: "No thanks" }).click();
    await expect(page.getByRole("heading", { name: "What kind of role are you looking for?" })).toBeVisible();
    expect(await settledZoom(page)).toBeCloseTo(1.3, 3);
    await page.getByRole("button", { name: "Set up later" }).click();
    await expect(page.locator(".app.in-setup")).toHaveCount(0);
    expect(await settledZoom(page)).toBe(1);
    const app = await page.locator(".app").boundingBox();
    expect(app!.height).toBeCloseTo(1440, 0);
  });

  test("a browser without zoom gets today's setup, not a corrected one", async ({ page }) => {
    await installSetup(page);
    await page.setViewportSize({ width: 2160, height: 1350 });
    await page.goto("/welcome");
    await expect(page.getByRole("button", { name: "Tune the radar" })).toBeVisible();
    await page.evaluate(() => {
      for (const sheet of document.styleSheets) {
        for (let i = sheet.cssRules.length - 1; i >= 0; i--) {
          const rule = sheet.cssRules[i];
          if (rule instanceof CSSSupportsRule && /zoom/.test(rule.conditionText)) sheet.deleteRule(i);
        }
      }
    });
    expect(await settledZoom(page)).toBe(1);
    const app = await page.locator(".app").boundingBox();
    expect(app!.height).toBeCloseTo(1350, 0);
    const pad = await page.locator(".main").evaluate((main) => getComputedStyle(main).getPropertyValue("--page-zoom").trim());
    expect(pad).toBe("");
  });

  test("every setup screen at 1.3 passes the accessibility scan", async ({ page }) => {
    test.setTimeout(180_000);
    await installSetup(page);
    await page.setViewportSize({ width: 2160, height: 1350 });
    const found: string[] = [];
    await walkSetup(page, async (screen) => {
      const { violations } = await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21aa", "wcag22aa"]).analyze();
      for (const v of violations) found.push(`${screen}: ${v.id} (${v.nodes.length})`);
    });
    expect(found).toEqual([]);
  });
}

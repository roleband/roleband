import type { Locator, Page } from "@playwright/test";
import { expect, test } from "./fixtures";
import {
  facetsFixture,
  hiringFixture,
  jobFixture,
  jobListFixture,
  levelGuideFixture,
  notificationsFixture,
  historyFixture, overviewFixture,
  statsFixture,
  statusFixture,
} from "../../src/test/fixtures";
import { msg } from "../../src/test/msg";
import { installJobDetailRoutes } from "./boardHarness";
import { showAdvancedInsights } from "./insightsView";

// The Statistics sub-tab lives in the path (`/statistics/:tab`) and the period in
// `?window=`, so the whole view is deep-linkable and shareable. These specs pin
// that: direct links, index redirect, push-on-tab, replace-on-window, invalid
// fallback, and reload persistence.

const velocityFixture = {
  days: 30,
  since: null,
  kpis: {
    open_total: 12, opened: 5, closed: 1, reposted: 0, first_scan: 0,
    median_days_open: 20, employer_dated_share: 0.5,
    median_observed_listing_duration_days: null, closed_sample: 1, closed_employer_dated_share: 1,
  },
  aging: [{ lo: 0, hi: 30, label: "0–30d", count: 8 }],
  posted: [{ lo: 0, hi: 30, label: "0–30d", count: 1 }],
  by_company: [
    { company: "google", open: 6, opened: 3, reposted: 0, closed: 1, median_days_open: 18, median_observed_listing_duration_days: null },
  ],
};

test.beforeEach(async ({ page }) => {
  await showAdvancedInsights(page);
  await page.route("/api/profile", (route) => route.fulfill({ json: {
    profile: null, scope_configured: true,
  } }));
  await page.route("/api/stats", (route) => route.fulfill({ json: statsFixture }));
  await page.route("/api/status", (route) => route.fulfill({ json: statusFixture }));
  await page.route("/api/facets", (route) => route.fulfill({ json: facetsFixture }));
  await page.route("/api/notifications**", (route) => route.fulfill({ json: notificationsFixture }));
  await page.route("/api/jobs/101", (route) => route.fulfill({ json: jobFixture }));
  await page.route("/api/jobs/*/similar**", (route) => route.fulfill({ json: { scope: "cross", items: [] } }));
  await page.route("/api/jobs?**", (route) => route.fulfill({ json: jobListFixture }));
  await page.route("/api/statistics/overview**", (route) => route.fulfill({ json: overviewFixture }));
  await page.route("/api/statistics/history**", (route) => route.fulfill({ json: historyFixture }));
  await page.route("/api/statistics/velocity**", (route) => route.fulfill({ json: velocityFixture }));
});

test("a direct link to a sub-tab renders it selected, with the breadcrumb", async ({ page }) => {
  await page.goto("/statistics/velocity");

  await expect(page).toHaveURL(/\/statistics\/velocity$/);
  await expect(page.getByRole("tab", { name: "Pace" })).toHaveAttribute("aria-selected", "true");
  await expect(page.getByRole("heading", { level: 2, name: "5 opened" })).toBeVisible();
  // The breadcrumb's second segment is derived from the route, not pushed imperatively.
  await expect(page.getByRole("banner", { name: msg("shell-topbar-aria") })).toContainText("Insights/Pace");
});

test("Pace's age bands name their clock and the share the employer dated", async ({ page, isMobile }) => {
  await page.goto("/statistics/velocity");
  const ages = page.locator(".panel").filter({ has: page.getByRole("heading", { name: "Age of open roles" }) });
  const note = ages.locator(".trends-note");
  await expect(note).toHaveText("Counted from when each role was first listed · 50% dated by the employer");
  // One line under the bands, like its neighbour's note, never wrapped to two.
  // A phone's narrow panel wraps any sentence, so the check is desktop's.
  if (isMobile) return;
  expect(await note.evaluate((el) => {
    const range = document.createRange();
    range.selectNodeContents(el);
    return new Set([...range.getClientRects()].map((rect) => Math.round(rect.top))).size;
  })).toBe(1);
});

test("the section index redirects to Overview", async ({ page }) => {
  await page.goto("/statistics");
  await expect(page).toHaveURL(/\/statistics\/overview$/);
  await expect(page.getByRole("tab", { name: "Overview" })).toHaveAttribute("aria-selected", "true");
  await expect(page.locator(".insight-hero .eyebrow")).toHaveText("Overview");
});

test("an unknown sub-tab falls back to Overview", async ({ page }) => {
  await page.goto("/statistics/bogus");
  await expect(page).toHaveURL(/\/statistics\/overview$/);
  await expect(page.getByRole("tab", { name: "Overview" })).toHaveAttribute("aria-selected", "true");
});

test("switching tabs pushes, so Back returns to the prior tab", async ({ page }) => {
  await page.goto("/statistics/overview");
  await page.getByRole("tab", { name: "Pace" }).click();
  await expect(page).toHaveURL(/\/statistics\/velocity$/);

  await page.goBack();
  await expect(page).toHaveURL(/\/statistics\/overview$/);
  await expect(page.getByRole("tab", { name: "Overview" })).toHaveAttribute("aria-selected", "true");
});

test("the window lens replaces, so it does not pollute the back button", async ({ page }) => {
  // Establish a real prior page (the board) before entering Statistics, so Back
  // has somewhere to return to.
  await page.goto("/");
  await page.goto("/statistics/overview");
  await expect(page).toHaveURL(/\/statistics\/overview$/);

  const period = page.getByRole("group", { name: "Time range" });
  await period.getByRole("button", { name: "90d" }).click();
  await expect(page).toHaveURL(/window=90/);
  await period.getByRole("button", { name: "7d" }).click();
  await expect(page).toHaveURL(/window=7/);

  // Each window change replaced the entry, so a single Back lands on the board —
  // not on window=90 then window=30.
  await page.goBack();
  await expect(page).toHaveURL(/\/$/);
});

test("a deep link with a window lens survives reload", async ({ page }) => {
  await page.goto("/statistics/overview?window=90");
  await expect(page.getByRole("button", { name: "90d" })).toHaveAttribute("aria-pressed", "true");

  await page.reload();
  await expect(page).toHaveURL(/\/statistics\/overview\?window=90$/);
  await expect(page.getByRole("tab", { name: "Overview" })).toHaveAttribute("aria-selected", "true");
  await expect(page.getByRole("button", { name: "90d" })).toHaveAttribute("aria-pressed", "true");
});

test("with six days of history there is no window to pick, and the figures say since when", async ({ page }) => {
  // Every window would show the figures of all time, so none is offered, and a
  // saved 30-day link reads the whole history and says where it starts.
  const since = "2026-11-03T06:02:00Z";
  await page.route("/api/statistics/history**", (route) => route.fulfill({ json: { since, days: 6 } }));
  await page.route("/api/statistics/overview**", (route) =>
    route.fulfill({ json: { ...overviewFixture, days: 0, since } }));
  const asked = page.waitForRequest((r) => r.url().includes("/api/statistics/overview?days=0"));
  await page.goto("/statistics/overview?window=30");

  await asked;
  const opened = page.locator(".insight-hero .kpi").filter({ hasText: "Opened" });
  await expect(opened).toContainText(/since \S+ \S+ \(\d+ days\)/);
  await expect(page.getByRole("group", { name: "Time range" })).toHaveCount(0);
  await expect(page.locator(".insight-hero .kpi").filter({ hasText: /^New/ })).toHaveCount(0);
  await expect(page.getByText(/last 30d|all time/)).toHaveCount(0);
});

/* Every tab opens with one hero whose eyebrow IS its tab label,
 * one level-2 figure, and two to four KPI tiles; nothing sits above it. */
test("every Insights tab opens with the same hero, named by its tab", async ({ page }) => {
  const summary = (p50: number) => ({ count: 4, min: p50 - 100_000, max: p50 + 200_000, p25: p50 - 50_000, p50, p75: p50 + 50_000, p90: p50 + 150_000 });
  const routes: Record<string, unknown> = {
    "/api/demand": hiringFixture,
    "/api/statistics/compensation**": {
      currency: "USD", min_roles: 5, coverage: { with_comp: 4, total_open: 12, pct: 0.333 }, overall: summary(500_000), histogram: [],
      by_level: [], by_company: [], by_family: [], by_skill: [],
      disclosed: { bands: [], reqs: 0, companies: 0, excluded: { unclear: 0, total: 0, not_usd: 0, not_yearly: 0, implausible: 0 }, truncated: false },
      disclosure: { overall: { open: 12, checked: 0, disclosed: 0, rate: null }, by_company: [], by_level: [] },
      base_estimates: { min_roles: 5, coverage: { with_base: 0, total_open: 12 }, overall: null, by_level: [], by_company: [], by_family: [] },
    },
    "/api/statistics/offer-terms": { feed_configured: false, companies: [] },
    "/api/profile/offer": { offer: null, valuations: {} },
    "/api/statistics/comp-trajectory": {
      currency: "USD",
      overall: { count: 3, median_tc: 600_000, base: 300_000, bonus: 60_000, equity: 240_000, equity_pct: 0.4,
                 sources: { base: "posted", bonus: "company_rule", equity: "estimated" } },
      public: [{ company: "google", ticker: "GOOGL", equity_vehicle: "rsu", vesting: null, count: 3, median_tc: 600_000, base: 300_000, bonus: 60_000, equity: 240_000, equity_pct: 0.4,
                 sources: { base: "posted", bonus: "company_rule", equity: "estimated" } }],
      private: [], choice: [], set_apart: [],
    },
    "/api/skills/top**": {
      items: [
        { term: "python", category: "language", job_count: 9, share: 0.3, market_share: 0.3, lift: 1, distinctiveness: 0 },
        { term: "sql", category: "language", job_count: 5, share: 0.17, market_share: 0.17, lift: 1, distinctiveness: 0 },
      ],
      competencies: [], roles: 30, market_roles: 30, narrowed: false,
    },
    "/api/statistics/levels": levelGuideFixture,
    "/api/companies/discovery": { sectors: [], companies: [] },
    "/api/settings": { enabled_role_tracks: [] },
  };
  for (const [pattern, json] of Object.entries(routes)) {
    await page.route(pattern, (route) => route.fulfill({ json }));
  }

  for (const tab of ["Overview", "Hiring", "Pace", "Compensation", "Levels", "Stock", "Skills"]) {
    await page.goto("/statistics/overview");
    await page.getByRole("tab", { name: tab, exact: true }).click();
    const hero = page.locator(".insight-hero");
    await expect(hero, tab).toHaveCount(1);
    await expect(hero.locator(".eyebrow"), tab).toHaveText(tab);
    await expect(hero.getByRole("heading", { level: 2 }), tab).toHaveCount(1);
    const tiles = await hero.locator(".kpi").count();
    // Skills keeps one tile, the roles its ranking reads; its lead skill is the figure.
    if (tab === "Skills") expect(tiles, tab).toBe(1);
    else {
      expect(tiles, tab).toBeGreaterThanOrEqual(2);
      expect(tiles, tab).toBeLessThanOrEqual(4);
    }
    // Nothing above it: the hero is the panel's first card.
    const first = await page.locator("#statistics-tabpanel .panel").first().evaluate((el) => el.classList.contains("insight-hero"));
    expect(first, tab).toBe(true);
  }
});

/* Levels is a long reference table: its toolbar and column heads stay in view
 * while the rows scroll under them, and a searched code translates. */
test("Levels keeps its search and column heads in view, and translates a searched code", async ({ page }) => {
  await page.route("/api/statistics/levels", (route) => route.fulfill({ json: levelGuideFixture }));
  await page.route("/api/companies/discovery", (route) => route.fulfill({ json: { sectors: [], companies: [] } }));
  await page.route("/api/settings", (route) => route.fulfill({ json: { enabled_role_tracks: [] } }));
  await page.setViewportSize({ width: 1440, height: 520 });
  await page.goto("/statistics/levels");

  const search = page.getByRole("searchbox", { name: "Company or level" });
  await search.fill("ICT4");
  await expect(page.getByRole("status").filter({ hasText: "Translating Apple ICT4 (Senior)" })).toBeVisible();
  await expect(page).toHaveURL(/[?&]q=ICT4/);

  // The table scrolls inside the app; the page itself never grows past the
  // window, or a scroll anywhere would slide the whole app up.
  expect(await page.evaluate(() => document.scrollingElement!.scrollHeight)).toBeLessThanOrEqual(520);
  // Scroll the app's own area, as a wheel or a swipe over the table does; a
  // wheel event does not exist on a touch device.
  await page.locator("main").evaluate((el) => el.scrollBy(0, 2000));
  await expect.poll(() => page.locator("main").evaluate((el) => el.scrollTop)).toBeGreaterThan(0);
  const head = page.getByRole("columnheader", { name: "Senior, translating" });
  await expect(search).toBeInViewport();
  await expect(head).toBeInViewport();
  // The heads sit under the toolbar, never behind it.
  const toolbar = await page.locator(".levels-toolbar").boundingBox();
  const cell = await head.boundingBox();
  expect(cell!.y).toBeGreaterThanOrEqual(toolbar!.y + toolbar!.height - 1);
});

/* One scope bar narrows every tab but Stock, and it travels with the
 * reader from tab to tab in the address, as the window does. */
test("a scope chosen on one tab narrows the next tab's request too", async ({ page }) => {
  await page.goto("/statistics/overview");
  const overview = page.waitForRequest((r) => r.url().includes("/api/statistics/overview") && r.url().includes("side=other"));
  await page.getByRole("group", { name: "Companies" }).getByRole("button", { name: "Other companies" }).click();
  await overview;

  const pace = page.waitForRequest((r) => r.url().includes("/api/statistics/velocity") && r.url().includes("side=other"));
  await page.getByRole("tab", { name: "Pace", exact: true }).click();
  await pace;
  await expect(page).toHaveURL(/\/statistics\/velocity\?.*side=other/);
  await expect(page.getByRole("button", { name: "Other companies" })).toHaveAttribute("aria-pressed", "true");
});

/* A panel opened again paints the answer it last had while it asks again, so
 * coming back to a tab never shows a spinner for something already seen. The
 * second read is held until the panel has been checked: what shows meanwhile
 * can only be the kept answer. */
test.describe("a tab opened again", () => {
  async function holdPace(page: Page) {
    let release!: () => void;
    const held = new Promise<void>((resolve) => { release = resolve; });
    const asked: string[] = [];
    await page.route("/api/statistics/velocity**", async (route) => {
      asked.push(route.request().url());
      await held;
      await route.fulfill({ json: { ...velocityFixture, kpis: { ...velocityFixture.kpis, opened: 6 } } });
    });
    return { asked, release };
  }

  test("paints its last answer from another tab, then the fresh one", async ({ page }) => {
    await page.goto("/statistics/velocity");
    await expect(page.getByRole("heading", { level: 2, name: "5 opened" })).toBeVisible();
    await page.getByRole("tab", { name: "Overview" }).click();
    await expect(page.locator(".insight-hero .eyebrow")).toHaveText("Overview");

    const pace = await holdPace(page);
    await page.getByRole("tab", { name: "Pace" }).click();
    await expect(page.getByRole("heading", { level: 2, name: "5 opened" })).toBeVisible();
    await expect.poll(() => pace.asked.length).toBeGreaterThan(0);

    pace.release();
    await expect(page.getByRole("heading", { level: 2, name: "6 opened" })).toBeVisible();
  });

  test("paints its last answer after a visit to another screen", async ({ page }) => {
    await page.goto("/statistics/velocity");
    await expect(page.getByRole("heading", { level: 2, name: "5 opened" })).toBeVisible();
    await page.getByRole("link", { name: "Radar", exact: true }).click();
    await expect(page.getByRole("heading", { name: "Radar", level: 1 })).toBeVisible();

    const pace = await holdPace(page);
    await page.goBack();
    await expect(page.getByRole("heading", { level: 2, name: "5 opened" })).toBeVisible();
    await expect.poll(() => pace.asked.length).toBeGreaterThan(0);
    pace.release();
    await expect(page.getByRole("heading", { level: 2, name: "6 opened" })).toBeVisible();
  });

  /** Leave Pace for the Radar, open a role there, act on it, and come back. */
  async function openARoleAndReturn(page: Page, act: (role: Locator) => Promise<void>) {
    await installJobDetailRoutes(page);
    await page.goto("/statistics/velocity");
    await expect(page.getByRole("heading", { level: 2, name: "5 opened" })).toBeVisible();
    await page.getByRole("link", { name: "Radar", exact: true }).click();
    const viewed = page.waitForResponse((r) => r.url().endsWith("/api/jobs/101/view"));
    await page.getByRole("article").filter({ hasText: "Staff Product Manager, API" })
      .getByText("Staff Product Manager, API").click();
    const role = page.getByRole("dialog", { name: /^Role:/ });
    await expect(role).toBeVisible();
    await viewed;
    await act(role);
    await role.getByRole("button", { name: "Back" }).click();
    await expect(role).toHaveCount(0);

    const pace = await holdPace(page);
    await page.goBack();
    await expect(page.getByRole("tab", { name: "Pace" })).toHaveAttribute("aria-selected", "true");
    await expect.poll(() => pace.asked.length).toBeGreaterThan(0);
    return pace;
  }

  test("paints its last answer after a role is opened, which only marks it viewed", async ({ page }) => {
    const pace = await openARoleAndReturn(page, async () => {});
    await expect(page.getByRole("heading", { level: 2, name: "5 opened" })).toBeVisible();
    pace.release();
    await expect(page.getByRole("heading", { level: 2, name: "6 opened" })).toBeVisible();
  });

  test("shows no answer after a role is saved, which may change it", async ({ page }) => {
    await page.route("/api/jobs/101/favorite", (route) => route.fulfill({ json: { job_id: 101, is_favorite: true } }));
    const pace = await openARoleAndReturn(page, async (role) => {
      const saved = page.waitForResponse((r) => r.url().endsWith("/api/jobs/101/favorite"));
      await role.getByRole("button", { name: msg("jobs-save") }).click();
      await saved;
    });
    await expect(page.getByRole("heading", { level: 2, name: /opened/ })).toHaveCount(0);
    pace.release();
    await expect(page.getByRole("heading", { level: 2, name: "6 opened" })).toBeVisible();
  });

  test("a first visit with the read held shows no answer", async ({ page }) => {
    const pace = await holdPace(page);
    await page.goto("/statistics/velocity");
    await expect.poll(() => pace.asked.length).toBeGreaterThan(0);
    await expect(page.getByRole("heading", { level: 2, name: /opened/ })).toHaveCount(0);
    pace.release();
    await expect(page.getByRole("heading", { level: 2, name: "6 opened" })).toBeVisible();
  });
});

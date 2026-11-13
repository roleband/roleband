import { expect, mockGet, test } from "./fixtures";
import { showAdvancedInsights } from "./insightsView";
import { msg } from "../../src/test/msg";
import {
  facetsFixture,
  jobFixture,
  jobListFixture,
  notificationsFixture,
  historyFixture, overviewFixture,
  statsFixture,
  statusFixture,
} from "../../src/test/fixtures";

// Compensation sub-tab. Two different quantities live here and must stay apart:
// the base salary employers post, which the tab leads with, per country and
// level in the country's own currency, and the estimate (a lookup of US pay,
// few distinct values), which every panel built from it names as such.

const level = (level_band: string, low: number | null, high: number | null, ranges: number, employers: number, roles: number) => ({
  level_band, ranges, employers, roles, enough: low != null, low, high,
  mid_p25: low == null ? null : low + 10_000, mid_p75: high == null ? null : high - 10_000,
});

const postedFixture = (over: Record<string, unknown> = {}) => ({
  min_employers: 5,
  min_ranges: 8,
  default_country: "US",
  your_levels: ["principal", "director_plus"],
  excluded: { not_base: 90, not_yearly: 3, implausible: 1, no_country: 4, placed_by_pay: 6, without_country: 5 },
  countries: [
    {
      country: "US", currency: "USD", ranges: 3, yours: true,
      levels: [level("staff", 230_000, 330_000, 9, 6, 40), level("principal", 198_000, 270_000, 241, 141, 600)],
      not_placed: { roles: 37, ranges: 12 }, other_currency: 2,
      excluded: { not_base: 80, not_yearly: 3, implausible: 1, placed_by_pay: 6 },
      bands: [
        { company: "google", level_band: "staff", low: 262_000, high: 365_000, reqs: 18 },
        { company: "google-deepmind", level_band: "staff", low: 207_000, high: 301_000, reqs: 1 },
        { company: "google", level_band: "principal", low: 240_000, high: 334_000, reqs: 12 },
      ],
    },
    {
      country: "GB", currency: "GBP", ranges: 1, yours: false,
      levels: [level("principal", null, null, 1, 1, 2)],
      not_placed: { roles: 0, ranges: 0 }, other_currency: 0,
      excluded: { not_base: 10, not_yearly: 0, implausible: 0, placed_by_pay: 0 },
      bands: [{ company: "google-deepmind", level_band: "principal", low: 110_000, high: 150_000, reqs: 2 }],
    },
    {
      country: "SE", currency: null, ranges: 0, yours: true, levels: [],
      not_placed: { roles: 0, ranges: 0 }, other_currency: 0, bands: [],
      excluded: { not_base: 0, not_yearly: 0, implausible: 0, placed_by_pay: 0 },
    },
  ],
  ...over,
});

const compFixture = (over: Record<string, unknown> = {}) => ({
  posted: postedFixture(),
  // 749 open, 600 read by the disclosure pass, 150 of those stating a range. The
  // gap between 749 and 600 is our extraction backlog, not employer silence, and
  // the panel has to say which is which.
  disclosure: {
    overall: { open: 749, checked: 600, disclosed: 150, rate: 0.25 },
    by_level: [
      { level_band: "senior", open: 406, checked: 400, disclosed: 100, rate: 0.25 },
      { level_band: "staff", open: 265, checked: 200, disclosed: 50, rate: 0.25 },
      { level_band: "unstated", open: 300, checked: 250, disclosed: 90, rate: 0.36 },
    ],
  },
  ...over,
});

/** A message's text as a regular expression, for a name match. */
const escape = (text: string) => text.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");

const tableRow = (company: string, over: Record<string, unknown> = {}) => ({
  company, followed_as_set: false, open_roles: 2, posting: 2, checked: 2, currency: "USD",
  low: 250_000, high: 320_000, ranges: [{ low: 250_000, high: 320_000, roles: 2 }],
  other_currency: false, reason: null, estimate_base: null, estimate_total: null, equity: null,
  ...over,
});

const tableFixture = (over: Record<string, unknown> = {}) => ({
  country: "US", level_band: "principal", currency: "USD", skill: null, estimates: true,
  rows: [
    tableRow("google", { open_roles: 4, posting: 3, checked: 4, low: 262_000, high: 365_000,
      ranges: [{ low: 262_000, high: 365_000, roles: 3 }],
      equity: { vehicle: "rsu", vesting: "25/25/25/25", rule: null } }),
    tableRow("apple", { low: null, high: null, ranges: [], currency: null, posting: 0, reason: "total",
      estimate_total: { low: 900_000, high: 900_000, rung: "ICT6" } }),
    tableRow("netflix", { low: null, high: null, ranges: [], currency: null, posting: 0, reason: "none",
      equity: { vehicle: "cash_election", vesting: null, rule: "employee_election" } }),
  ],
  not_placed: [{ company: "apple", roles: 299 }],
  skills: [{ term: "python", roles: 8 }],
  min_skill_roles: 3,
  by_discipline: {
    min_employers: 5, min_ranges: 8, max_employer_share: 0.4,
    disciplines: [
      { family: "product_management", picked: false, ranges: 10, employers: 5, roles: 40, enough: true,
        low: 245_000, high: 325_000, mid_p25: 262_500, mid_p75: 307_500, top_share: 0.2, withheld: null },
      { family: "data_science", picked: false, ranges: 4, employers: 3, roles: 9, enough: false,
        low: null, high: null, mid_p25: null, mid_p75: null, top_share: 0.5, withheld: "too_few" },
    ],
  },
  ...over,
});

test.beforeEach(async ({ page }) => {
  await showAdvancedInsights(page);
  await page.route("/api/statistics/overview**", (route) =>
    route.fulfill({ json: overviewFixture }));
  await mockGet(page, "/api/statistics/history**", (route) => route.fulfill({ json: historyFixture }));
  await page.route("/api/stats", (route) => route.fulfill({ json: statsFixture }));
  await page.route("/api/status", (route) => route.fulfill({ json: statusFixture }));
  await page.route("/api/facets", (route) => route.fulfill({ json: facetsFixture }));
  await page.route("/api/notifications**", (route) => route.fulfill({ json: notificationsFixture }));
  await page.route("/api/jobs/*/similar**", (route) => route.fulfill({ json: { scope: "cross", items: [] } }));
  await page.route("/api/jobs/101", (route) => route.fulfill({ json: jobFixture }));
  await page.route("/api/jobs?**", (route) => route.fulfill({ json: jobListFixture }));
  await page.route("/api/statistics/compensation**", (route) => route.fulfill({ json: compFixture() }));
  await mockGet(page, "/api/statistics/pay-table**", (route) => route.fulfill({ json: tableFixture() }));
});

test("opens on what employers post at the person's level, apart from the estimate", async ({ page }) => {
  const errors: string[] = [];
  page.on("console", (m) => m.type() === "error" && errors.push(m.text()));

  await page.goto("/statistics");
  await page.getByRole("tab", { name: "Compensation" }).click();

  // The answer leads the tab, as on every Insights tab: posted base salary at
  // the person's own level, never the estimate's median.
  const hero = page.locator(".insight-hero");
  await expect(hero.locator(".eyebrow")).toHaveText("Compensation");
  await expect(hero.getByRole("heading", { level: 2 })).toHaveText(msg("insights-posted-typically", { low: "$198K", high: "$270K" }));
  await expect(hero).toContainText(
    msg("insights-posted-line", { level: "Principal", country: "United States", ranges: 241, employers: 141, roles: 600 }),
  );
  await expect(hero.locator(".kpi", { hasText: msg("insights-posted-middle-half") })).toContainText("$208K–$260K");
  await expect(hero.locator(".kpi", { hasText: msg("insights-posted-share") })).toContainText("25%");
  // The estimate's median ($479K overall) is no headline; it stays in the estimate panels.
  await expect(hero).not.toContainText("$479K");
  const readTip = page.getByRole("button", { name: msg("insights-posted-how-read") });
  await readTip.hover();
  await expect(page.getByRole("tooltip").filter({ hasText: msg("insights-posted-how-read-body") })).toBeVisible();

  // Every level of the country, and the roles with no placed level said apart, never as a row.
  const byLevel = page.getByRole("region", { name: msg("insights-posted-by-level", { country: "United States" }) });
  await expect(byLevel.getByRole("listitem")).toHaveCount(3);
  await expect(byLevel.getByRole("listitem").last()).toContainText("Director+");
  await expect(byLevel.getByRole("listitem").last()).toContainText(msg("insights-posted-none"));
  await expect(byLevel).toContainText(msg("insights-posted-not-placed", { roles: 37, ranges: 12 }));
  await expect(byLevel.getByRole("listitem").filter({ hasText: /not placed/i })).toHaveCount(0);

  // No panel aggregates the estimate: each company's own is its table row.
  await expect(page.getByText(msg("insights-compensation-panel-top-paying-companies"))).toHaveCount(0);
  await expect(page.getByText(msg("insights-compensation-panel-median-comp-by-level"))).toHaveCount(0);
  expect(errors).toEqual([]);
});

test("switches country in the country's own currency, and names a country with nothing posted", async ({ page }) => {
  await page.goto("/statistics/compensation");
  const heading = page.locator(".insight-hero").getByRole("heading", { level: 2 });
  await expect(heading).toHaveText(msg("insights-posted-typically", { low: "$198K", high: "$270K" }));

  const country = page.getByRole("combobox", { name: msg("insights-posted-country") });
  await country.selectOption("GB");
  // One range from one employer: counts, and why there is no figure, never a figure.
  await expect(heading).toHaveText(msg("insights-posted-too-few"));
  await expect(page.locator(".insight-hero")).toContainText(msg("insights-posted-needs", { min_employers: 5, min_ranges: 8 }));
  await expect(page).toHaveURL(/country=GB/);

  await expect(country.locator("option", { hasText: msg("insights-posted-your-place", { name: "Sweden" }) })).toHaveCount(1);
  await country.selectOption("SE");
  await expect(heading).toHaveText(msg("insights-posted-none"));
  await expect(page.getByText(msg("insights-posted-none-in-country", { country: "Sweden" }))).toBeVisible();
});

test("a level picked is kept in the link and survives a reload", async ({ page }) => {
  await page.goto("/statistics/compensation");
  const heading = page.locator(".insight-hero").getByRole("heading", { level: 2 });
  await expect(heading).toHaveText(msg("insights-posted-typically", { low: "$198K", high: "$270K" }));

  await page.getByRole("combobox", { name: msg("insights-posted-level") }).selectOption("staff");
  await expect(heading).toHaveText(msg("insights-posted-typically", { low: "$230K", high: "$330K" }));
  await expect(page).toHaveURL(/level=staff/);

  await page.reload();
  await expect(heading).toHaveText(msg("insights-posted-typically", { low: "$230K", high: "$330K" }));
  await expect(page.getByRole("combobox", { name: msg("insights-posted-level") })).toHaveValue("staff");
});

test("draws every posted range a row per level, and colours only the employer picked", async ({ page }) => {
  const errors: string[] = [];
  page.on("console", (m) => m.type() === "error" && errors.push(m.text()));
  await page.goto("/statistics/compensation");

  const rows = page.getByRole("list", { name: msg("insights-pay-bands-published-base-salary-bands-by") });
  await expect(rows.getByRole("listitem")).toHaveCount(2);
  const staff = rows.getByRole("img", {
    name: msg("insights-comp-bands-level-ranges", { label: "Staff", bands: 2, employers: 2, figure: "some", low: "$230K", high: "$330K" }),
  });
  await expect(staff.locator(".pay-band[data-chosen]")).toHaveCount(0);
  // Every reason a role is left out is available from the heading.
  const about = page.getByRole("button", { name: msg("insights-compensation-panel-about-published-salary-bands") });
  await about.focus();
  await expect(page.getByRole("tooltip").filter({ hasText: msg("insights-comp-bands-placed-by-pay", { count: 6 }) })).toBeVisible();

  // Picking an employer is the only colour on the chart, and it is drawn where its range is.
  await page.locator(".pay-bands-pick").getByRole("button", { name: /^Filter by/ }).click();
  await page.getByRole("option", { name: /Google DeepMind/ }).click();
  await expect(staff).toHaveAttribute("aria-label", /Google DeepMind: \$207K to \$301K/);
  const picked = staff.locator(".pay-band[data-chosen]");
  await expect(picked).toHaveCount(1);
  const track = await staff.boundingBox();
  const bar = await picked.boundingBox();
  expect(track && bar && bar.x >= track.x && bar.x + bar.width <= track.x + track.width + 1).toBe(true);
  await expect(rows.getByRole("img", { name: /^Principal/ })).toHaveAttribute("aria-label", /posts no range/);
  expect(errors).toEqual([]);
});

test("the posted ranges chart follows the country, in its currency", async ({ page }) => {
  await page.goto("/statistics/compensation?country=GB");
  const rows = page.getByRole("list", { name: msg("insights-pay-bands-published-base-salary-bands-by") });
  await expect(rows.getByRole("img", {
    name: msg("insights-comp-bands-level-ranges", { label: "Principal", bands: 1, employers: 1, figure: "none", low: "", high: "" }),
  })).toBeVisible();
  await expect(page.locator(".pay-bands-axis")).toContainText("£");
  await expect(page.locator(".pay-bands-axis")).not.toContainText("$");
});

test("reports the disclosure rate against checked roles and names the backlog", async ({ page }) => {
  const errors: string[] = [];
  page.on("console", (m) => m.type() === "error" && errors.push(m.text()));

  await page.goto("/statistics");
  await page.getByRole("tab", { name: "Compensation" }).click();

  // 150 of 600 CHECKED roles, not 150 of 749 open ones. The 20% that the wrong
  // denominator would produce is our own extraction queue showing up as employer
  // behaviour, so the headline and the note must both be present.
  await expect(page.locator(".chart-insight", { hasText: /25% of 600 checked roles post a range/ })).toBeVisible();
  await expect(page.getByText(/149 of 749 open roles haven't been checked/i)).toBeVisible();

  // Who states pay is by level; a role whose level we cannot place has its own
  // row, never a rung's. Each company's own share is its table row instead.
  const byLevel = page.getByRole("img", { name: /post a range, by level/i });
  await expect(byLevel).toBeVisible();
  await expect(byLevel.getByText("Level unknown")).toBeVisible();
  await expect(byLevel.getByText(/^unstated$/)).toHaveCount(0);
  await expect(page.getByRole("group", { name: "Pay transparency breakdown" })).toHaveCount(0);

  expect(errors).toEqual([]);
});

test("Pay has no window and draws no pay over time; who posts a range stays", async ({ page }) => {
  // The daily pay snapshots began counting a role listed in several places
  // once, so a line across that day would read the change as a market move.
  // The trend routes are left unmocked: a request to either fails the test.
  const asked: string[] = [];
  page.on("request", (r) => {
    if (r.url().includes("/api/statistics/")) asked.push(new URL(r.url()).pathname);
  });
  await page.goto("/statistics/compensation?window=7");
  await expect(page.locator(".insight-hero").getByRole("heading", { level: 2 }))
    .toHaveText(msg("insights-posted-typically", { low: "$198K", high: "$270K" }));
  await expect(page.getByRole("img", { name: /post a range, by level/i })).toBeVisible();

  await expect(page.getByRole("group", { name: "Time range" })).toHaveCount(0);
  await expect(page.getByRole("img", { name: /over time/i })).toHaveCount(0);
  expect(asked.filter((path) => /trends/.test(path))).toEqual([]);
});

test("the company table leads with each company's posted range at the picked level", async ({ page }) => {
  const errors: string[] = [];
  page.on("console", (m) => m.type() === "error" && errors.push(m.text()));
  await page.goto("/statistics/compensation");

  const table = page.getByRole("region", {
    name: msg("insights-pay-table-heading", { level: "Principal", country: "United States" }),
  });
  await expect(table).toBeVisible();
  const google = table.getByRole("row", { name: /Google/ });
  await expect(google).toContainText("$262K–$365K");
  await expect(google).toContainText(msg("insights-pay-table-some-roles", { posting: 3, roles: 4 }));
  // Equity is what the employer states, never a share we estimate.
  await expect(google).toContainText("RSUs");
  await expect(google).toContainText(msg("insights-stock-trajectory-panel-vests", { schedule: "25/25/25/25" }));
  await expect(table.getByText("%")).toHaveCount(0);

  // A company that posts total compensation says so, and its estimate stands
  // in the estimate column alone.
  const apple = table.getByRole("row", { name: /Apple/ });
  await expect(apple).toContainText(msg("insights-pay-table-total"));
  await expect(apple).toContainText("$900K");
  // Roles with no placed level are counted below the table, never as a row.
  await expect(table).toContainText(msg("insights-pay-table-not-placed", { roles: 299, companies: 1 }));

  // The company name opens the board narrowed to it.
  await expect(table.getByRole("link", { name: "Google" })).toHaveAttribute("href", "/?company=google");
  expect(errors).toEqual([]);
});

test("the table follows the level picker and the skill filter, and the skill rides the link", async ({ page }) => {
  const asked: string[] = [];
  await mockGet(page, "/api/statistics/pay-table**", (route) => {
    asked.push(new URL(route.request().url()).search);
    return route.fulfill({ json: tableFixture() });
  });
  await page.goto("/statistics/compensation");
  await expect(page.getByRole("heading", { level: 3, name: new RegExp(escape(msg("insights-pay-table-heading", { level: "Principal", country: "United States" }))) })).toBeVisible();

  await page.getByRole("combobox", { name: msg("insights-posted-level") }).selectOption("staff");
  await expect.poll(() => asked.some((q) => q.includes("level=staff"))).toBe(true);

  await page.locator(".chart-head-controls").getByRole("button", { name: /^Filter by/ }).click();
  await page.getByRole("option", { name: /Python/ }).click();
  await expect(page).toHaveURL(/skill=python/);
  await expect.poll(() => asked.some((q) => q.includes("skill=python"))).toBe(true);

  // A new level answers its own skills, so the skill leaves the link.
  await page.getByRole("combobox", { name: msg("insights-posted-level") }).selectOption("principal");
  await expect(page).not.toHaveURL(/skill=/);
});

test("pay by discipline stays in the advanced view and withholds what one employer fills", async ({ page }) => {
  await page.goto("/statistics/compensation");
  const heading = msg("insights-pay-discipline-heading", { level: "Principal", country: "United States" });
  await expect(page.getByRole("region", { name: heading })).toBeVisible();

  const panel = page.getByRole("region", { name: heading });
  await expect(panel.getByRole("listitem")).toHaveCount(1);
  await expect(panel).toContainText("$245K–$325K");
  await expect(panel).toContainText(msg("insights-pay-discipline-too-few", { families: "Data Science & Analytics" }));
  await expect(panel).toContainText(msg("insights-pay-discipline-note"));
});

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

const summary = (p50: number, count: number) => ({
  count,
  min: 298_053,
  max: 1_500_000,
  p25: p50 - 40_000,
  p50,
  p75: p50 + 80_000,
  p90: p50 + 200_000,
});

const level = (level_band: string, low: number | null, high: number | null, ranges: number, employers: number, roles: number) => ({
  level_band, ranges, employers, roles, enough: low != null, low, high,
  mid_p25: low == null ? null : low + 10_000, mid_p75: high == null ? null : high - 10_000,
});

const postedFixture = (over: Record<string, unknown> = {}) => ({
  min_employers: 5,
  min_ranges: 8,
  default_country: "US",
  your_levels: ["principal", "director_plus"],
  excluded: { not_base: 90, not_yearly: 3, implausible: 1, no_country: 4, placed_by_pay: 6 },
  countries: [
    {
      country: "US", currency: "USD", ranges: 3, yours: true,
      levels: [level("staff", 230_000, 330_000, 9, 6, 40), level("principal", 198_000, 270_000, 241, 141, 600)],
      not_placed: { roles: 37, ranges: 12 }, other_currency: 2,
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
      bands: [{ company: "google-deepmind", level_band: "principal", low: 110_000, high: 150_000, reqs: 2 }],
    },
    {
      country: "SE", currency: null, ranges: 0, yours: true, levels: [],
      not_placed: { roles: 0, ranges: 0 }, other_currency: 0, bands: [],
    },
  ],
  ...over,
});

const compFixture = (over: Record<string, unknown> = {}) => ({
  currency: "USD",
  min_roles: 5,
  coverage: { with_comp: 732, total_open: 749, pct: 0.977 },
  overall: summary(479_251, 732),
  by_level: [
    { level_band: "senior", ...summary(306_217, 406) },
    { level_band: "staff", ...summary(644_468, 265) },
  ],
  by_company: [{ company: "openai", ...summary(900_000, 58) }],
  by_family: [{ family: "software_engineering", ...summary(479_251, 400) }],
  posted: postedFixture(),
  base_estimates: { min_roles: 5, coverage: { with_base: 0, total_open: 749 }, overall: null, by_level: [], by_company: [], by_family: [] },
  // 749 open, 600 read by the disclosure pass, 150 of those stating a range. The
  // gap between 749 and 600 is our extraction backlog, not employer silence, and
  // the panel has to say which is which.
  disclosure: {
    overall: { open: 749, checked: 600, disclosed: 150, rate: 0.25 },
    by_company: [
      { company: "google", open: 200, checked: 200, disclosed: 160, rate: 0.8 },
      { company: "openai", open: 60, checked: 50, disclosed: 5, rate: 0.1 },
      { company: "netflix", open: 40, checked: 0, disclosed: 0, rate: null },
    ],
    by_level: [
      { level_band: "senior", open: 406, checked: 400, disclosed: 100, rate: 0.25 },
      { level_band: "staff", open: 265, checked: 200, disclosed: 50, rate: 0.25 },
      { level_band: "unstated", open: 300, checked: 250, disclosed: 90, rate: 0.36 },
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
  await expect(hero.getByRole("heading", { level: 2 })).toHaveText("Typically $198K to $270K");
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

  // Every estimate panel says it is one, of US pay.
  for (const heading of ["Median estimated total compensation by level", "Top-paying companies"]) {
    const panel = page.locator(".panel", { has: page.getByRole("heading", { level: 3, name: heading }) });
    await expect(panel.locator(".eyebrow")).toHaveText(msg("insights-posted-estimate-us-only"));
  }
  await expect(page.locator(".comp-row", { hasText: "OpenAI" })).toContainText("58 roles");
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

  // Who states pay opens by level; a role whose level we cannot place has its own row, never a rung's.
  const byLevel = page.getByRole("img", { name: /post a range, by level/i });
  await expect(byLevel).toBeVisible();
  await expect(byLevel.getByText("Level unknown")).toBeVisible();
  await expect(byLevel.getByText(/^unstated$/)).toHaveCount(0);

  await page.getByRole("group", { name: "Pay transparency breakdown" }).getByRole("button", { name: "By company" }).click();
  const rateChart = page.getByRole("img", { name: /post a range, by company/i });
  await expect(rateChart).toBeVisible();
  await expect(rateChart.getByText("80% · 160/200")).toBeVisible();
  // Netflix has nothing checked; it must not be drawn as a 0% employer.
  await expect(rateChart.getByText("Netflix")).toHaveCount(0);

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

test("a fresh install's base-only roles have their own panel, apart from the totals", async ({ page }) => {
  // RoleBand's data prices these by their base
  // alone. They are counted, labelled and charted apart: never on the totals' axis.
  await page.route("/api/statistics/compensation**", (route) => route.fulfill({ json: compFixture({
    base_estimates: {
      min_roles: 5, coverage: { with_base: 40, total_open: 789 }, overall: summary(210_000, 40),
      by_level: [{ level_band: "senior", ...summary(196_000, 25) }, { level_band: "staff", ...summary(247_000, 15) }],
      by_company: [], by_family: [],
    },
  }) }));
  await page.goto("/statistics");
  await page.getByRole("tab", { name: "Compensation" }).click();

  const panel = page.getByRole("region", { name: "Estimated base salary by level" });
  await expect(panel).toBeVisible();
  await expect(panel).toContainText("40 more roles have only a base salary estimate");
  await expect(panel).toContainText("$196K");
  await expect(panel.locator(".eyebrow")).toHaveText(msg("insights-posted-estimate-us-only"));
  // The totals' level chart is the totals' alone.
  const totals = page.locator(".panel", { has: page.getByRole("heading", { level: 3, name: "Median estimated total compensation by level" }) });
  await expect(totals).not.toContainText("$196K");
});

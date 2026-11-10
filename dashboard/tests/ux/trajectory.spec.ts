import { msg } from "../../src/test/msg";
import { expect, test } from "./fixtures";
import { showAdvancedInsights } from "./insightsView";
import {
  facetsFixture,
  jobFixture,
  jobListFixture,
  notificationsFixture,
  overviewFixture,
  statsFixture,
  statusFixture,
} from "../../src/test/fixtures";

// Stock sub-tab: the slider re-prices the equity part of a public package
// while base and bonus stay fixed; private companies are held out as
// illiquid; a cash-or-equity company is a total with no split; roles with no
// split are counted apart. Mirrors the /api/statistics/comp-trajectory shape.
const estimated = { base: "estimated", bonus: "estimated", equity: "estimated" } as const;
const trajectoryFixture = {
  currency: "USD",
  // base 430k + bonus 120k + equity 450k
  overall: { count: 30, median_tc: 1_000_000, base: 430_000, bonus: 120_000, equity: 450_000, equity_pct: 0.45, sources: estimated },
  public: [
    { company: "google", ticker: "GOOGL", equity_vehicle: "rsu", vesting: "38/32/20/10", count: 20, median_tc: 1_000_000, base: 380_000, bonus: 120_000, equity: 500_000, equity_pct: 0.5,
      sources: { base: "posted", bonus: "company_rule", equity: "measured" } },
    { company: "microsoft", ticker: "MSFT", equity_vehicle: null, vesting: "25/25/25/25", count: 10, median_tc: 700_000, base: 476_000, bonus: 84_000, equity: 140_000, equity_pct: 0.2, sources: estimated },
  ],
  private: [
    { company: "openai", equity_vehicle: "options", vesting: null, count: 15, median_tc: 1_100_000, base: 550_000, bonus: 0, equity: 550_000, equity_pct: 0.5,
      sources: { base: "posted", bonus: "company_rule", equity: "estimated" } },
  ],
  choice: [{ company: "netflix", ticker: "NFLX", count: 4, median_tc: 756_250, total_source: "posted" }],
  set_apart: [{ reason: "not_us_pay", count: 5 }, { reason: "level_unplaced", count: 2 }],
};

test.beforeEach(async ({ page }) => {
  await showAdvancedInsights(page);
  await page.route("/api/statistics/overview**", (route) => route.fulfill({ json: overviewFixture }));
  await page.route("/api/profile", (route) => route.fulfill({ json: {
    profile: null, scope_configured: true,
  } }));
  await page.route("/api/stats", (route) => route.fulfill({ json: statsFixture }));
  await page.route("/api/status", (route) => route.fulfill({ json: statusFixture }));
  await page.route("/api/facets", (route) => route.fulfill({ json: facetsFixture }));
  await page.route("/api/notifications**", (route) => route.fulfill({ json: notificationsFixture }));
  await page.route("/api/jobs/*/similar**", (route) => route.fulfill({ json: { scope: "cross", items: [] } }));
  await page.route("/api/jobs/101", (route) => route.fulfill({ json: jobFixture }));
  await page.route("/api/jobs?**", (route) => route.fulfill({ json: jobListFixture }));
  await page.route("/api/statistics/comp-trajectory", (route) =>
    route.fulfill({ json: trajectoryFixture }),
  );
});

test("the Trajectory sub-tab re-prices total comp as the stock scenario moves", async ({ page }) => {
  await page.goto("/statistics");

  // Open the Trajectory sub-tab.
  await page.getByRole("tab", { name: "Stock" }).click();

  // Baseline: at today's price the projection is today's median, so the
  // headline is what moves with the price, the equity share.
  const hero = page.locator(".traj-cockpit h2");
  await expect(hero).toHaveText("45% of total compensation is equity");

  const slider = page.getByLabel("Stock price change percent");
  await expect(slider).toHaveValue("0");
  // At today's price the chart is a sensitivity view, never a chart of zeros.
  await expect(page.getByText("Per 10% stock move · adjust above for a scenario")).toBeVisible();
  const shock = page.getByRole("img", { name: "Equity impact by company" });
  await expect(shock).toContainText(/\+\$50K/);
  await expect(page.getByRole("group", { name: "Time range" })).toHaveCount(0);

  // Public companies render with their tickers and today's comp.
  const googleRow = page.getByRole("row", { name: /Google/ });
  await expect(googleRow).toContainText("GOOGL");
  await expect(googleRow).toContainText("$1M");

  // Private companies are held out as illiquid; the rationale stays one focus away.
  const privateTip = page.getByRole("button", { name: "Why private companies do not move" });
  await privateTip.focus();
  await expect(page.getByRole("tooltip").filter({ hasText: /Private-company equity has no daily price/i })).toBeVisible();
  await expect(page.getByRole("row", { name: /OpenAI/ })).toContainText("$1.10M");

  // Drive the stock up +100%: only the equity slice moves.
  await slider.fill("100");
  await expect(hero).toHaveText(/\$1\.45M projected TC/);
  // Google's fatter equity part (500k) gains more than Microsoft's thin one (140k).
  await expect(page.getByRole("row", { name: /Google/ })).toContainText("$1.50M");
  await expect(page.getByRole("row", { name: /Microsoft/ })).toContainText("$840K");
  // Netflix's people pick their own cash and equity mix: no price moves its total.
  await expect(page.getByRole("row", { name: /Netflix/ })).toContainText("$756K");
  // Private OpenAI is unaffected by the public-stock scenario.
  await expect(page.getByRole("row", { name: /OpenAI/ })).toContainText("$1.10M");

  // Drive it down: total comp falls below today.
  await slider.fill("-50");
  await expect(hero).toHaveText(/\$775K projected TC/);
  await expect(page.getByRole("row", { name: /Netflix/ })).toContainText("$756K");
});

test("each company says what it states: stock type, vesting, and a bonus it does not pay", async ({ page }) => {
  await page.goto("/statistics");
  await page.getByRole("tab", { name: msg("shell-tab-insights-stock"), exact: true }).click();

  const google = page.getByRole("row", { name: /Google/ });
  await expect(google).toContainText(msg("insights-stock-trajectory-panel-vests", { schedule: "38/32/20/10" }));
  // No stock type stated, a schedule stated: the schedule alone, no dash.
  const microsoft = page.getByRole("row", { name: /Microsoft/ });
  await expect(microsoft).toContainText(msg("insights-stock-trajectory-panel-vests", { schedule: "25/25/25/25" }));
  await expect(microsoft.locator(".traj-vehicle")).not.toContainText("—");
  await expect(page.getByRole("row", { name: /OpenAI/ })).toContainText(msg("insights-stock-trajectory-panel-no-bonus"));

  const choice = page.getByTestId("traj-choice");
  await expect(choice.getByRole("heading")).toHaveText(msg("insights-stock-trajectory-panel-choice-companies"));
  await expect(choice.getByRole("row", { name: /Netflix/ })).not.toContainText("%");

  const leftOut = page.getByTestId("traj-left-out");
  await expect(leftOut).toContainText(msg("insights-stock-trajectory-panel-left-out", { count: 7 }));
  const why = leftOut.getByRole("button", { name: msg("insights-stock-trajectory-panel-why-left-out") });
  await why.focus();
  const tip = leftOut.getByRole("tooltip");
  await expect(tip).toContainText(msg("insights-stock-trajectory-panel-left-out-reason", { reason: "not_us_pay" }));
  await expect(tip).toContainText(msg("insights-stock-trajectory-panel-left-out-reason", { reason: "level_unplaced" }));
});

/* Each figure says where it came from in one word; what the words mean is
   said once, behind a help mark on the first column they sit in. A hover-only
   title on every cell reached neither a keyboard nor a finger. */
for (const width of [1280, 360]) test(`the source labels are explained once, to a keyboard and a tap (${width}px)`, async ({ page }, testInfo) => {
  await page.setViewportSize({ width, height: 900 });
  await page.goto("/statistics");
  await page.getByRole("tab", { name: msg("shell-tab-insights-stock"), exact: true }).click();

  const googleRow = page.getByRole("row", { name: /Google/ });
  const label = googleRow.getByText(msg("insights-stock-trajectory-panel-part-source", { source: "posted" }), { exact: true });
  await expect(label).toBeVisible();
  await expect(label).not.toHaveAttribute("title");

  const table = page.locator(".traj-table").first();
  // One help mark for the table, not one per cell, on the first column: it
  // stays in view when a narrow table scrolls sideways to the figures.
  const help = table.getByRole("button", { name: msg("insights-stock-trajectory-panel-about-the-source-labels") });
  await expect(help).toHaveCount(1);
  expect(await help.evaluate((el) => (el.closest("th") as HTMLTableCellElement | null)?.cellIndex)).toBe(0);
  expect(await label.evaluate((el) => (el.closest("td") as HTMLTableCellElement | null)?.cellIndex)).toBe(3);

  const tip = table.getByRole("tooltip");
  await expect(tip).toBeHidden();
  await help.focus();
  await expect(help).toBeFocused();
  await expect(tip).toBeVisible();
  for (const source of ["posted", "company_rule", "measured", "estimated", "mixed"] as const) {
    await expect(tip).toContainText(msg("insights-stock-trajectory-panel-part-source", { source }));
    await expect(tip).toContainText(msg("insights-stock-trajectory-panel-part-source-explained", { source }));
  }
  const box = (await tip.boundingBox())!;
  expect(box.x, "the key starts off screen").toBeGreaterThanOrEqual(0);
  expect(box.x + box.width, "the key runs off screen").toBeLessThanOrEqual(width);
  const header = (await help.locator("xpath=ancestor::tr").boundingBox())!;
  expect(box.y, "the key covers the column names").toBeGreaterThanOrEqual(header.y + header.height);

  await help.blur();
  await expect(tip).toBeHidden();
  // A touch device opens it with a real tap; elsewhere a click, from a pointer
  // that was not already resting on the mark.
  if (testInfo.project.use.hasTouch) {
    await help.tap();
  } else {
    await page.mouse.move(0, 0);
    await help.click();
  }
  await expect(tip).toBeVisible();
});

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

// Stock-trajectory sub-tab: the slider re-prices the equity slice of a public
// package while base/bonus stay fixed, and private companies are held out as
// illiquid. Mirrors the /api/statistics/comp-trajectory payload shape.
const trajectoryFixture = {
  currency: "USD",
  assumptions: { bonus_pct: 0.12, equity_by_band: { senior: 0.35, staff: 0.45 } },
  // base 430k + bonus 120k + equity 450k
  overall: { count: 30, median_tc: 1_000_000, base: 430_000, bonus: 120_000, equity: 450_000, equity_pct: 0.45, split_source: "measured" },
  public: [
    { company: "google", ticker: "GOOGL", equity_vehicle: "rsu", split_source: "measured", count: 20, median_tc: 1_000_000, base: 380_000, bonus: 120_000, equity: 500_000, equity_pct: 0.5 },
    { company: "netflix", ticker: "NFLX", equity_vehicle: "rsu", split_source: "measured", count: 10, median_tc: 700_000, base: 476_000, bonus: 84_000, equity: 140_000, equity_pct: 0.2 },
  ],
  private: [
    { company: "openai", equity_vehicle: "options", split_source: "measured", count: 15, median_tc: 1_100_000, base: 418_000, bonus: 132_000, equity: 550_000, equity_pct: 0.5 },
  ],
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
  const shock = page.getByRole("img", { name: "Equity shockwave by company" });
  await expect(shock).toContainText(/\+\$50K/);
  await expect(page.getByRole("group", { name: "Time range" })).toHaveCount(0);

  // Public companies render with their tickers and today's comp.
  const googleRow = page.getByRole("row", { name: /Google/ });
  await expect(googleRow).toContainText("GOOGL");
  await expect(googleRow).toContainText("$1M");

  // Private companies are held out as illiquid; the rationale stays one focus away.
  const privateTip = page.getByRole("button", { name: "Why private companies do not move" });
  await privateTip.focus();
  await expect(page.getByRole("tooltip").filter({ hasText: /Pre-IPO equity is illiquid/i })).toBeVisible();
  await expect(page.getByRole("row", { name: /OpenAI/ })).toContainText("$1.10M");

  // Drive the stock up +100%: only the equity slice moves.
  await slider.fill("100");
  await expect(hero).toHaveText(/\$1\.45M projected TC/);
  // Google's fatter equity slice (500k) gains more than Netflix's thin one (140k).
  await expect(page.getByRole("row", { name: /Google/ })).toContainText("$1.50M");
  await expect(page.getByRole("row", { name: /Netflix/ })).toContainText("$840K");
  // Private OpenAI is unaffected by the public-stock scenario.
  await expect(page.getByRole("row", { name: /OpenAI/ })).toContainText("$1.10M");

  // Drive it down: total comp falls below today.
  await slider.fill("-50");
  await expect(hero).toHaveText(/\$775K projected TC/);
});

/* Each row says where its split came from in one word; what the words mean is
   said once, behind a help mark on the column they sit in. A hover-only title
   on every row reached neither a keyboard nor a finger. */
for (const width of [1280, 360]) test(`the split labels are explained once, to a keyboard and a tap (${width}px)`, async ({ page }) => {
  await page.setViewportSize({ width, height: 900 });
  await page.goto("/statistics");
  await page.getByRole("tab", { name: msg("shell-tab-insights-stock"), exact: true }).click();

  const googleRow = page.getByRole("row", { name: /Google/ });
  const label = googleRow.getByText(msg("insights-stock-trajectory-panel-split-source", { split: "measured" }), { exact: true });
  await expect(label).toBeVisible();
  await expect(label).not.toHaveAttribute("title");

  const table = page.locator(".traj-table").first();
  // One help mark for the column, not one per row.
  const help = table.getByRole("button", { name: msg("insights-stock-trajectory-panel-about-the-split-labels") });
  await expect(help).toHaveCount(1);
  // It sits on the column the words appear in: Equity, the third.
  expect(await help.evaluate((el) => (el.closest("th") as HTMLTableCellElement | null)?.cellIndex)).toBe(2);
  expect(await label.evaluate((el) => (el.closest("td") as HTMLTableCellElement | null)?.cellIndex)).toBe(2);

  const tip = table.getByRole("tooltip");
  await expect(tip).toBeHidden();
  await help.focus();
  await expect(help).toBeFocused();
  await expect(tip).toBeVisible();
  for (const split of ["measured", "mixed", "heuristic"] as const) {
    await expect(tip).toContainText(msg("insights-stock-trajectory-panel-split-source", { split }));
    await expect(tip).toContainText(msg("insights-stock-trajectory-panel-split-source-explained", { split }));
  }
  const box = (await tip.boundingBox())!;
  expect(box.x, "the key starts off screen").toBeGreaterThanOrEqual(0);
  expect(box.x + box.width, "the key runs off screen").toBeLessThanOrEqual(width);
  const header = (await help.locator("xpath=ancestor::tr").boundingBox())!;
  expect(box.y, "the key covers the column names").toBeGreaterThanOrEqual(header.y + header.height);

  await help.blur();
  await expect(tip).toBeHidden();
  await help.click();
  await expect(tip).toBeVisible();
});

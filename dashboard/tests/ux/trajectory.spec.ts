import { msg } from "../../src/test/msg";
import { expect, mockGet, test } from "./fixtures";
import { showAdvancedInsights } from "./insightsView";
import {
  facetsFixture,
  jobFixture,
  jobListFixture,
  notificationsFixture,
  historyFixture,
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

// What `/api/statistics/offer-terms` sends for these companies: only what each
// states, and no stored close while no price key is saved.
const rules = { listed: true, equity_vehicle: "rsu", vesting_stated_by: "estimated", sign_on_bridges_vesting: false, quote: null };
const offerTermsFixture = {
  feed_configured: false,
  companies: [
    { ...rules, company: "amazon", ticker: "AMZN", vesting: [5, 15, 40, 40], bonus_rule: "none", sign_on_bridges_vesting: true },
    { ...rules, company: "google", ticker: "GOOGL", vesting: [38, 32, 20, 10], bonus_rule: "pct_of_base" },
    { ...rules, company: "microsoft", ticker: "MSFT", vesting: [25, 25, 25, 25], vesting_stated_by: "employer", bonus_rule: "pct_of_base" },
    { ...rules, company: "openai", listed: false, ticker: null, vesting: [25, 25, 25, 25], bonus_rule: "none" },
    { ...rules, company: "netflix", ticker: "NFLX", equity_vehicle: "cash_election", vesting: null, vesting_stated_by: null, bonus_rule: "none" },
  ],
};

test.beforeEach(async ({ page }) => {
  await showAdvancedInsights(page);
  await page.route("/api/statistics/overview**", (route) => route.fulfill({ json: overviewFixture }));
  await mockGet(page, "/api/statistics/history**", (route) => route.fulfill({ json: historyFixture }));
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
  await page.route("/api/statistics/offer-terms", (route) => route.fulfill({ json: offerTermsFixture }));
  // No offer kept yet; the offer tests route a store of their own over this.
  await page.route("/api/profile/offer", (route) => route.fulfill({ json: { offer: null, valuations: {} } }));
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

  const table = page.getByTestId("traj-public").locator(".traj-table");
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

/* Every card on the tab stands apart from the next: the company tables keep
   the same gap the hero and the chart keep, and one search narrows them all. */
test("the company tables stand apart, and one search narrows them", async ({ page }) => {
  await page.setViewportSize({ width: 1280, height: 900 });
  await page.goto("/statistics");
  await page.getByRole("tab", { name: msg("shell-tab-insights-stock"), exact: true }).click();
  await expect(page.getByTestId("traj-choice")).toBeVisible();

  const gaps = await page.locator(".stats-panel > .panel").evaluateAll((cards) =>
    cards.slice(1).map((card, i) => Math.round(card.getBoundingClientRect().top - cards[i].getBoundingClientRect().bottom)));
  expect(gaps.length, "the tab shows its cards").toBeGreaterThanOrEqual(4);
  for (const gap of gaps) expect(gap, `cards ${JSON.stringify(gaps)} touch`).toBeGreaterThanOrEqual(12);

  const search = page.getByRole("searchbox", { name: msg("insights-demand-find-a-company") });
  const chart = page.locator(".chart-panel-wide");
  expect((await search.boundingBox())!.y, "the search sits under the chart")
    .toBeGreaterThan((await chart.boundingBox())!.y + (await chart.boundingBox())!.height);

  await search.fill("open");
  await expect(page.getByTestId("traj-private").getByRole("row", { name: /OpenAI/ })).toBeVisible();
  await expect(page.getByTestId("traj-public")).toHaveCount(0);
  await expect(page.getByTestId("traj-choice")).toHaveCount(0);

  await search.fill("nobody");
  await expect(page.getByTestId("traj-no-match")).toHaveText(msg("insights-stock-trajectory-panel-no-company-matches", { query: "nobody" }));
  await search.fill("");
  await expect(page.getByTestId("traj-public").getByRole("row", { name: /Google/ })).toBeVisible();
});

/* The offer routes, played in memory as the server answers them: what the
   person enters is kept there and nowhere else. */
type Kept = { offer: ({ inputs: Record<string, unknown>; answered: string[] } & Record<string, unknown>) | null; valuations: Record<string, Record<string, unknown>> };
async function keepOffer(page: import("@playwright/test").Page) {
  const kept: Kept = { offer: null, valuations: {} };
  await page.route("/api/profile/offer**", async (route) => {
    const request = route.request();
    const method = request.method();
    const path = new URL(request.url()).pathname;
    const savedAt = new Date().toISOString();
    const company = path.match(/^\/api\/profile\/offer\/valuations\/([^/]+)$/)?.[1];
    if (company && method === "PUT") kept.valuations[company] = { ...request.postDataJSON(), saved_at: savedAt };
    else if (company && method === "DELETE") delete kept.valuations[company];
    else if (method === "PUT") {
      const draft = request.postDataJSON();
      kept.offer = { ...draft, answered: [...new Set<string>(draft.answered)], saved_at: savedAt };
    } else if (method === "DELETE") kept.offer = null;
    await route.fulfill({ json: kept });
  });
  return kept;
}

/* Your offer, year by year: one question at a time, then the years at
   today's price and after the move. Each answer is kept by the local server
   through the offer routes; no other request carries a figure, and nothing
   is kept in the browser. */
test("an offer is asked one question at a time, kept on this computer, and read back after a reload", async ({ page }) => {
  const kept = await keepOffer(page);
  const sent: { method: string; path: string; body: string }[] = [];
  page.on("request", (request) => {
    const url = new URL(request.url());
    sent.push({ method: request.method(), path: url.pathname + url.search, body: request.postData() ?? "" });
  });
  await page.setViewportSize({ width: 1280, height: 900 });
  await page.goto("/statistics/trajectory");
  const offer = page.getByTestId("traj-offer");
  const question = offer.getByTestId("traj-offer-question");
  const next = () => question.getByRole("button", { name: msg("insights-offer-next") }).click();
  await expect(offer.getByRole("heading", { name: msg("insights-offer-start-title") })).toBeVisible();

  await offer.getByRole("combobox", { name: msg("insights-offer-all-companies") }).selectOption("amazon");
  await next();
  await question.getByLabel(msg("insights-offer-q-base"), { exact: true }).fill("213579");
  await next();
  await question.getByLabel(msg("insights-offer-q-stock", { vehicle: "rsu" }), { exact: true }).fill("400000");
  await next();
  // Amazon states 5/15/40/40 and pays no bonus: one press, and no bonus question.
  await question.getByRole("button", { name: msg("insights-offer-vesting-yes") }).click();
  await expect(question).toHaveAttribute("data-step", "sign_on");
  await question.getByRole("button", { name: msg("insights-offer-sign-on-yes") }).click();
  await question.getByLabel(msg("insights-offer-sign-on", { year: 1 }), { exact: true }).fill("100000");
  await question.getByLabel(msg("insights-offer-sign-on", { year: 2 }), { exact: true }).fill("80000");
  await next();

  await expect(offer.getByRole("heading", { name: msg("insights-offer-finished-title", { named: "yes", company: "Amazon" }) })).toBeVisible();
  await expect(offer.getByTestId("traj-offer-total")).toHaveText("$1.43M");
  await offer.getByText(msg("insights-offer-show-table")).click();
  // Amazon's 5/15/40/40: the sign-on carries the first two years.
  const years = offer.getByTestId("traj-offer-years");
  const yearRow = (year: number) => years.getByRole("row", { name: new RegExp(msg("insights-offer-year-n", { year })) });
  await expect(yearRow(1)).toContainText("$334K");
  await expect(yearRow(3)).toContainText("$374K");
  await offer.getByLabel(msg("insights-offer-move-aria", { listed: "yes" })).fill("20");
  // Only the equity takes the 20%: year 3 vests $160K, so it gains $32K.
  await expect(yearRow(3)).toContainText("$406K");
  await expect(yearRow(1)).toContainText("$338K");

  // Kept by the local server, as answered.
  await expect.poll(() => kept.offer?.answered).toEqual(["company", "base", "stock", "vesting", "sign_on"]);
  expect(kept.offer?.inputs).toMatchObject({ company: "amazon", base: 213579, grant: 400000, sign_on: [100000, 80000] });
  // Every write is to the offer routes, and no other request carries a figure.
  const api = sent.filter((r) => r.path.startsWith("/api/"));
  expect(api.filter((r) => r.method !== "GET" && !r.path.startsWith("/api/profile/offer")), "a write left the offer routes").toEqual([]);
  for (const figure of ["213579", "400000", "100000", "80000"]) {
    expect(api.filter((r) => !r.path.startsWith("/api/profile/offer") && (r.path.includes(figure) || r.body.includes(figure))),
      `a request carried ${figure}`).toEqual([]);
  }

  await page.reload();
  const again = page.getByTestId("traj-offer");
  await expect(again.getByRole("button", { name: msg("insights-offer-chip-edit", { answer: msg("insights-offer-chip-base", { amount: "$214K" }) }) }))
    .toBeVisible();
  expect(await page.evaluate(() => Object.keys(localStorage).filter((k) => /offer|valuation/i.test(k)))).toEqual([]);
  await again.getByRole("button", { name: msg("insights-offer-clear") }).click();
  await expect(again.getByRole("heading", { name: msg("insights-offer-start-title") })).toBeVisible();
  await expect.poll(() => kept.offer).toBeNull();
});

for (const width of [1280, 360]) test(`a company row starts the offer, and each view fits the screen (${width}px)`, async ({ page }) => {
  const kept = await keepOffer(page);
  await page.setViewportSize({ width, height: 900 });
  await page.goto("/statistics/trajectory");
  const row = page.getByTestId("traj-private").getByRole("row", { name: /OpenAI/ });
  await row.getByRole("button", { name: msg("insights-offer-start-aria", { company: "OpenAI" }) }).click();

  const offer = page.getByTestId("traj-offer");
  await expect(offer.getByRole("heading", { name: msg("insights-offer-finished-title", { named: "yes", company: "OpenAI" }) })).toBeFocused();
  const base = offer.getByRole("button", { name: msg("insights-offer-chip-edit", { answer: msg("insights-offer-chip-base", { amount: "$550K" }) }) });
  await expect(base).toContainText(msg("insights-offer-tag", { tag: "typical" }));
  await expect(offer.getByText(`${msg("insights-offer-private")} ${msg("insights-offer-valuation-none")}`)).toBeVisible();
  const noSideways = async (view: string) => {
    const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
    expect(overflow, `the page scrolls sideways (${view})`).toBeLessThanOrEqual(0);
  };
  await noSideways("finished");

  // One valuation, entered once from its chip, also reads in the private companies table.
  await offer.getByRole("button", { name: msg("insights-offer-chip-edit", { answer: msg("insights-offer-chip-valuation", { kind: "none", from: "", to: "" }) }) }).click();
  const question = offer.getByTestId("traj-offer-question");
  await expect(question).toHaveAttribute("data-step", "valuation");
  await noSideways("question");
  await question.getByLabel(msg("insights-offer-valuation-grant", { unit: "per_share" }), { exact: true }).fill("50");
  await question.getByLabel(msg("insights-offer-valuation-test", { unit: "per_share" }), { exact: true }).fill("75");
  await question.getByRole("button", { name: msg("insights-offer-done") }).click();
  await expect(row).toContainText("$1.38M");
  await expect.poll(() => kept.valuations.openai).toMatchObject({ unit: "per_share", grant_at: 50, test_at: 75 });
});

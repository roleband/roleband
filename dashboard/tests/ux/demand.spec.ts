import { installJobDetailRoutes } from "./boardHarness";
import { msg } from "../../src/test/msg";
import { expect, test } from "./fixtures";
import { expectOnTop, pointAndClick } from "./paint";
import {
  facetsFixture,
  hiringFixture,
  jobListFixture,
  notificationsFixture,
  historyFixture, overviewFixture,
  statsFixture,
  statusFixture,
  syncStartedFixture,
} from "../../src/test/fixtures";

test.beforeEach(async ({ page }) => {
  await installJobDetailRoutes(page);
  await page.route("/api/profile", (route) => route.fulfill({ json: {
    profile: null, scope_configured: true,
  } }));
  await page.route("/api/stats", (route) => route.fulfill({ json: statsFixture }));
  await page.route("/api/status", (route) => route.fulfill({ json: statusFixture }));
  await page.route("/api/sync", (route) => route.fulfill({ json: syncStartedFixture }));
  await page.route("/api/facets", (route) => route.fulfill({ json: facetsFixture }));
  await page.route("/api/notifications**", (route) => route.fulfill({ json: notificationsFixture }));
  await page.route("/api/demand**", (route) => route.fulfill({ json: hiringFixture }));
  await page.route("/api/statistics/overview**", (route) => route.fulfill({ json: overviewFixture }));
  await page.route("/api/statistics/history**", (route) => route.fulfill({ json: historyFixture }));
  await page.route("/api/jobs/*/similar**", (route) => route.fulfill({ json: { scope: "cross", items: [] } }));
  await page.route("/api/jobs?**", (route) => route.fulfill({ json: jobListFixture }));
});

test("Hiring is a basic tab with no window of its own", async ({ page }) => {
  // Hiring is a sub-tab of the Insights page.
  await page.goto("/statistics");
  await page.getByRole("tab", { name: "Hiring", exact: true }).click();
  await expect(page.getByRole("group", { name: "Time range" })).toHaveCount(0);
  await expect(page.getByRole("banner", { name: msg("shell-topbar-aria") })).toContainText("Insights/Hiring");
  // No role lists: Hiring answers who hires and where, and the Board lists roles.
  // Asked of the loaded panel, not the one still waiting for its answer.
  await expect(page.getByRole("heading", { level: 2, name: "236 roles open" })).toBeVisible();
  await expect(page.locator("#statistics-tabpanel a[href*='/job/']")).toHaveCount(0);
});

/* Unbounded, the tab would draw one bar per company, every place group and a
 * row per role, many screens tall. Every view has a ceiling. */
test("Hiring draws bounded views: fifteen companies, a counted tail, regions that open", async ({ page }) => {
  await page.goto("/statistics/demand");
  await expect(page.locator(".insight-hero .eyebrow")).toHaveText("Hiring");
  await expect(page.getByRole("heading", { level: 2, name: "236 roles open" })).toBeVisible();

  await expect(page.getByText("3 companies more have 12 roles (6% of these roles).")).toBeVisible();
  await expect(page.locator("table")).toHaveCount(0);
  // The whole tab fits in a few screens at a desktop width.
  const height = await page.locator(".stats-main").evaluate((el) => el.scrollHeight);
  expect(height).toBeLessThan(4000);

  // A side of the split is the scope bar's, sent to the route.
  const yours = page.waitForRequest((r) => r.url().includes("/api/demand?side=yours"));
  await page.getByRole("group", { name: "Companies" }).getByRole("button", { name: "Your companies" }).click();
  await yours;
  await expect(page).toHaveURL(/side=yours/);
  await page.getByRole("button", { name: "All companies" }).click();

  // Every company, searchable, in a sheet.
  await page.getByRole("button", { name: "Show all 18 companies" }).click();
  const sheet = page.getByRole("dialog", { name: "All companies hiring" });
  await sheet.getByRole("searchbox", { name: "Find a company" }).fill("market-1");
  await expect(sheet.getByText("6 of 18 companies")).toBeVisible();
  await page.keyboard.press("Escape");

  // A region opens into its countries; a role naming only the region stays apart.
  const europe = page.getByRole("button", { name: "Europe" });
  await expect(europe).toHaveAttribute("aria-expanded", "false");
  await europe.click();
  await expect(europe).toHaveAttribute("aria-expanded", "true");
  await expect(page.getByText("All of Europe")).toBeVisible();
  await expect(page.getByText("Germany")).toBeVisible();
});

/* Each company on Hiring opens its roles on the Board. A chart bar takes no
 * keyboard focus, so the full list is the keyboard's way to every company: a
 * link with the Board's own address, reachable by Tab and opened by Enter. */
test("a company in the full list is a link to its roles on the Board, and Back returns to Hiring", async ({ page }) => {
  await page.goto("/statistics/demand?side=yours");
  await page.getByRole("button", { name: "Show all 18 companies" }).click();
  const sheet = page.getByRole("dialog", { name: "All companies hiring" });
  const link = sheet.getByRole("link", { name: "Anthropic", exact: true });
  await expect(link).toHaveAttribute("href", "/?company=anthropic");
  await expect(sheet.getByRole("link")).toHaveCount(18);

  const narrowed = page.waitForRequest((r) => r.url().includes("/api/jobs?") && r.url().includes("company=anthropic"));
  await link.focus();
  await expect(link).toBeFocused();
  await page.keyboard.press("Enter");
  await narrowed;
  await expect(page).toHaveURL(/\/\?company=anthropic$/);

  await page.goBack();
  await expect(page).toHaveURL(/\/statistics\/demand\?side=yours$/);
  await expect(page.getByRole("tab", { name: "Hiring", exact: true })).toHaveAttribute("aria-selected", "true");
});

test("a company's name on the chart opens its roles on the Board", async ({ page }) => {
  await page.goto("/statistics/demand");
  const name = page.locator(".chart-demand svg text", { hasText: /^Google$/ });
  await expect(name).toBeVisible();
  // The chart, mid-screen and clear of the phone's bottom bar. WebKit does not
  // scroll to an SVG text element itself, so the chart's box is what scrolls.
  await page.locator(".chart-demand").evaluate((el) => el.scrollIntoView({ block: "center" }));
  await expectOnTop(name, "Google's name on the chart");
  const narrowed = page.waitForRequest((r) => r.url().includes("/api/jobs?") && r.url().includes("company=google"));
  await pointAndClick(page, name);
  await narrowed;
  await expect(page).toHaveURL(/\/\?company=google$/);

  await page.goBack();
  await expect(page).toHaveURL(/\/statistics\/demand$/);
});

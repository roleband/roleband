/* Not for me on a pick asks why, and Passed over lists what the assistant read
   and did not pick, with what the person removed. The rows there are the
   Radar's rows; the page is one of Top picks, so the rail keeps Top picks
   marked and the top bar names the page with Top picks as the way back. */

import AxeBuilder from "@axe-core/playwright";
import type { Page, Request } from "@playwright/test";
import { msg } from "../../src/test/msg";
import { expect, mockApi, test } from "./fixtures";
import { installPassedOverRoutes, installTopPicksRoutes, passedOverFixture } from "./topPicksHarness";

const railItem = (page: Page) => page.locator('.nav-rail a[href="/top-picks"]');
const pickRow = (page: Page, title: string) => page.getByRole("article").filter({ hasText: title });

test.beforeEach(async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
});

/** The feedback calls the page made, as method and body. */
async function recordFeedback(page: Page) {
  const calls: { method: string; id: number; body: unknown }[] = [];
  await mockApi(page, ["PUT", "DELETE"], "/api/jobs/*/feedback", (route) => {
    const request: Request = route.request();
    const id = Number(request.url().match(/jobs\/(\d+)\/feedback/)![1]);
    calls.push({ method: request.method(), id, body: request.postDataJSON() });
    return route.fulfill({ json: { job_id: id, is_dismissed: request.method() === "PUT", reason: null, company: "openai", department: null, team: null } });
  });
  return calls;
}

test("Not for me asks why first; a reason removes the pick and goes with it", async ({ page }) => {
  await installTopPicksRoutes(page);
  const calls = await recordFeedback(page);
  await page.goto("/top-picks");
  const row = pickRow(page, "Staff Product Manager, API");
  await row.getByRole("button", { name: "Not for me" }).click();

  const dialog = page.getByRole("dialog", { name: msg("picks-why-title") });
  await expect(dialog).toBeVisible();
  // Nothing happens until the person answers, and the safe answer has the focus.
  expect(calls).toEqual([]);
  await expect(row).toBeVisible();
  await expect(dialog.getByRole("button", { name: msg("picks-why-keep") })).toBeFocused();

  await dialog.getByRole("button", { name: msg("picks-why-level") }).click();
  await expect(dialog).toHaveCount(0);
  await expect(row).toHaveCount(0);
  expect(calls).toEqual([{ method: "PUT", id: 501, body: { verdict: "dismissed", reason: "wrong_level" } }]);
});

test("Skip the reason removes the pick with no reason", async ({ page }) => {
  await installTopPicksRoutes(page);
  const calls = await recordFeedback(page);
  await page.goto("/top-picks");
  await pickRow(page, "Staff Product Manager, API").getByRole("button", { name: "Not for me" }).click();
  await page.getByRole("dialog").getByRole("button", { name: msg("picks-why-skip") }).click();
  await expect(pickRow(page, "Staff Product Manager, API")).toHaveCount(0);
  expect(calls).toEqual([{ method: "PUT", id: 501, body: { verdict: "dismissed", reason: null } }]);
});

test("Keep it and Escape leave the pick where it was, and send nothing", async ({ page }) => {
  await installTopPicksRoutes(page);
  const calls = await recordFeedback(page);
  await page.goto("/top-picks");
  const row = pickRow(page, "Staff Product Manager, API");
  const dialog = page.getByRole("dialog", { name: msg("picks-why-title") });

  await row.getByRole("button", { name: "Not for me" }).click();
  await dialog.getByRole("button", { name: msg("picks-why-keep") }).click();
  await expect(dialog).toHaveCount(0);

  await row.getByRole("button", { name: "Not for me" }).click();
  await expect(dialog).toBeVisible();
  await page.keyboard.press("Escape");
  await expect(dialog).toHaveCount(0);

  await expect(row).toBeVisible();
  expect(calls).toEqual([]);
});

test("the dialog's answers sit in one row of reasons, inside the dialog, under the role they are about", async ({ page, isMobile }) => {
  await installTopPicksRoutes(page);
  await page.goto("/top-picks");
  await pickRow(page, "Staff Product Manager, API").getByRole("button", { name: "Not for me" }).click();
  const dialog = page.getByRole("dialog", { name: msg("picks-why-title") });
  await expect(dialog.locator(".pick-feedback-role")).toHaveText(
    msg("picks-why-role", { title: "Staff Product Manager, API", company: "OpenAI" }),
  );
  // It opens with a small scale-in: measure once it has settled.
  await expect.poll(() => dialog.evaluate((el) => el.getAnimations().every((one) => one.playState === "finished"))).toBe(true);
  const box = (await dialog.boundingBox())!;
  const reasons = dialog.locator(".pick-feedback-reasons .ui-btn");
  await expect(reasons).toHaveCount(6);
  const tops = new Set<number>();
  for (const reason of await reasons.all()) {
    const r = (await reason.boundingBox())!;
    expect(r.x).toBeGreaterThanOrEqual(box.x);
    expect(r.x + r.width).toBeLessThanOrEqual(box.x + box.width);
    tops.add(Math.round(r.y));
  }
  // Six answers wrap onto at most two lines at the dialog's 560 width, never a
  // column. A phone's narrower dialog wraps them further.
  if (!isMobile) expect(tops.size).toBeLessThanOrEqual(2);
});

test("the end line's count opens Passed over, a page of Top picks", async ({ page }) => {
  await installPassedOverRoutes(page);
  await page.goto("/top-picks");
  await page.locator(".board-list-end").getByRole("link", { name: msg("picks-end-passed", { count: 41 }) }).click();
  await expect(page).toHaveURL(/\/top-picks\/passed$/);

  await expect(page.getByRole("heading", { level: 1, name: msg("picks-passed-heading") })).toBeAttached();
  const crumb = page.getByRole("navigation", { name: "Breadcrumb" });
  await expect(crumb).toHaveText(/Top picks\s*\/\s*Passed over/);
  await expect(crumb.getByRole("link", { name: "Top picks" })).toHaveAttribute("href", "/top-picks");
  await expect(railItem(page)).toHaveAttribute("aria-current", "page");
});

test("Passed over lists the removed pick, what came close and the tallies, with the Radar's rows", async ({ page }) => {
  await installPassedOverRoutes(page);
  await page.goto("/top-picks/passed");

  const removed = page.getByRole("region", { name: msg("picks-passed-removed", { count: 1 }) });
  const close = page.getByRole("region", { name: msg("picks-passed-close", { count: 4 }) });
  await expect(removed.locator(".passed-said")).toHaveText(
    `${msg("picks-passed-said", { reason: "pay_too_low" })} ${msg("picks-passed-put-back")}`,
  );
  await expect(close.locator(".job-row")).toHaveCount(3);
  await expect(close.locator(".pick-reason-opening").first()).toHaveText("Mostly people management");
  // Short lists under their own heads: no column head.
  await expect(page.locator(".list-head")).toHaveCount(0);
  // The row is the Radar's row in its cells.
  const cells = await close.locator(".job-row").first().evaluate((row) =>
    [...row.children].map((cell) => cell.className).filter((name) => name !== "job-under"));
  expect(cells).toEqual(["job-signal", "jr-role", "jr-loc", "jr-comp", "jr-actions"]);

  await close.getByRole("button", { name: msg("picks-passed-show-all", { count: 4 }) }).click();
  await expect(close.locator(".job-row")).toHaveCount(4);

  await expect(page.getByRole("region", { name: msg("picks-passed-read", { count: 37 }) }).getByRole("listitem")).toHaveText([
    `${msg("picks-pass-hard-rule-named", { rules: "No on-call" })}30`,
    `${msg("picks-pass-below-level")}5`,
    `${msg("picks-pass-off-direction")}2`,
  ]);
  await expect(page.getByRole("region", { name: msg("picks-passed-ruled", { count: 12 }) }).getByRole("listitem"))
    .toHaveText(["Base under 200,00012"]);
});

test("Put it back clears the dismissal, takes the role off the page and opens nothing", async ({ page }) => {
  await installPassedOverRoutes(page);
  const calls = await recordFeedback(page);
  await page.goto("/top-picks/passed");
  const removed = page.getByRole("region", { name: msg("picks-passed-removed", { count: 1 }) });
  await removed.getByRole("button", { name: msg("picks-passed-put-back") }).click();
  await expect(removed).toHaveCount(0);
  expect(calls.map(({ method, id }) => ({ method, id }))).toEqual([{ method: "DELETE", id: 601 }]);
  await expect(page).toHaveURL(/\/top-picks\/passed$/);
});

test("Passed over's blocks start where the rows start and end where they end", async ({ page }) => {
  await installPassedOverRoutes(page);
  await page.goto("/top-picks/passed");
  const rowBox = (await page.locator(".job-row").first().boundingBox())!;
  const row = { left: rowBox.x, right: rowBox.x + rowBox.width };
  // The ledger margin is a block's right padding, and nothing is drawn in it.
  const drawn = (selector: string) => page.locator(selector).first().evaluate((node) => {
    const rect = node.getBoundingClientRect();
    return { left: rect.left, right: rect.right - parseFloat(getComputedStyle(node).paddingRight) };
  });
  for (const selector of [".passed-summary", ".passed-section .search-section-head", ".passed-tally"]) {
    const box = await drawn(selector);
    expect(Math.abs(box.left - row.left), `${selector} starts with the rows`).toBeLessThanOrEqual(1);
    expect(Math.abs(box.right - row.right), `${selector} ends with the rows`).toBeLessThanOrEqual(1);
  }
});

test("an empty week says so, with the way back and no count", async ({ page }) => {
  await installPassedOverRoutes(page, {
    passed: passedOverFixture({ passed_this_week: 0, near_misses: [], passes: [], ruled_out: 0, ruled_out_by_rule: [] }),
    removed: [],
  });
  await page.goto("/top-picks/passed");
  await expect(page.getByText(msg("picks-passed-empty-title"))).toBeVisible();
  await expect(page.getByRole("main").getByRole("link", { name: msg("picks-passed-back") })).toHaveAttribute("href", "/top-picks");
  await expect(page.locator(".passed-summary")).toHaveCount(0);
});

for (const theme of ["light", "dark"] as const) {
  test(`Passed over and the dialog: accessible contrast and names (${theme})`, async ({ page }) => {
    await installPassedOverRoutes(page);
    await page.addInitScript((value) => localStorage.setItem("theme", value), theme);
    await page.goto("/top-picks/passed");
    await expect(page.locator(".passed-section").first()).toBeVisible();
    const serious = async () => (await new AxeBuilder({ page }).analyze()).violations
      .filter((v) => v.impact === "serious" || v.impact === "critical")
      .map((v) => `${v.id}: ${v.nodes.map((n) => n.html).join("; ")}`);
    expect(await serious()).toEqual([]);

    await page.goto("/top-picks");
    await pickRow(page, "Staff Product Manager, API").getByRole("button", { name: "Not for me" }).click();
    const dialog = page.getByRole("dialog", { name: msg("picks-why-title") });
    await expect(dialog).toBeVisible();
    // It fades in: contrast is read once it has settled, not through the fade.
    await expect.poll(() => dialog.evaluate((el) => el.getAnimations({ subtree: true }).every((one) => one.playState === "finished"))).toBe(true);
    expect(await serious()).toEqual([]);
  });
}

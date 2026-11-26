/* Top picks: the Radar's list narrowed to the picks, each pick's reasons under
   its row. The row is the Radar's row, unchanged in its columns and controls;
   the reasons take the row's ink, so a read pick quietens them with its title;
   the rail's dot goes out when the screen opens. */

import type { Locator, Page } from "@playwright/test";
import { relative } from "../../src/copy/format";
import { msg } from "../../src/test/msg";
import { expect, mockApi, mockGet, test } from "./fixtures";
import { laidOut, overlapping } from "./geometry";
import { healthyState, installTopPicksRoutes, pickFixture, picksList } from "./topPicksHarness";

const railItem = (page: Page) => page.locator('.nav-rail a[href="/top-picks"]');
/** The end line's first sentence for the harness's last check, two hours ago by Claude Code. */
const checked = () => msg("picks-end-checked", { when: relative(-2 * 3600), host: msg("picks-host", { host: "claude-code" }) });

/** The column heads, and the first row's cells in order, as the page draws them. */
async function rowShape(page: Page) {
  const head = await page.locator(".list-head").first().evaluate((el) =>
    [...el.children].map((cell) => `${cell.className}:${cell.textContent?.trim()}`));
  const cells = await page.locator(".job-row").first().evaluate((row) =>
    [...row.children].map((cell) => cell.className).filter((name) => name !== "job-under"));
  const controls = await page.locator(".job-row .jr-actions").first().evaluate((el) =>
    [...el.querySelectorAll("button")].map((button) => button.getAttribute("aria-keyshortcuts") ?? button.className));
  return { head, cells, controls };
}

const ink = (locator: Locator) => locator.evaluate((el) => {
  const cs = getComputedStyle(el);
  return { color: cs.color, weight: cs.fontWeight, size: cs.fontSize };
});

test.beforeEach(async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
});

test("a pick's row is the Radar's row: the same columns and controls, in the same order", async ({ page }) => {
  await installTopPicksRoutes(page);
  await page.goto("/");
  await expect(page.locator(".job-row").first()).toBeVisible();
  const radar = await rowShape(page);

  await railItem(page).click();
  await expect(page).toHaveURL(/\/top-picks$/);
  // The picks' own rows, not the Radar's still on screen while the route loads.
  await expect(page.locator(".job-row .pick-reasons")).toHaveCount(2);
  const picks = await rowShape(page);

  expect(radar.cells).toEqual(["job-signal", "jr-role", "jr-loc", "jr-comp", "jr-actions"]);
  expect(picks).toEqual(radar);
  // Each screen keeps its own list: the Radar's rows are not the picks.
  await expect(page.getByRole("heading", { name: "Principal Product Manager, Platform" })).toBeVisible();
});

test("reasons sit under the row with no label, the opening in the row's ink at one weight", async ({ page }) => {
  await installTopPicksRoutes(page);
  await page.goto("/top-picks");
  const row = page.locator(".job-row").first();
  const reasons = row.locator(".pick-reasons li");
  await expect(reasons).toHaveText([
    "Staff level at a company that pays at the top of your band.",
    "Remote across the EU, as you asked.",
    "A small product team that ships weekly.",
  ]);
  await expect(row.locator(".job-under")).not.toContainText(/why|catch/i);

  const title = await ink(row.locator(".job-title"));
  const opening = await ink(row.locator(".pick-reason-opening").first());
  const rest = await ink(reasons.first());
  expect(opening.color).toBe(title.color);
  expect(rest.color).not.toBe(opening.color);
  expect(opening.weight).toBe(rest.weight);
  expect(opening.size).toBe(rest.size);
  expect(Number(rest.weight)).toBeLessThan(Number(title.weight));

  // Under the role's own lines, and inside the row.
  const titleBox = (await row.locator(".jr-role").boundingBox())!;
  const underBox = (await row.locator(".job-under").boundingBox())!;
  const rowBox = (await row.boundingBox())!;
  expect(underBox.y).toBeGreaterThanOrEqual(titleBox.y + titleBox.height - 0.5);
  expect(underBox.y + underBox.height).toBeLessThanOrEqual(rowBox.y + rowBox.height + 0.5);

  // Every pick is news, so no row carries the new-role bar.
  await expect(page.locator(".job-row.is-new")).toHaveCount(0);
});

test("a read pick quietens its reasons with its title", async ({ page }) => {
  await installTopPicksRoutes(page);
  await page.goto("/top-picks");
  const [unread, read] = [page.locator(".job-row").nth(0), page.locator(".job-row").nth(1)];
  await expect(read).toHaveClass(/is-viewed/);
  const unreadOpening = await ink(unread.locator(".pick-reason-opening").first());
  const readOpening = await ink(read.locator(".pick-reason-opening").first());
  const readTitle = await ink(read.locator(".job-title"));
  const readRest = await ink(read.locator(".pick-reasons li").first());
  const unreadRest = await ink(unread.locator(".pick-reasons li").first());
  expect(readOpening.color).not.toBe(unreadOpening.color);
  expect(readOpening.color).toBe(readTitle.color);
  expect(readRest.color).not.toBe(unreadRest.color);
});

test("the rail's dot is lit for an unseen pick and goes out when the screen opens", async ({ page }) => {
  const seen = await installTopPicksRoutes(page, { state: healthyState({ unseen_pick: true }) });
  await page.goto("/");
  await expect(railItem(page).locator(".rail-badge-dot")).toBeVisible();
  await expect(railItem(page).locator(".rail-badge-dot")).toHaveText("");

  await railItem(page).click();
  await expect(page.locator(".job-row .pick-reasons").first()).toBeVisible();
  await expect(railItem(page).locator(".rail-badge-dot")).toHaveCount(0);
  await expect.poll(() => seen.opened).toBe(1);

  await page.locator('.nav-rail a[href="/"]').click();
  await expect(page.locator(".job-row").first()).toBeVisible();
  await expect(railItem(page).locator(".rail-badge-dot")).toHaveCount(0);
});

test("no dot while nothing is unseen", async ({ page }) => {
  await installTopPicksRoutes(page, { state: healthyState({ unseen_pick: false }) });
  await page.goto("/");
  await expect(page.locator(".job-row").first()).toBeVisible();
  await expect(railItem(page)).toBeVisible();
  await expect(railItem(page).locator(".rail-badge")).toHaveCount(0);
});

/** Where the docked bar ends, and where the register and the content column begin. */
const underBar = (page: Page) => page.evaluate(() => {
  const top = (selector: string) => document.querySelector(selector)!.getBoundingClientRect().top;
  return {
    bar: document.querySelector(".board-toolbar")!.getBoundingClientRect().bottom,
    rail: top(".rail-shell-rail"),
    content: top(".board-content > *"),
  };
});

test("nothing starts under the docked bar, and the filter column stands level on both screens", async ({ page }) => {
  await installTopPicksRoutes(page);
  // Two rows on the Radar: a column as tall as its list, where sticky cannot
  // move the register down.
  await page.goto("/");
  await expect(page.locator(".job-row").first()).toBeVisible();
  const radar = await underBar(page);
  await page.goto("/top-picks");
  await expect(page.locator(".job-row .pick-reasons").first()).toBeVisible();
  const picks = await underBar(page);
  await mockGet(page, "/api/jobs?**", (route) => route.fulfill({ json: picksList([]) }));
  await page.goto("/top-picks");
  await expect(page.getByText(msg("picks-empty-title"))).toBeVisible();
  const empty = await underBar(page);
  for (const [name, at] of [["Radar", radar], ["Top picks", picks], ["Top picks, empty", empty]] as const) {
    expect(at.rail, `${name}: the filter column`).toBeGreaterThanOrEqual(at.bar - 0.5);
    expect(at.content, `${name}: the list or its empty state`).toBeGreaterThanOrEqual(at.bar - 0.5);
  }
  expect(picks.rail).toBe(radar.rail);
});

test("the first pick starts within 150px of the top at 900 tall, with no title above it", async ({ page }) => {
  await installTopPicksRoutes(page);
  await page.goto("/top-picks");
  await expect(page.locator(".job-row").first()).toBeVisible();
  const top = (await page.locator(".job-row").first().boundingBox())!.y;
  expect(top).toBeLessThanOrEqual(150);
  await expect(page.locator(".page-hero")).toHaveCount(0);
});

const LONG_TITLE = "Senior Staff Product Manager, Developer Platform and Infrastructure for Enterprise Machine Learning Workloads across North America and Europe";
const UNSPACED = "Kubernetes-operator-observability-reliability-platform-engineering-leadership-".repeat(3);

for (const width of [1440, 1100]) {
  test(`a long title, six reasons and an unspaced word stay inside the row at ${width}`, async ({ page }) => {
    await page.setViewportSize({ width, height: 900 });
    const reasons = [
      { opening: "Staff level", rest: " at a company that pays at the top of your band, with equity refreshed every year and a bonus." },
      { opening: UNSPACED, rest: " is the team's own name for the work." },
      { opening: "Remote", rest: " across the EU, as you asked, with two weeks a year in the Dublin office." },
      { opening: "", rest: `A plain reason with ${UNSPACED} in the middle of it.` },
      { opening: "Small team", rest: " of six, reporting to the head of product, who came from a company you follow." },
      { opening: "Posted", rest: " two days ago and still open." },
    ];
    await installTopPicksRoutes(page, { list: picksList([pickFixture({ id: 601, title: LONG_TITLE, pick_reasons: reasons })]) });
    await page.goto("/top-picks");
    const row = page.locator(".job-row").first();
    await expect(row.locator(".pick-reasons li")).toHaveCount(6);

    const boxes = await laidOut(row, ".jr-role, .jr-loc, .jr-comp, .jr-actions, .job-under");
    expect(overlapping(boxes)).toEqual([]);
    const rowBox = (await row.boundingBox())!;
    for (const line of await laidOut(row, ".pick-reasons li")) {
      expect(line.right, line.what).toBeLessThanOrEqual(rowBox.x + rowBox.width + 0.5);
    }
    const sideways = await page.locator(".main").evaluate((main) => main.scrollWidth - main.clientWidth);
    expect(sideways).toBeLessThanOrEqual(0);
  });
}

test("nothing cleared the bar: the empty state says how many roles were read, and the list's end", async ({ page }) => {
  await installTopPicksRoutes(page, { list: picksList([]) });
  await page.goto("/top-picks");
  await expect(page.getByText(msg("picks-empty-title"))).toBeVisible();
  await expect(page.getByText(msg("picks-empty-read", { count: 222 }))).toBeVisible();
  await expect(page.locator(".board-list-end")).toHaveText(`${checked()} ${msg("picks-end-passed", { count: 41 })}`);
});

test("picks the filters hide are counted, and Reset all brings them back", async ({ page }) => {
  await installTopPicksRoutes(page);
  // After the harness: the lens's list narrowed by a company answers nothing.
  await mockGet(page, "/api/jobs?**", (route) => {
    const params = new URL(route.request().url()).searchParams;
    if (params.get("top_picks") !== "true") return route.fallback();
    return route.fulfill({ json: params.has("company") ? picksList([]) : picksList() });
  });
  await page.goto("/top-picks?company=amazon");
  await expect(page.getByText(msg("picks-empty-filtered-title"))).toBeVisible();
  await expect(page.getByText(msg("picks-empty-filtered", { count: 2 }))).toBeVisible();
  await page.locator(".board-content").getByRole("button", { name: msg("radar-reset") }).click();
  await expect(page.locator(".job-row")).toHaveCount(2);
});

test("a search finds no pick: it says so, and the Radar's search stays its own", async ({ page }) => {
  await installTopPicksRoutes(page);
  await mockGet(page, "/api/jobs?**", (route) => {
    const params = new URL(route.request().url()).searchParams;
    if (params.get("top_picks") !== "true") return route.fallback();
    return route.fulfill({ json: params.get("q") ? picksList([]) : picksList() });
  });
  await page.goto("/top-picks");
  await expect(page.locator(".job-row")).toHaveCount(2);
  const search = page.getByRole("searchbox").first();
  await search.fill("zzzz");
  await search.press("Enter");
  await expect(page.getByText(msg("picks-empty-search-title"))).toBeVisible();

  await page.locator('.nav-rail a[href="/"]').click();
  await expect(page.locator(".job-row").first()).toBeVisible();
  await expect(page.getByRole("searchbox").first()).toHaveValue("");
});

test("paused checks say so above the list, and Resume checks turns them back on", async ({ page }) => {
  const paused = healthyState({ state: "off", health: "off" });
  await installTopPicksRoutes(page, { state: paused });
  const modes: unknown[] = [];
  await mockApi(page, "PUT", "/api/picks/mode", (route) => {
    modes.push(route.request().postDataJSON());
    return route.fulfill({ json: healthyState() });
  });
  await page.goto("/top-picks");
  const note = page.getByRole("note").filter({ hasText: msg("picks-note-paused") });
  await expect(note).toBeVisible();
  // Above the list, ending where the rows end.
  const noteBox = (await note.boundingBox())!;
  const firstRow = (await page.locator(".job-row").first().boundingBox())!;
  expect(noteBox.y + noteBox.height).toBeLessThanOrEqual(firstRow.y);
  expect(Math.abs(noteBox.x + noteBox.width - (firstRow.x + firstRow.width))).toBeLessThanOrEqual(1);

  await note.getByRole("button", { name: msg("picks-resume") }).click();
  await expect(note).toHaveCount(0);
  expect(modes).toEqual([{ state: "on" }]);
});

test("the list's end names the last check and how many roles were passed over, with nothing to click", async ({ page }) => {
  await installTopPicksRoutes(page);
  await page.goto("/top-picks");
  const end = page.locator(".board-list-end");
  await expect(end).toHaveText(`${checked()} ${msg("picks-end-passed", { count: 41 })}`);
  await expect(end.getByRole("link")).toHaveCount(0);
  const lastRow = (await page.locator(".job-row").last().boundingBox())!;
  expect((await end.boundingBox())!.y).toBeGreaterThanOrEqual(lastRow.y + lastRow.height);
});

for (const [what, over, said] of [
  ["late", { health: "late", waiting: 14 }, msg("picks-end-waiting", { count: 14 })],
  ["stopped early", { health: "stopped_early", last_check: {
    host: "claude-code", finished_at: new Date(Date.now() - 2 * 3_600_000).toISOString(), outcome: "stopped", note: "plan limit reached",
  } }, msg("picks-end-stopped", { reason: "plan limit reached" })],
] as const) {
  test(`checks ${what}: no note above the list, and the end line says it in its quiet ink`, async ({ page }) => {
    await installTopPicksRoutes(page, { state: healthyState(over) });
    await page.goto("/top-picks");
    await expect(page.locator(".job-row .pick-reasons")).toHaveCount(2);
    const end = page.locator(".board-list-end");
    await expect(end).toContainText(said);
    await expect(end).toContainText(checked());
    await expect(page.locator(".picks-notes, .search-truncation-note")).toHaveCount(0);
    const lastRow = (await page.locator(".job-row").last().boundingBox())!;
    expect((await end.boundingBox())!.y).toBeGreaterThanOrEqual(lastRow.y + lastRow.height);
    // Its ink is the end line's own, not a note's band.
    const look = await end.evaluate((el) => ({ fill: getComputedStyle(el).backgroundColor, edge: getComputedStyle(el).borderLeftWidth }));
    expect(look.edge).toBe("0px");
    expect(look.fill).toMatch(/rgba\(0, 0, 0, 0\)|transparent/);
  });
}

test("a note that asks for an action stays above the list while the checks are also late", async ({ page }) => {
  await installTopPicksRoutes(page, { state: healthyState({ health: "late", waiting: 14, routine_host_connection: "rule_missing" }) });
  await page.goto("/top-picks");
  await expect(page.locator(".job-row .pick-reasons")).toHaveCount(2);
  await expect(page.locator(".search-truncation-note")).toHaveCount(1);
  await expect(page.locator(".search-truncation-note").getByRole("link", { name: msg("picks-note-fix") })).toBeVisible();
  await expect(page.locator(".board-list-end")).toContainText(msg("picks-end-waiting", { count: 14 }));
});

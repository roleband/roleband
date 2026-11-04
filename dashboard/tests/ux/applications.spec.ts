import type { ApplicationCard, InterviewWrite } from "../../src/api";
import { msg } from "../../src/test/msg";
import { applicationCardFixture, applicationDetailFixture } from "../../src/test/fixtures";
import { installBoardRoutes, installJobDetailRoutes } from "./boardHarness";
import { expect, mockApi, mockGet, test, type Page } from "./fixtures";

/* The application pipeline in a browser: every move reachable from the
 * keyboard (the path the spec requires; dragging is only ever the fast one),
 * a whole card that opens its application's page, a drag that moves a card
 * and scrolls the board under it, Interviewing's question,
 * hidden columns a browser remembers, filters kept in the address, the
 * page's own stage button and Mark done, and Up next. The API is a small store, so a re-read
 * after a write shows the write. */

const cards: ApplicationCard[] = [
  applicationCardFixture({ job_id: 101, title: "Staff Product Manager, API", company: "openai" }),
  applicationCardFixture({
    job_id: 202, pursuit_id: 20, stage: "applied", title: "Principal Engineering Manager", company: "stripe",
  }),
  applicationCardFixture({
    job_id: 303, pursuit_id: 30, stage: "rejected", ended_at_stage: "interviewing", title: "Head of Platform",
    company: "apple",
  }),
];

async function installPipeline(page: Page, start: ApplicationCard[] = cards) {
  let stored = start.map((card) => ({ ...card }));
  const stageWrites: Array<{ jobId: number; stage: string }> = [];
  const pursuitWrites: Array<Record<string, unknown>> = [];
  const interviews: InterviewWrite[] = [];
  await mockGet(page, "/api/applications", (route) => route.fulfill({ json: { applications: stored } }));
  await mockGet(page, "/api/applications/*", (route, request) => {
    const jobId = Number(new URL(request.url()).pathname.split("/")[3]);
    const card = stored.find((one) => one.job_id === jobId);
    return card
      ? route.fulfill({ json: applicationDetailFixture({ application: card }) })
      : route.fulfill({ status: 404, json: { detail: { code: "application-not-found" } } });
  });
  await mockGet(page, "/api/applications/*/activity", (route) => route.fulfill({ json: { items: [] } }));
  await mockApi(page, "PUT", "/api/jobs/*/pursuit", async (route, request) => {
    const jobId = Number(new URL(request.url()).pathname.split("/")[3]);
    const update = request.postDataJSON() as Partial<ApplicationCard>;
    pursuitWrites.push(update);
    const stage = update.stage;
    if (stage) stageWrites.push({ jobId, stage });
    stored = stored.map((card) => (card.job_id === jobId ? { ...card, ...update } : card));
    const card = stored.find((one) => one.job_id === jobId)!;
    await route.fulfill({ json: { pursuit: {
      id: jobId, stage: card.stage, priority: card.priority, notes: null, next_action: card.next_action,
      next_action_due: card.next_action_due, updated_at: "2026-11-04T12:00:00Z",
    } } });
  });
  await mockApi(page, "POST", "/api/jobs/*/pursuit/interviews", async (route, request) => {
    const interview = request.postDataJSON() as InterviewWrite;
    interviews.push(interview);
    await route.fulfill({ json: { interview: {
      id: 9, outcome: null, notes: null, link: null, format: null, ...interview,
      created_at: "2026-11-04T12:00:00Z", updated_at: "2026-11-04T12:00:00Z",
    } } });
  });
  return { stageWrites, pursuitWrites, interviews };
}

const column = (page: Page, name: string) => page.getByRole("region", { name });
const menuButton = (page: Page, title: string) =>
  page.getByRole("button", { name: msg("applications-card-actions", { title }) });
const menu = (page: Page, title: string) =>
  page.getByRole("dialog", { name: msg("applications-menu-label", { title }) });

test.beforeEach(async ({ page }) => {
  await installBoardRoutes(page);
  await installJobDetailRoutes(page);
});

test("the rail place opens on the board, titled by its rail label", async ({ page }) => {
  await installPipeline(page);
  await page.goto("/pipeline");
  await expect(page).toHaveURL(/\/pipeline\/board$/);
  await expect(page.getByRole("heading", { level: 1 })).toHaveText(msg("shell-nav-pipeline"));
  await expect(column(page, "Considering").getByText("Staff Product Manager, API")).toBeVisible();
  await expect(page.getByText(msg("applications-board-summary", {
    moving: 2, decided: 0, closed: 1, needNext: msg("applications-board-need-next", { count: 1 }),
  }))).toBeVisible();
});

test("a card moves from its menu with the keyboard alone, and Undo moves it back", async ({ page }) => {
  const { stageWrites } = await installPipeline(page);
  await page.goto("/pipeline/board");

  await menuButton(page, "Staff Product Manager, API").focus();
  await page.keyboard.press("Enter");
  const options = menu(page, "Staff Product Manager, API");
  await expect(options).toBeVisible();
  await options.getByRole("button", { name: "Researching" }).focus();
  await page.keyboard.press("Enter");

  await expect(column(page, "Researching").getByText("Staff Product Manager, API")).toBeVisible();
  await expect(column(page, "Considering").getByText("Staff Product Manager, API")).toHaveCount(0);
  await expect.poll(() => stageWrites).toEqual([{ jobId: 101, stage: "researching" }]);

  await page.getByRole("button", { name: msg("applications-move-undo") }).click();
  await expect(column(page, "Considering").getByText("Staff Product Manager, API")).toBeVisible();
  await expect.poll(() => stageWrites.at(-1)).toEqual({ jobId: 101, stage: "saved" });
});

test("a click anywhere on a card opens its application, and the menu button stays its own control", async ({ page }) => {
  await installPipeline(page);
  await page.goto("/pipeline/board");

  const card = page.locator('.app-tile[data-job-id="101"]');
  await expect(card).toBeVisible();
  await menuButton(page, "Staff Product Manager, API").click();
  await expect(menu(page, "Staff Product Manager, API")).toBeVisible();
  await expect(page).toHaveURL(/\/pipeline\/board$/);
  await page.keyboard.press("Escape");

  const box = (await card.boundingBox())!;
  await page.mouse.click(box.x + 12, box.y + box.height - 8);
  await expect(page).toHaveURL(/\/pipeline\/101$/);
  await expect(page.getByRole("heading", { level: 1 })).toHaveText("Staff Product Manager, API");
});

/** Press a card in the middle and carry it to (x, y) in small steps, as a hand does. */
async function pressAndCarry(page: Page, jobId: number, x: number, y: number) {
  const from = (await page.locator(`.app-tile[data-job-id="${jobId}"]`).boundingBox())!;
  await page.mouse.move(from.x + from.width / 2, from.y + from.height / 2);
  await page.mouse.down();
  await page.mouse.move(x, y, { steps: 12 });
}
const middleOf = async (page: Page, name: string) => {
  const box = (await column(page, name).boundingBox())!;
  return { x: box.x + box.width / 2, y: box.y + 160 };
};

test("a card drags to another column, and the drop neither opens it nor selects any text", async ({ page }, testInfo) => {
  test.skip(testInfo.project.name === "mobile", "The pipeline has no phone layout; a touch moves cards from the menu.");
  const { stageWrites } = await installPipeline(page);
  await page.goto("/pipeline/board");
  await expect(column(page, "Considering").getByText("Staff Product Manager, API")).toBeVisible();

  const to = await middleOf(page, "Researching");
  await pressAndCarry(page, 101, to.x, to.y);
  await expect(column(page, "Researching")).toHaveAttribute("data-drop-target", "");
  expect(await page.evaluate(() => window.getSelection()?.toString() ?? "")).toBe("");
  await page.mouse.up();

  await expect(column(page, "Researching").getByText("Staff Product Manager, API")).toBeVisible();
  await expect.poll(() => stageWrites).toEqual([{ jobId: 101, stage: "researching" }]);
  await expect(page.getByRole("button", { name: msg("applications-move-undo") })).toBeVisible();
  await expect(page).toHaveURL(/\/pipeline\/board$/);
});

test("a drag held at the board's edge scrolls it, and a drop on Interviewing asks for the date first", async ({ page }, testInfo) => {
  test.skip(testInfo.project.name === "mobile", "The pipeline has no phone layout; a touch moves cards from the menu.");
  const { stageWrites } = await installPipeline(page);
  await page.goto("/pipeline/board");
  const scroller = page.locator(".app-board-scroll");
  await expect(column(page, "Considering").getByText("Staff Product Manager, API")).toBeVisible();
  expect(await scroller.evaluate((element) => element.scrollLeft)).toBe(0);

  const board = (await scroller.boundingBox())!;
  const end = await scroller.evaluate((element) => element.scrollWidth - element.clientWidth);
  await pressAndCarry(page, 101, board.x + board.width - 6, board.y + 160);
  await expect.poll(() => scroller.evaluate((element) => element.scrollLeft)).toBeGreaterThan(200);
  // It stops at the board's own end. The carried card is drawn inside the
  // board and widens it as it goes, so a scroll measured by the board's width
  // would chase the card for as long as the drag is held.
  await expect.poll(() => scroller.evaluate((element) => element.scrollLeft)).toBeGreaterThanOrEqual(end - 1);
  await page.waitForTimeout(400);
  expect(await scroller.evaluate((element) => element.scrollLeft)).toBeLessThanOrEqual(end + 1);

  const to = await middleOf(page, "Interviewing");
  await page.mouse.move(to.x, to.y, { steps: 6 });
  await expect(column(page, "Interviewing")).toHaveAttribute("data-drop-target", "");
  await page.mouse.up();

  const dialog = page.getByRole("dialog", { name: msg("applications-interview-title") });
  await expect(dialog).toBeVisible();
  await dialog.getByRole("button", { name: msg("applications-interview-cancel") }).click();
  await expect(column(page, "Considering").getByText("Staff Product Manager, API")).toBeVisible();
  expect(stageWrites).toEqual([]);
});

test("the application page moves its stage from the keyboard: S opens the menu, a number picks the stage", async ({ page }) => {
  const { stageWrites } = await installPipeline(page);
  await page.goto("/pipeline/202");
  // Named by what it shows: the stage, then the days in it.
  const stage = (name: string) => page.getByRole("button", { name: new RegExp(`^${name} · \\d+ days?$`) });
  await expect(stage("Applied")).toBeVisible();

  await page.keyboard.press("s");
  await expect(page.getByRole("dialog", { name: msg("applications-stage-menu-label", { title: "Principal Engineering Manager" }) }))
    .toBeVisible();
  // Networking shows as Researching, so the five moving stages are 1 to 5.
  await page.keyboard.press("5");
  await expect(stage("Offer")).toBeVisible();
  await expect.poll(() => stageWrites).toEqual([{ jobId: 202, stage: "offer" }]);
});

test("Mark done on the application page asks at once for the next step, and saves it", async ({ page }) => {
  const { pursuitWrites } = await installPipeline(page);
  await page.goto("/pipeline/101");
  await page.getByRole("button", { name: msg("applications-next-set") }).click();
  await page.getByLabel(msg("applications-next-prompt")).fill("Email the recruiter");
  await page.getByRole("button", { name: msg("applications-next-save") }).click();
  await expect(page.getByText("Email the recruiter")).toBeVisible();

  await page.getByRole("button", { name: msg("applications-next-done") }).click();
  await expect(page.getByLabel(msg("applications-next-prompt"))).toBeFocused();
  await page.getByRole("button", { name: msg("applications-next-not-now") }).click();
  await expect(page.getByText(msg("applications-next-empty"))).toBeVisible();
  await expect.poll(() => pursuitWrites).toEqual([
    { next_action: "Email the recruiter", next_action_due: null },
    { next_action: null, next_action_due: null },
  ]);
});

test("Up next lists what is due by day, overdue first, and a row opens its application", async ({ page }) => {
  const day = 86_400_000;
  await installPipeline(page, [
    { ...cards[0], next_action: "Ask for an intro", next_action_due: new Date(Date.now() - 2 * day).toISOString() },
    { ...cards[1], next_interview: {
      id: 5, label: "Hiring manager call", scheduled_at: new Date(Date.now() + 5 * day).toISOString(), all_day: false,
      format: "video",
    } },
    cards[2],
  ]);
  await page.goto("/pipeline/board");
  await page.getByRole("tab", { name: msg("shell-tab-pipeline-up-next") }).click();
  await expect(page).toHaveURL(/\/pipeline\/up-next$/);

  const days = page.getByRole("region");
  await expect(days.first()).toHaveAccessibleName(msg("applications-upnext-overdue"));
  await expect(days.first().getByText(msg("applications-upnext-step", { step: "Ask for an intro" }))).toBeVisible();
  await expect(days.nth(1).getByText(msg("applications-upnext-interview", { label: "Hiring manager call" }))).toBeVisible();

  await days.nth(1).getByRole("link").click();
  await expect(page).toHaveURL(/\/pipeline\/202$/);
  await expect(page.getByRole("heading", { level: 1 })).toHaveText("Principal Engineering Manager");
});

test("moving into Interviewing asks when the interview is, and records it with the move", async ({ page }) => {
  const { stageWrites, interviews } = await installPipeline(page);
  await page.goto("/pipeline/board");

  await menuButton(page, "Principal Engineering Manager").click();
  await menu(page, "Principal Engineering Manager").getByRole("button", { name: "Interviewing" }).click();
  const dialog = page.getByRole("dialog", { name: msg("applications-interview-title") });
  await expect(dialog).toBeVisible();
  expect(stageWrites).toEqual([]);

  await dialog.getByLabel(msg("applications-interview-date")).fill("2026-11-12");
  await dialog.getByLabel(msg("applications-interview-time")).fill("14:00");
  await dialog.getByRole("button", { name: msg("applications-interview-submit", { stage: "Interviewing" }) }).click();

  await expect(column(page, "Interviewing").getByText("Principal Engineering Manager")).toBeVisible();
  await expect.poll(() => interviews.length).toBe(1);
  expect(stageWrites).toEqual([{ jobId: 202, stage: "interviewing" }]);
  expect(interviews[0]).toMatchObject({ label: msg("applications-interview-default-label"), all_day: false });
  const sent = new Date(interviews[0].scheduled_at);
  expect([sent.getFullYear(), sent.getMonth(), sent.getDate(), sent.getHours()]).toEqual([2026, 10, 12, 14]);
});

test("a column hidden from its menu takes no room, stays hidden after a reload, and comes back from Columns", async ({ page }) => {
  await installPipeline(page);
  await page.goto("/pipeline/board");
  const closedName = msg("applications-column-closed");

  await page.getByRole("button", { name: msg("applications-column-menu", { column: closedName }) }).click();
  await page.getByRole("button", { name: msg("applications-column-hide") }).click();
  await expect(column(page, closedName)).toHaveCount(0);
  // Nothing stands in for it: Decided is now the board's last column.
  const board = await page.locator(".app-board").boundingBox();
  const decided = await column(page, msg("applications-column-decided")).boundingBox();
  expect(Math.round(board!.x + board!.width)).toBe(Math.round(decided!.x + decided!.width));

  await page.reload();
  await expect(column(page, "Considering").getByText("Staff Product Manager, API")).toBeVisible();
  await expect(page.getByText("Head of Platform")).toHaveCount(0);
  const columns = page.getByRole("button", { name: msg("applications-columns-hidden", { count: 1 }) });
  await columns.click();
  await page.getByRole("dialog", { name: msg("applications-columns") })
    .getByRole("checkbox", { name: new RegExp(`^${closedName}`) }).check();
  await expect(column(page, closedName).getByText("Head of Platform")).toBeVisible();
});

test("a filter lives in the address: it survives opening a card and coming back, and / goes to the search", async ({ page }) => {
  await installPipeline(page);
  await page.goto("/pipeline/board");
  await expect(column(page, "Considering").getByText("Staff Product Manager, API")).toBeVisible();

  await page.getByRole("button", { name: msg("applications-board-need-next", { count: 1 }) }).click();
  await expect(page).toHaveURL(/\/pipeline\/board\?only=needs_next$/);
  await expect(page.getByText("Staff Product Manager, API")).toHaveCount(0);
  await expect(column(page, "Applied").getByText(msg("applications-column-count-of", { count: 1, total: 1 }))).toBeVisible();

  await page.getByText("Principal Engineering Manager").click();
  await expect(page).toHaveURL(/\/pipeline\/202$/);
  await page.goBack();
  await expect(page).toHaveURL(/only=needs_next/);
  await expect(page.getByText("Staff Product Manager, API")).toHaveCount(0);

  await page.getByRole("button", { name: msg("applications-filter-highlight-instead") }).click();
  await expect(page.locator(".app-tile", { hasText: "Staff Product Manager, API" })).toHaveAttribute("data-match", "false");
  await expect(page.locator(".app-tile", { hasText: "Principal Engineering Manager" })).toHaveAttribute("data-match", "true");

  await page.locator("body").press("/");
  await expect(page.getByRole("searchbox", { name: msg("applications-search-label") })).toBeFocused();
});

import type { Locator } from "@playwright/test";
import type { ApplicationCard, InterviewWrite, Job } from "../../src/api";
import { msg } from "../../src/test/msg";
import { applicationCardFixture, applicationDetailFixture, jobDetailFixture, jobFixture, jobListFixture } from "../../src/test/fixtures";
import type { ApplicationStep } from "../../src/api";
import { installBoardRoutes, installJobDetailRoutes } from "./boardHarness";
import { expect, mockApi, mockGet, test, viewChoices, watchReads, type Page } from "./fixtures";
import { mainRail, openPipelineView, pipelineStar } from "./pipelineRail";

/* The application pipeline in a browser: every move reachable from the
 * keyboard (the path the spec requires; dragging is only ever the fast one),
 * a whole card that opens its role's posting over the view, a drag that
 * moves a card and scrolls the board under it, Interviewing's question,
 * hidden columns a browser remembers, filters kept in the address, the
 * posting's stage keys and the Workspace's next step, Up next and its month,
 * and the List: the backlog of roles still in Considering, its sort and
 * columns. The API is a small store, so a re-read after a write shows the
 * write. */

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

/** Soonest first, steps with no day last in the order added: the server's order. */
const soonestFirst = (steps: ApplicationStep[]) => [...steps].sort((a, b) =>
  (a.due == null ? 1 : 0) - (b.due == null ? 1 : 0) || (a.due ?? "").localeCompare(b.due ?? "") || a.id - b.id);

async function installPipeline(page: Page, start: ApplicationCard[] = cards) {
  // A card given only a next step holds it as its one step, as the server's
  // mirror keeps them.
  let stored = start.map((card) => card.next_action && card.steps.length === 0
    ? applicationCardFixture({ ...card, steps: undefined })
    : { ...card });
  const stageWrites: Array<{ jobId: number; stage: string }> = [];
  const pursuitWrites: Array<Record<string, unknown>> = [];
  const stepWrites: Array<Record<string, unknown>> = [];
  let nextStepId = 900;
  /** Changes one role's open steps and keeps its next step the soonest of them. */
  const setSteps = (jobId: number, change: (steps: ApplicationStep[]) => ApplicationStep[]) => {
    stored = stored.map((card) => {
      if (card.job_id !== jobId) return card;
      const steps = soonestFirst(change(card.steps));
      return { ...card, steps, next_action: steps[0]?.text ?? null, next_action_due: steps[0]?.due ?? null };
    });
  };
  const ticked = new Map<number, ApplicationStep>();
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
  // A role's posting, as the server reads it: its star and its pursuit are
  // the stored card's.
  await mockGet(page, /\/api\/jobs\/\d+$/, (route, request) => {
    const jobId = Number(new URL(request.url()).pathname.split("/")[3]);
    const card = stored.find((one) => one.job_id === jobId);
    if (!card) return route.fallback();
    return route.fulfill({ json: jobDetailFixture({
      id: jobId, company: card.company, title: card.title, is_favorite: card.starred,
      pursuit: card.pursuit_id == null ? null : {
        id: card.pursuit_id, job_id: jobId, stage: card.stage, priority: card.priority, notes: null,
        next_action: card.next_action, next_action_due: card.next_action_due,
        created_at: "2026-10-20T09:00:00Z", updated_at: "2026-11-04T12:00:00Z",
      },
    }) });
  });
  // The month's read: each card's next round and dated step in the span.
  await mockGet(page, "/api/applications/calendar**", (route, request) => {
    const url = new URL(request.url());
    const [start, end] = ["start", "end"].map((key) => new Date(url.searchParams.get(key)!).getTime());
    const inSpan = (at: string) => new Date(at).getTime() >= start && new Date(at).getTime() < end;
    const items = stored.flatMap((card) => [
      ...(card.next_interview && inSpan(card.next_interview.scheduled_at) ? [{
        kind: "interview", job_id: card.job_id, at: card.next_interview.scheduled_at,
        interview_id: card.next_interview.id, label: card.next_interview.label, all_day: card.next_interview.all_day,
        format: card.next_interview.format, outcome: null,
      }] : []),
      ...card.steps.filter((step) => step.due && inSpan(step.due)).map((step) => ({
        kind: "step", job_id: card.job_id, at: step.due, step: step.text, step_id: step.id,
      })),
    ]);
    return route.fulfill({ json: { items } });
  });
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
  const jobOf = (url: string) => Number(new URL(url).pathname.split("/")[3]);
  const stepOf = (url: string) => Number(new URL(url).pathname.split("/")[6]);
  // A star, as the server's board answers it: a role still at Considering
  // leaves the pipeline with its star and comes back with it.
  const unstarred: number[] = [];
  const offBoard = new Map<number, ApplicationCard>();
  await mockApi(page, ["PUT", "DELETE"], "/api/jobs/*/favorite", async (route, request) => {
    const jobId = jobOf(request.url());
    const on = request.method() === "PUT";
    if (!on) unstarred.push(jobId);
    const card = stored.find((one) => one.job_id === jobId);
    if (!on && card?.stage === "saved") {
      offBoard.set(jobId, card);
      stored = stored.filter((one) => one.job_id !== jobId);
    } else if (on && offBoard.has(jobId)) {
      stored = [...stored, { ...offBoard.get(jobId)!, starred: true }];
      offBoard.delete(jobId);
    } else {
      stored = stored.map((one) => (one.job_id === jobId ? { ...one, starred: on } : one));
    }
    await route.fulfill({ json: { job_id: jobId, is_favorite: on } });
  });
  await mockApi(page, "POST", "/api/jobs/*/pursuit/steps", async (route, request) => {
    const write = request.postDataJSON() as { text: string; due: string | null };
    stepWrites.push({ add: write });
    const step: ApplicationStep = { id: nextStepId++, text: write.text, due: write.due, created_at: "2026-11-04T12:00:00Z", done_at: null };
    setSteps(jobOf(request.url()), (steps) => [...steps, step]);
    await route.fulfill({ json: { step } });
  });
  await mockApi(page, ["PATCH", "DELETE"], "/api/jobs/*/pursuit/steps/*", async (route, request) => {
    const [jobId, stepId] = [jobOf(request.url()), stepOf(request.url())];
    if (request.method() === "DELETE") {
      stepWrites.push({ remove: stepId });
      setSteps(jobId, (steps) => steps.filter((one) => one.id !== stepId));
      return route.fulfill({ json: { id: stepId, deleted: true } });
    }
    const update = request.postDataJSON() as { text?: string; due?: string | null; done?: boolean };
    stepWrites.push({ [stepId]: update });
    const card = stored.find((one) => one.job_id === jobId)!;
    let step = card.steps.find((one) => one.id === stepId) ?? ticked.get(stepId)!;
    step = { ...step, ...("text" in update ? { text: update.text! } : {}), ...("due" in update ? { due: update.due! } : {}) };
    if (update.done === true) {
      ticked.set(stepId, { ...step, done_at: "2026-11-04T12:00:00Z" });
      setSteps(jobId, (steps) => steps.filter((one) => one.id !== stepId));
    } else {
      ticked.delete(stepId);
      setSteps(jobId, (steps) => [...steps.filter((one) => one.id !== stepId), { ...step, done_at: null }]);
    }
    return route.fulfill({ json: { step } });
  });
  return { stageWrites, pursuitWrites, stepWrites, interviews, unstarred };
}

const column = (page: Page, name: string) => page.getByRole("region", { name });
const menuButton = (page: Page, title: string) =>
  page.getByRole("button", { name: msg("applications-card-actions", { title }) });
const menu = (page: Page, title: string) =>
  page.getByRole("dialog", { name: msg("applications-menu-label", { title }) });

/** Let `count` frames paint: a watch over time counted in frames, which a
 *  loaded machine slows along with the page, rather than in milliseconds. */
async function frames(page: Page, count: number) {
  await page.evaluate((left) => new Promise<void>((resolve) => {
    const tick = (n: number) => (n === 0 ? resolve() : requestAnimationFrame(() => tick(n - 1)));
    tick(left);
  }), count);
}

test.beforeEach(async ({ page }) => {
  // Every board column on show, as a person sets it from Columns: these
  // contracts are about the columns' content. A test with its own choice
  // routes its own, which outranks this one.
  await viewChoices(page, { "pipeline.board-hidden": [] });
  await installBoardRoutes(page);
  await installJobDetailRoutes(page);
});

test("the rail place opens on the List, titled by its rail label, and the old Saved address opens it too", async ({ page, isMobile }) => {
  await installPipeline(page);
  await page.goto("/pipeline");
  await expect(page).toHaveURL(/\/pipeline\/list$/);
  await expect(page.getByRole("heading", { level: 1 })).toHaveText(msg("shell-nav-pipeline"));
  await expect(page.getByRole("table").getByRole("link", { name: "Staff Product Manager, API" })).toBeVisible();
  // The Pipeline's star, or on a phone's dock its views in a row.
  const rail = mainRail(page);
  await expect(isMobile ? rail.getByRole("link", { name: msg("shell-tab-pipeline-list"), exact: true }) : pipelineStar(page)).toBeVisible();
  await expect(rail.getByRole("link", { name: "Saved", exact: true })).toHaveCount(0);

  // A role saved and not yet started is in Considering, which the List holds.
  await page.goto("/favorites");
  await expect(page).toHaveURL(/\/pipeline\/list$/);
  await expect(page.getByRole("tab", { name: msg("shell-tab-pipeline-list") })).toHaveAttribute("aria-selected", "true");
  await expect(page.getByRole("table").getByRole("link", { name: "Staff Product Manager, API" })).toBeVisible();
});

test("a card moves from its menu with the keyboard alone, and Undo moves it back", async ({ page, isMobile }) => {
  test.skip(isMobile, "phones are not supported: there the toast's Undo never settles under a tap");
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
  // The keyboard's place goes with the card, so the next Enter acts on it again.
  await expect(column(page, "Researching").getByRole("button", { name: msg("applications-card-actions", { title: "Staff Product Manager, API" }) }))
    .toBeFocused();

  await page.getByRole("button", { name: msg("applications-move-undo") }).click();
  await expect(column(page, "Considering").getByText("Staff Product Manager, API")).toBeVisible();
  await expect.poll(() => stageWrites.at(-1)).toEqual({ jobId: 101, stage: "saved" });
});

const posting = (page: Page) => page.locator(".cover.job-detail");

test("a click anywhere on a card opens its posting over the board, and Back names the Board and returns to it", async ({ page, isMobile }) => {
  test.skip(isMobile, "phones are not supported: there the posting's Back never takes a tap");
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
  // A role in Considering opens on its posting.
  await expect(page).toHaveURL(/\/company\/openai\/job\/101\?tab=posting$/);
  const cover = posting(page);
  await expect(cover.getByRole("heading", { level: 1 })).toHaveText("Staff Product Manager, API");
  await expect(cover.getByRole("tab", { name: msg("role-job-detail-tab-posting") })).toHaveAttribute("aria-selected", "true");
  // A role opened from a list has no way to step to the next one.
  await expect(cover.getByRole("group", { name: /place in the list/i })).toHaveCount(0);
  await expect(cover.locator(".jd-pager")).toHaveCount(0);
  const back = cover.getByRole("button", { name: msg("role-job-detail-back-to", { view: msg("shell-tab-pipeline-board") }) });
  await expect(back).toHaveText(msg("shell-tab-pipeline-board"));
  await back.click();
  await expect(page).toHaveURL(/\/pipeline\/board$/);
  await expect(posting(page)).toHaveCount(0);
  await expect(page.locator('.app-tile[data-job-id="101"]')).toBeVisible();
});

/* A role opened from a Pipeline view stands beside the rail, not over it: the
   rail stays live and says where the person is, the posting has no pager, and
   the rail's own entry for the view goes back to it, landing on the card that
   was open. */
test("a role opened from the board leaves the rail live and marked, and the rail's Board returns to its card", async ({ page, isMobile }) => {
  test.skip(isMobile, "phones are not supported: there the rail lies along the bottom and the role covers the window");
  // The board as a first visit shows it: Considering and the endings hidden.
  await viewChoices(page, { "pipeline.board-hidden": ["saved", "decided", "closed"] });
  await installPipeline(page, [...cards, applicationCardFixture({
    job_id: 404, pursuit_id: 40, stage: "applied", title: "Director of Product", company: "netflix",
  })]);
  await page.goto("/pipeline/board");
  // The expanded rail names the views under the star; the collapsed one has the star alone.
  await mainRail(page).getByRole("button", { name: msg("shell-rail-expand-aria") }).click();
  const tiles = page.locator(".app-tile[data-job-id]");
  await expect(tiles).toHaveCount(2);
  const [firstId] = await tiles.evaluateAll((all) => all.map((tile) => tile.getAttribute("data-job-id")!));
  // The card moves while the rail widens; a click on the card itself waits
  // for it to settle, where one at measured coordinates can land beside it.
  const firstTile = (await tiles.first().boundingBox())!;
  await tiles.first().click({ position: { x: 12, y: firstTile.height - 8 } });
  // An Applied role opens on its Workspace.
  await expect(page).toHaveURL(new RegExp(`/job/${firstId}\\?tab=workspace$`));
  const cover = posting(page);

  const rail = mainRail(page);
  // The cover follows the rail's edge a frame after the rail settles, so the
  // two are read together until they meet.
  const apart = async () => {
    const [railAt, coverAt] = await Promise.all([rail.boundingBox(), page.locator(".ui-overlay-full.cover-beside").boundingBox()]);
    return coverAt!.x - (railAt!.x + railAt!.width);
  };
  await expect.poll(apart, { message: "the role starts where the rail ends" }).toBeCloseTo(0, 0);
  const railBox = (await rail.boundingBox())!;
  // The rail is on top where it stands: a point in it hits the rail, not the cover.
  const hit = await page.evaluate(([x, y]) => !!document.elementFromPoint(x, y)?.closest("nav"), [railBox.x + railBox.width / 2, railBox.y + railBox.height / 2]);
  expect(hit, "the rail is not covered").toBe(true);
  await expect(page.locator("[aria-modal]"), "no modal dialog").toHaveCount(0);
  const board = rail.getByRole("link", { name: msg("shell-tab-pipeline-board"), exact: true });
  await expect(board).toHaveAttribute("aria-current", "true");
  // The role's address sits under its company; Companies is not the place.
  await expect(rail.getByRole("link", { name: msg("shell-nav-companies"), exact: true })).not.toHaveAttribute("aria-current");

  // The tab being read is in the address; no pager offers another role.
  await cover.getByRole("tab", { name: msg("role-job-detail-tab-posting") }).click();
  await expect(page).toHaveURL(new RegExp(`/job/${firstId}\\?tab=posting$`));
  await expect(cover.getByRole("group", { name: /place in the list/i })).toHaveCount(0);
  await page.keyboard.press("j");
  await expect(page, "J does not step to the next card's role").toHaveURL(new RegExp(`/job/${firstId}\\?tab=posting$`));

  await board.click();
  await expect(page).toHaveURL(/\/pipeline\/board$/);
  await expect(posting(page)).toHaveCount(0);
  const returned = page.locator(`.app-tile[data-job-id="${firstId}"] a[href]`);
  await expect(returned, "focus lands on the card that was open").toBeFocused();
  await expect(returned).toHaveAttribute("data-returned", "");
  await expect(returned, "the mark fades on its own").not.toHaveAttribute("data-returned", { timeout: 5000 });
});

/* A Workspace block moves by dragging its grip, and a hidden block stays
   hidden on the next visit until the plus brings it back. Both are saved
   with the person's settings, so clearing the browser's storage keeps them. */
test("a Workspace block drags by its grip to a new place, and a hidden block stays hidden over a reload with the browser's storage cleared", async ({ page, isMobile }) => {
  test.skip(isMobile, "phones are not supported: a finger moves a block from its grip's menu, covered by the unit tests");
  // Tall enough that the drop point, low in the last block, is in the window.
  await page.setViewportSize({ width: 1440, height: 1000 });
  await installPipeline(page);
  await page.goto("/company/stripe/job/202?tab=workspace");
  const cover = posting(page);
  const names = () => cover.locator("[data-section] .app-ws-label").allTextContents();
  const NEXT = msg("applications-ws-next");
  const NOTES = msg("applications-notes-title");
  const ACTIVITY = msg("applications-feed-title");
  // Two columns in this window: the writing (notes, activity) in the main
  // one, the short list (next steps) beside it, which the page draws second.
  await expect.poll(names).toEqual([NOTES, ACTIVITY, NEXT]);
  const activity = cover.getByRole("region", { name: ACTIVITY });
  const activityBox = (await activity.boundingBox())!;
  const beside = (await cover.getByRole("region", { name: NEXT }).boundingBox())!;
  expect(beside.x, "next steps stand beside the writing").toBeGreaterThan(activityBox.x + activityBox.width);
  expect(Math.abs(beside.y - (await cover.getByRole("region", { name: NOTES }).boundingBox())!.y), "level with the first block").toBeLessThan(2);

  // A block carried toward the other column stays in its own.
  await cover.getByRole("button", { name: msg("applications-ws-move", { section: NEXT }) })
    .dragTo(activity, { targetPosition: { x: 40, y: activityBox.height - 12 } });
  await expect.poll(names).toEqual([NOTES, ACTIVITY, NEXT]);

  // Within its column it lands where it is dropped.
  await cover.getByRole("button", { name: msg("applications-ws-move", { section: NOTES }) })
    .dragTo(activity, { targetPosition: { x: 40, y: activityBox.height - 12 } });
  await expect.poll(names).toEqual([ACTIVITY, NOTES, NEXT]);

  // One order is saved for both columns.
  const saved = page.waitForRequest((request) => request.method() === "PUT" && request.url().endsWith("/api/settings/view-choices/workspace.applied")
    && JSON.stringify(request.postDataJSON()) === JSON.stringify({ value: { hidden: ["notes"], order: ["next", "activity", "notes"] } }));
  await cover.getByRole("button", { name: msg("applications-ws-hide", { section: NOTES }) }).click();
  await expect.poll(names).toEqual([ACTIVITY, NEXT]);
  await saved;
  await page.evaluate(() => localStorage.clear());
  await page.reload();
  await expect.poll(names).toEqual([ACTIVITY, NEXT]);

  await cover.getByRole("button", { name: msg("applications-ws-hide", { section: ACTIVITY }) }).click();
  await expect.poll(names).toEqual([NEXT]);

  // Each block offered back is its own row: room around its two lines, a
  // hairline between rows, and a pointer fills the row without boxing it in.
  await cover.getByRole("button", { name: msg("applications-ws-add") }).click();
  const offered = page.getByRole("dialog", { name: msg("applications-ws-add") }).getByRole("button");
  await expect(offered).toHaveCount(2);
  const [upper, lower] = [offered.nth(0), offered.nth(1)];
  const look = (row: Locator) => row.evaluate((el) => {
    const style = getComputedStyle(el);
    return { top: parseFloat(style.paddingTop), edge: style.borderTopColor, fill: style.backgroundColor };
  });
  expect((await look(upper)).top, "room above the name").toBeGreaterThanOrEqual(8);
  const gap = (await lower.boundingBox())!.y - ((await upper.boundingBox())!.y + (await upper.boundingBox())!.height);
  const rule = await lower.evaluate((el) => {
    const line = getComputedStyle(el, "::before");
    return { height: line.height, top: parseFloat(line.top), border: parseFloat(getComputedStyle(el).borderTopWidth) };
  });
  expect(rule.height, "a hairline parts the rows").toBe("1px");
  // The hairline sits in the gap between the rows, clear of both.
  const below = gap + rule.top + rule.border;
  expect(below).toBeGreaterThan(0);
  expect(below + 1).toBeLessThan(gap);
  await lower.hover();
  // The fill fades in, so it is read once the fade has begun.
  await expect.poll(async () => (await look(lower)).fill, { message: "the row fills" }).not.toBe("rgba(0, 0, 0, 0)");
  expect((await look(lower)).edge, "no edge drawn inside the menu").toBe("rgba(0, 0, 0, 0)");

  await offered.filter({ hasText: NOTES }).click();
  await expect.poll(names).toEqual([NOTES, NEXT]);

  // A window too narrow for two columns shows the same blocks as one list, in the saved order.
  await page.setViewportSize({ width: 1000, height: 1000 });
  await expect.poll(names).toEqual([NEXT, NOTES]);
  const [first, second] = [cover.getByRole("region", { name: NEXT }), cover.getByRole("region", { name: NOTES })];
  expect((await second.boundingBox())!.y, "one under the other").toBeGreaterThan((await first.boundingBox())!.y + (await first.boundingBox())!.height - 1);
});

const LONG_STEP = `Ask Mo for an introduction before the panel, then ${"cvb".repeat(40)} and who else joins the system design round, and what they ask`;

test("a long next step stops at two lines on its card, and the card stands one line taller than a short step's", async ({ page }) => {
  // No due day, so the two cards differ in the step alone.
  await installPipeline(page, [
    applicationCardFixture({ job_id: 101, stage: "researching", title: "Staff Product Manager", company: "openai", next_action: LONG_STEP, next_action_due: null }),
    applicationCardFixture({ job_id: 202, pursuit_id: 20, stage: "researching", title: "Staff Product Manager", company: "stripe", next_action: "Email the recruiter", next_action_due: null }),
  ]);
  await page.goto("/pipeline/board");
  const long = page.locator('.app-tile[data-job-id="101"]');
  const short = page.locator('.app-tile[data-job-id="202"]');
  const longStep = long.locator(".app-tile-lead-main");
  const shortStep = short.locator(".app-tile-lead-main");
  await expect(longStep).toBeVisible();
  await expect(shortStep).toBeVisible();

  const read = (step: Locator) => step.evaluate((el) => ({
    height: el.getBoundingClientRect().height,
    line: parseFloat(getComputedStyle(el).lineHeight),
    more: el.scrollHeight > el.clientHeight + 1,
  }));
  const a = await read(longStep);
  const b = await read(shortStep);
  // Fail-first: the step holds more than its two lines show.
  expect(a.more, "the long step runs past its lines").toBe(true);
  expect(a.height).toBeCloseTo(2 * a.line, 0);
  expect(b.more, "a short step reads whole").toBe(false);
  expect(b.height).toBeCloseTo(b.line, 0);
  // The words are all there for a screen reader and a search; only the view stops.
  await expect(longStep).toHaveText(LONG_STEP);

  const longCard = (await long.boundingBox())!;
  const shortCard = (await short.boundingBox())!;
  expect(longCard.height - shortCard.height).toBeCloseTo(a.line, 0);
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
  await frames(page, 24);
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

test("a role's posting moves its stage from the keyboard: M opens the menu, a number picks the stage", async ({ page }) => {
  const { stageWrites } = await installPipeline(page);
  await page.goto("/company/stripe/job/202?tab=workspace");
  const bar = posting(page).locator(".cover-bar");
  const stage = (name: string) => bar.getByRole("button", { name, exact: true });
  await expect(stage("Applied")).toBeVisible();

  await page.keyboard.press("m");
  await expect(page.getByRole("dialog", { name: msg("applications-stage-menu-label", { title: "Principal Engineering Manager" }) }))
    .toBeVisible();
  // Networking shows as Researching, so the five moving stages are 1 to 5.
  await page.keyboard.press("5");
  await expect(stage("Offer")).toBeVisible();
  await expect.poll(() => stageWrites).toEqual([{ jobId: 202, stage: "offer" }]);
});

test("an old address of a role's page opens its posting on the tab it named", async ({ page }) => {
  await installPipeline(page);
  await page.goto("/pipeline/202?tab=workspace");
  await expect(page).toHaveURL(/\/company\/stripe\/job\/202\?tab=workspace$/);
  await expect(posting(page).getByRole("tab", { name: msg("role-job-detail-tab-workspace") })).toHaveAttribute("aria-selected", "true");
});

/* A round to come with nothing written offers the outline its notes start
   from: the form opens on the notes with the caret under the first line, and
   what the person writes there is saved with the lines around it. */
test("a coming round's notes start from three lines to write under, and what is written under them is saved", async ({ page, isMobile }) => {
  test.skip(isMobile, "phones are not supported");
  await page.clock.setFixedTime(new Date(2026, 10, 4, 10, 0));
  const card = applicationCardFixture({ job_id: 505, pursuit_id: 50, stage: "interviewing", title: "Group Product Manager", company: "stripe" });
  await installPipeline(page, [card]);
  const round = {
    id: 31, label: "Panel", scheduled_at: new Date(2026, 10, 10, 15, 0).toISOString(), all_day: false,
    format: "video" as const, link: null, outcome: null, notes: null,
    created_at: "2026-11-01T09:00:00Z", updated_at: "2026-11-01T09:00:00Z",
  };
  await mockGet(page, "/api/applications/505", (route) => route.fulfill({
    json: applicationDetailFixture({ application: card, interviews: [round] }),
  }));
  const updates: Array<Record<string, unknown>> = [];
  await mockApi(page, "PATCH", "/api/jobs/505/pursuit/interviews/31", async (route, request) => {
    const update = request.postDataJSON() as Record<string, unknown>;
    updates.push(update);
    await route.fulfill({ json: { interview: { ...round, ...update } } });
  });

  await page.goto("/company/stripe/job/505?tab=workspace");
  await posting(page).getByRole("button", { name: msg("applications-ws-round-prepare") }).click();
  const form = page.getByRole("dialog", { name: msg("applications-interview-edit-title") });
  const notes = form.getByLabel(msg("applications-interview-notes"));
  await expect(notes).toBeFocused();
  await page.keyboard.type("Priya, head of design");
  await form.getByRole("button", { name: msg("applications-interview-edit-submit") }).click();
  await expect(form).toHaveCount(0);
  expect(updates).toEqual([expect.objectContaining({ notes: [
    msg("applications-interview-prompt-people"), "Priya, head of design",
    msg("applications-interview-prompt-questions"), "",
    msg("applications-interview-prompt-points"),
  ].join("\n") })]);
});

test("the Workspace's next steps are typed in place, listed soonest first, each done with its own tick, and Undo puts one back", async ({ page }) => {
  // A fixed clock: the month the day is picked from opens on the test's own.
  await page.clock.setFixedTime(new Date(2026, 10, 4, 10, 0));
  const { stepWrites } = await installPipeline(page);
  await page.goto("/company/stripe/job/202?tab=workspace");
  const cover = posting(page);
  const add = cover.getByRole("textbox", { name: msg("applications-ws-next-add") });
  await add.fill("Email the recruiter");
  await cover.getByRole("button", { name: msg("applications-next-save") }).click();
  const done = cover.getByRole("button", { name: msg("applications-upnext-done-label", { step: "Email the recruiter" }) });
  await expect(done).toBeVisible();
  // Said once: the main column holds it, so the side column's rows leave it out.
  await expect(cover.locator("dl.jd-pipeline-facts dt", { hasText: msg("applications-posting-next-step") })).toHaveCount(0);

  // A second step with a day goes above the one with none; the add line
  // stays under the last.
  await add.fill("Send the portfolio");
  // The day is picked from the month its field opens: December's first
  // stands in November's last week.
  await cover.getByRole("button", { name: new RegExp(`^${msg("applications-ws-next-due")} `) }).last().click();
  await page.getByRole("dialog", { name: msg("applications-ws-next-due") }).locator('[data-day="2026-12-01"]').click();
  await cover.getByRole("button", { name: msg("applications-next-save") }).click();
  const steps = cover.locator(".app-ws-step-list .app-ws-step-words");
  await expect(steps).toHaveText(["Send the portfolio", "Email the recruiter"]);
  const addBox = (await add.boundingBox())!;
  const lastBox = (await steps.last().boundingBox())!;
  expect(addBox.y, "the add line under the last step").toBeGreaterThan(lastBox.y + lastBox.height - 1);

  await done.click();
  await expect(steps).toHaveText(["Send the portfolio"]);
  await expect(cover.getByRole("button", { name: msg("applications-upnext-done-label", { step: "Send the portfolio" }) })).toBeFocused();
  await page.getByRole("button", { name: msg("applications-move-undo") }).click();
  await expect(steps).toHaveText(["Send the portfolio", "Email the recruiter"]);
  await expect.poll(() => stepWrites).toEqual([
    { add: { text: "Email the recruiter", due: null } },
    { add: { text: "Send the portfolio", due: expect.stringMatching(/^2026-12-0[12]T/) } },
    { 900: { done: true } },
    { 900: { done: false } },
  ]);
});

/** An application with `length` entries a day apart, newest now, whose move
 *  to Applied (event 201) is the entry 201 days back. */
async function installHistory(page: Page, length: number) {
  await installPipeline(page);
  const day = 86_400_000;
  const now = Date.now();
  const items = Array.from({ length }, (_, n) => n % 3 === 0
    ? { kind: "event", id: n, created_at: new Date(now - n * day).toISOString(), actor: "user", source: "app",
      event_type: "updated", from_stage: "networking", to_stage: n === 201 ? "applied" : "networking", changed: n === 201 ? ["stage"] : ["priority"] }
    : { kind: "comment", id: n, created_at: new Date(now - n * day).toISOString(), actor: "user", source: "app", body: `Note ${n}`, edited_at: null });
  await mockGet(page, "/api/applications/*/activity", (route) => route.fulfill({ json: { items } }));
  await mockGet(page, "/api/applications/101", (route) => route.fulfill({ json: applicationDetailFixture({
    application: cards[0],
    stages_reached: [{ stage: "applied", at: new Date(now - 201 * day).toISOString() }],
  }) }));
}

test("a long history keeps its month in view while it scrolls, and a jump lands its entry in view with focus", async ({ page, isMobile }) => {
  test.skip(isMobile, "phones are not supported: there a history this long does not draw in the time a test allows");
  // 300 entries a day apart, so the feed spans ten months.
  await installHistory(page, 300);
  await page.goto("/pipeline/101?tab=workspace");
  await expect(page.getByText("Note 299")).toBeAttached();

  // Scrolled deep into the feed, the divider of the month being read is the
  // one pinned at the top of the scroll, and nothing of the feed shows above it.
  await page.getByText("Note 100").scrollIntoViewIfNeeded();
  // A month's divider holds under the role's tabs.
  const top = await page.locator(".jd-tabs").evaluate((tabs) => tabs.getBoundingClientRect().bottom);
  const pinned = await page.locator(".app-feed-divider").evaluateAll((dividers, scrollTop) =>
    dividers.filter((divider) => Math.abs(divider.getBoundingClientRect().top - scrollTop) < 2).map((divider) => divider.textContent), top);
  expect(pinned, "one month's divider is held under the tabs").toHaveLength(1);

  await page.getByRole("button", { name: msg("applications-feed-jump-month", { month: pinned[0]! }) }).click();
  const menu = page.getByRole("dialog", { name: msg("applications-feed-jump-label") });
  await menu.getByRole("button", { name: new RegExp(msg("applications-feed-jump-applied")) }).click();

  const landed = page.locator('[data-feed~="event-201"]');
  await expect(landed).toBeFocused();
  await expect(landed).toBeInViewport();
  // It lands below its month's pinned divider, not under it.
  const [landedBox, dividerBox] = await Promise.all([
    landed.boundingBox(),
    landed.locator("xpath=ancestor::section[1]").locator(".app-feed-divider").boundingBox(),
  ]);
  expect(landedBox!.y).toBeGreaterThanOrEqual(dividerBox!.y + dividerBox!.height - 1);
});

test("under reduced motion a jump's ring holds still for a moment, then goes", async ({ page, isMobile }) => {
  test.skip(isMobile, "phones are not supported: there a history this long does not draw in the time a test allows");
  await page.emulateMedia({ reducedMotion: "reduce" });
  await installHistory(page, 240);
  await page.clock.install();
  await page.goto("/pipeline/101?tab=workspace");
  const [, tail] = msg("applications-feed-jump-month", { month: "\u0000" }).split("\u0000");
  const dividers = page.getByRole("button", { name: new RegExp(`${tail.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")}$`) });
  await expect(dividers.first()).toBeVisible();
  // The page's clock stops here, so only runFor moves the ring's timer.
  await page.clock.pauseAt(new Date(Date.now() + 60_000));
  await dividers.first().click();
  await page.getByRole("dialog", { name: msg("applications-feed-jump-label") })
    .getByRole("button", { name: new RegExp(msg("applications-feed-jump-applied")) }).click();

  const landed = page.locator('[data-feed~="event-201"]');
  await expect(landed).toBeFocused();
  // The ring's opacity, or 0 once it is gone.
  const ring = () => landed.evaluate((entry) => {
    const after = getComputedStyle(entry, "::after");
    return after.content === "none" ? 0 : Number(after.opacity);
  });
  expect(await ring(), "the ring is there on landing").toBe(1);
  await page.clock.runFor(2_000);
  expect(await ring(), "the ring holds still for two seconds").toBe(1);
  await page.clock.runFor(500);
  await expect.poll(ring).toBe(0);
  await expect(landed).toBeFocused();
});

test("Up next lists what is due by day, overdue first, and a row opens its application", async ({ page }) => {
  const day = 86_400_000;
  await installPipeline(page, [
    { ...cards[0], next_action: "Ask for an intro", next_action_due: new Date(Date.now() - 2 * day).toISOString() },
    { ...cards[1], next_interview: {
      id: 5, label: "Hiring manager call", scheduled_at: new Date(Date.now() + 5 * day).toISOString(), all_day: false,
      format: "video", link: null,
    } },
    cards[2],
  ]);
  await page.goto("/pipeline/board");
  await page.getByRole("tab", { name: msg("shell-tab-pipeline-up-next") }).click();
  await expect(page).toHaveURL(/\/pipeline\/up-next$/);

  const days = page.getByRole("region");
  await expect(days.first()).toHaveAccessibleName(msg("applications-upnext-overdue"));
  await expect(days.first().getByText("Ask for an intro")).toBeVisible();
  await expect(days.nth(1).getByText("Hiring manager call")).toBeVisible();

  // A day's heading is a date the person reads: title size, in its own case,
  // and the role under a step reads in the step's own ink.
  const look = await days.first().evaluate((day) => {
    const heading = getComputedStyle(day.querySelector("h2")!);
    return {
      size: heading.fontSize, title: heading.getPropertyValue("--app-type-title").trim(), transform: heading.textTransform,
      role: getComputedStyle(day.querySelector(".app-upnext-title")!).color,
      step: getComputedStyle(day.querySelector(".app-upnext-name")!).color,
    };
  });
  expect(look.size, "the day's heading is at title size").toBe(look.title);
  expect(look.transform, "in its own case").toBe("none");
  expect(look.role, "the role's name in the text's ink").toBe(look.step);

  await days.nth(1).getByRole("link").click();
  // From Up next a role opens on its Workspace, over Up next, and Back says so.
  await expect(page).toHaveURL(/\/company\/stripe\/job\/202\?tab=workspace$/);
  await expect(posting(page).getByRole("heading", { level: 1 })).toHaveText("Principal Engineering Manager");
  await expect(posting(page).getByRole("button", { name: msg("role-job-detail-back-to", { view: msg("shell-tab-pipeline-up-next") }) }))
    .toBeVisible();
});

test("Up next stands beside its month: a day says what is on it, and picking one brings it into view in Up next, marked", async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 700 });
  // A fixed clock: the month and its days are the test's, whatever day it runs.
  await page.clock.setFixedTime(new Date(2026, 10, 4, 10, 0));
  // A week of steps fills Up next past the window's foot, so a later day has
  // to be scrolled to.
  const filler = Array.from({ length: 7 }, (_, i) => applicationCardFixture({
    job_id: 600 + i, pursuit_id: 60 + i, stage: "researching", title: `Role ${i + 1}`, company: "notion",
    next_action: `Step ${i + 1}`, next_action_due: new Date(2026, 10, 8 + i, 23, 59).toISOString(),
  }));
  const intro = applicationCardFixture({
    job_id: 101, title: "Staff Product Manager, API", company: "openai",
    next_action: "Ask for an intro", next_action_due: new Date(2026, 10, 7, 23, 59).toISOString(),
  });
  await installPipeline(page, [
    intro,
    { ...cards[1], next_interview: {
      id: 5, label: "Hiring manager call", scheduled_at: new Date(2026, 10, 20, 14, 0).toISOString(), all_day: false,
      format: "video", link: null,
    } },
    cards[2],
    ...filler,
  ]);
  // The month's read, with a round already held: that one is the month's
  // alone, since Up next lists what is ahead.
  await mockGet(page, "/api/applications/calendar**", (route) => route.fulfill({ json: { items: [
    {
      kind: "interview", job_id: 202, at: new Date(2026, 10, 2, 15, 0).toISOString(), interview_id: 3,
      label: "Recruiter screen", all_day: false, format: "video", outcome: "passed",
    },
    // Each open step as the server sends it, by the id its card lists.
    ...[intro, ...filler].map((card) => ({
      kind: "step", job_id: card.job_id, at: card.steps[0].due, step: card.steps[0].text, step_id: card.steps[0].id,
    })),
    {
      kind: "interview", job_id: 202, at: new Date(2026, 10, 20, 14, 0).toISOString(), interview_id: 5,
      label: "Hiring manager call", all_day: false, format: "video", outcome: null,
    },
  ] } }));
  await page.goto("/pipeline/up-next");

  const month = page.getByRole("region", { name: msg("applications-month-label") });
  await expect(month.getByRole("heading", { level: 2 })).toHaveText(/November 2026/i);
  const target = month.getByRole("button", { name: `Fri, Nov 20: ${msg("applications-month-interviews", { count: 1 })}` });
  await expect(target).toBeVisible();
  await expect(month.getByRole("button", { name: `Sat, Nov 7: ${msg("applications-month-steps", { count: 1 })}` })).toBeVisible();
  await expect(month.getByRole("button", { name: /^Wed, Nov 4/ })).toHaveAttribute("aria-current", "date");

  // The month takes the right side the list left empty, level with it.
  const list = page.getByRole("region", { name: "Sat, Nov 7" });
  const [listBox, monthBox] = [await list.boundingBox(), await month.boundingBox()];
  expect(monthBox!.x, "the month stands right of the list").toBeGreaterThan(listBox!.x + listBox!.width);
  expect(monthBox!.x + monthBox!.width, "and inside the window").toBeLessThanOrEqual(1440);
  expect(await page.evaluate(() => document.documentElement.scrollWidth), "the page never widens").toBeLessThanOrEqual(1440);

  const day = page.locator("section.app-upnext-day").filter({ hasText: "Hiring manager call" });
  const row = day.locator(".app-upnext-item");
  await expect(day, "the day starts below the window").not.toBeInViewport();
  await target.click();
  await expect(target).toHaveAttribute("aria-pressed", "true");
  // The picked day and today are circles, as in the interview form: the
  // ring round today is the circle itself, and a day's marks stay inside it.
  for (const button of [target, month.getByRole("button", { name: /^Wed, Nov 4/ })]) {
    const shape = await button.evaluate((el) => {
      const box = el.getBoundingClientRect();
      const num = el.querySelector(".app-month-num")!.getBoundingClientRect();
      const marks = [...el.querySelectorAll(".app-month-mark")].map((mark) => mark.getBoundingClientRect());
      return {
        width: box.width, height: box.height, radius: parseFloat(getComputedStyle(el).borderTopLeftRadius),
        ring: Math.abs(num.width - box.width) <= 2 && Math.abs(num.height - box.height) <= 2,
        marks: marks.length,
        inside: marks.every((mark) => mark.top >= box.top && mark.bottom <= box.bottom && mark.left >= box.left && mark.right <= box.right),
      };
    });
    expect(Math.abs(shape.width - shape.height), "as tall as it is wide").toBeLessThanOrEqual(0.5);
    expect(shape.radius, "and round").toBeGreaterThanOrEqual(shape.width / 2);
    expect(shape.ring, "the number's ring is the circle").toBe(true);
    expect(shape.inside, "its marks inside it").toBe(true);
  }
  await expect(day).toBeInViewport();
  await expect(row).toHaveAttribute("data-picked", "true");
  await expect(page.locator(".app-upnext-item[data-picked]")).toHaveCount(1);
  // Marked with the chosen wash, as a picked day in the grid is.
  expect(await row.evaluate((el) => getComputedStyle(el).backgroundColor)).not.toBe("rgba(0, 0, 0, 0)");
  // Up next answers the day, so the grid lists nothing under it.
  await expect(month.getByRole("heading", { level: 3 })).toHaveCount(0);
  // The month stays beside the list while it scrolls.
  await expect(target).toBeInViewport();

  // A past round is the month's alone: it is listed under the grid, with its outcome.
  await month.getByRole("button", { name: /^Mon, Nov 2: / }).click();
  await expect(page.locator(".app-upnext-item[data-picked]")).toHaveCount(0);
  await expect(month.getByText(msg("applications-upnext-interview", { label: "Recruiter screen" }))).toBeVisible();
  await expect(month.getByText(msg("applications-interview-outcome-passed"))).toBeVisible();
  await month.getByRole("link", { name: /Principal Engineering Manager/ }).click();
  await expect(page).toHaveURL(/\/job\/202\?tab=workspace$/);
});

test("the month pages to the next one with its own read, and a filter leaves the same roles out of it", async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.clock.setFixedTime(new Date(2026, 10, 4, 10, 0));
  await installPipeline(page, [
    { ...cards[0], next_action: "Ask for an intro", next_action_due: new Date(2026, 11, 3, 23, 59).toISOString() },
    { ...cards[1], next_interview: {
      id: 5, label: "Hiring manager call", scheduled_at: new Date(2026, 11, 8, 14, 0).toISOString(), all_day: false,
      format: "video", link: null,
    } },
    cards[2],
  ]);
  const spans: string[] = [];
  page.on("request", (request) => {
    const url = new URL(request.url());
    if (url.pathname === "/api/applications/calendar") spans.push(url.searchParams.get("start")!);
  });
  await page.goto("/pipeline/up-next");
  const month = page.getByRole("region", { name: msg("applications-month-label") });
  await expect(month.getByRole("button", { name: /^Wed, Nov 4/ })).toBeVisible();

  await month.getByRole("button", { name: msg("applications-month-next") }).click();
  await expect(month.getByRole("heading", { level: 2 })).toHaveText(/December 2026/i);
  await expect(month.getByRole("button", { name: `Tue, Dec 8: ${msg("applications-month-interviews", { count: 1 })}` })).toBeVisible();
  // Each month reads its own grid: November's from 26 October, December's from 30 November.
  await expect.poll(() => [...new Set(spans.map((at) => new Date(at).getDate()))]).toEqual([26, 30]);

  // The search narrows the month as it narrows the list: only Stripe's round stays.
  await page.getByRole("searchbox").fill("stripe");
  await expect(month.getByRole("button", { name: "Thu, Dec 3", exact: true })).toBeVisible();
  await expect(month.getByRole("button", { name: `Tue, Dec 8: ${msg("applications-month-interviews", { count: 1 })}` })).toBeVisible();
});

/** Whether a field's edge is the danger colour of the surface it sits on. */
const dangerEdge = (field: Locator) => field.evaluate((el) => {
  const probe = document.createElement("span");
  probe.style.color = "var(--app-danger)";
  el.parentElement!.appendChild(probe);
  const danger = getComputedStyle(probe).color;
  probe.remove();
  return getComputedStyle(el).borderTopColor === danger;
});

test("moving into Interviewing asks when the interview is, and records it with the move", async ({ page, isMobile }) => {
  test.skip(isMobile, "phones are not supported: there the form's Save does not land");
  // A fixed clock: the month the form opens on is the test's.
  await page.clock.setFixedTime(new Date(2026, 10, 4, 10, 0));
  const { stageWrites, interviews } = await installPipeline(page);
  await page.goto("/pipeline/board");

  await menuButton(page, "Principal Engineering Manager").click();
  await menu(page, "Principal Engineering Manager").getByRole("button", { name: "Interviewing" }).click();
  const dialog = page.getByRole("dialog", { name: msg("applications-interview-title") });
  await expect(dialog).toBeVisible();
  expect(stageWrites).toEqual([]);

  await dialog.getByRole("button", { name: "Thu, Nov 12", exact: true }).click();
  // Only the picked day wears a circle; today, the 4th, is marked by its
  // number alone, so the month never looks as if two days were picked.
  // Polled: the picked day's wash fades in.
  await expect.poll(() => dialog.locator(".app-month-day").evaluateAll((days) => days
    .filter((day) => [day, day.querySelector(".app-month-num")!].some((part) => {
      const style = getComputedStyle(part);
      const clear = (colour: string) => colour === "transparent" || /rgba\(.*,\s*0\)$/.test(colour);
      return !clear(style.backgroundColor) || !clear(style.borderTopColor);
    }))
    .map((day) => day.getAttribute("aria-label")))).toEqual(["Thu, Nov 12"]);
  const today = dialog.locator('.app-month-day[aria-current="date"] .app-month-num');
  await expect(today).toHaveText("4");
  await expect(today).toHaveCSS("text-decoration-line", "underline");

  // A time it cannot read and a link with no scheme hold the move, and each
  // field's own edge says which: the form's field style does not hide it.
  const save = dialog.getByRole("button", { name: msg("applications-interview-submit", { stage: "Interviewing" }) });
  const time = dialog.getByLabel(msg("applications-interview-time"), { exact: true });
  await time.fill("25:00");
  await dialog.getByRole("button", { name: msg("applications-interview-format-video"), exact: true }).click();
  const link = dialog.getByLabel(msg("applications-interview-link"), { exact: true });
  await link.fill("meet.google.com/abc-defg-hij");
  await save.click();
  await expect(dialog.getByText(msg("applications-interview-link-invalid"))).toBeVisible();
  for (const field of [time, link]) {
    await expect(field).toHaveAttribute("aria-invalid", "true");
    await expect.poll(() => dangerEdge(field)).toBe(true);
  }
  expect(stageWrites).toEqual([]);
  expect(interviews).toEqual([]);
  await link.fill("https://meet.google.com/abc-defg-hij");

  const times = dialog.getByRole("group", { name: msg("applications-interview-times") });
  await times.getByRole("button", { name: "2:00 PM", exact: true }).click();
  await expect(dialog.locator(".app-interview-summary")).toHaveText("Thu, Nov 12 · 2:00 PM");
  await save.click();

  await expect(column(page, "Interviewing").getByText("Principal Engineering Manager")).toBeVisible();
  await expect.poll(() => interviews.length).toBe(1);
  expect(stageWrites).toEqual([{ jobId: 202, stage: "interviewing" }]);
  expect(interviews[0]).toMatchObject({
    label: msg("applications-interview-default-label"),
    all_day: false,
    format: "video",
    link: "https://meet.google.com/abc-defg-hij",
  });
  const sent = new Date(interviews[0].scheduled_at);
  expect([sent.getFullYear(), sent.getMonth(), sent.getDate(), sent.getHours()]).toEqual([2026, 10, 12, 14]);
});

test("the interview form fits the window: the times beside the month on a laptop, under it on a phone, and Save always in view", async ({ page, isMobile }) => {
  test.skip(isMobile, "phones are not supported: on the phone device the form's opening never settles");
  // The real clock: a fixed one would hold the dialog's opening animation still.
  await installPipeline(page);
  const openForm = async () => {
    await page.goto("/pipeline/board");
    await menuButton(page, "Principal Engineering Manager").click();
    await menu(page, "Principal Engineering Manager").getByRole("button", { name: "Interviewing" }).click();
    const dialog = page.getByRole("dialog", { name: msg("applications-interview-title") });
    await expect(dialog).toBeVisible();
    // It opens with a small scale-in: measure once it has settled.
    await expect.poll(() => dialog.evaluate((el) => el.getAnimations().every((one) => one.playState === "finished"))).toBe(true);
    return dialog;
  };
  // The 15% zoom leaves edges on fractions of a pixel, and WebKit reports a
  // button flush with the window as 0.9999 inside it.
  const inView = (target: Locator) => expect(target).toBeInViewport({ ratio: 0.99 });
  const parts = (dialog: Locator) => ({
    month: dialog.locator(".app-month-grid"),
    times: dialog.getByRole("group", { name: msg("applications-interview-times") }),
    save: dialog.getByRole("button", { name: msg("applications-interview-submit", { stage: "Interviewing" }) }),
  });

  // A laptop: the form drawn 15% larger, whole in view, the times as tall as the month beside it.
  await page.setViewportSize({ width: 1440, height: 900 });
  let dialog = await openForm();
  let { month, times, save } = parts(dialog);
  const box = (await dialog.boundingBox())!;
  expect(box.width, "the dialog's width, 560 drawn 15% larger").toBeCloseTo(644, 0);
  const [monthBox, timesBox] = [(await month.boundingBox())!, (await times.boundingBox())!];
  expect(timesBox.x, "the times stand right of the month").toBeGreaterThan(monthBox.x + monthBox.width);
  expect(timesBox.y + timesBox.height, "and end with it").toBeLessThanOrEqual(monthBox.y + monthBox.height + 2);
  await inView(save);
  expect(box.y + box.height, "nothing to scroll to reach Save").toBeLessThanOrEqual(900);

  // One shape per kind: a day is a circle, the plus a chip as tall as the
  // rounds beside it, and the time's label shares a line with the month's name.
  const day = (await dialog.locator(".app-month-day").first().boundingBox())!;
  expect(day.width, "a day is as wide as it is tall").toBeCloseTo(day.height, 0);
  const rounds = dialog.getByRole("group", { name: msg("applications-interview-round") });
  const chip = (await rounds.getByRole("button", { name: msg("applications-interview-round-final") }).boundingBox())!;
  const plus = (await rounds.getByRole("button", { name: msg("applications-interview-round-add") }).boundingBox())!;
  expect(plus.height, "the plus is as tall as a chip").toBeCloseTo(chip.height, 0);
  expect(plus.width, "and round").toBeCloseTo(plus.height, 0);
  const centre = (b: { y: number; height: number }) => b.y + b.height / 2;
  const monthName = (await dialog.locator(".app-daypicker-title").boundingBox())!;
  const timeLabel = (await dialog.getByText(msg("applications-interview-time"), { exact: true }).boundingBox())!;
  expect(Math.abs(centre(timeLabel) - centre(monthName)), "the time's label is level with the month's name").toBeLessThanOrEqual(2);

  // Paging the months moves nothing: February's four weeks take as much room as November's six.
  const heightOf = async () => (await month.boundingBox())!.height;
  const november = await heightOf();
  for (let step = 0; step < 3; step++) await dialog.getByRole("button", { name: msg("applications-month-next") }).click();
  await expect(dialog.getByText("February 2027")).toBeVisible();
  expect(await heightOf(), "February's grid").toBe(november);
  expect((await dialog.boundingBox())!.height, "the dialog's height").toBe(box.height);

  // A short window: the middle scrolls, the head and Save hold still.
  await page.setViewportSize({ width: 1280, height: 520 });
  ({ save } = parts(dialog));
  await inView(save);
  const body = dialog.locator(".app-interview-body");
  expect(await body.evaluate((el) => el.scrollHeight > el.clientHeight), "the middle scrolls").toBe(true);
  await body.evaluate((el) => el.scrollTo(0, el.scrollHeight));
  await inView(save);
  await inView(dialog.locator(".app-interview-summary"));

  // A phone: the times under the month, nothing wider than the screen, Save in reach.
  await page.setViewportSize({ width: 375, height: 667 });
  dialog = await openForm();
  ({ month, times, save } = parts(dialog));
  const [phoneMonth, phoneTimes] = [(await month.boundingBox())!, (await times.boundingBox())!];
  expect(phoneTimes.y, "the times sit under the month").toBeGreaterThan(phoneMonth.y + phoneMonth.height);
  expect((await dialog.boundingBox())!.width, "the dialog keeps a margin").toBeLessThanOrEqual(375 - 32);
  expect(await page.evaluate(() => document.documentElement.scrollWidth), "the page never widens").toBeLessThanOrEqual(375);
  await inView(save);
});

test("a column hidden from its menu takes no room, stays hidden after a reload, and comes back from Columns", async ({ page }) => {
  await installPipeline(page);
  await page.goto("/pipeline/board");
  const closedName = msg("applications-column-closed");

  await page.getByRole("button", { name: msg("applications-column-menu", { column: closedName }) }).click();
  await page.getByRole("button", { name: msg("applications-column-hide") }).click();
  await expect(column(page, closedName)).toHaveCount(0);
  // Nothing stands in for it: Decided is now the board's last column.
  await expect(page.locator(".app-board > :last-child")).toHaveAttribute("aria-labelledby", "app-column-decided");

  await page.reload();
  await expect(column(page, "Considering").getByText("Staff Product Manager, API")).toBeVisible();
  await expect(page.getByText("Head of Platform")).toHaveCount(0);
  const columns = page.getByRole("button", { name: msg("applications-columns-hidden", { count: 1 }) });
  await columns.click();
  await page.getByRole("dialog", { name: msg("applications-columns") })
    .getByRole("checkbox", { name: new RegExp(`^${closedName}`) }).check();
  await expect(column(page, closedName).getByText("Head of Platform")).toBeVisible();
});

/** Where the shown columns sit against the board's scroller. */
async function columnFit(page: Page) {
  return page.evaluate(() => {
    const scroller = document.querySelector(".app-board-scroll")!;
    const box = scroller.getBoundingClientRect();
    const columns = [...document.querySelectorAll(".app-column")].map((one) => one.getBoundingClientRect());
    return {
      startGap: columns[0].left - box.left,
      endGap: box.right - columns[columns.length - 1].right,
      widths: columns.map((one) => one.width),
      scrolls: scroller.scrollWidth > scroller.clientWidth + 1,
    };
  });
}

test("the columns shown share the board's width, and never shrink below their floor", async ({ page }, testInfo) => {
  test.skip(testInfo.project.name === "mobile", "a desktop layout: the phone width is the floor case, checked below at 1280");
  await installPipeline(page);
  await page.setViewportSize({ width: 2000, height: 1000 });
  await viewChoices(page, { "pipeline.board-hidden": ["decided", "closed"] });
  await page.goto("/pipeline/board");
  await expect(column(page, "Considering").getByText("Staff Product Manager, API")).toBeVisible();

  // Five columns at 2000px: they run from the board's left edge to its right
  // one, all the same width, wider than the floor, with nothing left over.
  const five = await columnFit(page);
  expect(five.widths).toHaveLength(5);
  expect(Math.abs(five.startGap)).toBeLessThanOrEqual(1);
  expect(Math.abs(five.endGap)).toBeLessThanOrEqual(1);
  expect(Math.max(...five.widths) - Math.min(...five.widths)).toBeLessThanOrEqual(1);
  expect(Math.min(...five.widths)).toBeGreaterThan(300);
  expect(five.scrolls).toBe(false);

  // Showing a column back takes its share from the others.
  await page.getByRole("button", { name: msg("applications-columns-hidden", { count: 2 }) }).click();
  await page.getByRole("dialog", { name: msg("applications-columns") })
    .getByRole("checkbox", { name: msg("applications-column-decided") }).check();
  await page.keyboard.press("Escape");
  const six = await columnFit(page);
  expect(six.widths).toHaveLength(6);
  expect(Math.abs(six.endGap)).toBeLessThanOrEqual(1);
  expect(Math.max(...six.widths)).toBeLessThan(Math.min(...five.widths));

  // Every column at 1280px: the floor holds and the board scrolls instead.
  await page.setViewportSize({ width: 1280, height: 900 });
  await page.getByRole("button", { name: msg("applications-columns-hidden", { count: 1 }) }).click();
  await page.getByRole("button", { name: msg("applications-columns-show-all") }).click();
  await page.keyboard.press("Escape");
  const seven = await columnFit(page);
  expect(seven.widths).toHaveLength(7);
  expect(seven.widths.every((width) => Math.round(width) === 252)).toBe(true);
  expect(seven.scrolls).toBe(true);
});

test("a filter lives in the address: it survives opening a card and coming back, and / goes to the search", async ({ page }) => {
  await installPipeline(page);
  await page.goto("/pipeline/board");
  await expect(column(page, "Considering").getByText("Staff Product Manager, API")).toBeVisible();

  await page.getByRole("button", { name: msg("shared-filters") }).click();
  await page.getByRole("dialog", { name: msg("applications-filter-menu") })
    .getByRole("checkbox", { name: new RegExp(`^${msg("applications-quick-needs-next")}`) }).click();
  await page.keyboard.press("Escape");
  await expect(page).toHaveURL(/\/pipeline\/board\?only=needs_next$/);
  await expect(page.getByText("Staff Product Manager, API")).toHaveCount(0);
  await expect(column(page, "Applied").getByText(msg("applications-column-count-of", { count: 1, total: 1 }))).toBeVisible();

  await page.getByText("Principal Engineering Manager").click();
  await expect(page).toHaveURL(/\/job\/202\?tab=workspace$/);
  await page.goBack();
  await expect(page).toHaveURL(/only=needs_next/);
  await expect(page.getByText("Staff Product Manager, API")).toHaveCount(0);

  await page.getByRole("button", { name: msg("applications-filter-highlight-instead") }).click();
  await expect(page.locator(".app-tile", { hasText: "Staff Product Manager, API" })).toHaveAttribute("data-match", "false");
  await expect(page.locator(".app-tile", { hasText: "Principal Engineering Manager" })).toHaveAttribute("data-match", "true");

  await page.locator("body").press("/");
  await expect(page.getByRole("searchbox", { name: msg("applications-search-label") })).toBeFocused();
});

test("switching between List, Board and Up next keeps the header still and reads the pipeline once", async ({ page }) => {
  await installPipeline(page);
  // A slow read: a tab switch that rebuilt the screen would wait on it with
  // the counts line missing, and the tabs would sit higher until it landed.
  const reads = watchReads(page, "GET", "/api/applications");
  await mockGet(page, "/api/applications", async (route) => {
    await new Promise((resolve) => setTimeout(resolve, 400));
    await route.fallback();
  });
  await page.goto("/pipeline/list");
  await expect(page.getByRole("link", { name: "Staff Product Manager, API" })).toBeVisible();
  const tabs = page.getByRole("tablist", { name: msg("applications-tabs-label") });
  const resting = (await tabs.boundingBox())!.y;
  const started = reads.started;

  for (const name of [msg("shell-tab-pipeline-board"), msg("shell-tab-pipeline-up-next"), msg("shell-tab-pipeline-list")]) {
    await page.evaluate(() => {
      const w = window as unknown as { tops: number[]; sampler: number };
      w.tops = [];
      w.sampler = window.setInterval(() => {
        const list = document.querySelector('[role="tablist"]');
        w.tops.push(list ? list.getBoundingClientRect().top : -1);
      }, 4);
    });
    await page.getByRole("tab", { name }).click();
    await expect(page.getByRole("tab", { name })).toHaveAttribute("aria-selected", "true");
    await frames(page, 36);
    const tops = await page.evaluate(() => {
      const w = window as unknown as { tops: number[]; sampler: number };
      window.clearInterval(w.sampler);
      return [...new Set(w.tops.map(Math.round))];
    });
    expect(tops, `the tabs moved while ${name} opened`).toEqual([Math.round(resting)]);
  }
  expect(reads.started, "a tab switch reads the pipeline again").toBe(started);
  expect(reads.answered).toBe(1);
});

test("the Pipeline's views and their tools share one row at the page's top, and the content starts right under it", async ({ page }, testInfo) => {
  test.skip(testInfo.project.name === "mobile", "On a phone the views keep a line of their own above the tools.");
  await installPipeline(page);
  await page.setViewportSize({ width: 1440, height: 900 });
  for (const [view, content] of [["board", ".app-board"], ["list", ".app-list-host"], ["up-next", ".app-upnext-split"]] as const) {
    await page.goto(`/pipeline/${view}`);
    await expect(page.locator(content)).toBeVisible();
    const seen = await page.evaluate((content) => {
      const middle = (selector: string) => {
        const box = document.querySelector(selector)!.getBoundingClientRect();
        return Math.round(box.top + box.height / 2);
      };
      const top = (selector: string) => Math.round(document.querySelector(selector)!.getBoundingClientRect().top);
      return {
        tab: middle('[role="tab"][aria-selected="true"]'),
        search: middle(".app-pipeline-search"),
        tools: middle(".app-pipeline-tools"),
        row: top(".app-pipeline-toolbar") - top("main"),
        content: top(content) - top("main"),
      };
    }, content);
    expect([seen.search, seen.tools], `${view}: the views and the tools share one centre line`).toEqual([seen.tab, seen.tab]);
    expect(seen.row, `${view}: nothing stands above the row`).toBe(0);
    expect(seen.content, `${view}: the content starts within 100px of the page's top`).toBeLessThan(100);
  }
});

test("the row stays one line where the views' names are long, in a window as narrow as a desktop's gets", async ({ page }, testInfo) => {
  test.skip(testInfo.project.name === "mobile", "On a phone the views keep a line of their own above the tools.");
  await installPipeline(page);
  // Spanish names the views at greater length than English does.
  await page.route("/api/settings/locale", (route) => route.fulfill({ json: { language: "es", region: null } }));
  for (const width of [1100, 900]) {
    await page.setViewportSize({ width, height: 700 });
    await page.goto("/pipeline/board");
    await expect(page.getByRole("tab", { selected: true })).toHaveText("Tablero");
    const lines = await page.evaluate(() => [".app-tabbar", ".app-pipeline-search", ".app-pipeline-tools"].map((selector) => {
      const box = document.querySelector(selector)!.getBoundingClientRect();
      return Math.round(box.top + box.height / 2);
    }));
    expect(new Set(lines).size, `${width} wide: the views, the search and the menus share one line (${lines.join(", ")})`).toBe(1);
    const [search, tools] = [(await page.locator(".app-pipeline-search").boundingBox())!, (await page.locator(".app-pipeline-tools").boundingBox())!];
    expect(search.width, `${width} wide: the search keeps room to type in`).toBeGreaterThanOrEqual(120);
    expect(tools.x + tools.width, `${width} wide: nothing runs past the row`).toBeLessThanOrEqual(width);
  }
});

test("a filter takes a line under the row and moves nothing in it, and a word typed fast keeps every letter", async ({ page }, testInfo) => {
  test.skip(testInfo.project.name === "mobile", "One desktop geometry is the claim.");
  await installPipeline(page);
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.goto("/pipeline/board");
  const tab = page.getByRole("tab", { name: msg("shell-tab-pipeline-board") });
  const search = page.getByRole("searchbox", { name: msg("applications-search-label") });
  await expect(search).toBeVisible();
  // The views stay where they are and the tools keep their line; along it the
  // search gives room to the two ways out that come beside it.
  const place = async () => {
    const [views, field] = [(await tab.boundingBox())!, (await page.locator(".app-pipeline-search").boundingBox())!];
    return [Math.round(views.x), Math.round(views.y), Math.round(field.y), Math.round(field.height)];
  };
  const resting = await place();

  await page.getByRole("button", { name: msg("shared-filters") }).click();
  await page.getByRole("dialog", { name: msg("applications-filter-menu") })
    .getByRole("checkbox", { name: new RegExp(`^${msg("applications-quick-needs-next")}`) }).click();
  await page.keyboard.press("Escape");
  const chip = page.getByRole("button", { name: msg("applications-filter-remove", { filter: msg("applications-quick-needs-next") }) });
  await expect(chip).toBeVisible();
  expect((await chip.boundingBox())!.y, "the chip stands under the row").toBeGreaterThan((await tab.boundingBox())!.y + (await tab.boundingBox())!.height);
  expect(await place(), "the row moved when the filter came").toEqual(resting);

  // No pause between keys: each arrives before the address has taken the one before.
  await search.pressSequentially("principal");
  await expect(search).toHaveValue("principal");
  await expect(page).toHaveURL(/[?&]q=principal(&|$)/);
  await expect(search, "the address catching up does not rewind the field").toHaveValue("principal");
});

test("Up next scrolls under the row, which stays at the page's top with its views", async ({ page }, testInfo) => {
  test.skip(testInfo.project.name === "mobile", "Below 860 the row does not dock.");
  const steps = Array.from({ length: 14 }, (_, index) => applicationCardFixture({
    job_id: 700 + index, pursuit_id: 70 + index, title: `Dated role ${index + 1}`, company: "openai", stage: "applied",
    next_action: `Step ${index + 1}`, next_action_due: new Date(Date.now() + (index + 1) * 86_400_000).toISOString(),
  }));
  await installPipeline(page, steps);
  await page.setViewportSize({ width: 1280, height: 520 });
  await page.goto("/pipeline/up-next");
  await expect(page.getByText("Step 1", { exact: true })).toBeVisible();
  const main = page.locator("main");
  const row = page.locator(".app-pipeline-toolbar");
  const top = Math.round((await main.boundingBox())!.y);
  await main.evaluate((node) => node.scrollTo({ top: 400 }));
  await expect.poll(() => main.evaluate((node) => node.scrollTop)).toBeGreaterThan(100);
  expect(Math.round((await row.boundingBox())!.y), "the row left the page's top").toBe(top);
  await expect(page.getByRole("tablist", { name: msg("applications-tabs-label") })).toBeInViewport();
  await expect(page.getByText("Step 1", { exact: true }), "the list scrolled under the row").not.toBeInViewport();
});

/** A control's opacity once any fade on it has landed. */
const seen = (control: Locator) => control.evaluate(async (el) => {
  getComputedStyle(el).opacity;
  await Promise.all(el.getAnimations().map((animation) => animation.finished.catch(() => {})));
  return getComputedStyle(el).opacity;
});

test("the Board's lanes are open: a card is the only box, and a card's and a lane's menu wait for the pointer or the keyboard", async ({ page }, testInfo) => {
  test.skip(testInfo.project.name === "mobile", "Where nothing hovers the menus always show.");
  await installPipeline(page);
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.goto("/pipeline/board");
  const lane = column(page, "Applied");
  const tile = lane.locator(".app-tile").first();
  await expect(tile).toBeVisible();
  await page.mouse.move(0, 0);
  const box = (node: Locator) => node.evaluate((el) => {
    const style = getComputedStyle(el);
    return { fill: style.backgroundColor, edge: style.boxShadow, border: parseFloat(style.borderTopWidth) };
  });
  expect(await box(lane), "a lane has no fill and no edge at rest").toEqual({ fill: "rgba(0, 0, 0, 0)", edge: "none", border: 0 });
  expect((await box(tile)).border, "the card is the box").toBeGreaterThan(0);

  const menu = tile.locator(".app-tile-menu");
  const laneMenu = lane.locator(".app-column-menu");
  expect([await seen(menu), await seen(laneMenu)], "nothing to press on a card or a lane at rest").toEqual(["0", "0"]);
  await tile.hover();
  await expect.poll(() => seen(menu), "under the pointer the card's menu shows").toBe("1");
  await expect.poll(() => seen(laneMenu), "and its lane's").toBe("1");
  await page.mouse.move(0, 0);
  await expect.poll(() => seen(menu)).toBe("0");

  // The keyboard reaches it as it reaches any button, and it shows while it holds the focus.
  await menu.focus();
  await expect.poll(() => seen(menu), "focused, the menu shows").toBe("1");
  // Open, it stays while the pointer is elsewhere.
  await menu.click();
  await expect(menu).toHaveAttribute("aria-expanded", "true");
  await page.mouse.move(0, 0);
  await expect.poll(() => seen(menu), "open, it stays").toBe("1");
});

test("Up next asks a past interview once, with the three outcomes behind the question, and a row's calendar tool waits for the pointer or the keyboard", async ({ page }, testInfo) => {
  test.skip(testInfo.project.name === "mobile", "Where nothing hovers the tools always show.");
  const soon = new Date(Date.now() + 3 * 86_400_000);
  soon.setHours(14, 0, 0, 0);
  const past = new Date(Date.now() - 2 * 86_400_000);
  past.setHours(14, 0, 0, 0);
  await installPipeline(page, [
    { ...cards[1], next_interview: { id: 41, label: "Hiring manager", scheduled_at: soon.toISOString(), all_day: false, format: "video", link: null } },
    applicationCardFixture({
      job_id: 808, pursuit_id: 80, stage: "interviewing", title: "Panel role", company: "openai",
      awaiting_outcome: { id: 42, label: "Panel", scheduled_at: past.toISOString(), all_day: false, format: null, link: null },
    }),
  ]);
  const outcomes: unknown[] = [];
  await mockApi(page, "PATCH", "/api/jobs/808/pursuit/interviews/42", async (route, request) => {
    outcomes.push(request.postDataJSON());
    await route.fulfill({ json: { interview: { id: 42, label: "Panel", scheduled_at: past.toISOString(), all_day: false, format: null, link: null,
      notes: null, outcome: "passed", created_at: past.toISOString(), updated_at: new Date().toISOString() } } });
  });
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.goto("/pipeline/up-next");
  const row = (text: string) => page.locator(".app-upnext-item", { hasText: text });
  await expect(row("Panel role")).toBeVisible();
  await page.mouse.move(0, 0);

  // The group is named for what it holds, so the question is asked once, in its row.
  await expect(page.getByRole("heading", { name: msg("applications-upnext-outcome") })).toHaveText("Past interviews");
  const ask = row("Panel role").getByRole("button", { name: msg("applications-ws-ask-outcome") });
  await expect(row("Panel role").getByRole("button")).toHaveCount(1);
  expect(await ask.evaluate((el) => getComputedStyle(el).borderTopColor), "a question, with no box at rest").toBe("rgba(0, 0, 0, 0)");

  // A coming interview's way to a calendar file is the row's own tool.
  const calendar = row("Hiring manager").getByRole("button", { name: msg("applications-interview-calendar-label", { label: "Hiring manager" }) });
  expect(await seen(calendar), "unseen at rest").toBe("0");
  await row("Hiring manager").hover();
  await expect.poll(() => seen(calendar), "under the pointer").toBe("1");
  await page.mouse.move(0, 0);
  await calendar.focus();
  await expect.poll(() => seen(calendar), "holding the focus").toBe("1");
  const [when, tool] = [(await row("Hiring manager").locator(".app-upnext-when").boundingBox())!, (await calendar.boundingBox())!];
  expect(tool.x + tool.width, "before the time, so every row's time ends on one edge").toBeLessThanOrEqual(when.x);

  await ask.click();
  const menu = page.getByRole("dialog", { name: msg("applications-upnext-outcome-label", { label: "Panel" }) });
  await expect(menu.getByRole("button")).toHaveText([
    msg("applications-interview-outcome-passed"),
    msg("applications-interview-outcome-not-passed"),
    msg("applications-interview-outcome-cancelled"),
  ]);
  await menu.getByRole("button", { name: msg("applications-interview-outcome-passed") }).click();
  await expect.poll(() => outcomes).toEqual([{ outcome: "passed" }]);
});

test("Considering's star waits with the row's other tools: every role here is starred, so it says nothing at rest", async ({ page }, testInfo) => {
  test.skip(testInfo.project.name === "mobile", "Where nothing hovers every action shows.");
  await installPipeline(page, backlog);
  await installPostings(page);
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.goto("/pipeline/list");
  const row = listRow(page, "Staff Product Manager, API");
  await expect(row).toBeVisible();
  await page.mouse.move(0, 0);
  const star = row.locator(".star-btn");
  await expect(star).toHaveAttribute("aria-pressed", "true");
  expect(await seen(star), "unseen at rest").toBe("0");
  await row.hover();
  await expect.poll(() => seen(star), "under the pointer").toBe("1");
  await page.mouse.move(0, 0);
  await expect.poll(() => seen(star)).toBe("0");
  await star.focus();
  await expect.poll(() => seen(star), "holding the focus").toBe("1");
  // A role in compare keeps its mark at rest: that is state the row alone holds.
  await row.hover();
  const compare = row.getByRole("button", { name: msg("jobs-compare") });
  await compare.click();
  await page.mouse.move(0, 0);
  await page.locator("body").click({ position: { x: 5, y: 5 } });
  await expect.poll(() => seen(compare), "in compare, the mark stays").toBe("1");
  await expect.poll(() => seen(star)).toBe("0");
});

test("each tab keeps its own filter: the board's stays off Up next, and both come back as they were left", async ({ page }) => {
  await installPipeline(page, [
    { ...cards[0], next_action: "Ask for an intro", next_action_due: new Date(Date.now() - 2 * 86_400_000).toISOString() },
    cards[1],
    cards[2],
  ]);
  await page.goto("/pipeline/board?only=needs_next");
  await expect(page.getByText("Staff Product Manager, API")).toHaveCount(0);
  const search = page.getByRole("searchbox", { name: msg("applications-search-label") });

  await page.getByRole("tab", { name: msg("shell-tab-pipeline-up-next") }).click();
  await expect(page).toHaveURL(/\/pipeline\/up-next$/);
  await expect(search).toHaveValue("");
  await expect(page.getByRole("button", { name: msg("applications-filter-reset") })).toHaveCount(0);
  await expect(page.getByText("Ask for an intro")).toBeVisible();
  await search.fill("zzz");
  await expect(page.getByText(msg("applications-no-matches"))).toBeVisible();

  await page.getByRole("tab", { name: msg("shell-tab-pipeline-board") }).click();
  await expect(page).toHaveURL(/\/pipeline\/board\?only=needs_next$/);
  await expect(page.getByText("Staff Product Manager, API")).toHaveCount(0);

  await page.getByRole("tab", { name: msg("shell-tab-pipeline-up-next") }).click();
  await expect(page).toHaveURL(/\/pipeline\/up-next\?q=zzz$/);
  await expect(search).toHaveValue("zzz");

  // Back walks the tabs as they were, each with its own filter.
  await page.goBack();
  await expect(page).toHaveURL(/\/pipeline\/board\?only=needs_next$/);
  await expect(page.getByText("Staff Product Manager, API")).toHaveCount(0);
});

/** The postings behind the List's rows, as the jobs list answers them. */
test("the board fills the window under the row and scrolls in its frame: an edge with more fades and steps one column, and each head stays over its cards", async ({ page }, testInfo) => {
  test.skip(testInfo.project.name === "mobile", "The step buttons are for a pointer; a phone swipes the board.");
  const many = Array.from({ length: 9 }, (_, index) =>
    applicationCardFixture({ job_id: 900 + index, pursuit_id: 90 + index, title: `Considered role ${index + 1}`, company: "openai" }));
  await installPipeline(page, [...cards, ...many]);
  await page.setViewportSize({ width: 1280, height: 640 });
  await page.goto("/pipeline/board");
  await expect(column(page, "Considering").getByText("Considered role 9")).toBeAttached();
  const frame = page.locator(".app-board-frame");
  const scroller = page.locator(".app-board-scroll");
  const back = page.getByRole("button", { name: msg("applications-board-scroll-back") });
  const on = page.getByRole("button", { name: msg("applications-board-scroll-on") });

  // The row leads the page: nothing stands above it, so it is at the page's
  // top from the start, the frame fills the window under it, and a wheel over
  // the board scrolls the columns at once.
  const main = page.locator("main");
  const toolbar = page.locator(".app-pipeline-toolbar");
  const top = (await main.boundingBox())!.y;
  expect(Math.round((await toolbar.boundingBox())!.y), "the row is at the page's top").toBe(Math.round(top));
  await expect(page.getByRole("tablist", { name: msg("applications-tabs-label") })).toBeInViewport();
  expect(await main.evaluate((node) => node.scrollHeight - node.clientHeight), "the page has nothing to scroll").toBeLessThan(1);
  const docked = (await toolbar.boundingBox())!;
  const framed = (await frame.boundingBox())!;
  expect(framed.y, "the frame starts under the row").toBeGreaterThanOrEqual(docked.y + docked.height - 1);
  expect(Math.round(framed.y + framed.height), "the frame reaches the window's foot").toBe(640);
  // At rest nothing has passed under a column's name, and it paints nothing.
  await expect(frame).not.toHaveAttribute("data-under");
  const resting = (await scroller.boundingBox())!;
  await page.mouse.move(resting.x + resting.width / 2, resting.y + 120);
  await page.mouse.wheel(0, 100);
  await expect.poll(() => scroller.evaluate((element) => element.scrollTop)).toBeGreaterThan(0);
  await expect(frame).toHaveAttribute("data-under", "true");
  await expect(frame).toHaveAttribute("data-more-on", "true");
  await expect(frame).not.toHaveAttribute("data-more-back");
  await expect(back).toHaveCount(0);

  // A step lands on the next column's edge, and the way back appears.
  const pitch = await scroller.evaluate((element) => {
    const [first, second] = element.querySelectorAll<HTMLElement>(".app-column");
    return second.offsetLeft - first.offsetLeft;
  });
  await on.click();
  await expect.poll(() => scroller.evaluate((element) => element.scrollLeft)).toBe(pitch);
  await expect(frame).toHaveAttribute("data-more-back", "true");
  await back.click();
  await expect.poll(() => scroller.evaluate((element) => element.scrollLeft)).toBe(0);
  await expect(back).toHaveCount(0);

  // Scrolled down, a column's head stays at the frame's top, over its cards.
  await scroller.evaluate((element) => { element.scrollTop = 300; });
  const head = column(page, "Considering").locator(".app-column-head");
  await expect.poll(async () => Math.round((await head.boundingBox())!.y - (await scroller.boundingBox())!.y)).toBe(0);
  const hidden = await page.evaluate(() => {
    const box = document.querySelector(".app-column-head")!.getBoundingClientRect();
    const under = document.elementFromPoint(box.left + box.width / 2, box.top + box.height / 2);
    return under?.closest(".app-column-head") != null;
  });
  expect(hidden, "the head is drawn over the cards that pass beneath it").toBe(true);

  // A board that fits has nothing to step to.
  await page.setViewportSize({ width: 2000, height: 900 });
  await page.getByRole("button", { name: msg("applications-columns"), exact: true }).click();
  for (const name of [msg("applications-column-decided"), msg("applications-column-closed")]) {
    await page.getByRole("dialog", { name: msg("applications-columns") }).getByRole("checkbox", { name }).uncheck();
  }
  await page.keyboard.press("Escape");
  await expect(frame).not.toHaveAttribute("data-more-on");
  await expect(on).toHaveCount(0);
});

async function installPostings(page: Page) {
  const asked: string[] = [];
  const posting = (over: Partial<Job> & { id: number }): Job => ({ ...jobFixture, ...over });
  await mockGet(page, "/api/jobs?**", (route, request) => {
    const url = new URL(request.url());
    if (!url.searchParams.has("ids")) return route.fallback();
    asked.push(url.search);
    return route.fulfill({ json: { ...jobListFixture, total: 3, limit: 500, items: [
      posting({ id: 101, company: "openai", locations: ["San Francisco, CA", "New York, NY"], level_band: "staff",
        level_basis: "title", posted_base: { min: 240_000, max: 300_000, period: "year", currency: "USD" } }),
      posting({ id: 202, company: "stripe", locations: ["Dublin, Ireland"], posted_base: null, comp_base_median: null }),
      posting({ id: 303, company: "apple", status: "closed", locations: ["Cupertino, CA"], posted_base: null, comp_base_median: null }),
      posting({ id: 404, company: "apple", locations: ["Cupertino, CA"], posted_base: null, comp_base_median: null }),
    ] } });
  });
  // The backlog's own role: the compare tray reads its posting by id.
  await mockGet(page, "/api/jobs/404", (route) => route.fulfill({ json: posting({
    id: 404, company: "apple", title: "Group Product Manager", locations: ["Cupertino, CA"], posted_base: null, comp_base_median: null,
  }) }));
  return asked;
}

const listRow = (page: Page, title: string) => page.getByRole("row").filter({ has: page.getByRole("link", { name: title }) });

/** The List's backlog: three roles still in Considering, and two the List
 *  leaves to the Board, one under way and one ended. */
const backlog: ApplicationCard[] = [
  cards[0],
  { ...cards[1], pursuit_id: null, stage: "saved" },
  applicationCardFixture({ job_id: 404, title: "Group Product Manager", company: "apple" }),
  applicationCardFixture({ job_id: 505, pursuit_id: 50, stage: "applied", title: "Director of Product", company: "notion" }),
  cards[2],
];

test("the List holds only roles in Considering, and starting one from its menu, by keyboard alone, sends it to the Board", async ({ page }) => {
  const { stageWrites } = await installPipeline(page, backlog);
  const asked = await installPostings(page);
  await page.goto("/pipeline/list");

  const first = listRow(page, "Staff Product Manager, API");
  await expect(first).toContainText("San Francisco, CA +1");
  await expect(first).toContainText(/240/);
  expect(new URLSearchParams(asked[0]).get("status")).toBe("");
  await expect(page.locator("table.app-list tbody tr")).toHaveCount(3);
  // Under way and ended: the Board's, not the backlog's.
  await expect(listRow(page, "Director of Product")).toHaveCount(0);
  await expect(listRow(page, "Head of Platform")).toHaveCount(0);
  await expect(page.locator('table.app-list th[data-col="stage"]')).toHaveCount(0);

  await menuButton(page, "Principal Engineering Manager").focus();
  await page.keyboard.press("Enter");
  const moves = menu(page, "Principal Engineering Manager");
  await expect(moves).toBeVisible();
  await moves.getByRole("button", { name: "Researching" }).focus();
  await page.keyboard.press("Enter");

  await expect(listRow(page, "Principal Engineering Manager")).toHaveCount(0);
  await expect.poll(() => stageWrites).toContainEqual({ jobId: 202, stage: "researching" });
  await page.getByRole("tab", { name: msg("shell-tab-pipeline-board") }).click();
  await expect(column(page, "Researching").getByText("Principal Engineering Manager")).toBeVisible();
});

test("the List's filters are its own: only those a role in Considering can match, and one the address carries otherwise is dropped", async ({ page }) => {
  await installPipeline(page, backlog.map((card) => (card.job_id === 404 ? { ...card, priority: 5, priority_set: true } : card)));
  await installPostings(page);
  await page.goto("/pipeline/list?only=quiet");

  // Gone quiet is the Board's: the List ignores it and shows its whole backlog.
  await expect(page.locator("table.app-list tbody tr")).toHaveCount(3);
  await expect(page.getByRole("button", { name: msg("applications-filter-remove", { filter: msg("applications-quick-quiet") }) })).toHaveCount(0);

  await page.getByRole("button", { name: msg("shared-filters") }).click();
  const menu = page.getByRole("dialog", { name: msg("applications-filter-menu") });
  const box = (label: string) => menu.getByRole("checkbox", { name: label, exact: true });
  await expect(menu.getByRole("checkbox")).toHaveCount(4);
  for (const label of [msg("applications-quick-overdue"), msg("applications-quick-due-week"), msg("applications-quick-high-priority"), msg("applications-card-posting-closed")]) {
    await expect(box(label)).toBeVisible();
  }
  await expect(box(msg("applications-quick-quiet"))).toHaveCount(0);
  await expect(box(msg("applications-quick-needs-next"))).toHaveCount(0);

  // The box shows the address, which the click changes a moment later.
  await box(msg("applications-quick-high-priority")).click();
  await expect(box(msg("applications-quick-high-priority"))).toBeChecked();
  await page.keyboard.press("Escape");
  await expect(page.locator("table.app-list tbody tr")).toHaveCount(1);
  await expect(listRow(page, "Group Product Manager")).toBeVisible();
  await expect(page).toHaveURL(/\/pipeline\/list\?only=high_priority$/);
});

test("the List says nothing is waiting, and points to the Board, once work has started on every role", async ({ page }) => {
  await installPipeline(page, [cards[1], cards[2]]);
  await page.goto("/pipeline/list");
  await expect(page.getByText(msg("applications-list-clear"))).toBeVisible();
  await page.getByRole("link", { name: msg("applications-list-clear-board") }).click();
  await expect(page).toHaveURL(/\/pipeline\/board$/);
  await expect(column(page, "Applied").getByText("Principal Engineering Manager")).toBeVisible();
});

/** A List header, by its column. */
const listHead = (page: Page, column: string) => page.locator(`table.app-list thead th[data-col="${column}"]`);
const listColumns = (page: Page) =>
  page.locator("table.app-list thead th[data-col]").evaluateAll((cells) => cells.map((cell) => (cell as HTMLElement).dataset.col));

test("the List's sort lives in the address and its hidden columns in the browser, both kept over a reload", async ({ page }) => {
  await installPipeline(page, backlog);
  await installPostings(page);
  await page.goto("/pipeline/list");
  const table = page.getByRole("table");
  const role = listHead(page, "role");

  await role.locator("button.col-sort").click();
  await expect(page).toHaveURL(/\/pipeline\/list\?sort=role&order=asc$/);
  await expect(role).toHaveAttribute("aria-sort", "ascending");
  // Apple, OpenAI, Stripe: by the company's name.
  await expect(table.locator("tbody tr").first()).toContainText("Group Product Manager");

  await page.getByRole("button", { name: /^Columns/ }).click();
  await page.getByRole("dialog", { name: msg("applications-columns") })
    .getByRole("checkbox", { name: msg("jobs-head-location") }).uncheck();
  await page.keyboard.press("Escape");
  await expect(listHead(page, "location")).toHaveCount(0);

  await page.reload();
  await expect(role).toHaveAttribute("aria-sort", "ascending");
  await expect(table.locator("tbody tr").first()).toContainText("Group Product Manager");
  await expect(listHead(page, "location")).toHaveCount(0);
  await expect(listHead(page, "pay")).toBeVisible();
});

test("a List header drags to a new place, and its menu moves or hides it, all kept over a reload", async ({ page }, testInfo) => {
  test.skip(testInfo.project.name === "mobile", "A touch moves a column from its header's menu; dragging is the pointer's way.");
  await installPipeline(page, backlog);
  await installPostings(page);
  await page.goto("/pipeline/list");
  await expect(listHead(page, "pay")).toBeVisible();

  // Dropped on the left half of Role: Base becomes the first column.
  const role = await listHead(page, "role").boundingBox();
  await listHead(page, "pay").dragTo(listHead(page, "role"), { targetPosition: { x: 8, y: role!.height / 2 } });
  await expect.poll(() => listColumns(page)).toEqual(["pay", "role", "location", "level", "posting", "saved"]);
  await expect(page.locator("tbody tr").first().locator("[data-col]").first()).toHaveAttribute("data-col", "pay");

  // The menu is the keyboard's way: it shows when its header holds focus.
  const levelMenu = page.getByRole("button", { name: msg("applications-column-menu", { column: msg("applications-fact-level") }) });
  await levelMenu.focus();
  await expect(levelMenu).toHaveCSS("opacity", "1");
  await page.keyboard.press("Enter");
  const menu = page.getByRole("dialog", { name: msg("applications-column-menu", { column: msg("applications-fact-level") }) });
  await menu.getByRole("button", { name: msg("applications-list-column-left") }).click();
  await expect.poll(() => listColumns(page)).toEqual(["pay", "role", "level", "location", "posting", "saved"]);
  await page.getByRole("button", { name: msg("applications-column-menu", { column: msg("applications-facts-posting") }) }).click();
  await page.getByRole("button", { name: msg("applications-column-hide") }).click();

  await page.reload();
  await expect.poll(() => listColumns(page)).toEqual(["pay", "role", "level", "location", "saved"]);
  await page.getByRole("button", { name: /^Columns/ }).click();
  await page.getByRole("button", { name: msg("applications-list-columns-reset") }).click();
  await expect.poll(() => listColumns(page)).toEqual(["role", "pay", "location", "level", "posting", "saved"]);
});

test("a List row's star takes the role off the pipeline, and the read after the write agrees", async ({ page }) => {
  const { unstarred } = await installPipeline(page, backlog);
  await installPostings(page);
  await page.goto("/pipeline/list");

  const considering = listRow(page, "Staff Product Manager, API");
  await considering.hover();
  // The board reads again once the write lands; the role stays off.
  const reread = page.waitForResponse((response) => response.url().endsWith("/api/applications"));
  await considering.getByRole("button", { name: msg("jobs-save") }).click();
  await expect(considering).toHaveCount(0);
  await expect.poll(() => unstarred).toEqual([101]);
  await reread;
  await expect(considering).toHaveCount(0);
});

test("the List's heads stay under its toolbar as its rows scroll, and a posting with no base says so", async ({ page }, testInfo) => {
  test.skip(testInfo.project.name === "mobile", "A phone's table scrolls sideways in its frame, where a head scrolls with it.");
  const many = Array.from({ length: 14 }, (_, index) =>
    applicationCardFixture({ job_id: 900 + index, title: `Backlog role ${index + 1}`, company: "openai" }));
  await installPipeline(page, [...backlog, ...many]);
  await installPostings(page);
  await page.setViewportSize({ width: 1440, height: 640 });
  await page.goto("/pipeline/list");
  await expect(page.getByRole("table").getByRole("link", { name: "Backlog role 14" })).toBeAttached();
  await expect(listRow(page, "Principal Engineering Manager").locator('[data-col="pay"]'))
    .toHaveText(msg("applications-fact-pay-none"));
  await expect(listRow(page, "Staff Product Manager, API").locator('[data-col="pay"]'))
    .not.toHaveText(msg("applications-fact-pay-none"));

  const main = page.locator("main");
  await main.evaluate((element) => { element.scrollTop = 400; });
  const head = page.getByRole("columnheader").first();
  const toolbar = page.locator(".app-pipeline-toolbar");
  // The toolbar pins at the page's top, and the heads right under it.
  await expect.poll(async () => Math.round((await toolbar.boundingBox())!.y - (await main.boundingBox())!.y)).toBe(0);
  await expect.poll(async () => {
    const bar = (await toolbar.boundingBox())!;
    return Math.round((await head.boundingBox())!.y - (bar.y + bar.height));
  }).toBe(0);
  const covered = await page.evaluate(() => {
    const box = document.querySelector(".app-list thead th")!.getBoundingClientRect();
    return document.elementFromPoint(box.left + 8, box.top + box.height / 2)?.closest("thead") != null;
  });
  expect(covered, "the head is drawn over the rows that pass beneath it").toBe(true);
});

test("the List never widens the page: a narrow window scrolls the table inside its frame", async ({ page }, testInfo) => {
  await installPipeline(page, backlog);
  await installPostings(page);
  await page.goto("/pipeline/list");
  await expect(page.getByRole("table").getByRole("link", { name: "Group Product Manager" })).toBeVisible();
  const fit = await page.evaluate(() => {
    const frame = document.querySelector(".app-list-scroll")!;
    return {
      pageScrolls: document.documentElement.scrollWidth > window.innerWidth + 1,
      tableScrolls: frame.scrollWidth > frame.clientWidth + 1,
    };
  });
  expect(fit.pageScrolls).toBe(false);
  // At a desktop width the default columns fit without a sideways scroll.
  if (testInfo.project.name !== "mobile") expect(fit.tableScrolls).toBe(false);
  // The pinned actions draw their edge exactly while columns pass beneath them.
  const frame = page.locator(".app-list-scroll");
  if (fit.tableScrolls) await expect(frame).toHaveAttribute("data-overflowing", "true");
  else await expect(frame).not.toHaveAttribute("data-overflowing");
  // Wherever the columns scroll, a row's star stays on screen at the right edge.
  const star = await listRow(page, "Group Product Manager").getByRole("button", { name: msg("jobs-save") }).boundingBox();
  const width = page.viewportSize()!.width;
  expect(star!.x + star!.width).toBeLessThanOrEqual(width);
  expect(star!.x).toBeGreaterThan(width / 2);
});

test("the List's compare beacon stands in Radar's margin, level with the role picked last and clear of every star", async ({ page }, testInfo) => {
  test.skip(testInfo.project.name === "mobile", "the margin exists from 1100px; a phone docks the beacon");
  await page.setViewportSize({ width: 1440, height: 900 });
  await installPipeline(page, backlog);
  await installPostings(page);
  await page.goto("/pipeline/list");
  for (const title of ["Staff Product Manager, API", "Group Product Manager"]) {
    const row = listRow(page, title);
    await row.hover();
    await row.getByRole("button", { name: msg("jobs-compare") }).click();
  }
  const pill = page.getByRole("button", { name: "2 in compare. Compare 2 roles" });
  await expect(pill).toBeVisible();
  // It scales in: measure once it has settled.
  await expect.poll(() => pill.evaluate((el) =>
    (el.closest(".job-beacon") ?? el).getAnimations({ subtree: true }).every((one) => one.playState === "finished"))).toBe(true);

  const table = (await page.locator(".app-list-scroll").boundingBox())!;
  const toolbar = (await page.locator(".app-pipeline-toolbar").boundingBox())!;
  const filters = (await page.getByRole("button", { name: msg("shared-filters") }).boundingBox())!;
  const last = (await listRow(page, "Group Product Manager").boundingBox())!;
  const box = (await pill.boundingBox())!;
  // One right edge for the toolbar and the rows, with the margin past both.
  expect(Math.abs(toolbar.x + toolbar.width - (table.x + table.width))).toBeLessThanOrEqual(1);
  // In the margin, never over the pinned stars, and inside the window.
  expect(box.x).toBeGreaterThan(table.x + table.width);
  expect(box.x + box.width).toBeLessThanOrEqual(page.viewportSize()!.width);
  // Level with the row picked last.
  const centre = box.y + box.height / 2;
  expect(centre).toBeGreaterThan(last.y);
  expect(centre).toBeLessThan(last.y + last.height);
  // A control of the page's own height, as the toolbar's buttons are.
  expect(Math.round(box.height)).toBe(Math.round(filters.height));
});

test("the Pipeline and Radar each keep their own comparison, through a visit to the other and a reload", async ({ page }, testInfo) => {
  test.skip(testInfo.project.name === "mobile", "the rail is a desktop control");
  await installPipeline(page, backlog);
  await installPostings(page);
  const rail = page.getByRole("navigation").first();
  const pipelinePill = page.getByRole("button", { name: "2 in compare. Compare 2 roles" });
  const compareOf = (row: ReturnType<typeof listRow>) => row.getByRole("button", { name: msg("jobs-compare") });
  await page.goto("/pipeline/list");
  for (const title of ["Staff Product Manager, API", "Group Product Manager"]) {
    await listRow(page, title).hover();
    await compareOf(listRow(page, title)).click();
  }
  await expect(pipelinePill).toBeVisible();
  await expect(page.getByRole("link", { name: msg("shell-compare-chip-aria", { count: 2 }) })).toBeVisible();

  // Radar holds none of the Pipeline's picks: no beacon, no count, no row pressed.
  await rail.getByRole("link", { name: msg("shell-nav-radar") }).click();
  const radarRow = (title: string) => page.getByRole("article").filter({ hasText: title });
  await expect(radarRow("Staff Product Manager, API")).toBeVisible();
  await expect(page.getByRole("button", { name: /in compare\. Compare/ })).toHaveCount(0);
  await expect(page.getByRole("link", { name: /roles in compare$/ })).toHaveCount(0);
  await expect(compareOf(radarRow("Staff Product Manager, API"))).toHaveAttribute("aria-pressed", "false");

  // Role 202 is in the Pipeline too, unpicked there; picked here it stays Radar's.
  await compareOf(radarRow("Principal Engineer, Platform")).click();
  await expect(compareOf(radarRow("Principal Engineer, Platform"))).toHaveAttribute("aria-pressed", "true");

  await openPipelineView(page, msg("shell-tab-pipeline-list"));
  await expect(pipelinePill).toBeVisible();
  await expect(compareOf(listRow(page, "Principal Engineering Manager"))).toHaveAttribute("aria-pressed", "false");
  await page.reload();
  await expect(pipelinePill).toBeVisible();
  await expect(compareOf(listRow(page, "Staff Product Manager, API"))).toHaveAttribute("aria-pressed", "true");
  await expect(compareOf(listRow(page, "Principal Engineering Manager"))).toHaveAttribute("aria-pressed", "false");

  await page.goto("/");
  await expect(compareOf(radarRow("Principal Engineer, Platform"))).toHaveAttribute("aria-pressed", "true");
  await expect(compareOf(radarRow("Staff Product Manager, API"))).toHaveAttribute("aria-pressed", "false");
});

test("on a phone the tabs keep their row, and Up next takes the tap", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 664 });
  await installPipeline(page);
  await page.goto("/pipeline/board");
  const upNext = page.getByRole("tab", { name: msg("shell-tab-pipeline-up-next") });
  await expect(upNext).toBeVisible();
  const look = await upNext.evaluate((tab) => {
    const row = tab.parentElement!.getBoundingClientRect();
    const box = tab.getBoundingClientRect();
    return {
      row: row.height, tab: box.height,
      hit: document.elementFromPoint(box.x + box.width / 2, box.y + box.height / 2) === tab,
    };
  });
  expect(look.row, "the tab row is as tall as its tabs").toBeGreaterThanOrEqual(look.tab);
  expect(look.hit, "nothing lies over Up next").toBe(true);
  await upNext.click();
  await expect(page).toHaveURL(/\/pipeline\/up-next$/);
});

import type { Locator } from "@playwright/test";
import type { ApplicationCard, InterviewWrite, Job } from "../../src/api";
import { msg } from "../../src/test/msg";
import { applicationCardFixture, applicationDetailFixture, jobDetailFixture, jobFixture, jobListFixture } from "../../src/test/fixtures";
import { installBoardRoutes, installJobDetailRoutes } from "./boardHarness";
import { expect, mockApi, mockGet, test, watchReads, type Page } from "./fixtures";

/* The application pipeline in a browser: every move reachable from the
 * keyboard (the path the spec requires; dragging is only ever the fast one),
 * a whole card that opens its application's page, a drag that moves a card
 * and scrolls the board under it, Interviewing's question,
 * hidden columns a browser remembers, filters kept in the address, the
 * page's own stage button and Mark done, Up next and its month, and the
 * List: the backlog of roles still in Considering, its sort and columns. The API is a small store, so a re-read
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
      ...(card.next_action && card.next_action_due && inSpan(card.next_action_due) ? [{
        kind: "step", job_id: card.job_id, at: card.next_action_due, step: card.next_action,
      }] : []),
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
  return { stageWrites, pursuitWrites, interviews };
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
  await installBoardRoutes(page);
  await installJobDetailRoutes(page);
});

test("the rail place opens on the List, titled by its rail label, and the old Saved address opens the Board, where every starred role is", async ({ page }) => {
  await installPipeline(page);
  await page.goto("/pipeline");
  await expect(page).toHaveURL(/\/pipeline\/list$/);
  await expect(page.getByRole("heading", { level: 1 })).toHaveText(msg("shell-nav-pipeline"));
  await expect(page.getByRole("table").getByRole("link", { name: "Staff Product Manager, API" })).toBeVisible();
  const rail = page.getByRole("navigation").first();
  await expect(rail.getByRole("link", { name: msg("shell-nav-pipeline") })).toBeVisible();
  await expect(rail.getByRole("link", { name: "Saved", exact: true })).toHaveCount(0);

  // Saved counts every starred role. The List leaves out the ones past
  // Considering, so the old address and the count both open the Board.
  await page.goto("/favorites");
  await expect(page).toHaveURL(/\/pipeline\/board$/);
  await expect(page.getByRole("tab", { name: msg("shell-tab-pipeline-board") })).toHaveAttribute("aria-selected", "true");
  await expect(column(page, "Considering").getByText("Staff Product Manager, API")).toBeVisible();
  await expect(column(page, "Applied").getByText("Principal Engineering Manager")).toBeVisible();
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
  // The keyboard's place goes with the card, so the next Enter acts on it again.
  await expect(column(page, "Researching").getByRole("button", { name: msg("applications-card-actions", { title: "Staff Product Manager, API" }) }))
    .toBeFocused();

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

test("the application page moves its stage from the keyboard: M opens the menu, a number picks the stage", async ({ page }) => {
  const { stageWrites } = await installPipeline(page);
  await page.goto("/pipeline/202");
  // Named by what it shows: the stage, then the days in it.
  const stage = (name: string) => page.getByRole("button", { name: new RegExp(`^${name} · \\d+ days?$`) });
  await expect(stage("Applied")).toBeVisible();

  await page.keyboard.press("m");
  await expect(page.getByRole("dialog", { name: msg("applications-stage-menu-label", { title: "Principal Engineering Manager" }) }))
    .toBeVisible();
  // Networking shows as Researching, so the five moving stages are 1 to 5.
  await page.keyboard.press("5");
  await expect(stage("Offer")).toBeVisible();
  await expect.poll(() => stageWrites).toEqual([{ jobId: 202, stage: "offer" }]);
});

test("on a phone the application page gives its title the full width, and a wrapped line never starts with a dot", async ({ page }) => {
  const long = applicationCardFixture({
    job_id: 404, pursuit_id: 40, stage: "applied", title: "Senior Staff Technical Program Manager, Infrastructure Management",
    company: "stripe",
  });
  await installPipeline(page, [...cards, long]);
  await mockGet(page, "/api/jobs/404", (route) => route.fulfill({ json: jobDetailFixture({
    id: 404, title: long.title, company: "stripe", locations: ["South San Francisco, California, United States"],
  }) }));
  // Where each dot after the first part is drawn, and whether its part starts a line.
  const dots = () => page.evaluate(() => {
    const meta = document.querySelector(".app-page-meta")!;
    const box = meta.getBoundingClientRect();
    return [...meta.children].slice(1).map((part) => {
      const at = part.getBoundingClientRect();
      const dot = getComputedStyle(part, "::before");
      const end = at.right - parseFloat(dot.right);
      return { startsLine: Math.abs(at.left - box.left) < 1, start: end - parseFloat(dot.width), end, edge: box.left,
        clipped: ["clip", "hidden"].includes(getComputedStyle(meta).overflowX) };
    });
  });
  const title = page.getByRole("heading", { level: 1, name: long.title });
  const stage = page.getByRole("button", { name: /^Applied · \d+ days?$/ });

  await page.setViewportSize({ width: 1440, height: 900 });
  await page.goto("/pipeline/404");
  await expect(page.locator(".app-page-meta")).toContainText("South San Francisco");
  const wide = await dots();
  expect(wide.map((dot) => dot.startsLine), "on a laptop the city follows the company on one line").toEqual([false]);
  expect(wide[0]!.start, "and the dot between them is drawn in full").toBeGreaterThanOrEqual(wide[0]!.edge);

  await page.setViewportSize({ width: 375, height: 812 });
  await expect.poll(async () => (await dots()).map((dot) => dot.startsLine), "the city wraps to a line of its own").toEqual([true]);
  const narrow = (await dots())[0]!;
  expect(narrow.end <= narrow.edge + 0.5 && narrow.clipped, "its dot falls past the line's start and is clipped").toBe(true);
  const [titleBox, stageBox, nameBox] = await Promise.all([
    title.boundingBox(), stage.boundingBox(), page.locator(".app-page-name").boundingBox(),
  ]);
  expect(stageBox!.y, "the stage button wraps under the title").toBeGreaterThanOrEqual(titleBox!.y + titleBox!.height - 1);
  expect(nameBox!.width, "the title keeps the row beside the company mark").toBeGreaterThan(375 - 32 - 32 - 14 - 20);
  expect(await page.evaluate(() => document.documentElement.scrollWidth), "the page never widens").toBeLessThanOrEqual(375);
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
  await page.getByRole("button", { name: msg("applications-interview-cancel") }).click();
  await expect(page.getByText(msg("applications-next-empty"))).toBeVisible();
  await expect(page.getByRole("button", { name: msg("applications-next-set") })).toBeFocused();
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

  // A day's heading is a date the person reads: title size, in its own case,
  // and the role under a step reads in the step's own ink.
  const look = await days.first().evaluate((day) => {
    const heading = getComputedStyle(day.querySelector("h2")!);
    return {
      size: heading.fontSize, title: heading.getPropertyValue("--app-type-title").trim(), transform: heading.textTransform,
      role: getComputedStyle(day.querySelector(".app-upnext-title")!).color,
      step: getComputedStyle(day.querySelector(".app-next-name")!).color,
    };
  });
  expect(look.size, "the day's heading is at title size").toBe(look.title);
  expect(look.transform, "in its own case").toBe("none");
  expect(look.role, "the role's name in the text's ink").toBe(look.step);

  await days.nth(1).getByRole("link").click();
  await expect(page).toHaveURL(/\/pipeline\/202$/);
  await expect(page.getByRole("heading", { level: 1 })).toHaveText("Principal Engineering Manager");
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
  await installPipeline(page, [
    { ...cards[0], next_action: "Ask for an intro", next_action_due: new Date(2026, 10, 7, 23, 59).toISOString() },
    { ...cards[1], next_interview: {
      id: 5, label: "Hiring manager call", scheduled_at: new Date(2026, 10, 20, 14, 0).toISOString(), all_day: false,
      format: "video",
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
    { kind: "step", job_id: 101, at: new Date(2026, 10, 7, 23, 59).toISOString(), step: "Ask for an intro" },
    ...filler.map((card) => ({ kind: "step", job_id: card.job_id, at: card.next_action_due, step: card.next_action })),
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

  const day = page.locator("section.app-upnext-day").filter({ hasText: msg("applications-upnext-interview", { label: "Hiring manager call" }) });
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
  await expect(page).toHaveURL(/\/pipeline\/202$/);
});

test("the month pages to the next one with its own read, and a filter leaves the same roles out of it", async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.clock.setFixedTime(new Date(2026, 10, 4, 10, 0));
  await installPipeline(page, [
    { ...cards[0], next_action: "Ask for an intro", next_action_due: new Date(2026, 11, 3, 23, 59).toISOString() },
    { ...cards[1], next_interview: {
      id: 5, label: "Hiring manager call", scheduled_at: new Date(2026, 11, 8, 14, 0).toISOString(), all_day: false,
      format: "video",
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

test("moving into Interviewing asks when the interview is, and records it with the move", async ({ page }) => {
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

  const times = dialog.getByRole("group", { name: msg("applications-interview-times") });
  await times.getByRole("button", { name: "2:00 PM", exact: true }).click();
  await expect(dialog.locator(".app-interview-summary")).toHaveText("Thu, Nov 12 · 2:00 PM");
  await dialog.getByRole("button", { name: msg("applications-interview-submit", { stage: "Interviewing" }) }).click();

  await expect(column(page, "Interviewing").getByText("Principal Engineering Manager")).toBeVisible();
  await expect.poll(() => interviews.length).toBe(1);
  expect(stageWrites).toEqual([{ jobId: 202, stage: "interviewing" }]);
  expect(interviews[0]).toMatchObject({ label: msg("applications-interview-default-label"), all_day: false });
  const sent = new Date(interviews[0].scheduled_at);
  expect([sent.getFullYear(), sent.getMonth(), sent.getDate(), sent.getHours()]).toEqual([2026, 10, 12, 14]);
});

test("the interview form fits the window: the times beside the month on a laptop, under it on a phone, and Save always in view", async ({ page }) => {
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
  await page.addInitScript(() => localStorage.setItem("roleband.pipeline-hidden-columns", JSON.stringify(["decided", "closed"])));
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
  await expect(page.getByText(msg("applications-upnext-step", { step: "Ask for an intro" }))).toBeVisible();
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
test("the board scrolls in a frame that fills the window: an edge with more fades and steps one column, and each head stays over its cards", async ({ page }, testInfo) => {
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

  // The page stays still: the board's frame ends inside the window.
  expect(await page.locator("main").evaluate((main) => main.scrollHeight - main.clientHeight)).toBeLessThanOrEqual(1);
  expect((await scroller.boundingBox())!.y + (await scroller.boundingBox())!.height).toBeLessThanOrEqual(640);
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
  await installPipeline(page, backlog.map((card) => (card.job_id === 404 ? { ...card, priority: 5 } : card)));
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
  await expect.poll(() => listColumns(page)).toEqual(["pay", "role", "location", "level", "next", "posting"]);
  await expect(page.locator("tbody tr").first().locator("[data-col]").first()).toHaveAttribute("data-col", "pay");

  // The menu is the keyboard's way: it shows when its header holds focus.
  const levelMenu = page.getByRole("button", { name: msg("applications-column-menu", { column: msg("applications-fact-level") }) });
  await levelMenu.focus();
  await expect(levelMenu).toHaveCSS("opacity", "1");
  await page.keyboard.press("Enter");
  const menu = page.getByRole("dialog", { name: msg("applications-column-menu", { column: msg("applications-fact-level") }) });
  await menu.getByRole("button", { name: msg("applications-list-column-left") }).click();
  await expect.poll(() => listColumns(page)).toEqual(["pay", "role", "level", "location", "next", "posting"]);
  await page.getByRole("button", { name: msg("applications-column-menu", { column: msg("applications-facts-posting") }) }).click();
  await page.getByRole("button", { name: msg("applications-column-hide") }).click();

  await page.reload();
  await expect.poll(() => listColumns(page)).toEqual(["pay", "role", "level", "location", "next"]);
  await page.getByRole("button", { name: /^Columns/ }).click();
  await page.getByRole("button", { name: msg("applications-list-columns-reset") }).click();
  await expect.poll(() => listColumns(page)).toEqual(["role", "pay", "location", "level", "next", "posting"]);
});

test("a List row's star takes the role off the pipeline", async ({ page }) => {
  await installPipeline(page, backlog);
  await installPostings(page);
  const unsaved: number[] = [];
  await mockApi(page, "DELETE", "/api/jobs/*/favorite", async (route, request) => {
    const jobId = Number(new URL(request.url()).pathname.split("/")[3]);
    unsaved.push(jobId);
    await route.fulfill({ json: { job_id: jobId, is_favorite: false } });
  });
  await page.goto("/pipeline/list");

  const considering = listRow(page, "Staff Product Manager, API");
  await considering.hover();
  await considering.getByRole("button", { name: msg("jobs-save") }).click();
  await expect(considering).toHaveCount(0);
  await expect.poll(() => unsaved).toEqual([101]);
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

  await rail.getByRole("link", { name: msg("shell-nav-pipeline") }).click();
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

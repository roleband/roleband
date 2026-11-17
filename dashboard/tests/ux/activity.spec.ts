/* Settings › AI › Activity: what connected assistant apps read, changed and
   were refused. The list is served from a fixture; these specs pin what a
   browser decides: the address, what pins while the list scrolls, the
   chosen look of the picked entry, and the requests the controls make. */

import type { Page } from "@playwright/test";
import { expect, mockGet, test } from "./fixtures";
import { expectMeasuredToolbar } from "./measuredToolbar";
import { installSettingsRoutes } from "./settingsHarness";
import { activityPage, olderActivityPage } from "./activityFixtures";

const ACTIVITY = "/settings/intelligence/activity";

async function routeActivity(page: Page, sink: URL[] = []) {
  const first = activityPage();
  await mockGet(page, "/api/agent-activity?**", (route) => {
    const url = new URL(route.request().url());
    sink.push(url);
    return route.fulfill({ json: url.searchParams.get("cursor") === "older-page" ? olderActivityPage : first });
  });
  return sink;
}

const list = (page: Page) => page.getByRole("region", { name: "Entries" });
const rows = (page: Page) => list(page).getByRole("link");
const inspector = (page: Page) => page.getByRole("complementary", { name: "Picked entry" });

test.beforeEach(async ({ page, isMobile }) => {
  test.skip(isMobile, "Desktop screens only: the list stands beside its inspector.");
  await installSettingsRoutes(page);
  await page.setViewportSize({ width: 1440, height: 900 });
});

test("is a screen under Settings › AI, with its own header and a way back", async ({ page }) => {
  await routeActivity(page);
  await page.goto(ACTIVITY);

  const crumbs = page.getByRole("navigation", { name: /breadcrumb/i });
  await expect(crumbs).toHaveText(/Settings\s*\/\s*AI\s*\/\s*Activity/);
  await expect(crumbs.getByText("Activity")).toHaveAttribute("aria-current", "page");
  const main = page.getByRole("main");
  await expect(main.getByRole("heading", { level: 1 })).toHaveText("Activity");
  await expect(main.locator(".page-hero .eyebrow")).toHaveText("Assistant apps");
  // No rail tab of its own: Settings stays the lit one.
  await expect(page.getByRole("navigation", { name: "Main" }).getByRole("link", { name: "Settings" }))
    .toHaveAttribute("aria-current", "page");

  await main.getByRole("link", { name: "Customize" }).click();
  await expect(page).toHaveURL(/\/settings\/intelligence$/);
  await page.goBack();
  await crumbs.getByRole("link", { name: "AI" }).click();
  await expect(page).toHaveURL(/\/settings\/intelligence$/);

  // The AI tab is the way in.
  await page.getByRole("region", { name: "Activity" }).getByRole("link", { name: "Open activity" }).click();
  await expect(page).toHaveURL(/\/settings\/intelligence\/activity$/);
  await expect(page.getByRole("main").getByRole("heading", { level: 1 })).toHaveText("Activity");
});

test("lists entries by day, picks one into the inspector, and keeps it in the address", async ({ page }) => {
  await routeActivity(page);
  await page.goto(ACTIVITY);

  await expect(rows(page)).toHaveCount(50);
  // Every time stays on one line, "12:12 PM" included.
  const wrapped = await list(page).locator(".activity-time").evaluateAll((cells) =>
    cells.filter((cell) => cell.getBoundingClientRect().height > 2 * parseFloat(getComputedStyle(cell).fontSize)).map((cell) => cell.textContent));
  expect(wrapped).toEqual([]);
  await expect(list(page).getByRole("heading", { level: 2 }).first()).toHaveText(/^Today/);
  const [moved, refused] = [rows(page).nth(0), rows(page).nth(1)];
  await expect(moved).toHaveAttribute("aria-current", "true");
  await expect(moved).toContainText("Moved Design Lead at contoso to Interviewing");
  await expect(refused.getByText("Not shared")).toBeVisible();

  await expect(inspector(page).getByRole("heading", { level: 2 })).toHaveText(/Moved Design Lead/);
  await expect(inspector(page).locator("s")).toHaveText("Applied");

  await refused.click();
  await expect(page).toHaveURL(/[?&]entry=499\b/);
  await expect(refused).toHaveAttribute("aria-current", "true");
  await expect(moved).not.toHaveAttribute("aria-current");
  await expect(inspector(page).getByRole("heading", { level: 2 })).toHaveText("Asked for your offer");
  await expect(inspector(page).getByText("offer.get")).toBeVisible();

  // The address names the entry: a reload opens on it.
  await page.reload();
  await expect(rows(page).nth(1)).toHaveAttribute("aria-current", "true");
});

test("opens a link to an entry on an older page on that entry, with no row claiming it", async ({ page }) => {
  await routeActivity(page);
  const [older] = olderActivityPage.items;
  const asked: string[] = [];
  await mockGet(page, `/api/agent-activity/${older.id}`, (route) => {
    asked.push(route.request().url());
    return route.fulfill({ json: older });
  });
  await page.goto(`${ACTIVITY}?entry=${older.id}`);

  await expect(rows(page)).toHaveCount(50);
  await expect(inspector(page).getByRole("heading", { level: 2 })).toHaveText("Drafted a recipe for careers-fabrikam");
  await expect(inspector(page).getByLabel("What changed")).toContainText("Draft 3");
  await expect(list(page).locator('[aria-current="true"]')).toHaveCount(0);
  expect(asked).toHaveLength(1);

  // Picking a row on the page leaves the linked entry for it.
  await rows(page).nth(0).click();
  await expect(inspector(page).getByRole("heading", { level: 2 })).toHaveText(/Moved Design Lead/);
});

test("says so when a link names an entry the log does not hold", async ({ page }) => {
  await routeActivity(page);
  await mockGet(page, "/api/agent-activity/9999", (route) => route.fulfill({
    status: 404, json: { detail: { code: "activity-entry-not-found", message: "activity entry not found" } },
  }));
  await page.goto(`${ACTIVITY}?entry=9999`);

  await expect(inspector(page)).toHaveText("This entry isn't in the activity log.");
  await expect(list(page).locator('[aria-current="true"]')).toHaveCount(0);
});

test("shows a linked entry beside an empty list", async ({ page }) => {
  await mockGet(page, "/api/agent-activity?**", (route) => route.fulfill({ json: { items: [], next_cursor: null } }));
  const [older] = olderActivityPage.items;
  await mockGet(page, `/api/agent-activity/${older.id}`, (route) => route.fulfill({ json: older }));
  await page.goto(`${ACTIVITY}?entry=${older.id}`);

  await expect(inspector(page).getByRole("heading", { level: 2 })).toHaveText("Drafted a recipe for careers-fabrikam");
  await expect(page.getByRole("main").getByText("Nothing yet")).toBeVisible();
});

test("marks the picked row with the chosen wash and an inset bar, and a refusal in the danger hue", async ({ page }) => {
  await routeActivity(page);
  await page.goto(ACTIVITY);
  const picked = rows(page).nth(0);
  const other = rows(page).nth(2);
  await expect(picked).toHaveAttribute("aria-current", "true");

  const paint = (row: typeof picked) => row.evaluate((element) => {
    const style = getComputedStyle(element);
    const bar = getComputedStyle(element, "::before");
    const probe = document.createElement("span");
    probe.style.color = "var(--app-chosen-mark)";
    document.body.append(probe);
    const mark = getComputedStyle(probe).color;
    probe.style.color = "var(--app-chosen-wash)";
    const wash = getComputedStyle(probe).color;
    probe.remove();
    return { background: style.backgroundColor, bar: bar.backgroundColor, barWidth: bar.width, mark, wash };
  });
  const chosen = await paint(picked);
  expect(chosen.background).toBe(chosen.wash);
  expect(chosen.bar).toBe(chosen.mark);
  expect(chosen.barWidth).toBe("3px");
  const plain = await paint(other);
  expect(plain.background).not.toBe(plain.wash);
  expect(plain.bar).not.toBe(plain.mark);

  const tag = rows(page).nth(1).getByText("Not shared");
  const colours = await tag.evaluate((element) => {
    const probe = document.createElement("span");
    probe.style.color = "var(--app-danger)";
    document.body.append(probe);
    const danger = getComputedStyle(probe).color;
    probe.remove();
    return { tag: getComputedStyle(element).color, danger };
  });
  expect(colours.tag).toBe(colours.danger);

  // A contrast theme repaints backgrounds; the bar keeps a system colour.
  await page.emulateMedia({ forcedColors: "active" });
  const forced = await picked.evaluate((element) => {
    const probe = document.createElement("span");
    probe.style.color = "CanvasText";
    document.body.append(probe);
    const ink = getComputedStyle(probe).color;
    probe.remove();
    return { bar: getComputedStyle(element, "::before").backgroundColor, ink };
  });
  expect(forced.bar).toBe(forced.ink);
});

test("keeps the toolbar, the day heading and the inspector in view as the list scrolls", async ({ page }) => {
  await routeActivity(page);
  await page.goto(ACTIVITY);
  await expect(rows(page)).toHaveCount(50);
  await expectMeasuredToolbar(page, ".activity-screen", ".activity-toolbar", "--activity-toolbar-h");

  // Scroll well into the second day.
  const deep = rows(page).nth(35);
  await deep.scrollIntoViewIfNeeded();
  await page.locator(".activity-screen").evaluate((main) => main.scrollBy(0, 200));

  const box = async (selector: string) => (await page.locator(selector).first().boundingBox())!;
  const toolbar = await box(".activity-toolbar");
  const panel = await inspector(page).boundingBox();
  expect(panel!.y).toBeGreaterThanOrEqual(toolbar.y + toolbar.height - 1);
  expect(panel!.y).toBeLessThan(toolbar.y + toolbar.height + 40);

  // The heading of the day being read sits just under the toolbar.
  const pinned = await page.locator(".activity-day").evaluateAll((headings, edge) =>
    headings.filter((heading) => Math.abs(heading.getBoundingClientRect().top - (edge as number)) <= 1).length,
  toolbar.y + toolbar.height);
  expect(pinned).toBe(1);
});

test("asks the server for each filter, and pages older by the cursor it was given", async ({ page }) => {
  const sink = await routeActivity(page);
  await page.goto(ACTIVITY);
  await expect(rows(page)).toHaveCount(50);
  expect(sink.at(-1)!.searchParams.get("since")).not.toBeNull();
  expect(sink.at(-1)!.searchParams.get("kind")).toBe("all");

  await page.getByRole("button", { name: "Changes" }).click();
  await expect(page).toHaveURL(/[?&]kind=change\b/);
  await expect.poll(() => sink.at(-1)!.searchParams.get("kind")).toBe("change");

  await page.getByRole("button", { name: /Any data/ }).click();
  await page.getByRole("radio", { name: "Offer" }).click();
  await expect.poll(() => sink.at(-1)!.searchParams.get("category")).toBe("offer");

  await page.getByRole("button", { name: /Last 30 days/ }).click();
  await page.getByRole("radio", { name: "Any time" }).click();
  await expect.poll(() => sink.at(-1)!.searchParams.get("since")).toBeNull();

  await page.getByRole("searchbox", { name: "Search activity" }).fill("contoso");
  await expect.poll(() => sink.at(-1)!.searchParams.get("q")).toBe("contoso");

  await expect(page.getByText("1 to 50")).toBeVisible();
  await page.getByRole("button", { name: "Older" }).click();
  await expect.poll(() => sink.at(-1)!.searchParams.get("cursor")).toBe("older-page");
  await expect(rows(page)).toHaveCount(1);
  await expect(page.getByText("51 to 51")).toBeVisible();
  await expect(rows(page).first()).toContainText("Drafted a recipe for careers-fabrikam");
  await expect(inspector(page).getByLabel("What changed")).toContainText("Draft 3");
  await expect(page.getByRole("button", { name: "Older" })).toHaveCount(0);
  await page.getByRole("button", { name: "Newer" }).click();
  await expect(page.getByText("1 to 50")).toBeVisible();
});

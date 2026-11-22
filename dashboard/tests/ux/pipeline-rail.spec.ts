import { msg } from "../../src/test/msg";
import { expect, test, type Page } from "./fixtures";
import { mainRail, pipelineStar } from "./pipelineRail";
import { installEveryRoute } from "./routesHarness";

/* The Pipeline in the rail: a star that is the Pipeline's entry. Collapsed,
   the star stands alone and the page's tabs switch between the views;
   expanded, the views are named under it, in the rail's flow, and drop in one
   after another as the rail widens. The states are pinned in
   `src/shell/NavRail.test.tsx`; this is what is drawn. A narrow window's dock
   lists the views in its row (applications.spec.ts). */

const view = (page: Page, name: string) => mainRail(page).getByRole("link", { name, exact: true });
const BOARD = msg("shell-tab-pipeline-board");
/** The rail entry under the Pipeline, which the views push down. */
const below = (page: Page) => view(page, "Profile");
const top = async (page: Page) => (await below(page).boundingBox())!.y;

test.beforeEach(async ({ page }, testInfo) => {
  test.skip(testInfo.project.name === "mobile", "a phone docks the rail; its views sit in the row");
  await installEveryRoute(page);
});

test("collapsed, the star stands alone: a resting pointer drops nothing, and inside the Pipeline the page's tabs switch the view", async ({ page }) => {
  await page.goto("/");
  await expect(pipelineStar(page)).toBeVisible();
  await expect(pipelineStar(page)).not.toHaveAttribute("aria-current");
  await expect(view(page, BOARD)).toHaveCount(0);
  const resting = await top(page);

  await pipelineStar(page).hover();
  await page.waitForTimeout(400);
  await expect(view(page, BOARD), "a resting pointer drops nothing").toHaveCount(0);
  expect(await top(page)).toBe(resting);

  await pipelineStar(page).click();
  await expect(page).toHaveURL(/\/pipeline\/list$/);
  await expect(page.getByRole("tab", { name: msg("shell-tab-pipeline-list") })).toHaveAttribute("aria-selected", "true");
  // The place is the Pipeline; the page is its view.
  await expect(pipelineStar(page)).toHaveAttribute("aria-current", "true");
  await expect(view(page, BOARD), "the page's tabs name the view, not the rail").toHaveCount(0);

  await page.getByRole("tab", { name: BOARD }).click();
  await expect(page).toHaveURL(/\/pipeline\/board$/);
  await expect(pipelineStar(page)).toHaveAttribute("aria-current", "true");

  await view(page, msg("shell-nav-radar")).click();
  await expect(page).toHaveURL(/\/$/);
  await expect(pipelineStar(page)).not.toHaveAttribute("aria-current");
});

test("expanded, the views drop in under the star one after another, in the rail's flow, and go when the rail narrows", async ({ page }) => {
  await page.goto("/pipeline/board");
  const resting = await top(page);
  await mainRail(page).getByRole("button", { name: msg("shell-rail-expand-aria") }).click();
  await expect(pipelineStar(page)).toHaveText(msg("shell-nav-pipeline"));
  const names = [msg("shell-tab-pipeline-list"), BOARD, msg("shell-tab-pipeline-up-next")];
  for (const name of names) await expect(view(page, name)).toHaveText(name);
  await expect(view(page, BOARD)).toHaveAttribute("aria-current", "page");
  await expect(view(page, msg("shell-tab-pipeline-list"))).not.toHaveAttribute("aria-current");

  // Each view drops after the one above it, onto a line that grows from the star.
  const motion = await mainRail(page).locator(".rail-sub").evaluateAll((links) =>
    links.map((link) => ({ name: getComputedStyle(link).animationName, delay: parseFloat(getComputedStyle(link).animationDelay) })),
  );
  expect(motion.map((one) => one.name)).toEqual(["rail-sub-drop", "rail-sub-drop", "rail-sub-drop"]);
  expect(motion[1].delay).toBeGreaterThan(motion[0].delay);
  expect(motion[2].delay).toBeGreaterThan(motion[1].delay);
  const line = await mainRail(page).locator(".rail-well").evaluate((well) => getComputedStyle(well, "::before").animationName);
  expect(line).toBe("rail-line-down");

  // The views make room in the rail rather than lie over it.
  const last = (await view(page, msg("shell-tab-pipeline-up-next")).boundingBox())!;
  expect(await top(page), "the views lie over the rail instead of making room").toBeGreaterThanOrEqual(last.y + last.height);
  const hit = await view(page, BOARD).evaluate((link) => {
    const box = link.getBoundingClientRect();
    const at = document.elementFromPoint(box.x + box.width / 2, box.y + box.height / 2);
    return Boolean(at && link.contains(at));
  });
  expect(hit).toBe(true);

  // Outside the Pipeline they stay, none of them marked.
  await view(page, msg("shell-nav-radar")).click();
  await expect(page).toHaveURL(/\/$/);
  await expect(view(page, BOARD)).toBeVisible();
  await expect(view(page, BOARD)).not.toHaveAttribute("aria-current");

  await mainRail(page).getByRole("button", { name: msg("shell-rail-collapse-aria") }).click();
  await expect(view(page, BOARD)).toHaveCount(0);
  await expect.poll(() => top(page)).toBe(resting);
});

test("under reduced motion the expanded rail's views arrive still", async ({ page }) => {
  await page.emulateMedia({ reducedMotion: "reduce" });
  await page.goto("/");
  await mainRail(page).getByRole("button", { name: msg("shell-rail-expand-aria") }).click();
  await expect(view(page, BOARD)).toBeVisible();
  const names = await mainRail(page).locator(".rail-sub").evaluateAll((links) => links.map((link) => getComputedStyle(link).animationName));
  expect(names).toEqual(["none", "none", "none"]);
});

import { msg } from "../../src/test/msg";
import { expect, test, type Page } from "./fixtures";
import { mainRail, pipelineStar } from "./pipelineRail";
import { installEveryRoute } from "./routesHarness";

/* The Pipeline in the rail: a star whose views drop out of it. At either rail
   width the views stay folded away until the pointer rests on the star or the
   star is pressed, and then they push the rest of the rail down rather than
   lie over it; expanded, they drop in named.
   The states are pinned in `src/shell/NavRail.test.tsx`; this is what is
   drawn. A phone's dock lists the views in its row (applications.spec.ts). */

const view = (page: Page, name: string) => mainRail(page).getByRole("link", { name, exact: true });
const BOARD = msg("shell-tab-pipeline-board");
/** The rail entry under the Pipeline, which the views push down. */
const below = (page: Page) => view(page, "Profile");
const top = async (page: Page) => (await below(page).boundingBox())!.y;

test.beforeEach(async ({ page }, testInfo) => {
  test.skip(testInfo.project.name === "mobile", "a phone docks the rail; its views sit in the row");
  await installEveryRoute(page);
});

test("the collapsed rail shows the star alone, and a resting pointer drops the views out of it, pushing the rail down", async ({ page }) => {
  await page.goto("/");
  await expect(pipelineStar(page)).toBeVisible();
  await expect(view(page, BOARD), "folded away at rest").toBeHidden();
  const resting = await top(page);

  await pipelineStar(page).hover();
  await expect(view(page, BOARD)).toBeVisible();
  await expect(view(page, msg("shell-tab-pipeline-list"))).toBeVisible();
  await expect(view(page, msg("shell-tab-pipeline-up-next"))).toBeVisible();
  await expect(pipelineStar(page)).toHaveAttribute("aria-expanded", "true");
  await expect.poll(() => top(page), "the views lie over the rail instead of making room").toBeGreaterThan(resting + 60);
  // Nothing covers a view: the well is in the rail's flow, not over it.
  const hit = await view(page, BOARD).evaluate((link) => {
    const box = link.getBoundingClientRect();
    const at = document.elementFromPoint(box.x + box.width / 2, box.y + box.height / 2);
    return Boolean(at && link.contains(at));
  });
  expect(hit).toBe(true);

  await page.mouse.move(700, 450);
  await expect(view(page, BOARD)).toBeHidden();
  await expect.poll(() => top(page)).toBe(resting);
});

test("a press on the star keeps the views open until one is picked, which opens it titled by its name", async ({ page }) => {
  await page.goto("/");
  await pipelineStar(page).click();
  await page.mouse.move(700, 450);
  await expect(view(page, BOARD), "a pressed star stays open when the pointer leaves").toBeVisible();

  await view(page, BOARD).click();
  await expect(page).toHaveURL(/\/pipeline\/board$/);
  await expect(page.getByRole("heading", { level: 1 })).toHaveText(BOARD);
  await page.mouse.move(700, 450);
  await expect(view(page, BOARD)).toBeHidden();
  await expect(pipelineStar(page)).toHaveAttribute("aria-expanded", "false");

  await pipelineStar(page).click();
  await page.keyboard.press("Escape");
  await expect(view(page, BOARD)).toBeHidden();
  await expect(pipelineStar(page)).toBeFocused();
});

test("the expanded rail folds the views away too, and a resting pointer drops them in named, pushing the rail down", async ({ page }) => {
  await page.goto("/pipeline/board");
  await mainRail(page).getByRole("button", { name: "Expand navigation" }).click();
  await expect(pipelineStar(page)).toHaveText(msg("shell-nav-pipeline"));
  await expect(view(page, BOARD), "folded away at rest").toBeHidden();
  const resting = await top(page);

  await pipelineStar(page).hover();
  await expect(view(page, msg("shell-tab-pipeline-list"))).toHaveText(msg("shell-tab-pipeline-list"));
  await expect(view(page, BOARD)).toHaveAttribute("aria-current", "page");
  await expect.poll(() => top(page), "the views lie over the rail instead of making room").toBeGreaterThan(resting + 60);

  await page.mouse.move(700, 450);
  await expect(view(page, BOARD)).toBeHidden();
  await expect.poll(() => top(page)).toBe(resting);
});

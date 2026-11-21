import { msg } from "../../src/test/msg";
import { expect, type Page } from "./fixtures";

/** The main rail, where the Pipeline's views are entries under its star. */
export const mainRail = (page: Page) => page.getByRole("navigation", { name: msg("shell-rail-aria") });

/** The Pipeline's star: it opens the views, it goes nowhere. */
export const pipelineStar = (page: Page) =>
  mainRail(page).getByRole("button", { name: msg("shell-nav-pipeline"), exact: true });

/** Opens a pipeline view the way a person does: from its rail entry, pressing
 *  the star first when the rail keeps the views folded away. */
export async function openPipelineView(page: Page, name: string) {
  const view = mainRail(page).getByRole("link", { name, exact: true });
  // The rail draws the view itself (a phone's dock) or the star that opens it.
  await expect(view.or(pipelineStar(page))).toBeVisible();
  if (!(await view.isVisible())) await pipelineStar(page).click();
  await view.click();
}

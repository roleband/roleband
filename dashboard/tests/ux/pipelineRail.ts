import { msg } from "../../src/test/msg";
import { expect, type Page } from "./fixtures";

/** The main rail: the Pipeline's star, and in the expanded rail its views under it. */
export const mainRail = (page: Page) => page.getByRole("navigation", { name: msg("shell-rail-aria") });

/** The Pipeline's star: the Pipeline's entry, which opens it at Considering. */
export const pipelineStar = (page: Page) =>
  mainRail(page).getByRole("link", { name: msg("shell-nav-pipeline"), exact: true });

/** Opens a pipeline view the way a person does: from its entry in the rail
 *  when the rail lists it (the expanded rail, a narrow window's dock), else by
 *  the star, which goes into the Pipeline at Considering, and then the page's
 *  own tab. */
export async function openPipelineView(page: Page, name: string) {
  const view = mainRail(page).getByRole("link", { name, exact: true });
  await expect(view.or(pipelineStar(page)).first()).toBeVisible();
  if (await view.isVisible()) {
    await view.click();
    return;
  }
  await pipelineStar(page).click();
  // The star lands on Considering, so there is no tab to pick for it, and a
  // screen that failed to load may have no tabs at all.
  if (name === msg("shell-tab-pipeline-list")) return;
  const tab = page.getByRole("tab", { name, exact: true });
  if ((await tab.getAttribute("aria-selected")) !== "true") await tab.click();
  await expect(tab).toHaveAttribute("aria-selected", "true");
}

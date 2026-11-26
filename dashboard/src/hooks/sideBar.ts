import type { SideBarChoice } from "../navigation";
import { setViewChoice, useViewChoiceFlag, useViewChoices } from "./viewChoices";

/* Which optional places the side bar lists: one of the person's view choices
 * per place (hooks/viewChoices), so the side bar is the same in any browser.
 * A place the person has not answered for follows its own default. */

export function listed(optional: SideBarChoice | undefined, choices: Record<string, unknown>): boolean {
  if (!optional) return true;
  const saved = choices[optional.choice];
  return typeof saved === "boolean" ? saved : optional.shown;
}

const EXPANDED_CHOICE = "sidebar.expanded";

/** Whether the side bar shows its labels, as the person last left it, in any
 *  browser. Collapsed until they open it. */
export function useSideBarExpanded(): [expanded: boolean, toggle: () => void] {
  const expanded = useViewChoiceFlag(EXPANDED_CHOICE, false);
  return [expanded, () => void setViewChoice(EXPANDED_CHOICE, !expanded)];
}

/** Whether each place is listed, kept current as the person changes it. */
export function useListed(): (optional: SideBarChoice | undefined) => boolean {
  const choices = useViewChoices();
  return (optional) => listed(optional, choices);
}

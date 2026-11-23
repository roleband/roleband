/* Which Insights a person sees: the basic view, the tabs and panels most
 * readers want, or the advanced view with every chart. One of the person's
 * view choices (hooks/viewChoices), so it holds in any browser; a failed save
 * keeps it for this visit. */

import { setViewChoice, viewChoice } from "../../hooks/viewChoices";

export type InsightsView = "basic" | "advanced";

const CHOICE = "insights.view";

/** The tabs only the advanced view lists. A link to one still opens it. */
export const ADVANCED_TABS: ReadonlySet<string> = new Set([
  "velocity",
  "levels",
  "trajectory",
]);

/** The stored view, or null when the person has never turned the advanced
 *  view on: Insights starts basic, and the first turn on asks first. Turning
 *  it off again stores "basic", so a later turn on does not ask twice. */
export function readInsightsView(): InsightsView | null {
  const saved = viewChoice(CHOICE);
  return saved === "basic" || saved === "advanced" ? saved : null;
}

export function writeInsightsView(view: InsightsView): void {
  void setViewChoice(CHOICE, view);
}

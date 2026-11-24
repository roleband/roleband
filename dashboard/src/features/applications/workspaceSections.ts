/* The Workspace's fixed sections, stage by stage: what the stage asks of the
 * person comes first, and the notes page follows. Which sections show, and in
 * what order, is the person's choice per stage, one of their view choices
 * (hooks/viewChoices), so a cleared browser or another one shows the same
 * Workspace. */

import type { ApplicationCard } from "../../api";
import { setViewChoice, viewChoicesNow } from "../../hooks/viewChoices";
import { boardStage, isMoving } from "./board";

export type WorkspaceSection = "interviews" | "next" | "notes" | "activity";
export type WorkspaceStage = "saved" | "researching" | "applied" | "interviewing" | "offer" | "accepted" | "ended";
interface Layout {
  hidden: WorkspaceSection[];
  order: WorkspaceSection[];
}

/** Every section a stage offers, in the order the page draws them. */
const OFFERED: Record<WorkspaceStage, readonly WorkspaceSection[]> = {
  saved: ["notes", "next", "activity"],
  researching: ["notes", "next", "activity"],
  applied: ["next", "notes", "activity"],
  interviewing: ["interviews", "next", "notes", "activity"],
  offer: ["next", "notes", "activity"],
  // An accepted offer has ended its search and still owes steps: signing, a start date.
  // How and when a role ended stands in the stage facts beside the Workspace.
  accepted: ["next", "notes", "activity"],
  ended: ["notes", "activity"],
};

/** The blocks that stand beside the writing where the role page has two
 *  columns: the short lists a person checks while they write. */
const BESIDE: ReadonlySet<WorkspaceSection> = new Set(["next", "interviews"]);
export const standsBeside = (section: WorkspaceSection): boolean => BESIDE.has(section);

export function workspaceStage(card: ApplicationCard): WorkspaceStage {
  if (card.stage === "accepted") return "accepted";
  if (!isMoving(card)) return "ended";
  return boardStage(card.stage) as WorkspaceStage;
}

export const offeredSections = (stage: WorkspaceStage): readonly WorkspaceSection[] => OFFERED[stage];

/** The sections this stage hides: none until the person hides one. Unknown
 *  names are dropped, and a list that would hide every section hides none:
 *  the Workspace always shows one. */
export function hiddenSections(stage: WorkspaceStage, stored?: { hidden?: readonly unknown[] }): WorkspaceSection[] {
  const offered = OFFERED[stage];
  const named = stored?.hidden;
  if (!Array.isArray(named)) return [];
  const hidden = offered.filter((section) => named.includes(section));
  return hidden.length === offered.length ? [] : hidden;
}

/** Every section this stage offers, in the order the person left them. A
 *  stored name the stage no longer offers is dropped; a section the stored
 *  order does not name keeps its own place among the others, so a stage that
 *  gains a section still shows it. */
export function sectionOrder(stage: WorkspaceStage, stored?: { order?: readonly unknown[] }): WorkspaceSection[] {
  const offered = OFFERED[stage];
  const named = stored?.order;
  if (!Array.isArray(named)) return [...offered];
  const known = named.filter((one): one is WorkspaceSection => offered.includes(one as WorkspaceSection));
  const order = [...new Set(known)];
  offered.forEach((section, index) => {
    if (order.includes(section)) return;
    const after = offered.slice(0, index).reverse().find((one) => order.includes(one));
    order.splice(after ? order.indexOf(after) + 1 : 0, 0, section);
  });
  return order;
}

/** A stage's layout as the person last left it, from their view choices. */
export const layoutOf = (stage: WorkspaceStage, choices: Record<string, unknown>): Layout => {
  const stored = choices[choiceName(stage)];
  const kept = stored && typeof stored === "object" ? (stored as { hidden?: unknown; order?: unknown }) : undefined;
  return {
    hidden: hiddenSections(stage, { hidden: Array.isArray(kept?.hidden) ? kept.hidden : undefined }),
    order: sectionOrder(stage, { order: Array.isArray(kept?.order) ? kept.order : undefined }),
  };
};

const choiceName = (stage: WorkspaceStage) => `workspace.${stage}`;

/** Changes one stage's layout: shown at once, then saved. False when the
 *  save failed; the change still holds until the page is reloaded. */
export function saveLayout(stage: WorkspaceStage, change: (was: Layout) => Layout): Promise<boolean> {
  return setViewChoice(choiceName(stage), change(layoutOf(stage, viewChoicesNow())));
}

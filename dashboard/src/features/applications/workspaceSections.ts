/* The Workspace's fixed sections, stage by stage: what the stage asks of the
 * person comes first, and the notes page follows. Which sections show, and in
 * what order, is a preference of this browser, kept per stage, as the board's
 * hidden columns are. Storage can throw on access, so a failed read shows the
 * stage's own sections in their own order and a failed write is dropped: the
 * choice still holds for this visit. */

import type { ApplicationCard } from "../../api";
import { boardStage, isMoving } from "./board";

export type WorkspaceSection = "interviews" | "next" | "notes" | "outcome" | "activity";
export type WorkspaceStage = "saved" | "researching" | "applied" | "interviewing" | "offer" | "accepted" | "ended";

/** Every section a stage offers, in the order the page draws them. */
const OFFERED: Record<WorkspaceStage, readonly WorkspaceSection[]> = {
  saved: ["notes", "next", "activity"],
  researching: ["notes", "next", "activity"],
  applied: ["next", "notes", "activity"],
  interviewing: ["interviews", "next", "notes", "activity"],
  offer: ["next", "notes", "activity"],
  // An accepted offer has ended its search and still owes steps: signing, a start date.
  accepted: ["outcome", "next", "notes", "activity"],
  ended: ["outcome", "notes", "activity"],
};

const KEY = "roleband.pipeline-workspace-hidden";
const ORDER_KEY = "roleband.pipeline-workspace-order";

export function workspaceStage(card: ApplicationCard): WorkspaceStage {
  if (card.stage === "accepted") return "accepted";
  if (!isMoving(card)) return "ended";
  return boardStage(card.stage) as WorkspaceStage;
}

export const offeredSections = (stage: WorkspaceStage): readonly WorkspaceSection[] => OFFERED[stage];

function readAll(key = KEY): Partial<Record<WorkspaceStage, unknown>> {
  try {
    const raw = localStorage.getItem(key);
    const stored: unknown = raw == null ? {} : JSON.parse(raw);
    return stored && typeof stored === "object" && !Array.isArray(stored) ? stored : {};
  } catch {
    return {};
  }
}

/** The sections this stage hides: none until the person hides one. Unknown
 *  names are dropped, and a list that would hide every section hides none:
 *  the Workspace always shows one. */
export function readHiddenSections(stage: WorkspaceStage): WorkspaceSection[] {
  const stored = readAll()[stage];
  const offered = OFFERED[stage];
  if (!Array.isArray(stored)) return [];
  const hidden = offered.filter((section) => stored.includes(section));
  return hidden.length === offered.length ? [] : hidden;
}

export function writeHiddenSections(stage: WorkspaceStage, hidden: readonly WorkspaceSection[]): void {
  try {
    const all = readAll();
    all[stage] = OFFERED[stage].filter((section) => hidden.includes(section));
    localStorage.setItem(KEY, JSON.stringify(all));
  } catch {
    // Not remembered: the next visit shows the stage's own sections.
  }
}

/** Every section this stage offers, in the order the person left them. A
 *  stored name the stage no longer offers is dropped; a section the stored
 *  order does not name keeps its own place among the others, so a stage that
 *  gains a section still shows it. */
export function readSectionOrder(stage: WorkspaceStage): WorkspaceSection[] {
  const offered = OFFERED[stage];
  const stored = readAll(ORDER_KEY)[stage];
  if (!Array.isArray(stored)) return [...offered];
  const known = stored.filter((one): one is WorkspaceSection => offered.includes(one as WorkspaceSection));
  const order = [...new Set(known)];
  offered.forEach((section, index) => {
    if (order.includes(section)) return;
    const after = offered.slice(0, index).reverse().find((one) => order.includes(one));
    order.splice(after ? order.indexOf(after) + 1 : 0, 0, section);
  });
  return order;
}

export function writeSectionOrder(stage: WorkspaceStage, order: readonly WorkspaceSection[]): void {
  try {
    const all = readAll(ORDER_KEY);
    all[stage] = order.filter((section) => OFFERED[stage].includes(section));
    localStorage.setItem(ORDER_KEY, JSON.stringify(all));
  } catch {
    // Not remembered: the next visit shows the stage's own order.
  }
}

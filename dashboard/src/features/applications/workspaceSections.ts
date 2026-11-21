/* The Workspace's fixed sections, stage by stage: what the stage asks of the
 * person comes first, and the notes page follows. Which sections show is a
 * preference of this browser, kept per stage, as the board's hidden columns
 * are. Storage can throw on access, so a failed read shows the stage's own
 * sections and a failed write is dropped: the choice still holds for this
 * visit. */

import type { ApplicationCard } from "../../api";
import { boardStage, isMoving } from "./board";

export type WorkspaceSection = "interviews" | "next" | "notes" | "outcome" | "history";
export type WorkspaceStage = "saved" | "researching" | "applied" | "interviewing" | "offer" | "ended";

/** Every section a stage offers, in the order the page draws them. */
const OFFERED: Record<WorkspaceStage, readonly WorkspaceSection[]> = {
  saved: ["notes", "next", "history"],
  researching: ["notes", "next", "history"],
  applied: ["next", "notes", "history"],
  interviewing: ["interviews", "next", "notes", "history"],
  offer: ["next", "notes", "history"],
  ended: ["outcome", "notes", "history"],
};

/** What a stage hides until the person shows it: the history, except once the
 *  role has ended, when it is the record of how it went. */
const HIDDEN_BY_DEFAULT: Record<WorkspaceStage, readonly WorkspaceSection[]> = {
  saved: ["history"],
  researching: ["history"],
  applied: ["history"],
  interviewing: ["history"],
  offer: ["history"],
  ended: [],
};

const KEY = "roleband.pipeline-workspace-hidden";

export function workspaceStage(card: ApplicationCard): WorkspaceStage {
  if (!isMoving(card)) return "ended";
  return boardStage(card.stage) as WorkspaceStage;
}

export const offeredSections = (stage: WorkspaceStage): readonly WorkspaceSection[] => OFFERED[stage];

function readAll(): Partial<Record<WorkspaceStage, unknown>> {
  try {
    const raw = localStorage.getItem(KEY);
    const stored: unknown = raw == null ? {} : JSON.parse(raw);
    return stored && typeof stored === "object" && !Array.isArray(stored) ? stored : {};
  } catch {
    return {};
  }
}

/** The sections this stage hides. Unknown names are dropped, and a list that
 *  would hide every section hides none: the Workspace always shows one. */
export function readHiddenSections(stage: WorkspaceStage): WorkspaceSection[] {
  const stored = readAll()[stage];
  const offered = OFFERED[stage];
  if (!Array.isArray(stored)) return [...HIDDEN_BY_DEFAULT[stage]];
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

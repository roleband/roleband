/* A column's name, and which columns the board hides. Hiding is a
 * preference of this browser, as the theme is, never a setting. Until the
 * person chooses, the board shows the stages a role moves through and hides
 * the rest: Considering, which the List holds, and the two that end a role.
 * Storage can throw on access (blocked site data, a private window), so a
 * failed read hides those same columns and a failed write is dropped: the
 * choice still holds for this visit. */

import { STAGE_LABEL } from "../../copy/vocabulary";
import { applicationsColumnClosed, applicationsColumnDecided } from "../../copy/gen/applications";
import { COLUMNS, type ColumnId } from "./board";

const KEY = "roleband.pipeline-hidden-columns";
/** Where a browser kept the one choice the board offered before, hiding
 *  Closed. The default hides Closed too, so it is only ever cleared. */
const CLOSED_KEY = "roleband.pipeline-closed-hidden";

const DEFAULT_HIDDEN: readonly ColumnId[] = ["saved", "decided", "closed"];

const NAME: Record<ColumnId, () => string> = {
  saved: () => STAGE_LABEL.saved,
  researching: () => STAGE_LABEL.researching,
  applied: () => STAGE_LABEL.applied,
  interviewing: () => STAGE_LABEL.interviewing,
  offer: () => STAGE_LABEL.offer,
  decided: () => applicationsColumnDecided(),
  closed: () => applicationsColumnClosed(),
};

/** A column's name: its stage's, or the name of the stages it gathers. */
export const columnName = (id: ColumnId): string => NAME[id]();

const IDS: readonly ColumnId[] = COLUMNS.map((column) => column.id);

/** The hidden columns, in board order. Unknown names are dropped, and a list
 *  that would hide every column hides none: a board always shows one. */
export function readHiddenColumns(): ColumnId[] {
  let stored: unknown;
  try {
    const raw = localStorage.getItem(KEY);
    stored = raw == null ? DEFAULT_HIDDEN : JSON.parse(raw);
  } catch {
    return [...DEFAULT_HIDDEN];
  }
  if (!Array.isArray(stored)) return [...DEFAULT_HIDDEN];
  const hidden = IDS.filter((id) => stored.includes(id));
  return hidden.length === IDS.length ? [] : hidden;
}

export function writeHiddenColumns(hidden: readonly ColumnId[]): void {
  try {
    if (hidden.length) localStorage.setItem(KEY, JSON.stringify(IDS.filter((id) => hidden.includes(id))));
    else localStorage.setItem(KEY, "[]");
    localStorage.removeItem(CLOSED_KEY);
  } catch {
    // Not remembered: the next visit shows the columns as they were.
  }
}

/* Which columns the board hides: a preference of this browser, as the theme
 * is, never a setting. Storage can throw on access (blocked site data, a
 * private window), so a failed read shows every column and a failed write is
 * dropped: the choice still holds for this visit. */

import { COLUMNS, type ColumnId } from "./board";

const KEY = "roleband.pipeline-hidden-columns";
/** Where a browser kept the one choice the board offered before: hiding Closed. */
const CLOSED_KEY = "roleband.pipeline-closed-hidden";

const IDS: readonly ColumnId[] = COLUMNS.map((column) => column.id);

/** The hidden columns, in board order. Unknown names are dropped, and a list
 *  that would hide every column hides none: a board always shows one. */
export function readHiddenColumns(): ColumnId[] {
  let stored: unknown;
  try {
    const raw = localStorage.getItem(KEY);
    stored = raw == null ? (localStorage.getItem(CLOSED_KEY) === "1" ? ["closed"] : []) : JSON.parse(raw);
  } catch {
    return [];
  }
  if (!Array.isArray(stored)) return [];
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

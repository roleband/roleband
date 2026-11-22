/* A column's name, and which columns the board hides: one of the person's
 * view choices (hooks/viewChoices), so it holds in any browser. Until the
 * person chooses, the board shows the stages a role moves through and hides
 * the rest: Considering, which the List holds, and the two that end a role.
 * A failed save keeps the choice for this visit. */

import { STAGE_LABEL } from "../../copy/vocabulary";
import { applicationsColumnClosed, applicationsColumnDecided } from "../../copy/gen/applications";
import { setViewChoice, viewChoice } from "../../hooks/viewChoices";
import { COLUMNS, type ColumnId } from "./board";

const CHOICE = "pipeline.board-hidden";

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
  const stored = viewChoice(CHOICE) ?? DEFAULT_HIDDEN;
  if (!Array.isArray(stored)) return [...DEFAULT_HIDDEN];
  const hidden = IDS.filter((id) => stored.includes(id));
  return hidden.length === IDS.length ? [] : hidden;
}

export function writeHiddenColumns(hidden: readonly ColumnId[]): void {
  void setViewChoice(CHOICE, IDS.filter((id) => hidden.includes(id)));
}

/* The List's rules, apart from how it looks: its columns, their order and
 * which of them a browser hides, and how rows sort. A row is a role still in
 * Considering and, when the posting has been read, the posting's own facts
 * beside it.
 * The column layout is a preference of this browser, as the board's columns
 * are; storage can throw, so a failed read shows the default layout and a
 * failed write is dropped. */

import type { ApplicationCard, Job } from "../../api";
import { compare } from "../../copy/format";
import { BAND_ORDER } from "../../format";
import { dueOf, sortColumn } from "./board";

/** The columns the List can show, in their first order. */
export const LIST_COLUMNS = [
  "role", "pay", "location", "level", "next", "posting", "priority", "in_stage", "activity",
] as const;
export type ListColumn = (typeof LIST_COLUMNS)[number];

/** The role names the row, so it is never hidden; it moves like any other. */
export const ALWAYS_SHOWN: ListColumn = "role";

export interface ListLayout {
  /** Every column, in the order the reader set. */
  order: ListColumn[];
  hidden: ListColumn[];
}

/** A first visit: what a card on the board shows, with priority, days in
 *  stage and last activity left to the reader to add. */
export const DEFAULT_LAYOUT: ListLayout = {
  order: [...LIST_COLUMNS],
  hidden: ["priority", "in_stage", "activity"],
};

const KEY = "roleband.pipeline-list-columns";

const isColumn = (value: unknown): value is ListColumn => (LIST_COLUMNS as readonly unknown[]).includes(value);

/** A stored layout made whole: unknown names dropped, each column once, and
 *  any column the store does not name placed where it first stands. */
function settle(order: readonly unknown[], hidden: readonly unknown[]): ListLayout {
  const kept = [...new Set(order.filter(isColumn))];
  for (const [index, column] of LIST_COLUMNS.entries()) {
    if (!kept.includes(column)) kept.splice(Math.min(index, kept.length), 0, column);
  }
  return { order: kept, hidden: kept.filter((column) => column !== ALWAYS_SHOWN && hidden.includes(column)) };
}

export function readListLayout(): ListLayout {
  let stored: unknown;
  try {
    const raw = localStorage.getItem(KEY);
    if (raw == null) return { order: [...DEFAULT_LAYOUT.order], hidden: [...DEFAULT_LAYOUT.hidden] };
    stored = JSON.parse(raw);
  } catch {
    return { order: [...DEFAULT_LAYOUT.order], hidden: [...DEFAULT_LAYOUT.hidden] };
  }
  const value = stored as Partial<Record<keyof ListLayout, unknown>> | null;
  if (!value || !Array.isArray(value.order) || !Array.isArray(value.hidden)) {
    return { order: [...DEFAULT_LAYOUT.order], hidden: [...DEFAULT_LAYOUT.hidden] };
  }
  return settle(value.order, value.hidden);
}

export function writeListLayout(layout: ListLayout): void {
  try {
    localStorage.setItem(KEY, JSON.stringify(settle(layout.order, layout.hidden)));
  } catch {
    // Not remembered: the next visit shows the columns as they were.
  }
}

/** The order with `column` moved to stand before `before`, or last when
 *  `before` is null. Moving a column onto itself changes nothing. */
export function moveColumn(order: readonly ListColumn[], column: ListColumn, before: ListColumn | null): ListColumn[] {
  if (column === before) return [...order];
  const rest = order.filter((one) => one !== column);
  const at = before == null ? rest.length : rest.indexOf(before);
  rest.splice(at < 0 ? rest.length : at, 0, column);
  return rest;
}

/** The order with `column` one place along among the SHOWN columns: a hidden
 *  column between two shown ones is not a step the reader can see. */
export function stepColumn(layout: ListLayout, column: ListColumn, by: -1 | 1): ListColumn[] {
  const shown = layout.order.filter((one) => !layout.hidden.includes(one));
  const at = shown.indexOf(column);
  const target = shown[at + by];
  if (at < 0 || target == null) return [...layout.order];
  if (by === -1) return moveColumn(layout.order, column, target);
  const after = layout.order[layout.order.indexOf(target) + 1] ?? null;
  return moveColumn(layout.order, column, after);
}

/** One row: the application, and its posting once that read is in. */
export interface ListRow {
  card: ApplicationCard;
  job: Job | undefined;
}

export const LIST_SORTS = ["board", "role", "pay", "level", "next", "posting", "priority", "in_stage", "activity"] as const;
export type ListSort = (typeof LIST_SORTS)[number];
export type ListOrder = "asc" | "desc";

/** The order a column sorts in when first chosen: the most useful end on top. */
export const FIRST_ORDER: Record<ListSort, ListOrder> = {
  board: "asc",
  role: "asc",
  pay: "desc",
  level: "desc",
  next: "asc",
  posting: "asc",
  priority: "desc",
  in_stage: "desc",
  activity: "desc",
};

const isSort = (value: string | null): value is ListSort => (LIST_SORTS as readonly string[]).includes(value ?? "");

/** The sort an address holds: `?sort=` and `?order=`. The board's own order
 *  for Considering is the default and is never written, so an unsorted List
 *  keeps a clean address. It has no header: no column states it. */
export function readSort(params: URLSearchParams): { sort: ListSort; order: ListOrder } {
  const named = params.get("sort");
  const sort = isSort(named) ? named : "board";
  const order = params.get("order");
  return { sort, order: order === "asc" || order === "desc" ? order : FIRST_ORDER[sort] };
}

export function writeSort(params: URLSearchParams, sort: ListSort, order: ListOrder): URLSearchParams {
  const next = new URLSearchParams(params);
  if (sort === "board" && order === FIRST_ORDER.board) {
    next.delete("sort");
    next.delete("order");
  } else {
    next.set("sort", sort);
    next.set("order", order);
  }
  return next;
}

const BAND_RANK = new Map(BAND_ORDER.map((band, index) => [band, index]));
const DAY = 86_400_000;

/** A posting's level, when it names one the bands can place. A level the
 *  posting does not state, or states in words no band maps to, is no level. */
export function placedBand(job: Job | undefined): string | null {
  if (!job || job.level_basis === "none" || job.level_basis === "unmapped") return null;
  return job.level_band ?? null;
}

/** A year's base, for ordering: the posted figure when the posting gives a
 *  yearly one, else the estimate. A list that mixes currencies orders by the
 *  number as written; converting would rank by a rate the row never shows. */
export function yearlyBase(job: Job | undefined): number | null {
  if (!job) return null;
  const posted = job.posted_base;
  if (posted && posted.period === "year") return posted.min ?? posted.max ?? null;
  return job.comp_base_median ?? null;
}

/** Each sort's key for a row; null sorts last whichever way the column runs. */
function key(row: ListRow, sort: Exclude<ListSort, "board" | "role">, now: Date): number | null {
  const { card, job } = row;
  switch (sort) {
    case "pay":
      return yearlyBase(job);
    case "level": {
      const band = placedBand(job);
      return band == null ? null : BAND_RANK.get(band) ?? null;
    }
    case "next":
      return dueOf(card)?.at.getTime() ?? null;
    case "posting":
      return job?.listed_days ?? null;
    case "priority":
      return card.priority;
    case "in_stage":
      return card.stage_since ? (now.getTime() - new Date(card.stage_since).getTime()) / DAY : null;
    case "activity":
      return card.last_activity_at ? new Date(card.last_activity_at).getTime() : null;
  }
}

/** The rows in the List's order. The board's order is the order the
 *  Considering column shows its cards in, so the List and the board read the
 *  same way down; every other sort breaks its ties by it. */
export function sortRows(rows: readonly ListRow[], sort: ListSort, order: ListOrder, now: Date, companyName: (slug: string) => string): ListRow[] {
  const byBoard = sortColumn(rows.map((row) => row.card), now);
  const boardIndex = new Map(byBoard.map((card, index) => [card.job_id, index]));
  const onBoard = (a: ListRow, b: ListRow) => (boardIndex.get(a.card.job_id) ?? 0) - (boardIndex.get(b.card.job_id) ?? 0);
  const sign = order === "asc" ? 1 : -1;
  return [...rows].sort((a, b) => {
    if (sort === "board") return sign * onBoard(a, b);
    if (sort === "role") {
      const by = compare(companyName(a.card.company), companyName(b.card.company))
        || compare(a.card.title, b.card.title);
      return sign * by || onBoard(a, b);
    }
    const ka = key(a, sort, now);
    const kb = key(b, sort, now);
    if (ka == null || kb == null) return ka == null && kb == null ? onBoard(a, b) : ka == null ? 1 : -1;
    return sign * (ka - kb) || onBoard(a, b);
  });
}

/* The List's rules, apart from how it looks: its columns, which of them a
 * browser hides, and how rows sort. A row is an application and, when the
 * posting has been read, the posting's own facts beside it. Hiding a column
 * is a preference of this browser, as the board's columns are; storage can
 * throw, so a failed read shows the default set and a failed write is
 * dropped. */

import type { ApplicationCard, Job } from "../../api";
import { compare } from "../../copy/format";
import { BAND_ORDER } from "../../format";
import { COLUMNS, boardStage, dueOf, sortColumn } from "./board";

/** The columns the List can show, in their order. The role is always shown. */
export const LIST_COLUMNS = [
  "stage", "pay", "location", "level", "next", "posting", "priority", "in_stage", "activity",
] as const;
export type ListColumn = (typeof LIST_COLUMNS)[number];

/** Shown on a first visit: what Saved's rows and a card held between them. */
const HIDDEN_BY_DEFAULT: readonly ListColumn[] = ["priority", "in_stage", "activity"];

const KEY = "roleband.pipeline-list-hidden-columns";

export function readListHidden(): ListColumn[] {
  let stored: unknown;
  try {
    const raw = localStorage.getItem(KEY);
    stored = raw == null ? HIDDEN_BY_DEFAULT : JSON.parse(raw);
  } catch {
    return [...HIDDEN_BY_DEFAULT];
  }
  if (!Array.isArray(stored)) return [...HIDDEN_BY_DEFAULT];
  return LIST_COLUMNS.filter((column) => stored.includes(column));
}

export function writeListHidden(hidden: readonly ListColumn[]): void {
  try {
    localStorage.setItem(KEY, JSON.stringify(LIST_COLUMNS.filter((column) => hidden.includes(column))));
  } catch {
    // Not remembered: the next visit shows the columns as they were.
  }
}

/** One row: the application, and its posting once that read is in. */
export interface ListRow {
  card: ApplicationCard;
  job: Job | undefined;
}

export const LIST_SORTS = ["stage", "role", "pay", "level", "next", "posting", "priority", "in_stage", "activity"] as const;
export type ListSort = (typeof LIST_SORTS)[number];
export type ListOrder = "asc" | "desc";

/** The order a column sorts in when first chosen: the most useful end on top. */
export const FIRST_ORDER: Record<ListSort, ListOrder> = {
  stage: "asc",
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

/** The sort an address holds: `?sort=` and `?order=`. The stage order is the
 *  default and is never written, so an unsorted List keeps a clean address. */
export function readSort(params: URLSearchParams): { sort: ListSort; order: ListOrder } {
  const named = params.get("sort");
  const sort = isSort(named) ? named : "stage";
  const order = params.get("order");
  return { sort, order: order === "asc" || order === "desc" ? order : FIRST_ORDER[sort] };
}

export function writeSort(params: URLSearchParams, sort: ListSort, order: ListOrder): URLSearchParams {
  const next = new URLSearchParams(params);
  if (sort === "stage" && order === FIRST_ORDER.stage) {
    next.delete("sort");
    next.delete("order");
  } else {
    next.set("sort", sort);
    next.set("order", order);
  }
  return next;
}

const STAGE_RANK = new Map(COLUMNS.flatMap((column) => column.stages).map((stage, index) => [stage, index]));
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
function key(row: ListRow, sort: Exclude<ListSort, "stage" | "role">, now: Date): number | null {
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

/** The rows in the List's order. By stage, a row keeps its place among its
 *  column's cards, so the List and the board read the same way down. Ties
 *  keep that order too. */
export function sortRows(rows: readonly ListRow[], sort: ListSort, order: ListOrder, now: Date, companyName: (slug: string) => string): ListRow[] {
  const byBoard = sortColumn(rows.map((row) => row.card), now);
  const boardIndex = new Map(byBoard.map((card, index) => [card.job_id, index]));
  const stageThenBoard = (a: ListRow, b: ListRow) =>
    (STAGE_RANK.get(boardStage(a.card.stage)) ?? 0) - (STAGE_RANK.get(boardStage(b.card.stage)) ?? 0)
    || (boardIndex.get(a.card.job_id) ?? 0) - (boardIndex.get(b.card.job_id) ?? 0);
  const sign = order === "asc" ? 1 : -1;
  return [...rows].sort((a, b) => {
    if (sort === "stage") return sign * stageThenBoard(a, b);
    if (sort === "role") {
      const by = compare(companyName(a.card.company), companyName(b.card.company))
        || compare(a.card.title, b.card.title);
      return sign * by || stageThenBoard(a, b);
    }
    const ka = key(a, sort, now);
    const kb = key(b, sort, now);
    if (ka == null || kb == null) return ka == null && kb == null ? stageThenBoard(a, b) : ka == null ? 1 : -1;
    return sign * (ka - kb) || stageThenBoard(a, b);
  });
}

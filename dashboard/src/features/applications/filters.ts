/* A pipeline view's filters, apart from how they look: which cards a quick
 * filter or a search matches, and how the choice is kept in the address.
 * Filters decide which cards show; they never add or remove a column.
 *
 * A filter lives in the query of its view's own path (`useTabRoute`'s rule:
 * a tab is a place, a filter is not), so each view has its own, it survives
 * opening an application and coming back, and leaving the pipeline from the
 * rail starts it afresh. */

import type { ApplicationCard } from "../../api";
import { companyName } from "../../format";
import { dueOf, dueState, isMoving, isStale, needsNextStep } from "./board";

export const QUICK_FILTERS = [
  "overdue",
  "due_week",
  "needs_next",
  "quiet",
  "high_priority",
  "posting_closed",
] as const;
export type QuickFilter = (typeof QUICK_FILTERS)[number];

/** The pipeline's views, each with its own filter. */
export type PipelineView = "board" | "list" | "up_next";

/** The quick filters a view offers: only those that can match one of its
 *  cards. The List holds roles still in Considering, which have no stage
 *  clock to go quiet on and are not yet owed a next step. Every row in Up
 *  next has a date, so none of them is waiting for a next step. */
export const VIEW_FILTERS: Record<PipelineView, readonly QuickFilter[]> = {
  board: QUICK_FILTERS,
  list: ["overdue", "due_week", "high_priority", "posting_closed"],
  up_next: ["overdue", "due_week", "quiet", "high_priority", "posting_closed"],
};

/** What a card that does not match does: leaves the board, or stays faded. */
export type FilterMode = "only" | "highlight";

export interface BoardFilter {
  quick: readonly QuickFilter[];
  query: string;
  mode: FilterMode;
}

const WEEK = 7 * 86_400_000;

/** A quick filter is about work in motion: an application that has ended
 *  matches none of them. */
export function matchesQuick(card: ApplicationCard, filter: QuickFilter, now: Date): boolean {
  if (!isMoving(card)) return false;
  const due = dueOf(card);
  switch (filter) {
    case "overdue":
      return due != null && dueState(due, now) === "overdue";
    case "due_week":
      return due != null && dueState(due, now) !== "overdue" && due.at.getTime() - now.getTime() <= WEEK;
    case "needs_next":
      return needsNextStep(card);
    case "quiet":
      return isStale(card, now);
    case "high_priority":
      return card.priority >= 4;
    case "posting_closed":
      return card.posting_status === "closed";
  }
}

const fold = (text: string) => text.toLocaleLowerCase().normalize("NFKD").replace(/\p{M}/gu, "");

/** The search reads the company's name and the role's title, whatever the
 *  case or accents. */
export function matchesSearch(card: ApplicationCard, query: string): boolean {
  const wanted = fold(query.trim());
  return !wanted || fold(`${companyName(card.company)} ${card.title}`).includes(wanted);
}

export function isFiltering(filter: BoardFilter): boolean {
  return filter.quick.length > 0 || filter.query.trim() !== "";
}

/** A card matches when it passes every quick filter that is on, and the search. */
export function matches(card: ApplicationCard, filter: BoardFilter, now: Date): boolean {
  return filter.quick.every((quick) => matchesQuick(card, quick, now)) && matchesSearch(card, filter.query);
}

export interface QuickCount {
  quick: QuickFilter;
  /** How many of the view's cards it would match on its own. */
  count: number;
}

/** The quick filters a view offers, in order, with how many of its cards each
 *  would match on its own. */
export function quickCounts(cards: readonly ApplicationCard[], now: Date, offered: readonly QuickFilter[]): QuickCount[] {
  return offered.map((quick) => ({ quick, count: cards.filter((card) => matchesQuick(card, quick, now)).length }));
}

const isQuick = (value: string): value is QuickFilter => (QUICK_FILTERS as readonly string[]).includes(value);

/** The filter an address holds: `?q=` the search, `?only=` the quick filters,
 *  `?show=highlight` the mode. Anything it does not know is ignored, and so is
 *  a quick filter the view does not offer. */
export function readFilter(params: URLSearchParams, offered: readonly QuickFilter[] = QUICK_FILTERS): BoardFilter {
  const named = (params.get("only") ?? "").split(",").filter(isQuick);
  return {
    quick: offered.filter((quick) => named.includes(quick)),
    query: params.get("q") ?? "",
    mode: params.get("show") === "highlight" ? "highlight" : "only",
  };
}

/** The address for a filter, keeping every other parameter. */
export function writeFilter(params: URLSearchParams, filter: BoardFilter): URLSearchParams {
  const next = new URLSearchParams(params);
  const set = (key: string, value: string) => (value ? next.set(key, value) : next.delete(key));
  set("q", filter.query);
  set("only", QUICK_FILTERS.filter((quick) => filter.quick.includes(quick)).join(","));
  set("show", filter.mode === "highlight" ? "highlight" : "");
  return next;
}

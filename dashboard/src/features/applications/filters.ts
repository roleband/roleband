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

/** How many of a view's cards each quick filter would match on its own. */
export function quickCounts(cards: readonly ApplicationCard[], now: Date): Record<QuickFilter, number> {
  return Object.fromEntries(
    QUICK_FILTERS.map((quick) => [quick, cards.filter((card) => matchesQuick(card, quick, now)).length]),
  ) as Record<QuickFilter, number>;
}

const isQuick =(value: string): value is QuickFilter => (QUICK_FILTERS as readonly string[]).includes(value);

/** The filter an address holds: `?q=` the search, `?only=` the quick filters,
 *  `?show=highlight` the mode. Anything it does not know is ignored. */
export function readFilter(params: URLSearchParams): BoardFilter {
  const named = (params.get("only") ?? "").split(",").filter(isQuick);
  return {
    quick: QUICK_FILTERS.filter((quick) => named.includes(quick)),
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

/* The month beside Up next, apart from how it looks: the weeks a month's grid
 * shows, the span its calendar read covers, and the items that fall on each
 * day. Days are the reader's own: built at local midnight, keyed by their
 * local date, so an interview at 23:30 sits on the day the person sees. */

import type { ApplicationCalendarItem } from "../../api";

/** "YYYY-MM-DD" of a moment, in the reader's zone. */
export function dayKey(at: Date): string {
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${at.getFullYear()}-${pad(at.getMonth() + 1)}-${pad(at.getDate())}`;
}

/** Local midnight of the day `key` names. */
export function fromDayKey(key: string): Date {
  return new Date(+key.slice(0, 4), +key.slice(5, 7) - 1, +key.slice(8, 10));
}

/** The first day of the month `at` falls in. */
export function monthOf(at: Date): Date {
  return new Date(at.getFullYear(), at.getMonth(), 1);
}

/** The month `by` months from `month`. */
export function shiftMonth(month: Date, by: number): Date {
  return new Date(month.getFullYear(), month.getMonth() + by, 1);
}

/** The day `by` days from `day`, at its local midnight. Built from the date's
 *  fields rather than by adding milliseconds, so a clock change in between
 *  never lands it on the wrong day. */
export function shiftDay(day: Date, by: number): Date {
  return new Date(day.getFullYear(), day.getMonth(), day.getDate() + by);
}

/** The weeks a month's grid shows, Monday first: from the Monday on or
 *  before the 1st to the Sunday on or after the last day. Four to six rows. */
export function monthWeeks(month: Date): Date[][] {
  const first = monthOf(month);
  const start = shiftDay(first, -((first.getDay() + 6) % 7));
  const last = new Date(first.getFullYear(), first.getMonth() + 1, 0);
  const weeks: Date[][] = [];
  for (let monday = start; monday <= last; monday = shiftDay(monday, 7)) {
    weeks.push(Array.from({ length: 7 }, (_, i) => shiftDay(monday, i)));
  }
  return weeks;
}

/** The span a month's calendar read covers: its grid's first midnight up to
 *  the midnight after its last day. Six weeks at most, the read's own limit. */
export function monthSpan(month: Date): { start: Date; end: Date } {
  const weeks = monthWeeks(month);
  return { start: weeks[0][0], end: shiftDay(weeks[weeks.length - 1][6], 1) };
}

/** The items of a read by the day each falls on, in the order the read gave. */
export function itemsByDay(items: readonly ApplicationCalendarItem[]): Map<string, ApplicationCalendarItem[]> {
  const days = new Map<string, ApplicationCalendarItem[]>();
  for (const item of items) {
    const key = dayKey(new Date(item.at));
    days.set(key, [...(days.get(key) ?? []), item]);
  }
  return days;
}

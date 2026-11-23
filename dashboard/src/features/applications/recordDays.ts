import { date as formatDate, timestamp } from "../../copy/format";

/** A day on the record (a step done, a stage reached, a round held), with its
 *  year when that is not the reader's current year: after New Year, last
 *  year's days must not read as this year's. */
export function recordDay(value: string | Date, now: Date): string {
  return formatDate(value, new Date(value).getFullYear() === now.getFullYear() ? "day" : "full");
}

/** A day with its weekday, and its year when that is not the reader's current one. */
export function weekdayDay(value: string | Date, now: Date): string {
  return new Date(value).getFullYear() === now.getFullYear()
    ? formatDate(value, "weekday")
    : timestamp(value, { weekday: "short", day: "numeric", month: "short", year: "numeric" });
}

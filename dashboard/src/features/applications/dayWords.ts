import { date as formatDate, weekday } from "../../copy/format";
import { applicationsPostingDueDay } from "../../copy/gen/applications";
import { dayOffset } from "./board";

/** Within a week either way, a day is named by its weekday alone. */
const WEEK = 6;

/** The day a date falls on, as a card says it: today, tomorrow, a weekday
 *  within the week, else the weekday and date. */
export function cardDay(on: Date, now: Date): string {
  const offset = dayOffset(on, now);
  const date = Math.abs(offset) <= WEEK ? weekday((on.getDay() + 6) % 7) : formatDate(on, "weekday");
  return applicationsPostingDueDay({ offset, date });
}

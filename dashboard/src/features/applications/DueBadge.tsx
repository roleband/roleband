import { date as formatDate } from "../../copy/format";
import {
  applicationsCardDueInterview,
  applicationsCardDueStep,
  applicationsCardOverdue,
  applicationsPostingDueDay,
} from "../../copy/gen/applications";
import { dayOffset, daysOverdue, dueState, type Due } from "./board";

/* A due date has one look wherever the pipeline shows it: the card, the List
 * row, Up next and the role's page. It is words in the row's quiet ink, never
 * a pill. Red is kept for a step past its date, the one state that asks the
 * person to act; a date still to come says today or tomorrow when it is close. */

/** What a due date says: how late a missed step is, else the day it falls on.
 *  Under a label that already says "Due", `bare` names the day alone. */
export function dueText(due: Due, now: Date, { bare = false }: { bare?: boolean } = {}): string {
  if (dueState(due, now) === "overdue") return applicationsCardOverdue({ days: daysOverdue(due, now) });
  const day = { offset: dayOffset(due.on, now), date: formatDate(due.on, "weekday") };
  if (bare) return applicationsPostingDueDay(day);
  return due.kind === "interview" ? applicationsCardDueInterview(day) : applicationsCardDueStep(day);
}

export function DueBadge({ due, now }: { due: Due; now: Date }) {
  const overdue = dueState(due, now) === "overdue";
  return <span className="app-due" data-overdue={overdue || undefined}>{dueText(due, now)}</span>;
}

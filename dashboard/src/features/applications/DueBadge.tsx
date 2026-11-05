import { date as formatDate } from "../../copy/format";
import { applicationsCardDueInterview, applicationsCardDueStep, applicationsCardOverdue } from "../../copy/gen/applications";
import { Badge } from "../../ui";
import { dayOffset, daysOverdue, dueState, type Due } from "./board";

/* A due date has one look wherever the pipeline shows it: the card, the List
 * row, Up next and the role's page. Red is kept for a step past its date, the
 * one state that asks the person to act; a date still to come is a neutral
 * tint, and its words say today or tomorrow when it is close. */

/** What a due date says: how late a missed step is, else the day it falls on. */
export function dueText(due: Due, now: Date): string {
  if (dueState(due, now) === "overdue") return applicationsCardOverdue({ days: daysOverdue(due, now) });
  const day = { offset: dayOffset(due.on, now), date: formatDate(due.on, "weekday") };
  return due.kind === "interview" ? applicationsCardDueInterview(day) : applicationsCardDueStep(day);
}

export function DueBadge({ due, now }: { due: Due; now: Date }) {
  const overdue = dueState(due, now) === "overdue";
  return (
    <Badge className="app-due" tone={overdue ? "danger" : "neutral"} variant={overdue ? "solid" : "tint"} size="sm">
      {dueText(due, now)}
    </Badge>
  );
}

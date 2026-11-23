import type { ApplicationInterview } from "../../api";
import { time as formatTime } from "../../copy/format";
import {
  applicationsInterviewFormatOnsite,
  applicationsInterviewFormatPhone,
  applicationsInterviewFormatVideo,
  applicationsInterviewOutcomeCancelled,
  applicationsInterviewOutcomeNotPassed,
  applicationsInterviewOutcomePassed,
  applicationsInterviewPromptPeople,
  applicationsInterviewPromptPoints,
  applicationsInterviewPromptQuestions,
  applicationsNextInterviewAllDay,
  applicationsNextInterviewAt,
} from "../../copy/gen/applications";
import { weekdayDay } from "./recordDays";

/** What a round's format is called wherever a round is shown. */
export const FORMAT_LABEL: Record<NonNullable<ApplicationInterview["format"]>, () => string> = {
  video: applicationsInterviewFormatVideo,
  phone: applicationsInterviewFormatPhone,
  onsite: applicationsInterviewFormatOnsite,
};

/** What a round's outcome is called, in the order they are offered. */
export const OUTCOME_LABEL: Record<NonNullable<ApplicationInterview["outcome"]>, () => string> = {
  passed: applicationsInterviewOutcomePassed,
  not_passed: applicationsInterviewOutcomeNotPassed,
  cancelled: applicationsInterviewOutcomeCancelled,
};

/** When an interview is, in words: the day, with its year when that is not
 *  the reader's current one, and the time unless it is all day. */
export function interviewWhen(interview: Pick<ApplicationInterview, "scheduled_at" | "all_day">, now: Date): string {
  const day = weekdayDay(interview.scheduled_at, now);
  return interview.all_day
    ? applicationsNextInterviewAllDay({ date: day })
    : applicationsNextInterviewAt({ date: day, time: formatTime(interview.scheduled_at) });
}

/** The instant a round is over: a timed one when it starts (it is then the
 *  day's, and asks how it went), an all-day one at the next local midnight,
 *  which a clock change puts 23 or 25 hours on. */
export function interviewEnds(interview: Pick<ApplicationInterview, "scheduled_at" | "all_day">): Date {
  const on = new Date(interview.scheduled_at);
  return interview.all_day ? new Date(on.getFullYear(), on.getMonth(), on.getDate() + 1) : on;
}

/** Whether a round is behind the reader: its end has passed. */
export function interviewPast(interview: Pick<ApplicationInterview, "scheduled_at" | "all_day">, now: Date): boolean {
  return interviewEnds(interview).getTime() < now.getTime();
}

/** The outline a coming round's notes start with: three lines to write
 *  under. It is plain text the person may change or delete. */
export function interviewOutline(): string {
  return `${[applicationsInterviewPromptPeople(), applicationsInterviewPromptQuestions(), applicationsInterviewPromptPoints()].join("\n\n")}\n`;
}

/** The notes a round keeps from what its form holds: none for an empty field
 *  or an outline left as it was offered, so a round nobody prepared for
 *  holds no notes for the Workspace or the person's assistant to show. */
export function notesToKeep(typed: string, outline: string): string | null {
  const bare = (text: string) => text.replace(/\s+/g, " ").trim();
  const kept = typed.trim();
  return !kept || (outline && bare(kept) === bare(outline)) ? null : kept;
}

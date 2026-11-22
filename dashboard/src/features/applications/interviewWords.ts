import type { ApplicationInterview } from "../../api";
import { date as formatDate, time as formatTime } from "../../copy/format";
import {
  applicationsInterviewFormatOnsite,
  applicationsInterviewFormatPhone,
  applicationsInterviewFormatVideo,
  applicationsInterviewOutcomeCancelled,
  applicationsInterviewOutcomeNotPassed,
  applicationsInterviewOutcomePassed,
  applicationsNextInterviewAllDay,
  applicationsNextInterviewAt,
} from "../../copy/gen/applications";

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

/** When an interview is, in words: the day, and the time unless it is all day. */
export function interviewWhen(interview: Pick<ApplicationInterview, "scheduled_at" | "all_day">): string {
  const day = formatDate(interview.scheduled_at, "weekday");
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

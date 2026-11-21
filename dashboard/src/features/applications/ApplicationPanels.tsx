import { useEffect, useRef } from "react";
import type { ApplicationInterview } from "../../api";
import { date as formatDate, time as formatTime } from "../../copy/format";
import { applicationsNextInterviewAllDay, applicationsNextInterviewAt } from "../../copy/gen/applications";

/** A field that takes focus when the form around it opens, so the person
 *  types where they asked to. */
export function useFocusWhen<T extends HTMLElement>(open: boolean) {
  const ref = useRef<T>(null);
  useEffect(() => {
    if (open) ref.current?.focus();
  }, [open]);
  return ref;
}

/** When an interview is, in words: the day, and the time unless it is all day. */
export function interviewWhen(interview: Pick<ApplicationInterview, "scheduled_at" | "all_day">): string {
  const day = formatDate(interview.scheduled_at, "weekday");
  return interview.all_day
    ? applicationsNextInterviewAllDay({ date: day })
    : applicationsNextInterviewAt({ date: day, time: formatTime(interview.scheduled_at) });
}

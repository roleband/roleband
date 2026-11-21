/* Up next, apart from how it looks: the interviews and dated next steps of
 * every application, grouped by the day they fall on. The board is the
 * weekly door; this is the daily one. */

import type { ApplicationCard, ApplicationCardInterview } from "../../api";
import type { StageSlug } from "../../copy/vocabulary";
import { dayOffset, dueState } from "./board";

/** The endings that owe nothing, as the follow-up reminders hold them
 *  (`TERMINAL_STAGES` in `tracker/notifications/pursuit_due.py`). An accepted
 *  offer is not one: signing and a start date still carry dates. */
const OWES_NOTHING: ReadonlySet<StageSlug> = new Set(["declined", "withdrawn", "rejected", "role_closed"]);

/** A row of Up next: a coming interview, a dated next step, or an interview
 *  that took place and waits for its outcome. */
export type UpNextItem =
  | { kind: "step"; card: ApplicationCard; at: Date }
  | { kind: "interview" | "outcome"; card: ApplicationCard; at: Date; interview: ApplicationCardInterview };

export interface UpNextDay {
  /** "overdue" for steps past their date; "outcome" for the rounds that wait
   *  for theirs; otherwise the day, as days from today. */
  key: "overdue" | "outcome" | number;
  items: UpNextItem[];
}

/** Every card's next interview and dated next step, but an ended card's. A
 *  step past its date leads, under Overdue; the rest fall on their day, today
 *  first. An interview is never overdue: once it has taken place it asks how
 *  it went, in the last group, until its outcome is in. */
export function upNext(cards: readonly ApplicationCard[], now: Date): UpNextDay[] {
  const overdue: UpNextItem[] = [];
  const awaiting: UpNextItem[] = [];
  const byDay = new Map<number, UpNextItem[]>();
  for (const card of cards) {
    if (OWES_NOTHING.has(card.stage)) continue;
    const past = card.awaiting_outcome;
    if (past) awaiting.push({ kind: "outcome", card, at: new Date(past.scheduled_at), interview: past });
    // A round that has begun is asked about, not listed again as coming.
    const next = card.next_interview;
    if (next && next.id !== past?.id) {
      const at = new Date(next.scheduled_at);
      const offset = Math.max(0, dayOffset(at, now));
      byDay.set(offset, [...(byDay.get(offset) ?? []), { kind: "interview", card, at, interview: next }]);
    }
    if (card.next_action && card.next_action_due) {
      const at = new Date(card.next_action_due);
      const step: UpNextItem = { kind: "step", card, at };
      if (dueState({ kind: "step", at, on: at }, now) === "overdue") overdue.push(step);
      else {
        const offset = Math.max(0, dayOffset(at, now));
        byDay.set(offset, [...(byDay.get(offset) ?? []), step]);
      }
    }
  }
  const order = (items: UpNextItem[]) =>
    items.sort((a, b) => a.at.getTime() - b.at.getTime() || a.card.job_id - b.card.job_id);
  const days: UpNextDay[] = [...byDay.entries()]
    .sort(([a], [b]) => a - b)
    .map(([key, items]) => ({ key, items: order(items) }));
  return [
    ...(overdue.length ? [{ key: "overdue" as const, items: order(overdue) }] : []),
    ...days,
    ...(awaiting.length ? [{ key: "outcome" as const, items: order(awaiting) }] : []),
  ];
}

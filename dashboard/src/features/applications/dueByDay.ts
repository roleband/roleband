/* Up next, apart from how it looks: the interviews and dated next steps of
 * every application, grouped by the day they fall on. The board is the
 * weekly door; this is the daily one. */

import type { ApplicationCard, ApplicationCardInterview, ApplicationStep } from "../../api";
import { dayOffset, dueState, owesNothing } from "./board";

/** A row of Up next: a coming interview, a dated next step, or an interview
 *  that took place and waits for its outcome. */
export type UpNextItem =
  | { kind: "step"; card: ApplicationCard; at: Date; step: ApplicationStep }
  | { kind: "interview" | "outcome"; card: ApplicationCard; at: Date; interview: ApplicationCardInterview };

export interface UpNextDay {
  /** "overdue" for steps on a day before today; "outcome" for the rounds that wait
   *  for theirs; otherwise the day, as days from today. */
  key: "overdue" | "outcome" | number;
  items: UpNextItem[];
}

/** Every card's next interview and each of its dated next steps, but an
 *  ended card's. A step on a day before today leads, under Overdue; the rest
 *  fall on their day, today first. An interview is never overdue: once it has
 *  taken place it asks how it went, in the last group, until its outcome is
 *  in. */
export function upNext(cards: readonly ApplicationCard[], now: Date): UpNextDay[] {
  const overdue: UpNextItem[] = [];
  const awaiting: UpNextItem[] = [];
  const byDay = new Map<number, UpNextItem[]>();
  for (const card of cards) {
    if (owesNothing(card)) continue;
    const past = card.awaiting_outcome;
    if (past) awaiting.push({ kind: "outcome", card, at: new Date(past.scheduled_at), interview: past });
    // A round that has begun is asked about, not listed again as coming.
    const next = card.next_interview;
    if (next && next.id !== past?.id) {
      const at = new Date(next.scheduled_at);
      const offset = Math.max(0, dayOffset(at, now));
      byDay.set(offset, [...(byDay.get(offset) ?? []), { kind: "interview", card, at, interview: next }]);
    }
    for (const step of card.steps) {
      if (!step.due) continue;
      const at = new Date(step.due);
      const row: UpNextItem = { kind: "step", card, at, step };
      if (dueState({ kind: "step", at, on: at }, now) === "overdue") overdue.push(row);
      else {
        const offset = Math.max(0, dayOffset(at, now));
        byDay.set(offset, [...(byDay.get(offset) ?? []), row]);
      }
    }
  }
  const order = (items: UpNextItem[]) =>
    items.sort((a, b) =>
      a.at.getTime() - b.at.getTime() || a.card.job_id - b.card.job_id || (a.kind === "step" && b.kind === "step" ? a.step.id - b.step.id : 0));
  const days: UpNextDay[] = [...byDay.entries()]
    .sort(([a], [b]) => a - b)
    .map(([key, items]) => ({ key, items: order(items) }));
  return [
    ...(overdue.length ? [{ key: "overdue" as const, items: order(overdue) }] : []),
    ...days,
    ...(awaiting.length ? [{ key: "outcome" as const, items: order(awaiting) }] : []),
  ];
}

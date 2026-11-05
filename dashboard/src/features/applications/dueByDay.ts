/* Up next, apart from how it looks: the interviews and dated next steps of
 * every application, grouped by the day they fall on. The board is the
 * weekly door; this is the daily one. */

import type { ApplicationCard } from "../../api";
import type { StageSlug } from "../../copy/vocabulary";
import { dayOffset, dueState } from "./board";

/** The endings that owe nothing, as the follow-up reminders hold them
 *  (`TERMINAL_STAGES` in `tracker/notifications/pursuit_due.py`). An accepted
 *  offer is not one: signing and a start date still carry dates. */
const OWES_NOTHING: ReadonlySet<StageSlug> = new Set(["declined", "withdrawn", "rejected", "role_closed"]);

export interface UpNextItem {
  kind: "interview" | "step";
  card: ApplicationCard;
  /** The instant the item names. */
  at: Date;
}

export interface UpNextDay {
  /** "overdue" for steps past their date; otherwise the day, as days from today. */
  key: "overdue" | number;
  items: UpNextItem[];
}

/** Every card's next interview and dated next step, but an ended card's. A
 *  step past its date leads, under Overdue; the rest fall on their day, today
 *  first. An interview is never overdue: one that started is today's until
 *  its outcome is in. */
export function upNext(cards: readonly ApplicationCard[], now: Date): UpNextDay[] {
  const overdue: UpNextItem[] = [];
  const byDay = new Map<number, UpNextItem[]>();
  for (const card of cards) {
    if (OWES_NOTHING.has(card.stage)) continue;
    if (card.next_interview) {
      const at = new Date(card.next_interview.scheduled_at);
      const offset = Math.max(0, dayOffset(at, now));
      byDay.set(offset, [...(byDay.get(offset) ?? []), { kind: "interview", card, at }]);
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
  return overdue.length ? [{ key: "overdue", items: order(overdue) }, ...days] : days;
}

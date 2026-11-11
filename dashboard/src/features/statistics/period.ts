/* The period an Insights figure covers, and the windows worth offering. Pure,
 * so the rules are unit-tested.
 *
 * A window longer than the history shows the same figures as all time, so the
 * view offers only the windows the history covers, and all the history reads
 * as "since 3 Nov (8 days)", never as a window it does not fill. */

import { date } from "../../copy/format";
import { insightsCommonLastDaysOrAllTime, insightsCommonSinceDate } from "../../copy/gen/insights";

const DAY_MS = 86_400_000;

/** All time, and each window shorter than the history (`historyDays` whole
 *  days; null when unknown, which offers every window). */
export function coveredWindows<P extends { days: number }>(periods: readonly P[], historyDays: number | null): P[] {
  return periods.filter((p) => p.days <= 0 || historyDays == null || p.days < historyDays);
}

/** Whether the figures start where the response says, rather than at the
 *  window's own start: all time, or a window the history is shorter than. The
 *  route reports the later of the two, so a start more than half a day after
 *  the window's means the history clipped it (the view offers no such window,
 *  but asks for one when the history could not be read). */
export function fromSince(days: number, since: string | null | undefined, now: number = Date.now()): since is string {
  if (!since) return false;
  return days <= 0 || Date.parse(since) > now - days * DAY_MS + DAY_MS / 2;
}

/** "last 30d" for a window; for all time or a window the history clipped,
 *  "since 3 Nov (8 days)" from the start the response reports; "all time"
 *  before any whole read. */
export function periodLabel(days: number, since: string | null | undefined, now: number = Date.now()): string {
  if (fromSince(days, since, now)) {
    const elapsed = Math.max(0, Math.floor((now - Date.parse(since)) / DAY_MS));
    return insightsCommonSinceDate({ date: date(since, "day"), days: elapsed });
  }
  return insightsCommonLastDaysOrAllTime({ period: days <= 0 ? "all" : "days", days });
}

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

/** "last 30d" for a window; for all time, "since 3 Nov (8 days)" from the
 *  start the response reports, or "all time" before any whole read. */
export function periodLabel(days: number, since: string | null | undefined, now: number = Date.now()): string {
  if (days <= 0 && since) {
    const elapsed = Math.max(0, Math.floor((now - Date.parse(since)) / DAY_MS));
    return insightsCommonSinceDate({ date: date(since, "day"), days: elapsed });
  }
  return insightsCommonLastDaysOrAllTime({ period: days <= 0 ? "all" : "days", days });
}

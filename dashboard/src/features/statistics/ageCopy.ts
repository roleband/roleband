import { relDays } from "../../format";
import { insightsAgeCopyListedFor, insightsAgeCopyListedToday } from "../../copy/gen/insights";

/* Age captions for Insights. Here rather than in format.ts:
   format.ts is in the app shell's chunk, and only these screens say them. */

/* One posting's age as a caption: the row's own `listed_days`.
 * Never `days_open`, our first-sighting clock, which only aggregates read
 * (docs/copy.md: "days open" is never said). */
export function listedFor(days: number | null | undefined): string | null {
  if (days == null) return null;
  if (days === 0) return insightsAgeCopyListedToday();
  return insightsAgeCopyListedFor({ days: String(relDays(days)) });
}

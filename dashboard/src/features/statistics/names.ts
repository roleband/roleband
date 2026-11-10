import type { StatisticsOverview } from "../../api";
import {
  insightsAgingFrom0Days,
  insightsAgingFrom14Days,
  insightsAgingFrom30Days,
  insightsAgingFrom60Days,
  insightsAgingFrom7Days,
  insightsAgingFrom90Days,
  insightsBriefOpen,
  insightsBriefOpened,
  insightsBriefTopSkill,
} from "../../copy/gen/insights";
import { skillName } from "../../copy/vocab";

/* Names the Statistics screens give what the API sends as slugs. */

/** A fixed age band by its lower bound in days (`velocity.AGING_BANDS`). */
const AGING: Record<number, () => string> = {
  0: insightsAgingFrom0Days,
  7: insightsAgingFrom7Days,
  14: insightsAgingFrom14Days,
  30: insightsAgingFrom30Days,
  60: insightsAgingFrom60Days,
  90: insightsAgingFrom90Days,
};

export const agingBandName = (lo: number): string => AGING[lo]?.() ?? String(lo);

/** The Overview's one line: its facts said as sentences, each only when it is
 *  there. */
export function overviewBrief(data: Pick<StatisticsOverview, "days" | "kpis" | "top_skills">): string {
  const k = data.kpis;
  const parts = [
    insightsBriefOpen({ open: k.open_total, companies: k.companies }),
    insightsBriefOpened({ allTime: data.days <= 0 ? "yes" : "no", opened: k.new_count, days: data.days, closed: k.closed_count }),
  ];
  const skill = data.top_skills[0];
  if (skill) parts.push(insightsBriefTopSkill({ skill: skillName(skill.term), count: skill.job_count }));
  return parts.join(" ");
}

import { compare as copyCompare } from "../../../copy/format";
import type { DisclosedBand, PostedLevel, PostedPay } from "../../../api";
import { companyName, fmtCompIn } from "../../../format";
import { levelLabel } from "./levelLabel";
import {
  insightsCompBandsEmployerAtLevel,
  insightsCompBandsImplausible,
  insightsCompBandsLevelRanges,
  insightsCompBandsNoCountry,
  insightsCompBandsNotBase,
  insightsCompBandsNotYearly,
  insightsCompBandsPlacedByPay,
  insightsCompBandsTo,
} from "../../../copy/gen/insights";

/**
 * Posted base ranges, by level, in one country and its currency.
 *
 * Deliberately NOT a distribution. An employer posts a range per
 * (company, level) and hangs many roles off it, so a dot-per-role plot would
 * assert a per-role salary sample that does not exist. The unit is the range
 * itself.
 *
 * A row per level: every range a faint span, the level's typical range
 * outlined when it has one, and colour kept for the employer a reader picks,
 * since colour cycled across every employer would name no one.
 */

export interface LevelBands {
  level: string;
  bands: DisclosedBand[];
  employers: number;
}

/** Ranges grouped by level, in the order the API sends them (seniority). */
export function bandsByLevel(bands: readonly DisclosedBand[]): LevelBands[] {
  const by = new Map<string, DisclosedBand[]>();
  for (const b of bands) by.set(b.level_band, [...(by.get(b.level_band) ?? []), b]);
  return [...by].map(([level, bs]) => ({
    level,
    bands: bs,
    employers: new Set(bs.map((b) => b.company)).size,
  }));
}

/** The smallest of 1, 2, 2.5 and 5 times a power of ten that splits `span`
 *  into at most six steps, so any currency's amounts get round ticks. */
function niceStep(span: number): number {
  const magnitude = 10 ** Math.floor(Math.log10(Math.max(span, 1) / 6));
  for (const m of [1, 2, 2.5, 5, 10]) {
    if (span / (m * magnitude) <= 6) return m * magnitude;
  }
  return 10 * magnitude;
}

/** One scale for every row: rounded ends and three to six ticks. */
export function bandScale(bands: readonly DisclosedBand[]): { min: number; max: number; ticks: number[] } {
  if (!bands.length) return { min: 0, max: 1, ticks: [] };
  const lo = Math.min(...bands.map((b) => b.low));
  const hi = Math.max(...bands.map((b) => b.high));
  const step = niceStep(hi - lo);
  const min = Math.floor(lo / step) * step;
  const max = Math.max(min + step, Math.ceil(hi / step) * step);
  const ticks: number[] = [];
  for (let t = min; t <= max; t += step) ticks.push(t);
  return { min, max, ticks };
}

/** Employers with a range, most open roles on their ranges first. */
export function bandEmployers(bands: readonly DisclosedBand[]): { value: string; label: string; count: number }[] {
  const reqs = new Map<string, number>();
  for (const b of bands) reqs.set(b.company, (reqs.get(b.company) ?? 0) + b.reqs);
  return [...reqs]
    .map(([company, count]) => ({ value: company, label: companyName(company), count }))
    .sort((a, b) => b.count - a.count || copyCompare(a.label, b.label));
}

/** One level's row, said in words for a screen reader. */
export function levelSummary(
  row: LevelBands,
  figure: PostedLevel | undefined,
  picked: readonly DisclosedBand[],
  employer: string | null,
  currency: string,
): string {
  const money = (x: number) => fmtCompIn(x, currency);
  const low = figure?.low ?? null;
  const high = figure?.high ?? null;
  const summary = insightsCompBandsLevelRanges({
    label: levelLabel(row.level),
    bands: row.bands.length,
    employers: row.employers,
    figure: low != null && high != null ? "some" : "none",
    low: low != null ? money(low) : "",
    high: high != null ? money(high) : "",
  });
  if (!employer) return summary;
  const ranges = picked.map((b) => insightsCompBandsTo({ low: money(b.low), high: money(b.high) })).join(", ");
  return insightsCompBandsEmployerAtLevel({ summary, employer: companyName(employer), published: picked.length ? "some" : "none", ranges });
}

/** What no country's figure reads, and why, a sentence per reason; "" when nothing. */
export function exclusionNote(excluded: PostedPay["excluded"]): string {
  const notes: [number, (args: { count: number }) => string][] = [
    [excluded.not_base, insightsCompBandsNotBase],
    [excluded.not_yearly, insightsCompBandsNotYearly],
    [excluded.implausible, insightsCompBandsImplausible],
    [excluded.no_country, insightsCompBandsNoCountry],
    [excluded.placed_by_pay, insightsCompBandsPlacedByPay],
  ];
  return notes
    .filter(([count]) => count > 0)
    .map(([count, say]) => say({ count }))
    .join(" ");
}

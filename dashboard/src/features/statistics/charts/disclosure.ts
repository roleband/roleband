import type { EChartsCoreOption } from "echarts/core";
import type { DisclosureRates } from "../../../api";
import { companyName } from "../../../format";
import { levelLabel } from "./levelLabel";
import { FAINT, MUTED, SIGNAL, compactGrid, valueAxis } from "./options";
import {
  insightsDisclosureNoOpenRolesHaveBeen,
  insightsDisclosureOfCheckedOpenRoles,
  insightsDisclosureOfRoles,
  insightsDisclosureShareOfCheckedOpenRoles,
  insightsDisclosureUnclassified,
  insightsDisclosureRateStatesPay,
} from "../../../copy/gen/insights";
import { tooltipHtml } from "./tooltip";

/**
 * Pay-transparency chart options (pure — no canvas, unit-testable).
 *
 * The RATE (%): how many open roles state pay at all. Its denominator is the
 * roles the disclosure pass has read, so a group whose `rate` is null has not
 * been checked yet and is dropped rather than drawn at 0% — "we have not
 * looked" and "this employer publishes nothing" are different findings.
 */

export const pct = (rate: number) => `${Math.round(rate * 100)}%`;

export interface DisclosureRateRow {
  key: string;
  label: string;
  rate: number;
  disclosed: number;
  checked: number;
}

/** Rows for the current-state rate chart, unchecked groups dropped. Lowest
 * rate first: the employers that post no range are what a reader looks for here. */
export function disclosureRateRows(
  rates: DisclosureRates,
  dim: "company" | "level",
): DisclosureRateRow[] {
  const source =
    dim === "company"
      ? rates.by_company.map((c) => ({ ...c, key: c.company, label: companyName(c.company) }))
      : rates.by_level.map((l) => ({
          ...l,
          key: l.level_band,
          label: l.level_band ? levelLabel(l.level_band) : insightsDisclosureUnclassified(),
        }));
  return source
    .filter((row): row is typeof row & { rate: number } => row.rate !== null)
    .map(({ key, label, rate, disclosed, checked }) => ({ key, label, rate, disclosed, checked }))
    .sort((a, b) => a.rate - b.rate || b.checked - a.checked);
}

/** Groups whose rate cannot be stated yet, so the panel can say so out loud. */
export function unratedCount(rates: DisclosureRates, dim: "company" | "level"): number {
  const source = dim === "company" ? rates.by_company : rates.by_level;
  return source.filter((row) => row.rate === null).length;
}

export function disclosureRateSummary(rows: DisclosureRateRow[], unrated: number): string {
  if (!rows.length) return insightsDisclosureNoOpenRolesHaveBeen();
  const rates = rows.map((r) => insightsDisclosureOfRoles({ label: r.label, rate: pct(r.rate), disclosed: r.disclosed, checked: r.checked })).join(". ");
  return insightsDisclosureShareOfCheckedOpenRoles({ rates, unrated });
}

export function buildDisclosureRateOption(rows: DisclosureRateRow[]): EChartsCoreOption {
  // ECharts draws category 0 at the bottom, so the rows go in reversed to put
  // the first on top; every index the chart hands back is into this order.
  const drawn = [...rows].reverse();
  return {
    // The EChart wrapper supplies a concise aria-label plus an sr-only summary;
    // echarts' own generated label would replace it with a robot paragraph.
    aria: { enabled: false },
    grid: { ...compactGrid, left: 14, right: 96, top: 12, bottom: 22 },
    tooltip: {
      trigger: "item",
      formatter: (p: { dataIndex: number }) => {
        const r = drawn[p.dataIndex];
        if (!r) return "";
        return tooltipHtml(r.label, [
          insightsDisclosureRateStatesPay({ rate: pct(r.rate) }),
          insightsDisclosureOfCheckedOpenRoles({ disclosed: r.disclosed, checked: r.checked }),
        ]);
      },
    },
    // A share is always read against 0-100%, never against the leader — an
    // auto-scaled axis would make 12% look like a full bar.
    xAxis: {
      ...valueAxis,
      min: 0,
      max: 100,
      axisLabel: { color: FAINT, fontSize: 9, formatter: (v: number) => `${v}%` },
    },
    yAxis: {
      type: "category",
      data: drawn.map((r) => r.label),
      axisLine: { show: false },
      axisTick: { show: false },
      axisLabel: { color: MUTED, fontSize: 10, interval: 0 },
    },
    series: [
      {
        type: "bar",
        barMaxWidth: 14,
        itemStyle: { color: SIGNAL, borderRadius: [0, 3, 3, 0] },
        data: drawn.map((r) => Math.round(r.rate * 1000) / 10),
        label: {
          show: true,
          position: "right",
          color: MUTED,
          fontFamily: "var(--app-font-mono)",
          fontSize: 9,
          formatter: (p: { dataIndex: number }) => {
            const r = drawn[p.dataIndex];
            return r ? `${pct(r.rate)} · ${r.disclosed}/${r.checked}` : "";
          },
        },
      },
    ],
  };
}

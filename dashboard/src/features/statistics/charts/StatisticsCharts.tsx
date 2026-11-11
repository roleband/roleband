import type { EChartsCoreOption } from "echarts/core";
import type {
  CompTrajectoryCompany,
  OverviewSkill,
  TopSkill,
} from "../../../api";
import { companyName, fmtComp } from "../../../format";
import { EChart } from "../../../ui/EChart";
import {
  BORDER,
  DANGER,
  DATA_2,
  FAINT,
  MUTED,
  SIGNAL,
  categoryAxis,
  compactGrid,
  valueAxis,
} from "./options";
import {
  insightsStatisticsChartsClosedCount,
  insightsStatisticsChartsEquityShockwaveByCompany,
  insightsStatisticsChartsLiftTheMarketSRate,
  insightsStatisticsChartsMarketDemandField,
  insightsStatisticsChartsNewClosed,
  insightsStatisticsChartsNewCount,
  insightsStatisticsChartsNoChange,
  insightsStatisticsChartsOfTheseRolesTheMarket,
  insightsStatisticsChartsOpenNewClosed,
  insightsStatisticsChartsOpenRolesByCompany,
  insightsStatisticsChartsShareOfTheseRoles,
  insightsStatisticsChartsTheMarketSRate,
  insightsStatisticsChartsWhatSetsTheseRolesApart,
  insightsCommonOpenRoles,
  insightsCommonOpenRolesUnit,
  insightsStatisticsChartsCompanyOpenRoles,
  insightsStatisticsChartsEquityChange,
  insightsStatisticsChartsShareAgainstMarket,
  insightsStatisticsChartsSkillOpenRoles,
} from "../../../copy/gen/insights";
import { skillName } from "../../../copy/vocab";
import { tooltipHtml, withParts } from "./tooltip";

const mono = "var(--app-font-mono)";

const direction = (amount: number) => (amount > 0 ? "up" : amount < 0 ? "down" : "flat");

export function OverviewSignalChart({ skills }: { skills: OverviewSkill[] }) {
  const ordered = skills.slice(0, 10).reverse();
  const values = ordered.map((s) => s.job_count);
  const option: EChartsCoreOption = {
    grid: { ...compactGrid, right: 48 },
    tooltip: {
      trigger: "item",
      formatter: (p: { dataIndex: number }) => {
        const skill = ordered[p.dataIndex];
        return tooltipHtml(skillName(skill.term), [
          insightsStatisticsChartsSkillOpenRoles({ job_count: skill.job_count, category: skill.category ?? "uncategorized" }),
        ]);
      },
    },
    xAxis: { ...valueAxis, name: insightsCommonOpenRolesUnit(), nameTextStyle: { color: FAINT, fontSize: 9 } },
    yAxis: { ...categoryAxis, data: ordered.map((s) => skillName(s.term)) },
    series: [
      {
        type: "bar",
        data: values,
        barMaxWidth: 2,
        silent: true,
        itemStyle: { color: DATA_2, opacity: 0.5 },
      },
      {
        type: "scatter",
        data: values,
        symbolSize: (value: number) => Math.max(8, Math.min(18, 7 + value * 0.32)),
        itemStyle: { color: SIGNAL, borderColor: "var(--app-surface-raised)", borderWidth: 2 },
        label: {
          show: true,
          position: "right",
          color: MUTED,
          fontFamily: mono,
          fontSize: 9,
          formatter: ({ value }: { value: number }) => String(value),
        },
      },
    ],
  };

  return (
    <EChart
      ariaLabel={insightsStatisticsChartsMarketDemandField()}
      className="chart-overview"
      height={292}
      option={option}
      summary={ordered.map((s) => `${skillName(s.term)}: ${s.job_count}`).join(", ")}
    />
  );
}

/** One bar of the Hiring company chart: one company. */
export interface HiringBar {
  /** The company's slug, which a click on its bar hands to `onPick`. */
  company: string;
  label: string;
  open: number;
  fresh: number;
  closed: number;
}

/** Open roles by company, leaders first. The caller bounds the rows
 *  (`hiring.topCompanies`): this draws what it is given, never a bar per company. */
export function HiringCompaniesChart({
  bars,
  onPick,
}: {
  bars: readonly HiringBar[];
  /** A click on a company's bar or its label. */
  onPick?: (company: string) => void;
}) {
  const rows = bars.slice().reverse();
  // A bar answers with its index; an axis label, with its text.
  const pick = (p: unknown) => {
    const { componentType, dataIndex, value } = p as { componentType?: string; dataIndex?: number; value?: unknown };
    const row = componentType === "yAxis" ? rows.find((r) => r.label === value) : rows[dataIndex ?? -1];
    if (row) onPick?.(row.company);
  };
  const option: EChartsCoreOption = {
    grid: { ...compactGrid, right: 118, top: 24 },
    tooltip: {
      trigger: "item",
      formatter: (p: { dataIndex: number }) => {
        const row = rows[p.dataIndex];
        return tooltipHtml(row.label, [
          insightsStatisticsChartsCompanyOpenRoles({ open: row.open }),
          withParts(insightsStatisticsChartsNewClosed, {
            new_roles: { text: insightsStatisticsChartsNewCount({ fresh: row.fresh }), tone: "new" },
            closed_roles: { text: insightsStatisticsChartsClosedCount({ closed: row.closed }), tone: "closed" },
          }),
        ]);
      },
    },
    xAxis: valueAxis,
    yAxis: { ...categoryAxis, data: rows.map((row) => row.label), triggerEvent: Boolean(onPick) },
    series: [
      {
        name: insightsCommonOpenRoles(),
        type: "bar",
        data: rows.map((row) => ({ value: row.open })),
        barMaxWidth: 13,
        cursor: onPick ? "pointer" : "default",
        itemStyle: {
          color: {
            type: "linear",
            x: 0,
            y: 0,
            x2: 1,
            y2: 0,
            colorStops: [{ offset: 0, color: SIGNAL }, { offset: 1, color: DATA_2 }],
          },
          borderRadius: [0, 5, 5, 0],
        },
        label: {
          show: true,
          position: "right",
          distance: 8,
          fontFamily: mono,
          fontSize: 9,
          formatter: (p: { dataIndex: number }) => {
            const row = rows[p.dataIndex];
            return `{open|${row.open}}  {new|+${row.fresh}} {closed|−${row.closed}}`;
          },
          rich: {
            open: { color: MUTED, fontFamily: mono, fontWeight: 700 },
            new: { color: DATA_2, fontFamily: mono },
            closed: { color: DANGER, fontFamily: mono },
          },
        },
      },
    ],
  };
  return (
    <EChart
      ariaLabel={insightsStatisticsChartsOpenRolesByCompany()}
      className="chart-demand"
      height={Math.max(220, 54 + rows.length * 30)}
      onEvents={onPick ? { click: pick } : undefined}
      option={option}
      summary={bars.map((b) => insightsStatisticsChartsOpenNewClosed({ label: String(b.label), open: b.open, fresh: b.fresh, closed: b.closed })).join("; ")}
    />
  );
}

export function TrajectoryShockChart({
  companies,
  priceChange,
}: {
  companies: CompTrajectoryCompany[];
  priceChange: number;
}) {
  const rows = companies
    .map((c) => ({ ...c, change: Math.round(c.equity * priceChange) }))
    .sort((a, b) => a.change - b.change);
  const zeroScenario = rows.every((row) => row.change === 0);
  const option: EChartsCoreOption = {
    grid: { ...compactGrid, right: zeroScenario ? 88 : 58, top: 22 },
    tooltip: {
      trigger: "axis",
      axisPointer: { type: "shadow" },
      valueFormatter: (value: number | unknown[]) => {
        const amount = Number(Array.isArray(value) ? value[0] : value);
        return insightsStatisticsChartsEquityChange({ direction: direction(amount), amount: fmtComp(Math.abs(amount)) });
      },
    },
    xAxis: {
      ...valueAxis,
      min: zeroScenario ? -1 : undefined,
      max: zeroScenario ? 1 : undefined,
      interval: zeroScenario ? 1 : undefined,
      axisLabel: {
        color: FAINT,
        fontSize: 9,
        formatter: (v: number) => zeroScenario
          ? (v === 0 ? "$0" : "")
          : (v === 0 ? "$0" : `${v > 0 ? "+" : "−"}${fmtComp(Math.abs(v))}`),
      },
    },
    yAxis: { ...categoryAxis, data: rows.map((c) => companyName(c.company)) },
    series: [
      {
        type: "bar",
        data: rows.map((c) => ({
          value: c.change,
          itemStyle: {
            color: c.change > 0 ? SIGNAL : c.change < 0 ? DANGER : MUTED,
            opacity: c.change === 0 ? 0.28 : 0.86,
            borderRadius: c.change >= 0 ? [0, 4, 4, 0] : [4, 0, 0, 4],
          },
        })),
        barMaxWidth: 14,
        label: {
          show: !zeroScenario,
          position: "right",
          color: MUTED,
          fontFamily: mono,
          fontSize: 9,
          formatter: ({ value }: { value: number }) => value === 0 ? "—" : `${value > 0 ? "+" : "−"}${fmtComp(Math.abs(value))}`,
        },
        markLine: { silent: true, symbol: "none", lineStyle: { color: BORDER }, data: [{ xAxis: 0 }] },
      },
      ...(zeroScenario ? [{
        name: insightsStatisticsChartsNoChange(),
        type: "scatter" as const,
        data: rows.map((c) => [0, companyName(c.company)]),
        symbolSize: 9,
        itemStyle: { color: DATA_2, borderColor: "var(--app-surface-raised)", borderWidth: 2 },
        label: {
          show: true,
          position: "right" as const,
          color: MUTED,
          fontFamily: mono,
          fontSize: 9,
          formatter: insightsStatisticsChartsNoChange(),
        },
        tooltip: { show: false },
      }] : []),
    ],
  };
  return (
    <EChart
      ariaLabel={insightsStatisticsChartsEquityShockwaveByCompany()}
      className="chart-trajectory"
      height={Math.max(zeroScenario ? 220 : 250, 58 + rows.length * 34)}
      option={option}
      summary={rows.map((c) => `${companyName(c.company)}: ${c.change >= 0 ? "+" : "−"}${fmtComp(Math.abs(c.change))}`).join(", ")}
    />
  );
}

/** A narrowed slice's skills: how much of the slice names each (x) against how
 *  much more than the market it does (y, log; the line is the market's own
 *  rate). */
export function SkillsConstellationChart({ skills }: { skills: TopSkill[] }) {
  const rows = skills.filter((s) => s.lift != null && s.lift > 0).slice(0, 18);
  const option: EChartsCoreOption = {
    grid: { ...compactGrid, left: 48, right: 32, bottom: 42, top: 28 },
    tooltip: {
      formatter: (p: { dataIndex: number }) => {
        const skill = rows[p.dataIndex];
        return tooltipHtml(skillName(skill.term), [
          insightsStatisticsChartsShareAgainstMarket({ share: Math.round(skill.share * 100), market_share: Math.round(skill.market_share * 100) }),
          insightsStatisticsChartsLiftTheMarketSRate({ lift: String(skill.lift) }),
        ]);
      },
    },
    xAxis: {
      ...valueAxis,
      name: insightsStatisticsChartsShareOfTheseRoles(),
      nameLocation: "middle",
      nameGap: 28,
      nameTextStyle: { color: FAINT, fontSize: 9 },
      axisLabel: { color: FAINT, fontSize: 10, formatter: (v: number) => `${v}%` },
    },
    yAxis: {
      type: "log",
      logBase: 2,
      min: 0.25,
      name: insightsStatisticsChartsTheMarketSRate(),
      nameTextStyle: { color: FAINT, fontSize: 9 },
      axisLine: { show: false },
      axisTick: { show: false },
      axisLabel: { color: FAINT, fontSize: 10, formatter: (v: number) => `×${v}` },
      splitLine: { lineStyle: { color: BORDER, type: "dashed" } },
    },
    series: [
      {
        type: "scatter",
        data: rows.map((s, index) => ({
          name: skillName(s.term),
          value: [Math.round(s.share * 1000) / 10, s.lift],
          label: { show: index < 5, position: index % 2 ? "bottom" : "top" },
        })),
        symbolSize: 14,
        itemStyle: { color: SIGNAL, opacity: 0.74, borderColor: DATA_2, borderWidth: 1.5 },
        label: { show: false, color: MUTED, fontSize: 10, distance: 7, formatter: "{b}" },
        labelLayout: { hideOverlap: true, moveOverlap: "shiftY" },
        markLine: {
          silent: true,
          symbol: "none",
          label: { show: false },
          lineStyle: { color: BORDER, type: "dashed", opacity: 0.85 },
          data: [{ yAxis: 1 }],
        },
        emphasis: {
          itemStyle: { opacity: 1, borderWidth: 2 },
          label: { show: true, color: "var(--app-text)", fontWeight: 700 },
          scale: 1.08,
        },
      },
    ],
  };
  return (
    <EChart
      ariaLabel={insightsStatisticsChartsWhatSetsTheseRolesApart()}
      className="chart-skills"
      height={350}
      option={option}
      summary={rows.map((s) => insightsStatisticsChartsOfTheseRolesTheMarket({ skill: skillName(s.term), share: Math.round(s.share * 100), lift: String(s.lift) })).join(", ")}
    />
  );
}

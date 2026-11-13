import { describe, expect, it } from "vitest";
import type { DisclosureRates } from "../../../api";
import { msg } from "../../../test/msg";
import {
  buildDisclosureRateOption,
  disclosureRateRows,
  disclosureRateSummary,
  unratedCount,
} from "./disclosure";

const rates = (over: Partial<DisclosureRates> = {}): DisclosureRates => ({
  overall: { open: 100, checked: 80, disclosed: 40, rate: 0.5 },
  by_level: [
    { level_band: "senior", open: 60, checked: 50, disclosed: 30, rate: 0.6 },
    { level_band: "staff", open: 40, checked: 30, disclosed: 10, rate: 0.3333 },
    // Nothing checked yet -> no rate can be stated for this level.
    { level_band: "principal", open: 20, checked: 0, disclosed: 0, rate: null },
  ],
  ...over,
});

const opt = (o: unknown) => o as Record<string, any>;

describe("disclosureRateRows", () => {
  it("drops levels with no rate instead of drawing them at zero", () => {
    // "We have not checked Principal yet" and "employers state nothing at
    // Principal" are different findings; a 0% bar would assert the second.
    const rows = disclosureRateRows(rates({
      by_level: [
        { level_band: "senior", open: 60, checked: 50, disclosed: 30, rate: 0.6 },
        { level_band: "staff", open: 40, checked: 30, disclosed: 0, rate: 0 },
        { level_band: "principal", open: 20, checked: 0, disclosed: 0, rate: null },
      ],
    }));

    expect(rows.map((r) => r.key)).toEqual(["staff", "senior"]);
    expect(unratedCount(rates())).toBe(1);
    // A checked level where employers genuinely state nothing IS drawn at 0%.
    expect(rows.find((r) => r.key === "staff")!.rate).toBe(0);
  });

  it("ranks the lowest rate first and applies display names", () => {
    const rows = disclosureRateRows(rates({
      by_level: [
        { level_band: "senior", open: 10, checked: 10, disclosed: 9, rate: 0.9 },
        { level_band: "staff", open: 5, checked: 5, disclosed: 1, rate: 0.2 },
        { level_band: "principal", open: 10, checked: 10, disclosed: 2, rate: 0.2 },
      ],
    }));
    // Equal rates: the level with more checked roles first.
    expect(rows.map((r) => r.label)).toEqual(["Principal", "Staff", "Senior"]);
  });

  it("puts the first row on top and every tooltip on its own bar", () => {
    const rows = disclosureRateRows(rates({
      by_level: [
        { level_band: "senior", open: 10, checked: 10, disclosed: 9, rate: 0.9 },
        { level_band: "staff", open: 10, checked: 10, disclosed: 0, rate: 0 },
        { level_band: "principal", open: 10, checked: 10, disclosed: 5, rate: 0.5 },
      ],
    }));
    const option = opt(buildDisclosureRateOption(rows));
    const labels: string[] = option.yAxis.data;
    // ECharts draws category 0 at the bottom: the lowest rate is the last.
    expect(labels[labels.length - 1]).toBe("Staff");
    labels.forEach((label, dataIndex) => {
      const box = document.createElement("div");
      box.innerHTML = option.tooltip.formatter({ dataIndex });
      expect(box.querySelector("strong")?.textContent).toBe(label);
    });
  });

  it("labels level bands and names the unclassified bucket", () => {
    const rows = disclosureRateRows(rates({
      by_level: [{ level_band: "", open: 5, checked: 5, disclosed: 1, rate: 0.2 }],
    }));
    expect(rows[0].label).toBe(msg("insights-disclosure-unclassified"));
  });

  it("names the roles whose level we cannot place as such, never as a rung", () => {
    const rows = disclosureRateRows(rates({
      by_level: [
        { level_band: "principal", open: 5, checked: 5, disclosed: 4, rate: 0.8 },
        { level_band: "unstated", open: 9, checked: 6, disclosed: 3, rate: 0.5 },
      ],
    }));
    expect(rows.map((r) => r.label)).toEqual([msg("taxonomy-level-not-placed"), "Principal"]);
  });
});

describe("buildDisclosureRateOption", () => {
  it("scales the axis 0-100%, never to the leading level", () => {
    // Auto-scaling a share makes 12% look like a full bar.
    const option = opt(buildDisclosureRateOption(disclosureRateRows(rates())));

    expect(option.xAxis.min).toBe(0);
    expect(option.xAxis.max).toBe(100);
  });

  it("plots percentages, and pairs each bar with its raw counts", () => {
    const option = opt(buildDisclosureRateOption(disclosureRateRows(rates())));
    const bar = option.series[0];

    // Categories are reversed so the lowest rate sits on top.
    expect(option.yAxis.data).toEqual(["Senior", "Staff"]);
    expect(bar.data).toEqual([60, 33.3]);
    expect(bar.label.formatter({ dataIndex: 1 })).toBe("33% · 10/30");
  });

  it("tooltips the denominator, not just the share", () => {
    const option = opt(buildDisclosureRateOption(disclosureRateRows(rates())));
    expect(option.tooltip.formatter({ dataIndex: 1 }))
      .toContain(msg("insights-disclosure-of-checked-open-roles", { disclosed: 10, checked: 30 }));
  });
});

describe("disclosureRateSummary", () => {
  it("states each group's share and counts, and flags the unrated ones", () => {
    const rows = disclosureRateRows(rates());
    const text = disclosureRateSummary(rows, 1);

    expect(text).toContain(msg("insights-disclosure-of-roles", {
      label: "Senior", rate: "60%", disclosed: 30, checked: 50,
    }));
    expect(text).toMatch(/1 more group has no role checked yet/);
  });

  it("omits the unrated note when every group has a rate", () => {
    expect(disclosureRateSummary(disclosureRateRows(rates()), 0)).not.toMatch(
      /no role checked/,
    );
  });

  it("handles a window where nothing has been checked", () => {
    expect(disclosureRateSummary([], 0)).toMatch(/no open roles have been checked/i);
  });
});

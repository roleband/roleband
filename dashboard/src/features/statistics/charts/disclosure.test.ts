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
  by_company: [
    { company: "google", open: 50, checked: 50, disclosed: 40, rate: 0.8 },
    { company: "meta", open: 30, checked: 30, disclosed: 0, rate: 0 },
    // Nothing checked yet -> no rate can be stated for this employer.
    { company: "openai", open: 20, checked: 0, disclosed: 0, rate: null },
  ],
  by_level: [
    { level_band: "senior", open: 60, checked: 50, disclosed: 30, rate: 0.6 },
    { level_band: "staff", open: 40, checked: 30, disclosed: 10, rate: 0.3333 },
  ],
  ...over,
});

const opt = (o: unknown) => o as Record<string, any>;

describe("disclosureRateRows", () => {
  it("drops groups with no rate instead of drawing them at zero", () => {
    // "We have not checked openai yet" and "openai publishes nothing" are
    // different findings; a 0% bar would assert the second from the first.
    const rows = disclosureRateRows(rates(), "company");

    expect(rows.map((r) => r.key)).toEqual(["meta", "google"]);
    expect(unratedCount(rates(), "company")).toBe(1);
    // A checked employer that genuinely discloses nothing IS drawn at 0%.
    expect(rows.find((r) => r.key === "meta")!.rate).toBe(0);
  });

  it("ranks the lowest rate first and applies display names", () => {
    const rows = disclosureRateRows(
      rates({
        by_company: [
          { company: "google", open: 10, checked: 10, disclosed: 9, rate: 0.9 },
          { company: "apple", open: 5, checked: 5, disclosed: 1, rate: 0.2 },
          { company: "meta", open: 10, checked: 10, disclosed: 2, rate: 0.2 },
        ],
      }),
      "company",
    );
    // Equal rates: the employer with more checked roles first.
    expect(rows.map((r) => r.label)).toEqual(["Meta", "Apple", "Google"]);
  });

  it("puts the first row on top and every tooltip on its own bar", () => {
    const rows = disclosureRateRows(
      rates({
        by_company: [
          { company: "google", open: 10, checked: 10, disclosed: 9, rate: 0.9 },
          { company: "meta", open: 10, checked: 10, disclosed: 0, rate: 0 },
          { company: "apple", open: 10, checked: 10, disclosed: 5, rate: 0.5 },
        ],
      }),
      "company",
    );
    const option = opt(buildDisclosureRateOption(rows));
    const labels: string[] = option.yAxis.data;
    // ECharts draws category 0 at the bottom: the lowest rate is the last.
    expect(labels[labels.length - 1]).toBe("Meta");
    labels.forEach((label, dataIndex) => {
      const box = document.createElement("div");
      box.innerHTML = option.tooltip.formatter({ dataIndex });
      expect(box.querySelector("strong")?.textContent).toBe(label);
    });
  });

  it("labels level bands and names the unclassified bucket", () => {
    const rows = disclosureRateRows(
      rates({
        by_level: [{ level_band: "", open: 5, checked: 5, disclosed: 1, rate: 0.2 }],
      }),
      "level",
    );
    expect(rows[0].label).toBe(msg("insights-disclosure-unclassified"));
  });

  it("names the roles whose level we cannot place as such, never as a rung", () => {
    const rows = disclosureRateRows(
      rates({
        by_level: [
          { level_band: "principal", open: 5, checked: 5, disclosed: 4, rate: 0.8 },
          { level_band: "unstated", open: 9, checked: 6, disclosed: 3, rate: 0.5 },
        ],
      }),
      "level",
    );
    expect(rows.map((r) => r.label)).toEqual([msg("taxonomy-level-not-placed"), "Principal"]);
  });
});

describe("buildDisclosureRateOption", () => {
  it("scales the axis 0-100%, never to the leading employer", () => {
    // Auto-scaling a share makes 12% look like a full bar.
    const option = opt(buildDisclosureRateOption(disclosureRateRows(rates(), "company")));

    expect(option.xAxis.min).toBe(0);
    expect(option.xAxis.max).toBe(100);
  });

  it("plots percentages, and pairs each bar with its raw counts", () => {
    const option = opt(buildDisclosureRateOption(disclosureRateRows(rates(), "company")));
    const bar = option.series[0];

    // Categories are reversed so the lowest rate sits on top.
    expect(option.yAxis.data).toEqual(["Google", "Meta"]);
    expect(bar.data).toEqual([80, 0]);
    expect(bar.label.formatter({ dataIndex: 0 })).toBe("80% · 40/50");
  });

  it("tooltips the denominator, not just the share", () => {
    const option = opt(buildDisclosureRateOption(disclosureRateRows(rates(), "company")));
    expect(option.tooltip.formatter({ dataIndex: 0 })).toContain("40 of 50 checked open roles");
  });
});

describe("disclosureRateSummary", () => {
  it("states each group's share and counts, and flags the unrated ones", () => {
    const rows = disclosureRateRows(rates(), "company");
    const text = disclosureRateSummary(rows, 1);

    expect(text).toContain("Google: 80%, 40 of 50 roles");
    expect(text).toMatch(/1 more group has no role checked yet/);
  });

  it("omits the unrated note when every group has a rate", () => {
    expect(disclosureRateSummary(disclosureRateRows(rates(), "level"), 0)).not.toMatch(
      /no role checked/,
    );
  });

  it("handles a window where nothing has been checked", () => {
    expect(disclosureRateSummary([], 0)).toMatch(/no open roles have been checked/i);
  });
});

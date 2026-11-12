import { describe, expect, it } from "vitest";
import type { DisclosedBand, PostedLevel, PostedPay } from "../../../api";
import { msg } from "../../../test/msg";
import { bandEmployers, bandScale, bandsByLevel, exclusionNote, levelSummary } from "./compBands";

const band = (over: Partial<DisclosedBand> = {}): DisclosedBand => ({
  company: "google",
  level_band: "staff",
  low: 262_000,
  high: 365_000,
  reqs: 18,
  ...over,
});

const figure = (over: Partial<PostedLevel> = {}): PostedLevel => ({
  level_band: "staff", ranges: 9, employers: 6, roles: 30, enough: true,
  low: 240_000, high: 340_000, mid_p25: 260_000, mid_p75: 320_000, ...over,
});

describe("bandsByLevel", () => {
  it("makes one row per level, counting ranges and employers, never roles", () => {
    const rows = bandsByLevel([
      band({ level_band: "senior", low: 200_000, high: 280_000, reqs: 50 }),
      band(),
      band({ company: "apple", low: 240_000, high: 340_000, reqs: 1 }),
      band({ company: "apple", low: 300_000, high: 420_000, reqs: 1 }),
    ]);

    expect(rows.map((r) => [r.level, r.bands.length, r.employers])).toEqual([
      ["senior", 1, 1],
      ["staff", 3, 2],
    ]);
  });
});

describe("levelSummary", () => {
  const [row] = bandsByLevel([band(), band({ company: "apple", low: 240_000, high: 340_000 })]);

  it("says the level's typical range in the country's currency", () => {
    expect(levelSummary(row, figure(), [], null, "GBP")).toBe(
      msg("insights-comp-bands-level-ranges", { label: "Staff", bands: 2, employers: 2, figure: "some", low: "£240K", high: "£340K" }),
    );
  });

  it("says a level below the minimums has too few ranges, never a figure", () => {
    const said = levelSummary(row, figure({ enough: false, low: null, high: null }), [], null, "USD");
    expect(said).toBe(
      msg("insights-comp-bands-level-ranges", { label: "Staff", bands: 2, employers: 2, figure: "none", low: "", high: "" }),
    );
    expect(said).not.toMatch(/\$/);
  });

  it("names the picked employer's ranges, or that it posts none here", () => {
    const summary = msg("insights-comp-bands-level-ranges", {
      label: "Staff", bands: 2, employers: 2, figure: "some", low: "$240K", high: "$340K",
    });
    expect(levelSummary(row, figure(), [band()], "google", "USD")).toBe(
      msg("insights-comp-bands-employer-at-level", {
        summary, employer: "Google", published: "some", ranges: msg("insights-comp-bands-to", { low: "$262K", high: "$365K" }),
      }),
    );
    expect(levelSummary(row, figure(), [], "meta", "USD")).toBe(
      msg("insights-comp-bands-employer-at-level", { summary, employer: "Meta", published: "none", ranges: "" }),
    );
  });
});

describe("bandScale", () => {
  it("rounds the ends to a step every band fits inside", () => {
    const { min, max, ticks } = bandScale([band({ low: 207_000, high: 365_000 }), band({ low: 140_000, high: 520_000 })]);
    expect(min).toBeLessThanOrEqual(140_000);
    expect(max).toBeGreaterThanOrEqual(520_000);
    expect(ticks[0]).toBe(min);
    expect(ticks[ticks.length - 1]).toBe(max);
    expect(ticks.length).toBeGreaterThanOrEqual(3);
    expect(ticks.length).toBeLessThanOrEqual(8);
  });

  it("gives round ticks in a currency counted in millions", () => {
    const { ticks } = bandScale([band({ low: 3_500_000, high: 6_000_000 }), band({ low: 2_000_000, high: 9_000_000 })]);
    expect(ticks.length).toBeGreaterThanOrEqual(3);
    expect(ticks.length).toBeLessThanOrEqual(8);
    expect(ticks.every((t) => t % 500_000 === 0)).toBe(true);
  });

  it("has no ticks with no bands", () => {
    expect(bandScale([]).ticks).toEqual([]);
  });
});

describe("bandEmployers", () => {
  it("lists each employer once, most open roles on its bands first", () => {
    const options = bandEmployers([
      band({ company: "apple", reqs: 3 }),
      band({ company: "google", reqs: 4, level_band: "senior" }),
      band({ company: "google", reqs: 4 }),
    ]);
    expect(options).toEqual([
      { value: "google", label: "Google", count: 8 },
      { value: "apple", label: "Apple", count: 3 },
    ]);
  });
});

const none: PostedPay["excluded"] = { not_base: 0, not_yearly: 0, implausible: 0, no_country: 0, placed_by_pay: 0 };

describe("exclusionNote", () => {
  it("says every reason a role is left out, one sentence each, singular for one", () => {
    expect(exclusionNote({ ...none, not_base: 3, not_yearly: 1 })).toBe(
      msg("insights-comp-bands-not-base", { count: 3 }) + " " + msg("insights-comp-bands-not-yearly", { count: 1 }),
    );
    expect(msg("insights-comp-bands-not-yearly", { count: 1 })).toMatch(/^1 more role posts its/);
  });

  it("never leaves out a reason, placed-by-pay and no-country included", () => {
    const text = exclusionNote({ not_base: 1, not_yearly: 2, implausible: 3, no_country: 4, placed_by_pay: 5 });
    expect(text).toContain(msg("insights-comp-bands-not-base", { count: 1 }));
    expect(text).toContain(msg("insights-comp-bands-not-yearly", { count: 2 }));
    expect(text).toContain(msg("insights-comp-bands-implausible", { count: 3 }));
    expect(text).toContain(msg("insights-comp-bands-no-country", { count: 4 }));
    expect(text).toContain(msg("insights-comp-bands-placed-by-pay", { count: 5 }));
  });

  it("says nothing when nothing is left out", () => {
    expect(exclusionNote(none)).toBe("");
  });
});

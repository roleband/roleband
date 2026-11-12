import { describe, expect, it } from "vitest";
import type { PostedCountry, PostedLevel, PostedPay } from "../../../api";
import { postedCountry, postedLevel, postedLevels } from "./postedPay";

const level = (level_band: string, over: Partial<PostedLevel> = {}): PostedLevel => ({
  level_band, ranges: 10, employers: 6, roles: 20, enough: true,
  low: 200_000, high: 270_000, mid_p25: 215_000, mid_p75: 255_000, ...over,
});
const thin = (level_band: string) => level(level_band, { ranges: 3, employers: 2, enough: false, low: null, high: null, mid_p25: null, mid_p75: null });

const country = (code: string, levels: PostedLevel[], over: Partial<PostedCountry> = {}): PostedCountry => ({
  country: code, currency: "USD", ranges: levels.reduce((n, l) => n + l.ranges, 0), yours: false, levels,
  not_placed: { roles: 0, ranges: 0 }, other_currency: 0, bands: [], ...over,
});

const posted = (countries: PostedCountry[], over: Partial<PostedPay> = {}): PostedPay => ({
  min_employers: 5, min_ranges: 8, default_country: countries[0]?.country ?? null, countries,
  excluded: { not_base: 0, not_yearly: 0, implausible: 0, no_country: 0, placed_by_pay: 0 },
  your_levels: [], ...over,
});

describe("postedCountry", () => {
  const us = country("US", [level("senior")]);
  const gb = country("GB", [level("senior")], { currency: "GBP" });

  it("opens on the server's default, and on a country asked for in the link", () => {
    const p = posted([gb, us], { default_country: "US" });
    expect(postedCountry(p, null)?.country).toBe("US");
    expect(postedCountry(p, "GB")?.country).toBe("GB");
  });

  it("falls back to the default for a country the link names but the server does not send", () => {
    expect(postedCountry(posted([us, gb], { default_country: "US" }), "SE")?.country).toBe("US");
  });

  it("has no country when nothing is posted anywhere", () => {
    expect(postedCountry(posted([]), "US")).toBeNull();
  });
});

describe("postedLevels", () => {
  it("adds the person's own levels with nothing posted, so the screen can say so, junior first", () => {
    const levels = postedLevels(country("SE", [level("senior")]), ["director_plus", "principal"]);
    expect(levels.map((l) => [l.level_band, l.ranges, l.enough])).toEqual([
      ["senior", 10, true],
      ["principal", 0, false],
      ["director_plus", 0, false],
    ]);
  });

  it("keeps a known level picked elsewhere, empty, and never adds an unknown one", () => {
    const se = country("SE", [level("senior")]);
    expect(postedLevels(se, [], "staff").map((l) => [l.level_band, l.ranges])).toEqual([["senior", 10], ["staff", 0]]);
    expect(postedLevels(se, [], "chief_wizard").map((l) => l.level_band)).toEqual(["senior"]);
    expect(postedLevels(se, [], "unstated").map((l) => l.level_band)).toEqual(["senior"]);
  });
});

describe("postedLevel", () => {
  const levels = [level("senior"), thin("staff"), level("principal"), level("director_plus")];

  it("opens on the person's first level that has a figure", () => {
    expect(postedLevel(levels, ["staff", "principal", "director_plus"], null)?.level_band).toBe("principal");
  });

  it("opens on the person's level with too few ranges before another level with a figure", () => {
    expect(postedLevel(levels, ["staff"], null)?.level_band).toBe("staff");
  });

  it("opens on the first level with a figure when the person picked no level", () => {
    expect(postedLevel([thin("senior"), level("staff")], [], null)?.level_band).toBe("staff");
  });

  it("keeps a level asked for in the link, even one with too few ranges", () => {
    expect(postedLevel(levels, ["principal"], "staff")?.level_band).toBe("staff");
  });

  it("ignores a level the country does not offer", () => {
    expect(postedLevel(levels, ["principal"], "intern")?.level_band).toBe("principal");
  });
});

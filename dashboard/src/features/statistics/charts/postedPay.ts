import type { PostedCountry, PostedLevel, PostedPay } from "../../../api";
import { BAND_ORDER } from "../../../format";

/**
 * Which country and level the Pay tab shows.
 *
 * The server sends every country with a posted range, and the person's own
 * countries even with none, so the screen can say a country has nothing
 * rather than leave it out. The level picker likewise offers the person's
 * own levels even where a country has no range at them.
 */

/** Seniority rank, junior first, as the server orders levels. */
const rank = (level: string) => {
  const i = BAND_ORDER.indexOf(level);
  return i < 0 ? 0 : BAND_ORDER.length - i;
};

const emptyLevel = (level_band: string): PostedLevel => ({
  level_band,
  ranges: 0,
  employers: 0,
  roles: 0,
  enough: false,
  low: null,
  high: null,
  mid_p25: null,
  mid_p75: null,
});

/** The country asked for, else the server's default, else the first; null
 *  when no country has anything to show. */
export function postedCountry(posted: PostedPay, asked: string | null): PostedCountry | null {
  const find = (code: string | null) => posted.countries.find((c) => c.country === code);
  return find(asked) ?? find(posted.default_country) ?? posted.countries[0] ?? null;
}

/** A country's levels with a range, and the person's own with none, junior first. */
export function postedLevels(country: PostedCountry, yourLevels: readonly string[]): PostedLevel[] {
  const levels = new Map(country.levels.map((l) => [l.level_band, l]));
  for (const level of yourLevels) if (!levels.has(level)) levels.set(level, emptyLevel(level));
  return [...levels.values()].sort((a, b) => rank(a.level_band) - rank(b.level_band));
}

/**
 * The level asked for when the country offers it. Otherwise the person's
 * first level with a figure, then their first with any range, then the
 * first level with a figure, then the first with any range: the tab opens
 * on the person's own level whenever there is something to say about it.
 */
export function postedLevel(
  levels: readonly PostedLevel[],
  yourLevels: readonly string[],
  asked: string | null,
): PostedLevel | null {
  const pick = levels.find((l) => l.level_band === asked);
  if (pick) return pick;
  const yours = levels.filter((l) => yourLevels.includes(l.level_band));
  return (
    yours.find((l) => l.enough)
    ?? yours.find((l) => l.ranges > 0)
    ?? levels.find((l) => l.enough)
    ?? levels.find((l) => l.ranges > 0)
    ?? levels[0]
    ?? null
  );
}

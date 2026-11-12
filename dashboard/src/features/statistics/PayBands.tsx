import { useMemo, useState } from "react";
import type { DisclosedBand, PostedCountry } from "../../api";
import { companyName, fmtCompIn } from "../../format";
import { FilterSelect } from "../../ui";
import { bandEmployers, bandScale, bandsByLevel, levelSummary } from "./charts/compBands";
import { levelLabel } from "./charts/levelLabel";
import {
  insightsPayBandsAnyEmployer,
  insightsPayBandsBandsFromEmployers,
  insightsPayBandsEachLineIsOnePublished,
  insightsPayBandsEmployerBands,
  insightsPayBandsPublishedBaseSalaryBandsBy,
  insightsPostedNotPlaced,
  insightsPostedTooFew,
} from "../../copy/gen/insights";

/* Every posted base range in one country, a row per level, in the country's
 * own currency. See `compBands.ts` for why the unit is the range and never a
 * role. Every range is a faint span; the outlined span is the level's typical
 * range, drawn only where the level has one; an employer picked here is the
 * only colour on the chart. */

export function PayBands({ country }: { country: PostedCountry }) {
  const [employer, setEmployer] = useState<string | null>(null);
  const currency = country.currency ?? "USD";
  const money = (x: number) => fmtCompIn(x, currency);
  const range = (low: number, high: number) => `${money(low)}–${money(high)}`;
  const levels = useMemo(() => bandsByLevel(country.bands), [country.bands]);
  const figures = useMemo(() => new Map(country.levels.map((l) => [l.level_band, l])), [country.levels]);
  const scale = useMemo(() => bandScale(country.bands), [country.bands]);
  const employers = useMemo(() => bandEmployers(country.bands), [country.bands]);

  const span = (low: number, high: number) => ({
    left: `${((low - scale.min) / (scale.max - scale.min)) * 100}%`,
    width: `${Math.max(0.6, ((high - low) / (scale.max - scale.min)) * 100)}%`,
  });

  return (
    <div className="pay-bands">
      <div className="pay-bands-pick">
        <FilterSelect
          label={employer ? companyName(employer) : insightsPayBandsAnyEmployer()}
          options={employers}
          selected={employer ? [employer] : []}
          onChange={(next) => setEmployer(next[0] ?? null)}
          multiple={false}
          searchable
        />
        <span className="hiring-note">
          {insightsPayBandsEachLineIsOnePublished()}
        </span>
      </div>
      <ol className="pay-bands-rows" aria-label={insightsPayBandsPublishedBaseSalaryBandsBy()}>
        {levels.map((row) => {
          const figure = figures.get(row.level);
          const picked: DisclosedBand[] = employer ? row.bands.filter((b) => b.company === employer) : [];
          return (
            <li key={row.level} className="pay-bands-row">
              <span className="pay-bands-level">
                <strong>{levelLabel(row.level)}</strong>
                <span className="dim">
                  {insightsPayBandsBandsFromEmployers({ bands: row.bands.length, employers: row.employers })}
                </span>
              </span>
              <span className="pay-bands-track" role="img" aria-label={levelSummary(row, figure, picked, employer, currency)}>
                {row.bands.map((b) => (
                  <span key={`${b.company}-${b.low}-${b.high}`} className="pay-band" style={span(b.low, b.high)} />
                ))}
                {figure?.low != null && figure.high != null && (
                  <span className="pay-band-median" style={span(figure.low, figure.high)} />
                )}
                {picked.map((b) => (
                  <span key={`picked-${b.low}-${b.high}`} className="pay-band" data-chosen style={span(b.low, b.high)} />
                ))}
              </span>
              <span className={`pay-bands-value${(employer && !picked.length) || (!employer && figure?.low == null) ? " dim" : ""}`}>
                {!employer
                  ? figure?.low != null && figure.high != null
                    ? range(figure.low, figure.high)
                    : insightsPostedTooFew()
                  : picked.length === 1
                    ? range(picked[0].low, picked[0].high)
                    : insightsPayBandsEmployerBands({
                        published: picked.length ? "some" : "none",
                        bands: picked.length,
                        range: picked.length ? range(Math.min(...picked.map((b) => b.low)), Math.max(...picked.map((b) => b.high))) : "",
                      })}
              </span>
            </li>
          );
        })}
      </ol>
      {/* The axis shares the rows' grid, so its ticks sit under the tracks. */}
      <div className="pay-bands-row" aria-hidden="true">
        <span />
        <span className="pay-bands-axis">
          {scale.ticks.map((t) => (
            <span key={t} style={{ left: `${((t - scale.min) / (scale.max - scale.min)) * 100}%` }}>
              {money(t)}
            </span>
          ))}
        </span>
        <span />
      </div>
      {country.not_placed.roles > 0 && (
        <p className="hiring-note">
          {insightsPostedNotPlaced({ roles: country.not_placed.roles, ranges: country.not_placed.ranges })}
        </p>
      )}
    </div>
  );
}

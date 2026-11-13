import { useSearchParams } from "react-router-dom";
import { CompensationStats, InsightsScope, PayTable as PayTableData, PostedCountry, PostedLevel, PostedPay, api } from "../../api";
import { useAsyncResource } from "../../hooks/useAsyncResource";
import { useSourceSwitch } from "../../context/SyncState";
import { fmtCompIn } from "../../format";
import { country as countryName } from "../../copy/format";
import { DisclosureRatePanel } from "./DisclosurePanel";
import { PayBands } from "./PayBands";
import { PayTable } from "./PayTable";
import { exclusionNote } from "./charts/compBands";
import { pct } from "./charts/disclosure";
import { levelLabel } from "./charts/levelLabel";
import { postedCountry, postedLevel, postedLevels } from "./charts/postedPay";
import { InfoTip } from "../../ui/InfoTip";
import { Badge, Button, Select } from "../../ui";
import { ResourceLoadState } from "../../ui/ResourceLoadState";
import { InsightHero } from "./InsightHero";
import { commonTryAgain } from "../../copy/gen/common";
import { sharedRefreshFailed } from "../../copy/gen/shared";
import {
  insightsCompensationPanelAboutPublishedSalaryBands,
  insightsCompensationPanelBandsFromEmployers,
  insightsCompensationPanelBaseSalaryQuotedFromThe,
  insightsCompensationPanelLoadFailed,
  insightsCompensationPanelLoading,
  insightsCompensationPanelPublishedBands,
  insightsPayBandsBandsFromEmployers,
  insightsPostedByLevel,
  insightsPostedChecked,
  insightsPostedCountry,
  insightsPostedEveryRange,
  insightsPostedHowRead,
  insightsPostedHowReadBody,
  insightsPostedLevel,
  insightsPostedLine,
  insightsPostedMiddleHalf,
  insightsPostedMidpoints,
  insightsPostedNeeds,
  insightsPostedNone,
  insightsPostedNoneAnywhere,
  insightsPostedNoneAtLevel,
  insightsPostedNoneInCountry,
  insightsPostedNotPlaced,
  insightsPayTableLoadFailed,
  insightsPayTableLoading,
  insightsPostedOtherCurrency,
  insightsPostedShare,
  insightsPostedTooFew,
  insightsPostedTypically,
  insightsPostedYourLevel,
  insightsPostedYourPlace,
  insightsLevelsYourLevel,
} from "../../copy/gen/insights";

/** A range in the country's own currency, never converted. */
const inCurrency = (country: PostedCountry) => (low: number, high: number) =>
  `${fmtCompIn(low, country.currency ?? "USD")}–${fmtCompIn(high, country.currency ?? "USD")}`;

/* The answer the tab opens on: what employers post as yearly base salary for
   one level in one country. A level below the minimums shows its counts and
   why it has no figure; it never shows a figure from too few ranges. */
function PostedHero({
  posted,
  country,
  level,
  levels,
  share,
  onCountry,
  onLevel,
}: {
  posted: PostedPay;
  country: PostedCountry | null;
  level: PostedLevel | null;
  levels: readonly PostedLevel[];
  share: CompensationStats["disclosure"]["overall"];
  onCountry: (code: string) => void;
  onLevel: (level: string) => void;
}) {
  // Two tiles in every state, so the hero keeps its shape: a level with no
  // figure has no middle half either, and says so with a dash.
  const tiles = (middle: string | null) => [
    { label: insightsPostedMiddleHalf(), value: middle ?? "—", sub: insightsPostedMidpoints(), wide: middle != null },
    {
      label: insightsPostedShare(),
      value: share.rate == null ? "—" : pct(share.rate),
      sub: insightsPostedChecked({ checked: share.checked }),
    },
  ];
  if (!country) {
    return <InsightHero tab="compensation" figure={insightsPostedNone()} line={insightsPostedNoneAnywhere()} kpis={tiles(null)} />;
  }
  const range = inCurrency(country);
  const place = countryName(country.country);
  const figure = level?.low != null && level.high != null;
  const middle = level?.mid_p25 != null && level.mid_p75 != null ? range(level.mid_p25, level.mid_p75) : null;

  let line;
  if (!country.ranges) line = insightsPostedNoneInCountry({ country: place });
  else if (!level || !level.ranges) line = insightsPostedNoneAtLevel({ country: place });
  else {
    line = (
      <>
        {insightsPostedLine({
          level: levelLabel(level.level_band),
          country: place,
          ranges: level.ranges,
          employers: level.employers,
          roles: level.roles,
        })}
        {!figure && <> {insightsPostedNeeds({ min_employers: posted.min_employers, min_ranges: posted.min_ranges })}</>}
        <InfoTip label={insightsPostedHowRead()}>{insightsPostedHowReadBody()}</InfoTip>
      </>
    );
  }

  return (
    <InsightHero
      tab="compensation"
      figure={
        level?.low != null && level.high != null
          ? insightsPostedTypically({ low: fmtCompIn(level.low, country.currency ?? "USD"), high: fmtCompIn(level.high, country.currency ?? "USD") })
          : level?.ranges
            ? insightsPostedTooFew()
            : insightsPostedNone()
      }
      line={line}
      kpis={tiles(middle)}
    >
      <div className="posted-pick">
        <Select
          label={insightsPostedCountry()}
          value={country.country}
          onChange={onCountry}
          options={posted.countries.map((c) => ({
            value: c.country,
            label: c.yours ? insightsPostedYourPlace({ name: countryName(c.country) }) : countryName(c.country),
          }))}
        />
        {levels.length > 0 && level && (
          <Select
            label={insightsPostedLevel()}
            value={level.level_band}
            onChange={onLevel}
            options={levels.map((l) => ({
              value: l.level_band,
              label: posted.your_levels.includes(l.level_band)
                ? insightsLevelsYourLevel({ level: levelLabel(l.level_band) })
                : levelLabel(l.level_band),
            }))}
          />
        )}
      </div>
    </InsightHero>
  );
}

/* Every level of one country side by side: its typical range, or why it has
   none, and the roles counted apart. */
function PostedByLevel({
  country,
  levels,
  yourLevels,
}: {
  country: PostedCountry;
  levels: readonly PostedLevel[];
  yourLevels: readonly string[];
}) {
  const range = inCurrency(country);
  const heading = insightsPostedByLevel({ country: countryName(country.country) });
  return (
    <section className="panel" aria-label={heading}>
      <span className="eyebrow">{insightsCompensationPanelPublishedBands()}</span>
      <h3>{heading}</h3>
      <ol className="posted-levels">
        {levels.map((l) => (
          <li key={l.level_band} className="posted-level" title={l.mid_p25 != null && l.mid_p75 != null ? `${insightsPostedMiddleHalf()}: ${range(l.mid_p25, l.mid_p75)}` : undefined}>
            <span className="posted-level-name">
              <strong>{levelLabel(l.level_band)}</strong>
              {yourLevels.includes(l.level_band) && <Badge tone="accent" variant="tint" size="sm">{insightsPostedYourLevel()}</Badge>}
            </span>
            <span className={`posted-level-value${l.low == null ? " dim" : ""}`}>
              {l.low != null && l.high != null ? range(l.low, l.high) : l.ranges ? insightsPostedTooFew() : insightsPostedNone()}
            </span>
            <span className="comp-n">
              {l.ranges > 0 && insightsPayBandsBandsFromEmployers({ bands: l.ranges, employers: l.employers })}
            </span>
          </li>
        ))}
      </ol>
      {country.not_placed.roles > 0 && (
        <p className="hiring-note">{insightsPostedNotPlaced({ roles: country.not_placed.roles, ranges: country.not_placed.ranges })}</p>
      )}
      {country.other_currency > 0 && (
        <p className="hiring-note">{insightsPostedOtherCurrency({ count: country.other_currency })}</p>
      )}
    </section>
  );
}

/** The query keys only the Pay tab reads: the country, level and skill it shows. */
export const PAY_PARAMS = ["country", "level", "skill"] as const;

export function CompensationPanel({
  scope,
  advanced = false,
}: {
  scope?: InsightsScope;
  /** The basic view keeps posted pay and the company table; the advanced view
   *  adds every posted range, who states pay, and pay by discipline. */
  advanced?: boolean;
}) {
  // The roles open now. Pay over time waits for enough history to compare
  // like with like (docs/decisions/0004-insights-answers-a-question.md).
  const { data, error, retry, refresh } = useAsyncResource<CompensationStats>(
    () => api.compensation(scope), [scope], { keep: "stats/compensation" });
  // Pay statistics follow the source answering pay.
  useSourceSwitch(refresh);
  const [params, setParams] = useSearchParams();

  const posted = data?.posted;
  const country = posted ? postedCountry(posted, params.get("country")) : null;
  const levels = country && posted ? postedLevels(country, posted.your_levels, params.get("level")) : [];
  const level = posted ? postedLevel(levels, posted.your_levels, params.get("level")) : null;
  const skill = params.get("skill");
  // The table follows the hero's pickers, so it is its own read: the picked
  // level and country are the question it answers. With neither picked there is
  // no question, so the tab asks nothing.
  const table = useAsyncResource<PayTableData | null>(
    (signal) => (country && level
      ? api.payTable(country.country, level.level_band, skill, scope, signal)
      : Promise.resolve(null)),
    [country?.country ?? "", level?.level_band ?? "", skill, scope],
    { keep: "stats/pay-table" },
  );
  // The table's estimates are the postings' stored figures, which the source
  // answering pay writes, so a switch re-reads the table too.
  useSourceSwitch(table.refresh);
  const choose = (key: "country" | "level" | "skill") => (value: string | null) =>
    setParams((prev) => {
      const next = new URLSearchParams(prev);
      if (value === null) next.delete(key);
      else next.set(key, value);
      // A level or country of its own answers its own skills.
      if (key !== "skill") next.delete("skill");
      return next;
    }, { replace: true });

  if (!data || !posted) {
    return <ResourceLoadState error={error} loading={insightsCompensationPanelLoading()} failed={insightsCompensationPanelLoadFailed()} onRetry={retry} />;
  }

  // Under a country's heading, the roles left out are that country's; every
  // role in no one country, whatever else left it out, is no country's, so
  // each heading says it.
  const excluded = country ? { ...country.excluded, no_country: posted.excluded.without_country } : posted.excluded;
  const rangesExplanation = [
    insightsCompensationPanelBaseSalaryQuotedFromThe(),
    exclusionNote(excluded),
  ].filter(Boolean).join(" ");

  return (
    <>
      <PostedHero
        posted={posted}
        country={country}
        level={level}
        levels={levels}
        share={data.disclosure.overall}
        onCountry={choose("country")}
        onLevel={choose("level")}
      />

      {/* Every company at the picked level, posted range first. A read of its
          own, so it says for itself when it is loading or could not be read;
          a failure that leaves the last answer on screen says so and stays. */}
      {country && level && (table.data
        ? (
          <>
            {table.refreshError && (
              <div className="empty-hint" role="status">
                {sharedRefreshFailed()}{" "}
                <Button variant="ghost" size="sm" onClick={() => void table.refresh({ preserveData: true })}>
                  {commonTryAgain()}
                </Button>
              </div>
            )}
            <PayTable data={table.data} skill={skill} onSkill={choose("skill")} advanced={advanced} />
          </>
        )
        : (
          <ResourceLoadState
            error={table.error}
            loading={insightsPayTableLoading()}
            failed={insightsPayTableLoadFailed()}
            onRetry={table.retry}
          />
        ))}

      {country && levels.length > 0 && (
        <PostedByLevel country={country} levels={levels} yourLevels={posted.your_levels} />
      )}

      {/* The panel stays when no range qualifies, so the reasons each role
          was left out can still be read. */}
      {advanced && !country && <p className="hiring-note">{rangesExplanation}</p>}
      {advanced && country && (
        <div className="panel chart-panel chart-panel-wide">
          <div className="chart-panel-head">
            <div>
              <span className="eyebrow">{insightsCompensationPanelPublishedBands()}</span>
              <h3>
                {insightsPostedEveryRange({ country: countryName(country.country) })}
                <InfoTip label={insightsCompensationPanelAboutPublishedSalaryBands()}>{rangesExplanation}</InfoTip>
              </h3>
            </div>
            {country.bands.length > 0 && (
              <span className="chart-insight">
                {insightsCompensationPanelBandsFromEmployers({
                  bands: country.bands.length,
                  employers: new Set(country.bands.map((b) => b.company)).size,
                })}
              </span>
            )}
          </div>
          {country.bands.length > 0
            ? <PayBands key={country.country} country={country} />
            : <p className="hiring-note">{rangesExplanation}</p>}
        </div>
      )}

      {/* What employers post (above) vs. how many of them post anything (here). */}
      {advanced && <DisclosureRatePanel rates={data.disclosure} />}
    </>
  );
}

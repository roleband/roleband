import { useSearchParams } from "react-router-dom";
import { CompensationStats, CompSummary, InsightsScope, PostedCountry, PostedLevel, PostedPay, api } from "../../api";
import { useAsyncResource } from "../../hooks/useAsyncResource";
import { useSourceSwitch } from "../../context/SyncState";
import { fmtComp, fmtCompIn, companyName, BAND_LABEL } from "../../format";
import { country as countryName } from "../../copy/format";
import { DisclosureRatePanel } from "./DisclosurePanel";
import { PayBands } from "./PayBands";
import { exclusionNote } from "./charts/compBands";
import { pct } from "./charts/disclosure";
import { levelLabel } from "./charts/levelLabel";
import { postedCountry, postedLevel, postedLevels } from "./charts/postedPay";
import { InfoTip } from "../../ui/InfoTip";
import { Badge, Select } from "../../ui";
import { ResourceLoadState } from "../../ui/ResourceLoadState";
import { InsightHero } from "./InsightHero";
import {
  insightsCompensationPanelAboutPublishedSalaryBands,
  insightsCompensationPanelBandsFromEmployers,
  insightsCompensationPanelBaseOnlyLead,
  insightsCompensationPanelBaseSalaryQuotedFromThe,
  insightsCompensationPanelEstimatedBaseByLevel,
  insightsCompensationPanelEstimatedTotalCompensationIsImputed,
  insightsCompensationPanelGroupsOfRolesOrMore,
  insightsCompensationPanelHowCompensationIsEstimated,
  insightsCompensationPanelLoadFailed,
  insightsCompensationPanelLoading,
  insightsCompensationPanelMedianCompByLevel,
  insightsCompensationPanelMedianPayByDiscipline,
  insightsCompensationPanelPublishedBands,
  insightsCompensationPanelRoles,
  insightsCompensationPanelSpread,
  insightsCompensationPanelTopPayingCompanies,
  insightsPayBandsBandsFromEmployers,
  insightsPostedByLevel,
  insightsPostedChecked,
  insightsPostedCountry,
  insightsPostedEstimateUsOnly,
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
  insightsPostedOtherCurrency,
  insightsPostedShare,
  insightsPostedTooFew,
  insightsPostedTypically,
  insightsPostedYourLevel,
  insightsPostedYourPlace,
  insightsLevelsYourLevel,
} from "../../copy/gen/insights";
import { roleName } from "../../copy/vocab";

// One ranked "name | median-bar | value | roles" row, scaled against the group
// max. Every row says how many roles it rests on.
function CompBar({
  label,
  s,
  max,
  title,
}: {
  label: string;
  s: CompSummary;
  max: number;
  title?: string;
}) {
  const median = s.p50 ?? 0;
  return (
    <div className="bar-row comp-row" title={title}>
      <span>{label}</span>
      <div className="bar-track">
        <div className="bar-fill" style={{ width: `${(median / max) * 100}%` }} />
      </div>
      <span className="val">{fmtComp(median)}</span>
      <span className="comp-n">{roles(s.count)}</span>
    </div>
  );
}

const roles = (count: number) => insightsCompensationPanelRoles({ count });
const iqr = (s: CompSummary) =>
  insightsCompensationPanelSpread({ low: String(fmtComp(s.p25)), high: String(fmtComp(s.p75)), roles: roles(s.count) });
// The two lists in a pair show the same number of rows.
const PAIR_ROWS = 8;

/* Roles whose pay estimate is a base alone. No total exists for them, so they
   have their own panel and their own axis: a base drawn beside totals reads as
   a lower-paying role. The payload may omit the block, so it is read
   optionally. */
function BaseEstimatesPanel({ base }: { base: CompensationStats["base_estimates"] | undefined }) {
  if (!base?.overall) return null;
  const max = Math.max(1, ...base.by_level.map((l) => l.p50 ?? 0));
  const heading = insightsCompensationPanelEstimatedBaseByLevel();
  return (
    <section className="panel" aria-label={heading}>
      <span className="eyebrow">{insightsPostedEstimateUsOnly()}</span>
      <h3>{heading}</h3>
      <p className="hiring-note">{insightsCompensationPanelBaseOnlyLead({ count: base.coverage.with_base })}</p>
      {base.by_level.map((l) => (
        <CompBar key={l.level_band} label={BAND_LABEL[l.level_band] ?? l.level_band} s={l} max={max} title={iqr(l)} />
      ))}
      <p className="hiring-note">{insightsCompensationPanelGroupsOfRolesOrMore({ min_roles: base.min_roles })}</p>
    </section>
  );
}

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

/** The query keys only the Pay tab reads: the country and level it shows. */
export const PAY_PARAMS = ["country", "level"] as const;

export function CompensationPanel({
  scope,
  advanced = false,
}: {
  scope?: InsightsScope;
  /** The basic view keeps posted pay and the estimates by level, company and
   *  discipline; the advanced view adds every posted range, who states pay
   *  and the base-only estimates. */
  advanced?: boolean;
}) {
  // The roles open now. Pay over time waits for enough history to compare
  // like with like (docs/decisions/0004-insights-answers-a-question.md).
  const { data, error, retry, refresh } = useAsyncResource<CompensationStats>(
    () => api.compensation(scope), [scope], { keep: "stats/compensation" });
  // Pay statistics follow the source answering pay.
  useSourceSwitch(refresh);
  const [params, setParams] = useSearchParams();

  if (!data) return <ResourceLoadState error={error} loading={insightsCompensationPanelLoading()} failed={insightsCompensationPanelLoadFailed()} onRetry={retry} />;

  const posted = data.posted;
  const country = postedCountry(posted, params.get("country"));
  const levels = country ? postedLevels(country, posted.your_levels, params.get("level")) : [];
  const level = postedLevel(levels, posted.your_levels, params.get("level"));
  const choose = (key: "country" | "level") => (value: string) =>
    setParams((prev) => {
      const next = new URLSearchParams(prev);
      next.set(key, value);
      return next;
    }, { replace: true });

  const o = data.overall;
  const levelMax = Math.max(1, ...data.by_level.map((l) => l.p50 ?? 0));
  const companies = data.by_company.slice(0, PAIR_ROWS);
  const families = data.by_family.slice(0, PAIR_ROWS);
  const companyMax = Math.max(1, ...companies.map((c) => c.p50 ?? 0));
  const familyMax = Math.max(1, ...families.map((f) => f.p50 ?? 0));
  const atLeast = insightsCompensationPanelGroupsOfRolesOrMore({ min_roles: data.min_roles });
  // Under a country's heading, the roles left out are that country's; every
  // role in no one country, whatever else left it out, is no country's, so
  // each heading says it.
  const excluded = country ? { ...country.excluded, no_country: posted.excluded.without_country } : posted.excluded;
  const rangesExplanation = [
    insightsCompensationPanelBaseSalaryQuotedFromThe(),
    exclusionNote(excluded),
  ].filter(Boolean).join(" ");
  const estimate = <span className="eyebrow">{insightsPostedEstimateUsOnly()}</span>;

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
      {advanced && <DisclosureRatePanel rates={data.disclosure} initialGroup="level" />}

      {/* The estimate reads US pay only, so every panel built from it says so. */}
      {o && (
        <>
          <div className="panel">
            {estimate}
            <h3>
              {insightsCompensationPanelMedianCompByLevel()}
              <InfoTip label={insightsCompensationPanelHowCompensationIsEstimated()}>
                {insightsCompensationPanelEstimatedTotalCompensationIsImputed()}
              </InfoTip>
            </h3>
            {data.by_level.map((l) => (
              <CompBar
                key={l.level_band}
                label={BAND_LABEL[l.level_band] ?? l.level_band}
                s={l}
                max={levelMax}
                title={iqr(l)}
              />
            ))}
            <p className="hiring-note">{atLeast}</p>
          </div>

          <div className="demand-grid pay-pair">
            <div className="panel">
              {estimate}
              <h3>{insightsCompensationPanelTopPayingCompanies()}</h3>
              {companies.map((c) => (
                <CompBar key={c.company} label={companyName(c.company)} s={c} max={companyMax} title={iqr(c)} />
              ))}
              <p className="hiring-note">{atLeast}</p>
            </div>

            <div className="panel">
              {estimate}
              <h3>{insightsCompensationPanelMedianPayByDiscipline()}</h3>
              {families.map((f) => (
                <CompBar key={f.family ?? "none"} label={roleName(f.family)} s={f} max={familyMax} title={iqr(f)} />
              ))}
              <p className="hiring-note">{atLeast}</p>
            </div>
          </div>
        </>
      )}

      {/* With no total to show, the base estimates are the only estimate
          figures, so both views keep them then. */}
      {(advanced || !o) && <BaseEstimatesPanel base={data.base_estimates} />}
    </>
  );
}

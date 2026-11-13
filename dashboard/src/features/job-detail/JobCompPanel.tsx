/**
 * The compensation package for one role.
 *
 * Two encodings, kept strictly separate, because conflating them is how a dashboard
 * starts lying to you:
 *
 *   HUE     = what kind of money it is   -> base / bonus / equity
 *   TEXTURE = how sure we are of it      -> solid = the employer stated it,
 *                                           hatched = we estimated it
 *
 * The hues are the same three the company section already uses (`.split-bar`), so the
 * two surfaces speak one language.
 *
 * Nothing here decides what is stated vs estimated — `backend/tracker/analytics/comp_package.py`
 * does, and this component only renders its verdict. In particular an `unclear` basis
 * arrives with no components at all, and we must not invent a split to fill the bar.
 */
import { useMemo } from "react";
import { calendarDay } from "../../copy/format";

import type { CompComponent, Job, JobCompPackage } from "../../api";
import { BAND_LABEL, companyName, fmtComp } from "../../format";
import { fmtCompIn } from "../../money";
import { Icon } from "../../ui/Icon";
import { InfoTip } from "../../ui/InfoTip";
import { PayFloorLine } from "./PayFloorLine";
import {
  roleJobCompPanelAboutTheSplit,
  roleJobCompPanelBase,
  roleJobCompPanelBaseCappedAt,
  roleJobCompPanelBaseSalaryIsTheFixed,
  roleJobCompPanelAboutBaseSalary,
  roleJobCompPanelBaseStatedByTheEmployer,
  roleJobCompPanelBasisNotStated,
  roleJobCompPanelSplitNotReported,
  roleJobCompPanelBonus,
  roleJobCompPanelBonusIsALevelSet,
  roleJobCompPanelEmployeeSelectedMix,
  roleJobCompPanelGuaranteedCash,
  roleJobCompPanelEquity,
  roleJobCompPanelEquityFillsAPerLevel,
  roleJobCompPanelEquityIsADollarGrant,
  roleJobCompPanelEstimated,
  roleJobCompPanelEstimatedSplit,
  roleJobCompPanelEstimatedTotalComp,
  roleJobCompPanelEstimatedTotalPackage,
  roleJobCompPanelFromThePostingSPay,
  roleJobCompPanelHourlyRate,
  roleJobCompPanelHr,
  roleJobCompPanelMarketMedianAtThisLevel,
  roleJobCompPanelMeasuredSplit,
  roleJobCompPanelMo,
  roleJobCompPanelMonthlyRate,
  roleJobCompPanelNoAnnualBonus,
  roleJobCompPanelNoCompensationDataForThis,
  roleJobCompPanelNoMeasuredSplitForThis,
  roleJobCompPanelNoMeasuredSplitForThis2,
  roleJobCompPanelNotReadYet,
  roleJobCompPanelOfBaseStated,
  roleJobCompPanelEstimateOfTotal,
  roleJobCompPanelOurIndependentEstimateOfTotal,
  roleJobCompPanelPayUnknownWhy,
  roleJobCompPanelPerYearVestsOverTime,
  roleJobCompPanelPeriodUnclear,
  roleJobCompPanelPostedBandSitsWellAbove,
  roleJobCompPanelPostedBandSitsWellBelow,
  roleJobCompPanelRolebandSplitsUsPayOnly,
  roleJobCompPanelLevelNotStatedOrMapped,
  roleJobCompPanelSplitFromAnotherDiscipline,
  roleJobCompPanelStated,
  roleJobCompPanelStatedByTheEmployer,
  roleJobCompPanelStatesThisAsTotalAnnual,
  roleJobCompPanelTargetNotGuaranteed,
  roleJobCompPanelThePostedBandDoesNot,
  roleJobCompPanelThePostingGivesAMonthly,
  roleJobCompPanelThePostingGivesAnHourly,
  roleJobCompPanelThePostingSWordingAnd,
  roleJobCompPanelThePostingStatesThisFigure,
  roleJobCompPanelThePluginReportsNoSplit,
  roleJobCompPanelThePostingStatesTotalCompensation,
  roleJobCompPanelThisCompanySRealBase,
  roleJobCompPanelThisEmployerPublishesNoPay,
  roleJobCompPanelThisPackageIsTheMarket,
  roleJobCompPanelTotalCompensation,
  roleJobCompPanelVests,
  roleJobCompPanelWeHaveNotCheckedThis,
  roleJobCompPanelYouChooseTheCashStock,
  roleJobCompPanelYr,
  roleJobCompPanelEstimatedBase,
  roleJobCompPanelBaseOnly,
  roleJobCompPanelSplitFromPlugin,
  roleJobCompPanelSplitFromRoleband,
} from "../../copy/gen/role";
import { sharedPayNotCoveredHint } from "../../copy/gen/shared";
import { LEVEL_NOT_MAPPED, LEVEL_NOT_STATED } from "../../copy/vocabulary";
import { Msg } from "../../ui/Msg";

const KIND_LABEL: Record<CompComponent["kind"], string> = {
  get base() { return roleJobCompPanelBase(); },
  get bonus() { return roleJobCompPanelBonus(); },
  get equity() { return roleJobCompPanelEquity(); },
};

const PROVENANCE_LABEL: Record<CompComponent["provenance"], string> = {
  get stated() { return roleJobCompPanelStated(); },
  get estimated() { return roleJobCompPanelEstimated(); },
};

const KIND_HINT: Record<CompComponent["kind"], string> = {
  get base() { return roleJobCompPanelGuaranteedCash(); },
  get bonus() { return roleJobCompPanelTargetNotGuaranteed(); },
  get equity() { return roleJobCompPanelPerYearVestsOverTime(); },
};

// How the base/bonus/equity ratios were obtained. A package scaled from a different job
// family's numbers is NOT a measured split, and the user is entitled to know.
const SPLIT_LABEL: Record<string, string> = {
  get measured() { return roleJobCompPanelMeasuredSplit(); },
  get cross_family() { return roleJobCompPanelSplitFromAnotherDiscipline(); },
  get heuristic() { return roleJobCompPanelEstimatedSplit(); },
};
const SPLIT_TITLE: Record<string, string> = {
  get measured() { return roleJobCompPanelThisCompanySRealBase(); },
  get cross_family() { return roleJobCompPanelNoMeasuredSplitForThis(); },
  get heuristic() { return roleJobCompPanelNoMeasuredSplitForThis2(); },
};

// A posted band that disagrees with what the level is measured to pay is evidence about
// the LEVEL, not about the employer's generosity — so the sentence names the suspicion
// rather than the number. Nothing here decides the verdict; comp_package.py does.
const RECONCILE_NOTE: Record<string, (band: string) => string> = {
  stated_above_measured: (band) =>
    roleJobCompPanelPostedBandSitsWellAbove({ band: String(band) }),
  stated_below_measured: (band) =>
    roleJobCompPanelPostedBandSitsWellBelow({ band: String(band) }),
};

function mid(c: { low: number; high: number }): number {
  return (c.low + c.high) / 2;
}

/** "$240K–$334K", or a single figure when the band is a point, in the
    currency the band was stated in. */
function span(c: { low: number; high: number }, currency = "USD"): string {
  return c.low === c.high ? fmtCompIn(c.low, currency) : `${fmtCompIn(c.low, currency)}–${fmtCompIn(c.high, currency)}`;
}

function StatedTag({ provenance }: { provenance: CompComponent["provenance"] }) {
  const stated = provenance === "stated";
  return (
    <span className={`pkg-tag ${stated ? "pkg-tag-stated" : "pkg-tag-est"}`}>
      {PROVENANCE_LABEL[provenance]}
    </span>
  );
}

// How the company constructs the offer, as one sentence of verified facts. Says
// nothing for an unverified company: an absent line is "unknown", and a default
// ("vests over 4 years") would be the guess the policy table exists to prevent.
function policyLine(policy: JobCompPackage["policy"]): string | null {
  if (!policy || !policy.verified) return null;
  const parts: string[] = [];
  if (policy.equity_rule === "employee_election") parts.push(roleJobCompPanelYouChooseTheCashStock());
  else if (policy.equity_rule === "tc_target_minus_base")
    parts.push(roleJobCompPanelEquityFillsAPerLevel());
  else if (policy.equity_rule === "dollar_grant_by_level")
    parts.push(roleJobCompPanelEquityIsADollarGrant());
  if (policy.vesting) {
    parts.push(
      roleJobCompPanelVests({ choice: (policy.sign_on_bridges_vesting) ? "yes" : "no", vesting: String(policy.vesting) }),
    );
  }
  if (policy.bonus_rule === "none") parts.push(roleJobCompPanelNoAnnualBonus());
  else if (policy.bonus_rule === "pct_of_base") parts.push(roleJobCompPanelBonusIsALevelSet());
  if (policy.base_cap_usd) parts.push(roleJobCompPanelBaseCappedAt({ base_cap_usd: String(fmtComp(policy.base_cap_usd)) }));
  return parts.length ? parts.join(" · ") + "." : null;
}

/** The unit after an employer's own figure, by the period the server serves. */
const PERIOD_UNIT: Record<string, string> = { get year() { return (" " + roleJobCompPanelYr()); }, get month() { return (" " + roleJobCompPanelMo()); }, get hour() { return (" " + roleJobCompPanelHr()); } };

/** Why an employer's figure is not broken into base, bonus and equity. A
    reason that names the employer reads it from the posting: the atlas, not
    this file, says which companies let employees pick their mix (only
    `companies.json` may name a company here). */
const NO_SPLIT: Record<
  NonNullable<JobCompPackage["no_split_reason"]>,
  { tag: string | ((job: Job) => string); why: string | ((company: string, plugin: string) => string) }
> = {
  hourly: {
    get tag() { return roleJobCompPanelHourlyRate(); },
    get why() { return roleJobCompPanelThePostingGivesAnHourly(); },
  },
  monthly: {
    get tag() { return roleJobCompPanelMonthlyRate(); },
    get why() { return roleJobCompPanelThePostingGivesAMonthly(); },
  },
  period_unclear: {
    get tag() { return roleJobCompPanelPeriodUnclear(); },
    get why() { return roleJobCompPanelThePostingSWordingAnd(); },
  },
  employee_election: {
    get tag() { return roleJobCompPanelEmployeeSelectedMix(); },
    why: (company) =>
      roleJobCompPanelStatesThisAsTotalAnnual({ company: String(company) }),
  },
  total_compensation: {
    get tag() { return roleJobCompPanelTotalCompensation(); },
    get why() { return roleJobCompPanelThePostingStatesTotalCompensation(); },
  },
  basis_unclear: {
    get tag() { return roleJobCompPanelBasisNotStated(); },
    get why() { return roleJobCompPanelThePostingStatesThisFigure(); },
  },
  // Not the employer's doing: the plugin answering pay states no split here,
  // and RoleBand's own is never put under its figure.
  plugin_without_split: {
    get tag() { return roleJobCompPanelSplitNotReported(); },
    get why() { return roleJobCompPanelThePluginReportsNoSplit(); },
  },
  // The plugin answering pay has not read this company: it gave nothing to
  // split, and RoleBand's own is off while it answers.
  plugin_not_covered: {
    get tag() { return roleJobCompPanelNotReadYet(); },
    why: (_company, plugin) => sharedPayNotCoveredHint({ plugin }),
  },
  // RoleBand answers pay, and its split is measured on US pay only.
  not_us_pay: {
    get tag() { return roleJobCompPanelSplitNotReported(); },
    get why() { return roleJobCompPanelRolebandSplitsUsPayOnly(); },
  },
  // The level is a guess kept for sorting: the posted pay stands, and nothing
  // is built on that level. The tag is the one the job card shows.
  level_unplaced: {
    tag: (job) => (job.level_basis === "none" ? LEVEL_NOT_STATED() : LEVEL_NOT_MAPPED()),
    get why() { return roleJobCompPanelLevelNotStatedOrMapped(); },
  },
};

function noSplitTag(reason: NonNullable<JobCompPackage["no_split_reason"]>, job: Job): string {
  const tag = NO_SPLIT[reason].tag;
  return typeof tag === "function" ? tag(job) : tag;
}

function noSplitWhy(reason: NonNullable<JobCompPackage["no_split_reason"]>, job: Job): string {
  const why = NO_SPLIT[reason].why;
  return typeof why === "function" ? why(companyName(job.company), pluginName(job)) : why;
}

/** The plugin answering this job's pay, by name. */
const pluginName = (job: Job): string => job.pay_source?.plugin_name ?? job.pay_source?.plugin ?? "";

/** A plugin answers pay and has not read this job's company. */
const notCovered = (job: Job): boolean => !!job.pay_source?.plugin && !job.pay_source.covered;

/** Who supplied the per-level split the segments are scaled by, and when:
 *  the plugin answering pay by its name, anything else RoleBand's own data. */
function splitFrom(job: Job, pkg: JobCompPackage): string | null {
  if (!pkg.split_provider) return null;
  const dated = pkg.split_as_of ? "yes" : "no";
  const date = pkg.split_as_of ? calendarDay(pkg.split_as_of) : "";
  return pkg.split_provider === job.pay_source?.plugin
    ? roleJobCompPanelSplitFromPlugin({ choice: dated, plugin: pluginName(job), date })
    : roleJobCompPanelSplitFromRoleband({ choice: dated, date });
}

/** Each component's share of the bar, by the MIDPOINT of its range, so a wide
 *  band does not make a segment look bigger than it is. */
function segmentWidths(pkg: JobCompPackage | null | undefined): number[] {
  const comps = pkg?.components ?? [];
  const total = comps.reduce((sum, c) => sum + mid(c), 0);
  if (total <= 0) return comps.map(() => 0);
  return comps.map((c) => (mid(c) / total) * 100);
}

/** The employer's own figure is a yearly base salary. */
const statedIsYearlyBase = (pkg: JobCompPackage): boolean =>
  !!pkg.stated && pkg.pay_period === "year" && pkg.basis === "base";

/** Only the base is estimated: the package's one component is the headline
 *  figure again, so a bar, a legend or a split badge would only repeat it. */
const baseOnly = (pkg: JobCompPackage): boolean => !!pkg.base_estimate && !pkg.total;

/** The panel's headline: the figure, the label that describes it, its unit and
 *  its currency. One reading for the panel and for its small copy. Null when
 *  the package holds no figure at all. */
function headlineOf(pkg: JobCompPackage) {
  const { total, stated, estimate } = pkg;
  const statedUnit = PERIOD_UNIT[pkg.pay_period ?? ""] ?? "";
  const cur = pkg.currency ?? "USD";
  // The headline label must describe the number underneath it. When we cannot build a
  // package (an unclear basis), the big figure falls back to our ESTIMATE — and calling
  // that "stated by the employer" would be the exact lie this panel exists to prevent.
  // The employer's own figure is shown separately, in its own box.
  let headline: { low: number; high: number };
  let headlineLabel: string;
  if (total) {
    headline = total;
    headlineLabel = roleJobCompPanelEstimatedTotalPackage({ choice: (total.provenance === "stated") ? "yes" : "no" });
  } else if (estimate?.median != null) {
    headline = { low: estimate.low ?? estimate.median, high: estimate.high ?? estimate.median };
    headlineLabel = roleJobCompPanelEstimatedTotalComp();
  } else if (pkg.base_estimate) {
    // Only the base is estimated: say so, and never call it a total.
    const base = pkg.base_estimate;
    headline = { low: base.low ?? base.median, high: base.high ?? base.median };
    headlineLabel = roleJobCompPanelEstimatedBase();
  } else if (stated) {
    headline = stated;
    // The figure is the whole of what is known, so its heading says what kind
    // of pay it is; no line under it has to.
    headlineLabel = statedIsYearlyBase(pkg) ? roleJobCompPanelBaseStatedByTheEmployer() : roleJobCompPanelStatedByTheEmployer();
  } else {
    return null;
  }

  // A total or our estimate is always yearly; only the employer's own figure
  // carries the posting's unit, so a yearly estimate never reads "/ hr".
  const headlineUnit = headline === stated ? statedUnit : (" " + roleJobCompPanelYr());

  const headlineCurrency = headline === stated || headline === total ? cur : "USD";

  return { headline, headlineLabel, headlineUnit, headlineCurrency };
}

/**
 * The pay panel's small copy, for the side column once the panel has scrolled
 * away: the same headline and figure, the same bar, and the components on one
 * line. It is the panel again, smaller, so it says nothing the panel does not
 * and stands for nothing when the panel has no figure.
 */
export function JobCompDock({ job }: { job: Job }) {
  const pkg = job.comp_package;
  if (!pkg) return null;
  const shown = headlineOf(pkg);
  if (!shown) return null;
  const { headline, headlineLabel, headlineUnit, headlineCurrency } = shown;
  const cur = pkg.currency ?? "USD";
  const widths = segmentWidths(pkg);
  return (
    <div className="pkg-mini">
      <div className="pkg-mini-eyebrow">{headlineLabel}</div>
      <div className="big">
        {span(headline, headlineCurrency)}
        {headlineUnit && <span className="pkg-per">{headlineUnit}</span>}
      </div>
      {pkg.components.length > 0 && !baseOnly(pkg) && (
        <>
          <div className="pkg-bar">
            {pkg.components.map((c, i) => (
              <span
                key={c.kind}
                className={`pkg-seg pkg-${c.kind}${c.provenance === "estimated" ? " pkg-est" : ""}`}
                style={{ width: `${widths[i]}%` }}
              />
            ))}
          </div>
          <div className="pkg-mini-parts">
            {pkg.components.map((c) => (
              <span key={c.kind}>{KIND_LABEL[c.kind]} <b>{span(c, cur)}</b></span>
            ))}
          </div>
        </>
      )}
    </div>
  );
}

/** Why the panel has no figure, in one sentence: the plugin answering pay has
 *  not read the company, the posting has not been read for pay yet, or the
 *  posting gives none and nothing was estimated. */
function unknownWhy(job: Job, pkg: JobCompPackage | null | undefined): string {
  if (notCovered(job)) return sharedPayNotCoveredHint({ plugin: pluginName(job) });
  if (!pkg) return roleJobCompPanelNoCompensationDataForThis();
  if (pkg.state === "unchecked") return roleJobCompPanelWeHaveNotCheckedThis();
  return roleJobCompPanelPayUnknownWhy();
}

/** The panel with no figure to show: the heading it always carries and the
 *  one reason, as a short card. Nothing else belongs here: a stand-in word
 *  in the figure's place, a bar, a pay policy or a note about estimates
 *  would describe a figure that is not there. */
function PayUnknown({ why }: { why: string }) {
  return (
    <div className="comp-panel pkg-panel pkg-unknown" data-testid="pkg-unknown">
      <div className="pkg-eyebrow">{roleJobCompPanelEstimatedTotalComp()}</div>
      <p className="pkg-unknown-why">{why}</p>
    </div>
  );
}

export default function JobCompPanel({ job }: { job: Job }) {
  const pkg: JobCompPackage | null | undefined = job.comp_package;

  const widths = useMemo(() => segmentWidths(pkg), [pkg]);

  const shown = pkg ? headlineOf(pkg) : null;
  if (!pkg || !shown) return <PayUnknown why={unknownWhy(job, pkg)} />;

  const { components, total, stated, estimate, state } = pkg;
  // A plugin answers pay: its figure is never called "ours", and its
  // provider's English provenance (a raw family code among it) is not shown.
  const byPlugin = !!job.pay_source?.plugin;
  const statedWidth = widths
    .filter((_w, i) => components[i].provenance === "stated")
    .reduce((a, b) => a + b, 0);
  // The unit the EMPLOYER'S figure is in. The server checks the stored
  // period against the amount's size, so "unclear" means the posting's own word and
  // the size disagree: that figure is shown with no unit at all, never a guessed one.
  const statedUnit = PERIOD_UNIT[pkg.pay_period ?? ""] ?? "";
  // The employer's band, and everything the package builds from it, is in the
  // posting's currency; only our estimate is dollars.
  const cur = pkg.currency ?? "USD";

  // The posted band versus what this level is measured to pay. A `measured` badge over a
  // level we have reason to doubt over-claims, so the badge is marked provisional — but
  // `split_source` itself stays exactly what it is: where the ratios came from is a fact,
  // and overwriting it with a confidence signal would corrupt the one honest field.
  const verdict = pkg.reconciliation?.verdict;
  const suspectLevel = verdict === "stated_above_measured" || verdict === "stated_below_measured";
  // The level's name as the catalog writes it: a translation, not this code, decides its case.
  const reconcileNote = verdict
    ? RECONCILE_NOTE[verdict]?.(BAND_LABEL[job.level_band] ?? job.level_band) ?? null
    : null;

  const { headline, headlineLabel, headlineUnit, headlineCurrency } = shown;
  // The employer's figure is the headline itself: nothing below repeats it.
  // By the figure, not the object: a stated total is the employer's band and
  // the package carries it twice, as `total` and as `stated`.
  const statedLeads =
    !!stated && headline.low === stated.low && headline.high === stated.high;
  const onlyBase = baseOnly(pkg);

  return (
    <div className="comp-panel pkg-panel">
      <div className="pkg-head">
        <div>
          <div className="pkg-eyebrow">{headlineLabel}</div>
          <div className="big">
            {span(headline, headlineCurrency)}
            {headlineUnit && <span className="pkg-per">{headlineUnit}</span>}
          </div>
        </div>
        {pkg.split_source && components.length > 0 && !onlyBase && (
          <span className="pkg-split">
            <span className={`split-src split-src-${pkg.split_source}${suspectLevel ? " split-src-suspect" : ""}`}>
              {SPLIT_LABEL[pkg.split_source]}
            </span>
            <InfoTip label={roleJobCompPanelAboutTheSplit()}>
              {suspectLevel
                ? roleJobCompPanelThePostedBandDoesNot({ sPLIT_TITLE: String(SPLIT_TITLE[pkg.split_source]) })
                : SPLIT_TITLE[pkg.split_source]}
            </InfoTip>
          </span>
        )}
        {pkg.split_source && components.length > 0 && !onlyBase && splitFrom(job, pkg) && (
          <p className="pkg-note" data-testid="comp-split-from">{splitFrom(job, pkg)}</p>
        )}
      </div>

      {/* ONE headline, and the market median as a reading on it rather than a rival to
          it. Two totals printed as peers make the reader arbitrate between them; the
          disagreement is the signal, so we state it. */}
      {estimate?.median != null && total && (
        <div
          className={`pkg-market${pkg.market_gap?.verdict === "diverges" ? " pkg-market-warn" : ""}`}
          data-testid="pkg-market"
        >
          <div className="pkg-market-n">
            <span>{roleJobCompPanelMarketMedianAtThisLevel()}</span>
            <b>{fmtComp(estimate.median)}</b>
          </div>
          {pkg.market_gap?.verdict === "diverges" && (
            <div className="pkg-market-warn-note">
              <Icon name="alert" size={13} /> <Msg of={roleJobCompPanelThisPackageIsTheMarket} elems={{ toFixed: pkg.market_gap.ratio.toFixed(2) }} />
            </div>
          )}
        </div>
      )}

      {reconcileNote && (
        <div className="pkg-caution" data-testid="pkg-reconciliation">
          <Icon name="alert" size={13} /> {reconcileNote}
        </div>
      )}

      {/* Which part of a larger figure is certain, in the ink the card gives
          the employer's own numbers. With the pay floor under it, the two
          rows hold the headline apart from the bar. The help mark says what
          base salary is, for a reader the card's own words assume too much
          of. */}
      {statedIsYearlyBase(pkg) && !statedLeads && (
        <p className="pkg-stated" data-testid="pkg-stated-base">
          <Icon name="checkCircle" size={14} />
          <b>{span(stated!, cur)}</b>
          <span>{roleJobCompPanelBase()}</span>
          <InfoTip label={roleJobCompPanelAboutBaseSalary()}>
            {roleJobCompPanelBaseSalaryIsTheFixed()}
          </InfoTip>
        </p>
      )}

      <PayFloorLine check={job.pay_floor_check} />

      {onlyBase && (
        <div className="pkg-note" data-testid="comp-base-only">
          {state === "none_stated" && <Icon name="xCircle" size={14} />}
          {roleJobCompPanelBaseOnly({ choice: state === "none_stated" ? "none" : "other" })}
        </div>
      )}
      {state === "none_stated" && !onlyBase && (
        <div className="pkg-note">
          <Icon name="xCircle" size={14} /> {roleJobCompPanelThisEmployerPublishesNoPay()}
        </div>
      )}
      {state === "unchecked" && (
        <div className="pkg-note">
          <Icon name="clock" size={14} /> {roleJobCompPanelWeHaveNotCheckedThis()}
        </div>
      )}

      {components.length > 0 && !onlyBase && (
        <>
          <div className="pkg-bar" role="img" aria-label={components
            .map((c) => `${KIND_LABEL[c.kind]} ${span(c, cur)} ${PROVENANCE_LABEL[c.provenance]}`)
            .join("; ")}
          >
            {components.map((c, i) => (
              <span
                key={c.kind}
                className={`pkg-seg pkg-${c.kind}${c.provenance === "estimated" ? " pkg-est" : ""}`}
                style={{ width: `${widths[i]}%` }}
                title={`${KIND_LABEL[c.kind]} ${span(c, cur)}, ${PROVENANCE_LABEL[c.provenance]}`}
              />
            ))}
          </div>

          {statedWidth > 0 && statedWidth < 100 && (
            <div className="pkg-bracket" aria-hidden="true">
              <span className="pkg-br-stated" style={{ width: `${statedWidth}%` }}>
                {roleJobCompPanelStated()}
              </span>
              <span className="pkg-br-est" style={{ width: `${100 - statedWidth}%` }}>
                {roleJobCompPanelEstimated()}
              </span>
            </div>
          )}

          <div className="pkg-legend">
            {components.map((c) => (
              <div className="pkg-leg" key={c.kind}>
                <i className={`pkg-sw pkg-${c.kind}${c.provenance === "estimated" ? " pkg-est" : ""}`} />
                <div>
                  <div className="pkg-leg-top">
                    {KIND_LABEL[c.kind]} <StatedTag provenance={c.provenance} />
                  </div>
                  <div className="pkg-leg-n">{span(c, cur)}</div>
                  <div className="pkg-leg-hint">
                    {c.kind === "bonus" && pkg.bonus_pct
                      ? roleJobCompPanelOfBaseStated({ round: Math.round(pkg.bonus_pct * 100) })
                      : KIND_HINT[c.kind]}
                  </div>
                </div>
              </div>
            ))}
          </div>
        </>
      )}

      {/* No bar, and no employer's figure apart from the headline: a plugin's
          estimate with no split of its own, or the employer's figure standing
          as the headline. This says why there is no bar. */}
      {pkg.no_split_reason && (!stated || statedLeads) && (
        <p className="pkg-note" data-testid="pkg-no-split">
          <span className="pkg-tag pkg-tag-warn">{noSplitTag(pkg.no_split_reason, job)}</span>{" "}
          {noSplitWhy(pkg.no_split_reason, job)}
        </p>
      )}

      {/* An employer figure we deliberately refuse to break down. */}
      {pkg.no_split_reason && stated && !statedLeads && (
        <div className="pkg-unclear">
          <div className="pkg-unclear-n">
            {span(stated, cur)}
            {statedUnit}
            <span className="pkg-tag pkg-tag-warn">{noSplitTag(pkg.no_split_reason, job)}</span>
          </div>
          <p>{noSplitWhy(pkg.no_split_reason, job)}</p>
          {estimate?.median != null && (
            <div className="pkg-vs">
              <Msg of={byPlugin ? roleJobCompPanelEstimateOfTotal : roleJobCompPanelOurIndependentEstimateOfTotal}
                   elems={{ range: <b>{fmtComp(estimate.low)}–{fmtComp(estimate.high)}</b> }} />
            </div>
          )}
        </div>
      )}

      {/* A band read from the posting's own pay field is in no sentence of
          the description below: say where it came from. */}
      {"disclosed_comp" in job && job.disclosed_comp?.from_pay_field && (
        <div className="pkg-foot" data-testid="pkg-from-field">{roleJobCompPanelFromThePostingSPay()}</div>
      )}

      {policyLine(pkg.policy) && (
        <div className="pkg-foot" data-testid="pkg-policy">
          {policyLine(pkg.policy)}
        </div>
      )}
    </div>
  );
}

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
import { BAND_LABEL, companyName } from "../../format";
import { fmtCompIn } from "../../money";
import { Icon } from "../../ui/Icon";
import { InfoTip } from "../../ui/InfoTip";
import {
  roleJobCompPanelAboutTheSplit,
  roleJobCompPanelBase,
  roleJobCompPanelBaseSalaryIsTheFixed,
  roleJobCompPanelAboutBaseSalary,
  roleJobCompPanelBaseStatedByTheEmployer,
  roleJobCompPanelBonus,
  roleJobCompPanelGuaranteedCash,
  roleJobCompPanelEquity,
  roleJobCompPanelEstimated,
  roleJobCompPanelEstimatedSplit,
  roleJobCompPanelEstimatedTotalComp,
  roleJobCompPanelEstimatedTotalPackage,
  roleJobCompPanelFromThePostingSPay,
  roleJobCompPanelHr,
  roleJobCompPanelMeasuredSplit,
  roleJobCompPanelMo,
  roleJobCompPanelNoMeasuredSplitForThis,
  roleJobCompPanelNoMeasuredSplitForThis2,
  roleJobCompPanelOfBaseStated,
  roleJobCompPanelOnTargetEarnings,
  roleJobCompPanelPerYearVestsOverTime,
  roleJobCompPanelPostedAs,
  roleJobCompPanelPostedBandSitsWellAbove,
  roleJobCompPanelPostedBandSitsWellBelow,
  roleJobCompPanelSplitFromAnotherDiscipline,
  roleJobCompPanelStated,
  roleJobCompPanelStatedByTheEmployer,
  roleJobCompPanelStatesThisAsTotalAnnual,
  roleJobCompPanelTargetNotGuaranteed,
  roleJobCompPanelThePostedBandDoesNot,
  roleJobCompPanelThePostingSWordingAnd,
  roleJobCompPanelThePostingStatesThisFigure,
  roleJobCompPanelThisCompanySRealBase,
  roleJobCompPanelYr,
  roleJobCompPanelEstimatedBase,
  roleJobCompPanelBaseOnly,
  roleJobCompPanelBaseFromPostedRate,
  roleJobCompPanelSplitFromPlugin,
  roleJobCompPanelSplitFromRoleband,
} from "../../copy/gen/role";
import { sharedPayNotCoveredHint } from "../../copy/gen/shared";

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

/** The unit after an employer's own figure, by the period the server serves. */
const PERIOD_UNIT: Record<string, string> = { get year() { return (" " + roleJobCompPanelYr()); }, get month() { return (" " + roleJobCompPanelMo()); }, get hour() { return (" " + roleJobCompPanelHr()); } };

type NoSplitReason = NonNullable<JobCompPackage["no_split_reason"]>;

/** Why an employer's figure is not broken into base, bonus and equity, in one
    sentence about the posting or the employer. A reason that names the
    employer reads it from the posting: the atlas, not this file, says which
    companies let employees pick their mix (only `companies.json` may name a
    company here).

    A reason with no entry says nothing: the headline already says it (an
    hourly or monthly rate, a stated total), or it is about what RoleBand does
    not compute (a level it cannot place, pay outside the US, a plugin with no
    split), which describes the app, not the job. */
const NO_SPLIT: Partial<Record<NoSplitReason, string | ((company: string, plugin: string) => string)>> = {
  get period_unclear() { return roleJobCompPanelThePostingSWordingAnd(); },
  employee_election: (company) => roleJobCompPanelStatesThisAsTotalAnnual({ company: String(company) }),
  get basis_unclear() { return roleJobCompPanelThePostingStatesThisFigure(); },
  // The plugin the person chose to answer pay has not read this company yet.
  plugin_not_covered: (_company, plugin) => sharedPayNotCoveredHint({ plugin }),
};

/** The sentence that says why the package has no bar, or null. */
function noSplitNote(pkg: JobCompPackage, job: Job): string | null {
  const why = pkg.no_split_reason ? NO_SPLIT[pkg.no_split_reason] : undefined;
  if (why === undefined) return null;
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

/** The panel's headline: the figure, the label that describes it, its unit,
 *  its currency, and whether it is the employer's own figure. One reading for
 *  the panel and for its small copy. Null when the package holds no figure.
 *
 *  The employer's figure leads whenever the posting states one: a total built
 *  on it, the full-time year of its hourly or monthly rate, or the figure as
 *  posted. Our estimate is the headline only where the posting states nothing,
 *  so it never sits above a figure the employer gave. */
function headlineOf(pkg: JobCompPackage) {
  const { total, stated, estimate } = pkg;
  const cur = pkg.currency ?? "USD";
  const yearly = " " + roleJobCompPanelYr();
  if (total) {
    const posted = total.provenance === "stated";
    return {
      headline: total,
      headlineLabel: posted && pkg.on_target_earnings
        ? roleJobCompPanelOnTargetEarnings()
        : roleJobCompPanelEstimatedTotalPackage({ choice: posted ? "yes" : "no" }),
      headlineUnit: yearly,
      headlineCurrency: cur,
      fromStated: posted,
    };
  }
  if (pkg.yearly_base) {
    // A rate is pay for the time worked: its year is base salary, never a total.
    return {
      headline: pkg.yearly_base,
      headlineLabel: roleJobCompPanelBaseFromPostedRate(),
      headlineUnit: yearly,
      headlineCurrency: cur,
      fromStated: true,
    };
  }
  if (stated) {
    // The figure is the whole of what is known, so its heading says what kind
    // of pay it is; no line under it has to. An unclear period has no unit,
    // never a guessed one.
    return {
      headline: stated,
      headlineLabel: statedIsYearlyBase(pkg) ? roleJobCompPanelBaseStatedByTheEmployer() : roleJobCompPanelStatedByTheEmployer(),
      headlineUnit: PERIOD_UNIT[pkg.pay_period ?? ""] ?? "",
      headlineCurrency: cur,
      fromStated: true,
    };
  }
  // Our figures are yearly and in dollars.
  if (estimate?.median != null) {
    return {
      headline: { low: estimate.low ?? estimate.median, high: estimate.high ?? estimate.median },
      headlineLabel: roleJobCompPanelEstimatedTotalComp(),
      headlineUnit: yearly,
      headlineCurrency: "USD",
      fromStated: false,
    };
  }
  if (pkg.base_estimate) {
    // Only the base is estimated: say so, and never call it a total.
    const base = pkg.base_estimate;
    return {
      headline: { low: base.low ?? base.median, high: base.high ?? base.median },
      headlineLabel: roleJobCompPanelEstimatedBase(),
      headlineUnit: yearly,
      headlineCurrency: "USD",
      fromStated: false,
    };
  }
  return null;
}

/** The posting's own hourly or monthly rate, under the full-time year the
 *  headline shows for it. */
function postedRate(pkg: JobCompPackage): string | null {
  if (!pkg.yearly_base || !pkg.stated) return null;
  const unit = PERIOD_UNIT[pkg.pay_period ?? ""] ?? "";
  return roleJobCompPanelPostedAs({
    choice: pkg.pay_period === "hour" ? "hour" : "other",
    rate: `${span(pkg.stated, pkg.currency ?? "USD")}${unit}`,
  });
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

/** The one line the panel keeps when it has no figure, or null for no panel:
 *  the plugin the person chose has not read the company. Otherwise there is no
 *  panel. Saying the posting states no pay would turn a figure the reader
 *  missed into a claim about the employer, and the person reads the posting
 *  itself below. */
function unknownWhy(job: Job): string | null {
  return notCovered(job) ? sharedPayNotCoveredHint({ plugin: pluginName(job) }) : null;
}

/** The panel with no figure to show: the one line, and nothing else. A
 *  heading would name a figure that is not there, and so would a stand-in
 *  word in its place, a bar or a pay policy. */
function PayUnknown({ why }: { why: string }) {
  return (
    <div className="comp-panel pkg-panel pkg-unknown" data-testid="pkg-unknown">
      <p className="pkg-unknown-why">{why}</p>
    </div>
  );
}

export default function JobCompPanel({ job }: { job: Job }) {
  const pkg: JobCompPackage | null | undefined = job.comp_package;

  const widths = useMemo(() => segmentWidths(pkg), [pkg]);

  const shown = pkg ? headlineOf(pkg) : null;
  if (!pkg || !shown) {
    const why = unknownWhy(job);
    return why ? <PayUnknown why={why} /> : null;
  }

  const { components, stated } = pkg;
  const statedWidth = widths
    .filter((_w, i) => components[i].provenance === "stated")
    .reduce((a, b) => a + b, 0);
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

  const { headline, headlineLabel, headlineUnit, headlineCurrency, fromStated } = shown;
  const onlyBase = baseOnly(pkg);
  const rate = postedRate(pkg);
  const note = noSplitNote(pkg, job);

  return (
    <div className="comp-panel pkg-panel">
      <div className="pkg-head">
        <div>
          <div className="pkg-eyebrow">{headlineLabel}</div>
          <div className="big">
            {span(headline, headlineCurrency)}
            {headlineUnit && <span className="pkg-per">{headlineUnit}</span>}
          </div>
          {rate && <p className="pkg-posted-rate" data-testid="pkg-posted-rate">{rate}</p>}
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

      {/* Which part of a larger figure is certain, in the ink the card gives
          the employer's own numbers, read straight under the headline it
          belongs to. The help mark says what base salary is, for a reader
          the card's own words assume too much of. */}
      {statedIsYearlyBase(pkg) && !fromStated && (
        <p className="pkg-stated" data-testid="pkg-stated-base">
          <Icon name="checkCircle" size={14} />
          <b>{span(stated!, cur)}</b>
          <span>{roleJobCompPanelBase()}</span>
          <InfoTip label={roleJobCompPanelAboutBaseSalary()}>
            {roleJobCompPanelBaseSalaryIsTheFixed()}
          </InfoTip>
        </p>
      )}

      {/* No line says the posting states no pay: "estimated" on the headline
          and on every part already says the figure is ours, and the claim
          would be false whenever the reader missed a figure. */}
      {onlyBase && (
        <div className="pkg-note" data-testid="comp-base-only">
          {roleJobCompPanelBaseOnly()}
        </div>
      )}

      {reconcileNote && (
        <div className="pkg-caution" data-testid="pkg-reconciliation">
          <Icon name="alert" size={13} /> {reconcileNote}
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

      {/* No bar: why, unless the headline already says it. */}
      {note && (
        <p className="pkg-note" data-testid="pkg-no-split">{note}</p>
      )}

      {/* A band read from the posting's own pay field is in no sentence of
          the description below: say where it came from. */}
      {"disclosed_comp" in job && job.disclosed_comp?.from_pay_field && (
        <div className="pkg-foot" data-testid="pkg-from-field">{roleJobCompPanelFromThePostingSPay()}</div>
      )}
    </div>
  );
}

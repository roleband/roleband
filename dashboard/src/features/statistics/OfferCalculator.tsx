import { forwardRef, useEffect, useId, useRef, useState, type FormEvent, type ReactNode } from "react";
import { Link } from "react-router-dom";
import type { OfferDraft, OfferTerms, OfferTermsCompany } from "../../api";
import { calendarDay, compare, list, money, number, numberInput, parseNumber } from "../../copy/format";
import { companyName, fmtComp } from "../../format";
import { Abbr } from "../../ui/Abbr";
import { Badge } from "../../ui/Badge";
import { Button } from "../../ui/Button";
import { FilterChip } from "../../ui/FilterChip";
import { Msg } from "../../ui/Msg";
import { Segmented } from "../../ui/Segmented";
import { Select } from "../../ui/Select";
import {
  insightsOfferAllCompanies,
  insightsOfferAnotherCompany,
  insightsOfferBack,
  insightsOfferBonusChoice,
  insightsOfferBonusOther,
  insightsOfferBonusRule,
  insightsOfferCancel,
  insightsOfferChart,
  insightsOfferChipAnother,
  insightsOfferChipBase,
  insightsOfferChipBonus,
  insightsOfferChipEdit,
  insightsOfferChipPrice,
  insightsOfferChipSignOn,
  insightsOfferChipStock,
  insightsOfferChipStrike,
  insightsOfferChipValuation,
  insightsOfferChipVesting,
  insightsOfferClear,
  insightsOfferContinue,
  insightsOfferDone,
  insightsOfferDontKnow,
  insightsOfferDrop,
  insightsOfferEntered,
  insightsOfferEquityType,
  insightsOfferFinishedTitle,
  insightsOfferFourYears,
  insightsOfferGrantUnit,
  insightsOfferGrantUnitOption,
  insightsOfferLater,
  insightsOfferListed,
  insightsOfferListedLabel,
  insightsOfferMissing,
  insightsOfferMove,
  insightsOfferMoveAria,
  insightsOfferNeed,
  insightsOfferNext,
  insightsOfferNoStock,
  insightsOfferOwnPrice,
  insightsOfferPercentOfGrant,
  insightsOfferPerShare,
  insightsOfferPerYear,
  insightsOfferPickCompany,
  insightsOfferPriceNeedsKey,
  insightsOfferPriceNoClose,
  insightsOfferPriceSettings,
  insightsOfferPrivate,
  insightsOfferProgress,
  insightsOfferQBase,
  insightsOfferQBaseHint,
  insightsOfferQBonus,
  insightsOfferQBonusHint,
  insightsOfferQCompany,
  insightsOfferQCompanyHint,
  insightsOfferQPrice,
  insightsOfferQPriceQuote,
  insightsOfferQSignOn,
  insightsOfferQSignOnHint,
  insightsOfferQStock,
  insightsOfferQStockHint,
  insightsOfferQStrike,
  insightsOfferQStrikeHint,
  insightsOfferQValuation,
  insightsOfferQVesting,
  insightsOfferQVestingHint,
  insightsOfferQVestingStated,
  insightsOfferQVestingStatedHint,
  insightsOfferSaveFailed,
  insightsOfferShareCount,
  insightsOfferShowTable,
  insightsOfferSignOn,
  insightsOfferSignOnBridges,
  insightsOfferSignOnColumn,
  insightsOfferSignOnNo,
  insightsOfferSignOnYes,
  insightsOfferStartIntro,
  insightsOfferStartTitle,
  insightsOfferStartedFrom,
  insightsOfferSwap,
  insightsOfferTag,
  insightsOfferTcMoved,
  insightsOfferTcMovedFull,
  insightsOfferTcToday,
  insightsOfferTcTodayFull,
  insightsOfferTypical,
  insightsOfferUndo,
  insightsOfferUnfinished,
  insightsOfferUsePrice,
  insightsOfferValuationGrant,
  insightsOfferValuationHint,
  insightsOfferValuationNone,
  insightsOfferValuationTest,
  insightsOfferValuationUnit,
  insightsOfferValuationUnitOption,
  insightsOfferVestingDiffers,
  insightsOfferVestingEven,
  insightsOfferVestingOther,
  insightsOfferVestingSum,
  insightsOfferVestingTooMuch,
  insightsOfferVestingYear,
  insightsOfferVestingYes,
  insightsOfferVsToday,
  insightsOfferYear,
  insightsOfferYearN,
  insightsStockTrajectoryPanelBase,
  insightsStockTrajectoryPanelBonus,
  insightsStockTrajectoryPanelEquity,
  insightsStockTrajectoryPanelOptions,
  insightsStockTrajectoryPanelRsus,
} from "../../copy/gen/insights";
import {
  ANOTHER_COMPANY,
  EMPTY_OFFER,
  OFFER_YEARS,
  computeOffer,
  pickCompany,
  termsFor,
  type GrantUnit,
  type OfferInputs,
  type OfferResult,
  type StoredOffer,
  type StoredValuation,
  type Valuation,
  type ValuationUnit,
  type Vehicle,
} from "./offerModel";
import { BONUS_PRESETS, VESTING_PRESETS, nextStep, stageOf, stepsFor, type OfferStep } from "./offerSteps";

/* The person's own offer, year by year (docs/ui.md, Insights views), asked one
 * question at a time beside a chart that fills in with each answer. Every
 * answer is kept on this computer (`/api/profile/offer`); this component makes
 * no request of its own. */

const SLIDER_MIN = -75;
const SLIDER_MAX = 200;
/** Companies offered as one press on the first question. */
const SUGGESTED = 4;
/** The company picker's value before a company is chosen. */
const UNPICKED = "-";

function toInput(n: number | null | undefined): string {
  return n == null ? "" : numberInput(n);
}

function readInput(text: string): number | null | undefined {
  const t = text.trim();
  if (t === "") return null;
  const n = parseNumber(t);
  return Number.isFinite(n) && n >= 0 ? n : undefined;
}

/** A number the person types. The draft is the field's own until it reads as a
 *  number; a figure set from outside (a preset) replaces it. */
function NumberField({
  label,
  value,
  onChange,
  suffix,
  invalid,
  className,
}: {
  label: string;
  value: number | null;
  onChange: (value: number | null) => void;
  suffix?: ReactNode;
  invalid?: boolean;
  className?: string;
}) {
  const [draft, setDraft] = useState(() => toInput(value));
  useEffect(() => {
    setDraft((current) => {
      const read = readInput(current);
      return read === value || (read != null && value != null && Math.abs(read - value) < 1e-9) ? current : toInput(value);
    });
  }, [value]);
  const id = useId();
  return (
    <span className={`traj-offer-field${className ? ` ${className}` : ""}`}>
      <label className="sr-only" htmlFor={id}>{label}</label>
      <input
        id={id}
        type="text"
        inputMode="decimal"
        autoComplete="off"
        aria-invalid={invalid || readInput(draft) === undefined || undefined}
        value={draft}
        onChange={(e) => {
          setDraft(e.target.value);
          const read = readInput(e.target.value);
          if (read !== undefined) onChange(read);
        }}
      />
      {suffix && <span className="traj-offer-suffix" aria-hidden="true">{suffix}</span>}
    </span>
  );
}

const fmtMoney = (n: number): string => String(fmtComp(Math.round(n)));
const fmtCount = (n: number): string => number(Math.round(n));
const schedule = (v: readonly (number | null)[]): string => list(v.map((x) => number(x ?? 0)));

/** A choice made with one press: pressed while it is the answer. */
function Choice({ pressed, onClick, children }: { pressed: boolean; onClick: () => void; children: ReactNode }) {
  return (
    <FilterChip selected={pressed} onClick={onClick}>
      {children}
    </FilterChip>
  );
}

export interface OfferCalculatorProps {
  terms: OfferTerms | null;
  /** The kept offer, or null before the first answer. */
  offer: StoredOffer | null;
  valuations: Record<string, StoredValuation>;
  /** Companies the tab lists, most relevant first: the first few are one press. */
  suggested: readonly string[];
  /** Keeps the offer as it now stands. */
  onSave: (draft: OfferDraft) => void;
  onClear: () => void;
  onValuation: (company: string, valuation: Valuation | null) => void;
  /** The last save did not reach the store. */
  saveFailed: boolean;
  /** The offer before the last start from typical figures, for Undo. */
  previous: StoredOffer | null;
  onUndo: () => void;
  /** The tab's move, whole percent; one slider for the tab and this offer. */
  pct: number;
  onPct: (pct: number) => void;
}

/** How the person reached the question on screen: walking the questions in
 *  order, or changing one answer from its chip. */
type Mode = "walk" | "edit";

export const OfferCalculator = forwardRef<HTMLHeadingElement, OfferCalculatorProps>(function OfferCalculator(
  { terms, offer, valuations, suggested, onSave, onClear, onValuation, saveFailed, previous, onUndo, pct, onPct },
  headingRef,
) {
  const headingId = useId();
  const [asking, setAsking] = useState<OfferStep | null>(null);
  const [mode, setMode] = useState<Mode>("walk");
  const [draft, setDraft] = useState<OfferInputs>(offer?.inputs ?? EMPTY_OFFER);
  const [picked, setPicked] = useState<string>(offer ? offer.inputs.company : UNPICKED);
  const [valuationDraft, setValuationDraft] = useState<Valuation | null>(null);
  // One question's own state: a choice that reveals fields, and what is missing.
  const [open, setOpen] = useState(false);
  const [need, setNeed] = useState(false);
  // Focus follows the person's own steps, never the first paint.
  const moved = useRef(false);
  const questionRef = useRef<HTMLHeadingElement>(null);

  const answered = offer?.answered ?? [];
  const startsFromTypical = !!offer?.started_from;
  const inputs = asking ? draft : offer?.inputs ?? EMPTY_OFFER;
  const company = termsFor(terms, inputs.company);
  const steps = stepsFor(inputs, company);
  const stage = stageOf(offer, steps);
  // Before the first answer the block is the first question.
  const question: OfferStep | null = asking ?? (stage === "start" ? "company" : null);

  useEffect(() => {
    if (moved.current) questionRef.current?.focus({ preventScroll: false });
  }, [question]);

  // A cleared offer starts again at the first question.
  const cleared = offer === null;
  useEffect(() => {
    if (!cleared) return;
    setAsking(null);
    setMode("walk");
    setDraft(EMPTY_OFFER);
    setPicked(UNPICKED);
    setNeed(false);
  }, [cleared]);

  const valuation = valuations[inputs.company] ?? null;
  const shownValuation = asking === "valuation" ? valuationDraft : valuation;
  const result = computeOffer(inputs, company, shownValuation, pct / 100);

  const ask = (step: OfferStep | null, how: Mode = mode, from: OfferInputs = offer?.inputs ?? EMPTY_OFFER) => {
    moved.current = true;
    setAsking(step);
    setMode(how);
    setDraft(from);
    setPicked(from.company === ANOTHER_COMPANY && !offer ? UNPICKED : from.company);
    setValuationDraft(valuations[from.company] ?? null);
    setOpen(false);
    setNeed(false);
  };

  /** Keep the answer to `step` and move on: to the next question still open,
   *  or, after changing one answer, back to the offer. */
  const answer = (step: OfferStep, next: OfferInputs) => {
    const nowAnswered = [...new Set([...answered, step])];
    onSave({ inputs: next, answered: nowAnswered, started_from: offer?.started_from ?? null });
    const following = stepsFor(next, termsFor(terms, next.company));
    // A change from a chip goes back to the offer, unless the change opened a
    // question the offer now asks (a grant in shares asks today's price).
    const after = startsFromTypical && mode === "edit" ? null : nextStep(nowAnswered, following);
    ask(after, mode, next);
  };

  const edit = (patch: Partial<OfferInputs>) => {
    setNeed(false);
    setDraft((d) => ({ ...d, ...patch }));
  };

  if (question === null && stage === "unfinished" && offer) {
    const open = steps.filter((s) => !answered.includes(s));
    return (
      <section className="panel traj-offer traj-offer-paused" aria-labelledby={headingId} data-testid="traj-offer">
        <div>
          <h3 id={headingId} ref={headingRef} tabIndex={-1}>{insightsOfferFinishedTitle(titleArgs(inputs.company))}</h3>
          <p className="sub">{insightsOfferUnfinished({ answered: steps.length - open.length, total: steps.length })}</p>
        </div>
        <div className="traj-offer-actions">
          <Dots steps={steps} done={steps.length - open.length} />
          <Button variant="primary" onClick={() => ask(open[0], "walk")}>{insightsOfferContinue()}</Button>
          <Button variant="ghost" size="sm" onClick={onClear}>{insightsOfferClear()}</Button>
        </div>
        {saveFailed && <SaveFailed />}
      </section>
    );
  }

  if (question === null && offer) {
    return (
      <section className="panel traj-offer" aria-labelledby={headingId} data-testid="traj-offer">
        <div className="traj-offer-head">
          <h3 id={headingId} ref={headingRef} tabIndex={-1}>{insightsOfferFinishedTitle(titleArgs(inputs.company))}</h3>
          {answered.some((s) => s !== "company") && (
            <span className="split-src split-src-entered">{insightsOfferEntered({ date: calendarDay(offer.saved_at) })}</span>
          )}
        </div>
        {offer.started_from && (
          <p className="traj-offer-origin" role="status">
            {insightsOfferStartedFrom({
              kind: offer.started_from.title ? "role" : "company",
              title: offer.started_from.title ?? "",
              company: companyName(offer.started_from.company),
            })}
            {previous && (
              <>
                {" "}
                <Button variant="link" onClick={onUndo}>{insightsOfferUndo()}</Button>
              </>
            )}
          </p>
        )}
        {offer.started_from && steps.some((s) => s !== "company" && !answered.includes(s)) && (
          <p className="traj-offer-typical">
            {insightsOfferTypical()}{" "}
            <Button variant="primary" size="sm" onClick={() => ask(nextStep(answered, steps), "walk")}>{insightsOfferSwap()}</Button>
          </p>
        )}
        <ul className="traj-offer-answers" aria-label={insightsOfferFinishedTitle(titleArgs(inputs.company))}>
          {steps.map((step) => {
            const chip = chipFor(step, inputs, company, result, valuation);
            const tag = tagFor(step, answered, startsFromTypical, result);
            return (
              <li key={step}>
                <Button
                  size="sm"
                  className="traj-offer-answer"
                  aria-label={insightsOfferChipEdit({ answer: chip })}
                  onClick={() => ask(step, "edit")}
                >
                  {chip}
                  {tag && <Badge shape="tag" variant="outline">{insightsOfferTag({ tag })}</Badge>}
                </Button>
              </li>
            );
          })}
          {company?.bonus_rule === "none" && (
            <li>
              <span className="traj-offer-rule">
                {insightsOfferChipBonus({ pct: 0 })}
                <Badge shape="tag" variant="outline">{insightsOfferTag({ tag: "rule" })}</Badge>
              </span>
            </li>
          )}
        </ul>
        <Outcome result={result} pct={pct} onPct={onPct} />
        <div className="traj-offer-actions">
          <Button variant="ghost" size="sm" onClick={onClear}>{insightsOfferClear()}</Button>
        </div>
        {saveFailed && <SaveFailed />}
      </section>
    );
  }

  const step = question ?? "company";
  const index = steps.indexOf(step);
  const name = inputs.company === ANOTHER_COMPANY ? "" : companyName(inputs.company);
  const startView = stage === "start" && asking === null;

  const submit = (e: FormEvent) => {
    e.preventDefault();
    const missing = missingFor(step, draft, picked, valuationDraft, open, company);
    if (missing) {
      setNeed(true);
      return;
    }
    if (step === "company") {
      const next = pickCompany(
        { ...draft, listed: picked === ANOTHER_COMPANY ? draft.listed : true },
        picked,
        terms,
      );
      answer("company", next);
      return;
    }
    if (step === "valuation" && valuationDraft) onValuation(draft.company, valuationDraft);
    answer(step, draft);
  };

  return (
    <section className="panel traj-offer" aria-labelledby={headingId} data-testid="traj-offer">
      {startView && (
        <div className="traj-offer-head">
          <div>
            <h3 id={headingId} ref={headingRef} tabIndex={-1}>{insightsOfferStartTitle()}</h3>
            <p className="sub">{insightsOfferStartIntro()}</p>
          </div>
        </div>
      )}
      {!startView && <h3 id={headingId} ref={headingRef} tabIndex={-1} className="sr-only">{insightsOfferFinishedTitle(titleArgs(inputs.company))}</h3>}
      <div className="traj-offer-ask">
        <form className="traj-offer-question" onSubmit={submit} noValidate data-testid="traj-offer-question" data-step={step}>
          {mode === "walk" && index >= 0 && !startView && (
            <>
              <Dots steps={steps} done={index} />
              <span className="sr-only">{insightsOfferProgress({ n: index + 1, total: steps.length })}</span>
            </>
          )}
          <Question
            step={step}
            ref={questionRef}
            draft={draft}
            company={company}
            name={name}
            terms={terms}
            suggested={suggested}
            picked={picked}
            onPick={(value) => {
              setNeed(false);
              setPicked(value);
            }}
            edit={edit}
            open={open}
            setOpen={setOpen}
            valuation={valuationDraft}
            setValuation={(v) => {
              setNeed(false);
              setValuationDraft(v);
            }}
            onAnswer={(next) => answer(step, next)}
            onSkipValuation={() => answer("valuation", draft)}
          />
          {need && (
            <p className="traj-offer-need" role="alert">
              {step === "vesting" && vestingSum(draft) > 100
                ? insightsOfferVestingTooMuch({ pct: vestingSum(draft) })
                : insightsOfferNeed({ what: step })}
            </p>
          )}
          <div className="traj-offer-actions">
            {(mode === "edit" || index > 0) && !startView && (
              <Button
                variant="ghost"
                onClick={() => (mode === "edit" ? ask(null, "walk") : ask(steps[index - 1], "walk", draft))}
              >
                {mode === "edit" ? insightsOfferCancel() : insightsOfferBack()}
              </Button>
            )}
            {showsNext(step, company, open) && (
              <Button variant="primary" type="submit">{mode === "edit" ? insightsOfferDone() : insightsOfferNext()}</Button>
            )}
            {mode === "walk" && offer && (
              <Button variant="link" onClick={() => ask(null, "walk")}>{insightsOfferLater()}</Button>
            )}
          </div>
          {saveFailed && <SaveFailed />}
        </form>
        <div className="traj-offer-preview">
          <Bars result={result} empty={!inputs.base} />
        </div>
      </div>
    </section>
  );
});

function titleArgs(company: string) {
  return company === ANOTHER_COMPANY
    ? { named: "no", company: "" }
    : { named: "yes", company: companyName(company) };
}

function vestingSum(inputs: OfferInputs): number {
  return Math.round((inputs.vesting ?? []).reduce<number>((a, v) => a + (v ?? 0), 0) * 10) / 10;
}

/** What a question still needs before Next keeps it; null when it is ready. */
function missingFor(
  step: OfferStep,
  d: OfferInputs,
  picked: string,
  valuation: Valuation | null,
  open: boolean,
  company: OfferTermsCompany | null,
): boolean {
  switch (step) {
    case "company":
      return picked === UNPICKED;
    case "base":
      return !d.base;
    case "stock":
      return d.grant == null;
    case "strike":
      return d.strike == null;
    case "price":
      return (open || !company?.quote) && !d.price;
    case "valuation":
      return !valuation?.grant_at;
    case "vesting":
      // No choice is an even schedule, shown as assumed.
      return vestingSum(d) > 100 || (d.vesting?.every((v) => v == null) ?? false);
    case "bonus":
      return d.bonus_pct == null;
    case "sign_on":
      return open && !d.sign_on[0] && !d.sign_on[1];
  }
}

/** Whether a question shows Next: a question answered with one press shows it
 *  only once a field is open. */
function showsNext(step: OfferStep, company: OfferTermsCompany | null, open: boolean): boolean {
  if (step === "price") return open || !company?.quote;
  if (step === "vesting") return open || !company?.vesting?.length;
  if (step === "sign_on") return open;
  return true;
}

interface QuestionProps {
  step: OfferStep;
  draft: OfferInputs;
  company: OfferTermsCompany | null;
  /** The company's name, or empty for a company not on the list. */
  name: string;
  terms: OfferTerms | null;
  suggested: readonly string[];
  picked: string;
  onPick: (company: string) => void;
  edit: (patch: Partial<OfferInputs>) => void;
  open: boolean;
  setOpen: (open: boolean) => void;
  valuation: Valuation | null;
  setValuation: (valuation: Valuation) => void;
  onAnswer: (next: OfferInputs) => void;
  onSkipValuation: () => void;
}

/** One question: its heading, a line on what to enter, and the answer. */
const Question = forwardRef<HTMLHeadingElement, QuestionProps>(function Question(props, ref) {
  const { step, draft, company, name } = props;
  const heading = (text: string) => (
    <h4 className="traj-offer-q" ref={ref} tabIndex={-1}>{text}</h4>
  );
  const hint = (text: ReactNode) => <p className="traj-offer-hint">{text}</p>;

  switch (step) {
    case "company":
      return (
        <>
          {heading(insightsOfferQCompany())}
          {hint(insightsOfferQCompanyHint())}
          <CompanyAnswer {...props} />
        </>
      );
    case "base":
      return (
        <>
          {heading(insightsOfferQBase())}
          {hint(insightsOfferQBaseHint())}
          <NumberField label={insightsOfferQBase()} value={draft.base} onChange={(base) => props.edit({ base })} suffix={insightsOfferPerYear()} />
        </>
      );
    case "stock": {
      const kind = stockKind(draft, company);
      return (
        <>
          {heading(insightsOfferQStock({ vehicle: kind === "another" ? "rsu" : kind }))}
          {hint(insightsOfferQStockHint({ vehicle: kind, company: name }))}
          {kind === "another" && (
            <Segmented<Vehicle>
              label={insightsOfferEquityType()}
              value={draft.vehicle}
              onChange={(vehicle) => props.edit({ vehicle, grant_unit: vehicle === "options" ? "shares" : draft.grant_unit })}
              options={[
                { value: "rsu", label: insightsStockTrajectoryPanelRsus() },
                { value: "options", label: insightsStockTrajectoryPanelOptions() },
              ]}
            />
          )}
          <div className="traj-offer-row">
            <NumberField
              label={insightsOfferQStock({ vehicle: kind === "another" ? "rsu" : kind })}
              value={draft.grant}
              onChange={(grant) => props.edit({ grant })}
              suffix={draft.vehicle === "options" ? insightsStockTrajectoryPanelOptions() : undefined}
            />
            {draft.vehicle !== "options" && kind !== "cash" && (
              <Segmented<GrantUnit>
                label={insightsOfferGrantUnit()}
                value={draft.grant_unit}
                onChange={(grant_unit) => props.edit({ grant_unit })}
                options={[
                  { value: "dollars", label: insightsOfferGrantUnitOption({ unit: "dollars" }) },
                  { value: "shares", label: insightsOfferGrantUnitOption({ unit: "shares" }) },
                ]}
              />
            )}
            <Button variant="ghost" onClick={() => props.onAnswer({ ...draft, grant: 0 })}>
              {insightsOfferNoStock({ vehicle: draft.vehicle === "options" ? "options" : kind === "cash" ? "cash" : "rsu" })}
            </Button>
          </div>
        </>
      );
    }
    case "strike":
      return (
        <>
          {heading(insightsOfferQStrike())}
          {hint(insightsOfferQStrikeHint())}
          <NumberField label={insightsOfferQStrike()} value={draft.strike} onChange={(strike) => props.edit({ strike })} suffix={insightsOfferPerShare()} />
        </>
      );
    case "price":
      return <PriceAnswer {...props} heading={heading} hint={hint} />;
    case "valuation":
      return <ValuationAnswer {...props} heading={heading} hint={hint} />;
    case "vesting":
      return <VestingAnswer {...props} heading={heading} hint={hint} />;
    case "bonus":
      return (
        <>
          {heading(insightsOfferQBonus())}
          {hint(company?.bonus_rule === "pct_of_base" ? insightsOfferBonusRule({ rule: "pct_of_base" }) : insightsOfferQBonusHint())}
          <div className="traj-offer-row">
            {BONUS_PRESETS.map((p) => (
              <Choice key={p} pressed={draft.bonus_pct === p && !props.open} onClick={() => {
                props.setOpen(false);
                props.edit({ bonus_pct: p });
              }}>
                {insightsOfferBonusChoice({ pct: p })}
              </Choice>
            ))}
            <NumberField
              className="traj-offer-field-short"
              label={insightsOfferBonusOther()}
              value={BONUS_PRESETS.includes(draft.bonus_pct ?? -1) ? null : draft.bonus_pct}
              onChange={(bonus_pct) => props.edit({ bonus_pct })}
              suffix="%"
            />
          </div>
        </>
      );
    case "sign_on":
      return (
        <>
          {heading(insightsOfferQSignOn())}
          {hint(company?.sign_on_bridges_vesting ? insightsOfferSignOnBridges() : insightsOfferQSignOnHint())}
          <div className="traj-offer-row">
            <Choice pressed={props.open} onClick={() => props.setOpen(true)}>{insightsOfferSignOnYes()}</Choice>
            <Choice pressed={false} onClick={() => props.onAnswer({ ...draft, sign_on: [null, null] })}>{insightsOfferSignOnNo()}</Choice>
          </div>
          {props.open && (
            <div className="traj-offer-pair">
              {[0, 1].map((i) => (
                <div key={i} className="traj-offer-labelled">
                  <span aria-hidden="true">{insightsOfferSignOn({ year: i + 1 })}</span>
                  <NumberField
                    label={insightsOfferSignOn({ year: i + 1 })}
                    value={draft.sign_on[i]}
                    onChange={(v) => props.edit({ sign_on: i === 0 ? [v, draft.sign_on[1]] : [draft.sign_on[0], v] })}
                  />
                </div>
              ))}
            </div>
          )}
        </>
      );
  }
});

type StockKind = "rsu" | "options" | "cash" | "another";

function stockKind(d: OfferInputs, company: OfferTermsCompany | null): StockKind {
  if (company?.equity_vehicle === "cash_election") return "cash";
  if (!company) return d.vehicle === "options" ? "options" : "another";
  return d.vehicle === "options" ? "options" : "rsu";
}

function CompanyAnswer({ terms, suggested, picked, onPick, draft, edit }: QuestionProps) {
  const known = new Set((terms?.companies ?? []).map((c) => c.company));
  const quick = suggested.filter((c) => known.has(c)).slice(0, SUGGESTED);
  const options = [
    { value: UNPICKED, label: insightsOfferPickCompany() },
    ...(terms?.companies ?? [])
      .map((c) => ({ value: c.company, label: companyName(c.company) }))
      .sort((a, b) => compare(a.label, b.label)),
    { value: ANOTHER_COMPANY, label: insightsOfferAnotherCompany() },
  ];
  return (
    <>
      {quick.length > 0 && (
        <div className="traj-offer-row">
          {quick.map((c) => (
            <Choice key={c} pressed={picked === c} onClick={() => onPick(c)}>{companyName(c)}</Choice>
          ))}
        </div>
      )}
      <div className="traj-offer-row">
        <Select label={insightsOfferAllCompanies()} value={picked} options={options} onChange={onPick} />
        {picked === ANOTHER_COMPANY && (
          <Segmented
            label={insightsOfferListedLabel()}
            value={draft.listed ? "yes" : "no"}
            onChange={(v) => edit({ listed: v === "yes" })}
            options={[
              { value: "yes", label: insightsOfferListed({ listed: "yes" }) },
              { value: "no", label: insightsOfferListed({ listed: "no" }) },
            ]}
          />
        )}
      </div>
    </>
  );
}

interface Framed extends QuestionProps {
  heading: (text: string) => ReactNode;
  hint: (text: ReactNode) => ReactNode;
}

function PriceAnswer({ draft, company, name, terms, open, setOpen, edit, onAnswer, heading, hint }: Framed) {
  const quote = company?.quote ?? null;
  if (quote && !open) {
    const price = money(quote.price);
    return (
      <>
        {heading(insightsOfferQPrice({ quote: "yes", company: name }))}
        {hint(insightsOfferQPriceQuote({ price, date: calendarDay(quote.as_of) }))}
        <div className="traj-offer-row">
          <Button variant="primary" onClick={() => onAnswer({ ...draft, price: null })}>{insightsOfferUsePrice({ price })}</Button>
          <Button variant="ghost" onClick={() => setOpen(true)}>{insightsOfferOwnPrice()}</Button>
        </div>
      </>
    );
  }
  return (
    <>
      {heading(insightsOfferQPrice({ quote: "no", company: name }))}
      {/* A close can be filled only for a company the catalog lists. */}
      {!quote && company && hint(
        terms?.feed_configured && company?.ticker
          ? insightsOfferPriceNoClose({ ticker: company.ticker })
          : <Msg of={insightsOfferPriceNeedsKey} elems={{ link: <Link to="/settings/plugins">{insightsOfferPriceSettings()}</Link> }} />,
      )}
      <NumberField label={insightsOfferQPrice({ quote: "no", company: name })} value={draft.price} onChange={(price) => edit({ price })} suffix={insightsOfferPerShare()} />
    </>
  );
}

function ValuationAnswer({ name, valuation, setValuation, onSkipValuation, heading, hint }: Framed) {
  const v: Valuation = valuation ?? { unit: "per_share", grant_at: null, test_at: null, share_count: null };
  const unit: ValuationUnit = v.unit;
  return (
    <>
      {heading(insightsOfferQValuation({ company: name }))}
      {hint(<>{insightsOfferPrivate()} {insightsOfferValuationHint()}</>)}
      <Segmented<ValuationUnit>
        label={insightsOfferValuationUnit()}
        value={unit}
        onChange={(u) => setValuation({ ...v, unit: u })}
        options={[
          { value: "per_share", label: insightsOfferValuationUnitOption({ unit: "per_share" }) },
          { value: "company", label: insightsOfferValuationUnitOption({ unit: "company" }) },
        ]}
      />
      <div className="traj-offer-pair">
        <div className="traj-offer-labelled">
          <span aria-hidden="true">{insightsOfferValuationGrant({ unit })}</span>
          <NumberField label={insightsOfferValuationGrant({ unit })} value={v.grant_at} onChange={(grant_at) => setValuation({ ...v, grant_at })} />
        </div>
        <div className="traj-offer-labelled">
          <span aria-hidden="true">{insightsOfferValuationTest({ unit })}</span>
          <NumberField label={insightsOfferValuationTest({ unit })} value={v.test_at} onChange={(test_at) => setValuation({ ...v, test_at })} />
        </div>
        {unit === "company" && (
          <div className="traj-offer-labelled">
            <span aria-hidden="true">{insightsOfferShareCount()}</span>
            <NumberField label={insightsOfferShareCount()} value={v.share_count} onChange={(share_count) => setValuation({ ...v, share_count })} />
          </div>
        )}
      </div>
      {!valuation?.grant_at && (
        <div className="traj-offer-row">
          <Button variant="ghost" onClick={onSkipValuation}>{insightsOfferDontKnow()}</Button>
        </div>
      )}
    </>
  );
}

function VestingAnswer({ draft, company, name, open, setOpen, edit, onAnswer, heading, hint }: Framed) {
  const stated = company?.vesting?.length ? company.vesting : null;
  const fields = (
    <>
      <div className="traj-offer-years">
        {Array.from({ length: OFFER_YEARS }, (_, i) => (
          <NumberField
            key={i}
            label={insightsOfferVestingYear({ year: i + 1 })}
            value={draft.vesting?.[i] ?? null}
            onChange={(v) => {
              const next = Array.from({ length: OFFER_YEARS }, (_, j) => draft.vesting?.[j] ?? null);
              next[i] = v;
              edit({ vesting: next });
            }}
            suffix="%"
          />
        ))}
      </div>
      {hint(insightsOfferPercentOfGrant())}
    </>
  );
  if (stated) {
    return (
      <>
        {heading(insightsOfferQVestingStated({ schedule: schedule(stated) }))}
        {!open && hint(insightsOfferQVestingStatedHint({ company: name }))}
        {!open && (
          <div className="traj-offer-row">
            <Button variant="primary" onClick={() => onAnswer({ ...draft, vesting: null })}>{insightsOfferVestingYes()}</Button>
            <Button variant="ghost" onClick={() => {
              edit({ vesting: [...stated] });
              setOpen(true);
            }}>{insightsOfferVestingDiffers()}</Button>
          </div>
        )}
        {open && fields}
      </>
    );
  }
  const current = draft.vesting;
  const preset = VESTING_PRESETS.find((p) => current && p.every((v, i) => current[i] === v));
  return (
    <>
      {heading(insightsOfferQVesting())}
      {hint(insightsOfferQVestingHint(name ? { named: "yes", company: name } : { named: "no", company: "" }))}
      <div className="traj-offer-row">
        {VESTING_PRESETS.map((p, i) => (
          <Choice key={i} pressed={!open && preset === p} onClick={() => {
            setOpen(false);
            edit({ vesting: [...p] });
          }}>
            {p.join(" / ")}
            {i === 0 && <Badge shape="tag" variant="outline">{insightsOfferVestingEven()}</Badge>}
          </Choice>
        ))}
        <Choice pressed={open} onClick={() => {
          edit({ vesting: current ?? [...VESTING_PRESETS[0]] });
          setOpen(true);
        }}>{insightsOfferVestingOther()}</Choice>
      </div>
      {open && fields}
    </>
  );
}

function Dots({ steps, done }: { steps: readonly OfferStep[]; done: number }) {
  return (
    <span className="traj-offer-dots" aria-hidden="true">
      {steps.map((s, i) => <i key={s} data-done={i <= done || undefined} />)}
    </span>
  );
}

function SaveFailed() {
  return <p className="traj-offer-need" role="alert">{insightsOfferSaveFailed()}</p>;
}

/** Each year's total as a stacked bar: base, bonus, sign-on, equity after the
 *  move. Before the base is known the bars are outlines of what is coming. */
function Bars({ result, empty }: { result: OfferResult; empty: boolean }) {
  const totals = result.years.map((y) => y.totalMoved);
  const top = Math.max(1, ...totals);
  return (
    <figure className="traj-offer-bars" aria-label={insightsOfferChart()} data-empty={empty || undefined}>
      <div className="traj-offer-bars-plot" aria-hidden="true">
        {result.years.map((y) => (
          <div key={y.year} className="traj-offer-bar">
            <div className="traj-offer-bar-stack">
              {empty ? (
                <i className="traj-offer-seg-ghost" style={{ height: `${55 + y.year * 8}%` }} />
              ) : (
                <>
                  <i className="traj-offer-seg-equity" style={{ height: `${(y.equityMoved / top) * 100}%` }} />
                  <i className="traj-offer-seg-signon" style={{ height: `${(y.signOn / top) * 100}%` }} />
                  <i className="traj-offer-seg-bonus" style={{ height: `${(y.bonus / top) * 100}%` }} />
                  <i className="traj-offer-seg-base" style={{ height: `${(y.base / top) * 100}%` }} />
                </>
              )}
            </div>
            <span className="traj-offer-bar-total">{empty ? insightsOfferYearN({ year: y.year }) : fmtMoney(y.totalMoved)}</span>
            {!empty && y.drop && <span className="traj-offer-drop-note">{insightsOfferDrop({ year: y.year - 1 })}</span>}
          </div>
        ))}
      </div>
      {!empty && (
        <figcaption className="traj-offer-legend">
          <span><i className="traj-offer-seg-base" />{insightsStockTrajectoryPanelBase()}</span>
          <span><i className="traj-offer-seg-bonus" />{insightsStockTrajectoryPanelBonus()}</span>
          <span><i className="traj-offer-seg-signon" />{insightsOfferSignOnColumn()}</span>
          <span><i className="traj-offer-seg-equity" />{insightsStockTrajectoryPanelEquity()}</span>
        </figcaption>
      )}
    </figure>
  );
}

/** The finished offer: the bars, the four-year total, the move, and the years
 *  as a table for exact figures and screen readers. */
function Outcome({ result, pct, onPct }: { result: OfferResult; pct: number; onPct: (pct: number) => void }) {
  const moved = pct !== 0;
  const change = result.totalMoved - result.total;
  const listed = result.listed ? "yes" : "no";
  return (
    <>
      <div className="traj-offer-outcome">
        <Bars result={result} empty={false} />
        <div className="traj-offer-sum">
          <span className="traj-offer-sum-label">{insightsOfferFourYears()}</span>
          <strong className="traj-offer-sum-value" data-testid="traj-offer-total">{fmtMoney(result.totalMoved)}</strong>
          <span className="traj-offer-sum-change">
            {insightsOfferVsToday({
              sign: Math.round(change) > 0 ? "up" : Math.round(change) < 0 ? "down" : "same",
              amount: fmtMoney(Math.abs(change)),
            })}
          </span>
          <label className="traj-slider-row traj-offer-move">
            <span className="traj-slider-label">
              {insightsOfferMove({ listed })}
              <output className="traj-slider-val" aria-live="polite">
                {pct > 0 ? "+" : ""}
                {pct}%
              </output>
            </span>
            <input
              type="range"
              className="traj-slider"
              min={SLIDER_MIN}
              max={SLIDER_MAX}
              step={5}
              value={pct}
              aria-label={insightsOfferMoveAria({ listed })}
              onChange={(e) => onPct(Number(e.target.value))}
            />
          </label>
        </div>
      </div>
      {result.missing && (
        <p className="traj-offer-missing" role="status" data-testid="traj-offer-missing">
          {insightsOfferMissing({ missing: result.missing })}
        </p>
      )}
      {!result.listed && result.valued === "priced" && result.years.some((y) => y.equity > 0) && (
        <p className="traj-offer-hint">{insightsOfferPrivate()} {insightsOfferValuationNone()}</p>
      )}
      {result.vestedPct !== 100 && result.years.some((y) => y.equity > 0) && (
        <p className="traj-offer-hint">{insightsOfferVestingSum({ pct: result.vestedPct })}</p>
      )}
      <details className="traj-offer-table-wrap">
        <summary>{insightsOfferShowTable()}</summary>
        <table className="traj-table traj-offer-table" data-testid="traj-offer-years">
          <thead>
            <tr>
              <th scope="col">{insightsOfferYear()}</th>
              <th scope="col" className="num">{insightsStockTrajectoryPanelBase()}</th>
              <th scope="col" className="num">{insightsStockTrajectoryPanelBonus()}</th>
              <th scope="col" className="num">{insightsOfferSignOnColumn()}</th>
              <th scope="col" className="num">{insightsStockTrajectoryPanelEquity()}</th>
              <th scope="col" className="num">
                <Abbr short={insightsOfferTcToday()} full={insightsOfferTcTodayFull()} />
              </th>
              {moved && (
                <th scope="col" className="num">
                  <Abbr
                    short={insightsOfferTcMoved({ move: pct > 0 ? "up" : "down", pct })}
                    full={insightsOfferTcMovedFull({ move: pct > 0 ? "up" : "down", pct: Math.abs(pct) })}
                  />
                </th>
              )}
            </tr>
          </thead>
          <tbody>
            {result.years.map((y) => (
              <tr key={y.year} className={y.drop ? "traj-offer-drop" : undefined}>
                <th scope="row">{insightsOfferYearN({ year: y.year })}</th>
                <td className="num">{fmtMoney(y.base)}</td>
                <td className="num">{fmtMoney(y.bonus)}</td>
                <td className="num">{fmtMoney(y.signOn)}</td>
                <td className="num">{fmtMoney(y.equity)}</td>
                <td className="num traj-offer-total">{fmtMoney(y.total)}</td>
                {moved && <td className="num traj-offer-total">{fmtMoney(y.totalMoved)}</td>}
              </tr>
            ))}
          </tbody>
          <tfoot>
            <tr>
              <th scope="row">{insightsOfferFourYears()}</th>
              <td className="num">{fmtMoney(result.years.reduce((a, y) => a + y.base, 0))}</td>
              <td className="num">{fmtMoney(result.years.reduce((a, y) => a + y.bonus, 0))}</td>
              <td className="num">{fmtMoney(result.years.reduce((a, y) => a + y.signOn, 0))}</td>
              <td className="num">{fmtMoney(result.years.reduce((a, y) => a + y.equity, 0))}</td>
              <td className="num traj-offer-total">{fmtMoney(result.total)}</td>
              {moved && <td className="num traj-offer-total">{fmtMoney(result.totalMoved)}</td>}
            </tr>
          </tfoot>
        </table>
      </details>
    </>
  );
}

/** One answer as its chip reads. */
function chipFor(
  step: OfferStep,
  d: OfferInputs,
  company: OfferTermsCompany | null,
  result: OfferResult,
  valuation: StoredValuation | null,
): string {
  switch (step) {
    case "company":
      return d.company === ANOTHER_COMPANY
        ? insightsOfferChipAnother({ listed: d.listed ? "yes" : "no" })
        : companyName(d.company);
    case "base":
      return insightsOfferChipBase({ amount: fmtMoney(d.base ?? 0) });
    case "stock": {
      if (!d.grant) return insightsOfferChipStock({ kind: "none", amount: "", count: "" });
      if (company?.equity_vehicle === "cash_election") return insightsOfferChipStock({ kind: "cash", amount: fmtMoney(d.grant), count: "" });
      if (d.vehicle === "options") return insightsOfferChipStock({ kind: "options", amount: "", count: fmtCount(d.grant) });
      if (d.grant_unit === "shares") return insightsOfferChipStock({ kind: "shares", amount: "", count: fmtCount(d.grant) });
      return insightsOfferChipStock({ kind: "dollars", amount: fmtMoney(d.grant), count: "" });
    }
    case "strike":
      return insightsOfferChipStrike({ amount: money(d.strike ?? 0) });
    case "price":
      return insightsOfferChipPrice({ amount: result.price ? money(result.price.value) : "?" });
    case "valuation":
      if (!valuation?.grant_at) return insightsOfferChipValuation({ kind: "none", from: "", to: "" });
      return insightsOfferChipValuation({
        kind: valuation.unit,
        from: valuation.unit === "company" ? fmtMoney(valuation.grant_at) : money(valuation.grant_at),
        to: valuation.unit === "company" ? fmtMoney(valuation.test_at ?? valuation.grant_at) : money(valuation.test_at ?? valuation.grant_at),
      });
    case "vesting":
      return insightsOfferChipVesting({ schedule: result.vesting.map((v) => number(v)).join(" / ") });
    case "bonus":
      return insightsOfferChipBonus({ pct: d.bonus_pct ?? 0 });
    case "sign_on":
      return d.sign_on[0] || d.sign_on[1]
        ? insightsOfferChipSignOn({ kind: "some", first: fmtMoney(d.sign_on[0] ?? 0), second: fmtMoney(d.sign_on[1] ?? 0) })
        : insightsOfferChipSignOn({ kind: "none", first: "", second: "" });
  }
}

/** Where an answer comes from, when it is not simply the person's. */
function tagFor(
  step: OfferStep,
  answered: readonly OfferStep[],
  typical: boolean,
  result: OfferResult,
): string | null {
  // A schedule and a price say where they come from even once confirmed: the
  // company's stated schedule, an assumed even one, the stored close.
  if (step === "vesting") return result.vestingFrom === "you" ? null : result.vestingFrom;
  if (step === "price") return result.price?.from === "quote" ? "quote" : null;
  if (step === "company" || answered.includes(step)) return null;
  return typical ? "typical" : null;
}

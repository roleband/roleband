import "../../patterns/figure-table.css";
import { ResourceLoadState } from "../../ui/ResourceLoadState";
import { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import type { CompPackage, CompPartSource, CompTrajectory, CompTrajectoryCompany, OfferAnswers, OfferDraft, OfferTerms } from "../../api";
import { api } from "../../api";
import { useAsyncResource } from "../../hooks/useAsyncResource";
import { useWriteQueue } from "../../hooks/useWriteQueue";
import { useSourceSwitch } from "../../context/SyncState";
import { InsightHero } from "./InsightHero";
import { fmtComp, companyName } from "../../format";
import { TrajectoryShockChart } from "./charts/StatisticsCharts";
import { InfoTip } from "../../ui/InfoTip";
import { Abbr } from "../../ui/Abbr";
import { Button } from "../../ui/Button";
import { useToast } from "../../ui/Toast";
import { SearchField } from "../../ui/SearchField";
import { matchCompanies } from "./hiring";
import { OfferCalculator } from "./OfferCalculator";
import { offerFromPackage, type StoredOffer, type StoredValuation, type Valuation } from "./offerModel";
import {
  insightsCommonCompany,
  insightsSkillsViewRoles,
  insightsStockTrajectoryPanelAboutPublicCompanyProjections,
  insightsStockTrajectoryPanelAboutTheSourceLabels,
  insightsStockTrajectoryPanelAtPriceChange,
  insightsStockTrajectoryPanelBase,
  insightsStockTrajectoryPanelBonus,
  insightsStockTrajectoryPanelChoiceCompanies,
  insightsStockTrajectoryPanelChoiceExplained,
  insightsStockTrajectoryPanelCashElection,
  insightsStockTrajectoryPanelChange,
  insightsStockTrajectoryPanelEquity,
  insightsStockTrajectoryPanelEquityFigure,
  insightsStockTrajectoryPanelEquityShare,
  insightsStockTrajectoryPanelEquityShockwave,
  insightsStockTrajectoryPanelHowStockTrajectoryIsProjected,
  insightsStockTrajectoryPanelHowToReadEquitySensitivity,
  insightsStockTrajectoryPanelLeftOut,
  insightsStockTrajectoryPanelLeftOutReason,
  insightsStockTrajectoryPanelLoadFailed,
  insightsDemandFindACompany,
  insightsStockTrajectoryPanelLoading,
  insightsStockTrajectoryPanelNoCompanyMatches,
  insightsStockTrajectoryPanelMedianTc,
  insightsStockTrajectoryPanelMedianTcFull,
  insightsStockTrajectoryPanelMedianTcTile,
  insightsStockTrajectoryPanelMedianTcTileFull,
  insightsStockTrajectoryPanelNoBonus,
  insightsStockTrajectoryPanelNoEquity,
  insightsStockTrajectoryPanelNoExposure,
  insightsStockTrajectoryPanelNoOpenRolesAtPublic,
  insightsStockTrajectoryPanelNoOpenRolesAtPublicYet,
  insightsStockTrajectoryPanelOfTcAtRisk,
  insightsStockTrajectoryPanelOfTcAtRiskFull,
  insightsStockTrajectoryPanelOptions,
  insightsStockTrajectoryPanelPartSource,
  insightsStockTrajectoryPanelPartSourceExplained,
  insightsStockTrajectoryPanelPaidInCashUnaffectedBy,
  insightsStockTrajectoryPanelPreIpoEquityIsIlliquid,
  insightsStockTrajectoryPanelPrivateCompanies,
  insightsStockTrajectoryPanelProjected,
  insightsStockTrajectoryPanelProjectedTc,
  insightsStockTrajectoryPanelProjectedTcFull,
  insightsStockTrajectoryPanelPublicCompanies,
  insightsStockTrajectoryPanelResetToToday,
  insightsStockTrajectoryPanelRsus,
  insightsStockTrajectoryPanelScenario,
  insightsStockTrajectoryPanelSensitivityExplained,
  insightsStockTrajectoryPanelSortedByEquityExposureOnly,
  insightsStockTrajectoryPanelStockMovesRePriceEquity,
  insightsStockTrajectoryPanelStockPriceChange,
  insightsStockTrajectoryPanelStockPriceChangePercent,
  insightsStockTrajectoryPanelStockTrajectory,
  insightsStockTrajectoryPanelTicker,
  insightsStockTrajectoryPanelToday,
  insightsStockTrajectoryPanelTypicalPackage,
  insightsStockTrajectoryPanelVests,
  insightsStockTrajectoryPanelVsToday,
  insightsStockTrajectoryPanelWhoMovesWhenTheStock,
  insightsStockTrajectoryPanelWhyLeftOut,
  insightsStockTrajectoryPanelWhyPrivateCompaniesDoNot,
  insightsOfferAtYourValuation,
  insightsOfferAtYourValuationMoved,
  insightsOfferCleared,
  insightsOfferAtYourValuationFull,
  insightsOfferColumn,
  insightsOfferEntered,
  insightsOfferLoadFailed,
  insightsOfferLoading,
  insightsOfferStart,
  insightsOfferStartAria,
  insightsOfferUndo,
} from "../../copy/gen/insights";
import { calendarDay } from "../../copy/format";
import { Msg } from "../../ui/Msg";

// Project a comp package onto a stock-price scenario: only the equity slice
// moves (base + bonus are fixed cash), so TC(d) = base + bonus + equity*(1+d).
function projectTc(p: CompPackage, priceChange: number): number {
  return Math.round(p.base + p.bonus + p.equity * (1 + priceChange));
}
const projectedDelta = (p: CompPackage, d: number) => Math.round(p.equity * d);

function fmtSigned(n: number): string {
  const s = fmtComp(Math.abs(n));
  return n < 0 ? `−${s}` : `+${s}`;
}
const fmtPct = (frac: number) => `${Math.round(frac * 100)}%`;

const VEHICLE_LABEL: Record<string, string> = {
  get rsu() { return insightsStockTrajectoryPanelRsus(); },
  get options() { return insightsStockTrajectoryPanelOptions(); },
  get none() { return insightsStockTrajectoryPanelNoEquity(); },
  get cash_election() { return insightsStockTrajectoryPanelCashElection(); },
};

// Says where one part of a package comes from: posted, the company's own rule,
// measured, estimated, or a mix across the company's roles. An estimate must
// never read as a posted or measured figure.
function PartSource({ source }: { source?: CompPartSource }) {
  // Defensive: an absent source must render nothing, never throw: one missing
  // field should not take down the whole panel.
  if (!source) return null;
  return (
    <span className={`split-src split-src-${source}`}>
      {insightsStockTrajectoryPanelPartSource({ source })}
    </span>
  );
}

const PART_SOURCES = ["posted", "company_rule", "measured", "estimated", "mixed"] as const;

// One help mark for the table rather than one per cell: every cell would
// otherwise add a stop to the Tab order for the same sentences. It sits on the
// first column, which stays in view when a narrow table scrolls sideways, so
// the key that hangs from the header row opens on screen.
function SourceKey() {
  return (
    <InfoTip label={insightsStockTrajectoryPanelAboutTheSourceLabels()}>
      {PART_SOURCES.map((source) => (
        <span className="traj-split-key" key={source}>
          <b>{insightsStockTrajectoryPanelPartSource({ source })}</b>
          <span>{insightsStockTrajectoryPanelPartSourceExplained({ source })}</span>
        </span>
      ))}
    </InfoTip>
  );
}

// The equity a company grants and how it vests, as the company states them.
function EquityTerms({ c }: { c: CompTrajectoryCompany }) {
  return (
    <td className="traj-vehicle">
      {c.equity_vehicle && (VEHICLE_LABEL[c.equity_vehicle] ?? c.equity_vehicle)}
      {c.vesting && <span className="traj-vesting">{insightsStockTrajectoryPanelVests({ schedule: c.vesting })}</span>}
      {!c.equity_vehicle && !c.vesting && "—"}
    </td>
  );
}

// Base and bonus with where each comes from. A bonus of zero the company's own
// rule states reads as "No bonus", a fact, never as a figure of $0.
function CashParts({ c }: { c: CompPackage }) {
  return (
    <>
      <td className="num traj-part">
        {fmtComp(c.base)}
        <PartSource source={c.sources.base} />
      </td>
      <td className="num traj-part">
        {c.bonus === 0 && c.sources.bonus === "company_rule" ? insightsStockTrajectoryPanelNoBonus() : fmtComp(c.bonus)}
        <PartSource source={c.sources.bonus} />
      </td>
      <td className="num traj-part">
        {fmtPct(c.equity_pct)}
        <PartSource source={c.sources.equity} />
      </td>
    </>
  );
}

// -75%..+200% in 5% steps; the scenario the equity slice is stress-tested at.
const SLIDER_MIN = -75;
const SLIDER_MAX = 200;
const NO_VALUATIONS: Record<string, StoredValuation> = {};
const NO_ANSWERS: OfferAnswers = { offer: null, valuations: NO_VALUATIONS };

// At today's price the chart shows what a 10% move is worth to each company:
// a chart of zeros would ask a reader to act before telling them anything.
const SENSITIVITY = 0.1;

/** The figures a role's detail page hands this tab to start an offer from. */
interface RoleOffer {
  company: string;
  title: string;
  base: number;
  bonus: number;
  equity: number;
}

// Router state outlives the code that wrote it (a restored history entry), so
// it is read as untrusted.
function roleOfferFrom(state: unknown): RoleOffer | null {
  const from = (state as { offerFrom?: unknown } | null)?.offerFrom as Record<string, unknown> | undefined;
  if (!from || typeof from !== "object") return null;
  const { company, title, base, bonus, equity } = from;
  const ok = (n: unknown): n is number => typeof n === "number" && Number.isFinite(n) && n >= 0;
  if (typeof company !== "string" || typeof title !== "string" || !ok(base) || !ok(bonus) || !ok(equity)) return null;
  return { company, title, base, bonus, equity };
}

// What a private company's typical package reads with its equity at the
// valuation the person entered, after the tab's move; null without one.
function atValuation(c: CompPackage, v: Valuation | undefined, d: number): number | null {
  if (!v?.grant_at || v.test_at == null) return null;
  return Math.round(c.base + c.bonus + c.equity * (v.test_at / v.grant_at) * (1 + d));
}

const draftOf = (offer: StoredOffer): OfferDraft => ({
  inputs: offer.inputs,
  answered: offer.answered,
  started_from: offer.started_from,
});

export function StockTrajectoryPanel() {
  const [pct, setPct] = useState(0); // stock price change, whole percent
  const [query, setQuery] = useState("");
  const { data, error, retry, refresh } = useAsyncResource<CompTrajectory>(api.compTrajectory, [], { keep: "stats/stock-trajectory" });
  // The split follows the source answering pay.
  useSourceSwitch(refresh);
  // The calculator works without these: they only fill in a company's rules.
  const { data: terms, error: termsError } = useAsyncResource<OfferTerms>(api.offerTerms, [], { keep: "stats/offer-terms" });

  // The person's offer, kept on this computer. Each write shows at once and
  // is sent in order: every route answers with the whole offer and valuations,
  // so each write orders against all the others. The answer to the latest
  // write is the one kept on screen.
  const { data: kept, error: keptError, retry: keptRetry } = useAsyncResource<OfferAnswers>(api.offer, []);
  const [written, setWritten] = useState<OfferAnswers | null>(null);
  const answers = written ?? kept ?? null;
  const offer = answers?.offer ?? null;
  const valuations: Record<string, StoredValuation> = answers?.valuations ?? NO_VALUATIONS;
  const [saveFailed, setSaveFailed] = useState(false);
  const [previous, setPrevious] = useState<StoredOffer | null>(null);
  // Counts the offers started from a package; each one remounts the calculator.
  const [starts, setStarts] = useState(0);
  const offerHeading = useRef<HTMLHeadingElement>(null);
  const { toast } = useToast();
  const focusOffer = useRef(false);
  const { exclusive } = useWriteQueue("stock-offer");
  const latest = useRef(0);
  // What the screen shows, read by each write: two writes in one step (a
  // valuation, then the answer it belongs to) build on each other, not on the
  // render before both.
  const shownNow = useRef<OfferAnswers | null>(answers);
  useLayoutEffect(() => {
    shownNow.current = answers;
  }, [answers]);

  // Writes the server did not keep, by what they wrote ("offer", or one
  // company's valuation). Each stays on screen over any later answer from the
  // server, and the failure stays said, until a write of the same thing is kept.
  const unsaved = useRef(new Map<string, (now: OfferAnswers) => OfferAnswers>());

  const write = useCallback((
    subject: string,
    change: (now: OfferAnswers) => OfferAnswers,
    send: () => Promise<OfferAnswers>,
  ) => {
    const n = ++latest.current;
    const shown = change(shownNow.current ?? NO_ANSWERS);
    shownNow.current = shown;
    setWritten(shown);
    exclusive([], send).then(
      (stored) => {
        unsaved.current.delete(subject);
        setSaveFailed(unsaved.current.size > 0);
        if (n !== latest.current) return;
        setWritten([...unsaved.current.values()].reduce((now, redo) => redo(now), stored));
      },
      () => {
        unsaved.current.set(subject, change);
        setSaveFailed(true);
      },
    );
  }, [exclusive]);
  const saveOffer = useCallback((draft: OfferDraft) => {
    write(
      "offer",
      (now) => ({ ...now, offer: { ...draft, saved_at: new Date().toISOString() } }),
      () => api.saveOffer(draft),
    );
  }, [write]);
  const clearOffer = () => write("offer", (now) => ({ ...now, offer: null }), () => api.clearOffer());
  const setValuation = (company: string, valuation: Valuation | null) => {
    write(
      `valuation:${company}`,
      (now) => {
        const next = { ...now.valuations };
        if (valuation) next[company] = { ...valuation, saved_at: new Date().toISOString() };
        else delete next[company];
        return { ...now, valuations: next };
      },
      () => (valuation ? api.saveValuation(company, valuation) : api.clearValuation(company)),
    );
  };
  const startFrom = useCallback((
    company: string,
    parts: { base: number; bonus: number; equity: number },
    listed: boolean,
    title?: string,
  ) => {
    // Until the kept offer is read, there is nothing to put back with Undo.
    if (!answers) return;
    setPrevious(answers.offer);
    setStarts((n) => n + 1);
    saveOffer({
      inputs: offerFromPackage(company, parts, terms ?? null, listed),
      answered: ["company"],
      started_from: { company, title: title ?? null },
    });
    focusOffer.current = true;
  }, [answers, terms, saveOffer]);
  // The started offer is a new view: its heading takes focus once drawn.
  useEffect(() => {
    if (!focusOffer.current || !offerHeading.current) return;
    focusOffer.current = false;
    offerHeading.current.scrollIntoView?.({ block: "start" });
    offerHeading.current.focus({ preventScroll: true });
  }, [answers]);

  // A role's detail page opens this tab with its figures to start from. They
  // fill the form once; the history entry then forgets them, so a reload or
  // Back does not fill it again over what the person typed since.
  const location = useLocation();
  const navigate = useNavigate();
  const roleOffer = useMemo(() => roleOfferFrom(location.state), [location.state]);
  const handedOff = useRef<string | null>(null);
  // Waits for the company rules, or for their failure: the form fills either way.
  const termsSettled = terms != null || termsError != null;
  useEffect(() => {
    if (!roleOffer || !termsSettled || !data || !answers || handedOff.current === location.key) return;
    handedOff.current = location.key;
    const listed = !data.private.some((c) => c.company === roleOffer.company);
    startFrom(roleOffer.company, roleOffer, listed, roleOffer.title);
    navigate({ pathname: location.pathname, search: location.search }, { replace: true, state: null });
  }, [roleOffer, termsSettled, data, answers, location.key, location.pathname, location.search, navigate, startFrom]);

  const d = pct / 100;

  const overall = data?.overall ?? null;
  const projected = useMemo(
    () => (overall ? projectTc(overall, d) : null),
    [overall, d],
  );

  if (!data) {
    return <ResourceLoadState error={error} loading={insightsStockTrajectoryPanelLoading()} failed={insightsStockTrajectoryPanelLoadFailed()} onRetry={retry} />;
  }

  const calculator = !answers ? (
    <div className="panel traj-offer">
      <ResourceLoadState error={keptError} loading={insightsOfferLoading()} failed={insightsOfferLoadFailed()} onRetry={keptRetry} />
    </div>
  ) : (
    <OfferCalculator
      // A started offer replaces the one on screen: a question open on the old
      // offer must not save its answers over the new one.
      key={starts}
      ref={offerHeading}
      terms={terms ?? null}
      offer={offer}
      valuations={valuations}
      suggested={[...data.public, ...data.private, ...data.choice].map((c) => c.company)}
      onSave={(draft) => {
        setPrevious(null);
        saveOffer(draft);
      }}
      onClear={() => {
        const cleared = offer;
        setPrevious(null);
        clearOffer();
        if (cleared) {
          toast({
            key: "stock-offer",
            text: insightsOfferCleared(),
            action: { label: insightsOfferUndo(), onClick: () => saveOffer(draftOf(cleared)) },
          });
        }
      }}
      onValuation={setValuation}
      saveFailed={saveFailed}
      previous={previous}
      onUndo={() => {
        if (previous) saveOffer(draftOf(previous));
        else clearOffer();
        setPrevious(null);
      }}
      pct={pct}
      onPct={setPct}
    />
  );
  const startButton = (company: string, parts: { base: number; bonus: number; equity: number }, listed: boolean) => (
    <td className="traj-offer-start">
      <Button variant="link" disabled={!answers} onClick={() => startFrom(company, parts, listed)} aria-label={insightsOfferStartAria({ company: companyName(company) })}>
        {insightsOfferStart()}
      </Button>
    </td>
  );

  // Nothing at all to show. A tab with only private companies, a
  // cash-or-equity company or roles left out still shows those.
  if (!overall && !data.private.length && !data.choice.length && !data.set_apart.length) {
    return (
      <>
      <div className="panel traj-companies">
        <h3>{insightsStockTrajectoryPanelStockTrajectory()}</h3>
        <div className="empty-hint">
          {insightsStockTrajectoryPanelNoOpenRolesAtPublic()}
        </div>
      </div>
      {calculator}
      </>
    );
  }

  // One search narrows every table; the chart above stays the whole picture.
  const publicRows = matchCompanies(data.public, query, companyName);
  const privateRows = matchCompanies(data.private, query, companyName);
  const choiceRows = matchCompanies(data.choice, query, companyName);
  const searching = query.trim() !== "";
  const companyCount = data.public.length + data.private.length + data.choice.length;
  const noMatch = searching && publicRows.length + privateRows.length + choiceRows.length === 0;

  // The column of private companies at the person's own valuation shows once
  // one of them has one.
  const valued = privateRows.some((c) => atValuation(c, valuations[c.company], 0) != null);
  const baseline = overall?.median_tc ?? 0;
  const delta = (projected ?? 0) - baseline;
  const sign = pct > 0 ? "up" : pct < 0 ? "down" : "flat";

  return (
    <>
      {overall && <InsightHero
        tab="trajectory"
        className="traj-cockpit"
        // At today's price the projection is today's figure again, so the
        // headline is what a move would act on: the equity share.
        figure={sign === "flat"
          ? insightsStockTrajectoryPanelEquityFigure({ share: fmtPct(overall.equity_pct) })
          : <Abbr
              short={insightsStockTrajectoryPanelProjectedTc({ projected: String(fmtComp(projected)) })}
              full={insightsStockTrajectoryPanelProjectedTcFull({ projected: String(fmtComp(projected)) })}
            />}
        line={<>{insightsStockTrajectoryPanelTypicalPackage({ equity: overall.sources.equity })}
            <InfoTip label={insightsStockTrajectoryPanelHowStockTrajectoryIsProjected()}>
              {insightsStockTrajectoryPanelStockMovesRePriceEquity()}
            </InfoTip></>}
        kpis={[
          { label: insightsStockTrajectoryPanelToday(), value: fmtComp(baseline), sub: <Abbr short={insightsStockTrajectoryPanelMedianTcTile()} full={insightsStockTrajectoryPanelMedianTcTileFull()} /> },
          {
            label: insightsStockTrajectoryPanelProjected(),
            value: fmtComp(projected),
            sub: insightsStockTrajectoryPanelAtPriceChange({ move: sign, pct }),
            tone: sign === "up" ? "good" : sign === "down" ? "bad" : undefined,
          },
          {
            label: insightsStockTrajectoryPanelChange(),
            value: delta === 0 ? "$0" : fmtSigned(delta),
            sub: insightsStockTrajectoryPanelVsToday(),
            tone: delta > 0 ? "good" : delta < 0 ? "bad" : undefined,
          },
          { label: insightsStockTrajectoryPanelEquityShare(), value: fmtPct(overall.equity_pct), sub: <Abbr short={insightsStockTrajectoryPanelOfTcAtRisk()} full={insightsStockTrajectoryPanelOfTcAtRiskFull()} /> },
        ]}
      >


          <label className="traj-slider-row">
            <span className="traj-slider-label">
              {insightsStockTrajectoryPanelStockPriceChange()}
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
              aria-label={insightsStockTrajectoryPanelStockPriceChangePercent()}
              onChange={(e) => setPct(Number(e.target.value))}
            />
          </label>
          <div className="traj-reset-row">
            {pct !== 0 && (
              <Button variant="link" onClick={() => setPct(0)}>
                {insightsStockTrajectoryPanelResetToToday()}
              </Button>
            )}
          </div>
      </InsightHero>}

      {data.public.length > 0 && (
        <div className="panel chart-panel chart-panel-wide">
          <div className="chart-panel-head">
            <div>
              <span className="eyebrow">{insightsStockTrajectoryPanelEquityShockwave()}</span>
              <h3>
                {insightsStockTrajectoryPanelWhoMovesWhenTheStock()}
                <InfoTip label={insightsStockTrajectoryPanelHowToReadEquitySensitivity()}>
                  {insightsStockTrajectoryPanelSensitivityExplained({ move: sign })}
                </InfoTip>
              </h3>
            </div>
            <span className={`chart-insight ${sign === "up" ? "good" : sign === "down" ? "bad" : ""}`}>
              {insightsStockTrajectoryPanelScenario({ move: sign, pct })}
            </span>
          </div>
          <TrajectoryShockChart companies={data.public} priceChange={pct === 0 ? SENSITIVITY : d} />
        </div>
      )}

      {calculator}

      {companyCount > 1 && (
        <div className="traj-search">
          <SearchField label={insightsDemandFindACompany()} placeholder={insightsDemandFindACompany()} value={query} onChange={setQuery} />
        </div>
      )}
      {noMatch && (
        <p className="empty-hint" role="status" data-testid="traj-no-match">{insightsStockTrajectoryPanelNoCompanyMatches({ query: query.trim() })}</p>
      )}

      {!(searching && publicRows.length === 0) && <div className="panel traj-companies" data-testid="traj-public">
        <h3>
          <Msg of={insightsStockTrajectoryPanelPublicCompanies} args={{ move: sign }} elems={{ pct: pct }} />
          <InfoTip label={insightsStockTrajectoryPanelAboutPublicCompanyProjections()}>
            {insightsStockTrajectoryPanelSortedByEquityExposureOnly()}
          </InfoTip>
        </h3>
        {data.public.length === 0 ? (
          <div className="empty-hint">{insightsStockTrajectoryPanelNoOpenRolesAtPublicYet()}</div>
        ) : (
          <table className="traj-table">
            <thead>
              <tr>
                <th scope="col">{insightsCommonCompany()}<SourceKey /></th>
                <th scope="col">{insightsStockTrajectoryPanelTicker()}</th>
                <th scope="col">{insightsStockTrajectoryPanelEquity()}</th>
                <th scope="col" className="num">{insightsStockTrajectoryPanelBase()}</th>
                <th scope="col" className="num">{insightsStockTrajectoryPanelBonus()}</th>
                <th scope="col" className="num">{insightsStockTrajectoryPanelEquityShare()}</th>
                <th scope="col" className="num">{insightsStockTrajectoryPanelToday()}</th>
                <th scope="col" className="num">{insightsStockTrajectoryPanelProjected()}</th>
                <th scope="col" className="num">{insightsStockTrajectoryPanelChange()}</th>
                <th scope="col"><span className="sr-only">{insightsOfferColumn()}</span></th>
              </tr>
            </thead>
            <tbody>
              {publicRows.map((c) => {
                const proj = projectTc(c, d);
                const ch = projectedDelta(c, d);
                // A listed company can still be immune to its own stock price:
                // one that pays a cash election has an equity share of 0.
                const immovable = c.equity_pct === 0;
                return (
                  <tr key={c.company} className={immovable ? "traj-immovable" : undefined}>
                    <th scope="row">{companyName(c.company)}</th>
                    <td className="traj-ticker">{c.ticker}</td>
                    <EquityTerms c={c} />
                    <CashParts c={c} />
                    <td className="num">{fmtComp(c.median_tc)}</td>
                    <td className="num">{fmtComp(proj)}</td>
                    <td className={`num ${ch > 0 ? "good" : ch < 0 ? "bad" : ""}`}>
                      {immovable ? (
                        <span title={insightsStockTrajectoryPanelPaidInCashUnaffectedBy()}>
                          {insightsStockTrajectoryPanelNoExposure()}
                        </span>
                      ) : ch === 0 ? (
                        "—"
                      ) : (
                        fmtSigned(ch)
                      )}
                    </td>
                    {startButton(c.company, c, true)}
                  </tr>
                );
              })}
            </tbody>
          </table>
        )}
      </div>}

      {privateRows.length > 0 && (
        <div className="panel traj-companies" data-testid="traj-private">
          <h3>
            {insightsStockTrajectoryPanelPrivateCompanies()}
            <InfoTip label={insightsStockTrajectoryPanelWhyPrivateCompaniesDoNot()}>
              {insightsStockTrajectoryPanelPreIpoEquityIsIlliquid()}
            </InfoTip>
          </h3>
          <table className="traj-table">
            <thead>
              <tr>
                <th scope="col">{insightsCommonCompany()}<SourceKey /></th>
                <th scope="col">{insightsStockTrajectoryPanelEquity()}</th>
                <th scope="col" className="num">{insightsStockTrajectoryPanelBase()}</th>
                <th scope="col" className="num">{insightsStockTrajectoryPanelBonus()}</th>
                <th scope="col" className="num">{insightsStockTrajectoryPanelEquityShare()}</th>
                <th scope="col" className="num"><Abbr short={insightsStockTrajectoryPanelMedianTc()} full={insightsStockTrajectoryPanelMedianTcFull()} /></th>
                {valued && (
                  <th scope="col" className="num">
                    {pct === 0
                      ? insightsOfferAtYourValuation()
                      : insightsOfferAtYourValuationMoved({ move: pct > 0 ? "up" : "down", pct })}
                  </th>
                )}
                <th scope="col"><span className="sr-only">{insightsOfferColumn()}</span></th>
              </tr>
            </thead>
            <tbody>
              {privateRows.map((c) => {
                const v = valuations[c.company];
                const at = atValuation(c, v, d);
                return (
                  <tr key={c.company}>
                    <th scope="row">{companyName(c.company)}</th>
                    <EquityTerms c={c} />
                    <CashParts c={c} />
                    <td className="num">{fmtComp(c.median_tc)}</td>
                    {valued && (
                      <td className="num traj-part">
                        {at == null || !v ? "—" : (
                          <>
                            {fmtComp(at)}
                            <span className="split-src split-src-entered" title={insightsOfferAtYourValuationFull({ date: calendarDay(v.saved_at) })}>
                              {insightsOfferEntered({ date: calendarDay(v.saved_at) })}
                            </span>
                          </>
                        )}
                      </td>
                    )}
                    {startButton(c.company, c, false)}
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}

      {choiceRows.length > 0 && (
        <div className="panel traj-companies" data-testid="traj-choice">
          <h3>{insightsStockTrajectoryPanelChoiceCompanies()}</h3>
          <p className="sub">{insightsStockTrajectoryPanelChoiceExplained()}</p>
          <table className="traj-table">
            <thead>
              <tr>
                <th scope="col">{insightsCommonCompany()}<SourceKey /></th>
                <th scope="col">{insightsStockTrajectoryPanelTicker()}</th>
                <th scope="col" className="num">{insightsSkillsViewRoles()}</th>
                <th scope="col" className="num"><Abbr short={insightsStockTrajectoryPanelMedianTc()} full={insightsStockTrajectoryPanelMedianTcFull()} /></th>
                <th scope="col"><span className="sr-only">{insightsOfferColumn()}</span></th>
              </tr>
            </thead>
            <tbody>
              {choiceRows.map((c) => (
                <tr key={c.company}>
                  <th scope="row">{companyName(c.company)}</th>
                  <td className="traj-ticker">{c.ticker ?? "—"}</td>
                  <td className="num">{c.count}</td>
                  <td className="num traj-part">
                    {fmtComp(c.median_tc)}
                    <PartSource source={c.total_source} />
                  </td>
                  {startButton(c.company, { base: c.median_tc, bonus: 0, equity: 0 }, c.ticker != null)}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {data.set_apart.length > 0 && (
        <p className="traj-left-out" data-testid="traj-left-out">
          {insightsStockTrajectoryPanelLeftOut({ count: data.set_apart.reduce((n, r) => n + r.count, 0) })}
          {/* The tooltip is phrasing content inside this paragraph, so the
              list is spans carrying list roles rather than ul and li. */}
          <InfoTip label={insightsStockTrajectoryPanelWhyLeftOut()}>
            <span className="traj-left-out-list" role="list">
              {data.set_apart.map((r) => (
                <span className="traj-left-out-item" role="listitem" key={r.reason}>
                  <span>{insightsStockTrajectoryPanelLeftOutReason({ reason: r.reason })}</span>
                  <span className="num">{r.count}</span>
                </span>
              ))}
            </span>
          </InfoTip>
        </p>
      )}
    </>
  );
}

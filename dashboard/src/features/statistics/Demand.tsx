import { number as copyNumber } from "../../copy/format";
import { useCallback, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { ResourceLoadState } from "../../ui/ResourceLoadState";
import { Demand as DemandData, HiringRegion, InsightsScope, api } from "../../api";
import { useAsyncResource } from "../../hooks/useAsyncResource";
import { LOC_LABEL, companyName } from "../../format";
import { InfoTip } from "../../ui/InfoTip";
import { Button, SearchField, Sheet } from "../../ui";
import { HiringCompaniesChart, type HiringBar } from "./charts/StatisticsCharts";
import { count, NOUN } from "../../copy/vocabulary";
import { matchCompanies, topCompanies } from "./hiring";
import { InsightHero, n } from "./InsightHero";
import {
  insightsCommonAllCompanies,
  insightsCommonByCompany,
  insightsCommonClosed,
  insightsCommonCompanies,
  insightsCommonNew,
  insightsCommonOpenRoles,
  insightsDemandARoleOpenInSeveral,
  insightsDemandAllCompaniesHiring,
  insightsDemandAllOf,
  insightsDemandAndMoreCountries,
  insightsDemandEachRoleCountsOnceHowever,
  insightsDemandEachRoleOnce,
  insightsDemandFindACompany,
  insightsDemandHiringNowTodayNewClosed,
  insightsDemandHowCompaniesAreCounted,
  insightsDemandHowRegionsAreCounted,
  insightsDemandLast2Days,
  insightsDemandLoadFailed,
  insightsDemandLoading,
  insightsDemandMoreHold,
  insightsDemandNameNoPlaceWeCan,
  insightsDemandNoOpenRolesAtThese,
  insightsDemandNoOpenRolesYet,
  insightsDemandOf,
  insightsDemandOpen,
  insightsDemandOpenRolesByCompany,
  insightsDemandOpenRolesByRegion,
  insightsDemandShowAll,
  insightsDemandToday,
  insightsDemandWithAnOpenRole,
  insightsOtherCompanies,
  insightsYourCompanies,
} from "../../copy/gen/insights";
import { Msg } from "../../ui/Msg";

/** Leaders shown per view; the rest fold into one row that still counts them. */
const TOP_COMPANIES = 15;
const TOP_COUNTRIES = 8;

const SIDE_LABEL: Record<InsightsScope["side"], string> = {
  get all() { return insightsCommonAllCompanies(); },
  get yours() { return insightsYourCompanies(); },
  get other() { return insightsOtherCompanies(); },
};

const place = (key: string) => LOC_LABEL[key] ?? key;

/** The Board narrowed to one company: where a company row on Hiring leads. */
const boardFor = (company: string) => `/?company=${encodeURIComponent(company)}`;

export function DemandView({ scope }: { scope?: InsightsScope }) {
  /* The error path is real, never a hardcoded `error={null}`: without it a
     failed /api/demand renders a spinner that never resolves, with no message
     and no retry, and the only escape is a page reload. The `loading-spinner`
     ratchet measures the markup and cannot see that. */
  const { data, error, retry } = useAsyncResource<DemandData>(() => api.demand(scope), [scope], { keep: "stats/demand" });
  const navigate = useNavigate();
  const openBoard = useCallback((company: string) => navigate(boardFor(company)), [navigate]);
  const side = scope?.side ?? "all";
  const [allOpen, setAllOpen] = useState(false);
  if (!data) {
    return (
      <div className="stats-view">
        <ResourceLoadState error={error} loading={insightsDemandLoading()} failed={insightsDemandLoadFailed()} onRetry={retry} />
      </div>
    );
  }

  const hiring = data.companies.filter((c) => c.open > 0).length;
  const { rows, rest, total } = topCompanies(data.companies, TOP_COMPANIES);
  const sideOpen = rows.reduce((n, c) => n + c.open, 0) + (rest?.open ?? 0);
  const bars: HiringBar[] = rows.map((c) => ({
    company: c.company,
    label: companyName(c.company),
    open: c.open,
    fresh: c.new_today,
    closed: c.closed_today,
  }));

  return (
    <>
      <InsightHero
        tab="demand"
        figure={insightsDemandOpen({ role: String(count(NOUN.role, data.open_total)) })}
        line={insightsDemandHiringNowTodayNewClosed({ company: String(count(NOUN.company, hiring)), new_today: String(n(data.new_today)), closed_today: String(n(data.closed_today)) })}
        kpis={[
          { label: insightsCommonOpenRoles(), value: n(data.open_total), sub: insightsDemandEachRoleOnce() },
          { label: insightsCommonCompanies(), value: n(hiring), sub: insightsDemandWithAnOpenRole() },
          { label: insightsCommonNew(), value: n(data.new_today), sub: insightsDemandLast2Days(), tone: "good" },
          { label: insightsCommonClosed(), value: n(data.closed_today), sub: insightsDemandToday() },
        ]}
      />

      <div className="panel chart-panel chart-panel-wide hiring-companies">
        <div className="chart-panel-head">
          <div>
            <span className="eyebrow">{insightsCommonByCompany()}</span>
            <h3>
              {insightsDemandOpenRolesByCompany()}
              <InfoTip label={insightsDemandHowCompaniesAreCounted()}>
                {insightsDemandEachRoleCountsOnceHowever()}
              </InfoTip>
            </h3>
          </div>
          <span className="chart-insight">{SIDE_LABEL[side]}</span>
        </div>
        {bars.length > 0 ? (
          <HiringCompaniesChart bars={bars} onPick={openBoard} />
        ) : (
          <p className="hiring-note">{insightsDemandNoOpenRolesAtThese()}</p>
        )}
        {/* The tail is a sentence, not a bar: drawn, its sum would flatten
            the leaders beside it. The full list shows even without a tail:
            a chart bar takes no keyboard focus, so the list's links are the
            way to every company's roles. */}
        {total > 0 && (
          <div className="hiring-foot">
            {rest && (
              <p className="hiring-note">
                {insightsDemandMoreHold({
                  companies: count(NOUN.company, rest.companies),
                  roles: count(NOUN.role, rest.open),
                  share: sideOpen > 0 ? "known" : "none",
                  percent: sideOpen > 0 ? Math.round((rest.open / sideOpen) * 100) : 0,
                })}
              </p>
            )}
            <Button variant="link" onClick={() => setAllOpen(true)}>
              <Msg of={insightsDemandShowAll} elems={{ company: count(NOUN.company, total) }} />
            </Button>
          </div>
        )}
      </div>
      <AllCompanies data={data} title={SIDE_LABEL[side]} isOpen={allOpen} onClose={() => setAllOpen(false)} />

      <RegionsPanel regions={data.regions} unplaced={data.unplaced} />
    </>
  );
}

function RegionsPanel({ regions, unplaced }: { regions: HiringRegion[]; unplaced: number }) {
  const [expanded, setExpanded] = useState<string | null>(null);
  const max = Math.max(1, ...regions.map((r) => r.open));
  return (
    <div className="panel hiring-regions">
      <h3>
        {insightsDemandOpenRolesByRegion()}
        <InfoTip label={insightsDemandHowRegionsAreCounted()}>
          {insightsDemandARoleOpenInSeveral()}
        </InfoTip>
      </h3>
      {regions.length === 0 && <div style={{ color: "var(--app-text-faint)" }}>{insightsDemandNoOpenRolesYet()}</div>}
      {regions.map((region) => {
        const isOpen = expanded === region.key;
        const countries = region.countries.slice(0, TOP_COUNTRIES);
        const more = region.countries.length - countries.length;
        const countryMax = Math.max(1, ...countries.map((c) => c.open), region.region_wide);
        return (
          <div className="hiring-region" key={region.key}>
            <div className="bar-row">
              <span>
                <Button
                  variant="link"
                  aria-expanded={isOpen}
                  onClick={() => setExpanded(isOpen ? null : region.key)}
                >
                  {place(region.key)}
                </Button>
              </span>
              <div className="bar-track">
                <div className="bar-fill" style={{ width: `${(region.open / max) * 100}%` }} />
              </div>
              <span className="val">{copyNumber(region.open)}</span>
            </div>
            {isOpen && (
              <div className="hiring-countries">
                {countries.map((c) => (
                  <div className="bar-row" key={c.key}>
                    <span>{place(c.key)}</span>
                    <div className="bar-track">
                      <div className="bar-fill" style={{ width: `${(c.open / countryMax) * 100}%` }} />
                    </div>
                    <span className="val">{copyNumber(c.open)}</span>
                  </div>
                ))}
                {region.region_wide > 0 && (
                  <div className="bar-row hiring-region-wide">
                    <span><Msg of={insightsDemandAllOf} elems={{ region: place(region.key) }} /></span>
                    <div className="bar-track">
                      <div className="bar-fill" style={{ width: `${(region.region_wide / countryMax) * 100}%` }} />
                    </div>
                    <span className="val">{copyNumber(region.region_wide)}</span>
                  </div>
                )}
                {more > 0 && <p className="hiring-note">{insightsDemandAndMoreCountries({ more })}</p>}
              </div>
            )}
          </div>
        );
      })}
      {unplaced > 0 && (
        <p className="hiring-note">
          <Msg of={insightsDemandNameNoPlaceWeCan} elems={{ role: count(NOUN.role, unplaced) }} />
        </p>
      )}
    </div>
  );
}

function AllCompanies({
  data,
  title,
  isOpen,
  onClose,
}: {
  data: DemandData;
  title: string;
  isOpen: boolean;
  onClose: () => void;
}) {
  const [query, setQuery] = useState("");
  const { rows } = topCompanies(data.companies, Number.MAX_SAFE_INTEGER);
  const shown = matchCompanies(rows, query, companyName);
  const max = Math.max(1, ...rows.map((c) => c.open));
  return (
    <Sheet isOpen={isOpen} onClose={onClose} label={insightsDemandAllCompaniesHiring()} className="hiring-sheet app-overlay">
      {/* A portal leaves the screen's design-system root, so the sheet names
          its own, as Cover does: the bar rows are styled under it. */}
      <div className="hiring-sheet-body" data-design-system="app">
      <div className="hiring-sheet-head">
        <h3>{title}</h3>
        <SearchField label={insightsDemandFindACompany()} value={query} onChange={setQuery} size="sm" />
        <span className="hiring-note" data-selection="chrome">
          <Msg of={insightsDemandOf} elems={{ shown: copyNumber(shown.length), companies: count(NOUN.company, rows.length) }} />
        </span>
      </div>
      <div className="hiring-sheet-list">
        {shown.map((c) => (
          <div className="bar-row" key={c.company}>
            <span><Link to={boardFor(c.company)}>{companyName(c.company)}</Link></span>
            <div className="bar-track">
              <div className="bar-fill" style={{ width: `${(c.open / max) * 100}%` }} />
            </div>
            <span className="val">{copyNumber(c.open)}</span>
          </div>
        ))}
      </div>
      </div>
    </Sheet>
  );
}

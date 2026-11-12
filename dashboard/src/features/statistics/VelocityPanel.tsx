import { InsightsScope, VelocityStats, api } from "../../api";
import { useAsyncResource } from "../../hooks/useAsyncResource";
import { companyName } from "../../format";
import { InfoTip } from "../../ui/InfoTip";
import { ResourceLoadState } from "../../ui/ResourceLoadState";
import { InsightHero, n } from "./InsightHero";
import {
  insightsCommonClosed,
  insightsCommonCompany,
  insightsCommonOpened,
  insightsVelocityPanelAgeOfOpenRoles,
  insightsVelocityPanelAgeUnknown,
  insightsVelocityPanelCompanies,
  insightsVelocityPanelCountedFromFirstListed,
  insightsVelocityPanelFromTheFirstScanThat,
  insightsVelocityPanelHowLongPostingsStayUp,
  insightsVelocityPanelLoadFailed,
  insightsVelocityPanelLoading,
  insightsVelocityPanelMedianAge,
  insightsVelocityPanelMedianTimePosted,
  insightsVelocityPanelMoreAlreadyListedWhenFound,
  insightsVelocityPanelOpen,
  insightsVelocityPanelOpenCount,
  insightsVelocityPanelOpenedCount,
  insightsVelocityPanelThisBuildsUpAsRoles,
  insightsVelocityPanelTimePosted,
  insightsVelocityPanelTimePostedUnknown,
  insightsVelocityPanelWhatAlreadyListedMeans,
  insightsVelocityPanelWhatUnknownMeans,
  insightsVelocityPanelWhyAlreadyListed,
  insightsVelocityPanelWhyAStartIsUnknown,
  insightsVelocityPanelWhatTimePostedMeasures,
} from "../../copy/gen/insights";
import { Msg } from "../../ui/Msg";
import { agingBandName } from "./names";
import { periodLabel } from "./period";

const days = (value: number | null) => (value == null ? "" : `${Math.round(value)}d`);

export function VelocityPanel({ days: period, scope }: { days: number; scope?: InsightsScope }) {
  const { data, error, retry } = useAsyncResource<VelocityStats>(
    () => api.velocity(period, scope),
    [period, scope],
    { keep: "stats/velocity" },
  );

  if (!data) return <ResourceLoadState error={error} loading={insightsVelocityPanelLoading()} failed={insightsVelocityPanelLoadFailed()} onRetry={retry} />;

  const k = data.kpis;
  const window = periodLabel(period, data.since);
  const openMax = Math.max(1, ...data.by_company.map((c) => c.open));
  const thinPosted = k.median_observed_listing_duration_days == null;
  // A company's time posted needs 5 closed roles with a known start; until
  // one has them, the column would be blank on every row.
  const showPosted = data.by_company.some((c) => c.median_observed_listing_duration_days != null);

  return (
    <>
      <InsightHero
        tab="velocity"
        figure={insightsVelocityPanelOpenedCount({ opened: n(k.opened) })}
        line={
          <>
            {[
              insightsVelocityPanelOpenCount({ open_total: n(k.open_total) }),
              k.median_days_open != null && insightsVelocityPanelMedianAge({ median_days_open: String(days(k.median_days_open)) }),
              k.median_observed_listing_duration_days != null &&
                insightsVelocityPanelMedianTimePosted({ median_observed_listing_duration_days: String(days(k.median_observed_listing_duration_days)) }),
              k.already_listed > 0 && insightsVelocityPanelMoreAlreadyListedWhenFound({ already_listed: String(n(k.already_listed)) }),
            ]
              .filter(Boolean)
              .join(" · ")}
            {k.already_listed > 0 && (
              <InfoTip label={insightsVelocityPanelWhatAlreadyListedMeans()}>{insightsVelocityPanelWhyAlreadyListed()}</InfoTip>
            )}
          </>
        }
        kpis={[
          { label: insightsCommonOpened(), value: n(k.opened), sub: window, tone: "good" },
          { label: insightsCommonClosed(), value: n(k.closed), sub: window },
        ]}
      />

      {/* One table for everything keyed by company: separate panels for
          activity, time posted and open roles would list the same companies
          three times, at three heights. */}
      <div className="panel vel-companies">
        <h3><Msg of={insightsVelocityPanelCompanies} elems={{ window: window }} /></h3>
        <table className="data-table vel-table">
          <thead>
            <tr>
              <th>{insightsCommonCompany()}</th>
              <th className="num vel-open-col">{insightsVelocityPanelOpen()}</th>
              <th className="num">{insightsCommonOpened()}</th>
              <th className="num">{insightsCommonClosed()}</th>
              {showPosted && (
                <th className="num">
                  {insightsVelocityPanelTimePosted()}
                  <InfoTip label={insightsVelocityPanelWhatTimePostedMeasures()}>
                    {insightsVelocityPanelFromTheFirstScanThat()}
                  </InfoTip>
                </th>
              )}
            </tr>
          </thead>
          <tbody>
            {data.by_company.map((c) => (
              <tr key={c.company}>
                <td>{companyName(c.company)}</td>
                <td className="num vel-open-col">
                  <span className="vel-open">
                    <span className="bar-track">
                      <span className="bar-fill" style={{ width: `${(c.open / openMax) * 100}%` }} />
                    </span>
                    <span>{n(c.open)}</span>
                  </span>
                </td>
                <td className="num pos">{n(c.opened)}</td>
                <td className="num">{n(c.closed)}</td>
                {showPosted && (
                  <td className="num">{c.median_observed_listing_duration_days != null ? days(c.median_observed_listing_duration_days) : ""}</td>
                )}
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div className="demand-grid vel-distributions">
        <div className="panel">
          <h3>{insightsVelocityPanelAgeOfOpenRoles()}</h3>
          <Bands bands={data.aging} />
          <Basis lead={insightsVelocityPanelCountedFromFirstListed()} unknown={k.age_unknown} label={insightsVelocityPanelAgeUnknown} />
        </div>

        <div className="panel">
          <h3>{insightsVelocityPanelHowLongPostingsStayUp()}</h3>
          {thinPosted ? (
            <p className="vel-basis">
              {insightsVelocityPanelThisBuildsUpAsRoles({ closed_sample: k.closed_sample })}
            </p>
          ) : (
            <Bands bands={data.posted} />
          )}
          <Basis unknown={k.closed_unknown} label={insightsVelocityPanelTimePostedUnknown} />
        </div>
      </div>
    </>
  );
}

/* The plain line under a chart: which clock it counts by, and the roles whose
 * start is unknown, which sit beside the bands, never in one, so the bands and
 * this count add up to every role the panel describes. */
function Basis({
  lead,
  unknown,
  label,
}: {
  lead?: string;
  unknown: number;
  label: (args: { count: string }) => string;
}) {
  if (!lead && unknown <= 0) return null;
  return (
    <p className="vel-basis">
      {lead}
      {lead && unknown > 0 && " "}
      {unknown > 0 && (
        <>
          {label({ count: n(unknown) })}
          <InfoTip label={insightsVelocityPanelWhatUnknownMeans()}>{insightsVelocityPanelWhyAStartIsUnknown()}</InfoTip>
        </>
      )}
    </p>
  );
}

function Bands({ bands }: { bands: VelocityStats["aging"] }) {
  const max = Math.max(1, ...bands.map((b) => b.count));
  return (
    <>
      {bands.map((b) => (
        <div className="bar-row" key={b.lo}>
          <span>{agingBandName(b.lo)}</span>
          <div className="bar-track">
            <div className="bar-fill" style={{ width: `${(b.count / max) * 100}%` }} />
          </div>
          <span className="val">{n(b.count)}</span>
        </div>
      ))}
    </>
  );
}

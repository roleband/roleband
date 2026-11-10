import { InsightsScope, StatisticsOverview, api } from "../../api";
import { useAsyncResource } from "../../hooks/useAsyncResource";
import { companyName } from "../../format";
import { listedFor } from "./ageCopy";
import { OverviewSignalChart } from "./charts/StatisticsCharts";
import { InfoTip } from "../../ui/InfoTip";
import { ResourceLoadState } from "../../ui/ResourceLoadState";
import { JobLinkRow } from "../../patterns/jobs/JobLinkRow";
import { InsightHero, n } from "./InsightHero";
import {
  insightsCommonClosed,
  insightsCommonLastDaysOrAllTime,
  insightsCommonNew,
  insightsCommonOpenRoles,
  insightsOverviewPanelAboutTheDemandField,
  insightsOverviewPanelCompanies,
  insightsOverviewPanelLeadsRoles,
  insightsOverviewPanelLoadFailed,
  insightsOverviewPanelLoading,
  insightsOverviewPanelMostNamedSkills,
  insightsOverviewPanelNoOpenRoles,
  insightsOverviewPanelOpenTheLongest,
  insightsOverviewPanelOpenedClosed,
  insightsOverviewPanelTheRolesAdvertisedLongestThat,
  insightsOverviewPanelTheSkillsOpenRolesName,
  insightsOverviewPanelWhatIsPullingTheMarket,
  insightsOverviewPanelWhatOpenTheLongestMeans,
} from "../../copy/gen/insights";
import { Msg } from "../../ui/Msg";
import { skillName } from "../../copy/vocab";
import { overviewBrief } from "./names";

export function OverviewPanel({
  days,
  scope,
  onOpen,
  advanced = false,
}: {
  days: number;
  scope?: InsightsScope;
  onOpen: (id: number, companySlug?: string | null) => void;
  /** The advanced view adds the roles open longest. */
  advanced?: boolean;
}) {
  const { data, error, retry } = useAsyncResource<StatisticsOverview>(
    () => api.statisticsOverview(days, scope),
    [days, scope],
    { keep: "stats/overview" },
  );

  if (!data) return <ResourceLoadState error={error} loading={insightsOverviewPanelLoading()} failed={insightsOverviewPanelLoadFailed()} onRetry={retry} />;

  const window = insightsCommonLastDaysOrAllTime({ period: days <= 0 ? "all" : "days", days });
  const k = data.kpis;

  return (
    <>
      <InsightHero
        tab="overview"
        figure={insightsOverviewPanelOpenedClosed({ new_count: String(n(k.new_count)), closed_count: String(n(k.closed_count)) })}
        line={overviewBrief(data)}
        kpis={[
          { label: insightsCommonOpenRoles(), value: n(k.open_total), sub: insightsOverviewPanelCompanies({ companies: String(n(k.companies)) }) },
          { label: insightsCommonNew(), value: n(k.new_count), sub: window, tone: "good" },
          { label: insightsCommonClosed(), value: n(k.closed_count), sub: window },
        ]}
      />

      {data.top_skills.length > 0 && (
        <div className="panel chart-panel chart-panel-wide">
          <div className="chart-panel-head">
            <div>
              <span className="eyebrow">{insightsOverviewPanelMostNamedSkills()}</span>
              <h3>
                {insightsOverviewPanelWhatIsPullingTheMarket()}
                <InfoTip label={insightsOverviewPanelAboutTheDemandField()}>
                  {insightsOverviewPanelTheSkillsOpenRolesName()}
                </InfoTip>
              </h3>
            </div>
            <span className="chart-insight"><Msg of={insightsOverviewPanelLeadsRoles} elems={{ display: skillName(data.top_skills[0].term), job_count: n(data.top_skills[0].job_count) }} /></span>
          </div>
          <OverviewSignalChart skills={data.top_skills} />
        </div>
      )}

      {/* Three rows, and no skills list: it would draw the chart above a
          second time. */}
      {advanced && <div className="demand-grid">
        <div className="panel">
          <h3>
            {insightsOverviewPanelOpenTheLongest()}
            <InfoTip label={insightsOverviewPanelWhatOpenTheLongestMeans()}>
              {insightsOverviewPanelTheRolesAdvertisedLongestThat()}
            </InfoTip>
          </h3>
          {data.longest_open.length === 0 && <p className="hiring-note">{insightsOverviewPanelNoOpenRoles()}</p>}
          {data.longest_open.map((job) => (
            <JobLinkRow className="mini-job" key={job.id} jobId={job.id} company={job.company} onOpen={onOpen}>
              <div>
                <div className="mj-title" data-selection="content">{job.title}</div>
                <div className="mj-meta">
                  {[companyName(job.company), listedFor(job.listed_days)].filter(Boolean).join(" · ")}
                </div>
              </div>
            </JobLinkRow>
          ))}
        </div>
      </div>}
    </>
  );
}

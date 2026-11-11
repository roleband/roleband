import { InsightsScope, StatisticsOverview, api } from "../../api";
import { useAsyncResource } from "../../hooks/useAsyncResource";
import { OverviewSignalChart } from "./charts/StatisticsCharts";
import { InfoTip } from "../../ui/InfoTip";
import { ResourceLoadState } from "../../ui/ResourceLoadState";
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
  insightsOverviewPanelOpenedClosed,
  insightsOverviewPanelTheSkillsOpenRolesName,
  insightsOverviewPanelWhatIsPullingTheMarket,
} from "../../copy/gen/insights";
import { Msg } from "../../ui/Msg";
import { skillName } from "../../copy/vocab";
import { overviewBrief } from "./names";

export function OverviewPanel({ days, scope }: { days: number; scope?: InsightsScope }) {
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
    </>
  );
}

import { number as copyNumber } from "../../copy/format";
import { useMemo, useState } from "react";
import { DisclosureRates } from "../../api";
import { EChart } from "../../ui/EChart";
import {
  buildDisclosureRateOption,
  disclosureRateRows,
  disclosureRateSummary,
  pct,
  unratedCount,
} from "./charts/disclosure";
import { InfoTip, Segmented } from "../../ui";
import {
  insightsCommonByLevel,
  insightsCommonByCompany,
  insightsDisclosurePanelDisclosureBreakdown,
  insightsDisclosurePanelHowTheDisclosureRateIs,
  insightsDisclosurePanelNoOpenRolesHaveBeen,
  insightsDisclosurePanelOfCheckedRolesStatePay,
  insightsDisclosurePanelOfOpenRolesHaveNot,
  insightsDisclosurePanelPayTransparency,
  insightsDisclosurePanelShareOfOpenRolesStating,
  insightsDisclosurePanelTheShareOfOpenRoles,
  insightsDisclosurePanelWhoStatesPay,
} from "../../copy/gen/insights";
import { Msg } from "../../ui/Msg";

/**
 * Pay transparency: the disclosure RATE, by company or level. Sits beside the
 * posted-ranges chart, which shows what employers print but never how many of
 * them print anything.
 *
 * The denominator is stated everywhere it is used. `open - checked` roles are
 * queued for the disclosure pass, not silent employers, so they are excluded from
 * the rate and reported separately — the panel must never let a scraping backlog
 * read as an employer choice.
 */

const GROUPS: { key: "company" | "level"; label: string }[] = [
  { key: "company", get label() { return insightsCommonByCompany(); } },
  { key: "level", get label() { return insightsCommonByLevel(); } },
];

function BacklogNote({ open, checked }: { open: number; checked: number }) {
  const pending = open - checked;
  if (pending <= 0) return null;
  return (
    <div className="sub">
      <Msg of={insightsDisclosurePanelOfOpenRolesHaveNot} elems={{ pending: copyNumber(pending), open: copyNumber(open) }} />
    </div>
  );
}

export function DisclosureRatePanel({
  rates,
  initialGroup = "company",
}: {
  rates: DisclosureRates;
  /** The grouping the panel opens on. */
  initialGroup?: "company" | "level";
}) {
  const [group, setGroup] = useState<"company" | "level">(initialGroup);
  const rows = useMemo(() => disclosureRateRows(rates, group), [rates, group]);
  const unrated = unratedCount(rates, group);
  const option = useMemo(() => buildDisclosureRateOption(rows), [rows]);
  const o = rates.overall;

  return (
    <div className="panel chart-panel chart-panel-wide">
      <div className="chart-panel-head">
        <div>
          <span className="eyebrow">{insightsDisclosurePanelPayTransparency()}</span>
          <h3>
            {insightsDisclosurePanelWhoStatesPay()}
            <InfoTip label={insightsDisclosurePanelHowTheDisclosureRateIs()}>
              {insightsDisclosurePanelTheShareOfOpenRoles()}
            </InfoTip>
          </h3>
          <BacklogNote open={o.open} checked={o.checked} />
        </div>
        <div className="chart-head-controls">
          {o.rate !== null && (
            <span className="chart-insight">
              <Msg of={insightsDisclosurePanelOfCheckedRolesStatePay} elems={{ rate: pct(o.rate), checked: copyNumber(o.checked) }} />
            </span>
          )}
          {rows.length > 0 && (
            <Segmented
              className="chart-seg"
              label={insightsDisclosurePanelDisclosureBreakdown()}
              value={group}
              onChange={setGroup}
              options={GROUPS.map((g) => ({ value: g.key, label: g.label }))}
            />
          )}
        </div>
      </div>

      {rows.length === 0 ? (
        <div className="empty-hint">{insightsDisclosurePanelNoOpenRolesHaveBeen()}</div>
      ) : (
        <>
          <EChart
            ariaLabel={insightsDisclosurePanelShareOfOpenRolesStating({ group })}
            className="chart-disclosure-rate"
            height={Math.max(180, 40 + rows.length * 26)}
            option={option}
            summary={disclosureRateSummary(rows, unrated)}
          />
        </>
      )}
    </div>
  );
}

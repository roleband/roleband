import { useMemo, useState } from "react";
import { Link } from "react-router-dom";
import type { PayDiscipline, PayTable as PayTableData, PayTableEquity, PayTableRow } from "../../api";
import { companyName, fmtCompIn } from "../../format";
import { country as countryName, number as copyNumber } from "../../copy/format";
import { roleName, skillName } from "../../copy/vocab";
import { Badge, Button, Content, FilterSelect, InfoTip, SearchField } from "../../ui";
import { Abbr } from "../../ui/Abbr";
import { levelLabel } from "./charts/levelLabel";
import { matchCompanies } from "./hiring";
import { payRanges, silentBelow } from "./charts/payTable";
import {
  insightsCommonOpenRoles,
  insightsStockTrajectoryPanelEquity,
  insightsDemandFindACompany,
  insightsDemandShowAll,
  insightsPayDisciplineCounts,
  insightsPayDisciplineHeading,
  insightsPayDisciplineNote,
  insightsPayDisciplineOneEmployer,
  insightsPayDisciplineTooFew,
  insightsPayDisciplineYours,
  insightsPayTableAbout,
  insightsPayTableAnySkill,
  insightsPayTableEmpty,
  insightsPayTableEstBase,
  insightsPayTableEstBaseFrom,
  insightsPayTableEstBaseFull,
  insightsPayTableEstTc,
  insightsPayTableEstTcFrom,
  insightsPayTableEstTcFromLevel,
  insightsPayTableEstTcFull,
  insightsPayTableEstimate,
  insightsPayTableEstimatesUs,
  insightsPayTableFollowedAsSet,
  insightsPayTableHeading,
  insightsPayTableHeadingSkill,
  insightsPayTableHowRead,
  insightsPayTableMoreSilent,
  insightsPayTableNoRange,
  insightsPayTableNotPlaced,
  insightsPayTableNotYearly,
  insightsPayTablePlacedByPay,
  insightsPayTablePosted,
  insightsPayTableRanges,
  insightsPayTableRangesRead,
  insightsPayTableSeveralCountries,
  insightsPayTableSkillEmpty,
  insightsPayTableSomeRoles,
  insightsPayTableTotal,
  insightsPayTableUnclear,
  insightsPayTableUnread,
  insightsStockTrajectoryPanelCashElection,
  insightsStockTrajectoryPanelNoEquity,
  insightsStockTrajectoryPanelOptions,
  insightsStockTrajectoryPanelRsus,
  insightsStockTrajectoryPanelVests,
  insightsCommonCompany,
} from "../../copy/gen/insights";
import "../../patterns/figure-table.css";

/* One row per company hiring at the picked level in the picked country, the
   posted range first. The range is the authority; an estimate shows only
   where a company posts none, and never sets the order (docs/pay.md, "Posted
   pay on Insights"). Equity names what the employer states, never a share we
   estimate. */

/** Rows shown before Show all. */
const ROWS = 20;

const REASON: Record<string, () => string> = {
  none: insightsPayTableNoRange,
  total: insightsPayTableTotal,
  unclear: insightsPayTableUnclear,
  several_countries: insightsPayTableSeveralCountries,
  not_yearly: insightsPayTableNotYearly,
  placed_by_pay: insightsPayTablePlacedByPay,
  unread: insightsPayTableUnread,
};

const VEHICLE: Record<string, () => string> = {
  rsu: insightsStockTrajectoryPanelRsus,
  options: insightsStockTrajectoryPanelOptions,
  none: insightsStockTrajectoryPanelNoEquity,
  cash_election: insightsStockTrajectoryPanelCashElection,
};

/** The equity a company states: its type, how it vests, or its own rule of
 *  none. A dash where it states nothing; never an estimated share. */
function Equity({ equity }: { equity: PayTableEquity | null }) {
  const rule = equity?.rule === "none"
    ? insightsStockTrajectoryPanelNoEquity()
    : equity?.rule === "employee_election"
      ? insightsStockTrajectoryPanelCashElection()
      : null;
  const vehicle = equity?.vehicle ? VEHICLE[equity.vehicle]?.() ?? equity.vehicle : null;
  const words = rule ?? vehicle;
  return (
    <td className="traj-vehicle">
      {words}
      {equity?.vesting && <span className="traj-vesting">{insightsStockTrajectoryPanelVests({ schedule: equity.vesting })}</span>}
      {!words && !equity?.vesting && "—"}
    </td>
  );
}

/** A company's posted range, the ranges behind it, and the strip that draws
 *  them against the level's typical range. With no range, why there is none. */
function Posted({ row, currency, scale }: { row: PayTableRow; currency: string; scale: { min: number; max: number } | null }) {
  const money = (x: number) => fmtCompIn(x, row.currency ?? currency);
  if (row.low == null || row.high == null) {
    return <td className="pay-table-posted dim">{(row.reason && REASON[row.reason]?.()) ?? insightsPayTableNoRange()}</td>;
  }
  const spans = scale && scale.max > scale.min
    ? row.ranges.map((r) => ({
        key: `${r.low}-${r.high}`,
        left: `${((r.low - scale.min) / (scale.max - scale.min)) * 100}%`,
        width: `${Math.max(0.6, ((r.high - r.low) / (scale.max - scale.min)) * 100)}%`,
      }))
    : [];
  return (
    <td className="pay-table-posted">
      <span className="pay-table-figure">{money(row.low)}–{money(row.high)}</span>
      {row.ranges.length > 1 && (
        <span className="comp-n">{insightsPayTableRanges({ count: row.ranges.length })}</span>
      )}
      {row.posting < row.checked && (
        <span className="comp-n">{insightsPayTableSomeRoles({ posting: row.posting, roles: row.checked })}</span>
      )}
      {spans.length > 0 && (
        <span
          className="pay-table-strip"
          role="img"
          aria-label={insightsPayTableRangesRead({
            company: companyName(row.company),
            ranges: payRanges(row, (x) => money(x)),
          })}
        >
          {spans.map((s) => (
            <span key={s.key} className="pay-table-span" style={{ left: s.left, width: s.width }} />
          ))}
        </span>
      )}
    </td>
  );
}

/** The estimate, where one answers: a base for this level and discipline, or a
 *  total read at one rung. Each says which it is and where it comes from. */
function Estimate({ row, level }: { row: PayTableRow; level: string }) {
  const base = row.estimate_base;
  const total = row.estimate_total;
  if (!base && !total) return <td className="pay-table-estimate dim">—</td>;
  const figure = base ?? total!;
  const money = (x: number) => fmtCompIn(x, "USD");
  const source = base
    ? insightsPayTableEstBaseFrom({
        level: levelLabel(level),
        disciplines: base.families.map(roleName).join(", "),
      })
    : total!.rung
      ? insightsPayTableEstTcFrom({ rung: total!.rung })
      : insightsPayTableEstTcFromLevel({ level: levelLabel(level) });
  return (
    <td className="pay-table-estimate">
      <span className="pay-table-figure">
        {figure.low === figure.high ? money(figure.low) : `${money(figure.low)}–${money(figure.high)}`}
      </span>
      <InfoTip label={base ? insightsPayTableEstBaseFull() : insightsPayTableEstTcFull()}>{source}</InfoTip>
      <span className="pay-table-kind">
        <Abbr
          short={base ? insightsPayTableEstBase() : insightsPayTableEstTc()}
          full={base ? insightsPayTableEstBaseFull() : insightsPayTableEstTcFull()}
        />
      </span>
    </td>
  );
}

/** Posted pay per discipline within the level: every discipline at once, the
 *  picked one tagged, and those withheld named in one line with the rule each
 *  misses. */
function PayDisciplines({ data }: { data: PayTableData }) {
  const { disciplines } = data.by_discipline;
  const shown = disciplines.filter((d) => d.withheld === null);
  const withheld = (rule: PayDiscipline["withheld"]) =>
    disciplines.filter((d) => d.withheld === rule).map((d) => roleName(d.family)).join(", ");
  const tooFew = withheld("too_few");
  const oneEmployer = withheld("one_employer");
  const heading = insightsPayDisciplineHeading({
    level: levelLabel(data.level_band),
    country: countryName(data.country),
  });
  if (disciplines.length === 0) return null;
  const money = (x: number) => fmtCompIn(x, data.currency ?? "USD");
  return (
    <section className="panel" aria-label={heading}>
      <h3>{heading}</h3>
      <ol className="posted-levels">
        {shown.map((d) => (
          <li key={d.family} className="posted-level">
            <span className="posted-level-name">
              <strong>{roleName(d.family)}</strong>
              {d.picked && <Badge tone="accent" variant="tint" size="sm">{insightsPayDisciplineYours()}</Badge>}
            </span>
            <span className="posted-level-value">{money(d.low!)}–{money(d.high!)}</span>
            <span className="comp-n">{insightsPayDisciplineCounts({ ranges: d.ranges, employers: d.employers })}</span>
          </li>
        ))}
      </ol>
      {tooFew && <p className="hiring-note">{insightsPayDisciplineTooFew({ families: tooFew })}</p>}
      {oneEmployer && <p className="hiring-note">{insightsPayDisciplineOneEmployer({ families: oneEmployer })}</p>}
      <p className="hiring-note">{insightsPayDisciplineNote()}</p>
    </section>
  );
}

export function PayTable({
  data,
  skill,
  onSkill,
  advanced = false,
}: {
  data: PayTableData;
  /** The skill the table is narrowed to, kept in the link. */
  skill: string | null;
  onSkill: (skill: string | null) => void;
  /** The advanced view adds posted pay by discipline. */
  advanced?: boolean;
}) {
  const [query, setQuery] = useState("");
  const [all, setAll] = useState(false);
  const place = countryName(data.country);
  const level = levelLabel(data.level_band);
  const heading = skill
    ? insightsPayTableHeadingSkill({ level, country: place, skill: skillName(skill) })
    : insightsPayTableHeading({ level, country: place });

  // The find box searches every row, not only the ones in view.
  const matched = useMemo(() => matchCompanies(data.rows, query, companyName), [data.rows, query]);
  const rows = all || query.trim() ? matched : matched.slice(0, ROWS);
  const hiddenSilent = silentBelow(matched, rows.length);
  // One axis for the whole table, so two companies' strips compare.
  const scale = useMemo(() => {
    const ends = data.rows.flatMap((r) => (r.other_currency ? [] : r.ranges.flatMap((x) => [x.low, x.high])));
    return ends.length > 1 ? { min: Math.min(...ends), max: Math.max(...ends) } : null;
  }, [data.rows]);
  // The picked skill is always among the options, even when the table's own
  // roles no longer offer it: it is how the person returns to every skill.
  const offered = data.skills.map((s) => s.term);
  const skills = (skill && !offered.includes(skill) ? [skill, ...offered] : offered)
    .map((term) => ({ value: term, label: skillName(term) }));

  return (
    <>
      <section className="panel pay-table-panel" aria-label={heading}>
        <div className="chart-panel-head">
          <h3>
            {heading}
            <InfoTip label={insightsPayTableAbout()}>{insightsPayTableHowRead()}</InfoTip>
          </h3>
          <div className="chart-head-controls">
            {skills.length > 0 && (
              <FilterSelect
                label={skill ? skillName(skill) : insightsPayTableAnySkill()}
                options={skills}
                selected={skill ? [skill] : []}
                onChange={(next) => onSkill(next[0] ?? null)}
                multiple={false}
                searchable
              />
            )}
            {(data.rows.length > 1 || query.trim() !== "") && (
              <SearchField
                label={insightsDemandFindACompany()}
                placeholder={insightsDemandFindACompany()}
                value={query}
                onChange={setQuery}
              />
            )}
          </div>
        </div>

        {data.rows.length === 0 ? (
          <div className="empty-hint">
            {skill ? insightsPayTableSkillEmpty({ country: place, skill: skillName(skill) }) : insightsPayTableEmpty({ country: place })}
          </div>
        ) : (
          <table className="traj-table pay-table">
            <thead>
              <tr>
                <th scope="col">{insightsCommonCompany()}</th>
                <th scope="col">{insightsPayTablePosted()}</th>
                {data.estimates && <th scope="col">{insightsPayTableEstimate()}</th>}
                <th scope="col" className="num">{insightsCommonOpenRoles()}</th>
                <th scope="col">{insightsStockTrajectoryPanelEquity()}</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((row) => (
                <tr key={row.company}>
                  <th scope="row">
                    <Link to={`/?company=${encodeURIComponent(row.company)}`}>
                      <Content text={companyName(row.company)} />
                    </Link>
                    {row.followed_as_set && (
                      <span className="sr-only">{insightsPayTableFollowedAsSet()}</span>
                    )}
                  </th>
                  <Posted row={row} currency={data.currency ?? "USD"} scale={scale} />
                  {data.estimates && <Estimate row={row} level={data.level_band} />}
                  <td className="num">{copyNumber(row.open_roles)}</td>
                  <Equity equity={row.equity} />
                </tr>
              ))}
            </tbody>
          </table>
        )}

        {!all && !query.trim() && matched.length > rows.length && (
          <Button variant="link" onClick={() => setAll(true)}>
            {insightsDemandShowAll({ company: matched.length })}
          </Button>
        )}
        {hiddenSilent > 0 && <p className="hiring-note">{insightsPayTableMoreSilent({ count: hiddenSilent })}</p>}
        {!data.estimates && <p className="hiring-note">{insightsPayTableEstimatesUs()}</p>}
        {data.not_placed.length > 0 && (
          <p className="hiring-note">
            {insightsPayTableNotPlaced({
              roles: data.not_placed.reduce((sum, c) => sum + c.roles, 0),
              companies: data.not_placed.length,
            })}
          </p>
        )}
      </section>
      {advanced && <PayDisciplines data={data} />}
    </>
  );
}

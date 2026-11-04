import { useCallback, useRef, useState } from "react";
import { Link, useLocation, useSearchParams } from "react-router-dom";
import type { ApplicationCard } from "../../api";
import { useJobActions, useJobWorkspace } from "../../context/JobWorkspace";
import { date as formatDate } from "../../copy/format";
import { STAGE_LABEL, type StageSlug } from "../../copy/vocabulary";
import { BAND_LABEL, companyName, relDays } from "../../format";
import { usePayCoverage } from "../../payCoverage";
import { baseShown } from "../../payShown";
import { CompareBeacon } from "../../patterns/jobs/CompareBeacon";
import { primaryLocation } from "../../patterns/jobs/location";
import { SortButton } from "../../patterns/jobs/SortButton";
import { AsyncBoundary, Badge, Button, CompanyIcon, Content, EmptyState, Icon, MenuItem } from "../../ui";
import { Abbr } from "../../ui/Abbr";
import { Msg } from "../../ui/Msg";
import {
  jobsCompare,
  jobsCompareFull,
  jobsCompareFullCap,
  jobsHeadLocation,
  jobsHeadPay,
  jobsHeadRole,
} from "../../copy/gen/jobs";
import {
  applicationsBoardLoadFailed,
  applicationsCardDaysInStage,
  applicationsCardDaysShort,
  applicationsCardDueInterview,
  applicationsCardDueStep,
  applicationsCardOverdue,
  applicationsCardPostingClosed,
  applicationsCardPriority,
  applicationsFactDays,
  applicationsFactLastActivity,
  applicationsFactLevel,
  applicationsFactPriority,
  applicationsFactsPosting,
  applicationsListEmpty,
  applicationsListEmptyHint,
  applicationsListHeadNext,
  applicationsListHeadStage,
  applicationsListNoMatches,
  applicationsListStage,
  applicationsMenuLabel,
  applicationsMenuRemove,
} from "../../copy/gen/applications";
import { applicationPath, boardStage, dayOffset, daysInStage, daysOverdue, dueOf, dueState } from "./board";
import { isFiltering, matches, quickCounts } from "./filters";
import {
  FIRST_ORDER,
  LIST_COLUMNS,
  placedBand,
  readListHidden,
  readSort,
  sortRows,
  writeListHidden,
  writeSort,
  type ListColumn,
  type ListRow,
  type ListSort,
} from "./listRows";
import { PipelineToolbar } from "./PipelineToolbar";
import { StageMenu } from "./StageMenu";
import type { useBoardController } from "./useBoardController";
import { usePostings } from "./usePostings";
import { useStageAsk } from "./useStageAsk";
import { useViewFilter } from "./useViewFilter";

const PRIORITY_STEPS = [1, 2, 3, 4, 5] as const;

/** Each column's header, and the sort it chooses. A city is not a rank, so
 *  Location sorts nothing. */
const HEAD: Record<ListColumn | "role", { name: () => string; sort?: ListSort; num?: boolean }> = {
  role: { name: jobsHeadRole, sort: "role" },
  stage: { name: applicationsListHeadStage, sort: "stage" },
  pay: { name: jobsHeadPay, sort: "pay", num: true },
  location: { name: jobsHeadLocation },
  level: { name: applicationsFactLevel, sort: "level" },
  next: { name: applicationsListHeadNext, sort: "next" },
  posting: { name: applicationsFactsPosting, sort: "posting" },
  priority: { name: applicationsFactPriority, sort: "priority" },
  in_stage: { name: applicationsFactDays, sort: "in_stage", num: true },
  activity: { name: applicationsFactLastActivity, sort: "activity" },
};

/** The List's sort, kept in its own address beside its filter. Choosing a
 *  sort replaces the entry and keeps what the entry holds besides. */
function useListSort() {
  const [params, setParams] = useSearchParams();
  const { state } = useLocation();
  const { sort, order } = readSort(params);
  const choose = useCallback(
    (next: ListSort) => {
      setParams((current) => {
        const was = readSort(current);
        const nextOrder = was.sort === next ? (was.order === "asc" ? "desc" : "asc") : FIRST_ORDER[next];
        return writeSort(current, next, nextOrder);
      }, { replace: true, state });
    },
    [setParams, state],
  );
  return { sort, order, choose };
}

function NextStep({ card, now }: { card: ApplicationCard; now: Date }) {
  const due = dueOf(card);
  const what = due?.kind === "interview" ? card.next_interview?.label : card.next_action;
  if (!due && !card.next_action) return <span className="app-list-none" aria-hidden="true">·</span>;
  const state = due ? dueState(due, now) : null;
  const when = due
    ? state === "overdue"
      ? applicationsCardOverdue({ days: daysOverdue(due, now) })
      : (due.kind === "interview" ? applicationsCardDueInterview : applicationsCardDueStep)({
        offset: dayOffset(due.on, now), date: formatDate(due.on, "weekday"),
      })
    : null;
  return (
    <span className="app-list-next" data-state={state ?? undefined}>
      {what && <span className="app-list-next-what"><Content text={what} /></span>}
      {when && <span className="app-list-next-when">{when}</span>}
    </span>
  );
}

function Row({ row, now, shown, onMove, onRemove, match }: {
  row: ListRow;
  now: Date;
  shown: ReadonlySet<ListColumn>;
  onMove: (card: ApplicationCard, stage: StageSlug) => void;
  onRemove: (card: ApplicationCard) => void;
  match?: boolean;
}) {
  const { card, job } = row;
  const { viewedIds, compareIds, compareFull, compareCap } = useJobWorkspace();
  const { toggleCompare } = useJobActions();
  const cover = usePayCoverage();
  const [stageButton, setStageButton] = useState<HTMLButtonElement | null>(null);
  const [menuOpen, setMenuOpen] = useState(false);
  const company = companyName(card.company);
  const stage = STAGE_LABEL[boardStage(card.stage)];
  const unread = job != null && job.viewed_at == null && !viewedIds.has(card.job_id);
  const compareOn = compareIds.has(card.job_id);
  const full = compareFull && !compareOn;
  const base = job ? baseShown(job, cover) : null;
  const where = job ? primaryLocation(job.locations) : null;
  const band = placedBand(job);
  const days = daysInStage(card, now);
  const quietFor = card.last_activity_at
    ? Math.floor((now.getTime() - new Date(card.last_activity_at).getTime()) / 86_400_000)
    : null;
  const cell = (column: ListColumn, content: React.ReactNode, num = false) =>
    shown.has(column) ? <td className={num ? "num" : undefined} data-col={column}>{content}</td> : null;

  return (
    <tr
      className="app-list-row"
      data-job-id={card.job_id}
      data-unread={unread || undefined}
      data-match={match == null ? undefined : String(match)}
    >
      <th scope="row" className="app-list-role">
        <span className="app-list-company">
          <CompanyIcon slug={card.company} display={company} size={16} />
          <span data-selection="content"><Content text={company} /></span>
        </span>
        <Link to={applicationPath(card.job_id)} className="app-list-title" data-selection="content">
          <Content text={card.title} />
        </Link>
      </th>
      {cell("stage", (
        <>
          <Button
            ref={setStageButton}
            size="sm"
            className="app-list-stage"
            aria-label={applicationsListStage({ stage, title: card.title })}
            aria-haspopup="dialog"
            aria-expanded={menuOpen}
            onClick={() => setMenuOpen((open) => !open)}
          >
            {stage}
            <Icon name="chevronDown" size={12} />
          </Button>
          <StageMenu
            current={card.stage}
            label={applicationsMenuLabel({ title: card.title })}
            anchor={stageButton}
            isOpen={menuOpen}
            onClose={() => setMenuOpen(false)}
            onMove={(next) => {
              setMenuOpen(false);
              onMove(card, next);
            }}
          >
            {card.stage === "saved" && card.starred && (
              <MenuItem
                onSelect={() => {
                  setMenuOpen(false);
                  onRemove(card);
                }}
              >
                {applicationsMenuRemove()}
              </MenuItem>
            )}
          </StageMenu>
        </>
      ))}
      {cell("pay", base && (
        <span className="comp" title={base.hint}>
          {base.text}
          {base.hint && <span className="sr-only"> {base.hint}</span>}
        </span>
      ), true)}
      {cell("location", where?.city && (
        <span title={where.others.length ? [where.city, ...where.others].join(" · ") : undefined}>
          <Content text={where.city} />
          {where.others.length > 0 && <span className="app-list-more"> +{where.others.length}</span>}
        </span>
      ))}
      {cell("level", band && (BAND_LABEL[band] ?? band))}
      {cell("next", <NextStep card={card} now={now} />)}
      {cell("posting", card.posting_status === "closed"
        ? <Badge tone="warning" variant="tint" size="sm">{applicationsCardPostingClosed()}</Badge>
        : job && <span className="app-list-age">{relDays(job.listed_days)}</span>)}
      {cell("priority", (
        <span className="app-tile-priority" role="img" aria-label={applicationsCardPriority({ priority: card.priority })}>
          {PRIORITY_STEPS.map((step) => (
            <span key={step} className="app-tile-dot" data-filled={step <= card.priority || undefined} aria-hidden="true" />
          ))}
        </span>
      ))}
      {cell("in_stage", days != null && (
        <Abbr short={applicationsCardDaysShort({ days })} full={applicationsCardDaysInStage({ days })} />
      ), true)}
      {cell("activity", quietFor != null && relDays(quietFor))}
      <td className="app-list-compare">
        <Button
          variant="icon"
          size="sm"
          aria-label={jobsCompare()}
          aria-pressed={compareOn}
          aria-disabled={full || undefined}
          title={full ? (compareCap === undefined ? jobsCompareFull() : jobsCompareFullCap({ cap: compareCap })) : jobsCompare()}
          onClick={() => {
            if (!full) toggleCompare(card.job_id);
          }}
        >
          <Icon name={compareOn ? "check" : "columns"} size={14} />
        </Button>
      </td>
    </tr>
  );
}

/** The List: every application as a row of a table, with its posting's facts
 *  beside it. It owns its filter, its sort and its columns; the page lends it
 *  only the applications. A row's stage opens the same moves a card's menu
 *  holds, and its title opens the application. */
export function ListView({ board, now }: {
  board: ReturnType<typeof useBoardController>;
  /** The page's clock, so a row's due date reads as the board's does. */
  now: Date;
}) {
  const { cards, resource, move, remove } = board;
  const [filter, setFilter] = useViewFilter();
  const { sort, order, choose } = useListSort();
  const [hidden, setHiddenState] = useState<ListColumn[]>(readListHidden);
  const postings = usePostings(cards);
  const { ask, dialog } = useStageAsk(move);
  const host = useRef<HTMLDivElement>(null);
  const filtering = isFiltering(filter);
  const highlight = filtering && filter.mode === "highlight";
  const shown = new Set(LIST_COLUMNS.filter((column) => !hidden.includes(column)));
  const setHidden = (next: ListColumn[]) => {
    writeListHidden(next);
    setHiddenState(next);
  };

  const all = sortRows(cards.map((card) => ({ card, job: postings.get(card.job_id) })), sort, order, now, companyName);
  const rows = filtering && !highlight ? all.filter((row) => matches(row.card, filter, now)) : all;

  const head = (column: ListColumn | "role") => {
    const { name, sort: key, num } = HEAD[column];
    const label = name();
    const active = key != null && sort === key;
    return (
      <th
        key={column}
        scope="col"
        className={num ? "num" : undefined}
        data-col={column}
        aria-sort={active ? (order === "asc" ? "ascending" : "descending") : undefined}
      >
        {key ? (
          <SortButton shown={label} spoken={label} active={active} order={order} onSort={() => choose(key)} />
        ) : label}
      </th>
    );
  };

  return (
    <>
      <PipelineToolbar
        filter={filter}
        onFilter={setFilter}
        quickCounts={quickCounts(cards, now)}
        columns={{
          all: LIST_COLUMNS.map((column) => ({ id: column, name: HEAD[column].name() })),
          hidden,
          onHidden: setHidden,
          anchored: true,
        }}
      />
      <AsyncBoundary
        resource={resource}
        failed={applicationsBoardLoadFailed()}
        isEmpty={(data) => data.applications.length === 0}
        empty={
          <EmptyState title={applicationsListEmpty()}>
            <Msg of={applicationsListEmptyHint} elems={{ icon: <Icon name="star" size={12} /> }} />
          </EmptyState>
        }
      >
        {() => rows.length === 0 ? (
          <p className="app-column-empty app-list-empty">{applicationsListNoMatches()}</p>
        ) : (
          // The compare beacon sits in the margin beside the rows, outside
          // the scroller that would clip it.
          <div className="job-margin-host" ref={host}>
            <div className="app-list-scroll">
            <table className="data-table app-list" data-highlight={highlight ? "" : undefined}>
              <thead>
                <tr>
                  {head("role")}
                  {LIST_COLUMNS.filter((column) => shown.has(column)).map(head)}
                  <th scope="col"><span className="sr-only">{jobsCompare()}</span></th>
                </tr>
              </thead>
              <tbody>
                {rows.map((row) => (
                  <Row
                    key={row.card.job_id}
                    row={row}
                    now={now}
                    shown={shown}
                    onMove={ask}
                    onRemove={remove}
                    match={highlight ? matches(row.card, filter, now) : undefined}
                  />
                ))}
              </tbody>
            </table>
            </div>
            <CompareBeacon host={host} anchorVersion={rows} />
          </div>
        )}
      </AsyncBoundary>
      {dialog}
    </>
  );
}

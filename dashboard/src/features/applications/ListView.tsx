import { useCallback, useLayoutEffect, useRef, useState, type DragEvent, type ReactNode } from "react";
import { Link, useLocation, useSearchParams } from "react-router-dom";
import type { ApplicationCard } from "../../api";
import { useJobActions, useJobWorkspace } from "../../context/JobWorkspace";
import { date as formatDate } from "../../copy/format";
import { STAGE_LABEL, type StageSlug } from "../../copy/vocabulary";
import { BAND_LABEL, companyName, relDays } from "../../format";
import { usePayCoverage } from "../../payCoverage";
import { baseShown } from "../../payShown";
import { CompareBeacon } from "../../patterns/jobs/CompareBeacon";
import { StarButton } from "../../patterns/jobs/JobControls";
import { primaryLocation } from "../../patterns/jobs/location";
import { SortButton } from "../../patterns/jobs/SortButton";
import { AsyncBoundary, Badge, Button, CompanyIcon, Content, EmptyState, Icon, Menu, MenuGroup, MenuItem, useToast } from "../../ui";
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
import { sharedNotForMe } from "../../copy/gen/shared";
import { errorApplicationUnderWay } from "../../copy/gen/errors";
import {
  applicationsBoardLoadFailed,
  applicationsCardDaysInStage,
  applicationsCardDaysShort,
  applicationsCardDueInterview,
  applicationsCardDueStep,
  applicationsCardOverdue,
  applicationsCardPostingClosed,
  applicationsCardPriority,
  applicationsColumnHide,
  applicationsColumnMenu,
  applicationsFactDays,
  applicationsFactLastActivity,
  applicationsFactLevel,
  applicationsFactPriority,
  applicationsFactsPosting,
  applicationsListColumnLeft,
  applicationsListColumnRight,
  applicationsListEmpty,
  applicationsListEmptyHint,
  applicationsListEnded,
  applicationsListHeadActions,
  applicationsListHeadNext,
  applicationsListHeadStage,
  applicationsListNoMatches,
  applicationsListStage,
  applicationsPageWithdraw,
  applicationsMenuLabel,
  applicationsMenuRemove,
} from "../../copy/gen/applications";
import { applicationPath, boardStage, dayOffset, daysInStage, daysOverdue, dueOf, dueState, isMoving } from "./board";
import { isFiltering, matches, quickCounts } from "./filters";
import {
  ALWAYS_SHOWN,
  DEFAULT_LAYOUT,
  FIRST_ORDER,
  moveColumn,
  placedBand,
  readListLayout,
  readSort,
  sortRows,
  stepColumn,
  writeListLayout,
  writeSort,
  type ListColumn,
  type ListLayout,
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
const HEAD: Record<ListColumn, { name: () => string; sort?: ListSort; num?: boolean }> = {
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
  if (!due && !card.next_action) return null;
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

/** A column header's ⋯ menu: move the column one place either way among the
 *  columns shown, or hide it. The keyboard's way to do what a drag does. */
function ColumnMenu({ name, first, last, canHide, onStep, onHide }: {
  name: string;
  first: boolean;
  last: boolean;
  canHide: boolean;
  onStep: (by: -1 | 1) => void;
  onHide: () => void;
}) {
  const [button, setButton] = useState<HTMLButtonElement | null>(null);
  const [open, setOpen] = useState(false);
  const label = applicationsColumnMenu({ column: name });
  const pick = (act: () => void) => () => {
    setOpen(false);
    act();
  };
  return (
    <>
      <Button
        ref={setButton}
        variant="icon"
        size="sm"
        className="app-list-head-menu"
        aria-label={label}
        aria-haspopup="dialog"
        aria-expanded={open}
        draggable={false}
        onClick={() => setOpen((was) => !was)}
      >
        <Icon name="more" size={14} />
      </Button>
      <Menu isOpen={open} onClose={() => setOpen(false)} anchor={button} label={label}>
        <MenuGroup>
          <MenuItem icon="arrowLeft" disabled={first} onSelect={pick(() => onStep(-1))}>
            {applicationsListColumnLeft()}
          </MenuItem>
          <MenuItem icon="arrowRight" disabled={last} onSelect={pick(() => onStep(1))}>
            {applicationsListColumnRight()}
          </MenuItem>
        </MenuGroup>
        {canHide && (
          <MenuGroup>
            <MenuItem icon="eyeOff" onSelect={pick(onHide)}>{applicationsColumnHide()}</MenuItem>
          </MenuGroup>
        )}
      </Menu>
    </>
  );
}

interface RowActions {
  onMove: (card: ApplicationCard, stage: StageSlug) => void;
  onRemove: (card: ApplicationCard) => void;
  onNotForMe: (card: ApplicationCard) => void;
  /** Star or Not for me on a role past Considering, which stays. */
  onStays: (card: ApplicationCard) => void;
}

function Row({ row, now, columns, actions, match }: {
  row: ListRow;
  now: Date;
  columns: readonly ListColumn[];
  actions: RowActions;
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
  const fullReason = compareCap === undefined ? jobsCompareFull() : jobsCompareFullCap({ cap: compareCap });
  const fullReasonId = `app-list-full-${card.job_id}`;
  // In Considering a role can leave; past it the star stays and the way out
  // is a stage, which the server holds to as well.
  const leaves = card.stage === "saved";
  const base = job ? baseShown(job, cover) : null;
  const where = job ? primaryLocation(job.locations) : null;
  const band = placedBand(job);
  const days = daysInStage(card, now);
  const quietFor = card.last_activity_at
    ? Math.floor((now.getTime() - new Date(card.last_activity_at).getTime()) / 86_400_000)
    : null;

  const cells: Record<ListColumn, () => ReactNode> = {
    role: () => (
      <th key="role" scope="row" className="app-list-role" data-col="role">
        <span className="app-list-company">
          <CompanyIcon slug={card.company} display={company} size={16} />
          <span data-selection="content"><Content text={company} /></span>
        </span>
        <Link to={applicationPath(card.job_id)} className="app-list-title" data-selection="content">
          <Content text={card.title} />
        </Link>
      </th>
    ),
    stage: () => (
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
            actions.onMove(card, next);
          }}
        >
          {leaves && card.starred && (
            <MenuItem
              onSelect={() => {
                setMenuOpen(false);
                actions.onRemove(card);
              }}
            >
              {applicationsMenuRemove()}
            </MenuItem>
          )}
        </StageMenu>
      </>
    ),
    pay: () => base && (
      <span className="comp" title={base.hint}>
        {base.text}
        {base.hint && <span className="sr-only"> {base.hint}</span>}
      </span>
    ),
    location: () => where?.city && (
      <span title={where.others.length ? [where.city, ...where.others].join(" · ") : undefined}>
        <Content text={where.city} />
        {where.others.length > 0 && <span className="app-list-more"> +{where.others.length}</span>}
      </span>
    ),
    level: () => band && (BAND_LABEL[band] ?? band),
    next: () => <NextStep card={card} now={now} />,
    posting: () => card.posting_status === "closed"
      ? <Badge tone="warning" variant="tint" size="sm">{applicationsCardPostingClosed()}</Badge>
      : job && <span className="app-list-age">{relDays(job.listed_days)}</span>,
    priority: () => (
      <span className="app-tile-priority" role="img" aria-label={applicationsCardPriority({ priority: card.priority })}>
        {PRIORITY_STEPS.map((step) => (
          <span key={step} className="app-tile-dot" data-filled={step <= card.priority || undefined} aria-hidden="true" />
        ))}
      </span>
    ),
    in_stage: () => days != null && (
      <Abbr short={applicationsCardDaysShort({ days })} full={applicationsCardDaysInStage({ days })} />
    ),
    activity: () => quietFor != null && relDays(quietFor),
  };

  return (
    <tr
      className="app-list-row"
      data-job-id={card.job_id}
      data-unread={unread || undefined}
      data-match={match == null ? undefined : String(match)}
    >
      {columns.map((column) => column === "role"
        ? cells.role()
        : <td key={column} className={HEAD[column].num ? "num" : undefined} data-col={column}>{cells[column]()}</td>)}
      {/* Radar's row actions, in Radar's order: Not for me, Compare, the star. */}
      <td className="app-list-actions">
        <span className="app-list-actions-set">
          <Button
            variant="icon"
            size="sm"
            aria-label={sharedNotForMe()}
            title={sharedNotForMe()}
            onClick={() => (leaves ? actions.onNotForMe(card) : actions.onStays(card))}
          >
            <Icon name="eyeOff" size={14} />
          </Button>
          {/* Full: still focusable, with the reason as its description. */}
          <Button
            variant="icon"
            size="sm"
            aria-label={jobsCompare()}
            aria-pressed={compareOn}
            aria-disabled={full || undefined}
            aria-describedby={full ? fullReasonId : undefined}
            title={full ? fullReason : jobsCompare()}
            onClick={() => {
              if (!full) toggleCompare(card.job_id);
            }}
          >
            <Icon name={compareOn ? "check" : "columns"} size={14} />
          </Button>
          {full && <span id={fullReasonId} className="sr-only">{fullReason}</span>}
          <StarButton
            on={card.starred || !leaves}
            size={16}
            onToggle={() => (leaves ? actions.onRemove(card) : actions.onStays(card))}
          />
        </span>
      </td>
    </tr>
  );
}

/** The List's columns: their order and which are hidden, this browser's. */
function useListLayout() {
  const [layout, setLayoutState] = useState<ListLayout>(readListLayout);
  const setLayout = useCallback((next: ListLayout) => {
    writeListLayout(next);
    setLayoutState(next);
  }, []);
  return [layout, setLayout] as const;
}

/** Whether the table is wider than its frame, so it scrolls sideways. The
 *  frame is a node, not a ref: it mounts only once the applications load. */
function useOverflowing(node: HTMLDivElement | null, version: unknown) {
  const [overflowing, setOverflowing] = useState(false);
  useLayoutEffect(() => {
    if (!node) return;
    const measure = () => setOverflowing(node.scrollWidth > node.clientWidth + 1);
    measure();
    const observer = typeof ResizeObserver === "undefined" ? null : new ResizeObserver(measure);
    observer?.observe(node);
    if (node.firstElementChild) observer?.observe(node.firstElementChild);
    return () => observer?.disconnect();
  }, [node, version]);
  return overflowing;
}

/** Where a dragged header would land: before `before`, or last when null. */
interface Drop {
  over: ListColumn;
  side: "before" | "after";
  before: ListColumn | null;
}

/** The List: every application as a row of a table, with its posting's facts
 *  beside it. It owns its filter, its sort and its columns; the page lends it
 *  only the applications. A row's stage opens the same moves a card's menu
 *  holds, its title opens the application, and its last cell holds Radar's
 *  row actions. A header sorts, drags to a new place, and its menu moves or
 *  hides it. */
export function ListView({ board, now }: {
  board: ReturnType<typeof useBoardController>;
  /** The page's clock, so a row's due date reads as the board's does. */
  now: Date;
}) {
  const { cards, resource, move, remove, dismiss } = board;
  const [filter, setFilter] = useViewFilter();
  const { sort, order, choose } = useListSort();
  const [layout, setLayout] = useListLayout();
  const postings = usePostings(cards);
  const { ask, dialog } = useStageAsk(move);
  const { toast } = useToast();
  const host = useRef<HTMLDivElement>(null);
  const [frame, setFrame] = useState<HTMLDivElement | null>(null);
  const [dragged, setDragged] = useState<ListColumn | null>(null);
  const [drop, setDrop] = useState<Drop | null>(null);
  const filtering = isFiltering(filter);
  const highlight = filtering && filter.mode === "highlight";
  const shown = layout.order.filter((column) => !layout.hidden.includes(column));
  const overflowing = useOverflowing(frame, shown.join());
  const asFirst = layout.order.join() === DEFAULT_LAYOUT.order.join()
    && [...layout.hidden].sort().join() === [...DEFAULT_LAYOUT.hidden].sort().join();

  const stays = (card: ApplicationCard) => {
    if (isMoving(card)) {
      toast({
        key: "applications",
        text: errorApplicationUnderWay(),
        action: { label: applicationsPageWithdraw(), onClick: () => ask(card, "withdrawn") },
      });
    } else {
      toast({ key: "applications", text: applicationsListEnded() });
    }
  };
  const actions: RowActions = { onMove: ask, onRemove: remove, onNotForMe: dismiss, onStays: stays };

  const all = sortRows(cards.map((card) => ({ card, job: postings.get(card.job_id) })), sort, order, now, companyName);
  const rows = filtering && !highlight ? all.filter((row) => matches(row.card, filter, now)) : all;

  const endDrag = () => {
    setDragged(null);
    setDrop(null);
  };
  const dragOver = (column: ListColumn) => (event: DragEvent<HTMLTableCellElement>) => {
    if (dragged == null) return;
    event.preventDefault();
    event.dataTransfer.dropEffect = "move";
    const box = event.currentTarget.getBoundingClientRect();
    const side = event.clientX < box.left + box.width / 2 ? "before" : "after";
    const before = side === "before" ? column : shown[shown.indexOf(column) + 1] ?? null;
    if (drop?.over !== column || drop.side !== side) setDrop({ over: column, side, before });
  };
  const dropped = (event: DragEvent<HTMLTableCellElement>) => {
    event.preventDefault();
    if (dragged != null && drop != null) setLayout({ ...layout, order: moveColumn(layout.order, dragged, drop.before) });
    endDrag();
  };

  const head = (column: ListColumn, index: number) => {
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
        draggable
        data-dragged={dragged === column || undefined}
        data-drop={drop?.over === column && dragged !== column ? drop.side : undefined}
        onDragStart={(event) => {
          event.dataTransfer.effectAllowed = "move";
          event.dataTransfer.setData("text/plain", column);
          setDragged(column);
        }}
        onDragOver={dragOver(column)}
        onDrop={dropped}
        onDragEnd={endDrag}
      >
        <span className="app-list-head">
          {key ? (
            <SortButton shown={label} spoken={label} active={active} order={order} onSort={() => choose(key)} />
          ) : <span className="app-list-head-name">{label}</span>}
          <ColumnMenu
            name={label}
            first={index === 0}
            last={index === shown.length - 1}
            canHide={column !== ALWAYS_SHOWN}
            onStep={(by) => setLayout({ ...layout, order: stepColumn(layout, column, by) })}
            onHide={() => setLayout({ ...layout, hidden: [...layout.hidden, column] })}
          />
        </span>
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
          all: layout.order.filter((column) => column !== ALWAYS_SHOWN).map((column) => ({ id: column, name: HEAD[column].name() })),
          hidden: layout.hidden,
          onHidden: (hidden) => setLayout({ ...layout, hidden }),
          anchored: true,
          onReset: () => setLayout({ order: [...DEFAULT_LAYOUT.order], hidden: [...DEFAULT_LAYOUT.hidden] }),
          asFirst,
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
          <div className="app-list-host job-margin-host" ref={host}>
            <div className="app-list-scroll" ref={setFrame} data-overflowing={overflowing || undefined}>
              <table className="data-table app-list" data-highlight={highlight ? "" : undefined} data-dragging={dragged ? "" : undefined}>
                <thead data-selection="chrome">
                  <tr>
                    {shown.map(head)}
                    <th scope="col" className="app-list-actions"><span className="sr-only">{applicationsListHeadActions()}</span></th>
                  </tr>
                </thead>
                <tbody>
                  {rows.map((row) => (
                    <Row
                      key={row.card.job_id}
                      row={row}
                      now={now}
                      columns={shown}
                      actions={actions}
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

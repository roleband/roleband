import { useCallback, useEffect, useRef, useState } from "react";
import { useNavigate, useParams, useSearchParams } from "react-router-dom";
import type { ApplicationCard, InterviewWrite } from "../../api";
import { STAGE_LABEL, type StageSlug } from "../../copy/vocabulary";
import { PageHeader } from "../../patterns/PageHeader";
import { useTabRoute } from "../../routing/useTabRoute";
import { AsyncBoundary, Button, Icon, Popover, TabBar } from "../../ui";
import { Msg } from "../../ui/Msg";
import { shellNavPipeline, shellTabPipelineBoard, shellTabPipelineUpNext } from "../../copy/gen/shell";
import {
  applicationsBoardLoadFailed,
  applicationsBoardNeedNext,
  applicationsBoardSummary,
  applicationsColumnClosed,
  applicationsColumnCountOf,
  applicationsColumnDecided,
  applicationsColumnEmpty,
  applicationsColumnEmptySaved,
  applicationsColumnHide,
  applicationsColumnHideLast,
  applicationsColumnMenu,
  applicationsColumnNoMatches,
  applicationsMoved,
  applicationsMovedHidden,
  applicationsSectionEmpty,
  applicationsTabsLabel,
} from "../../copy/gen/applications";
import { ApplicationPage } from "./ApplicationPage";
import { ApplicationTile } from "./ApplicationTile";
import { COLUMNS, boardCounts, byStage, columnOf, type ColumnDef, type ColumnId } from "./board";
import { readHiddenColumns, writeHiddenColumns } from "./columnView";
import { upNext } from "./dueByDay";
import {
  QUICK_FILTERS,
  isFiltering,
  matches,
  matchesQuick,
  readFilter,
  writeFilter,
  type BoardFilter,
  type QuickFilter,
} from "./filters";
import { InterviewDialog } from "./InterviewDialog";
import { PipelineToolbar } from "./PipelineToolbar";
import { UpNext } from "./UpNext";
import { useCardDrag } from "./useCardDrag";
import { useBoardController } from "./useBoardController";
import "./applications.css";

const PIPELINE_SLUGS = ["board", "up-next"] as const;
type PipelineTab = (typeof PIPELINE_SLUGS)[number];
const TAB_LABEL: Record<PipelineTab, () => string> = {
  board: shellTabPipelineBoard,
  "up-next": shellTabPipelineUpNext,
};
const isApplication = (slug: string | undefined): slug is string => slug != null && /^\d+$/.test(slug);

const COLUMN_NAME: Record<ColumnDef["id"], () => string> = {
  saved: () => STAGE_LABEL.saved,
  researching: () => STAGE_LABEL.researching,
  applied: () => STAGE_LABEL.applied,
  interviewing: () => STAGE_LABEL.interviewing,
  offer: () => STAGE_LABEL.offer,
  decided: () => applicationsColumnDecided(),
  closed: () => applicationsColumnClosed(),
};

/** The application pipeline. `/pipeline/<job id>` is one application's page;
 *  every other slug is one of the place's tabs. */
export function ApplicationsScreen() {
  const { tab } = useParams();
  // Keyed by the role, so stepping to a neighbour starts its page afresh.
  if (isApplication(tab)) return <ApplicationPage key={tab} jobId={Number(tab)} />;
  return <PipelineTabs />;
}

/** One column's ⋯ menu. Hiding is the one thing it does; the last shown
 *  column cannot hide, so the board is never empty of columns. */
function ColumnMenu({ name, last, onHide }: { name: string; last: boolean; onHide: () => void }) {
  const [button, setButton] = useState<HTMLButtonElement | null>(null);
  const [open, setOpen] = useState(false);
  const label = applicationsColumnMenu({ column: name });
  return (
    <>
      <Button
        ref={setButton}
        variant="icon"
        size="sm"
        className="app-column-menu"
        aria-label={label}
        aria-haspopup="dialog"
        aria-expanded={open}
        onClick={() => setOpen((was) => !was)}
      >
        <Icon name="more" size={16} />
      </Button>
      <Popover isOpen={open} onClose={() => setOpen(false)} anchor={button} align="end" label={label} className="app-overlay app-menu">
        <div className="app-menu-group">
          <Button
            variant="ghost"
            size="sm"
            className="app-menu-option"
            disabled={last}
            title={last ? applicationsColumnHideLast() : undefined}
            onClick={() => {
              setOpen(false);
              onHide();
            }}
          >
            <Icon name="eyeOff" size={14} />
            <span className="app-menu-name">{applicationsColumnHide()}</span>
          </Button>
        </div>
      </Popover>
    </>
  );
}

/** The Board, every starred or pursued role as a card in the column of its
 *  stage, and Up next, what is due by day. Both read the same applications,
 *  under one toolbar whose filters apply to both. */
function PipelineTabs() {
  const { tab } = useTabRoute<PipelineTab>({ base: "/pipeline", slugs: PIPELINE_SLUGS, fallback: "board" });
  const navigate = useNavigate();
  const [params, setParams] = useSearchParams();
  const filter = readFilter(params);
  const [hidden, setHiddenState] = useState<ColumnId[]>(readHiddenColumns);
  // The toast reads the columns hidden when a move lands, not when the
  // board's controller was made.
  const hiddenNow = useRef(hidden);
  useEffect(() => {
    hiddenNow.current = hidden;
  }, [hidden]);
  const said = useCallback((title: string, stage: StageSlug) => {
    const column = columnOf(stage);
    return hiddenNow.current.includes(column.id)
      ? applicationsMovedHidden({ title, stage: STAGE_LABEL[stage], column: COLUMN_NAME[column.id]() })
      : applicationsMoved({ title, stage: STAGE_LABEL[stage] });
  }, []);
  const { cards, resource, move, remove } = useBoardController({ said });
  const [asking, setAsking] = useState<ApplicationCard | null>(null);
  // One clock per render, so every card on the board measures from the same instant.
  const now = new Date();
  const groups = byStage(cards, now);
  const counts = boardCounts(cards);
  const filtering = isFiltering(filter);
  const highlight = filter.mode === "highlight";
  /** Cards that do not match leave the board, rather than fade. */
  const narrowed = filtering && !highlight;
  const hits = (card: ApplicationCard) => matches(card, filter, now);

  // A tab is a place and keeps the filter: the query rides along.
  const setTab = (next: PipelineTab) => navigate({ pathname: `/pipeline/${next}`, search: params.toString() });
  // Typing is not a destination, so a filter change replaces the entry.
  const setFilter = (next: Partial<BoardFilter>) =>
    setParams((current) => writeFilter(current, { ...readFilter(current), ...next }), { replace: true });
  const setHidden = (next: ColumnId[]) => {
    writeHiddenColumns(next);
    setHiddenState(next);
  };

  // Interviewing asks for the interview's date first: it is the column's
  // entry condition. Every other move is immediate.
  const ask = (card: ApplicationCard, stage: StageSlug) => {
    if (stage === "interviewing" && card.stage !== "interviewing") setAsking(card);
    else void move(card, stage);
  };
  const confirmInterview = (interview: InterviewWrite) => {
    const card = asking;
    setAsking(null);
    if (card) void move(card, "interviewing", interview);
  };
  // A drop is a move like the menu's, and asks for the same.
  const scroller = useRef<HTMLDivElement>(null);
  const { drag, handlers } = useCardDrag(scroller, ask);
  /** The stage a drop now would move the dragged card to. */
  const landing = drag && drag.target !== drag.stage ? drag.target : null;

  const shown = COLUMNS.filter((column) => !hidden.includes(column.id));
  const columnTotal = (column: ColumnDef) => column.stages.reduce((sum, stage) => sum + (groups.get(stage)?.length ?? 0), 0);
  const quickCounts = Object.fromEntries(
    QUICK_FILTERS.map((quick) => [quick, cards.filter((card) => matchesQuick(card, quick, now)).length]),
  ) as Record<QuickFilter, number>;
  // The count is what the open view holds: the cards in the columns shown,
  // or Up next's rows.
  const onBoard = shown.flatMap((column) => column.stages.flatMap((stage) => groups.get(stage) ?? []));
  const due = upNext(cards, now).flatMap((day) => day.items);
  const [count, total] = tab === "up-next"
    ? [due.filter((item) => hits(item.card)).length, due.length]
    : [onBoard.filter(hits).length, onBoard.length];
  const needNext = filter.quick.includes("needs_next");

  return (
    <main className="main app-main" data-design-system="app">
      <PageHeader title={shellNavPipeline()}
        meta={resource.data ? (
          <p className="app-summary">
            <Msg
              of={applicationsBoardSummary}
              args={{ moving: counts.moving, decided: counts.decided, closed: counts.closed }}
              elems={{
                needNext: counts.needNextStep > 0 && !needNext ? (
                  <Button variant="link" onClick={() => setFilter({ quick: [...filter.quick, "needs_next"] })}>
                    {applicationsBoardNeedNext({ count: counts.needNextStep })}
                  </Button>
                ) : applicationsBoardNeedNext({ count: counts.needNextStep }),
              }}
            />
          </p>
        ) : undefined}
      />
      <TabBar
        className="app-tabbar"
        label={applicationsTabsLabel()}
        idPrefix="pipeline"
        controls="pipeline-tabpanel"
        value={tab}
        onChange={setTab}
        tabs={PIPELINE_SLUGS.map((slug) => ({ id: slug, label: TAB_LABEL[slug]() }))}
      />
      <div id="pipeline-tabpanel" className="app-tabpanel" role="tabpanel" aria-labelledby={`pipeline-tab-${tab}`}>
      <PipelineToolbar
        filter={filter}
        onFilter={setFilter}
        count={count}
        total={total}
        noun={tab === "up-next" ? "due" : "application"}
        quickCounts={quickCounts}
        columns={tab === "up-next" ? undefined : {
          all: COLUMNS.map((column) => ({ id: column.id, name: COLUMN_NAME[column.id](), count: columnTotal(column) })),
          hidden,
          onHidden: setHidden,
        }}
      />
      {tab === "up-next" ? <UpNext resource={resource} filter={filter} now={now} /> : <AsyncBoundary
        resource={resource}
        failed={applicationsBoardLoadFailed()}
        skeleton={<div className="app-board" aria-hidden="true" />}
      >
        {() => (
          <div className="app-board-scroll" ref={scroller}>
            <div className="app-board" data-dragging={drag ? "" : undefined} data-highlight={filtering && highlight ? "" : undefined}>
              {shown.map((column) => {
                const name = COLUMN_NAME[column.id]();
                const all = columnTotal(column);
                const matched = column.stages.reduce((sum, stage) => sum + (groups.get(stage) ?? []).filter(hits).length, 0);
                const sectioned = column.stages.length > 1;
                return (
                  <section
                    key={column.id}
                    className="app-column"
                    aria-labelledby={`app-column-${column.id}`}
                    data-drop-column={column.id}
                    data-drop-target={!sectioned && landing != null && column.stages.includes(landing) ? "" : undefined}
                  >
                    <div className="app-column-head">
                      <h2 id={`app-column-${column.id}`} className="app-column-name">{name}</h2>
                      <span className="app-column-count">
                        {filtering ? applicationsColumnCountOf({ count: matched, total: all }) : all}
                      </span>
                      <ColumnMenu name={name} last={shown.length === 1} onHide={() => setHidden([...hidden, column.id])} />
                    </div>
                    {narrowed && matched === 0 && (all > 0 || sectioned) && (
                      <p className="app-column-empty">{applicationsColumnNoMatches()}</p>
                    )}
                    {column.stages.map((stage) => {
                      const every = groups.get(stage) ?? [];
                      const list = narrowed ? every.filter(hits) : every;
                      // A section the filter empties stays as a drop target,
                      // with nothing drawn: the column's line says what matched.
                      const quiet = sectioned && narrowed && list.length === 0;
                      return (
                        <div
                          key={stage}
                          className="app-section"
                          role={sectioned ? "group" : undefined}
                          aria-label={sectioned ? STAGE_LABEL[stage] : undefined}
                          data-drop-stage={stage}
                          data-drop-target={sectioned && landing === stage ? "" : undefined}
                        >
                          {sectioned && !quiet && (
                            <h3 className="app-section-name" aria-hidden="true">
                              {STAGE_LABEL[stage]} <span className="app-column-count">{list.length}</span>
                            </h3>
                          )}
                          {every.length === 0 && !quiet && (
                            <p className="app-column-empty">
                              {sectioned
                                ? applicationsSectionEmpty()
                                : stage === "saved" ? applicationsColumnEmptySaved() : applicationsColumnEmpty()}
                            </p>
                          )}
                          {list.map((card) => (
                            <ApplicationTile
                              key={card.job_id}
                              card={card}
                              now={now}
                              onMove={ask}
                              onRemove={remove}
                              drag={handlers(card)}
                              dragged={drag?.jobId === card.job_id ? drag : null}
                              match={filtering && highlight ? hits(card) : undefined}
                            />
                          ))}
                        </div>
                      );
                    })}
                  </section>
                );
              })}
            </div>
          </div>
        )}
      </AsyncBoundary>}
      </div>
      {asking && (
        <InterviewDialog card={asking} moving onCancel={() => setAsking(null)} onSubmit={confirmInterview} />
      )}
    </main>
  );
}

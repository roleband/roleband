import { useRef, useState } from "react";
import type { ApplicationCard } from "../../api";
import { STAGE_LABEL } from "../../copy/vocabulary";
import { AsyncBoundary, Button, Icon, Menu, MenuGroup, MenuItem } from "../../ui";
import {
  applicationsBoardLoadFailed,
  applicationsColumnCountOf,
  applicationsColumnEmpty,
  applicationsColumnEmptySaved,
  applicationsColumnHide,
  applicationsColumnHideLast,
  applicationsColumnMenu,
  applicationsColumnNoMatches,
} from "../../copy/gen/applications";
import { ApplicationTile } from "./ApplicationTile";
import { COLUMNS, byStage, type ColumnDef, type ColumnId } from "./board";
import { columnName, readHiddenColumns, writeHiddenColumns } from "./columnView";
import { VIEW_FILTERS, isFiltering, matches, quickCounts } from "./filters";
import { beside, useFocusAfter } from "./focusAfter";
import { NoMatches, PipelineEmpty } from "./PipelineEmpty";
import { PipelineToolbar } from "./PipelineToolbar";
import type { useBoardController } from "./useBoardController";
import { useCardDrag } from "./useCardDrag";
import { useStageAsk } from "./useStageAsk";
import { useViewFilter } from "./useViewFilter";

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
      <Menu isOpen={open} onClose={() => setOpen(false)} anchor={button} label={label}>
        <MenuGroup>
          <MenuItem
            icon="eyeOff"
            disabled={last}
            title={last ? applicationsColumnHideLast() : undefined}
            onSelect={() => {
              setOpen(false);
              onHide();
            }}
          >
            {applicationsColumnHide()}
          </MenuItem>
        </MenuGroup>
      </Menu>
    </>
  );
}

/** The Board: every starred or pursued role as a card in the column of its
 *  stage. It owns its filter, its columns and its moves; the page lends it
 *  only the applications. */
export function BoardView({ board, now }: {
  board: ReturnType<typeof useBoardController>;
  /** The page's clock, so every card measures from the same instant. */
  now: Date;
}) {
  const { cards, resource, move, remove } = board;
  const [filter, setFilter] = useViewFilter("board");
  const [hidden, setHiddenState] = useState<ColumnId[]>(readHiddenColumns);
  const groups = byStage(cards, now);
  const filtering = isFiltering(filter);
  const highlight = filter.mode === "highlight";
  /** Cards that do not match leave the board, rather than fade. */
  const narrowed = filtering && !highlight;
  const hits = (card: ApplicationCard) => matches(card, filter, now);
  /** The filters leave nothing on the whole board: one line says so above
   *  it, in place of a "No matches." in every column. */
  const nothingMatches = narrowed && cards.length > 0 && !cards.some(hits);
  const setHidden = (next: ColumnId[]) => {
    writeHiddenColumns(next);
    setHiddenState(next);
  };

  // A card that leaves its column takes focus with it: the moved card's menu
  // takes it in its new column, or, where it is not drawn (a hidden column, a
  // filter it no longer matches), the card that stood beside it.
  const scroller = useRef<HTMLDivElement>(null);
  const focusAfter = useFocusAfter();
  const besideCard = (jobId: number) => {
    const tile = scroller.current?.querySelector(`.app-tile[data-job-id="${jobId}"]`);
    const column = tile?.closest(".app-column");
    return beside(tile, column?.querySelectorAll(".app-tile") ?? [], ".app-tile-menu")
      ?? column?.querySelector<HTMLElement>(".app-column-menu");
  };
  const moveKeepingFocus: typeof move = (card, stage, interview) => {
    const fallback = besideCard(card.job_id);
    focusAfter(() => scroller.current?.querySelector<HTMLElement>(
      `[data-drop-stage="${stage}"] .app-tile[data-job-id="${card.job_id}"] .app-tile-menu`,
    ) ?? fallback);
    return move(card, stage, interview);
  };
  const removeKeepingFocus = (card: ApplicationCard) => {
    const fallback = besideCard(card.job_id);
    focusAfter(() => fallback);
    remove(card);
  };
  const hideKeepingFocus = (column: ColumnId) => {
    const sections = scroller.current?.querySelectorAll(".app-column") ?? [];
    const here = scroller.current?.querySelector(`[data-drop-column="${column}"]`);
    const fallback = beside(here, sections, ".app-column-menu");
    focusAfter(() => fallback ?? document.querySelector<HTMLElement>(".app-pipeline-toolbar .app-columns-button"));
    setHidden([...hidden, column]);
  };

  const { ask, dialog } = useStageAsk(moveKeepingFocus);
  // A drop is a move like the menu's, and asks for the same.
  const { drag, handlers } = useCardDrag(scroller, ask);
  /** The stage a drop now would move the dragged card to. */
  const landing = drag && drag.target !== drag.stage ? drag.target : null;

  const shown = COLUMNS.filter((column) => !hidden.includes(column.id));
  const columnTotal = (column: ColumnDef) => column.stages.reduce((sum, stage) => sum + (groups.get(stage)?.length ?? 0), 0);

  return (
    <>
      <PipelineToolbar
        filter={filter}
        onFilter={setFilter}
        quickCounts={quickCounts(cards, now, VIEW_FILTERS.board)}
        columns={{
          all: COLUMNS.map((column) => ({ id: column.id, name: columnName(column.id), count: columnTotal(column) })),
          hidden,
          onHidden: setHidden,
        }}
      />
      <AsyncBoundary
        resource={resource}
        failed={applicationsBoardLoadFailed()}
        skeleton={<div className="app-board" aria-hidden="true" />}
        isEmpty={(data) => data.applications.length === 0}
        empty={<PipelineEmpty />}
      >
        {() => (
          <>
            {nothingMatches && <NoMatches />}
            <div className="app-board-scroll" ref={scroller}>
              <div className="app-board" data-dragging={drag ? "" : undefined} data-highlight={filtering && highlight ? "" : undefined}>
                {shown.map((column) => {
                  const name = columnName(column.id);
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
                        <ColumnMenu name={name} last={shown.length === 1} onHide={() => hideKeepingFocus(column.id)} />
                      </div>
                      {narrowed && !nothingMatches && matched === 0 && (all > 0 || sectioned) && (
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
                            data-empty={sectioned && every.length === 0 ? "" : undefined}
                          >
                            {sectioned && !quiet && (
                              <h3 className="app-section-name" aria-hidden="true">
                                {STAGE_LABEL[stage]} <span className="app-column-count">{list.length}</span>
                              </h3>
                            )}
                            {/* An empty ending is its heading alone, drawn
                                quietly: its 0 says it, and an ending that
                                holds applications stands out beside it. */}
                            {every.length === 0 && !sectioned && (
                              <p className="app-column-empty">
                                {stage === "saved" ? applicationsColumnEmptySaved() : applicationsColumnEmpty()}
                              </p>
                            )}
                            {list.map((card) => (
                              <ApplicationTile
                                key={card.job_id}
                                card={card}
                                now={now}
                                onMove={ask}
                                onRemove={removeKeepingFocus}
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
          </>
        )}
      </AsyncBoundary>
      {dialog}
    </>
  );
}

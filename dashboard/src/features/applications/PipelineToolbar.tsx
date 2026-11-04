import { useState } from "react";
import { useMissionActions } from "../../context/MissionState";
import { number } from "../../copy/format";
import { sharedFilters, sharedFiltersCount } from "../../copy/gen/shared";
import {
  applicationsCardPostingClosed,
  applicationsColumnHideLast,
  applicationsColumns,
  applicationsColumnsHidden,
  applicationsColumnsShow,
  applicationsColumnsShowAll,
  applicationsFilterHighlightInstead,
  applicationsFilterMenu,
  applicationsFilterQuick,
  applicationsFilterRemove,
  applicationsFilterReset,
  applicationsFilterWhile,
  applicationsModeHighlight,
  applicationsModeHighlightHint,
  applicationsModeOnly,
  applicationsModeOnlyHint,
  applicationsQuickDueWeek,
  applicationsQuickHighPriority,
  applicationsQuickNeedsNext,
  applicationsQuickOverdue,
  applicationsQuickQuiet,
  applicationsResults,
  applicationsResultsDue,
  applicationsResultsDueOf,
  applicationsResultsOf,
  applicationsSearchLabel,
  applicationsSearchPlaceholder,
} from "../../copy/gen/applications";
import { Button, FilterChip, Icon, Kbd, Menu, MenuCheck, MenuGroup, MenuItem, MenuRadio, SearchField } from "../../ui";
import { Msg } from "../../ui/Msg";
import type { ColumnId } from "./board";
import { QUICK_FILTERS, isFiltering, type BoardFilter, type FilterMode, type QuickFilter } from "./filters";

const QUICK_LABEL: Record<QuickFilter, () => string> = {
  overdue: applicationsQuickOverdue,
  due_week: applicationsQuickDueWeek,
  needs_next: applicationsQuickNeedsNext,
  quiet: applicationsQuickQuiet,
  high_priority: applicationsQuickHighPriority,
  posting_closed: applicationsCardPostingClosed,
};

const MODES: readonly [FilterMode, () => string, () => string][] = [
  ["only", applicationsModeOnly, applicationsModeOnlyHint],
  ["highlight", applicationsModeHighlight, applicationsModeHighlightHint],
];

/** What the count counts: the board's applications, or Up next's rows. */
const SAY = {
  application: { count: applicationsResults, of: applicationsResultsOf },
  due: { count: applicationsResultsDue, of: applicationsResultsDueOf },
} as const;

export interface ColumnChoice {
  id: ColumnId;
  name: string;
  count: number;
}

export interface PipelineToolbarProps {
  filter: BoardFilter;
  onFilter: (next: Partial<BoardFilter>) => void;
  /** How many of `total` match the filter; the same as `total` while nothing filters. */
  count: number;
  total: number;
  noun: keyof typeof SAY;
  /** How many applications each quick filter would match on its own. */
  quickCounts: Record<QuickFilter, number>;
  /** The board's columns, for the Columns menu. Up next has none. */
  columns?: {
    all: readonly ColumnChoice[];
    hidden: readonly ColumnId[];
    onHidden: (hidden: ColumnId[]) => void;
  };
}

/**
 * The one row of tools over the board and Up next, in Radar's order: the
 * search, the count with its way back, the filters that are on, and at the
 * row's end the menus. A quick filter shows as a chip only while it is on,
 * so the row holds what narrows the view and nothing else.
 */
export function PipelineToolbar({ filter, onFilter, count, total, noun, quickCounts, columns }: PipelineToolbarProps) {
  const { boardSearchRef } = useMissionActions();
  const [filterButton, setFilterButton] = useState<HTMLButtonElement | null>(null);
  const [columnsButton, setColumnsButton] = useState<HTMLButtonElement | null>(null);
  const [open, setOpen] = useState<"filter" | "columns" | null>(null);
  const filtering = isFiltering(filter);
  const toggleQuick = (quick: QuickFilter) =>
    onFilter({ quick: filter.quick.includes(quick) ? filter.quick.filter((q) => q !== quick) : [...filter.quick, quick] });
  const highlight = filter.mode === "highlight";

  const n = <strong>{number(count)}</strong>;
  return (
    <div className="app-toolbar app-pipeline-toolbar" data-selection="chrome">
      <SearchField
        ref={boardSearchRef}
        className="app-pipeline-search"
        label={applicationsSearchLabel()}
        placeholder={applicationsSearchPlaceholder()}
        value={filter.query}
        onChange={(query) => onFilter({ query })}
        trailing={<Kbd>/</Kbd>}
      />
      <div className="results-count">
        {filtering ? (
          <Msg of={SAY[noun].of} args={{ total }} elems={{ n, t: <strong>{number(total)}</strong> }} />
        ) : (
          <Msg of={SAY[noun].count} args={{ count }} elems={{ n }} />
        )}
        {filtering && (
          <>
            {" "}<span className="results-sep" aria-hidden="true">·</span>{" "}
            <Button variant="link" className="ui-btn-quiet" onClick={() => onFilter({ mode: highlight ? "only" : "highlight" })}>
              {highlight ? applicationsModeOnly() : applicationsFilterHighlightInstead()}
            </Button>
            {" "}<span className="results-sep" aria-hidden="true">·</span>{" "}
            <Button variant="link" className="ui-btn-quiet" onClick={() => onFilter({ quick: [], query: "" })}>
              {applicationsFilterReset()}
            </Button>
          </>
        )}
      </div>
      {filter.quick.map((quick) => (
        <FilterChip
          key={quick}
          selected
          className="app-filter-chip"
          aria-label={applicationsFilterRemove({ filter: QUICK_LABEL[quick]() })}
          onClick={() => toggleQuick(quick)}
        >
          {QUICK_LABEL[quick]()}
          <Icon name="close" size={12} />
        </FilterChip>
      ))}

      <div className="app-pipeline-tools">
        <Button
          ref={setFilterButton}
          aria-haspopup="dialog"
          aria-expanded={open === "filter"}
          onClick={() => setOpen(open === "filter" ? null : "filter")}
        >
          <Icon name="sliders" size={14} />{" "}
          {filter.quick.length > 0 ? sharedFiltersCount({ count: filter.quick.length }) : sharedFilters()}
        </Button>
        {columns && (
          <Button
            ref={setColumnsButton}
            aria-haspopup="dialog"
            aria-expanded={open === "columns"}
            aria-label={columns.hidden.length ? applicationsColumnsHidden({ count: columns.hidden.length }) : undefined}
            onClick={() => setOpen(open === "columns" ? null : "columns")}
          >
            <Icon name="columns" size={14} /> {applicationsColumns()}
            {columns.hidden.length > 0 && (
              <span className="app-columns-hidden" aria-hidden="true">
                <Icon name="eyeOff" size={13} />
                {number(columns.hidden.length)}
              </span>
            )}
          </Button>
        )}
      </div>

      <Menu isOpen={open === "filter"} onClose={() => setOpen(null)} anchor={filterButton} label={applicationsFilterMenu()}>
        <MenuGroup label={applicationsFilterQuick()}>
          {QUICK_FILTERS.map((quick) => (
            <MenuCheck
              key={quick}
              checked={filter.quick.includes(quick)}
              onChange={() => toggleQuick(quick)}
              count={number(quickCounts[quick])}
            >
              {QUICK_LABEL[quick]()}
            </MenuCheck>
          ))}
        </MenuGroup>
        <MenuGroup label={applicationsFilterWhile()}>
          {MODES.map(([mode, label, hint]) => (
            <MenuRadio
              key={mode}
              name="app-filter-mode"
              checked={filter.mode === mode}
              onChange={() => onFilter({ mode })}
              hint={hint()}
            >
              {label()}
            </MenuRadio>
          ))}
        </MenuGroup>
      </Menu>

      {columns && (
        <Menu isOpen={open === "columns"} onClose={() => setOpen(null)} anchor={columnsButton} label={applicationsColumns()}>
          <MenuGroup label={applicationsColumnsShow()}>
            {columns.all.map((column) => {
              const shown = !columns.hidden.includes(column.id);
              // The last shown column cannot go: a board always shows one.
              const last = shown && columns.hidden.length === columns.all.length - 1;
              return (
                <MenuCheck
                  key={column.id}
                  checked={shown}
                  disabled={last}
                  title={last ? applicationsColumnHideLast() : undefined}
                  count={number(column.count)}
                  onChange={() => columns.onHidden(
                    shown ? [...columns.hidden, column.id] : columns.hidden.filter((id) => id !== column.id),
                  )}
                >
                  {column.name}
                </MenuCheck>
              );
            })}
          </MenuGroup>
          <MenuGroup>
            <MenuItem icon="eye" disabled={columns.hidden.length === 0} onSelect={() => columns.onHidden([])}>
              {applicationsColumnsShowAll()}
            </MenuItem>
          </MenuGroup>
        </Menu>
      )}
    </div>
  );
}

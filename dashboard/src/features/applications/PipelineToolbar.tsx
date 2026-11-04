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
  applicationsSearchLabel,
  applicationsSearchPlaceholder,
} from "../../copy/gen/applications";
import { Button, FilterChip, Icon, Kbd, Menu, MenuCheck, MenuGroup, MenuItem, MenuRadio, SearchField } from "../../ui";
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

export interface ColumnChoice<C extends string> {
  id: C;
  name: string;
  /** How many the column holds, where that is a fact worth showing. */
  count?: number;
}

export interface PipelineToolbarProps<C extends string = string> {
  filter: BoardFilter;
  onFilter: (next: Partial<BoardFilter>) => void;
  /** How many applications each quick filter would match on its own. */
  quickCounts: Record<QuickFilter, number>;
  /** The view's columns, for the Columns menu. Up next has none. */
  columns?: {
    all: readonly ColumnChoice<C>[];
    hidden: readonly C[];
    onHidden: (hidden: C[]) => void;
    /** A column outside the menu always shows (the List's role), so every
     *  column in it can hide. Unset, the last shown one stays. */
    anchored?: boolean;
  };
}

/**
 * A pipeline view's row of tools: the search, while filtering the way to
 * fade instead and the way back, the filters that are on, and at the row's
 * end the menus. A quick filter shows as a chip only while it is on, so the
 * row holds what narrows the view and nothing else. Each view draws its own,
 * over its own filter.
 */
export function PipelineToolbar<C extends string>({ filter, onFilter, quickCounts, columns }: PipelineToolbarProps<C>) {
  const { boardSearchRef } = useMissionActions();
  const [filterButton, setFilterButton] = useState<HTMLButtonElement | null>(null);
  const [columnsButton, setColumnsButton] = useState<HTMLButtonElement | null>(null);
  const [open, setOpen] = useState<"filter" | "columns" | null>(null);
  const filtering = isFiltering(filter);
  const toggleQuick = (quick: QuickFilter) =>
    onFilter({ quick: filter.quick.includes(quick) ? filter.quick.filter((q) => q !== quick) : [...filter.quick, quick] });
  const highlight = filter.mode === "highlight";

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
      {filtering && (
        <div className="app-filter-ways">
          <Button variant="link" className="ui-btn-quiet" onClick={() => onFilter({ mode: highlight ? "only" : "highlight" })}>
            {highlight ? applicationsModeOnly() : applicationsFilterHighlightInstead()}
          </Button>
          <span className="app-filter-sep" aria-hidden="true">·</span>
          <Button variant="link" className="ui-btn-quiet" onClick={() => onFilter({ quick: [], query: "" })}>
            {applicationsFilterReset()}
          </Button>
        </div>
      )}
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
            {/* A space between the label and the count, so the text shown
                reads as the start of the button's spoken name. */}
            {columns.hidden.length > 0 && " "}
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
              // The last shown column cannot go: a view always shows one.
              const last = !columns.anchored && shown && columns.hidden.length === columns.all.length - 1;
              return (
                <MenuCheck
                  key={column.id}
                  checked={shown}
                  disabled={last}
                  title={last ? applicationsColumnHideLast() : undefined}
                  count={column.count == null ? undefined : number(column.count)}
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

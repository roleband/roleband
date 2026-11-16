import { useEffect, useMemo, useRef, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { api } from "../../../api";
import type { ActivityCategory, ActivityPage } from "../../../api/agentActivity";
import { useAsyncResource } from "../../../hooks/useAsyncResource";
import { useMeasuredCssSize } from "../../../hooks/useMeasuredCssSize";
import { PageHeader } from "../../../patterns/PageHeader";
import { useSearchParam } from "../../../routing/useSearchParam";
import {
  AsyncBoundary, Button, EmptyState, FilterChip, Icon, Menu, MenuGroup, MenuRadio, SearchField,
} from "../../../ui";
import { ActivityInspector } from "./ActivityInspector";
import { ActivityList } from "./ActivityList";
import { CATEGORIES, categoryName } from "./activityText";
import "./activity.css";
import {
  activityCategoryAny,
  activityCategoryMenu,
  activityCustomize,
  activityEmptyBody,
  activityEmptyTitle,
  activityEyebrow,
  activityFilters,
  activityKindAll,
  activityKindChanges,
  activityKindReads,
  activityKindRefused,
  activityLoadFailed,
  activityLoading,
  activityRangeAll,
  activityRangeMenu,
  activityRangeMonth,
  activityRangeToday,
  activityRangeWeek,
  activityRefreshFailed,
  activitySearch,
  activityTitle,
} from "../../../copy/gen/activity";

/** The engine's page size: the list asks for its default. */
export const PAGE_SIZE = 50;
/** The Board's search debounce; a keystroke is not a query. */
const SEARCH_DEBOUNCE_MS = 250;

const KINDS = ["all", "change", "read", "refused"] as const;
type KindFilter = (typeof KINDS)[number];
const KIND_LABEL: Record<KindFilter, () => string> = {
  all: activityKindAll,
  change: activityKindChanges,
  read: activityKindReads,
  refused: activityKindRefused,
};

const ANY = "any";
const CATEGORY_OPTIONS = [ANY, ...CATEGORIES] as const;

const RANGES = ["today", "week", "month", "all"] as const;
type Range = (typeof RANGES)[number];
const RANGE_LABEL: Record<Range, () => string> = {
  today: activityRangeToday,
  week: activityRangeWeek,
  month: activityRangeMonth,
  all: activityRangeAll,
};
/** Days before today a range starts on: today counts as the first. */
const RANGE_DAYS: Record<Exclude<Range, "all">, number> = { today: 0, week: 6, month: 29 };

/** Where a range starts: the reader's own midnight, `days` days back. */
function rangeStart(range: Range, now: Date): string | null {
  if (range === "all") return null;
  const start = new Date(now.getFullYear(), now.getMonth(), now.getDate() - RANGE_DAYS[range]);
  return start.toISOString();
}

/** The Activity screen: every read, change and refusal by a connected
 *  assistant app, newest first, a page of 50 at a time, with the picked
 *  entry in the inspector beside the list. Filters live in the address
 *  (`?kind=`, `?category=`, `?range=`), as does the picked entry (`?entry=`);
 *  the search and the page stay in memory. */
export function ActivityScreen() {
  const [kind, setKind] = useSearchParam("kind", { options: KINDS, fallback: "all" });
  const [category, setCategory] = useSearchParam("category", { options: CATEGORY_OPTIONS, fallback: ANY });
  const [range, setRange] = useSearchParam("range", { options: RANGES, fallback: "month" });
  const [searchParams] = useSearchParams();
  const [search, setSearch] = useState("");
  const [query, setQuery] = useState("");
  const [open, setOpen] = useState<"category" | "range" | null>(null);
  const [categoryButton, setCategoryButton] = useState<HTMLButtonElement | null>(null);
  const [rangeButton, setRangeButton] = useState<HTMLButtonElement | null>(null);
  const root = useRef<HTMLElement>(null);
  const toolbarRef = useRef<HTMLDivElement>(null);
  useMeasuredCssSize({ rootRef: root, elementRef: toolbarRef, property: "--activity-toolbar-h" });

  useEffect(() => {
    const id = window.setTimeout(() => setQuery(search.trim()), SEARCH_DEBOUNCE_MS);
    return () => window.clearTimeout(id);
  }, [search]);

  // Read once per range: a start that moved on every render would refetch forever.
  const since = useMemo(() => rangeStart(range, new Date()), [range]);
  // The pages read so far, by the cursor each was read with. Any filter edit
  // starts over at the newest: a cursor belongs to the list it was read from.
  const filterKey = [kind, category, since, query].join("\u001f");
  const [paging, setPaging] = useState<{ key: string; cursors: (string | null)[] }>({ key: filterKey, cursors: [null] });
  if (paging.key !== filterKey) {
    // Drop the old stack, not just hide it: coming back to a filter is a new list.
    setPaging({ key: filterKey, cursors: [null] });
  }
  const cursors = paging.key === filterKey ? paging.cursors : [null];
  const cursor = cursors[cursors.length - 1];
  const pageIndex = cursors.length - 1;

  const list = useAsyncResource<ActivityPage>(
    (signal) => api.agentActivity({
      q: query || null,
      kind,
      category: category === ANY ? null : (category as ActivityCategory),
      since,
      cursor,
    }, signal),
    [kind, category, since, query, cursor],
  );

  const narrowed = kind !== "all" || category !== ANY || range !== "month" || query !== "";
  const picked = Number(searchParams.get("entry"));

  return (
    <main className="main activity-screen" data-design-system="app" ref={root}>
      <PageHeader
        eyebrow={activityEyebrow()}
        title={activityTitle()}
        actions={(
          <Link className="ui-btn ui-btn-ghost ui-btn-md" to="/settings/intelligence">
            {activityCustomize()}
          </Link>
        )}
      />

      <div
        className="activity-toolbar app-toolbar"
        role="toolbar"
        aria-label={activityFilters()}
        data-selection="chrome"
        ref={toolbarRef}
      >
        <SearchField
          className="activity-search"
          label={activitySearch()}
          placeholder={activitySearch()}
          value={search}
          onChange={setSearch}
        />
        <span className="activity-toolbar-rule" aria-hidden="true" />
        {KINDS.map((option) => (
          <FilterChip key={option} selected={kind === option} onClick={() => setKind(option)}>
            {KIND_LABEL[option]()}
          </FilterChip>
        ))}
        <span className="activity-toolbar-rule" aria-hidden="true" />
        <Button
          ref={setCategoryButton}
          aria-haspopup="dialog"
          aria-expanded={open === "category"}
          onClick={() => setOpen(open === "category" ? null : "category")}
        >
          {category === ANY ? activityCategoryAny() : categoryName(category)} <Icon name="chevronDown" size={14} />
        </Button>
        <Button
          ref={setRangeButton}
          aria-haspopup="dialog"
          aria-expanded={open === "range"}
          onClick={() => setOpen(open === "range" ? null : "range")}
        >
          {RANGE_LABEL[range]()} <Icon name="chevronDown" size={14} />
        </Button>
      </div>

      <Menu isOpen={open === "category"} onClose={() => setOpen(null)} anchor={categoryButton} label={activityCategoryMenu()} align="start">
        <MenuGroup>
          {CATEGORY_OPTIONS.map((option) => (
            <MenuRadio
              key={option}
              name="activity-category"
              checked={category === option}
              onChange={() => { setCategory(option); setOpen(null); }}
            >
              {option === ANY ? activityCategoryAny() : categoryName(option)}
            </MenuRadio>
          ))}
        </MenuGroup>
      </Menu>
      <Menu isOpen={open === "range"} onClose={() => setOpen(null)} anchor={rangeButton} label={activityRangeMenu()} align="start">
        <MenuGroup>
          {RANGES.map((option) => (
            <MenuRadio
              key={option}
              name="activity-range"
              checked={range === option}
              onChange={() => { setRange(option); setOpen(null); }}
            >
              {RANGE_LABEL[option]()}
            </MenuRadio>
          ))}
        </MenuGroup>
      </Menu>

      <AsyncBoundary
        resource={list}
        loading={activityLoading()}
        failed={activityLoadFailed()}
        refreshFailed={activityRefreshFailed()}
        isEmpty={(page) => page.items.length === 0}
        empty={(
          <EmptyState title={activityEmptyTitle({ choice: narrowed ? "yes" : "no" })}>
            {activityEmptyBody({ choice: narrowed ? "yes" : "no" })}
          </EmptyState>
        )}
      >
        {(page) => {
          const selected = page.items.find((item) => item.id === picked) ?? page.items[0];
          return (
            <div className="activity-split">
              <ActivityList
                page={page}
                first={pageIndex * PAGE_SIZE + 1}
                selectedId={selected.id}
                onOlder={page.next_cursor
                  ? () => setPaging({ key: filterKey, cursors: [...cursors, page.next_cursor] })
                  : undefined}
                onNewer={pageIndex > 0
                  ? () => setPaging({ key: filterKey, cursors: cursors.slice(0, -1) })
                  : undefined}
              />
              <ActivityInspector entry={selected} />
            </div>
          );
        }}
      </AsyncBoundary>
    </main>
  );
}

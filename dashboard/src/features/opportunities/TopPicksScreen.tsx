import { shellNavTopPicks } from "../../copy/gen/shell";
import {
  picksEmptyFiltered,
  picksEmptyFilteredTitle,
  picksEmptyRead,
  picksEmptySearchTitle,
  picksEmptyTitle,
  picksEndChecked,
  picksEndPassed,
  picksEndPassedNone,
  picksEndPassedOnly,
  picksEndStopped,
  picksEndStoppedPlain,
  picksEndWaiting,
  picksFreshMore,
  picksHost,
  picksLoadFailed,
  picksLoading,
  picksNoteAsks,
  picksNoteConnect,
  picksNoteDisconnected,
  picksNoteFix,
  picksNotePaused,
  picksRefreshFailed,
  picksRemovedEmpty,
  picksRemovedEmptyTitle,
  picksRemovedPutBack,
  picksRemovedPutBackName,
  picksRemovedSaid,
  picksRemovedWords,
  picksResume,
  picksResumeFailed,
} from "../../copy/gen/picks";
import { sharedNotForMe } from "../../copy/gen/shared";
import {
  radarBoardFreshChanged,
  radarBoardFreshShow,
  radarExactHead,
  radarLoadFailed,
  radarLoading,
  radarOtherHead,
  radarReset,
  radarShowAll,
  radarShowOther,
} from "../../copy/gen/radar";
import { Fragment, useCallback, useEffect, useRef, useState } from "react";
import { api, type Job, type PicksState } from "../../api";
import { relative } from "../../copy/format";
import { useJobActions, useJobWorkspace } from "../../context/JobWorkspace";
import { useAsyncResource } from "../../hooks/useAsyncResource";
import { useMediaQuery } from "../../hooks/useMediaQuery";
import { useMeasuredCssSize } from "../../hooks/useMeasuredCssSize";
import { picksOpened } from "../../hooks/picksDot";
import { PageHeader } from "../../patterns/PageHeader";
import { Pager } from "../../patterns/Pager";
import { RailShell } from "../../patterns/RailShell";
import { CompareBeacon } from "../../patterns/jobs/CompareBeacon";
import { DismissBeacon } from "../../patterns/jobs/DismissBeacon";
import { JobCard } from "../../patterns/jobs/JobCard";
import { JobList } from "../../patterns/jobs/JobList";
import { useSearchParam } from "../../routing/useSearchParam";
import { useSearchParamList } from "../../routing/useSearchParamList";
import { AsyncBoundary, Button, Content, EmptyState, Msg, RAIL_QUERY, RouterLink, useToast } from "../../ui";
import { RowSkeleton } from "../../ui/RowSkeleton";
import { PASSED_OVER_ROUTE } from "../../routing/paths";
import { PickFeedbackDialog, type PickFeedbackReason } from "./PickFeedbackDialog";
import { TopPicksOnboarding } from "./TopPicksOnboarding";
import { BoardFilters } from "./BoardFilters";
import { BoardToolbar } from "./BoardToolbar";
import {
  MODE_PARAM,
  NO_LENSES,
  RESET_FILTERS,
  TOP_PICKS_MEMORY_SCOPE,
  countNarrowingFilters,
  modeFromParam,
  type BoardMode,
} from "./filters";
import { useBoardController, type BoardSurface } from "./useBoardController";
import "../../patterns/jobs/job-page.css";
import "./board-shell.css";
import "./top-picks.css";

/** Settings › AI: where an assistant is connected, and its connection fixed. */
const SETTINGS_AI_PATH = "/settings/intelligence";
// Top picks reads with the Radar's lenses off, so there is none to clear.
const nothingToClear = () => {};
/** Showing's positions on Top picks: the picks, and the picks the person
 *  marked Not for me. `?show=not-for-me` is the second, as on the Radar. */
const TOP_PICKS_MODES = ["open", "dismissed"] as const satisfies readonly BoardMode[];
const TOP_PICKS_MODE_PARAMS = TOP_PICKS_MODES.map((mode) => MODE_PARAM[mode]);

/* Top picks: the few roles the person's assistant judged worth a move. It is
   the Radar's list, toolbar, filter column and row, narrowed to the picks,
   with each pick's reasons under its row. Its filters and its search are its
   own. Showing, at the foot of the filters, switches to the picks the person
   marked Not for me, each with the reason they gave and the way back. Before
   setup it is the onboarding (TopPicksOnboarding), which gives way to the
   list once the checks are set up. Opening it puts out the rail's dot.
   Its title stands where the Radar's does, so the two screens' toolbars and
   lists start on one line. The onboarding leads with its own headline, so
   there the title stays the page's heading off screen. */
export function TopPicksScreen() {
  useEffect(() => {
    picksOpened();
  }, []);
  const state = useAsyncResource(() => api.picksState(), []);
  const { mutate } = state;
  const onPicksChange = useCallback((next: PicksState) => mutate(() => next), [mutate]);
  const rootRef = useRef<HTMLElement>(null);
  return (
    <main className="main board-main job-margin-page" data-design-system="app" ref={rootRef}>
      <PageHeader title={shellNavTopPicks()} offScreen={state.data?.state === "never_set_up"} />
      <AsyncBoundary resource={state} loading={picksLoading()} failed={picksLoadFailed()}>
        {(picks) => picks.state === "never_set_up"
          ? <TopPicksOnboarding picks={picks} onPicksChange={onPicksChange} />
          : <TopPicksList picks={picks} rootRef={rootRef} onPicksChange={onPicksChange} />}
      </AsyncBoundary>
    </main>
  );
}

function TopPicksList({ picks, rootRef, onPicksChange }: {
  picks: PicksState;
  rootRef: React.RefObject<HTMLElement | null>;
  onPicksChange: (next: PicksState) => void;
}) {
  const [companyParam, onCompanyParamChange] = useSearchParamList("company");
  const [search, setSearch] = useState("");
  const surface: BoardSurface = { topPicks: true, search };
  const [showParam, onShowParamChange] = useSearchParam("show", {
    options: TOP_PICKS_MODE_PARAMS,
    fallback: MODE_PARAM.open,
  });
  const mode = modeFromParam(showParam);
  // Stable: the controller mirrors the mode from an effect.
  const onModeChange = useCallback(
    (next: BoardMode) => onShowParamChange(MODE_PARAM[next]),
    [onShowParamChange],
  );
  const {
    filters, facets, facetsError, retryFacets, list, listError, listRefreshError, retryList, refreshList, baseline,
    total, isDirect, relatedTotal, expanded, pageableTotal,
    update, updateFilters, onSort, toggleFav, dismiss, dismissal, undoDismiss, fresh, showFresh,
  } = useBoardController({ companyParam, onCompanyParamChange, mode, onModeChange }, surface);
  const takeFresh = useCallback(() => {
    showFresh();
    picksOpened();
  }, [showFresh]);
  // The pick whose Not for me is asking why, before anything is removed.
  const [asking, setAsking] = useState<Job | null>(null);
  const keep = useCallback(() => setAsking(null), []);
  const remove = useCallback((job: Job, reason: PickFeedbackReason | null) => {
    setAsking(null);
    dismiss(job, reason);
  }, [dismiss]);
  const { viewedIds, compareIds, compareFull, compareCap } = useJobWorkspace();
  const { openJob, toggleCompare } = useJobActions();
  const narrowed = countNarrowingFilters(filters, NO_LENSES) > 0;
  // The picks marked Not for me: a different list, not a narrowing of this one.
  const inLens = filters.dismissed_only;
  const resetAll = useCallback(() => updateFilters(RESET_FILTERS), [updateFilters]);
  const railMode = useMediaQuery(RAIL_QUERY);
  const toolbarRef = useRef<HTMLDivElement>(null);
  const hostRef = useRef<HTMLDivElement>(null);
  useMeasuredCssSize({ rootRef, elementRef: toolbarRef, property: "--board-toolbar-h" });

  const renderRow = useCallback(
    (job: Job) => (
      <JobCard
        key={job.id}
        job={job}
        newMark={false}
        viewed={job.viewed_at != null || viewedIds.has(job.id)}
        onOpen={() => openJob(job.id, job.company)}
        onToggleFav={() => toggleFav(job)}
        // A removed pick's button puts it back, as on the Radar's Not for me.
        /* A marked pick goes back by the link under it, the one way back on this list. */
        onDismiss={job.is_dismissed ? undefined : () => setAsking(job)}
        under={job.is_dismissed
          ? <RemovedPickUnder job={job} onPutBack={() => dismiss(job)} />
          : job.pick_reasons && job.pick_reasons.length > 0 && <PickReasons reasons={job.pick_reasons} />}
        compareOn={compareIds.has(job.id)}
        onToggleCompare={() => toggleCompare(job.id)}
        compareDisabled={compareFull}
        compareCap={compareCap}
      />
    ),
    [compareCap, compareFull, compareIds, dismiss, openJob, toggleCompare, toggleFav, viewedIds],
  );

  /* The dismissed row's seam, where the way back sits level in the margin
     (patterns/jobs/margin.css), as on the Radar. */
  const withSeams = (rows: Job[], section: "items" | "related_items") => {
    const here = dismissal?.section === section ? dismissal : null;
    if (!here) return rows.map(renderRow);
    const seam = <div key={`seam-${here.job.id}`} className="job-seam" data-seam-for={here.job.id} />;
    const out: React.ReactNode[] = [];
    rows.forEach((row) => {
      if (here.beforeId === row.id) out.push(seam);
      out.push(renderRow(row));
    });
    if (here.beforeId === null || !rows.some((row) => row.id === here.beforeId)) out.push(seam);
    return out;
  };

  const register = (
    <BoardFilters
      facets={facets}
      facetsError={facetsError}
      onRetryFacets={retryFacets}
      filters={filters}
      update={updateFilters}
      mode={mode}
      onModeChange={onModeChange}
      modes={TOP_PICKS_MODES.map((value) => ({ value, label: value === "open" ? shellNavTopPicks() : sharedNotForMe() }))}
      memoryScope={TOP_PICKS_MEMORY_SCOPE}
    />
  );

  const hidden = baseline.total ?? 0;
  // As on the Radar, the lens's empty teaches it and leads back to the picks;
  // under a search or filter the marked picks exist, so the restriction speaks.
  // The hidden count is the open picks' baseline, so the lens shows none.
  const empty = inLens && !filters.q.trim() && !narrowed ? (
    <EmptyState title={picksRemovedEmptyTitle()}>
      {picksRemovedEmpty()}{" "}
      <Button variant="link" onClick={() => onModeChange("open")}>{radarShowAll()}</Button>
    </EmptyState>
  ) : filters.q.trim() ? (
    <EmptyState title={picksEmptySearchTitle()} />
  ) : narrowed && hidden > 0 && !inLens ? (
    <EmptyState title={picksEmptyFilteredTitle()}>
      {picksEmptyFiltered({ count: hidden })}{" "}
      <Button variant="link" onClick={resetAll}>{radarReset()}</Button>
    </EmptyState>
  ) : narrowed && (inLens || baseline.total === null) ? (
    <EmptyState title={picksEmptyFilteredTitle()}>
      <Button variant="link" onClick={resetAll}>{radarReset()}</Button>
    </EmptyState>
  ) : (
    <>
      <EmptyState title={picksEmptyTitle()}>{picksEmptyRead({ count: picks.read_this_week })}</EmptyState>
      <PicksEnd picks={picks} />
    </>
  );

  const content = (
    <div className="board-content job-margin-host" ref={hostRef}>
      <AsyncBoundary
        resource={{
          data: list, error: list ? null : listError, loading: !list && !listError,
          retry: retryList, refresh: refreshList, refreshError: listRefreshError,
        }}
        loading={radarLoading()}
        failed={radarLoadFailed()}
        refreshFailed={picksRefreshFailed()}
        skeleton={<JobList><RowSkeleton rows={4} /></JobList>}
      >
        {() => total === 0 && relatedTotal === 0 ? empty : (
          <>
            {isDirect && list!.items.length > 0 && (
              <h2 className="search-section-head">{radarExactHead({ count: list!.items.length })}</h2>
            )}
            <JobList sortControl={{ sort: filters.sort, order: filters.order, onSort }}>
              {withSeams(list!.items, "items")}
            </JobList>
            {isDirect && relatedTotal > 0 && !expanded && (
              <div className="search-related-disclosure">
                <Button className="search-related-toggle" onClick={() => update({ include_related: true, offset: 0 })}>
                  {radarShowOther({ count: relatedTotal })}
                </Button>
              </div>
            )}
            {expanded && (
              <>
                <h2 className="search-section-head">{radarOtherHead({ count: relatedTotal })}</h2>
                <JobList>{withSeams(list!.related_items ?? [], "related_items")}</JobList>
              </>
            )}
            <Pager total={pageableTotal} pageSize={filters.limit} offset={filters.offset}
              onOffsetChange={(offset) => update({ offset })} />
            {!isDirect && !inLens && filters.offset + list!.items.length >= total && <PicksEnd picks={picks} />}
          </>
        )}
      </AsyncBoundary>
      {list && <CompareBeacon host={hostRef} anchorVersion={list} />}
      {list && dismissal && (
        <DismissBeacon
          key={dismissal.job.id}
          host={hostRef}
          anchorVersion={list}
          dockSlot={1}
          dismissal={dismissal}
          onUndo={undoDismiss}
        />
      )}
      <PickFeedbackDialog job={asking} onRemove={remove} onKeep={keep} />
    </div>
  );

  return (
    <>
      <BoardToolbar
        toolbarRef={toolbarRef}
        register={register}
        filters={filters}
        update={updateFilters}
        total={total}
        baseTotal={baseline.total}
        baselineError={baseline.error}
        onRetryBaseline={baseline.retry}
        onModeChange={onModeChange}
        railMode={railMode}
        newSignalsOnly={false}
        clearNewSignals={nothingToClear}
        repostsOnly={false}
        clearReposts={nothingToClear}
        query={{ search, setSearch }}
        noun="pick"
      />
      <PicksNotes picks={picks} onPicksChange={onPicksChange} />
      {/* A check made a pick, or a scan ended, while the list was open: as on
          the Radar, the update waits for the reader, so no row moves under
          them mid-read. Taking it is opening Top picks, so the dot goes out. */}
      {fresh && (
        <div className="empty-hint" role="status">
          {fresh.more > 0 ? picksFreshMore({ count: fresh.more }) : radarBoardFreshChanged()}{" "}
          <Button variant="ghost" size="sm" onClick={takeFresh}>
            {radarBoardFreshShow()}
          </Button>
        </div>
      )}
      <RailShell railMode={railMode} register={register} className="board-shell">
        {content}
      </RailShell>
    </>
  );
}

/** A pick's reasons, under its row, with no label: each line's opening fact
 *  in the row's ink and the rest of it muted, at one weight. A reason saved
 *  with no opening is a plain line. The assistant wrote them: they are
 *  content, never translated. */
export function PickReasons({ reasons }: { reasons: NonNullable<Job["pick_reasons"]> }) {
  return (
    <ul className="pick-reasons">
      {reasons.map((reason, i) => (
        <li key={i}>
          {reason.opening && <Content className="pick-reason-opening" text={reason.opening} />}
          <Content text={reason.rest} />
        </li>
      ))}
    </ul>
  );
}

/** Under a pick the person marked Not for me: the assistant's reasons, then
 *  what the person said (the reason they chose, their own words) and the way
 *  back, which clears Not for me so the role is a pick and on the Radar
 *  again. Their words are content, never translated. */
function RemovedPickUnder({ job, onPutBack }: { job: Job; onPutBack: () => void }) {
  const said = job.dismiss_reason && job.dismiss_reason !== "other" ? job.dismiss_reason : null;
  // The sentence around the words ends them, so their own full stop goes.
  const words = job.dismiss_reason_text?.trim().replace(/[.。]+$/u, "");
  return (
    <div className="pick-removed">
      {job.pick_reasons && job.pick_reasons.length > 0 && <PickReasons reasons={job.pick_reasons} />}
      <p className="pick-said">
        {said && <>{picksRemovedSaid({ reason: said })}{" "}</>}
        {words && <><Msg of={picksRemovedWords} elems={{ words: <Content text={words} /> }} />{" "}</>}
        <Button
          variant="link"
          aria-label={picksRemovedPutBackName({ title: job.title })}
          onClick={(event) => { event.stopPropagation(); onPutBack(); }}
          onKeyDown={(event) => event.stopPropagation()}
        >
          {picksRemovedPutBack()}
        </Button>
      </p>
    </div>
  );
}

const ago = (at: string) => relative((Date.parse(at) - Date.now()) / 1000);

/** The Radar's note, above the list, for each way the checks need the person
 *  to act, with the action in it, until it is put right. A state that asks
 *  nothing of the person (late, stopped early) is said where the list ends. */
export function PicksNotes({ picks, onPicksChange }: { picks: PicksState; onPicksChange: (next: PicksState) => void }) {
  const { toast } = useToast();
  const [resuming, setResuming] = useState(false);
  const host = picksHost({ host: picks.routine_host ?? "" });
  const notes: { key: string; body: React.ReactNode }[] = [];
  if (picks.state === "off") {
    const resume = () => {
      setResuming(true);
      api.setPicksMode("on")
        .then(onPicksChange)
        .catch(() => toast({ key: "top-picks", text: picksResumeFailed(), tone: "error" }))
        .finally(() => setResuming(false));
    };
    notes.push({
      key: "paused",
      body: <>{picksNotePaused()}{" "}<Button variant="link" onClick={resume} disabled={resuming}>{picksResume()}</Button></>,
    });
  } else {
    if (picks.routine_host && picks.routine_host_connection === null) {
      notes.push({
        key: "disconnected",
        body: <>{picksNoteDisconnected({ host })}{" "}<RouterLink variant="link" to={SETTINGS_AI_PATH}>{picksNoteConnect()}</RouterLink></>,
      });
    } else if (picks.routine_host_connection === "rule_missing") {
      notes.push({
        key: "asks",
        body: <>{picksNoteAsks({ host })}{" "}<RouterLink variant="link" to={SETTINGS_AI_PATH}>{picksNoteFix()}</RouterLink></>,
      });
    }
  }
  if (notes.length === 0) return null;
  return (
    <div className="picks-notes">
      {notes.map((note) => <p key={note.key} className="search-truncation-note is-stacked" role="note">{note.body}</p>)}
    </div>
  );
}

/** Where the list ends, in its quiet ink: who checked last and when, what of
 *  the checks needs no action (roles waiting while they are late, why the last
 *  one stopped early), and the way to what was passed over this week. That
 *  last sentence is there every week, plain text in a week with nothing
 *  passed over, so the way to Passed over never moves. */
export function PicksEnd({ picks }: { picks: PicksState }) {
  const check = picks.last_check;
  const sentences: React.ReactNode[] = [];
  if (check) {
    sentences.push(picksEndChecked({ when: ago(check.finished_at), host: picksHost({ host: check.host ?? "" }) }));
  }
  if (picks.health === "late" && picks.waiting > 0) sentences.push(picksEndWaiting({ count: picks.waiting }));
  if (picks.health === "stopped_early") {
    const reason = check?.note?.trim().replace(/[.。!！]+$/u, "");
    // The reason is the assistant's own words, set into the sentence as content.
    sentences.push(reason ? <Msg of={picksEndStopped} elems={{ reason: <Content text={reason} /> }} /> : picksEndStoppedPlain());
  }
  if (picks.passed_this_week > 0) {
    const passed = <RouterLink variant="link" to={PASSED_OVER_ROUTE}>{picksEndPassed({ count: picks.passed_this_week })}</RouterLink>;
    sentences.push(<Msg of={picksEndPassedOnly} elems={{ passed }} />);
  } else {
    sentences.push(picksEndPassedNone());
  }
  return (
    <p className="board-list-end" role="note">
      {sentences.map((sentence, i) => <Fragment key={i}>{i > 0 && " "}{sentence}</Fragment>)}
    </p>
  );
}

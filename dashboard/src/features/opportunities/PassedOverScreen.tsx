import { useCallback, useState } from "react";
import { DEFAULT_FILTERS, api, type Job, type PassCode, type PassedOver, type RemovedPicks } from "../../api";
import {
  picksPassBelowLevel,
  picksPassHardRule,
  picksPassHardRuleNamed,
  picksPassNotBetter,
  picksPassNotReal,
  picksPassOffDirection,
  picksPassOther,
  picksPassOutOfReach,
  picksPassedBack,
  picksPassedClose,
  picksPassedEmpty,
  picksPassedEmptyTitle,
  picksPassedHeading,
  picksPassedLoadFailed,
  picksPassedLoading,
  picksPassedPutBack,
  picksPassedPutBackFailed,
  picksPassedRead,
  picksPassedRemoved,
  picksPassedRuled,
  picksPassedSaid,
  picksPassedShowAll,
  picksPassedSummary,
  picksPassedWords,
} from "../../copy/gen/picks";
import { number } from "../../copy/format";
import { list as joined } from "../../copy/format/display";
import { radarSaveFailed, radarUnsaveFailed } from "../../copy/gen/radar";
import { useJobActions, useJobWorkspace } from "../../context/JobWorkspace";
import { useAsyncResource } from "../../hooks/useAsyncResource";
import { useRoleSaves } from "../../hooks/useRoleSaves";
import { PageHeader } from "../../patterns/PageHeader";
import { JobCard } from "../../patterns/jobs/JobCard";
import { JobList } from "../../patterns/jobs/JobList";
import { AsyncBoundary, Button, Content, EmptyState, Msg, RouterLink, useToast } from "../../ui";
import { PickReasons } from "./TopPicksScreen";
import "../../patterns/jobs/job-page.css";
import "./board-shell.css";
import "./top-picks.css";

const TOP_PICKS_PATH = "/top-picks";
/** The near misses shown before Show all. */
const FIRST_NEAR_MISSES = 3;

const PASS_LABEL: Record<Exclude<PassCode, "hard_rule">, () => string> = {
  off_direction: picksPassOffDirection,
  below_level: picksPassBelowLevel,
  out_of_reach: picksPassOutOfReach,
  not_better: picksPassNotBetter,
  not_real: picksPassNotReal,
  other: picksPassOther,
};

interface PassedOverData {
  passed: PassedOver;
  removed: RemovedPicks["picks"];
  /** The rows of the removed picks and the near misses, by id. */
  rows: Map<number, Job>;
}

async function load(signal: AbortSignal): Promise<PassedOverData> {
  const [passed, removed] = await Promise.all([api.picksPassed(signal), api.picksRemoved(signal)]);
  // By id, a role is listed whatever its status and whether or not the person
  // marked it Not for me, so the removed picks come back with the near misses.
  const ids = [...new Set([...removed.picks.map((pick) => pick.job_id), ...passed.near_misses.map((miss) => miss.job_id)])];
  const rows = ids.length === 0
    ? []
    : (await api.jobs({ ...DEFAULT_FILTERS, ids, status: "", sort: "first_seen", limit: Math.min(ids.length, 500) }, signal)).items;
  return { passed, removed: removed.picks, rows: new Map(rows.map((row) => [row.id, row])) };
}

/* Passed over: what the person's assistant read this week and did not pick,
   and what the person removed. The picks they removed come first, each with
   why and a way back; then the near misses, each with the one thing that
   failed; then the passes by why, and what the hard rules ruled out before
   any reading. It is a page of Top picks: the rail keeps Top picks marked and
   the top bar names the page. */
export function PassedOverScreen() {
  const data = useAsyncResource(load, []);
  return (
    <main className="main passed-over job-margin-page" data-design-system="app">
      <PageHeader title={picksPassedHeading()} offScreen />
      <AsyncBoundary resource={data} loading={picksPassedLoading()} failed={picksPassedLoadFailed()}>
        {(loaded) => <PassedOverPage data={loaded} onPutBack={(jobId) => data.mutate((current) => current && {
          ...current, removed: current.removed.filter((pick) => pick.job_id !== jobId),
        })} />}
      </AsyncBoundary>
    </main>
  );
}

function PassedOverPage({ data, onPutBack }: { data: PassedOverData; onPutBack: (jobId: number) => void }) {
  const { passed, removed, rows } = data;
  const [allNear, setAllNear] = useState(false);
  const { toast } = useToast();
  const { viewedIds, compareIds, compareFull, compareCap } = useJobWorkspace();
  const { openJob, toggleCompare } = useJobActions();
  const [saved, setSaved] = useState<ReadonlyMap<number, boolean>>(new Map());

  const saveRole = useRoleSaves();

  const toggleFav = useCallback((job: Job) => {
    const was = saved.get(job.id) ?? job.is_favorite;
    const next = !was;
    saveRole({
      jobId: job.id, was, next,
      show: (on) => setSaved((prev) => new Map(prev).set(job.id, on)),
      send: () => api.setFavorite(job.id, next),
    }).catch(() => toast({
      key: "passed-over",
      text: <Msg of={next ? radarSaveFailed : radarUnsaveFailed} elems={{ title: <Content text={job.title} /> }} />,
    }));
  }, [saved, saveRole, toast]);

  const putBack = useCallback((job: Job) => {
    api.undismissJob(job.id)
      .then(() => onPutBack(job.id))
      .catch(() => toast({
        key: "passed-over",
        text: <Msg of={picksPassedPutBackFailed} elems={{ title: <Content text={job.title} /> }} />,
        tone: "error",
      }));
  }, [onPutBack, toast]);

  const row = (job: Job, under: React.ReactNode) => (
    <JobCard
      key={job.id}
      job={{ ...job, is_favorite: saved.get(job.id) ?? job.is_favorite }}
      newMark={false}
      viewed={job.viewed_at != null || viewedIds.has(job.id)}
      onOpen={() => openJob(job.id, job.company)}
      onToggleFav={() => toggleFav(job)}
      under={under}
      compareOn={compareIds.has(job.id)}
      onToggleCompare={() => toggleCompare(job.id)}
      compareDisabled={compareFull}
      compareCap={compareCap}
    />
  );

  const removedRows = removed.flatMap((pick) => {
    const job = rows.get(pick.job_id);
    return job ? [{ pick, job }] : [];
  });
  const nearRows = passed.near_misses.flatMap((miss) => {
    const job = rows.get(miss.job_id);
    return job ? [{ miss, job }] : [];
  });
  const shownNear = allNear ? nearRows : nearRows.slice(0, FIRST_NEAR_MISSES);
  const readAndPassed = passed.passes.reduce((sum, group) => sum + group.count, 0);
  // The rules are the brief's own words: content inside the label.
  const passLabel = (code: PassCode) => code === "hard_rule"
    ? (passed.judged_rules.length > 0
      ? <Msg of={picksPassHardRuleNamed} elems={{ rules: <Content text={joined(passed.judged_rules, "or")} /> }} />
      : picksPassHardRule())
    : PASS_LABEL[code]();

  const back = <RouterLink variant="link" to={TOP_PICKS_PATH}>{picksPassedBack()}</RouterLink>;
  const nothing = removedRows.length === 0 && nearRows.length === 0 && readAndPassed === 0 && passed.ruled_out === 0;

  return (
    <>
      {nothing ? (
        <EmptyState title={picksPassedEmptyTitle()} actions={back}>{picksPassedEmpty()}</EmptyState>
      ) : (
        <p className="passed-summary">
          {passed.passed_this_week > 0 && <span>{picksPassedSummary({ count: passed.passed_this_week })}</span>}
          {back}
        </p>
      )}

      {removedRows.length > 0 && (
        <section className="passed-section" aria-labelledby="passed-removed">
          <h2 id="passed-removed" className="search-section-head">{picksPassedRemoved({ count: removedRows.length })}</h2>
          <JobList columns={false}>
            {removedRows.map(({ pick, job }) => row(job, (
              <p className="passed-said">
                {pick.reason && pick.reason !== "other" && <>{picksPassedSaid({ reason: pick.reason })}{" "}</>}
                {pick.reason_text && <><Msg of={picksPassedWords} elems={{ words: <Content text={pick.reason_text} /> }} />{" "}</>}
                <Button
                  variant="link"
                  onClick={(event) => { event.stopPropagation(); putBack(job); }}
                  onKeyDown={(event) => event.stopPropagation()}
                >
                  {picksPassedPutBack()}
                </Button>
              </p>
            )))}
          </JobList>
        </section>
      )}

      {nearRows.length > 0 && (
        <section className="passed-section" aria-labelledby="passed-close">
          <h2 id="passed-close" className="search-section-head">{picksPassedClose({ count: nearRows.length })}</h2>
          <JobList columns={false}>
            {shownNear.map(({ miss, job }) => row(job, <PickReasons reasons={[miss.reason]} />))}
          </JobList>
          {!allNear && nearRows.length > FIRST_NEAR_MISSES && (
            <p className="passed-more">
              <Button variant="link" className="ui-btn-quiet" onClick={() => setAllNear(true)}>
                {picksPassedShowAll({ count: nearRows.length })}
              </Button>
            </p>
          )}
        </section>
      )}

      {readAndPassed > 0 && (
        <section className="passed-section" aria-labelledby="passed-read">
          <h2 id="passed-read" className="search-section-head">{picksPassedRead({ count: readAndPassed })}</h2>
          <ul className="passed-tally">
            {passed.passes.map((group) => (
              <li key={group.code}><span>{passLabel(group.code)}</span><span className="passed-count">{number(group.count)}</span></li>
            ))}
          </ul>
        </section>
      )}

      {passed.ruled_out > 0 && (
        <section className="passed-section" aria-labelledby="passed-ruled">
          <h2 id="passed-ruled" className="search-section-head">{picksPassedRuled({ count: passed.ruled_out })}</h2>
          <ul className="passed-tally">
            {passed.ruled_out_by_rule.map((rule) => (
              <li key={rule.rule}><Content text={rule.rule} /><span className="passed-count">{number(rule.count)}</span></li>
            ))}
          </ul>
        </section>
      )}
    </>
  );
}

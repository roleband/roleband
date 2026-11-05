import { useMemo } from "react";
import { DEFAULT_FILTERS, api, type ApplicationCard, type Job } from "../../api";
import { useSourceSwitch } from "../../context/SyncState";
import { useAsyncResource, useRefetchOn } from "../../hooks/useAsyncResource";

/** The most postings one read returns: the list route's own cap. */
const PAGE = 500;

/**
 * The postings behind the pipeline's applications, by job id: pay, place,
 * level and age, read from the jobs list the way Radar reads them, so the
 * List shows the same figures under the same pay source. Every status, since
 * an application outlives its posting.
 *
 * Optional: until it answers, or when it fails, a row shows the application
 * without its posting's facts, never with wrong ones. A role added to the
 * pipeline re-reads in place, with the rows already shown kept.
 */
export function usePostings(cards: readonly ApplicationCard[]): ReadonlyMap<number, Job> {
  const ids = useMemo(() => [...new Set(cards.map((card) => card.job_id))].sort((a, b) => a - b), [cards]);
  const key = ids.join(",");
  const ready = ids.length > 0;
  // No ids is no read: an empty `ids` filter is no filter, and would list Radar.
  const postings = useAsyncResource(
    (signal) => ready
      ? api.jobs({ ...DEFAULT_FILTERS, ids: ids.slice(0, PAGE), status: "", limit: PAGE }, signal)
      : Promise.resolve(null),
    [ready],
  );
  useRefetchOn(key, postings.refresh);
  useSourceSwitch(postings.refresh);
  return useMemo(
    () => new Map((postings.data?.items ?? []).map((job) => [job.id, job])),
    [postings.data],
  );
}

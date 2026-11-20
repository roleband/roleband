import { useCallback, useEffect, useRef, useState } from "react";
import { api, type Job, type PostingTextResult } from "../../api";

/** How long a read runs before the section says the employer's site is slow
 *  and offers the posting there. The server gives a read up after 20 s. */
export const SLOW_AFTER_MS = 6000;

export type TextReadPhase = "reading" | "slow" | "failed";

/** The text of a posting that opened with none, while it is read: what the
 *  Description section shows in its place, and the way to ask again. */
export type TextRead = { phase: TextReadPhase; retry: () => void };

/**
 * Reads the text of a posting that opened with none, AFTER the screen shows,
 * so an open never waits on the employer's site. The detail says whether
 * there is anything to read (`description_readable`); the read is asked once
 * per open of a posting, and again within that open only by `retry`. A new
 * open after a failure asks again: the server answers it from its cool-down
 * without asking the site.
 *
 * `show` writes an answer's text into the posting on screen. `reread` reads
 * the posting again after a fresh read, because its text also moves what the
 * pay panel says.
 *
 * Returns what the section shows instead of text, or null. A readable
 * posting counts as reading from its first frame, so "No description" never
 * flashes before the read begins. An answer for a posting no longer on
 * screen, or one a retry superseded, is dropped; a posting whose answer was
 * dropped is asked again when it is shown again. Nothing is retired on
 * unmount: StrictMode's practice unmount keeps refs, and a retired first
 * read would never be asked again.
 */
export function usePostingText(
  job: Job | null,
  show: (id: number, result: PostingTextResult) => void,
  reread: () => void,
): { read: TextRead | null; arrived: boolean } {
  const id = job?.id ?? null;
  const readable = job?.description_readable === true;
  const [state, setState] = useState<{ id: number; phase: TextReadPhase } | null>(null);
  const [arrivedFor, setArrivedFor] = useState<number | null>(null);
  const asked = useRef<number | null>(null);
  /** Each posting's latest read: the newest is the one whose answer counts,
   *  and a posting with one still in flight is never asked a second time. */
  const attempts = useRef(new Map<number, number>());
  const inFlight = useRef(new Set<number>());
  const shown = useRef(id);
  shown.current = id;

  const start = useCallback(
    (jobId: number, retry: boolean) => {
      const mine = (attempts.current.get(jobId) ?? 0) + 1;
      attempts.current.set(jobId, mine);
      inFlight.current.add(jobId);
      const current = () => attempts.current.get(jobId) === mine && shown.current === jobId;
      /** An answer that came while another posting was on screen is dropped,
       *  and frees this posting to be asked again when it comes back: kept as
       *  asked, a posting whose read failed while away would show a line that
       *  never ends. */
      const landed = () => {
        if (shown.current !== jobId && asked.current === jobId) asked.current = null;
        return current();
      };
      // Over whatever an earlier read of this posting left: a retry leaves
      // its failure, and a new open of the posting starts over.
      setState({ id: jobId, phase: "reading" });
      const slow = window.setTimeout(() => {
        if (current()) setState({ id: jobId, phase: "slow" });
      }, SLOW_AFTER_MS);
      api
        .readPostingText(jobId, retry)
        .then((result) => {
          if (!landed()) return;
          if (result.outcome === "failed") {
            setState({ id: jobId, phase: "failed" });
            return;
          }
          setState(null);
          show(jobId, result);
          if (result.description_text || result.description_sections.length) setArrivedFor(jobId);
          if (result.outcome === "read") reread();
        })
        .catch(() => {
          if (landed()) setState({ id: jobId, phase: "failed" });
        })
        .finally(() => {
          window.clearTimeout(slow);
          if (attempts.current.get(jobId) === mine) inFlight.current.delete(jobId);
        });
    },
    [show, reread],
  );

  useEffect(() => {
    // Another posting is shown: one whose read has answered is asked again on
    // its next open, failed or not. One still being read is not asked twice,
    // whatever was shown meanwhile; its answer lands now that it is shown.
    if (asked.current !== id && !(asked.current != null && inFlight.current.has(asked.current))) {
      asked.current = null;
    }
    if (!readable || id == null || asked.current === id) return;
    asked.current = id;
    if (!inFlight.current.has(id)) start(id, false);
  }, [readable, id, start]);

  const retry = useCallback(() => {
    if (shown.current != null) start(shown.current, true);
  }, [start]);

  const arrived = id != null && arrivedFor === id;
  if (id == null) return { read: null, arrived };
  if (state && state.id === id) return { read: { phase: state.phase, retry }, arrived };
  if (readable) return { read: { phase: "reading", retry }, arrived };
  return { read: null, arrived };
}

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
 * per posting per open, and again only by `retry`.
 *
 * `show` writes an answer's text into the posting on screen. `reread` reads
 * the posting again after a fresh read, because its text also moves what the
 * pay panel says.
 *
 * Returns what the section shows instead of text, or null. A readable
 * posting counts as reading from its first frame, so "No description" never
 * flashes before the read begins. An answer for a posting no longer on
 * screen, or one a retry superseded, is dropped. Nothing is retired on
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
  const attempt = useRef(0);
  const shown = useRef(id);
  shown.current = id;

  const start = useCallback(
    (jobId: number, retry: boolean) => {
      const mine = ++attempt.current;
      const current = () => attempt.current === mine && shown.current === jobId;
      // Over whatever an earlier read of this posting left: a retry leaves
      // its failure, and a new open of the posting starts over.
      setState({ id: jobId, phase: "reading" });
      const slow = window.setTimeout(() => {
        if (current()) setState({ id: jobId, phase: "slow" });
      }, SLOW_AFTER_MS);
      api
        .readPostingText(jobId, retry)
        .then((result) => {
          if (!current()) return;
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
          if (current()) setState({ id: jobId, phase: "failed" });
        })
        .finally(() => window.clearTimeout(slow));
    },
    [show, reread],
  );

  useEffect(() => {
    if (!readable || id == null || asked.current === id) return;
    asked.current = id;
    start(id, false);
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

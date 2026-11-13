import { type RefObject, useLayoutEffect, useRef, useState } from "react";
import { flushSync } from "react-dom";
import type { Job } from "../../api";

/* One posting giving place to another in a cover that stays open (docs/ui.md
   "Job detail"). The posting on show stays until the next one has loaded, so
   the screen is never emptied to a loading line between two postings; then
   the reading area turns to it in one view transition, and the bar stays
   where it is.

   The turn is the browser's: it draws the old reading area as a picture,
   lets the document change under it, and brings the new one in
   (job-detail.css, "the turn"). A browser without view transitions, and a
   person who asked for reduced motion, get the same change with no motion. */

/** Which way the next posting comes: along the list it was opened from, or
 *  from a link on the posting itself. */
export type Turn = "next" | "previous" | "open";

/** The name the reading area carries for the length of one turn. It is set on
 *  the one element that turns: a posting opened over a posting leaves two
 *  reading areas in the document, and a name on both would cancel the turn. */
const NAME = "posting";
/** The attribute on the root element the turn's keyframes read their way from. */
const WAY = "postingTurn";

/** What the new posting's own parts may take to arrive before it is shown,
 *  and how long the reading area must have stood unchanged to count as whole. */
const SETTLE_CAP = 240;
const SETTLE_QUIET = 40;
/** How long the browser has to begin a turn. It begins one with a frame, and
 *  a window that draws none (covered, or in the background) would keep the
 *  old posting for as long as it stays so. Past this the turn is skipped and
 *  the posting changes with no motion. */
const BEGIN_WITHIN = 200;

/** Resolves once `box` has stopped changing: the posting's own late reads
 *  (its twins, its places, its list of similar roles) land before the picture
 *  of it is taken, so they are part of what turns in and never a second
 *  redraw after it. Timers only: the browser holds every frame while a turn
 *  waits, so nothing that runs with a frame would. */
function settled(box: HTMLElement): Promise<void> {
  return new Promise((resolve) => {
    let quiet = window.setTimeout(done, SETTLE_QUIET);
    const cap = window.setTimeout(done, SETTLE_CAP);
    const watch = new MutationObserver(() => {
      window.clearTimeout(quiet);
      quiet = window.setTimeout(done, SETTLE_QUIET);
    });
    watch.observe(box, { childList: true, subtree: true });
    function done() {
      window.clearTimeout(quiet);
      window.clearTimeout(cap);
      watch.disconnect();
      resolve();
    }
  });
}

/** The new posting opens at `top` (its own top, unless it is one gone back
 *  to), with the keyboard still on it: a link on the old posting had focus
 *  and left with it, so the dialog that holds the cover takes it, as it does
 *  when the cover opens. Focus on the bar (the pager) stays where it is. */
function arrive(box: HTMLElement, top: number): void {
  box.scrollTop = top;
  const dialog = box.closest<HTMLElement>('[role="dialog"]');
  if (dialog && !dialog.contains(document.activeElement)) dialog.focus({ preventScroll: true });
}

/** The turn under way, so one that another has overtaken leaves the
 *  newer one's marks alone when it ends. */
let latest = 0;

/** This browser held the page still before it began a turn: one that draws
 *  the pictures in software can take seconds over the first. It gets no more
 *  turns for the life of the page; the posting changes with no motion. */
let heldStill = false;

/** Tests start each case with a browser not yet found slow. */
export function forgetTurnSpeed(): void {
  heldStill = false;
}

/** Turns the reading area `box` to what `commit` draws, the way `way` says,
 *  scrolled to `top`. The returned function cancels a turn another has
 *  overtaken: its `commit` then never runs. */
export function turnPosting(box: HTMLElement | null, way: Turn, commit: () => void, top = 0): () => void {
  const still = typeof matchMedia === "function" && matchMedia("(prefers-reduced-motion: reduce)").matches;
  const plain = still || heldStill || document.visibilityState === "hidden" || typeof document.startViewTransition !== "function";
  if (!box || plain) {
    commit();
    // After React has drawn the commit, which it does before any microtask.
    if (box) queueMicrotask(() => arrive(box, top));
    return () => undefined;
  }
  // Before the change is drawn a turn can be cancelled; once it is drawn the
  // turn is the browser's to finish, and the caller's own redraw (which the
  // change causes) must not cut it short.
  let state: "waiting" | "cancelled" | "drawn" = "waiting";
  const mine = ++latest;
  const root = document.documentElement;
  box.style.setProperty("view-transition-name", NAME);
  root.dataset[WAY] = way;
  const clear = () => {
    if (latest !== mine) return;
    box.style.removeProperty("view-transition-name");
    delete root.dataset[WAY];
  };
  const asked = performance.now();
  const transition = document.startViewTransition(async () => {
    window.clearTimeout(late);
    if (performance.now() - asked > 2 * BEGIN_WITHIN) heldStill = true;
    if (state !== "waiting") return;
    state = "drawn";
    flushSync(commit);
    arrive(box, top);
    await settled(box);
  });
  // Skipping a turn that has not begun makes the browser run its change at
  // once. A timer that fires on time found a window that draws no frames; one
  // that fires long after it was due was held up with everything else.
  const late = window.setTimeout(() => {
    if (performance.now() - asked > 2 * BEGIN_WITHIN) heldStill = true;
    transition.skipTransition();
  }, BEGIN_WITHIN);
  // A turn that is skipped or overtaken rejects `ready`, never `finished`.
  transition.ready.catch(() => undefined);
  void transition.finished.then(clear, clear);
  return () => {
    if (state !== "waiting") return;
    state = "cancelled";
    window.clearTimeout(late);
    transition.skipTransition();
  };
}

/**
 * The posting to draw. It follows `fresh`, the posting the route asked for,
 * except between two postings: while the next one loads the last one stays,
 * and once the next is in hand the reading area turns to it.
 *
 * `turning` is true while the posting drawn is not the one the route names:
 * what is drawn then is for the eye only, and its controls would act on the
 * wrong posting.
 */
export function useShownPosting(
  fresh: Job | null,
  { wanted, loading, failed, place, box, returning = false }: {
    /** The posting the route names. */
    wanted: number;
    loading: boolean;
    failed: boolean;
    /** The posting's place in the list it was opened from, if it has one. */
    place: number | null;
    /** The cover's scroll box: the reading area that turns. */
    box: RefObject<HTMLElement | null>;
    /** The route was reached by going back or forward: a posting this cover
     *  has shown before opens where it was left, not at its top. */
    returning?: boolean;
  },
): { job: Job | null; turning: boolean } {
  const [shown, setShown] = useState<{ job: Job; place: number | null } | null>(null);
  const incoming = fresh && shown && fresh.id !== shown.job.id ? fresh : null;
  // The same posting read again or changed in place, and the first one a
  // cover opens on: drawn at once. A posting that failed to load leaves
  // nothing to hold.
  if (fresh && !incoming && shown?.job !== fresh) setShown({ job: fresh, place });
  if (failed && shown) setShown(null);

  const stood = shown?.place ?? null;
  const leaving = shown?.job.id ?? null;
  /** Where each posting this cover has shown was left. */
  const left = useRef(new Map<number, number>());
  useLayoutEffect(() => {
    if (!incoming) return;
    const along = stood != null && place != null && stood !== place;
    const way: Turn = along ? (place > stood ? "next" : "previous") : "open";
    if (leaving != null && box.current) left.current.set(leaving, box.current.scrollTop);
    const top = returning ? left.current.get(incoming.id) ?? 0 : 0;
    return turnPosting(box.current, way, () => setShown({ job: incoming, place }), top);
  }, [incoming, stood, leaving, place, box, returning]);

  const job = incoming ? shown!.job : fresh ?? (loading ? shown?.job ?? null : null);
  return { job, turning: job != null && job.id !== wanted };
}

/** `value`, or the last one seen before `hold` began: what belongs to the
 *  posting on show while the next one loads. */
export function useHeld<T>(value: T, hold: boolean): T {
  const [kept, setKept] = useState(value);
  if (!hold && !Object.is(kept, value)) setKept(value);
  return hold ? kept : value;
}

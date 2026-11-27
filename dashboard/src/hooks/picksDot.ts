import { useSyncExternalStore } from "react";
import { shellApi, type PicksState } from "../api/shell";
import { useVisibleInterval } from "./useVisibleInterval";

/* The Top picks rail dot: lit while a pick has arrived since the person last
 * opened Top picks (`unseen_pick`), never a count and never the checks'
 * health. Module state, because the rail reads it and the screen puts it out,
 * and the two share no component.
 *
 * Every read and every opening takes the next generation and only the newest
 * may write, so a poll that left before the screen opened cannot light the dot
 * again with the answer it carried. */

let unseen = false;
let generation = 0;
// Counts the picks that arrived since the last opening, as the reads see them,
// which an open Top picks screen offers as an update: the dot lighting is one;
// while it stays lit, a check that closed after the last read is another, since
// it may have made a pick the offer on screen lacks.
let arrivals = 0;
let lastCheck: string | null = null;
const listeners = new Set<() => void>();

function publish(state: Pick<PicksState, "unseen_pick" | "last_check"> | false, mine: number): void {
  if (mine !== generation) return;
  const next = state ? state.unseen_pick : false;
  const check = state ? state.last_check?.finished_at ?? null : lastCheck;
  const arrived = next && (!unseen || check !== lastCheck);
  lastCheck = check;
  if (!arrived && next === unseen) return;
  unseen = next;
  if (arrived) arrivals += 1;
  listeners.forEach((listener) => listener());
}

function subscribe(listener: () => void): () => void {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

function read(): void {
  const mine = ++generation;
  shellApi.picksState()
    .then((state) => publish(state, mine))
    .catch(() => {});
}

/** Whether the rail's Top picks item wears its dot; read every minute the
 *  page is visible, as the rail's counts are. */
export function usePicksDot(): boolean {
  useVisibleInterval(read, 60_000);
  return useSyncExternalStore(subscribe, () => unseen);
}

/** A number that grows each time a pick arrives after the last opening, as the
 *  rail's read sees it; Top picks re-reads its list when it changes. */
export function usePickArrivals(): number {
  return useSyncExternalStore(subscribe, () => arrivals);
}

/** Top picks is on screen: the dot goes out at once, and the engine's answer
 *  to the opening is what stands after it. A failed opening leaves the next
 *  read to light the dot again, since nothing was recorded. */
export function picksOpened(): void {
  const mine = ++generation;
  publish(false, mine);
  shellApi.picksOpened()
    .then((state) => publish(state, mine))
    .catch(() => {});
}

/** Each test starts with the dot out and no read in flight. */
export function forgetPicksDot(): void {
  generation += 1;
  unseen = false;
  lastCheck = null;
}

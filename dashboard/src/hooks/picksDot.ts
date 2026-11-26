import { useSyncExternalStore } from "react";
import { shellApi } from "../api/shell";
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
const listeners = new Set<() => void>();

function publish(next: boolean, mine: number): void {
  if (mine !== generation || next === unseen) return;
  unseen = next;
  listeners.forEach((listener) => listener());
}

function subscribe(listener: () => void): () => void {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

function read(): void {
  const mine = ++generation;
  shellApi.picksState()
    .then((state) => publish(state.unseen_pick, mine))
    .catch(() => {});
}

/** Whether the rail's Top picks item wears its dot; read every minute the
 *  page is visible, as the rail's counts are. */
export function usePicksDot(): boolean {
  useVisibleInterval(read, 60_000);
  return useSyncExternalStore(subscribe, () => unseen);
}

/** Top picks is on screen: the dot goes out at once, and the engine's answer
 *  to the opening is what stands after it. A failed opening leaves the next
 *  read to light the dot again, since nothing was recorded. */
export function picksOpened(): void {
  const mine = ++generation;
  publish(false, mine);
  shellApi.picksOpened()
    .then((state) => publish(state.unseen_pick, mine))
    .catch(() => {});
}

/** Each test starts with the dot out and no read in flight. */
export function forgetPicksDot(): void {
  generation += 1;
  unseen = false;
}

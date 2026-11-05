import type { UsageState } from "../api";

/* An answer to the sharing question recorded on a screen of its own (the
   welcome), told to the shell. The shell asks a configured install from the
   state it read at startup, so without this it could ask again what was just
   answered. Its own module: the shell loads it at startup, and `sharing.ts`
   only once something is shared. */

const listeners = new Set<(state: UsageState) => void>();

/** Tells the shell the state an answer recorded. */
export function sharingAnswered(state: UsageState): void {
  for (const listener of listeners) listener(state);
}

/** Calls `listener` with each answer recorded outside the shell; returns the way to stop. */
export function onSharingAnswered(listener: (state: UsageState) => void): () => void {
  listeners.add(listener);
  return () => { listeners.delete(listener); };
}

import { shellApi, type ViewChoices } from "../api/shell";

/* The person's view choices, read once per page load. main.tsx starts the
   read before the first render, beside the company names, so a screen opens
   already arranged; the store that screens use (`viewChoices.ts`) adopts the
   answer. Only this read is in the startup chunk. */

type Choices = ViewChoices["choices"];

let reading: Promise<Choices | null> | null = null;
let held: Choices | null = null;
/** Moves on with each reset, so a read begun before one is not held after it. */
let generation = 0;

/** The read's answer once it has come back; null before, or after a failure. */
export const heldViewChoices = (): Choices | null => held;

/** Starts the read, or joins the one under way. A failed read answers null
 *  and the next call reads again. */
export function readViewChoices(): Promise<Choices | null> {
  const mine = generation;
  reading ??= Promise.resolve().then(() => shellApi.viewChoices()).then(
    (read) => {
      if (mine === generation) held = read.choices;
      return read.choices;
    },
    () => {
      if (mine === generation) reading = null;
      return null;
    },
  );
  return reading;
}

/** Forgets the read. For tests. */
export function forgetViewChoicesRead(): void {
  generation += 1;
  reading = null;
  held = null;
}

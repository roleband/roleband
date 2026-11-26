import { useEffect, useSyncExternalStore } from "react";
import { shellApi } from "../api/shell";
import { browserChoices, forgetBrowserKeys } from "./viewChoicesInBrowser";
import { forgetViewChoicesRead, heldViewChoices, readViewChoices } from "./viewChoicesRead";

/* How the person arranged what the screens show: the Workspace's blocks, the
 * Pipeline's columns, crossings dismissed, a posting's folded section, each
 * screen's filters. Kept in the database with their settings, one choice per
 * name, so a cleared browser or another one shows the same screens
 * (docs/decisions/0027-view-choices-in-local-database.md).
 *
 * Read once per page load, before the first render when the answer is quick
 * (main.tsx), and held here for every screen: a screen reads its choice at
 * once, as it read browser storage before. A change shows at once and is saved
 * in the background. Saves of one choice go one at a time, and while one is on
 * its way only the latest change waits behind it, so a burst of changes is two
 * saves and the database keeps the last. What a value means is each screen's
 * own business: a screen decodes what it reads, as it did from the browser. */

type Choices = Record<string, unknown>;
type State = "reading" | "answered" | "failed";

let choices: Choices = {};
let state: State | null = null;
/** Moves on with each reset, so a read or a save begun before one lands
 *  nowhere after it. */
let generation = 0;
/** Choices made on this page before the read answered: they outrank it. */
const madeHere = new Set<string>();
const listeners = new Set<() => void>();
const publish = (next: Choices) => {
  choices = next;
  listeners.forEach((listener) => listener());
};

function adopt(read: Choices): void {
  const mine = Object.fromEntries([...madeHere].filter((name) => name in choices).map((name) => [name, choices[name]]));
  state = "answered";
  publish({ ...read, ...mine });
  moveFromBrowser();
}

/** Starts the read when nothing has asked yet; `again` asks once more after
 *  a failure, which only a screen opening does, never every render. */
function ensureRead(again = false): void {
  if (state === "reading" || state === "answered" || (state === "failed" && !again)) return;
  const held = heldViewChoices();
  if (held) return adopt(held);
  state = "reading";
  const mine = generation;
  void readViewChoices().then((read) => {
    if (mine !== generation) return;
    if (read) adopt(read);
    else {
      state = "failed";
      publish(choices);
    }
  });
}

/** Every choice as last made; empty until the read answers. */
export function viewChoicesNow(): Choices {
  ensureRead();
  return choices;
}

/** One choice as last made, or undefined when the person has not made it
 *  (or the read has not answered yet): the screen then shows its default. */
export function viewChoice(name: string): unknown {
  ensureRead();
  return choices[name];
}

const queued = new Map<string, { value: unknown; settled: ((saved: boolean) => void)[] }>();
const sending = new Set<string>();

async function send(name: string): Promise<void> {
  const mine = generation;
  sending.add(name);
  for (let next = queued.get(name); next; next = queued.get(name)) {
    queued.delete(name);
    const { value } = next;
    const saved = await Promise.resolve().then(() => shellApi.saveViewChoice(name, value)).then(() => true, () => false);
    next.settled.forEach((settle) => settle(saved));
    // After a reset the saves queued are the new page's, sent by its own loop.
    if (mine !== generation) return;
  }
  sending.delete(name);
}

/** Makes a choice: shown at once, then saved. Answers false when the save
 *  failed; the choice still holds on this page until it is reloaded. */
export function setViewChoice(name: string, value: unknown): Promise<boolean> {
  ensureRead();
  madeHere.add(name);
  publish({ ...choices, [name]: value });
  return new Promise((settle) => {
    const waiting = queued.get(name);
    if (waiting) {
      waiting.value = value;
      waiting.settled.push(settle);
      return;
    }
    queued.set(name, { value, settled: [settle] });
    if (!sending.has(name)) void send(name);
  });
}

function onViewChoices(listener: () => void): () => void {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

const snapshot = () => choices;
const answered = () => state === "answered" || state === "failed";

/** Every choice, kept current: a late read or a change made elsewhere on the
 *  page draws again. */
export function useViewChoices(): Choices {
  ensureRead();
  return useSyncExternalStore(onViewChoices, snapshot);
}

/** Whether the read has answered, so a screen whose first frame would show
 *  a default and then jump can wait for it. A failed read counts: the screen
 *  shows its defaults. */
export function useViewChoicesAnswered(): boolean {
  useEffect(() => ensureRead(true), []);
  return useSyncExternalStore(onViewChoices, answered);
}

/** Moves the choices a browser kept before they moved here: each into the
 *  database when the database holds none, then out of the browser once it is
 *  saved there. A save that fails leaves the browser's copy for the next
 *  visit to move. */
function moveFromBrowser(): void {
  for (const { keys, choices: kept } of browserChoices()) {
    const missing = Object.entries(kept).filter(([name]) => !(name in choices));
    void Promise.all(missing.map(([name, value]) => setViewChoice(name, value))).then(
      (saved) => saved.every(Boolean) && forgetBrowserKeys(keys),
    );
  }
}

/** Forgets every choice and save, as on a fresh page; `seed` stands in for
 *  the database's answer. For tests. */
export function forgetViewChoices(seed?: Choices): void {
  generation += 1;
  choices = seed ?? {};
  state = seed ? "answered" : null;
  madeHere.clear();
  queued.clear();
  sending.clear();
  forgetViewChoicesRead();
}

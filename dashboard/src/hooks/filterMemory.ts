/* Filter memory — the store behind "the app remembers how you narrowed it".
 *
 * A reader who filtered the radar down to three companies last night should
 * find those three companies there this morning, and should not have to say
 * so again after a reload, a nav-rail round trip, a restart, or another
 * browser. Filters that live in the address survive a reload on their own;
 * filters held in `useState` die with the screen unless they are remembered
 * here, as one of the person's view choices (`viewChoices.ts`), kept in the
 * database.
 *
 * Two rules this file exists to hold:
 *
 *  1. **What comes back is untrusted data, not state.** A stored blob
 *     outlives the code that wrote it: a shipped key can change type and a
 *     facet slug can be retired. So a scope declares a SHAPE — one decoder per
 *     key it is willing to restore — and `decodeShape` returns only what that
 *     shape accepts. A key the shape does not name is not persisted and
 *     cannot be restored, which makes the shape the whitelist as well as the
 *     validator.
 *  2. **Nothing here may take a screen down.** A read before the choices have
 *     come back is "nothing remembered", and a write that fails to save still
 *     holds for this visit.
 *
 * This is the storage half only, and it is pure — no React. The hooks are
 * `useFilterMemory.ts`; the address-backed variant is
 * `routing/useRememberedParams.ts`.
 */

import { setViewChoice, viewChoice } from "./viewChoices";

/** A stored array is bounded on both axes: a corrupt blob must not be able to
 *  build a 10,000-term query string out of one restore. */
const MAX_VALUES = 200;
const MAX_VALUE_LENGTH = 120;

/** Each screen's memory is the view choice `filters.<key>`; the database
 *  knows every key a screen uses. */
const choiceName = (key: string) => `filters.${key}`;

/** The blob last written for `key`, or null when none is remembered. */
export function readEntry(key: string): unknown {
  return viewChoice(choiceName(key)) ?? null;
}

export function writeEntry(key: string, value: unknown): void {
  void setViewChoice(choiceName(key), value);
}

/** Forgets `key`: read back as nothing, apart from a blob left empty. */
export function forgetEntry(key: string): void {
  void setViewChoice(choiceName(key), null);
}

/* ---- the shape: one decoder per restorable key ---------------------------- */

/** Returns the value when the raw JSON is acceptable, `undefined` when it is
 *  not. `undefined` means "keep the default" — never "the default is wrong". */
export type Decoder<V> = (raw: unknown) => V | undefined;

/** What a scope is willing to remember. A key absent from the shape is neither
 *  written nor restored, so this is the persistence whitelist. */
export type MemoryShape<T> = { [K in keyof T]?: Decoder<T[K]> };

/** A facet selection: a bounded list of short strings. Values are NOT checked
 *  against the live vocabulary — a slug retired since the write simply matches
 *  nothing, which is the same outcome as an empty facet, while a round trip
 *  through the facets endpoint would make restoring wait on a request. */
export const slugs: Decoder<string[]> = (raw) => {
  if (!Array.isArray(raw)) return undefined;
  const clean = raw.filter(
    (value): value is string => typeof value === "string" && value.length > 0 && value.length <= MAX_VALUE_LENGTH,
  );
  return clean.slice(0, MAX_VALUES);
};

export const flag: Decoder<boolean> = (raw) => (typeof raw === "boolean" ? raw : undefined);

/** A number-or-nothing field (a comp floor, a posted-within window). NaN and
 *  Infinity are what `JSON.parse` gives back for a hand-edited blob, and both
 *  reach the wire as `base_min=null`-shaped nonsense, so both are refused. */
export const amount: Decoder<number | null> = (raw) => {
  if (raw === null) return null;
  return typeof raw === "number" && Number.isFinite(raw) ? raw : undefined;
};

/** A closed set — the only decoder that can say "this stored value is not one
 *  of the set", because it is the only one handed the vocabulary. */
export const oneOf =
  <T extends string>(options: readonly T[]): Decoder<T> =>
  (raw) =>
    typeof raw === "string" && (options as readonly string[]).includes(raw) ? (raw as T) : undefined;

/** Free text, bounded. A closed set, such as a sort key (`JobSort`), takes
 *  `oneOf` instead. */
export const text: Decoder<string> = (raw) =>
  typeof raw === "string" && raw.length <= MAX_VALUE_LENGTH ? raw : undefined;

/** Everything the shape accepts out of one stored blob. Keys the shape does
 *  not name, and values it refuses, are simply absent from the result — so the
 *  caller's own defaults show through. */
export function decodeShape<T>(shape: MemoryShape<T>, raw: unknown): Partial<T> {
  if (raw == null || typeof raw !== "object" || Array.isArray(raw)) return {};
  const stored = raw as Record<string, unknown>;
  const out: Partial<T> = {};
  for (const key of Object.keys(shape) as (keyof T)[]) {
    if (!(key in stored)) continue;
    const decode = shape[key];
    if (!decode) continue;
    const value = decode(stored[key as string]);
    if (value !== undefined) out[key] = value;
  }
  return out;
}

/** The payload to store: the shaped keys of a live value, and nothing else.
 *  Paging, the search query and transport keys stay out of memory by being
 *  out of the shape. */
export function encodeShape<T extends object>(shape: MemoryShape<T>, value: T): Partial<T> {
  const out: Partial<T> = {};
  for (const key of Object.keys(shape) as (keyof T)[]) {
    if (value[key] !== undefined) out[key] = value[key];
  }
  return out;
}

/* ---- the address variant: remembered query params ------------------------- */

/** A snapshot of the query params a screen owns, in URL order. Each key maps
 *  to every value it carries, because a facet lens repeats its key. */
export type ParamSnapshot = Record<string, string[]>;

export function decodeParams(raw: unknown, keys: readonly string[]): ParamSnapshot {
  if (raw == null || typeof raw !== "object" || Array.isArray(raw)) return {};
  const stored = raw as Record<string, unknown>;
  const out: ParamSnapshot = {};
  for (const key of keys) {
    const values = slugs(stored[key]);
    if (values && values.length > 0) out[key] = values;
  }
  return out;
}

/* Where the posting's own history crosses the application's: the posting
 * closed, reopened or changed its pay after the person applied. The posting
 * and the application are two separate records; the facts worth a line are
 * where they meet. */

import type { ApplicationDetail, JobDetail } from "../../api";

export type CrossingKind = "closed" | "reopened" | "pay";

export interface Crossing {
  kind: CrossingKind;
  /** When the posting changed. */
  at: string;
  /** Whole days between applying and the change. */
  days: number;
}

const DAY = 86_400_000;

/** The latest crossing, or null. Only a change after the person applied
 *  counts: before it, the posting they applied to already said so. */
export function latestCrossing(
  lifecycle: JobDetail["lifecycle"],
  reached: ApplicationDetail["stages_reached"],
): Crossing | null {
  const applied = reached.find((step) => step.stage === "applied");
  if (!applied) return null;
  const from = new Date(applied.at).getTime();
  let latest: Crossing | null = null;
  for (const entry of lifecycle) {
    const at = new Date(entry.at).getTime();
    if (at <= from) continue;
    const kind: CrossingKind | null = entry.event_type === "closed"
      ? "closed"
      : entry.event_type === "reopened"
        ? "reopened"
        : entry.event_type === "changed" && "disclosed_base" in entry.detail ? "pay" : null;
    if (!kind) continue;
    if (!latest || at >= new Date(latest.at).getTime()) {
      latest = { kind, at: entry.at, days: Math.floor((at - from) / DAY) };
    }
  }
  return latest;
}

/** Whether the posting's pay changed after the person applied. */
export function payChangedSinceApplied(
  lifecycle: JobDetail["lifecycle"],
  reached: ApplicationDetail["stages_reached"],
): boolean {
  const applied = reached.find((step) => step.stage === "applied");
  if (!applied) return false;
  const from = new Date(applied.at).getTime();
  return lifecycle.some((entry) =>
    entry.event_type === "changed" && "disclosed_base" in entry.detail && new Date(entry.at).getTime() > from);
}

const DISMISSED_KEY = "roleband.pipeline-crossings-dismissed";

/** A crossing the reader dismissed, by role and instant: a later change to
 *  the same posting is a new line. Kept per browser. */
export const crossingKey = (jobId: number, crossing: Crossing): string => `${jobId}:${crossing.kind}:${crossing.at}`;

export function readDismissed(): Set<string> {
  try {
    const raw = localStorage.getItem(DISMISSED_KEY);
    const parsed: unknown = raw ? JSON.parse(raw) : [];
    return new Set(Array.isArray(parsed) ? parsed.filter((key): key is string => typeof key === "string") : []);
  } catch {
    return new Set();
  }
}

export function writeDismissed(keys: ReadonlySet<string>): void {
  try {
    localStorage.setItem(DISMISSED_KEY, JSON.stringify([...keys]));
  } catch {
    // A browser that keeps no storage shows the line again next visit.
  }
}

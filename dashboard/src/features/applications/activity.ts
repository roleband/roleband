/* An application's feed, apart from how it looks: comments stand on their
 * own, the recorded changes between two comments fold into one quiet line,
 * and the whole history is parted by month, with the points a person can
 * jump to. Pure, so the tests hold the folding and the jumps without a
 * screen. */

import type { ActivityItem, ApplicationDetail } from "../../api";
import { STAGE_LABEL } from "../../copy/vocabulary";
import {
  applicationsFeedAdded,
  applicationsFeedAddedAt,
  applicationsFeedMoved,
  applicationsFeedNextStep,
  applicationsFeedNotes,
  applicationsFeedPriority,
  applicationsFeedUpdated,
} from "../../copy/gen/applications";

export type ActivityComment = Extract<ActivityItem, { kind: "comment" }>;
export type ActivityEvent = Extract<ActivityItem, { kind: "event" }>;

export type FeedMode = "comments" | "all";

export type FeedEntry =
  | { kind: "comment"; comment: ActivityComment }
  /** Recorded changes in a row. Folded, they read as one line that names what
   *  changed; unfolded, one line each. */
  | { kind: "events"; key: string; events: ActivityEvent[] };

/** The feed as the reader sees it, newest first as the server sends it. With
 *  `comments`, each run of changes between two comments is one entry; with
 *  `all`, every change is its own. */
export function feedEntries(items: readonly ActivityItem[], mode: FeedMode): FeedEntry[] {
  const entries: FeedEntry[] = [];
  for (const item of items) {
    if (item.kind === "comment") {
      entries.push({ kind: "comment", comment: item });
      continue;
    }
    const last = entries[entries.length - 1];
    if (mode === "comments" && last?.kind === "events") last.events.push(item);
    else entries.push({ kind: "events", key: `event-${item.id}`, events: [item] });
  }
  return entries;
}

/** Whether the reader opened this run. A run is known by every change in it,
 *  not by one: the person's next write joins the newest run at its top, and
 *  deleting a comment joins the runs on either side, yet both stay the run
 *  that was opened. */
export function runOpened(events: readonly ActivityEvent[], opened: ReadonlySet<number>): boolean {
  return events.some((event) => opened.has(event.id));
}

/** What one recorded change did, one phrase per field it touched. A move
 *  names the stage; the next step's text and date are one change. */
export function eventChanges(event: ActivityEvent): string[] {
  const changes: string[] = [];
  if (event.event_type === "created") {
    changes.push(event.to_stage === "saved" ? applicationsFeedAdded() : applicationsFeedAddedAt({ stage: STAGE_LABEL[event.to_stage] }));
  } else if (event.from_stage !== event.to_stage) {
    changes.push(applicationsFeedMoved({ stage: STAGE_LABEL[event.to_stage] }));
  }
  if (event.changed.includes("priority")) changes.push(applicationsFeedPriority());
  if (event.changed.includes("notes")) changes.push(applicationsFeedNotes());
  if (event.changed.includes("next_action") || event.changed.includes("next_action_due")) {
    changes.push(applicationsFeedNextStep());
  }
  return changes.length ? changes : [applicationsFeedUpdated()];
}

/** Every distinct change a run of events made, newest first. */
export function runChanges(events: readonly ActivityEvent[]): string[] {
  return [...new Set(events.flatMap(eventChanges))];
}

export interface FeedMonth {
  /** The month in the reader's zone, as "YYYY-MM". */
  key: string;
  /** Its first day, at the reader's midnight. */
  start: Date;
  entries: FeedEntry[];
  /** Every entry of the month in the feed's order, folded or not. */
  items: ActivityItem[];
  comments: number;
}

/** The month an instant falls in, in the reader's zone, as "YYYY-MM". */
export function monthKey(at: string | Date): string {
  const day = new Date(at);
  return `${day.getFullYear()}-${String(day.getMonth() + 1).padStart(2, "0")}`;
}

/** The feed parted by month, newest first. A folded run of changes never
 *  crosses a month: each month folds its own. */
export function feedMonths(items: readonly ActivityItem[], mode: FeedMode): FeedMonth[] {
  const groups: ActivityItem[][] = [];
  let open: string | null = null;
  for (const item of items) {
    const key = monthKey(item.created_at);
    if (key !== open) {
      groups.push([]);
      open = key;
    }
    groups[groups.length - 1].push(item);
  }
  return groups.map((group) => {
    const first = new Date(group[0].created_at);
    return {
      key: monthKey(first),
      start: new Date(first.getFullYear(), first.getMonth(), 1),
      entries: feedEntries(group, mode),
      items: group,
      comments: group.filter((item) => item.kind === "comment").length,
    };
  });
}

/** The key one entry is found by on the page: a comment's, or a change's. */
export const itemKey = (item: ActivityItem): string => `${item.kind}-${item.id}`;

export type JumpKind = "recent" | "applied" | "interview" | "offer" | "beginning";

export interface JumpPoint {
  kind: JumpKind;
  at: Date;
  /** The entry the jump lands on. */
  item: ActivityItem;
}

/** The entry nearest an instant; of two as near, the newer. */
export function nearestItem(items: readonly ActivityItem[], at: Date): ActivityItem | undefined {
  let best: ActivityItem | undefined;
  let gap = Infinity;
  for (const item of items) {
    const distance = Math.abs(new Date(item.created_at).getTime() - at.getTime());
    if (distance < gap) {
      best = item;
      gap = distance;
    }
  }
  return best;
}

/** The moments of this application a person remembers it by, newest first
 *  except the beginning, which closes the list. A moment the application has
 *  not reached is left out, and so is an interview still to come: the feed
 *  holds only what happened. Each lands on the entry nearest its moment. */
export function jumpPoints(
  items: readonly ActivityItem[],
  detail: Pick<ApplicationDetail, "stages_reached" | "interviews">,
  now: Date,
): JumpPoint[] {
  if (items.length === 0) return [];
  const reached = (stage: string) => detail.stages_reached.find((step) => step.stage === stage)?.at;
  const held = detail.interviews
    .filter((interview) => interview.outcome !== "cancelled" && new Date(interview.scheduled_at) <= now)
    .map((interview) => new Date(interview.scheduled_at).getTime());
  const moments: { kind: JumpKind; at: Date | null }[] = [
    { kind: "offer", at: reached("offer") ? new Date(reached("offer")!) : null },
    { kind: "interview", at: held.length ? new Date(Math.min(...held)) : null },
    { kind: "applied", at: reached("applied") ? new Date(reached("applied")!) : null },
  ];
  const points: JumpPoint[] = [{ kind: "recent", at: new Date(items[0].created_at), item: items[0] }];
  for (const { kind, at } of moments.filter((moment) => moment.at != null).sort((a, b) => b.at!.getTime() - a.at!.getTime())) {
    const item = nearestItem(items, at!);
    if (item) points.push({ kind, at: at!, item });
  }
  const last = items[items.length - 1];
  if (items.length > 1) points.push({ kind: "beginning", at: new Date(last.created_at), item: last });
  return points;
}

/* An application's feed, apart from how it looks: comments stand on their
 * own, and the recorded changes between two comments fold into one quiet
 * line. Pure, so the tests hold the folding without a screen. */

import type { ActivityItem } from "../../api";
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

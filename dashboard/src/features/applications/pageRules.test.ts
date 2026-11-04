import { describe, expect, it } from "vitest";
import type { ActivityItem } from "../../api";
import { msg } from "../../test/msg";
import { applicationCardFixture as card } from "../../test/fixtures";
import { eventChanges, feedEntries, runChanges, type ActivityEvent } from "./activity";
import { placeInColumn } from "./board";
import { latestCrossing, payChangedSinceApplied } from "./crossings";
import { upNext } from "./dueByDay";

/* The application page's rules and Up next's, as the spec states them: the
 * feed folds the changes between two comments, a posting change counts only
 * after the person applied, a step past its date leads Up next while an
 * interview never does, and the page steps through its column in the
 * board's order. */

const NOW = new Date("2026-11-04T12:00:00");
const hours = (n: number) => new Date(NOW.getTime() + n * 3_600_000).toISOString();
const days = (n: number) => hours(n * 24);

const event = (id: number, over: Partial<ActivityEvent> = {}): ActivityEvent => ({
  kind: "event", id, created_at: days(-id), actor: "user", source: "app",
  event_type: "updated", from_stage: "applied", to_stage: "applied", changed: [], ...over,
});
const comment = (id: number): ActivityItem => ({
  kind: "comment", id, created_at: days(-id), actor: "user", source: "app", body: `Comment ${id}`, edited_at: null,
});

describe("the feed", () => {
  const items: ActivityItem[] = [
    comment(1),
    event(2, { from_stage: "researching", to_stage: "applied", changed: ["stage"] }),
    event(3, { changed: ["priority"] }),
    comment(4),
    event(5, { changed: ["notes"] }),
  ];

  it("folds the changes between two comments into one entry, and keeps a comment between runs apart", () => {
    const entries = feedEntries(items, "comments");
    expect(entries.map((entry) => entry.kind === "comment" ? `c${entry.comment.id}` : entry.events.map((e) => e.id)))
      .toEqual(["c1", [2, 3], "c4", [5]]);
  });

  it("gives every change its own entry under All activity", () => {
    const entries = feedEntries(items, "all");
    expect(entries.filter((entry) => entry.kind === "events").map((entry) => entry.kind === "events" && entry.events.length))
      .toEqual([1, 1, 1]);
  });

  it("names each change once, and the next step's text and date as one change", () => {
    expect(eventChanges(event(1, { changed: ["next_action", "next_action_due"] })))
      .toEqual([msg("applications-feed-next-step")]);
    expect(eventChanges(event(1, { from_stage: "applied", to_stage: "offer", changed: ["stage", "priority"] })))
      .toEqual([msg("applications-feed-moved", { stage: "Offer" }), msg("applications-feed-priority")]);
    expect(eventChanges(event(1, { event_type: "created", from_stage: null, to_stage: "saved", changed: ["stage"] })))
      .toEqual([msg("applications-feed-added")]);
    expect(eventChanges(event(1, { changed: [] }))).toEqual([msg("applications-feed-updated")]);
  });

  it("lists a run's changes without repeating one", () => {
    expect(runChanges([event(1, { changed: ["priority"] }), event(2, { changed: ["priority"] })]))
      .toEqual([msg("applications-feed-priority")]);
  });
});

describe("a crossing", () => {
  const reached = [{ stage: "applied" as const, at: days(-10) }];

  it("counts only a posting change after the person applied, and says how many days after", () => {
    const lifecycle = [
      { event_type: "changed", detail: { disclosed_base: {} }, at: days(-12) },
      { event_type: "closed", detail: {}, at: days(-6) },
    ];
    expect(latestCrossing(lifecycle, reached)).toEqual({ kind: "closed", at: days(-6), days: 4 });
    expect(latestCrossing(lifecycle.slice(0, 1), reached)).toBeNull();
  });

  it("is a pay change only when the change moved the posted band", () => {
    const other = [{ event_type: "changed", detail: { title: {} }, at: days(-2) }];
    const pay = [{ event_type: "changed", detail: { disclosed_base: {} }, at: days(-2) }];
    expect(latestCrossing(other, reached)).toBeNull();
    expect(latestCrossing(pay, reached)).toMatchObject({ kind: "pay", days: 8 });
    expect(payChangedSinceApplied(pay, reached)).toBe(true);
    expect(payChangedSinceApplied(other, reached)).toBe(false);
  });

  it("does not exist before the person applied", () => {
    expect(latestCrossing([{ event_type: "closed", detail: {}, at: days(-1) }], [])).toBeNull();
  });
});

describe("Up next", () => {
  const interview = (at: string) => ({ id: 1, label: "Screen", scheduled_at: at, all_day: false, format: null });

  it("leads with steps past their date, then each day from today, soonest first within a day", () => {
    const groups = upNext([
      card({ job_id: 1, next_action: "Follow up", next_action_due: days(-2) }),
      card({ job_id: 2, next_interview: interview(hours(3)) }),
      card({ job_id: 3, next_action: "Send portfolio", next_action_due: hours(1) }),
      card({ job_id: 4, next_interview: interview(days(1)) }),
      card({ job_id: 5 }),
    ], NOW);
    expect(groups.map((day) => [day.key, day.items.map((item) => item.card.job_id)])).toEqual([
      ["overdue", [1]],
      [0, [3, 2]],
      [1, [4]],
    ]);
  });

  it("never lists an interview as overdue: one that has started stays today's", () => {
    const groups = upNext([card({ job_id: 1, next_interview: interview(hours(-2)) })], NOW);
    expect(groups).toEqual([{ key: 0, items: [expect.objectContaining({ kind: "interview" })] }]);
  });

  it("lists a step with no date nowhere", () => {
    expect(upNext([card({ next_action: "Think about it", next_action_due: null })], NOW)).toEqual([]);
  });
});

describe("stepping through a column", () => {
  it("follows the board's order, section by section, across a split column", () => {
    const cards = [
      card({ job_id: 1, stage: "withdrawn", last_activity_at: days(-1) }),
      card({ job_id: 2, stage: "accepted", last_activity_at: days(-5) }),
      card({ job_id: 3, stage: "declined", last_activity_at: days(-3) }),
      card({ job_id: 4, stage: "applied" }),
    ];
    const place = placeInColumn(cards, 3, NOW)!;
    expect(place).toMatchObject({ index: 1, total: 3 });
    expect([place.previous?.job_id, place.next?.job_id]).toEqual([2, 1]);
    expect(placeInColumn(cards, 99, NOW)).toBeNull();
  });
});

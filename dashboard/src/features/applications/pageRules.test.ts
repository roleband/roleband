import { describe, expect, it } from "vitest";
import type { ActivityItem } from "../../api";
import { msg } from "../../test/msg";
import { applicationCardFixture as card, stepFixture } from "../../test/fixtures";
import { eventChanges, feedEntries, feedMonths, jumpPoints, monthKey, nearestItem, runChanges, runOpened, type ActivityEvent } from "./activity";
import { latestCrossing } from "./crossings";
import { upNext } from "./dueByDay";

/* The application page's rules and Up next's, as the spec states them: the
 * feed folds the changes between two comments, a posting change counts only
 * after the person applied, the feed parts by month and offers the moments
 * of the application to jump to, a step past its date leads Up next while an
 * interview never does, an ending owes nothing on Up next but an accepted
 * offer, and the page steps through its column in the board's order. */

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
    const entries = feedEntries(items);
    expect(entries.map((entry) => entry.kind === "comment" ? `c${entry.comment.id}` : entry.events.map((e) => e.id)))
      .toEqual(["c1", [2, 3], "c4", [5]]);
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

  it("names a step by its words and what was done to it, over the one-step wording", () => {
    const step = (action: NonNullable<ActivityEvent["step"]>["action"]) =>
      eventChanges(event(1, { changed: ["steps", "next_action"], step: { id: 7, action, text: "Send the portfolio", due: null } }));
    expect(step("added")).toEqual([msg("applications-feed-step-added", { step: "Send the portfolio" })]);
    expect(step("done")).toEqual([msg("applications-feed-step-done", { step: "Send the portfolio" })]);
    expect(step("reopened")).toEqual([msg("applications-feed-step-reopened", { step: "Send the portfolio" })]);
    expect(step("edited")).toEqual([msg("applications-feed-step-edited", { step: "Send the portfolio" })]);
    expect(step("removed")).toEqual([msg("applications-feed-step-removed", { step: "Send the portfolio" })]);
    // Each action reads differently.
    expect(new Set((["added", "edited", "done", "reopened", "removed"] as const).map((action) => step(action)[0])).size).toBe(5);
  });

  it("keeps a run the reader opened open as changes join it at either end, or a run beside it", () => {
    const opened = new Set([2, 3]);
    expect(runOpened([event(9), event(2), event(3)], opened)).toBe(true);
    expect(runOpened([event(2), event(3), event(8)], opened)).toBe(true);
    expect(runOpened([event(2), event(3), event(5)], opened)).toBe(true);
    expect(runOpened([event(5), event(6)], opened)).toBe(false);
  });

  it("lists a run's changes without repeating one", () => {
    expect(runChanges([event(1, { changed: ["priority"] }), event(2, { changed: ["priority"] })]))
      .toEqual([msg("applications-feed-priority")]);
  });
});

describe("the feed by month", () => {
  // Local times, so a month boundary is the reader's own.
  const at = (iso: string) => new Date(iso).toISOString();
  const items: ActivityItem[] = [
    { ...comment(1), created_at: at("2026-11-02T09:00:00") },
    event(2, { created_at: at("2026-11-01T08:00:00"), changed: ["priority"] }),
    event(3, { created_at: at("2026-10-31T22:00:00"), changed: ["notes"] }),
    { ...comment(4), created_at: at("2026-10-20T09:00:00") },
    event(5, { created_at: at("2026-09-12T09:00:00"), from_stage: "networking", to_stage: "applied", changed: ["stage"] }),
    { ...comment(6), created_at: at("2025-12-30T09:00:00") },
  ];

  it("parts the feed by the reader's month, newest first, and never folds a run across a month", () => {
    const months = feedMonths(items);
    expect(months.map((month) => month.key)).toEqual(["2026-11", "2026-10", "2026-09", "2025-12"]);
    // Changes 2 and 3 sit together between two comments, but in two months.
    expect(months[0].entries.map((entry) => entry.kind === "comment" ? `c${entry.comment.id}` : entry.events.map((e) => e.id)))
      .toEqual(["c1", [2]]);
    expect(months[1].entries.map((entry) => entry.kind === "comment" ? `c${entry.comment.id}` : entry.events.map((e) => e.id)))
      .toEqual([[3], "c4"]);
    expect(months.map((month) => month.comments)).toEqual([1, 1, 0, 1]);
    expect(months[3].start).toEqual(new Date(2025, 11, 1));
  });

  it("keys a month by the reader's calendar", () => {
    expect(monthKey(new Date(2026, 0, 31, 23, 59))).toBe("2026-01");
    expect(monthKey(new Date(2026, 1, 1, 0, 0))).toBe("2026-02");
  });

  it("lands on the nearest entry, the newer of two as near", () => {
    expect(nearestItem(items, new Date("2026-10-25T09:00:00"))?.id).toBe(4);
    expect(nearestItem([items[0], items[1]], new Date((new Date(items[0].created_at).getTime() + new Date(items[1].created_at).getTime()) / 2))?.id).toBe(1);
    expect(nearestItem([], NOW)).toBeUndefined();
  });

  it("offers the moments the application reached, newest first, and the beginning last", () => {
    const points = jumpPoints(items, {
      stages_reached: [
        { stage: "saved", at: at("2025-12-30T09:00:00") },
        { stage: "applied", at: at("2026-09-12T09:00:00") },
      ],
      interviews: [
        { id: 1, label: "Screen", scheduled_at: at("2026-10-19T15:00:00"), all_day: false, format: null, link: null, outcome: "passed", notes: null, created_at: at("2026-10-01T09:00:00"), updated_at: at("2026-10-19T16:00:00") },
        { id: 2, label: "Cancelled", scheduled_at: at("2026-10-01T15:00:00"), all_day: false, format: null, link: null, outcome: "cancelled", notes: null, created_at: at("2026-09-20T09:00:00"), updated_at: at("2026-09-30T09:00:00") },
        { id: 3, label: "Panel", scheduled_at: at("2026-11-20T15:00:00"), all_day: false, format: null, link: null, outcome: null, notes: null, created_at: at("2026-11-01T09:00:00"), updated_at: at("2026-11-01T09:00:00") },
      ],
    }, NOW);
    expect(points.map((point) => [point.kind, point.item.id])).toEqual([
      ["recent", 1],
      // The first interview that took place: not the cancelled one, not the panel still to come.
      ["interview", 4],
      ["applied", 5],
      ["beginning", 6],
    ]);
  });

  it("offers no offer before there is one, and nothing at all on an empty feed", () => {
    const points = jumpPoints(items, { stages_reached: [], interviews: [] }, NOW);
    expect(points.map((point) => point.kind)).toEqual(["recent", "beginning"]);
    expect(jumpPoints([], { stages_reached: [{ stage: "offer", at: at("2026-11-01T09:00:00") }], interviews: [] }, NOW)).toEqual([]);
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
  });

  it("does not exist before the person applied", () => {
    expect(latestCrossing([{ event_type: "closed", detail: {}, at: days(-1) }], [])).toBeNull();
  });
});

describe("Up next", () => {
  const interview = (at: string) => ({ id: 1, label: "Screen", scheduled_at: at, all_day: false, format: null, link: null });

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

  it("lists each dated step of one application on its own day, and its undated steps nowhere", () => {
    const steps = [
      stepFixture({ id: 11, text: "Follow up", due: days(-1) }),
      stepFixture({ id: 12, text: "Send portfolio", due: hours(2) }),
      stepFixture({ id: 13, text: "Ask Sam", due: days(2) }),
      stepFixture({ id: 14, text: "Read the blog", due: null }),
    ];
    const groups = upNext([card({ job_id: 1, steps })], NOW);
    expect(groups.map((day) => [day.key, day.items.map((item) => item.kind === "step" ? item.step.text : null)])).toEqual([
      ["overdue", ["Follow up"]],
      [0, ["Send portfolio"]],
      [2, ["Ask Sam"]],
    ]);
  });

  it("lists nothing for an application that ended, except one the person accepted", () => {
    const dated = { next_action: "Ask for feedback", next_action_due: hours(2), next_interview: interview(hours(4)) };
    const ended = (["declined", "withdrawn", "rejected", "role_closed"] as const).map((stage, i) =>
      card({ job_id: 10 + i, stage, ...dated }));
    const accepted = card({ job_id: 20, stage: "accepted", next_action: "Sign the offer", next_action_due: hours(1) });
    const offer = card({ job_id: 21, stage: "offer", ...dated });

    const groups = upNext([...ended, accepted, offer], NOW);

    expect(groups.map((day) => [day.key, day.items.map((item) => item.card.job_id)])).toEqual([[0, [20, 21, 21]]]);
  });
});

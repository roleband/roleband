import { describe, expect, it } from "vitest";
import { STAGES } from "../../copy/vocabulary";
import { applicationCardFixture as card } from "../../test/fixtures";
import { COLUMNS, boardCounts, byStage, dueOf, dueState, isStale, sortColumn } from "./board";

/* The board's rules as the spec states them: eleven stages in eight columns,
 * one due field that is the sooner of two dates, three due states, a stale
 * threshold per stage, and a column order of urgent first, then latest
 * activity. Each rule carries the case a plausible wrong version gets wrong. */

const NOW = new Date("2026-11-04T12:00:00Z");
const hours = (n: number) => new Date(NOW.getTime() + n * 3_600_000).toISOString();
const days = (n: number) => hours(n * 24);

describe("the columns", () => {
  it("place every stage in exactly one column, in the taxonomy's order", () => {
    const placed = COLUMNS.flatMap((column) => column.stages);
    expect(placed).toEqual(STAGES);
    expect(COLUMNS.map((column) => column.id)).toEqual([
      "saved", "researching", "networking", "applied", "interviewing", "offer", "decided", "closed",
    ]);
  });

  it("split the endings by who decided: the person's in Decided, the company's in Closed", () => {
    expect(COLUMNS.find((column) => column.id === "decided")!.stages).toEqual(["accepted", "declined", "withdrawn"]);
    expect(COLUMNS.find((column) => column.id === "closed")!.stages).toEqual(["rejected", "role_closed"]);
  });

  it("keep a card whose stage has no cards beside it in its own stage, and leave other stages empty", () => {
    const groups = byStage([card({ job_id: 1, stage: "applied" })], NOW);
    expect(groups.get("applied")!.map((c) => c.job_id)).toEqual([1]);
    expect(groups.get("saved")).toEqual([]);
    expect(groups.size).toBe(STAGES.length);
  });
});

describe("the due field", () => {
  it("is the sooner of the next interview and the next step", () => {
    const interviewFirst = card({
      next_action_due: days(3),
      next_interview: { id: 1, label: "Hiring manager", scheduled_at: days(1), all_day: false, format: "video" },
    });
    expect(dueOf(interviewFirst)).toMatchObject({ kind: "interview" });
    const stepFirst = card({
      next_action_due: days(1),
      next_interview: { id: 1, label: "Hiring manager", scheduled_at: days(3), all_day: false, format: null },
    });
    expect(dueOf(stepFirst)).toMatchObject({ kind: "step" });
    expect(dueOf(card())).toBeNull();
  });

  it("holds an all-day interview open until its day ends", () => {
    const due = dueOf(card({
      next_interview: { id: 1, label: "Onsite", scheduled_at: hours(-2), all_day: true, format: "onsite" },
    }))!;
    expect(due.at.getTime()).toBe(new Date(hours(22)).getTime());
  });

  it("is overdue once a step's date passes, but an interview that started is never overdue", () => {
    const step = dueOf(card({ next_action_due: hours(-1) }))!;
    expect(dueState(step, NOW)).toBe("overdue");
    const interview = dueOf(card({
      next_interview: { id: 1, label: "Screen", scheduled_at: hours(-1), all_day: false, format: "phone" },
    }))!;
    expect(dueState(interview, NOW)).toBe("soon");
  });

  it("turns urgent within 48 hours, and not before", () => {
    expect(dueState(dueOf(card({ next_action_due: hours(47) }))!, NOW)).toBe("soon");
    expect(dueState(dueOf(card({ next_action_due: hours(49) }))!, NOW)).toBe("set");
  });
});

describe("a column's order", () => {
  it("puts overdue and soon-due cards first, soonest first, then the latest activity", () => {
    const sorted = sortColumn([
      card({ job_id: 1, last_activity_at: hours(-1) }),
      card({ job_id: 2, next_action_due: hours(30), last_activity_at: days(-10) }),
      card({ job_id: 3, next_action_due: days(-2), last_activity_at: days(-9) }),
      card({ job_id: 4, last_activity_at: days(-5) }),
    ], NOW);
    expect(sorted.map((c) => c.job_id)).toEqual([3, 2, 1, 4]);
  });

  it("does not lift a card whose due date is weeks away above fresher activity", () => {
    const sorted = sortColumn([
      card({ job_id: 1, next_action_due: days(20), last_activity_at: days(-8) }),
      card({ job_id: 2, last_activity_at: hours(-2) }),
    ], NOW);
    expect(sorted.map((c) => c.job_id)).toEqual([2, 1]);
  });
});

describe("a quiet card", () => {
  it("goes stale after its stage's own threshold, and not a day before", () => {
    expect(isStale(card({ stage: "applied", last_activity_at: days(-14) }), NOW)).toBe(true);
    expect(isStale(card({ stage: "applied", last_activity_at: days(-13) }), NOW)).toBe(false);
    expect(isStale(card({ stage: "offer", last_activity_at: days(-3) }), NOW)).toBe(true);
    expect(isStale(card({ stage: "interviewing", last_activity_at: days(-6) }), NOW)).toBe(false);
  });

  it("counts any activity as movement, not only a stage change", () => {
    const commented = card({ stage: "applied", stage_since: days(-30), last_activity_at: days(-2) });
    expect(isStale(commented, NOW)).toBe(false);
  });

  it("never goes stale in Considering or in an ending", () => {
    for (const stage of ["saved", "accepted", "declined", "withdrawn", "rejected", "role_closed"] as const) {
      expect(isStale(card({ stage, last_activity_at: days(-200) }), NOW), stage).toBe(false);
    }
  });
});

describe("the summary", () => {
  it("counts the cards past Considering that have neither a next step nor an interview", () => {
    const counts = boardCounts([
      card({ job_id: 1, stage: "saved" }),
      card({ job_id: 2, stage: "applied" }),
      card({ job_id: 3, stage: "applied", next_action: "Follow up" }),
      card({ job_id: 4, stage: "interviewing", next_interview: {
        id: 9, label: "Screen", scheduled_at: days(2), all_day: false, format: null,
      } }),
      card({ job_id: 5, stage: "withdrawn", ended_at_stage: "applied" }),
      card({ job_id: 6, stage: "rejected", ended_at_stage: "interviewing" }),
      card({ job_id: 7, stage: "accepted", ended_at_stage: "offer" }),
    ]);
    expect(counts).toEqual({ moving: 4, decided: 2, closed: 1, needNextStep: 1 });
  });
});

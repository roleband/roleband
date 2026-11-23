import { describe, expect, it } from "vitest";
import { STAGES } from "../../copy/vocabulary";
import { applicationCardFixture as card, stepFixture } from "../../test/fixtures";
import { COLUMNS, byStage, daysInStage, daysOverdue, daysToSay, dueOf, dueState, isStale, movedCard, needsNextStep, owesNothing, sortColumn, withStep, withoutStep } from "./board";

/* The board's rules as the spec states them: ten stages in seven columns,
 * one due field that is the sooner of two dates, three due states, a stale
 * threshold per stage, and a column order of urgent first, then latest
 * activity. Each rule carries the case a plausible wrong version gets wrong. */

const NOW = new Date("2026-11-04T12:00:00Z");
const hours = (n: number) => new Date(NOW.getTime() + n * 3_600_000).toISOString();
const days = (n: number) => hours(n * 24);

describe("the columns", () => {
  it("place every stage but Networking in exactly one column, in the taxonomy's order", () => {
    const placed = COLUMNS.flatMap((column) => column.stages);
    expect(placed).toEqual(STAGES.filter((stage) => stage !== "networking"));
    expect(COLUMNS.map((column) => column.id)).toEqual([
      "saved", "researching", "applied", "interviewing", "offer", "decided", "closed",
    ]);
  });

  it("show a Networking card in Researching, keeping its own stage", () => {
    const groups = byStage([card({ job_id: 1, stage: "networking" }), card({ job_id: 2, stage: "researching" })], NOW);
    expect(groups.get("researching")!.map((c) => c.job_id).sort()).toEqual([1, 2]);
    expect(groups.get("researching")!.find((c) => c.job_id === 1)!.stage).toBe("networking");
    expect(groups.has("networking")).toBe(false);
  });

  it("split the endings by who decided: the person's in Decided, the company's in Closed", () => {
    expect(COLUMNS.find((column) => column.id === "decided")!.stages).toEqual(["accepted", "declined", "withdrawn"]);
    expect(COLUMNS.find((column) => column.id === "closed")!.stages).toEqual(["rejected", "role_closed"]);
  });

  it("keep a card whose stage has no cards beside it in its own stage, and leave other stages empty", () => {
    const groups = byStage([card({ job_id: 1, stage: "applied" })], NOW);
    expect(groups.get("applied")!.map((c) => c.job_id)).toEqual([1]);
    expect(groups.get("saved")).toEqual([]);
    expect(groups.size).toBe(STAGES.length - 1);
  });
});

describe("the due field", () => {
  it("is the sooner of the next interview and the next step", () => {
    const interviewFirst = card({
      next_action_due: days(3),
      next_interview: { id: 1, label: "Hiring manager", scheduled_at: days(1), all_day: false, format: "video", link: null },
    });
    expect(dueOf(interviewFirst)).toMatchObject({ kind: "interview" });
    const stepFirst = card({
      next_action_due: days(1),
      next_interview: { id: 1, label: "Hiring manager", scheduled_at: days(3), all_day: false, format: null, link: null },
    });
    expect(dueOf(stepFirst)).toMatchObject({ kind: "step" });
    expect(dueOf(card())).toBeNull();
  });

  it("holds an all-day interview open until its day ends: the next local midnight", () => {
    const allDay = (on: Date) => dueOf(card({
      next_interview: { id: 1, label: "Onsite", scheduled_at: on.toISOString(), all_day: true, format: "onsite", link: null },
    }))!;
    expect(allDay(new Date(2026, 10, 4)).at).toEqual(new Date(2026, 10, 5));

    // A day the reader's clock changes on is 23 or 25 hours long, and still
    // ends at the next midnight. In a zone with no clock change, none is found
    // and the plain day above is the whole case.
    const changes = Array.from({ length: 365 }, (_, i) => new Date(2026, 0, 1 + i))
      .filter((day) => new Date(day.getFullYear(), day.getMonth(), day.getDate() + 1).getTime() - day.getTime() !== 86_400_000);
    for (const change of changes) {
      const next = new Date(change.getFullYear(), change.getMonth(), change.getDate() + 1);
      expect(allDay(change).at, change.toDateString()).toEqual(next);
    }
  });

  it("is overdue once a step's day has passed, but an interview that started is never overdue", () => {
    const step = dueOf(card({ next_action_due: days(-1) }))!;
    expect(dueState(step, NOW)).toBe("overdue");
    const interview = dueOf(card({
      next_interview: { id: 1, label: "Screen", scheduled_at: hours(-1), all_day: false, format: "phone", link: null },
    }))!;
    expect(dueState(interview, NOW)).toBe("soon");
  });

  it("turns urgent within two calendar days, and not before", () => {
    expect(dueState(dueOf(card({ next_action_due: hours(47) }))!, NOW)).toBe("soon");
    expect(dueState(dueOf(card({ next_action_due: days(3) }))!, NOW)).toBe("set");
  });

  describe("by the reader's calendar days, as the day headings count them", () => {
    // Early morning: a step due late two days ago is two days back on the
    // calendar, though fewer than 48 hours have passed.
    const morning = new Date(2026, 10, 4, 9, 0);
    const at = (day: number, hour: number, minute = 0) => new Date(2026, 10, day, hour, minute).toISOString();

    it("count a step due late two days ago as two days overdue, not one", () => {
      const step = dueOf(card({ next_action_due: at(2, 23, 59) }))!;
      expect(dueState(step, morning)).toBe("overdue");
      expect(daysOverdue(step, morning)).toBe(2);
    });

    it("count yesterday as one day overdue whatever the hour", () => {
      const step = dueOf(card({ next_action_due: at(3, 23, 59) }))!;
      expect(daysOverdue(step, morning)).toBe(1);
      expect(daysOverdue(dueOf(card({ next_action_due: at(3, 0, 1) }))!, new Date(2026, 10, 4, 23, 30))).toBe(1);
    });

    it("leave a step whose time today has passed on today, not overdue", () => {
      expect(dueState(dueOf(card({ next_action_due: at(4, 8) }))!, new Date(2026, 10, 4, 14, 0))).toBe("soon");
    });

    it("read tomorrow's last minute as urgent and the day after next's as set only past two days", () => {
      expect(dueState(dueOf(card({ next_action_due: at(6, 23, 59) }))!, morning)).toBe("soon");
      expect(dueState(dueOf(card({ next_action_due: at(7, 0, 1) }))!, morning)).toBe("set");
    });
  });
});

describe("a card's steps after a local change", () => {
  const steps = [
    stepFixture({ id: 11, text: "Email Sam", due: days(1) }),
    stepFixture({ id: 12, text: "Send portfolio", due: days(3) }),
    stepFixture({ id: 13, text: "Read the blog", due: null }),
  ];
  const base = card({ steps });

  it("re-sorts an edited step into the server's order and derives the next step from it", () => {
    const moved = withStep(base, { ...steps[1], text: "Send portfolio now", due: days(0) });
    expect(moved.steps.map((step) => step.id)).toEqual([12, 11, 13]);
    expect([moved.next_action, moved.next_action_due]).toEqual(["Send portfolio now", days(0)]);
  });

  it("puts a step that loses its day after the dated ones, ordered by id among the undated", () => {
    const undated = withStep(base, { ...steps[0], due: null });
    expect(undated.steps.map((step) => step.id)).toEqual([12, 11, 13]);
    expect(undated.next_action).toBe("Send portfolio");
  });

  it("inserts a step the card does not hold yet", () => {
    const added = withStep(base, stepFixture({ id: 99, text: "Call Pat", due: days(2) }));
    expect(added.steps.map((step) => step.id)).toEqual([11, 99, 12, 13]);
    expect(added.next_action).toBe("Email Sam");
  });

  it("agrees with withoutStep about the mirror: the soonest of what is left", () => {
    expect(withoutStep(base, 11)).toMatchObject({ next_action: "Send portfolio", next_action_due: days(3) });
    expect(withoutStep(card({ steps: [steps[0]] }), 11)).toMatchObject({ steps: [], next_action: null, next_action_due: null });
  });
});

describe("an ending that owes nothing", () => {
  it("is every ending but an accepted offer, which still has signing and a start date", () => {
    for (const stage of ["declined", "withdrawn", "rejected", "role_closed"] as const) expect(owesNothing(card({ stage })), stage).toBe(true);
    for (const stage of ["saved", "applied", "offer", "accepted"] as const) expect(owesNothing(card({ stage })), stage).toBe(false);
  });

  it("asks only a moving role past Considering for a next step: an ending, accepted included, is asked for none", () => {
    expect(needsNextStep(card({ stage: "applied" }))).toBe(true);
    expect(needsNextStep(card({ stage: "applied", next_action: "Chase" }))).toBe(false);
    expect(needsNextStep(card({ stage: "accepted" }))).toBe(false);
    expect(needsNextStep(card({ stage: "rejected" }))).toBe(false);
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

describe("a move's paint", () => {
  const at = "2026-11-10T12:00:00Z";

  it("names the stage an ending was reached from, as the server does", () => {
    const moved = movedCard(card({ stage: "applied", stage_since: "2026-11-01T09:00:00Z" }), "rejected", at);
    expect(moved).toMatchObject({ stage: "rejected", ended_at_stage: "applied", stage_since: at, last_activity_at: at });
  });

  it("keeps that stage from one ending to another, and drops it once the card moves again", () => {
    const declined = card({ stage: "declined", ended_at_stage: "offer" });
    expect(movedCard(declined, "accepted", at).ended_at_stage).toBe("offer");
    expect(movedCard(declined, "offer", at).ended_at_stage).toBeNull();
    expect(movedCard(card({ stage: "saved" }), "applied", at).ended_at_stage).toBeNull();
  });
});

describe("days in stage, as the stage button and the card say them", () => {
  it("says nothing on the day of the move, which still counts as day 0 for ordering", () => {
    const moved = card({ stage: "applied", stage_since: hours(-2) });
    expect(daysToSay(moved, NOW)).toBeNull();
    expect(daysInStage(moved, NOW)).toBe(0);
  });

  it("counts whole days from the day after the move", () => {
    expect(daysToSay(card({ stage: "applied", stage_since: days(-1) }), NOW)).toBe(1);
    expect(daysToSay(card({ stage: "applied", stage_since: hours(-47) }), NOW)).toBe(1);
    expect(daysToSay(card({ stage: "applied", stage_since: days(-12) }), NOW)).toBe(12);
  });

  it("says nothing when no date says when the stage began", () => {
    expect(daysToSay(card({ stage: "applied", stage_since: null }), NOW)).toBeNull();
  });
});

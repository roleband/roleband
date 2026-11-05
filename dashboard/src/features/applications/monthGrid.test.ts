import { describe, expect, it } from "vitest";
import type { ApplicationCalendarItem } from "../../api";
import { dayKey, fromDayKey, itemsByDay, monthSpan, monthWeeks, shiftDay, shiftMonth } from "./monthGrid";

/* The month grid's contracts: Monday-first whole weeks that cover the month
 * and nothing past its last week, a read span the API accepts for any month,
 * and items filed under the reader's own day. Built with local constructors,
 * so each case holds in whatever zone the suite runs. */

const keys = (weeks: Date[][]) => weeks.map((week) => week.map(dayKey));

describe("monthWeeks", () => {
  it("starts on the Monday on or before the 1st and ends on the Sunday on or after the last day", () => {
    // November 2026 opens on a Sunday and closes on a Monday.
    const weeks = keys(monthWeeks(new Date(2026, 10, 1)));
    expect(weeks[0][0]).toBe("2026-10-26");
    expect(weeks[0][6]).toBe("2026-11-01");
    expect(weeks[weeks.length - 1][0]).toBe("2026-11-30");
    expect(weeks[weeks.length - 1][6]).toBe("2026-12-06");
    expect(weeks).toHaveLength(6);
  });

  it("draws a month that opens on a Monday from its 1st, and four weeks when four hold it", () => {
    // February 2027: Monday the 1st to Sunday the 28th.
    const weeks = keys(monthWeeks(new Date(2027, 1, 14)));
    expect(weeks).toHaveLength(4);
    expect(weeks[0][0]).toBe("2027-02-01");
    expect(weeks[3][6]).toBe("2027-02-28");
  });

  it("adds no week the month does not reach", () => {
    // May 2026 ends on Sunday the 31st: the grid stops there.
    const weeks = keys(monthWeeks(new Date(2026, 4, 1)));
    expect(weeks[weeks.length - 1][6]).toBe("2026-05-31");
    expect(weeks.flat()).not.toContain("2026-06-01");
  });

  it("every day of every month in ten years is in its grid, in order, a day apart", () => {
    for (let month = new Date(2025, 0, 1); month.getFullYear() < 2035; month = shiftMonth(month, 1)) {
      const days = monthWeeks(month).flat();
      const last = new Date(month.getFullYear(), month.getMonth() + 1, 0).getDate();
      const inMonth = days.filter((day) => day.getMonth() === month.getMonth()).map((day) => day.getDate());
      expect(inMonth, dayKey(month)).toEqual(Array.from({ length: last }, (_, i) => i + 1));
      days.forEach((day, i) => {
        if (i > 0) expect(dayKey(day), dayKey(month)).toBe(dayKey(shiftDay(days[i - 1], 1)));
      });
      expect(days[0].getDay(), "Monday first").toBe(1);
    }
  });
});

describe("monthSpan", () => {
  it("runs from the grid's first midnight to the midnight after its last day", () => {
    const { start, end } = monthSpan(new Date(2026, 10, 1));
    expect(start).toEqual(new Date(2026, 9, 26));
    expect(end).toEqual(new Date(2026, 11, 7));
  });

  it("never asks for more than the six weeks the calendar read admits", () => {
    for (let month = new Date(2025, 0, 1); month.getFullYear() < 2035; month = shiftMonth(month, 1)) {
      const { start, end } = monthSpan(month);
      const days = Math.round((end.getTime() - start.getTime()) / 86_400_000);
      expect(days, dayKey(month)).toBeLessThanOrEqual(42);
    }
  });
});

describe("itemsByDay", () => {
  const item = (at: Date, label: string): ApplicationCalendarItem => ({
    kind: "interview", job_id: 1, at: at.toISOString(), interview_id: 1, label, all_day: false,
    format: null, outcome: null,
  });

  it("files an item under the reader's own day, late evening included", () => {
    const late = new Date(2026, 10, 9, 23, 30);
    const early = new Date(2026, 10, 10, 0, 15);
    const days = itemsByDay([item(late, "Late"), item(early, "Early")]);
    expect(days.get("2026-11-09")?.map((i) => i.kind === "interview" && i.label)).toEqual(["Late"]);
    expect(days.get("2026-11-10")?.map((i) => i.kind === "interview" && i.label)).toEqual(["Early"]);
  });

  it("keeps the read's order within a day", () => {
    const at = (h: number) => new Date(2026, 10, 9, h);
    const days = itemsByDay([item(at(9), "First"), item(at(14), "Second"), item(at(16), "Third")]);
    expect(days.get("2026-11-09")?.map((i) => i.kind === "interview" && i.label)).toEqual(["First", "Second", "Third"]);
  });
});

describe("day keys", () => {
  it("round-trip through local midnight", () => {
    expect(dayKey(fromDayKey("2026-03-08"))).toBe("2026-03-08");
    expect(fromDayKey("2026-03-08")).toEqual(new Date(2026, 2, 8));
  });

  it("a day shifted across a month's end lands on the next month", () => {
    expect(dayKey(shiftDay(new Date(2026, 10, 30), 1))).toBe("2026-12-01");
    expect(dayKey(shiftDay(new Date(2026, 0, 1), -1))).toBe("2025-12-31");
  });
});

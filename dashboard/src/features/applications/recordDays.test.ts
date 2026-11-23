import { describe, expect, it } from "vitest";
import { interviewWhen } from "./interviewWords";
import { recordDay, weekdayDay } from "./recordDays";

/* A day said without its year is read as this year's. So a day in another
 * year says its year, and a day in this one does not repeat it. */

const NOW = new Date(2026, 0, 6, 12);

describe("a day on the record", () => {
  it("leaves the year out within the reader's current year", () => {
    expect(recordDay(new Date(2026, 0, 2, 9), NOW)).not.toMatch(/2026/);
    expect(weekdayDay(new Date(2026, 0, 2, 9), NOW)).not.toMatch(/2026/);
  });

  it("names the year of a day in another year, past or to come", () => {
    expect(recordDay(new Date(2025, 11, 30, 9), NOW)).toMatch(/2025/);
    expect(weekdayDay(new Date(2025, 11, 30, 9), NOW)).toMatch(/2025/);
    expect(recordDay(new Date(2027, 0, 4, 9), NOW)).toMatch(/2027/);
  });

  it("tells last December's round from this year's in the interview's line", () => {
    const at = (date: Date) => ({ scheduled_at: date.toISOString(), all_day: false });
    expect(interviewWhen(at(new Date(2025, 11, 30, 15)), NOW)).toMatch(/2025/);
    expect(interviewWhen(at(new Date(2026, 0, 8, 15)), NOW)).not.toMatch(/2026/);
    expect(interviewWhen({ scheduled_at: new Date(2025, 11, 30).toISOString(), all_day: true }, NOW)).toMatch(/2025/);
  });
});

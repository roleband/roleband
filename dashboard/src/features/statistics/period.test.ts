import { expect, it } from "vitest";
import { date } from "../../copy/format";
import { msg } from "../../test/msg";
import { coveredWindows, periodLabel } from "./period";

const WINDOWS = [{ days: 7 }, { days: 30 }, { days: 90 }, { days: 0 }];
const days = (history: number | null) => coveredWindows(WINDOWS, history).map((w) => w.days);

it("offers all time, and each window shorter than the history", () => {
  // A window the history does not exceed shows the same figures as all time.
  expect(days(0)).toEqual([0]);
  expect(days(6)).toEqual([0]);
  expect(days(7)).toEqual([0]);
  expect(days(8)).toEqual([7, 0]);
  expect(days(31)).toEqual([7, 30, 0]);
  expect(days(120)).toEqual([7, 30, 90, 0]);
  // Unknown history: every window, as before there was a history to read.
  expect(days(null)).toEqual([7, 30, 90, 0]);
});

const lastDays = (days: number) => msg("insights-common-last-days-or-all-time", { period: "days", days });
const sinceDate = (since: string, days: number) => msg("insights-common-since-date", { date: date(since, "day"), days });

it("says a window as its length, and all time as the history since its start", () => {
  const since = "2026-11-03T06:02:00Z";
  const now = Date.parse("2026-11-11T12:00:00Z");
  expect(periodLabel(0, since, now)).toBe(sinceDate(since, 8));
  expect(periodLabel(0, since, Date.parse("2026-11-04T07:00:00Z"))).toBe(sinceDate(since, 1));
  // Before any whole read there is no start to name.
  expect(periodLabel(0, null, now)).toBe(msg("insights-common-last-days-or-all-time", { period: "all", days: 0 }));
});

it("says a window the history clipped as the history since its start, and a whole window as its length", () => {
  const now = Date.parse("2026-11-11T12:00:00Z");
  // The route reports the window's own start when the history covers it, a
  // moment before the view reads the clock.
  const windowStart = new Date(now - 30 * 86_400_000 - 5_000).toISOString();
  expect(periodLabel(30, windowStart, now)).toBe(lastDays(30));
  expect(periodLabel(30, null, now)).toBe(lastDays(30));
  // Asked for 90 days with 8 days of history (the history could not be read,
  // so the view offered the window): the figures cover the 8 days.
  const history = "2026-11-03T06:02:00Z";
  expect(periodLabel(90, history, now)).toBe(sinceDate(history, 8));
});

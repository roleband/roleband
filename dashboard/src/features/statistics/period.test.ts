import { expect, it } from "vitest";
import { date } from "../../copy/format";
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

it("says a window as its length, and all time as the history since its start", () => {
  const since = "2026-11-03T06:02:00Z";
  const now = Date.parse("2026-11-11T12:00:00Z");
  expect(periodLabel(30, since, now)).toBe("last 30d");
  expect(periodLabel(0, since, now)).toBe(`since ${date(since, "day")} (8 days)`);
  expect(periodLabel(0, since, Date.parse("2026-11-04T07:00:00Z"))).toBe(`since ${date(since, "day")} (1 day)`);
  // Before any whole read there is no start to name.
  expect(periodLabel(0, null, now)).toBe("all time");
});

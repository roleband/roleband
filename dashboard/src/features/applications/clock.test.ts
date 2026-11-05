import { describe, expect, it } from "vitest";
import { QUARTER_HOURS, anchorClock, clockLabel, parseClock } from "./clock";

/* The time field reads what people type for a time of day, and refuses what
 * names none rather than guessing. */

describe("a typed time", () => {
  it.each([
    ["2pm", "14:00"],
    ["2 PM", "14:00"],
    ["2:30 pm", "14:30"],
    ["2.30p", "14:30"],
    ["2:30 p.m.", "14:30"],
    ["12am", "00:00"],
    ["12 pm", "12:00"],
    ["9", "09:00"],
    ["14:30", "14:30"],
    ["1430", "14:30"],
    ["230", "02:30"],
    ["14h30", "14:30"],
    ["  7:05 am ", "07:05"],
  ])("reads %j as %s", (typed, clock) => {
    expect(parseClock(typed)).toBe(clock);
  });

  it("reads a time written the way the list writes it", () => {
    expect(parseClock(clockLabel("16:45"))).toBe("16:45");
  });

  it.each(["", "  ", "25:00", "13pm", "0am", "2:75", "noonish", "2:3"])("names no time in %j", (typed) => {
    expect(parseClock(typed)).toBeNull();
  });
});

describe("the list of times", () => {
  it("holds every quarter hour of a day, in order", () => {
    expect(QUARTER_HOURS).toHaveLength(96);
    expect(QUARTER_HOURS[0]).toBe("00:00");
    expect(QUARTER_HOURS[37]).toBe("09:15");
    expect(QUARTER_HOURS[95]).toBe("23:45");
  });

  it("opens on the chosen time's quarter, or on nine in the morning", () => {
    expect(anchorClock("")).toBe("09:00");
    expect(anchorClock("14:37")).toBe("14:30");
    expect(anchorClock("07:00")).toBe("07:00");
  });
});

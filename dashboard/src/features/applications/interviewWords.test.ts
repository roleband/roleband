import { describe, expect, it } from "vitest";
import { interviewEnds, interviewPast } from "./interviewWords";

/* A round is over when it has begun, and an all-day one when its day ends: the
 * same rule wherever a round is called coming or past. */

const now = new Date(2026, 10, 4, 10, 0);
const round = (at: Date, all_day: boolean) => ({ scheduled_at: at.toISOString(), all_day });

describe("when a round is over", () => {
  it("ends a timed round when it starts", () => {
    const at = new Date(2026, 10, 4, 9, 0);
    expect(interviewEnds(round(at, false)).getTime()).toBe(at.getTime());
    expect(interviewPast(round(at, false), now)).toBe(true);
    expect(interviewPast(round(new Date(2026, 10, 4, 11, 0), false), now)).toBe(false);
  });

  it("ends an all-day round at the next local midnight, so it is not past at 00:01 of its own day", () => {
    const day = new Date(2026, 10, 4);
    expect(interviewEnds(round(day, true))).toEqual(new Date(2026, 10, 5));
    expect(interviewPast(round(day, true), new Date(2026, 10, 4, 0, 1))).toBe(false);
    expect(interviewPast(round(day, true), new Date(2026, 10, 5, 0, 1))).toBe(true);
  });
});

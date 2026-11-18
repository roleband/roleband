import { describe, expect, it } from "vitest";
import { placeLeft, placeTop } from "./place";

const OPTIONS = { gap: 6, margin: 8 };
/** An 18px mark at (x, y). */
const mark = (x: number, y: number) => ({ left: x, right: x + 18, top: y, bottom: y + 18 });

describe("placing a panel beside its anchor", () => {
  it("puts a panel that fits below the anchor, lined up with its start", () => {
    expect(placeTop(mark(100, 100), 50, 800, OPTIONS)).toBe(124);
    expect(placeLeft(mark(100, 100), 200, 1280, OPTIONS)).toBe(100);
  });

  it("moves a panel near the right edge left until it ends at the margin", () => {
    // Lined up with a mark at 1200, a 320px panel would end at 1520.
    expect(placeLeft(mark(1200, 100), 320, 1280, OPTIONS)).toBe(1280 - 320 - 8);
  });

  it("lines up with the anchor's end when asked", () => {
    expect(placeLeft(mark(600, 100), 200, 1280, { ...OPTIONS, align: "end" })).toBe(618 - 200);
  });

  it("starts a panel wider than the window at the left margin, never off the left edge", () => {
    expect(placeLeft(mark(300, 100), 500, 390, OPTIONS)).toBe(8);
  });

  it("flips above an anchor whose panel would fall off the bottom", () => {
    expect(placeTop(mark(100, 760), 60, 800, OPTIONS)).toBe(760 - 60 - 6);
  });

  it("keeps a panel below while it is still unmeasured", () => {
    expect(placeTop(mark(100, 790), 0, 800, OPTIONS)).toBe(814);
  });

  it("never flips a panel above the window's top margin", () => {
    expect(placeTop(mark(100, 20), 900, 800, OPTIONS)).toBe(8);
  });
});

import { describe, expect, it } from "vitest";
import { dropStageAt, edgeSpeed, scrollStep, type DropColumn } from "./dropTarget";

/* Where a dragged card lands. The board is generous: the pointer anywhere
 * over a column's width counts, a gap between columns counts for the nearer,
 * and a column split into sections gives the card to the section nearest the
 * pointer. The board scrolls only when a drag is held at its edge. */

const columns: DropColumn[] = [
  { left: 0, right: 250, sections: [{ stage: "applied", top: 40, bottom: 600 }] },
  { left: 262, right: 512, sections: [{ stage: "offer", top: 40, bottom: 120 }] },
  {
    left: 524,
    right: 774,
    sections: [
      { stage: "accepted", top: 40, bottom: 160 },
      { stage: "declined", top: 200, bottom: 320 },
      { stage: "withdrawn", top: 360, bottom: 480 },
    ],
  },
];

describe("where a drop lands", () => {
  it("is the column under the pointer, above or below its cards", () => {
    expect(dropStageAt(columns, 300, 90)).toBe("offer");
    expect(dropStageAt(columns, 300, 700)).toBe("offer");
    expect(dropStageAt(columns, 300, 0)).toBe("offer");
  });

  it("is the nearer column from the gap between two", () => {
    expect(dropStageAt(columns, 253, 90)).toBe("applied");
    expect(dropStageAt(columns, 259, 90)).toBe("offer");
  });

  it("is the section under the pointer in a split column, else the nearest one", () => {
    expect(dropStageAt(columns, 600, 250)).toBe("declined");
    expect(dropStageAt(columns, 600, 175)).toBe("accepted");
    expect(dropStageAt(columns, 600, 345)).toBe("withdrawn");
    expect(dropStageAt(columns, 600, 900)).toBe("withdrawn");
  });

  it("is nowhere on a board with no columns", () => {
    expect(dropStageAt([], 100, 100)).toBeNull();
  });
});

describe("scrolling the board under a drag", () => {
  it("is still away from the edges", () => {
    expect(edgeSpeed(500, 0, 1000)).toBe(0);
    expect(edgeSpeed(48, 0, 1000)).toBe(0);
    expect(edgeSpeed(952, 0, 1000)).toBe(0);
  });

  it("goes toward the edge the pointer is held at, faster the deeper in", () => {
    const slow = edgeSpeed(990 - 30, 0, 990);
    const fast = edgeSpeed(990 - 5, 0, 990);
    expect(slow).toBeGreaterThan(0);
    expect(fast).toBeGreaterThan(slow);
    expect(edgeSpeed(5, 0, 990)).toBe(-fast);
  });

  it("tops out past the edge, with the pointer off the board", () => {
    expect(edgeSpeed(1400, 0, 990)).toBe(edgeSpeed(990, 0, 990));
    expect(edgeSpeed(-300, 0, 990)).toBe(-edgeSpeed(990, 0, 990));
  });
});

describe("how far the board scrolls", () => {
  // The board shows 0..600 of columns that run from 0 to 774.
  it("goes at the edge's speed while columns are still hidden that way", () => {
    expect(scrollStep(18, columns, 0, 600)).toBe(18);
    expect(scrollStep(-18, columns.map((c) => ({ ...c, left: c.left - 100, right: c.right - 100 })), 0, 600)).toBe(-18);
  });

  it("stops where the last column comes into view, however far the carried card reaches", () => {
    expect(scrollStep(18, columns, 0, 770)).toBe(4);
    expect(scrollStep(18, columns, 0, 774)).toBe(0);
    expect(scrollStep(18, columns, 0, 900)).toBe(0);
  });

  it("stops where the first column comes into view", () => {
    expect(scrollStep(-18, columns, 0, 600)).toBe(0);
    expect(scrollStep(-18, columns.map((c) => ({ ...c, left: c.left - 5, right: c.right - 5 })), 0, 600)).toBe(-5);
  });

  it("is still on a board with no columns", () => {
    expect(scrollStep(18, [], 0, 600)).toBe(0);
  });
});

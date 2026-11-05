import { describe, expect, it } from "vitest";
import { RESTING, coast, grab, move, onPlanet, release } from "./globeDrag";
import { MAX_TILT, MIN_TILT, TILT, backingDensity, facingLon, onCanvas, pageScale, place } from "./globeView";

const at = place(1928, 1056);
const perDegree = (at.r * Math.PI) / 180; // pixels the pointer moves per degree

describe("dragging the planet", () => {
  it("can be grabbed on the planet only", () => {
    expect(onPlanet(at.cx, at.cy, at)).toBe(true);
    expect(onPlanet(at.cx - at.r * 0.99, at.cy, at)).toBe(true);
    expect(onPlanet(at.cx - at.r * 1.01, at.cy, at)).toBe(false);
    expect(onPlanet(100, 100, at)).toBe(false);
  });

  it("turns with the pointer: dragging right brings the west into view", () => {
    const held = grab(RESTING, at.cx, at.cy, 0);
    const dragged = move(held, at.cx + 30 * perDegree, at.cy, 100, at.r);
    expect(dragged.turned).toBeCloseTo(30, 5);
    expect(facingLon(0, dragged.turned)).toBeCloseTo(facingLon(0, 0) - 30, 5);
    expect(dragged.tilt).toBe(TILT);
  });

  it("tilts with the pointer, and stops at its limits instead of turning over", () => {
    const held = grab(RESTING, at.cx, at.cy, 0);
    expect(move(held, at.cx, at.cy + 10 * perDegree, 50, at.r).tilt).toBeCloseTo(TILT + 10, 5);
    expect(move(held, at.cx, at.cy + 1000 * perDegree, 50, at.r).tilt).toBe(MAX_TILT);
    expect(move(held, at.cx, at.cy - 1000 * perDegree, 50, at.r).tilt).toBe(MIN_TILT);
  });

  it("ignores a move with nothing held", () => {
    expect(move(RESTING, 500, 500, 10, at.r)).toBe(RESTING);
  });

  it("coasts after a flick, slows to rest, and keeps where it stopped", () => {
    let state = grab(RESTING, at.cx, at.cy, 0);
    state = move(state, at.cx + 20 * perDegree, at.cy, 100, at.r); // 20 degrees in 0.1 s
    state = release(state, false);
    expect(state.grab).toBeNull();
    expect(state.coast).toBeGreaterThan(100);
    const before = state.turned;
    for (let i = 0; i < 300; i++) state = coast(state, 1 / 60);
    expect(state.coast).toBe(0);
    expect(state.turned).toBeGreaterThan(before);
  });

  it("does not coast with reduced motion", () => {
    let state = grab(RESTING, at.cx, at.cy, 0);
    state = move(state, at.cx + 20 * perDegree, at.cy, 100, at.r);
    expect(release(state, true).coast).toBe(0);
  });
});

/* Under first-run setup's magnification the page is drawn larger by CSS
   `zoom`: the pointer and the canvas's box arrive in window pixels while the
   planet is laid out in the canvas's own. */
describe("on a magnified page", () => {
  const ZOOM = 1.3;
  const layout = { width: 1440, height: 846 };
  const planet = place(layout.width, layout.height);
  const box = { left: 40, top: 12, width: layout.width * ZOOM };
  const drawn = (x: number, y: number): [number, number] => [box.left + x * ZOOM, box.top + y * ZOOM];
  const around = (share: number) => [0, 1, 2, 3, 4, 5, 6, 7].map((eighth) => {
    const angle = (eighth * Math.PI) / 4;
    return drawn(planet.cx + Math.cos(angle) * planet.r * share, planet.cy + Math.sin(angle) * planet.r * share);
  });

  it("answers a press anywhere the planet is drawn, and nowhere beside it", () => {
    for (const [x, y] of [...around(0), ...around(0.5), ...around(0.97)]) {
      expect(onPlanet(...onCanvas(x, y, box, layout.width), planet)).toBe(true);
    }
    for (const [x, y] of around(1.03)) {
      expect(onPlanet(...onCanvas(x, y, box, layout.width), planet)).toBe(false);
    }
  });

  it("would miss the planet's edge if the press were read in window pixels", () => {
    const raw = around(0.97).map(([x, y]) => [x - box.left, y - box.top] as const);
    expect(raw.some(([x, y]) => !onPlanet(x, y, planet))).toBe(true);
  });

  it("turns as far for a drag as on a plain page", () => {
    const [fromX, fromY] = drawn(planet.cx, planet.cy);
    const [toX] = drawn(planet.cx + 30 * ((planet.r * Math.PI) / 180), planet.cy);
    const held = grab(RESTING, ...onCanvas(fromX, fromY, box, layout.width), 0);
    const dragged = move(held, ...onCanvas(toX, fromY, box, layout.width), 100, planet.r);
    expect(dragged.turned).toBeCloseTo(30, 5);
  });

  it("reads a plain page as it is", () => {
    expect(onCanvas(140, 80, { left: 40, top: 30, width: 1440 }, 1440)).toEqual([100, 50]);
    expect(pageScale(1872, 1440)).toBeCloseTo(1.3, 9);
    expect(pageScale(0, 0)).toBe(1);
    expect(pageScale(100, 0)).toBe(1);
  });
});

describe("the planet's backing store", () => {
  it.each([
    [1, 1, 1], [2, 1, 2], [3, 1, 2], [2, 1.3, 2.6], [3, 1.3, 2.6], [1, 1.3, 1.3], [0, 1.2, 1.2],
  ])("at density %f and zoom %f has %f pixels per canvas pixel", (density, zoom, expected) => {
    expect(backingDensity(density, zoom, 2)).toBeCloseTo(expected, 9);
  });
});

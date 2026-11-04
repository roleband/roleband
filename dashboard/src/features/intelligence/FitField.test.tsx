import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import type { IntelligenceFit } from "../../api";
import { msg } from "../../test/msg";
import { intelligenceFitFixture } from "../../test/fixtures";
import { FitField } from "./FitField";
import { fitBandName } from "./serverText";

// The field draws each band at the lower edge the server cut its count at.
// Edges unlike the shipped ones (.70, .40, .30) make a copy of the old
// constants visible: their lines would sit in another proportion.
const moved: IntelligenceFit = {
  ...intelligenceFitFixture,
  bins: [
    { fit: 0.1, count: 3 },
    { fit: 0.36, count: 40 },
    { fit: 0.5, count: 25 },
    { fit: 0.72, count: 4 },
  ],
  bands: [
    { key: "strong", count: 4, lower_edge: 0.7 },
    { key: "good", count: 25, lower_edge: 0.4 },
    { key: "some", count: 40, lower_edge: 0.3 },
    { key: "weak", count: 3, lower_edge: null },
  ],
};

function draw(fit: IntelligenceFit) {
  const { container } = render(<FitField fit={fit} topCount={3} selected={null} onSelect={vi.fn()} />);
  const lines = [...container.querySelectorAll("line.fit-grid")].map((line) => Number(line.getAttribute("y1")));
  const zones = [...container.querySelectorAll("rect.fit-band-zone")].map((rect) => ({
    top: Number(rect.getAttribute("y")) - 1,
    bottom: Number(rect.getAttribute("y")) + Number(rect.getAttribute("height")) + 1,
  }));
  // Every point of the silhouette, signs included: a point drawn above or
  // below the frame has a negative or too-large coordinate.
  const d = container.querySelector("path.fit-shape")?.getAttribute("d") ?? "";
  const cx = Number(d.match(/^M(-?[\d.]+),/)?.[1]);
  const shape = [...d.matchAll(/[ML](-?[\d.]+),(-?[\d.]+)/g)].map((m) => ({ x: Number(m[1]), y: Number(m[2]) }));
  // The silhouette's left side, one point per bin, lowest fit first: the
  // points after the bottom of the centre line, before its top.
  const left = shape.slice(1, 1 + fit.bins.length);
  expect(shape[1 + fit.bins.length].x).toBe(cx);
  // Each band's label as drawn: the name's baseline and the count's.
  const labels = [...container.querySelectorAll("g.fit-band")].map((band) => ({
    name: Number(band.querySelector("text.fit-band-name")?.getAttribute("y")),
    count: Number(band.querySelector("text.fit-band-count")?.getAttribute("y")),
    // The band's hit area in the label gutter (x = 0).
    gutter: [...band.querySelectorAll("rect.fit-band-hit")]
      .filter((rect) => rect.getAttribute("x") === "0")
      .map((rect) => ({
        top: Number(rect.getAttribute("y")),
        bottom: Number(rect.getAttribute("y")) + Number(rect.getAttribute("height")),
      }))[0],
  }));
  return { lines, zones, left, shape, labels };
}

// The installed app's board with no saved role and no aim, only "Not for me":
// the intent points away from every role, so every fit is below zero.
const awayFromEverything: IntelligenceFit = {
  ...intelligenceFitFixture,
  intent_statement: null,
  bins: (
    [
      [-0.66, 1], [-0.64, 3], [-0.62, 8], [-0.6, 12], [-0.58, 29], [-0.56, 108],
      [-0.54, 202], [-0.52, 408], [-0.5, 808], [-0.48, 1482], [-0.46, 2480],
      [-0.44, 3267], [-0.42, 3571], [-0.4, 3135], [-0.38, 2029], [-0.36, 1128],
      [-0.34, 482], [-0.32, 198], [-0.3, 130], [-0.28, 94], [-0.26, 217],
      [-0.24, 311], [-0.22, 356], [-0.2, 336], [-0.18, 241], [-0.16, 133],
      [-0.14, 85], [-0.12, 23], [-0.1, 9], [-0.08, 4],
    ] as const
  ).map(([fit, count]) => ({ fit, count })),
  bands: [
    { key: "strong", count: 0, lower_edge: 0.6 },
    { key: "good", count: 0, lower_edge: 0.5 },
    { key: "some", count: 0, lower_edge: 0.42 },
    { key: "weak", count: 21290, lower_edge: null },
  ],
};

describe("FitField", () => {
  it("draws a line at each band's lower edge, in the payload's proportions", () => {
    const { lines } = draw(moved);
    // Weak is open below: three edges, three lines, highest fit at the top.
    expect(lines).toHaveLength(3);
    expect(lines[0]).toBeLessThan(lines[1]);
    expect(lines[1]).toBeLessThan(lines[2]);
    // Fit maps to height linearly, so the gaps keep the edges' ratio:
    // (.70 - .40) / (.40 - .30) = 3.
    expect((lines[1] - lines[0]) / (lines[2] - lines[1])).toBeCloseTo(3, 6);
  });

  it("spans each band between its own edge and the one above", () => {
    const { lines, zones } = draw(moved);
    expect(zones).toHaveLength(4);
    expect(zones[0].bottom).toBeCloseTo(lines[0], 6);
    expect(zones[1].top).toBeCloseTo(lines[0], 6);
    expect(zones[1].bottom).toBeCloseTo(lines[1], 6);
    expect(zones[2].top).toBeCloseTo(lines[1], 6);
    expect(zones[2].bottom).toBeCloseTo(lines[2], 6);
    expect(zones[3].top).toBeCloseTo(lines[2], 6);
    // Good spans .70 to .40 and some .40 to .30: three times the height.
    const height = (i: number) => zones[i].bottom - zones[i].top;
    expect(height(1) / height(2)).toBeCloseTo(3, 6);
    for (const band of moved.bands) {
      expect(
        screen.getByRole("button", { name: msg("ai-fit-field-roles", { label: fitBandName(band.key), count: String(band.count) }) }),
      ).toBeInTheDocument();
    }
  });

  it("draws each bin across the width the server binned it at", () => {
    // Bins .10 wide: the bin at .30 spans .30 to .40, so its point sits at .35,
    // a quarter of the way from the .30 line to the .50 one.
    const wide: IntelligenceFit = {
      ...moved,
      bin_width: 0.1,
      bins: [
        { fit: 0.3, count: 5 },
        { fit: 0.5, count: 5 },
      ],
      bands: [
        { key: "strong", count: 0, lower_edge: 0.7 },
        { key: "good", count: 5, lower_edge: 0.5 },
        { key: "some", count: 5, lower_edge: 0.3 },
        { key: "weak", count: 0, lower_edge: null },
      ],
    };
    const { lines, left } = draw(wide);
    expect(left).toHaveLength(2);
    expect((lines[2] - left[0].y) / (lines[2] - lines[1])).toBeCloseTo(0.25, 2);
    expect((lines[1] - left[1].y) / (lines[1] - lines[0])).toBeCloseTo(0.25, 2);
  });

  it("reaches past the outermost edges wherever the payload puts them", () => {
    // Every role sits below all three edges (.90, .80, .75): the field still
    // draws each line inside the frame, with strong and weak given a height.
    const high: IntelligenceFit = {
      ...moved,
      bins: [{ fit: 0.5, count: 72 }],
      bands: [
        { key: "strong", count: 0, lower_edge: 0.9 },
        { key: "good", count: 0, lower_edge: 0.8 },
        { key: "some", count: 0, lower_edge: 0.75 },
        { key: "weak", count: 72, lower_edge: null },
      ],
    };
    const { lines, zones } = draw(high);
    expect((lines[1] - lines[0]) / (lines[2] - lines[1])).toBeCloseTo(2, 6);
    for (const y of lines) {
      expect(y).toBeGreaterThan(0);
      expect(y).toBeLessThan(300);
    }
    expect(zones[0].bottom - zones[0].top).toBeGreaterThan(0);
    expect(zones[3].bottom - zones[3].top).toBeGreaterThan(0);
  });

  it("draws every role inside the frame when every fit is below zero", () => {
    const { shape, left, lines, zones } = draw(awayFromEverything);
    expect(left).toHaveLength(awayFromEverything.bins.length);
    for (const point of shape) {
      expect(point.x).toBeGreaterThanOrEqual(96);
      expect(point.x).toBeLessThanOrEqual(320);
      expect(point.y).toBeGreaterThanOrEqual(0);
      expect(point.y).toBeLessThanOrEqual(300);
    }
    // The roles sit in the weak band, below the fair line, and the weak
    // band reaches down to hold the lowest of them.
    const fairLine = lines[2];
    for (const point of left) expect(point.y).toBeGreaterThan(fairLine);
    expect(zones[3].bottom).toBeGreaterThan(Math.max(...left.map((point) => point.y)));
  });

  it("keeps band labels apart when the bands are thinner than their labels", () => {
    const { labels, lines } = draw(awayFromEverything);
    // The three upper bands are thin here: their middles are closer together
    // than one label is tall, so drawn at their middles they would overprint.
    expect(lines[1] - lines[0]).toBeLessThan(34);
    for (const label of labels) {
      expect(label.name).toBeGreaterThanOrEqual(13);
      expect(label.count).toBeLessThan(300);
    }
    for (let i = 1; i < labels.length; i++) {
      // A name's glyphs rise about one line above its baseline.
      expect(labels[i].name - labels[i - 1].count).toBeGreaterThanOrEqual(16);
    }
    // Each label lies inside its own band's slice of the gutter, and the
    // slices do not overlap, so a click on a label reaches its band.
    for (const label of labels) {
      expect(label.gutter.top).toBeLessThanOrEqual(label.name - 12);
      expect(label.gutter.bottom).toBeGreaterThanOrEqual(label.count + 3);
    }
    for (let i = 1; i < labels.length; i++) {
      expect(labels[i].gutter.top).toBeGreaterThanOrEqual(labels[i - 1].gutter.bottom);
    }
  });

  it("leaves labels at their band's middle when the bands have room", () => {
    const { labels, zones } = draw(moved);
    labels.forEach((label, i) => {
      expect(label.name + 3).toBeCloseTo((zones[i].top + zones[i].bottom) / 2, 6);
    });
    // The gutter slices still cover the whole gutter, top to bottom.
    expect(labels[0].gutter.top).toBe(0);
    expect(labels[labels.length - 1].gutter.bottom).toBe(300);
    for (let i = 1; i < labels.length; i++) {
      expect(labels[i].gutter.top).toBeCloseTo(labels[i - 1].gutter.bottom, 6);
    }
  });
});

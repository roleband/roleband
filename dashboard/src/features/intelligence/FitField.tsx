import { number as copyNumber } from "../../copy/format";
// The field: the board's fit distribution drawn as a vertical silhouette.
// Fit RISES, so the best matches sit at the top, bracketed. Up is good; a
// horizontal curve would put the strongest roles at a bottom-right tail,
// which reads as "you are at the bottom of a falling chart".
//
// Each band is an instrument control, not just a label: hovering tints the
// band's slice of the field, clicking selects it and the preview list beside
// the field shows that band's strongest roles. The bracket always marks what
// the list is showing: the top of the field by default, the selected band's
// span otherwise.
//
// Dataviz SVG, not an icon: drawn inline on purpose.
// Colours come from the ledger scope via CSS classes; nothing is hard-coded.
import { KeyboardEvent } from "react";
import { IntelligenceFit, IntelligenceFitBand } from "../../api";
import {
  aiFitFieldFitOfOpenRolesRising,
  aiFitFieldRoles,
} from "../../copy/gen/ai";
import { fitBandName } from "./serverText";

export type FitBandKey = IntelligenceFitBand["key"];

const WIDTH = 320;
const HEIGHT = 300;
const AXIS = 96; // left gutter for band names + counts
/** Empty fit above and below what is drawn, so nothing touches the frame. */
const MARGIN = 0.02;
/** Fit is cosine similarity, so it spans -1 to 1. An intent built only from
 *  "Not for me" points away from the whole board and every fit is negative;
 *  the field reaches down to wherever the bins are. */
const FIT_FLOOR = -1;
const FIT_CEIL = 1;
/** A band's name sits 3 above its label point and its count 13 below; two
 *  labels closer than this overlap. */
const LABEL_PITCH = 34;
/** Room above the first name's baseline and below the last count's. */
const LABEL_TOP = 16;
const LABEL_BOTTOM = HEIGHT - 17;

interface Layout {
  y: (fit: number) => number;
  lo: number;
  hi: number;
  /** The fit one histogram bin spans, as the server binned it (`bin_width`). */
  bin: number;
}

/** The edges the server cut the band counts at (each band's `lower_edge`),
 *  highest first; weak has none, being open below. */
function bandEdges(fit: IntelligenceFit): number[] {
  return fit.bands.flatMap((b) => (b.lower_edge == null ? [] : [b.lower_edge]));
}

function layout(fit: IntelligenceFit, edges: number[]): Layout {
  const bin = fit.bin_width;
  const bins = fit.bins.map((b) => b.fit);
  // The field always reaches one bin past the outermost band edges, so the
  // open-ended top and bottom bands always have a height to draw.
  const lo = Math.max(FIT_FLOOR, Math.min(...bins, ...edges.map((e) => e - bin)) - MARGIN);
  // A bin's `fit` is its lower edge, so the top bin reaches one width higher.
  const hi = Math.min(FIT_CEIL, Math.max(...bins, ...edges.map((e) => e + bin)) + bin + MARGIN);
  const y = (v: number) => HEIGHT - 6 - ((v - lo) / (hi - lo)) * (HEIGHT - 12);
  return { y, lo, hi, bin };
}

/** Closed silhouette path: half-width per bin, mirrored around the center. */
function shapePath(fit: IntelligenceFit, l: Layout): string {
  const cx = AXIS + (WIDTH - AXIS) / 2;
  const max = Math.max(...fit.bins.map((b) => b.count), 1);
  const half = (count: number) => (count / max) * ((WIDTH - AXIS) / 2 - 6);
  const pts = fit.bins.map((b) => ({ y: l.y(b.fit + l.bin / 2), w: half(b.count) }));
  const down = pts.map((p) => `L${(cx - p.w).toFixed(1)},${p.y.toFixed(1)}`).join(" ");
  const up = [...pts]
    .reverse()
    .map((p) => `L${(cx + p.w).toFixed(1)},${p.y.toFixed(1)}`)
    .join(" ");
  return `M${cx},${l.y(l.lo).toFixed(1)} ${down} L${cx},${l.y(l.hi).toFixed(1)} ${up} Z`;
}

/** Band fit stops, highest first: the field's top, then each band's lower
 *  edge (weak's is the field's bottom). Band i spans stops[i] (top) down to
 *  stops[i+1]. */
function bandStops(fit: IntelligenceFit, l: Layout): number[] {
  return [l.hi, ...fit.bands.map((b) => b.lower_edge ?? l.lo)];
}

/** Where each band's label sits: its band's middle, pushed apart where bands
 *  are thinner than two lines of text, and kept inside the frame. Bands are
 *  ordered top to bottom, so the labels keep that order. */
function labelPoints(mids: number[]): number[] {
  const points = [...mids];
  for (let i = 0; i < points.length; i++) {
    points[i] = Math.max(points[i], i === 0 ? LABEL_TOP : points[i - 1] + LABEL_PITCH);
  }
  for (let i = points.length - 1; i >= 0; i--) {
    points[i] = Math.min(points[i], i === points.length - 1 ? LABEL_BOTTOM : points[i + 1] - LABEL_PITCH);
  }
  return points;
}

/** The label gutter cut into one slice per band, top to bottom. A slice ends
 *  at its band's lower line, moved only as far as needed to hold the whole of
 *  its own label and none of the next, so a click on a label always reaches
 *  that label's band. */
function gutterCuts(lines: number[], points: number[]): number[] {
  const half = LABEL_PITCH / 2;
  const inner = lines.map((line, i) =>
    Math.min(Math.max(line, points[i] + half), points[i + 1] - half),
  );
  return [0, ...inner, HEIGHT];
}

export function FitField({
  fit,
  topCount,
  selected,
  onSelect,
}: {
  fit: IntelligenceFit;
  topCount: number;
  selected: FitBandKey | null;
  onSelect: (band: FitBandKey | null) => void;
}) {
  if (fit.bins.length === 0) return null;
  const edges = bandEdges(fit);
  const l = layout(fit, edges);
  const cx = AXIS + (WIDTH - AXIS) / 2;
  const stops = bandStops(fit, l);
  const best = fit.bins[fit.bins.length - 1];
  const tops = stops.slice(0, -1).map(l.y);
  const bottoms = stops.slice(1).map(l.y);
  const points = labelPoints(tops.map((top, i) => (top + bottoms[i]) / 2));
  const cuts = gutterCuts(bottoms.slice(0, -1), points);

  // The bracket marks what the preview list shows: the selected few at the
  // top by default, the selected band's whole span otherwise.
  const bracketTop = selected
    ? l.y(stops[fit.bands.findIndex((b) => b.key === selected)]) + 2
    : l.y(Math.min(best.fit + l.bin + 0.01, l.hi));
  const bracketBottom = selected
    ? l.y(stops[fit.bands.findIndex((b) => b.key === selected) + 1]) - 2
    : Math.min(l.y(best.fit) + 26, HEIGHT - 8);

  const toggle = (key: FitBandKey) => onSelect(selected === key ? null : key);
  const onKey = (e: KeyboardEvent, key: FitBandKey) => {
    if (e.key === "Enter" || e.key === " ") {
      e.preventDefault();
      toggle(key);
    }
  };

  return (
    <svg
      className="intel-field-svg"
      viewBox={`0 0 ${WIDTH} ${HEIGHT}`}
      width={WIDTH}
      height={HEIGHT}
      role="group"
      aria-label={aiFitFieldFitOfOpenRolesRising({ total: String(copyNumber(fit.total)), join: String(fit.bands.map((b) => `${fitBandName(b.key)} ${b.count}`).join(", ")) })}
    >
      {edges.map((edge) => (
        <line
          key={edge}
          className="fit-grid"
          x1={AXIS}
          y1={l.y(edge)}
          x2={WIDTH}
          y2={l.y(edge)}
          strokeDasharray="2 3"
        />
      ))}
      <path className="fit-shape" d={shapePath(fit, l)} />
      {/* the selected few, as dots at the very top of the field */}
      {Array.from({ length: Math.min(topCount, 6) }, (_, i) => (
        <circle
          key={i}
          className="fit-top"
          cx={cx + [0, -5, 6, -2, 4, -6][i]}
          cy={l.y(best.fit + l.bin / 2) + (i % 3) * 3}
          r={2.6}
        />
      ))}
      <path
        className="fit-bracket"
        d={
          selected
            ? `M${WIDTH - 9},${bracketTop.toFixed(1)} h8 V${bracketBottom.toFixed(1)} h-8`
            : `M${cx + 22},${bracketTop.toFixed(1)} h8 V${bracketBottom.toFixed(1)} h-8`
        }
      />
      {fit.bands.map((band, i) => {
        const top = tops[i];
        const bottom = bottoms[i];
        const label = points[i];
        return (
          <g
            key={band.key}
            className="fit-band"
            role="button"
            tabIndex={0}
            aria-pressed={selected === band.key}
            aria-label={aiFitFieldRoles({ label: String(fitBandName(band.key)), count: String(copyNumber(band.count)) })}
            onClick={() => toggle(band.key)}
            onKeyDown={(e) => onKey(e, band.key)}
          >
            <rect
              className="fit-band-zone"
              x={AXIS}
              y={top + 1}
              width={WIDTH - AXIS}
              height={Math.max(bottom - top - 2, 0)}
            />
            <text className="fit-band-name" x={AXIS - 12} y={label - 3} textAnchor="end">
              {fitBandName(band.key)}
            </text>
            <text className="fit-band-count" x={AXIS - 12} y={label + 13} textAnchor="end">
              {copyNumber(band.count)}
            </text>
            {/* Two hit areas: the band's own span across the field, and its
                slice of the label gutter, which follows the label. */}
            <rect
              className="fit-band-hit"
              x={AXIS}
              y={top}
              width={WIDTH - AXIS}
              height={Math.max(bottom - top, 0)}
            />
            <rect
              className="fit-band-hit"
              x={0}
              y={cuts[i]}
              width={AXIS}
              height={Math.max(cuts[i + 1] - cuts[i], 0)}
            />
          </g>
        );
      })}
    </svg>
  );
}

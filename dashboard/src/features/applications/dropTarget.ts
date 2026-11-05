/* Where a dragged card would land, and how the board scrolls under a drag.
 * Pure functions of the board's geometry, so the tests hold them without a
 * layout engine. A drop is generous: anywhere over a column's width counts,
 * above or below its cards, and a gap between two columns counts for the
 * nearer one. In a column split into sections, the section nearest the
 * pointer takes the card. */

import type { StageSlug } from "../../copy/vocabulary";

export interface DropColumn {
  left: number;
  right: number;
  /** The column's sections, top to bottom. A column of one stage has one. */
  sections: readonly { stage: StageSlug; top: number; bottom: number }[];
}

/** How far a point lies outside a span; 0 inside it. */
const outside = (point: number, from: number, to: number) =>
  point < from ? from - point : point > to ? point - to : 0;

function nearest<T>(items: readonly T[], away: (item: T) => number): T | null {
  let best: T | null = null;
  let least = Infinity;
  for (const item of items) {
    const distance = away(item);
    if (distance < least) {
      least = distance;
      best = item;
    }
  }
  return best;
}

/** The stage a card dropped at (x, y) moves to. */
export function dropStageAt(columns: readonly DropColumn[], x: number, y: number): StageSlug | null {
  const column = nearest(columns, (candidate) => outside(x, candidate.left, candidate.right));
  if (!column) return null;
  return nearest(column.sections, (section) => outside(y, section.top, section.bottom))?.stage ?? null;
}

/** The band along each side of the board where a held drag scrolls it. */
const EDGE = 48;
/** The fastest a drag scrolls the board, in pixels a frame. */
const TOP_SPEED = 18;

/** How far the board scrolls this frame under a drag at x: nothing away from
 *  its edges, faster the deeper into an edge's band, and the most past it. */
export function edgeSpeed(x: number, left: number, right: number): number {
  const depth = x < left + EDGE ? x - (left + EDGE) : x > right - EDGE ? x - (right - EDGE) : 0;
  if (depth === 0) return 0;
  return Math.sign(depth) * Math.ceil(TOP_SPEED * Math.min(1, Math.abs(depth) / EDGE));
}

/** How far to scroll the board this frame: the edge's speed, stopped where
 *  the first or last column comes fully into view. The dragged card is drawn
 *  inside the board, so the board's own scroll width grows with every step
 *  it is carried; measured by that, a drag held at the edge would chase the
 *  card forever. */
export function scrollStep(speed: number, columns: readonly DropColumn[], left: number, right: number): number {
  const first = columns[0];
  const last = columns[columns.length - 1];
  if (!first || !last || speed === 0) return 0;
  if (speed > 0) return Math.max(0, Math.min(speed, last.right - right));
  return Math.min(0, Math.max(speed, first.left - left));
}

/** The board's columns as drawn now. Read on every move: the board scrolls
 *  under a drag, and a column's sections grow as cards land. */
export function readDropColumns(root: Element): DropColumn[] {
  return [...root.querySelectorAll<HTMLElement>("[data-drop-column]")].map((column) => {
    const box = column.getBoundingClientRect();
    return {
      left: box.left,
      right: box.right,
      sections: [...column.querySelectorAll<HTMLElement>("[data-drop-stage]")].map((section) => {
        const rect = section.getBoundingClientRect();
        return { stage: section.dataset.dropStage as StageSlug, top: rect.top, bottom: rect.bottom };
      }),
    };
  });
}

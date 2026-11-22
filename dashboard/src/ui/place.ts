// Where a floating panel goes beside the element it belongs to: below it, or
// above when below would run off the window, and moved sideways no further than
// keeps it on screen. Popover and InfoTip both place through here, so the two
// cannot disagree about the window's edges.

export interface Side {
  top: number;
  bottom: number;
  left: number;
  right: number;
}

export interface PlaceOptions {
  /** Space between the anchor and the panel. */
  gap: number;
  /** The least space kept between the panel and the window's edge. */
  margin: number;
  /** Which of the anchor's edges the panel lines up with. Default "start". */
  align?: "start" | "end";
}

/** The panel's top: below the anchor, flipped above it when a measured panel
 *  would fall off the bottom, and never above the window's top margin. */
export function placeTop(anchor: Side, height: number, windowHeight: number, { gap, margin }: PlaceOptions): number {
  const below = anchor.bottom + gap;
  if (height && below + height > windowHeight - margin) return Math.max(margin, anchor.top - height - gap);
  return below;
}

/** The panel's left: lined up with the anchor's start or end edge, then held
 *  inside the window's side margins. A panel wider than the window starts at
 *  the left margin, so its start can always be read. */
export function placeLeft(anchor: Side, width: number, windowWidth: number, { margin, align = "start" }: PlaceOptions): number {
  const left = align === "end" ? anchor.right - width : anchor.left;
  return Math.max(margin, Math.min(left, windowWidth - width - margin));
}

import { useEffect, type RefObject } from "react";

/* Which of the description's section headings is stuck at the top of the
 * scroll box, marked `data-stuck` on the heading. A stuck heading draws a
 * ground that covers what passes under it; one in its place draws none, so
 * that ground never lies over the section's own first line.
 *
 * CSS has no signal for a sticky element being stuck in every browser
 * (`scroll-state(stuck)` is Chromium's only), so it is read from the
 * heading's own box: a heading cut by a line one pixel below where it sticks
 * is at that line or past it. One below the bottom edge is cut too, and is
 * told apart by where it is.
 *
 * Where a heading sticks is its own `top`: under the posting's tabs, when it
 * has them, rather than at the box's edge. The line is read from the styles.
 */
export function useStuckHeadings(sections: RefObject<HTMLElement | null>, key: unknown): void {
  useEffect(() => {
    const list = sections.current;
    if (!list) return;
    return markStuck(Array.from(list.querySelectorAll<HTMLElement>(":scope > .jd-section > h2")));
  }, [sections, key]);
}

/** The posting's tabs, marked `data-stuck` the same way while they are held
 *  under the bar: in their place they draw no ground over the hero's. */
export function useStuckTabs(tabs: HTMLElement | null): void {
  useEffect(() => (tabs ? markStuck([tabs]) : undefined), [tabs]);
}

/** Marks each of the elements, all sticking at one `top` in the posting's
 *  scroll box, while it is stuck there. Returns the way to stop. */
function markStuck(elements: HTMLElement[]): (() => void) | undefined {
  const root = elements[0]?.closest<HTMLElement>(".cover-scroll") ?? null;
  if (!root || typeof IntersectionObserver === "undefined") return;
  const inset = parseFloat(getComputedStyle(elements[0]).top) || 0;
  const seen = new IntersectionObserver(
    (entries) => {
      for (const entry of entries) {
        const top = entry.rootBounds?.top ?? root.getBoundingClientRect().top + inset;
        const stuck = entry.intersectionRatio < 1 && entry.boundingClientRect.top <= top + 1;
        entry.target.toggleAttribute("data-stuck", stuck);
      }
    },
    { root, rootMargin: `-${inset + 1}px 0px 0px 0px`, threshold: [0, 1] },
  );
  for (const element of elements) seen.observe(element);
  return () => {
    seen.disconnect();
    for (const element of elements) element.removeAttribute("data-stuck");
  };
}

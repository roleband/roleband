import { useEffect, type RefObject } from "react";

/* Which of the description's section headings is stuck at the top of the
 * scroll box, marked `data-stuck` on the heading. A stuck heading draws a
 * ground that covers what passes under it; one in its place draws none, so
 * that ground never lies over the section's own first line.
 *
 * CSS has no signal for a sticky element being stuck in every browser
 * (`scroll-state(stuck)` is Chromium's only), so it is read from the
 * heading's own box: a heading cut by a line one pixel below the scroll box's
 * top edge is at that edge or past it. One below the bottom edge is cut too,
 * and is told apart by where it is.
 */
export function useStuckHeadings(sections: RefObject<HTMLElement | null>, key: unknown): void {
  useEffect(() => {
    const list = sections.current;
    const root = list?.closest<HTMLElement>(".cover-scroll") ?? null;
    if (!list || !root || typeof IntersectionObserver === "undefined") return;
    const headings = Array.from(list.querySelectorAll<HTMLElement>(":scope > .jd-section > h2"));
    const seen = new IntersectionObserver(
      (entries) => {
        for (const entry of entries) {
          const top = entry.rootBounds?.top ?? root.getBoundingClientRect().top;
          const stuck = entry.intersectionRatio < 1 && entry.boundingClientRect.top <= top + 1;
          entry.target.toggleAttribute("data-stuck", stuck);
        }
      },
      { root, rootMargin: "-1px 0px 0px 0px", threshold: [0, 1] },
    );
    for (const heading of headings) seen.observe(heading);
    return () => {
      seen.disconnect();
      for (const heading of headings) heading.removeAttribute("data-stuck");
    };
  }, [sections, key]);
}

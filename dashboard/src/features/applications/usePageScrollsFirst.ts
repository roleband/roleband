import { useEffect } from "react";

/** Pixels per wheel step when the wheel reports lines or pages, not pixels. */
const LINE = 16;

/** A scroll down over `node` moves the page first, until the page can go no
 *  further, and only then `node` itself. The Board's frame scrolls inside the
 *  page: left to the browser, a wheel over it would scroll the columns while
 *  the page's title and tabs stayed on screen, where the Radar's list scrolls
 *  them away and docks its toolbar at once. Up is the browser's own order
 *  (the frame to its top, then the page), which brings them back last. A
 *  scroll mostly sideways, or a pinch (ctrl), is left alone. */
export function usePageScrollsFirst(node: HTMLElement | null): void {
  useEffect(() => {
    const page = node?.closest("main");
    if (!node || !page) return;
    const onWheel = (event: WheelEvent) => {
      if (event.ctrlKey || event.deltaY <= 0 || Math.abs(event.deltaX) > Math.abs(event.deltaY)) return;
      const room = page.scrollHeight - page.clientHeight - page.scrollTop;
      if (room < 1) return;
      const step = event.deltaMode === WheelEvent.DOM_DELTA_LINE ? LINE
        : event.deltaMode === WheelEvent.DOM_DELTA_PAGE ? page.clientHeight : 1;
      event.preventDefault();
      page.scrollTop += Math.min(room, event.deltaY * step);
    };
    node.addEventListener("wheel", onWheel, { passive: false });
    return () => node.removeEventListener("wheel", onWheel);
  }, [node]);
}

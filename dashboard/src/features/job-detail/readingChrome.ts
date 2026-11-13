import { useEffect, useRef, type RefObject } from "react";

/* What answers the posting's scroll, beside the text itself.
 *
 * - The role in the bar. Once the posting's heading has left the scroll box,
 *   the bar's middle carries the title, the company and the level, starting
 *   at the heading's own left edge so it reads as the heading risen into the
 *   bar.
 * - The pay panel's small copy. The panel leads the page; as its last part
 *   leaves, the copy grows at the top of the side column and its figure comes
 *   down from the panel's size. The copy follows the scroll, forward and
 *   back, so its state is the scroll position's and nothing else's.
 *
 * Both are written straight to the elements: a scroll frame renders nothing.
 * The one thing told to the screen is the moment the copy has grown whole and
 * the moment it starts to go (`onDocked`): the person is reading, or back at
 * the top.
 */

/** How much of the panel's exit the copy grows over, in pixels. */
const HANDOVER = 170;

export function useReadingChrome(
  scrollRef: RefObject<HTMLElement | null>,
  { title, main, dock, role }: { title: HTMLElement | null; main: HTMLElement | null; dock: HTMLElement | null; role: HTMLElement | null },
  onDocked?: (docked: boolean) => void,
): void {
  const told = useRef(onDocked);
  useEffect(() => {
    told.current = onDocked;
  });
  useEffect(() => {
    const scroller = scrollRef.current;
    if (!scroller || !title) return;
    const calm = typeof matchMedia === "function" && matchMedia("(prefers-reduced-motion: reduce)").matches;
    let docked = false;
    let shown = -1;

    const read = () => {
      const top = scroller.getBoundingClientRect().top;

      if (role) {
        const heading = title.getBoundingClientRect();
        const gap = heading.left - role.getBoundingClientRect().left;
        role.style.paddingLeft = `${Math.max(0, gap).toFixed(2)}px`;
        // A heading with no box yet has not left: it has not arrived.
        role.toggleAttribute("data-shown", heading.height > 0 && heading.bottom <= top);
      }

      if (dock) {
        const panel = main?.querySelector(".pkg-panel") ?? null;
        let progress = 0;
        // No panel, or a side column that follows the text in one column: nothing docks.
        if (panel && dock.offsetParent !== null) {
          progress = Math.min(1, Math.max(0, (top + HANDOVER - panel.getBoundingClientRect().bottom) / HANDOVER));
        }
        if (calm) progress = progress >= 1 ? 1 : 0;
        // Only on a change: the handover is a few dozen frames of a scroll
        // that is otherwise all 0 or all 1, and the row size is layout, so
        // writing it again for the same value would lay the column out for
        // nothing.
        if (progress !== shown) {
          shown = progress;
          dock.style.gridTemplateRows = `${progress.toFixed(4)}fr`;
          dock.style.setProperty("--jd-dock", progress.toFixed(4));
        }
        // Told when the copy is whole and again only when it is gone, so a
        // column that changes height on being told cannot flip it back. A
        // side column taller than the text sets the page's length: changing
        // it would move the scroll, so there it is never told.
        const column = dock.parentElement;
        const textLeads = !!main && !!column && main.getBoundingClientRect().height >= column.getBoundingClientRect().height;
        const next = progress >= 1 && textLeads ? true : progress <= 0 ? false : docked;
        if (next !== docked) {
          docked = next;
          told.current?.(docked);
        }
      }
    };

    read();
    scroller.addEventListener("scroll", read, { passive: true });
    window.addEventListener("resize", read);
    const seen = typeof ResizeObserver === "undefined" ? null : new ResizeObserver(read);
    seen?.observe(scroller);
    // What the box scrolls: when it grows a scrollbar, the heading moves.
    if (scroller.firstElementChild) seen?.observe(scroller.firstElementChild);
    if (main) seen?.observe(main);
    return () => {
      scroller.removeEventListener("scroll", read);
      window.removeEventListener("resize", read);
      seen?.disconnect();
      if (docked) told.current?.(false);
    };
  }, [scrollRef, title, main, dock, role]);
}

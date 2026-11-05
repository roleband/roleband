import { useEffect, useRef, useState } from "react";

/** Which ways a sideways scroller can still move, and the room its own
 *  scrollbars take, so a fade drawn over an edge stops short of them. */
export interface ScrollEdges {
  back: boolean;
  on: boolean;
  barX: number;
  barY: number;
}

const NONE: ScrollEdges = { back: false, on: false, barX: 0, barY: 0 };

const same = (a: ScrollEdges, b: ScrollEdges) =>
  a.back === b.back && a.on === b.on && a.barX === b.barX && a.barY === b.barY;

/** Kept current as `node` scrolls, as it resizes, and after every render of
 *  the component that holds it: a column hidden or shown changes how far the
 *  content reaches without resizing any box. The node is a node, not a ref,
 *  because the board mounts only once it has loaded. */
export function useScrollEdges(node: HTMLElement | null): ScrollEdges {
  const [edges, setEdges] = useState(NONE);
  const remeasure = useRef<(() => void) | null>(null);
  // Every render, on purpose; the state only changes when an edge does.
  useEffect(() => remeasure.current?.());
  useEffect(() => {
    if (!node) return;
    const measure = () => {
      const travel = node.scrollWidth - node.clientWidth;
      const at = Math.abs(node.scrollLeft);
      const next = {
        back: at > 1,
        on: at < travel - 1,
        barX: node.offsetHeight - node.clientHeight,
        barY: node.offsetWidth - node.clientWidth,
      };
      setEdges((was) => (same(was, next) ? was : next));
    };
    measure();
    remeasure.current = measure;
    node.addEventListener("scroll", measure, { passive: true });
    const observer = typeof ResizeObserver === "undefined" ? null : new ResizeObserver(measure);
    observer?.observe(node);
    if (node.firstElementChild) observer?.observe(node.firstElementChild);
    return () => {
      node.removeEventListener("scroll", measure);
      observer?.disconnect();
      remeasure.current = null;
    };
  }, [node]);
  return edges;
}

/** Scroll `node` one column toward `direction`, landing on a column's edge. */
export function stepColumns(node: HTMLElement, direction: -1 | 1, column: string) {
  const first = node.querySelector<HTMLElement>(column);
  const second = first?.nextElementSibling as HTMLElement | null | undefined;
  const pitch = first && second ? second.offsetLeft - first.offsetLeft : node.clientWidth * 0.8;
  const target = Math.round((node.scrollLeft + direction * pitch) / pitch) * pitch;
  const reduced = window.matchMedia?.("(prefers-reduced-motion: reduce)").matches ?? false;
  node.scrollTo({ left: target, behavior: reduced ? "auto" : "smooth" });
}

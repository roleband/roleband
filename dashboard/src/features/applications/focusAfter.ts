import { useCallback, useEffect, useRef } from "react";

/* Focus for a control that acts and then leaves the page: a card moved to
 * another column, a row removed, a column hidden, a filter chip taken off.
 * The menu it opened has nothing to hand focus back to, and the reader would
 * be dropped at the top of the page. The view names where focus goes when it
 * acts, and the control takes focus once the change has drawn. A target that
 * has not appeared within a moment is let go, so a late render never pulls
 * focus away from where the reader has gone since. */

export type FocusTarget = () => HTMLElement | null | undefined;

const PATIENCE_MS = 1500;

/** Returns `focusAfter(target)`: focus `target()` after the next render that
 *  draws it, in the component that holds the hook. */
export function useFocusAfter(): (target: FocusTarget) => void {
  const pending = useRef<{ target: FocusTarget; until: number } | null>(null);
  // Every render, on purpose: the change that draws the target is a render.
  useEffect(() => {
    const want = pending.current;
    if (!want) return;
    if (performance.now() > want.until) {
      pending.current = null;
      return;
    }
    const element = want.target();
    if (!element?.isConnected) return;
    pending.current = null;
    element.focus();
  });
  return useCallback((target: FocusTarget) => {
    pending.current = { target, until: performance.now() + PATIENCE_MS };
  }, []);
}

/** The `control` inside the item after `item` among `items`, else the one
 *  before it: the neighbour that takes focus when `item` leaves. Read it
 *  before the change, while `item` is still on the page. */
export function beside(item: Element | null | undefined, items: Iterable<Element>, control: string): HTMLElement | null {
  const all = [...items];
  const at = item ? all.indexOf(item) : -1;
  if (at < 0) return null;
  const other = all[at + 1] ?? all[at - 1];
  return other?.querySelector<HTMLElement>(control) ?? null;
}

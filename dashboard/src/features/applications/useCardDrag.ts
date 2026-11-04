import { useEffect, useState } from "react";
import type { MouseEvent as ReactMouseEvent, PointerEvent as ReactPointerEvent, RefObject } from "react";
import type { ApplicationCard } from "../../api";
import type { StageSlug } from "../../copy/vocabulary";
import { useEscapeLayer } from "../../ui";
import { dropStageAt, edgeSpeed, readDropColumns, scrollStep } from "./dropTarget";

/* Dragging a card to another column: the fast path for a move the card's menu
 * also makes, which stays the keyboard's path.
 *
 * A press becomes a drag only after it travels THRESHOLD pixels, and only then
 * does the card capture the pointer. Capturing on the press would send the
 * click that ends a plain press to the card instead of its title link, and the
 * link would never open. After a drag, the click the release produces is
 * swallowed, so a drop does not also open the application.
 *
 * The card follows the pointer by a transform, measured from where it was
 * pressed plus how far the board has scrolled since: the board scrolls under
 * a drag held at its edge, and the card is drawn inside the board. */

const THRESHOLD = 4;

export interface CardDragState {
  jobId: number;
  /** The stage the card is in, where a drop changes nothing. */
  stage: StageSlug;
  /** Where a drop now would move it; null where a drop does nothing. */
  target: StageSlug | null;
  /** How far the card is drawn from its place. */
  dx: number;
  dy: number;
}

export interface CardDragHandlers {
  onPointerDown: (event: ReactPointerEvent<HTMLElement>) => void;
  onPointerMove: (event: ReactPointerEvent<HTMLElement>) => void;
  onPointerUp: (event: ReactPointerEvent<HTMLElement>) => void;
  onPointerCancel: (event: ReactPointerEvent<HTMLElement>) => void;
  onLostPointerCapture: (event: ReactPointerEvent<HTMLElement>) => void;
  onClickCapture: (event: ReactMouseEvent<HTMLElement>) => void;
}

interface Press {
  card: ApplicationCard;
  element: HTMLElement;
  pointerId: number;
  startX: number;
  startY: number;
  x: number;
  y: number;
  scrollStart: number;
  moved: boolean;
  /** Escape gave the drag up while the pointer is still down. */
  dropped: boolean;
}

/* jsdom implements neither capture method, and both can throw on a pointer
   the browser no longer counts as active. An uncaptured drag still tracks
   while the pointer stays on the card. */
function capture(element: Element, pointerId: number) {
  try {
    element.setPointerCapture(pointerId);
  } catch {
    // Tracked without capture.
  }
}

function release(element: Element, pointerId: number) {
  try {
    if (element.hasPointerCapture?.(pointerId)) element.releasePointerCapture(pointerId);
  } catch {
    // Already released: the browser drops capture at pointerup on its own.
  }
}

/** The drag's state outside React: the press, the click latch and the frame.
 *  One per board, made once, so the handlers of every render share it. */
function cardDragMachine(scroller: RefObject<HTMLElement | null>, show: (state: CardDragState | null) => void) {
  let held: Press | null = null;
  let swallow = false;
  let frame: number | null = null;

  /* The click a release produces arrives in the same task as the release, so
     the latch lasts no longer: a later click, from the keyboard on another
     card, is never mistaken for a drag's tail. */
  const swallowNextClick = () => {
    swallow = true;
    setTimeout(() => {
      swallow = false;
    }, 0);
  };

  const targetAt = (x: number, y: number): StageSlug | null => {
    const root = scroller.current;
    if (!root) return null;
    const box = root.getBoundingClientRect();
    if (x < box.left || x > box.right || y < box.top || y > box.bottom) return null;
    return dropStageAt(readDropColumns(root), x, y);
  };

  /** One redraw a frame, however fast moves arrive. Held at the board's edge,
   *  the board keeps scrolling with no move to drive it. */
  const paint = () => {
    frame = null;
    const root = scroller.current;
    if (!held?.moved || !root) return;
    const box = root.getBoundingClientRect();
    const speed = held.y >= box.top && held.y <= box.bottom ? edgeSpeed(held.x, box.left, box.right) : 0;
    const step = scrollStep(speed, readDropColumns(root), box.left, box.right);
    const before = root.scrollLeft;
    if (step) root.scrollLeft = before + step;
    show({
      jobId: held.card.job_id,
      stage: held.card.stage,
      target: targetAt(held.x, held.y),
      dx: held.x - held.startX + root.scrollLeft - held.scrollStart,
      dy: held.y - held.startY,
    });
    if (root.scrollLeft !== before) schedule();
  };
  const schedule = () => {
    if (frame === null) frame = requestAnimationFrame(paint);
  };

  const end = (): Press | null => {
    if (frame !== null) cancelAnimationFrame(frame);
    frame = null;
    const was = held;
    held = null;
    if (was) release(was.element, was.pointerId);
    if (was?.moved) show(null);
    return was;
  };

  return {
    press(card: ApplicationCard, event: ReactPointerEvent<HTMLElement>) {
      swallow = false;
      if (held || event.button !== 0 || event.pointerType === "touch") return;
      // The card's menu button is a control of its own, not a handle.
      if (event.target instanceof Element && event.target.closest("button")) return;
      held = {
        card,
        element: event.currentTarget,
        pointerId: event.pointerId,
        startX: event.clientX,
        startY: event.clientY,
        x: event.clientX,
        y: event.clientY,
        scrollStart: scroller.current?.scrollLeft ?? 0,
        moved: false,
        dropped: false,
      };
    },
    move(event: ReactPointerEvent<HTMLElement>) {
      if (!held || held.pointerId !== event.pointerId || held.dropped) return;
      held.x = event.clientX;
      held.y = event.clientY;
      if (!held.moved) {
        if (Math.hypot(held.x - held.startX, held.y - held.startY) < THRESHOLD) return;
        held.moved = true;
        capture(held.element, held.pointerId);
      }
      schedule();
    },
    /** The drop the release makes, if it makes one. */
    release(event: ReactPointerEvent<HTMLElement>): { card: ApplicationCard; stage: StageSlug } | null {
      if (!held || held.pointerId !== event.pointerId) return null;
      const target = held.moved && !held.dropped ? targetAt(event.clientX, event.clientY) : null;
      const was = end();
      if (!was?.moved) return null;
      swallowNextClick();
      return target && target !== was.card.stage ? { card: was.card, stage: target } : null;
    },
    /** The pointer is gone: the browser took it, or the card lost it. */
    cancel(pointerId: number) {
      if (held?.pointerId === pointerId) end();
    },
    /** Escape: the card goes back while the button is still down. The card
     *  keeps the pointer until the release, so the click that follows lands
     *  on the card, and is swallowed, rather than opening the application. */
    giveUp() {
      if (!held?.moved || held.dropped) return;
      held.dropped = true;
      if (frame !== null) cancelAnimationFrame(frame);
      frame = null;
      show(null);
    },
    unmount() {
      held = null;
      if (frame !== null) cancelAnimationFrame(frame);
      frame = null;
    },
    /** Whether this click is the tail of a drag; consumes the latch. */
    swallowClick(): boolean {
      const was = swallow;
      swallow = false;
      return was;
    },
  };
}

/** Drag the board's cards between its columns. `scroller` is the board's
 *  scrolling box: drop targets are read inside it, and a drag held at its
 *  edge scrolls it. */
export function useCardDrag(
  scroller: RefObject<HTMLElement | null>,
  onDrop: (card: ApplicationCard, stage: StageSlug) => void,
) {
  const [drag, setDrag] = useState<CardDragState | null>(null);
  const [machine] = useState(() => cardDragMachine(scroller, setDrag));
  // Escape drops nothing: the card goes back where it was.
  useEscapeLayer(drag != null, () => machine.giveUp());
  useEffect(() => () => machine.unmount(), [machine]);

  const handlers = (card: ApplicationCard): CardDragHandlers => ({
    onPointerDown: (event) => machine.press(card, event),
    onPointerMove: (event) => machine.move(event),
    onPointerUp: (event) => {
      const drop = machine.release(event);
      if (drop) onDrop(drop.card, drop.stage);
    },
    onPointerCancel: (event) => machine.cancel(event.pointerId),
    onLostPointerCapture: (event) => machine.cancel(event.pointerId),
    onClickCapture: (event) => {
      if (!machine.swallowClick()) return;
      event.preventDefault();
      event.stopPropagation();
    },
  });

  return { drag, handlers };
}

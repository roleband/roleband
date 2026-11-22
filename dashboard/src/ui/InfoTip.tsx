import "./InfoTip.css";
import { useId, useLayoutEffect, useRef, useState } from "react";
import { useEscapeLayer } from "./escapeLayer";
import { Icon } from "./Icon";
import { placeLeft, placeTop } from "./place";
import { uiInfoTipMoreInformation } from "../copy/gen/ui";

const GAP = 7;
const MARGIN = 8;
/** The stylesheet's width cap, repeated where a hung tip narrows it to its host. */
const MAX_WIDTH = "320px, calc(100vw / var(--page-zoom, 1) - 40px)";

/** Whether this engine can open a popover. One that only knows the attribute
 *  hides the element and can never show it, so the attribute is set only where
 *  the call that shows it exists; elsewhere the tip is a fixed element. */
const POPOVER = typeof HTMLElement !== "undefined" && "showPopover" in HTMLElement.prototype;

/** An ⓘ mark whose tip shows while the pointer is on it or it has focus.
 *
 *  The tip opens in the top layer (`popover="manual"`), above every dialog and
 *  outside every box that clips its content, and is placed in window
 *  coordinates. Placed inside the page instead, it is cut off by the first
 *  scrolling or clipping box around it: a dialog, a sheet, a card. It stays
 *  where it is in the DOM, so it is still described by the mark and found
 *  inside its own section.
 *
 *  By default the tip opens below the mark from its left edge. `align="end"`
 *  lines it up with the mark's right edge instead. `hangFrom` names an
 *  ancestor (a CSS selector) the tip hangs below: the tip opens under that box,
 *  lined up with its start or end edge, and no wider than it. A mark sitting in
 *  a table's header row hangs its tip from the row, so the tip covers no
 *  column name and stays as narrow as the table. */
export function InfoTip({
  children,
  label = uiInfoTipMoreInformation(),
  align = "start",
  hangFrom,
}: {
  children: React.ReactNode;
  label?: string;
  align?: "start" | "end";
  hangFrom?: string;
}) {
  const id = useId();
  const [hovered, setHovered] = useState(false);
  const [focused, setFocused] = useState(false);
  // Escape hides the tip and leaves focus on the mark; it shows again on the
  // next pointer entry or focus, not while the mark keeps the focus it had.
  const [dismissed, setDismissed] = useState(false);
  const open = (hovered || focused) && !dismissed;
  useEscapeLayer(open, () => setDismissed(true));
  const trigger = useRef<HTMLButtonElement | null>(null);
  const tip = useRef<HTMLSpanElement | null>(null);

  useLayoutEffect(() => {
    const panel = tip.current;
    const anchor = trigger.current;
    if (!open || !panel || !anchor) return;
    if (POPOVER && !panel.matches(":popover-open")) panel.showPopover();
    const place = () => {
      const host = hangFrom ? anchor.closest(hangFrom) : null;
      const from = (host ?? anchor).getBoundingClientRect();
      // Capped to the host's width before it is measured, so the measure is the
      // size it is placed at.
      if (host) panel.style.maxWidth = `min(${from.width}px, ${MAX_WIDTH})`;
      else panel.style.removeProperty("max-width");
      const options = { gap: GAP, margin: MARGIN, align };
      panel.style.top = `${placeTop(from, panel.offsetHeight, window.innerHeight, options)}px`;
      panel.style.left = `${placeLeft(from, panel.offsetWidth, window.innerWidth, options)}px`;
    };
    place();
    // A scroll anywhere (the dialog's own included) moves the mark under it.
    window.addEventListener("scroll", place, true);
    window.addEventListener("resize", place);
    return () => {
      window.removeEventListener("scroll", place, true);
      window.removeEventListener("resize", place);
      if (POPOVER && panel.matches(":popover-open")) panel.hidePopover();
    };
  }, [open, align, hangFrom]);

  return (
    <span
      className="info-tip"
      onPointerEnter={() => {
        setHovered(true);
        setDismissed(false);
      }}
      onPointerLeave={() => setHovered(false)}
      onFocus={() => {
        if (!focused) setDismissed(false);
        setFocused(true);
      }}
      onBlur={(e) => {
        if (!e.currentTarget.contains(e.relatedTarget as Node | null)) setFocused(false);
      }}
    >
      <button
        ref={trigger}
        type="button"
        className="info-tip-trigger"
        aria-label={label}
        aria-describedby={id}
      >
        <Icon name="info" size={13} />
      </button>
      <span
        ref={tip}
        className="info-tip-popover"
        id={id}
        role="tooltip"
        popover={POPOVER ? "manual" : undefined}
        data-open={open ? "" : undefined}
      >
        {children}
      </span>
    </span>
  );
}

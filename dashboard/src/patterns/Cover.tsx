import { CSSProperties, ReactNode, RefObject, useEffect, useLayoutEffect, useRef, useState } from "react";
import { useEscapeLayer } from "../ui/escapeLayer";
import { BEHIND_COVER, BESIDE_COVER, Overlay } from "../ui/Overlay";
import "./cover.css";

/* The Cover (docs/ui.md "Cover"): a full-viewport surface for
 * studying one thing, or a few, over the list it was opened from. Job detail
 * is its first occupant; Compare its second.
 *
 * Two shells, one body — because the two are different things to a keyboard
 * and a screen reader. Opened from a list it covers a page that stays MOUNTED
 * underneath (the list keeps its scroll and filters; Back pops history), so it
 * is a modal dialog: ui/Overlay owns role, aria-modal, focus capture/trap/
 * restore, Escape and the body scroll lock. Reached by URL or refresh it IS
 * the page — its one `main` landmark — and Escape is this component's to own,
 * as a `page` layer (ui/escapeLayer): one layer per cover whichever shell, or
 * onBack runs twice and steps back two entries; and anything opened over the
 * page (the palette) takes the press first.
 *
 * No scrim: the cover is opaque, so a dim layer under it would paint nothing
 * and a click-to-close target would sit over a page you cannot see.
 *
 * Opened BESIDE the rail (a role opened from a Pipeline view) it covers the
 * page but not the rail: the rail stays live and keeps the view marked, so
 * the cover is a page of that place rather than a dialog over it. It is not
 * modal then: the rest of the page behind it is inert, the rail keeps its
 * pointer and its place in the tab order, and Escape still goes back. Back
 * hands focus to the page's link to what the cover showed last (the card it
 * was opened from, or the one a link on the posting swapped in), which wears
 * `data-returned` for a moment so the eye finds where it was. Found by its
 * address, because a card pressed with a pointer never held focus.
 *
 * `data-design-system="app"` stays on the cover in BOTH shells: the rules in
 * design/surfaces.css and design/dataviz.css are gated on it, so a shell that
 * drops it silently unstyles the panels inside. */

/** How long the link back wears `data-returned` once the cover is gone. */
const RETURNED_MS = 2400;

/** Where the rail ends, so a cover beside it starts there. A rail laid along
 *  the bottom of a narrow window is not beside anything: the cover takes the
 *  whole width then. */
function railEdge(): number {
  let edge = 0;
  document.querySelectorAll<HTMLElement>(`[${BESIDE_COVER}]`).forEach((element) => {
    const box = element.getBoundingClientRect();
    if (box.height >= window.innerHeight / 2) edge = Math.max(edge, box.right);
  });
  return edge;
}

/** The page behind a cover that opens beside the rail: inert but for the
 *  rail, its scroll held, and the cover's left edge kept on the rail's as it
 *  widens or narrows. */
function useBesideRail(on: boolean): CSSProperties | undefined {
  const [left, setLeft] = useState(0);
  // The address the cover shows, kept current as a link on the posting swaps another in.
  const shown = useRef(window.location.pathname);
  useEffect(() => {
    shown.current = window.location.pathname;
  });

  useLayoutEffect(() => {
    if (!on) return;
    const measure = () => setLeft(railEdge());
    measure();
    const observer = typeof ResizeObserver === "undefined" ? null : new ResizeObserver(measure);
    document.querySelectorAll(`[${BESIDE_COVER}]`).forEach((element) => observer?.observe(element));
    window.addEventListener("resize", measure);
    return () => {
      observer?.disconnect();
      window.removeEventListener("resize", measure);
    };
  }, [on]);

  // After the Overlay has moved focus in, so nothing focused goes inert; and
  // released before the Overlay hands focus back, which an inert page refuses.
  useEffect(() => {
    if (!on) return;
    const behind = Array.from(document.querySelectorAll<HTMLElement>(`[${BEHIND_COVER}]:not([${BESIDE_COVER}])`));
    behind.forEach((element) => element.setAttribute("inert", ""));
    const overflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      behind.forEach((element) => element.removeAttribute("inert"));
      document.body.style.overflow = overflow;
      const path = shown.current;
      // After the Overlay has handed focus back to whatever held it at open.
      window.setTimeout(() => {
        const link = Array.from(document.querySelectorAll<HTMLAnchorElement>("a[href]")).find(
          (anchor) => anchor.pathname === path && !anchor.closest(`[${BESIDE_COVER}]`),
        );
        if (!link) return;
        link.focus();
        link.setAttribute("data-returned", "");
        window.setTimeout(() => link.removeAttribute("data-returned"), RETURNED_MS);
      }, 0);
    };
  }, [on]);

  return on ? ({ "--cover-left": `${left}px` } as CSSProperties) : undefined;
}
export function Cover({
  label,
  asOverlay,
  onBack,
  bar,
  className,
  scrollRef,
  besideRail = false,
  children,
}: {
  /** Accessible name — the thing being studied ("Role: …", "Comparison"). */
  label: string;
  /** True when this covers a page still mounted underneath. */
  asOverlay: boolean;
  onBack: () => void;
  /** The Bar's contents: Back · frame line · spacer · verbs · one primary. */
  bar: ReactNode;
  /** The occupant's own root class, for its scoped rules. */
  className?: string;
  /** The cover's own scroll box. An occupant scrolls through this, never a
      document-wide lookup: as an overlay, the page underneath has a cover of
      its own (a comparison, a role reached by URL) and comes first in the
      document. */
  scrollRef?: RefObject<HTMLDivElement | null>;
  /** Opened from a Pipeline view: beside the rail, not over it. Applies only
      as an overlay; reached by URL the cover is the whole page. */
  besideRail?: boolean;
  children: ReactNode;
}) {
  useEscapeLayer(!asOverlay, onBack, "page");
  const beside = asOverlay && besideRail;
  const besideStyle = useBesideRail(beside);

  // By URL the cover IS the page, so it is the page's one `main` landmark; as
  // an overlay the dialog is the landmark and this is its content.
  const Root = asOverlay ? "section" : "main";
  const cover = (
    <Root
      className={`cover${className ? ` ${className}` : ""}`}
      data-design-system="app"
      aria-label={asOverlay ? undefined : label}
      // As the page there is no dialog to hold the keyboard, so the cover
      // itself takes it when what had focus leaves with a turn. As an overlay
      // the dialog owns that (ui/Overlay).
      tabIndex={asOverlay ? undefined : -1}
    >
      <div className="cover-bar">{bar}</div>
      <div className="cover-scroll" ref={scrollRef}>{children}</div>
    </Root>
  );

  if (!asOverlay) return cover;
  return (
    <Overlay
      isOpen
      onClose={onBack}
      label={label}
      modal={!beside}
      layer="cover"
      scrim={false}
      closeOnScrim={false}
      className={beside ? "ui-overlay-full cover-beside" : "ui-overlay-full"}
      style={besideStyle}
    >
      {cover}
    </Overlay>
  );
}

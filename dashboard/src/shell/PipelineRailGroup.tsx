import { useEffect, useId, useRef, useState, type FocusEvent, type PointerEvent } from "react";
import { NavLink, useLocation } from "react-router-dom";
import type { NavTabDef } from "../navigation";
import { Icon, type IconName } from "../ui/Icon";

/** Each view's mark: not started yet, columns of cards, what is due by day. */
const VIEW_ICON: Record<string, IconName> = { list: "circleDashed", board: "board", "up-next": "calendarClock" };

/** How long the pointer rests on the star before its views open, and how long
 *  it may be away before they close: a pointer crossing the rail opens
 *  nothing, and one moving from the star down into the views loses nothing. */
const OPEN_AFTER_MS = 120;
const CLOSE_AFTER_MS = 240;

/* The Pipeline in the rail: its star, and under it the pipeline's views.
 *
 * The views stay folded away until the pointer rests on the star or the star
 * is pressed; then they drop out of it into a well that pushes the rest of
 * the rail down. Collapsed, the well is a narrower tile under the star;
 * expanded, the views are named on a line set in from it. A press keeps them
 * open until a view is picked, the star is pressed again, Escape, or a press
 * elsewhere. The star carries the mark of the place on screen, so a closed
 * well still says the Pipeline is open. */
export function PipelineRailGroup({ tab, expanded }: { tab: NavTabDef; expanded: boolean }) {
  const { pathname } = useLocation();
  const within = pathname === tab.path || pathname.startsWith(`${tab.path}/`);
  const wellId = useId();
  const family = useRef<HTMLDivElement>(null);
  const star = useRef<HTMLButtonElement>(null);

  const [shown, setShown] = useState(false);
  const [pinned, setPinned] = useState(false);
  const timer = useRef<number | undefined>(undefined);

  const close = () => {
    window.clearTimeout(timer.current);
    setShown(false);
    setPinned(false);
  };
  const after = (ms: number, then: () => void) => {
    window.clearTimeout(timer.current);
    timer.current = window.setTimeout(then, ms);
  };
  useEffect(() => () => window.clearTimeout(timer.current), []);

  // Picking a view, going anywhere else, or resizing the rail folds the well away.
  useEffect(() => {
    window.clearTimeout(timer.current);
    setShown(false);
    setPinned(false);
  }, [pathname, expanded]);

  // A press elsewhere closes a well the star's press opened.
  useEffect(() => {
    if (!pinned) return;
    const away = (event: globalThis.PointerEvent) => {
      if (!family.current?.contains(event.target as Node)) close();
    };
    document.addEventListener("pointerdown", away);
    return () => document.removeEventListener("pointerdown", away);
  }, [pinned]);

  // Escape folds the views while focus is among them, and hands the star its
  // focus back. Focus elsewhere keeps Escape for whatever holds it.
  useEffect(() => {
    if (!shown) return;
    const onEscape = (event: globalThis.KeyboardEvent) => {
      if (event.key !== "Escape" || !family.current?.contains(document.activeElement)) return;
      close();
      star.current?.focus();
    };
    document.addEventListener("keydown", onEscape);
    return () => document.removeEventListener("keydown", onEscape);
  }, [shown]);

  const onPointerEnter = (event: PointerEvent) => {
    if (event.pointerType === "mouse") after(OPEN_AFTER_MS, () => setShown(true));
  };
  const onPointerLeave = (event: PointerEvent) => {
    if (event.pointerType !== "mouse") return;
    if (pinned) window.clearTimeout(timer.current);
    else after(CLOSE_AFTER_MS, () => setShown(false));
  };
  const onStar = () => {
    window.clearTimeout(timer.current);
    if (shown && pinned) close();
    else {
      setShown(true);
      setPinned(true);
    }
  };
  const onBlur = (event: FocusEvent) => {
    if (pinned && !family.current?.contains(event.relatedTarget as Node | null)) close();
  };

  const views = tab.tabs ?? [];
  return (
    <div
      ref={family}
      className={`rail-family${shown ? " open" : ""}${within ? " is-within" : ""}`}
      onPointerEnter={onPointerEnter}
      onPointerLeave={onPointerLeave}
      onBlur={onBlur}
    >
      <button
        ref={star}
        type="button"
        className="rail-item rail-family-star"
        aria-expanded={shown}
        aria-controls={wellId}
        aria-label={tab.label}
        data-tip={tab.label}
        title={tab.label}
        onClick={onStar}
      >
        <Icon name={tab.icon} size={18} />
        {expanded && <span className="rail-label">{tab.label}</span>}
      </button>
      <div className="rail-well" id={wellId}>
        {views.map((view) => (
          <NavLink
            key={view.slug}
            to={`${tab.path}/${view.slug}`}
            className="rail-item rail-sub"
            aria-label={view.label}
            data-tip={view.label}
            title={view.label}
          >
            <Icon name={VIEW_ICON[view.slug] ?? "circleDashed"} size={16} />
            <span className="rail-label">{view.label}</span>
          </NavLink>
        ))}
      </div>
    </div>
  );
}

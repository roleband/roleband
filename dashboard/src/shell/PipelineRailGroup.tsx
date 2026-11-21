import { useEffect, useRef, useState, type PointerEvent } from "react";
import { Link, NavLink, useLocation } from "react-router-dom";
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
 * The star is the Pipeline's entry: a press opens it at its first view,
 * Considering. In the Pipeline the star is marked as the place, and the views
 * stay on show under it with the one on screen marked too, so the rail says
 * where the person is at both levels. Its `aria-current` is "true", not
 * "page": the page is the view. Anywhere else they
 * are folded away, and a pointer resting on the star drops them in under it,
 * pushing the rest of the rail down, so a view can be opened directly; they
 * fold again once the pointer leaves. Collapsed, the views sit in a narrower
 * tile under the star; expanded, they are named on a line set in from it.
 *
 * The rail must not move under a press: a fold landing between a button
 * going down and coming up shifts the entries, and the click lands on the one
 * that slid under the pointer. So a fold timed for the pointer leaving waits
 * for a press in progress to end. */
export function PipelineRailGroup({ tab, expanded }: { tab: NavTabDef; expanded: boolean }) {
  const { pathname } = useLocation();
  const within = pathname === tab.path || pathname.startsWith(`${tab.path}/`);
  const views = tab.tabs ?? [];

  // Outside the Pipeline, whether a resting pointer has the views open.
  const [shown, setShown] = useState(false);
  const open = within || shown;
  const timer = useRef<number | undefined>(undefined);
  const pressing = useRef(false);

  const after = (ms: number, then: () => void) => {
    window.clearTimeout(timer.current);
    timer.current = window.setTimeout(then, ms);
  };
  const foldWhenStill = () => {
    if (pressing.current) after(CLOSE_AFTER_MS, foldWhenStill);
    else setShown(false);
  };
  useEffect(() => () => window.clearTimeout(timer.current), []);

  // Going anywhere, or resizing the rail, starts afresh.
  useEffect(() => {
    window.clearTimeout(timer.current);
    setShown(false);
  }, [pathname, expanded]);

  // Whether a button is down anywhere, read when a timed fold comes due. Up is
  // marked after the click it ends has gone where it was aimed.
  useEffect(() => {
    const down = () => {
      pressing.current = true;
    };
    const up = () => window.setTimeout(() => (pressing.current = false), 0);
    document.addEventListener("pointerdown", down, true);
    document.addEventListener("pointerup", up, true);
    document.addEventListener("pointercancel", up, true);
    return () => {
      document.removeEventListener("pointerdown", down, true);
      document.removeEventListener("pointerup", up, true);
      document.removeEventListener("pointercancel", up, true);
    };
  }, []);

  const onPointerEnter = (event: PointerEvent) => {
    if (event.pointerType === "mouse" && !within) after(OPEN_AFTER_MS, () => setShown(true));
  };
  const onPointerLeave = (event: PointerEvent) => {
    if (event.pointerType === "mouse" && !within) after(CLOSE_AFTER_MS, foldWhenStill);
  };

  return (
    <div
      className={`rail-family${open ? " open" : ""}${within ? " is-within" : ""}`}
      onPointerEnter={onPointerEnter}
      onPointerLeave={onPointerLeave}
    >
      <Link
        to={`${tab.path}/${views[0]?.slug ?? ""}`}
        className="rail-item rail-family-star"
        aria-current={within ? "true" : undefined}
        aria-label={tab.label}
        data-tip={tab.label}
        title={tab.label}
      >
        <Icon name={tab.icon} size={18} />
        {expanded && <span className="rail-label">{tab.label}</span>}
      </Link>
      <div className="rail-well">
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

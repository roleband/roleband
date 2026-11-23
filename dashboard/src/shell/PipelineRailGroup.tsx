import { Link, NavLink, useLocation, useNavigate } from "react-router-dom";
import type { NavTabDef } from "../navigation";
import { useMediaQuery } from "../hooks/useMediaQuery";
import { pipelineViewUnder } from "../routing/paths";
import { Icon, type IconName } from "../ui/Icon";

/** Each view's mark: not started yet, columns of cards, what is due by day. */
const VIEW_ICON: Record<string, IconName> = { list: "circleDashed", board: "board", "up-next": "calendarClock" };

/** The width at which the rail becomes the dock (shell.css): the dock has no
 *  star, and lists the views as entries of their own. */
const DOCK_QUERY = "(max-width: 860px)";

/* The Pipeline in the rail: its star, and in the expanded rail its views.
 *
 * The star is the Pipeline's entry: a press opens it at its first view,
 * Considering. In the Pipeline the star is marked as the place; its
 * `aria-current` is "true", not "page", since the page is the view.
 *
 * Collapsed, the star stands alone: the page's own tabs switch between the
 * views. Expanded, the views are named under it on a line set in from it, with
 * the one on screen marked too, so the rail says where the person is at both
 * levels. They drop in one after another as the rail widens (shell.css).
 *
 * A role opened from a view is a page of the Pipeline (patterns/Cover beside
 * the rail): the star stays marked and the view under the role stays marked
 * too, and pressing that view goes back to its address as it was left, filter
 * included, rather than opening afresh or stepping to the previous posting. */
export function PipelineRailGroup({ tab, expanded }: { tab: NavTabDef; expanded: boolean }) {
  const location = useLocation();
  const { pathname } = location;
  const navigate = useNavigate();
  const background = (location.state as { backgroundLocation?: { search?: unknown } } | null)?.backgroundLocation;
  // The view as it was left: its address, search included, whichever postings
  // the person has stepped through since.
  const viewSearch = typeof background?.search === "string" ? background.search : "";
  const docked = useMediaQuery(DOCK_QUERY);
  const under = pipelineViewUnder(location);
  const within = under != null || pathname === tab.path || pathname.startsWith(`${tab.path}/`);
  const views = tab.tabs ?? [];

  return (
    <div className="rail-family">
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
      {(expanded || docked) && (
        <div className="rail-well">
          {views.map((view) => {
            const to = `${tab.path}/${view.slug}`;
            const entry = {
              to, className: "rail-item rail-sub", "aria-label": view.label, title: view.label,
              children: <><Icon name={VIEW_ICON[view.slug] ?? "circleDashed"} size={16} /><span className="rail-label">{view.label}</span></>,
            };
            // The view under an open role: marked as the place, not the page,
            // and a press goes back to it.
            return under === to
              ? <Link key={view.slug} {...entry} aria-current="true" onClick={(event) => { event.preventDefault(); navigate({ pathname: to, search: viewSearch }); }} />
              : <NavLink key={view.slug} {...entry} />;
          })}
        </div>
      )}
    </div>
  );
}

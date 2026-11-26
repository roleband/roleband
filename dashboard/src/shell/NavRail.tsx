import {
  shellBrand,
  shellBellUnread,
  shellBrandLine,
  shellRailAria,
  shellRailCollapse,
  shellRailCollapseAria,
  shellRailExpand,
  shellRailExpandAria,
  shellRailItemCount,
  shellRailPending,
  shellRailPicksUnseen,
  shellThemeAria,
  shellThemeDark,
  shellThemeLight,
  shellThemeTitle,
} from "../copy/gen/shell";
import { Link, NavLink, useLocation } from "react-router-dom";
import { NAV_TABS } from "../navigation";
import { pipelineViewUnder } from "../routing/paths";
import { countBadge } from "../format";
import { useMissionStats } from "../context/MissionState";
import { Icon } from "../ui/Icon";
import { BrandMark } from "../ui/BrandMark";
import { BEHIND_COVER, BESIDE_COVER } from "../ui/Overlay";
import { CountBadge } from "../ui/CountBadge";
import { PipelineRailGroup } from "./PipelineRailGroup";
import { usePicksDot } from "../hooks/picksDot";

interface Props {
  expanded: boolean;
  onToggleExpanded: () => void;
  theme: string;
  onToggleTheme: () => void;
}

export function NavRail({ expanded, onToggleExpanded, theme, onToggleTheme }: Props) {
  const stats = useMissionStats();
  const unseenPick = usePicksDot();
  const primary = NAV_TABS.filter((t) => t.path !== "/settings");
  const settings = NAV_TABS.find((t) => t.path === "/settings");
  // A role open beside the rail belongs to the Pipeline view under it, though
  // its address sits under its company: no other entry is the place then.
  const besideRole = pipelineViewUnder(useLocation()) != null;

  /* Each count carries the noun that says what it counts, because the number
     leaves the badge: it is spoken and shown as "Review, 342 pending". */
  const badge = (path: string) => {
    if (path === "/notifications" && (stats?.notif_unread ?? 0) > 0)
      return countBadge(stats!.notif_unread, shellBellUnread);
    if (path === "/review" && (stats?.review_pending ?? 0) > 0)
      return countBadge(stats!.review_pending, shellRailPending);
    // A dot, never a number: a pick arrived since Top picks was last opened.
    if (path === "/top-picks" && unseenPick) return { text: null, dot: true, label: shellRailPicksUnseen() };
    return null;
  };

  return (
    <nav className={`nav-rail ${expanded ? "expanded" : "collapsed"}`} data-design-system="app" data-selection="chrome" aria-label={shellRailAria()} {...{ [BEHIND_COVER]: "", [BESIDE_COVER]: "" }}>
      <div className="rail-top">
        <div className="rail-brand">
          <span className="brand-mark"><BrandMark /></span>
          <span className="brand-copy">
            <strong>{shellBrand()}</strong>
            <small>{shellBrandLine()}</small>
          </span>
        </div>
        <button
          className="rail-toggle"
          onClick={onToggleExpanded}
          aria-expanded={expanded}
          aria-label={expanded ? shellRailCollapseAria() : shellRailExpandAria()}
          title={expanded ? shellRailCollapseAria() : shellRailExpandAria()}
          data-tip={expanded ? shellRailCollapseAria() : shellRailExpandAria()}
        >
          <Icon name={expanded ? "panelCollapse" : "panelExpand"} size={17} />
          <span className="rail-toggle-label">{expanded ? shellRailCollapse() : shellRailExpand()}</span>
        </button>
        <div className="rail-group">
          {primary.map((t) => {
            if (t.path === "/pipeline") return <PipelineRailGroup key={t.path} tab={t} expanded={expanded} />;
            const count = badge(t.path);
            /* One string for all three: the hover tooltip when the rail is
               collapsed (`data-tip`), the native one when it is expanded
               (`title`), and the accessible name. The dot has no digits, so
               this is where its count is. */
            const name = count ? shellRailItemCount({ label: t.label, badge: count.label }) : t.label;
            const badgeClass = count?.dot ? "rail-badge rail-badge-dot" : "rail-badge";
            const entry = {
              to: t.path, className: "rail-item", "aria-label": name, "data-tip": name, title: name,
              children: (
                <>
                  <Icon name={t.icon} size={18} />
                  <span className="rail-label">{t.label}</span>
                  {count && <CountBadge className={badgeClass}>{count.text}</CountBadge>}
                </>
              ),
            };
            return besideRole ? <Link key={t.path} {...entry} /> : <NavLink key={t.path} {...entry} end={t.end} />;
          })}
        </div>
      </div>
      <div className="rail-group rail-bottom">
        {settings && (
          <NavLink
            to={settings.path}
            className="rail-item"
            aria-label={settings.label}
            data-tip={settings.label}
            title={settings.label}
          >
            <Icon name={settings.icon} size={18} />
            <span className="rail-label">{settings.label}</span>
          </NavLink>
        )}
        <button className="rail-item" onClick={onToggleTheme} aria-label={shellThemeAria()} data-tip={shellThemeTitle()} title={shellThemeTitle()}>
          <Icon name={theme === "dark" ? "sun" : "moon"} size={18} />
          <span className="rail-label">{theme === "dark" ? shellThemeLight() : shellThemeDark()}</span>
        </button>
      </div>
    </nav>
  );
}

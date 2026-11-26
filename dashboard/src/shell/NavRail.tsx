import {
  shellBrand,
  shellBrandLine,
  shellRailAria,
  shellRailCollapse,
  shellRailCollapseAria,
  shellRailExpand,
  shellRailExpandAria,
  shellRailItemCount,
  shellRailPicksUnseen,
  shellThemeAria,
  shellThemeDark,
  shellThemeLight,
  shellThemeTitle,
} from "../copy/gen/shell";
import { Link, NavLink, useLocation } from "react-router-dom";
import { NAV_TABS, type NavTabDef } from "../navigation";
import { pipelineViewUnder } from "../routing/paths";
import { useListed } from "../hooks/sideBar";
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
  /** Pressed on the Radar entry: the open board, whatever lens the Radar wears.
   *  A lens lives in memory, not the address, so a link to `/` alone keeps it. */
  onRadar?: () => void;
}

export function NavRail({ expanded, onToggleExpanded, theme, onToggleTheme, onRadar }: Props) {
  const unseenPick = usePicksDot();
  const isListed = useListed();
  const shown = NAV_TABS.filter((t) => t.rail !== null && isListed(t.optional));
  const top = shown.filter((t) => t.rail === "top");
  const foot = shown.filter((t) => t.rail === "foot");
  // A role open beside the rail belongs to the Pipeline view under it, though
  // its address sits under its company: no other entry is the place then.
  const besideRole = pipelineViewUnder(useLocation()) != null;

  /* The only mark on the rail: a dot, never a number, when a pick arrived
     since Top picks was last opened. A count lit most days says nothing, so
     no other place carries one. The dot has no digits, so what it means goes
     into the item's name. */
  const dot = (path: string) => path === "/top-picks" && unseenPick;

  const item = (t: NavTabDef) => {
    if (t.path === "/pipeline") return <PipelineRailGroup key={t.path} tab={t} expanded={expanded} />;
    const marked = dot(t.path);
    /* One string for all three: the hover tooltip when the rail is
       collapsed (`data-tip`), the native one when it is expanded
       (`title`), and the accessible name. */
    const name = marked ? shellRailItemCount({ label: t.label, badge: shellRailPicksUnseen() }) : t.label;
    const entry = {
      to: t.path, className: "rail-item", "aria-label": name, "data-tip": name, title: name,
      onClick: t.path === "/" ? onRadar : undefined,
      children: (
        <>
          <Icon name={t.icon} size={18} />
          <span className="rail-label">{t.label}</span>
          {marked && <CountBadge className="rail-badge rail-badge-dot" />}
        </>
      ),
    };
    return besideRole ? <Link key={t.path} {...entry} /> : <NavLink key={t.path} {...entry} end={t.end} />;
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
        <div className="rail-group">{top.map(item)}</div>
      </div>
      <div className="rail-group rail-bottom">
        {foot.map(item)}
        <button className="rail-item" onClick={onToggleTheme} aria-label={shellThemeAria()} data-tip={shellThemeTitle()} title={shellThemeTitle()}>
          <Icon name={theme === "dark" ? "sun" : "moon"} size={18} />
          <span className="rail-label">{theme === "dark" ? shellThemeLight() : shellThemeDark()}</span>
        </button>
      </div>
    </nav>
  );
}

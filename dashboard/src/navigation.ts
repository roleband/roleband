import {
  shellNavRadar,
  shellNavTopPicks,
  shellNavPipeline,
  shellNavProfile,
  shellNavInsights,
  shellNavCompanies,
  shellNavDuplicates,
  shellNavNotifications,
  shellNavSettings,
} from "./copy/gen/shell";
import type { IconName } from "./ui/Icon";
// Sub-tab constants live in a leaf module (navTabs) so section components can
// import them without forming a cycle.
import { PIPELINE_TABS, PROFILE_TABS, SETTINGS_TABS, STATISTICS_TABS, SubTabDef } from "./navTabs";

export type { SubTabDef };

/**
 * Navigation METADATA — paths, labels, icons, sub-tabs. No components, no JSX,
 * no feature imports.
 *
 * This module and `routeRegistry.tsx` are two files because one file would
 * make a visit to any route evaluate every screen in the product: the rail,
 * the breadcrumb and the command palette all need the labels, so importing
 * the labels would import the elements, and importing the elements every
 * feature and its CSS. Nothing here reaches a screen, so the three chrome
 * consumers cost nothing but this table.
 */
export interface NavTabDef {
  path: string;
  label: string;
  icon: IconName;
  /** Exact-match the path (the Board owns "/", which prefixes everything). */
  end?: boolean;
  /** Multi-view sections declare their path sub-tabs here so the router, the
   *  section shell, the breadcrumb and the palette derive from one list. */
  tabs?: SubTabDef[];
  /** Default sub-tab a section index (`/statistics`) redirects to. */
  indexRedirect?: string;
  /** Entity sections mount `${path}/:<entityParam>?`, one route with an
   *  optional segment (e.g. company -> `/company/:slug?`), preserving deep links
   *  without remounting the screen when a pick adds the segment. */
  entityParam?: string;
  /** Where the side bar lists the place: with the work at the top, at the
   *  foot with what is about the person and the app, or nowhere, when a
   *  control in view all the time already opens it. */
  rail: "top" | "foot" | null;
  /** A place the person may take off the side bar (Settings › Preferences):
   *  the view choice that holds their answer, and whether the place is listed
   *  before they answer. A place off the side bar still opens from the
   *  palette and from every link to it. */
  optional?: SideBarChoice;
}

/** An optional place's view choice, and whether it is listed by default. */
export interface SideBarChoice {
  choice: string;
  shown: boolean;
}

// Single source of truth for navigation. The header, the rail, the palette and
// the router all derive from this list, so adding a tab is a line here plus a
// loader in routeRegistry.tsx.
//
// The table's order is the palette's; the side bar keeps it within each of
// its two groups.
//
// A rail entry is a PLACE with standing content — a list, a queue with a
// backlog, settings. A view of something chosen elsewhere (one role, a
// selection) is a cover opened from where the choosing happens, and is not
// listed: a Compare entry would advertise an empty room (docs/ui.md "Cover").
export const NAV_TABS: NavTabDef[] = [
  { path: "/", get label() { return shellNavRadar(); }, icon: "grid", end: true, rail: "top" },
  { path: "/top-picks", get label() { return shellNavTopPicks(); }, icon: "crosshair", rail: "top" },
  { path: "/pipeline", get label() { return shellNavPipeline(); }, icon: "star", tabs: PIPELINE_TABS, indexRedirect: "list", rail: "top" },
  { path: "/profile", get label() { return shellNavProfile(); }, icon: "person", tabs: PROFILE_TABS, indexRedirect: "direction", rail: "foot" },
  {
    path: "/statistics",
    get label() { return shellNavInsights(); },
    icon: "chart",
    tabs: STATISTICS_TABS,
    indexRedirect: "overview",
    rail: "top",
    optional: { choice: "sidebar.insights", shown: true },
  },
  {
    path: "/company",
    get label() { return shellNavCompanies(); },
    icon: "building",
    entityParam: "slug",
    rail: "top",
    optional: { choice: "sidebar.companies", shown: true },
  },
  // A queue that always has a backlog: listed only for the person who works it.
  {
    path: "/review",
    get label() { return shellNavDuplicates(); },
    icon: "files",
    rail: "top",
    optional: { choice: "sidebar.duplicates", shown: false },
  },
  // The top bar's bell holds the same list and count, and opens this page.
  { path: "/notifications", get label() { return shellNavNotifications(); }, icon: "bell", rail: null },
  {
    path: "/settings",
    get label() { return shellNavSettings(); },
    icon: "gear",
    tabs: SETTINGS_TABS,
    indexRedirect: "companies",
    rail: "foot",
  },
];

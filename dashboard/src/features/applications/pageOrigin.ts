import { useLocation, type Location } from "react-router-dom";
import { shellTabPipelineBoard, shellTabPipelineList, shellTabPipelineUpNext } from "../../copy/gen/shell";

/* A role's page goes back to the view it was opened from, as it was: the same
 * tab, its filter and the tabs' own history state. A link into the page
 * carries that place in its history state; the page's own arrows pass it on,
 * so paging through a column keeps the way back. A page opened from anywhere
 * else (an address, a notification) goes back to the board. */

const KEY = "pipelineOrigin";

const VIEWS = {
  "/pipeline/list": shellTabPipelineList,
  "/pipeline/board": shellTabPipelineBoard,
  "/pipeline/up-next": shellTabPipelineUpNext,
} as const;
type ViewPath = keyof typeof VIEWS;

export interface PageOrigin {
  pathname: ViewPath;
  search: string;
  state: unknown;
}

const isView = (path: unknown): path is ViewPath => typeof path === "string" && Object.prototype.hasOwnProperty.call(VIEWS, path);

/** The history state a link into a role's page carries from this view. */
export function originState(location: Pick<Location, "pathname" | "search" | "state">): Record<string, PageOrigin> | undefined {
  if (!isView(location.pathname)) return undefined;
  return { [KEY]: { pathname: location.pathname, search: location.search, state: location.state } };
}

/** The state for links into a role's page from the view on screen. */
export function useOriginState() {
  return originState(useLocation());
}

/** Where the page's Back goes and what it is called. */
export function backOf(state: unknown): { pathname: string; search: string; state: unknown; view: string } {
  const origin = state && typeof state === "object" ? (state as Record<string, unknown>)[KEY] : undefined;
  if (origin && typeof origin === "object") {
    const { pathname, search, state: inner } = origin as Record<string, unknown>;
    if (isView(pathname)) {
      return { pathname, search: typeof search === "string" ? search : "", state: inner, view: VIEWS[pathname]() };
    }
  }
  return { pathname: "/pipeline/board", search: "", state: undefined, view: VIEWS["/pipeline/board"]() };
}

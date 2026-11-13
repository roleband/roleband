// Canonical URL for an individual position (job). A position is a sub-resource
// of its company, so it nests under the company path — every position is tied to
// its company through the link (`/company/google/job/123`). Singular segments:
// each names one entity (the company, the job).
export const POSITION_ROUTE = "/company/:slug/job/:id";

export function positionPath(companySlug: string, id: number | string): string {
  return `/company/${encodeURIComponent(companySlug)}/job/${id}`;
}

/** One key per position, whichever URL names it, or null for any other path.
 *  A short /job/:id, or a position under the wrong company, rewrites itself
 *  to `positionPath` once the job loads; a key that changed with that rewrite
 *  would remount the detail and fetch all of it again. */
export function positionKey(pathname: string): string | null {
  const id = /^(?:\/company\/[^/]+)?\/job\/([^/]+)\/?$/.exec(pathname)?.[1];
  return id ? `position:${id}` : null;
}

/** The page a cover opens OVER. A cover never stacks on a role: opened from a
 *  role cover it reuses that cover's background, so Back lands on the list,
 *  and a role that is the page itself is replaced as the page (`openJob`).
 *  A comparison is the one exception a role may stack on (`openJob`), because
 *  a reader who opens a column expects Back to return to the comparison. */
export function coverBackground(location: { pathname: string; state: unknown }): unknown {
  const behind = (location.state as { backgroundLocation?: unknown } | null)?.backgroundLocation;
  return behind ?? location;
}

export const COMPARE_ROUTE = "/compare";

type Place = { pathname: string; search?: string; state: unknown };

/** The page at the bottom of a stack of covers: a cover opens over a page, and
 *  a role opened from Compare over Compare, which opens over the list. */
export function pageUnder(location: Place): Place {
  let page = location;
  for (let depth = 0; depth < 4; depth += 1) {
    const behind = (page.state as { backgroundLocation?: Place } | null)?.backgroundLocation;
    if (!behind) break;
    page = behind;
  }
  return page;
}

/** The list screen a page belongs to, for the state each screen keeps of its
 *  own (the compare selection, the search the palette runs). A cover belongs
 *  to the page under it (`pageUnder`). The Pipeline is its tabs and every
 *  application's page under `/pipeline`; every other page is Radar's,
 *  including Compare reached by its address alone. */
export function listScreenOf(location: Place): "radar" | "pipeline" {
  const { pathname } = pageUnder(location);
  return pathname === "/pipeline" || pathname.startsWith("/pipeline/") ? "pipeline" : "radar";
}

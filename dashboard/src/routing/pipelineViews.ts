/* The pipeline's views are rail entries of their own (shell/NavRail), so a
 * view is reached through the rail at a bare address. Its filters come back
 * on that arrival through `useRememberedParams`, under the view's own scope,
 * kept by this browser like the theme. */

/** The address keys a view owns: the search, the quick filters and how they
 *  show, and the List's sort. A module constant, as `useRememberedParams`
 *  asks. */
export const PIPELINE_VIEW_PARAMS: readonly string[] = ["q", "only", "show", "sort", "order"];

/** The filter-memory scope of one view. */
export const pipelineViewScope = (slug: string): string => `pipeline-${slug}`;

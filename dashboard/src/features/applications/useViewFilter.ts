import { useCallback } from "react";
import { useLocation, useSearchParams } from "react-router-dom";
import { VIEW_FILTERS, readFilter, writeFilter, type BoardFilter, type PipelineView } from "./filters";

/** One view's filter, kept in that view's own address. The query belongs to
 *  the path it is on, so a view reads only its own filter and two views never
 *  share one. Typing is not a destination, so a change replaces the entry,
 *  and keeps what the entry holds besides (the page's note of other views).
 *  It holds only the quick filters the view offers: one it does not, in an
 *  address typed or kept from elsewhere, is ignored and dropped on the next
 *  change. */
export function useViewFilter(view: PipelineView): [BoardFilter, (next: Partial<BoardFilter>) => void] {
  const offered = VIEW_FILTERS[view];
  const [params, setParams] = useSearchParams();
  const { state } = useLocation();
  const set = useCallback(
    (next: Partial<BoardFilter>) =>
      setParams((current) => writeFilter(current, { ...readFilter(current, offered), ...next }), { replace: true, state }),
    [setParams, state, offered],
  );
  return [readFilter(params, offered), set];
}

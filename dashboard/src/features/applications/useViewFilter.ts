import { useCallback } from "react";
import { useLocation, useSearchParams } from "react-router-dom";
import { readFilter, writeFilter, type BoardFilter } from "./filters";

/** One view's filter, kept in that view's own address. The query belongs to
 *  the path it is on, so a view reads only its own filter and two views never
 *  share one. Typing is not a destination, so a change replaces the entry,
 *  and keeps what the entry holds besides (the page's note of other views). */
export function useViewFilter(): [BoardFilter, (next: Partial<BoardFilter>) => void] {
  const [params, setParams] = useSearchParams();
  const { state } = useLocation();
  const set = useCallback(
    (next: Partial<BoardFilter>) =>
      setParams((current) => writeFilter(current, { ...readFilter(current), ...next }), { replace: true, state }),
    [setParams, state],
  );
  return [readFilter(params), set];
}

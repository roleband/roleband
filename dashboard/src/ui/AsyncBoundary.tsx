import { commonTryAgain } from "../copy/gen/common";
import { sharedEmpty, sharedRefreshFailed } from "../copy/gen/shared";
import { Component, Fragment, createRef, type ReactNode, type RefObject } from "react";
import type { AsyncResource } from "../hooks/useAsyncResource";
import { Button } from "./Button";
import { EmptyState } from "./EmptyState";
import { ResourceLoadState } from "./ResourceLoadState";

// AsyncBoundary (F1 primitive): canonical loading/error/empty/ready shell over
// a useAsyncResource result. Reuses ResourceLoadState for the default loading
// and error renders (no fork); slots override presentation, never the state
// machine. Hand-rolled loading states are ratchet-tracked.

export interface AsyncBoundaryProps<T> {
  /** Result of useAsyncResource (mutate not required).
   *
   *  `refreshError` and `refresh` are optional so a hand-built resource still
   *  type-checks, but passing the whole hook result is the point: it is the
   *  only thing that renders a failed background refresh, and `refresh` is
   *  what lets its Try again keep the rows on screen. */
  resource: Pick<AsyncResource<T>, "data" | "error" | "loading" | "retry"> & {
    refreshError?: Error | null;
    refresh?: AsyncResource<T>["refresh"];
  };
  /** "Loading your saved roles…": the whole loading line, from the catalog,
   *  as are the messages below: a sentence assembled from a noun cannot be
   *  translated. Unused when `skeleton` is given. */
  loading?: string;
  /** "Couldn't load your saved roles": the whole failure heading. */
  failed?: string;
  /** "No scan schedule yet": the default empty state's title. Unused when
   *  `empty` is given. */
  emptyTitle?: string;
  /** "Couldn't refresh plugins. Showing the last result.": said above the
   *  data a failed background refresh left on screen. */
  refreshFailed?: string;
  /** A newer result the reader can choose to display. */
  updateOffer?: Notice;
  /** The list's scrollport, so an offscreen notice keeps the rows in view. */
  scrollContainer?: RefObject<HTMLElement | null>;
  /** Ready render — only called with loaded, non-empty data. */
  children: (data: T) => ReactNode;
  /** Loading slot (e.g. skeleton rows). Defaults to the spinner line. */
  skeleton?: ReactNode;
  /** When provided and true for the loaded data, renders the empty slot. */
  isEmpty?: (data: T) => boolean;
  /** Empty slot. Defaults to the radar EmptyState. */
  empty?: ReactNode;
}

type Notice = { message: string; label: string; apply: () => void };

export function AsyncBoundary<T>({
  resource,
  children,
  skeleton,
  isEmpty,
  empty,
  loading: loadingLine,
  failed,
  emptyTitle,
  refreshFailed,
  updateOffer,
  scrollContainer,
}: AsyncBoundaryProps<T>) {
  const { data, error, loading, retry, refreshError, refresh } = resource;
  if (loading) {
    return body(skeleton ?? <ResourceLoadState error={null} loading={loadingLine} onRetry={retry} />);
  }
  if (error) {
    return <ResourceLoadState error={error} failed={failed} onRetry={retry} />;
  }
  /* A resolved-null payload is EMPTY, not failed. "Couldn't load" over an
     Error this component fabricated tells the user to retry a request that
     already succeeded, and hides a real empty state behind a false failure. */
  if (data == null || isEmpty?.(data)) {
    return <>{empty ?? <EmptyState title={emptyTitle ?? sharedEmpty()} />}</>;
  }
  const notice = updateOffer ?? (refreshError ? {
    message: refreshFailed ?? sharedRefreshFailed(),
    label: commonTryAgain(),
    apply: refresh ? () => void refresh({ preserveData: true }) : retry,
  } : null);
  return body(children(data), scrollContainer
    ? <AnchoredNotice key="refresh-notice-slot" notice={notice} scrollContainer={scrollContainer} />
    : noticeLine(notice));
}

function noticeLine(notice: Notice | null) {
  // One button stays mounted while a failed offer turns into an available update.
  return notice && (
    <div key="refresh-notice" className="empty-hint" role="status">
      {notice.message}{" "}
      <Button variant="ghost" size="sm" onClick={notice.apply}>
        {notice.label}
      </Button>
    </div>
  );
}

type AnchoredNoticeProps = {
  notice: Notice | null;
  scrollContainer: RefObject<HTMLElement | null>;
};

class AnchoredNotice extends Component<AnchoredNoticeProps, object, number | null> {
  private readonly slot = createRef<HTMLDivElement>();

  getSnapshotBeforeUpdate({ notice: previous }: AnchoredNoticeProps): number | null {
    const { notice, scrollContainer } = this.props;
    if (previous?.message === notice?.message && previous?.label === notice?.label) return null;
    const root = scrollContainer.current;
    if (!root || root.scrollTop === 0 || !this.slot.current) return null;
    const bottom = this.slot.current.getBoundingClientRect().bottom;
    return bottom <= root.getBoundingClientRect().top ? bottom : null;
  }

  componentDidUpdate(_props: AnchoredNoticeProps, _state: object, previousBottom: number | null) {
    const root = this.props.scrollContainer.current;
    const slot = this.slot.current;
    // Measure after native anchoring, which may already have held the rows.
    if (root && slot && previousBottom !== null) {
      root.scrollTop += slot.getBoundingClientRect().bottom - previousBottom;
    }
  }

  render() {
    return <div ref={this.slot}>{noticeLine(this.props.notice)}</div>;
  }
}

/* The content sits under one key in every state, so React matches it by key
   when the refresh notice comes or goes, or the loading slot gives way to the
   ready content: the subtree stays mounted, with its focus, scroll and any
   playing media. By position alone, the notice arriving in front of it would
   remount it. */
function body(content: ReactNode, notice?: ReactNode) {
  return (
    <>
      {notice}
      <Fragment key="content">{content}</Fragment>
    </>
  );
}

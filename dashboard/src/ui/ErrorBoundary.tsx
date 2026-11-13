import { Component, type ErrorInfo, type ReactNode } from "react";

/* The app's only error boundary, and the reason it exists is lazy routes.
 *
 * A lazy route makes each screen a NETWORK dependency, and `<Suspense>` — the
 * only thing wrapped around them — handles a pending import, never a rejected
 * one. Without this, a dropped connection during navigation throws through the
 * whole tree and unmounts the root: a white page, from a two-second blip.
 *
 * A boundary is a class because there is no hook form; `getDerivedStateFromError`
 * is the only render-phase catch React offers.
 *
 * There is deliberately no soft `retry()`: for the failure this exists to catch
 * — a dead route chunk — clearing render state recovers nothing, because the
 * browser's module map has already recorded the fetch failure for the lifetime
 * of the document (see App.tsx). The reset that DOES work is
 * remounting on navigation, which the caller gets with a `key`.
 *
 * A caller that keeps one boundary across several things (a cover that stays
 * open from one posting to the next) names the thing in `resetKey` instead:
 * a caught error is dropped when it changes, so a posting that failed to
 * draw does not stand in for the next one. */
export class ErrorBoundary extends Component<
  {
    children: ReactNode;
    fallback: (error: Error) => ReactNode;
    /** Reported for telemetry. Must not throw. */
    onError?: (error: Error, info: ErrorInfo) => void;
    /** What the children show. A caught error is dropped when it changes. */
    resetKey?: string;
  },
  { error: Error | null }
> {
  state: { error: Error | null } = { error: null };

  static getDerivedStateFromError(error: Error) {
    return { error };
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    this.props.onError?.(error, info);
  }

  componentDidUpdate(previous: { resetKey?: string }) {
    if (this.state.error && previous.resetKey !== this.props.resetKey) this.setState({ error: null });
  }

  render() {
    const { error } = this.state;
    if (error) return <>{this.props.fallback(error)}</>;
    return <>{this.props.children}</>;
  }
}

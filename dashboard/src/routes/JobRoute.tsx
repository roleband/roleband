import { useCallback, useEffect } from "react";
import { Navigate, useLocation, useNavigate, useNavigationType, useParams } from "react-router-dom";
import { JobDetail, type PostingTab } from "../features/job-detail/JobDetail";
import { usePostingPipeline } from "../features/applications/usePostingPipeline";
import { useJobActions, useJobWorkspace } from "../context/JobWorkspace";
import { pipelineViewUnder, positionPath } from "../routing/paths";
import { shellNavRadar, shellTabPipelineBoard, shellTabPipelineList, shellTabPipelineUpNext } from "../copy/gen/shell";

/** The views Back names when the posting covers one of them. */
const VIEW_NAME: Record<string, () => string> = {
  "/": shellNavRadar,
  "/pipeline/board": shellTabPipelineBoard,
  "/pipeline/list": shellTabPipelineList,
  "/pipeline/up-next": shellTabPipelineUpNext,
};

const isTab = (value: string | null): value is PostingTab => value === "posting" || value === "workspace";

/* Routed full-screen detail. Canonical URL nests under the company
   (/company/:slug/job/:id); /job/:id is the short form. Works both as an
   overlay reached from a list and as a standalone page reached by a direct
   link or refresh. Which one is the SLOT's decision (App renders the overlay
   routes separately), not history's: a comparison with a role stacked on it
   carries a background too, and must still render as the page underneath. */
export function JobRoute({ asOverlay = false }: { asOverlay?: boolean }) {
  const { slug, id } = useParams();
  const jobId = Number(id);
  const navigate = useNavigate();
  const location = useLocation();
  const { openJob, openCompare, markJobViewed, setCompare, toggleCompare } = useJobActions();
  // The route subscribes to the selection because the detail's toggle is a
  // STATE, not just a verb: it has to say whether this role is in, and what the
  // selection it is joining already holds.
  const { compareIds, compareFull, compareCap } = useJobWorkspace();

  useEffect(() => {
    if (Number.isInteger(jobId) && jobId > 0) markJobViewed(jobId);
  }, [jobId, markJobViewed]);

  const background = (location.state as { backgroundLocation?: { pathname?: unknown } } | null)?.backgroundLocation;
  const hasBackground = Boolean(background);
  // Reached from a link on a posting that was the page: that posting is one
  // entry back.
  const steppedFrom = Boolean((location.state as { steppedFrom?: unknown } | null)?.steppedFrom);
  // Reached by going back or forward: a posting read before opens where it was left.
  const returning = useNavigationType() === "POP";

  const onBack = useCallback(() => {
    // Reached via in-app navigation: step back so the underlying list keeps its
    // scroll and filters. Reached directly (refresh / shared link): go to board.
    if (hasBackground || steppedFrom) navigate(-1);
    else navigate("/");
  }, [hasBackground, steppedFrom, navigate]);

  // Back names where it goes: the view under the cover, the Radar for a
  // posting that is the page, and nothing more for a step back to the
  // posting this one was opened from.
  const under = typeof background?.pathname === "string" ? background.pathname : null;
  // Opened from a Pipeline view, the role is a page of the Pipeline: it opens
  // beside the rail, which keeps that view marked.
  const besideRail = asOverlay && pipelineViewUnder(location) != null;
  const backTo = hasBackground
    ? (under != null && Object.prototype.hasOwnProperty.call(VIEW_NAME, under) ? VIEW_NAME[under]() : null)
    : steppedFrom ? null : shellNavRadar();

  // The tab of a role in the pipeline is part of the address, so a link names
  // it; switching replaces the entry and keeps the way back.
  const named = new URLSearchParams(location.search).get("tab");
  const tab = isTab(named) ? named : null;
  const onTab = useCallback(
    (next: PostingTab) => {
      const search = new URLSearchParams(location.search);
      search.set("tab", next);
      navigate({ pathname: location.pathname, search: `?${search}` }, { replace: true, state: location.state });
    },
    [navigate, location.pathname, location.search, location.state],
  );

  // Canonicalize the URL to the company-scoped form once the job's company is
  // known: a short /job/:id (no slug) or a hand-typed wrong slug is replaced
  // with /company/:slug/job/:id, preserving any overlay background so shared
  // links and the back button keep working.
  const onCompanyResolved = useCallback(
    (companySlug: string) => {
      if (companySlug && slug !== companySlug) {
        navigate({ pathname: positionPath(companySlug, jobId), search: location.search }, { replace: true, state: location.state });
      }
    },
    [slug, jobId, navigate, location.search, location.state],
  );

  if (!Number.isInteger(jobId) || jobId <= 0) return <Navigate to="/" replace />;

  return (
    <JobDetail
      jobId={jobId}
      asOverlay={asOverlay}
      besideRail={besideRail}
      onBack={onBack}
      onOpen={openJob}
      onCompare={(ids) => {
        setCompare(ids);
        openCompare();
      }}
      compareOn={compareIds.has(jobId)}
      compareCount={compareIds.size}
      compareDisabled={compareFull}
      compareCap={compareCap}
      onToggleCompare={() => toggleCompare(jobId)}
      onViewCompare={openCompare}
      onCompanyResolved={onCompanyResolved}
      usePipeline={usePostingPipeline}
      returning={returning}
      tab={tab}
      onTab={onTab}
      backTo={backTo}
    />
  );
}

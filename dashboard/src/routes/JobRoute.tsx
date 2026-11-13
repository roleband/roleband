import { useCallback, useEffect } from "react";
import { Navigate, useLocation, useNavigate, useNavigationType, useParams } from "react-router-dom";
import { JobDetail } from "../features/job-detail/JobDetail";
import { usePostingPipeline } from "../features/applications/usePostingPipeline";
import { useJobActions, useJobWorkspace, type PostingNeighbour } from "../context/JobWorkspace";
import { positionPath } from "../routing/paths";

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

  const hasBackground = Boolean((location.state as { backgroundLocation?: unknown } | null)?.backgroundLocation);
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

  // Canonicalize the URL to the company-scoped form once the job's company is
  // known: a short /job/:id (no slug) or a hand-typed wrong slug is replaced
  // with /company/:slug/job/:id, preserving any overlay background so shared
  // links and the back button keep working.
  const onCompanyResolved = useCallback(
    (companySlug: string) => {
      if (companySlug && slug !== companySlug) {
        navigate(positionPath(companySlug, jobId), { replace: true, state: location.state });
      }
    },
    [slug, jobId, navigate, location.state],
  );

  // The list the posting was opened from, when it was opened from one and is
  // still in it: its place there, and the way to the rows on either side. A
  // step replaces this history entry, so Back still returns to the list.
  const postingList = (location.state as { postingList?: readonly PostingNeighbour[] } | null)?.postingList;
  const at = postingList ? postingList.findIndex((one) => one.id === jobId) : -1;
  const step = useCallback(
    (to: PostingNeighbour | undefined) => {
      if (!to) return;
      navigate(to.company ? positionPath(to.company, to.id) : `/job/${to.id}`, { replace: true, state: location.state });
    },
    [navigate, location.state],
  );
  const pager = postingList && at >= 0
    ? {
        position: at + 1,
        count: postingList.length,
        onPrevious: at > 0 ? () => step(postingList[at - 1]) : undefined,
        onNext: at < postingList.length - 1 ? () => step(postingList[at + 1]) : undefined,
        next: postingList[at + 1],
      }
    : undefined;

  if (!Number.isInteger(jobId) || jobId <= 0) return <Navigate to="/" replace />;

  return (
    <JobDetail
      jobId={jobId}
      asOverlay={asOverlay}
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
      pager={pager}
      returning={returning}
    />
  );
}

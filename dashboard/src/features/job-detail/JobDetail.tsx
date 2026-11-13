import "../../patterns/jobs/job-row.css";
import { ResourceLoadState } from "../../ui/ResourceLoadState";
import { Badge } from "../../ui/Badge";
import { Button } from "../../ui/Button";
import { type ReactNode, useCallback, useEffect, useId, useRef, useState } from "react";
import { useSyncEpoch } from "../../context/SyncState";
import { useAsyncResource, useRefetchOn } from "../../hooks/useAsyncResource";
import { useSaveCommand } from "../../context/useSaveCommand";
import { useToast } from "../../ui/Toast";
import { Job, PursuitStage, SimilarJob, api, isNotFound } from "../../api";
import { statusName } from "../../copy/vocab";
import { BAND_LABEL, companyName } from "../../format";
import { payPoint } from "../../payShown";
import { usePayCoverage } from "../../payCoverage";
import JobCompPanel, { JobCompDock } from "./JobCompPanel";
import { useReadingChrome } from "./readingChrome";
import { useHeld, useShownPosting } from "./postingTurn";
import { JobDescription } from "./JobDescription";
import { JobRequirementsPanel } from "./JobRequirementsPanel";
import { LineageStack } from "./LineageStack";
import { ListingAge } from "./ListingAge";
import { postingTeam, postingWorkplace } from "./detailFacts";
import { PostingReality } from "./PostingReality";
import { unfollowedSentence } from "../../patterns/jobs/unfollowed";
import { applyAsk } from "./applyAsk";
import { PlaceSetSection } from "./PlaceSetSection";
import { TwinDeck } from "./TwinDeck";
import { readSimilarFolded, writeSimilarFolded } from "./similarFold";
import { Icon } from "../../ui/Icon";
import { CompanyChip } from "../../patterns/companies/CompanyChip";
import { BandBadge, LocBadge } from "../../patterns/jobs/JobBadges";
import "./job-detail.css";
import { JobLinkRow } from "../../patterns/jobs/JobLinkRow";
import { Cover } from "../../patterns/Cover";
import { postingPlaces } from "../../patterns/jobs/location";
import { placeGroupsBeyond } from "../../patterns/jobs/placeGroups";
import {
  roleJobDetail1InComparePickOne,
  roleJobDetailBack,
  roleJobDetailBack2,
  roleJobDetailNextPosting,
  roleJobDetailPager,
  roleJobDetailPagerNext,
  roleJobDetailPagerPlace,
  roleJobDetailPagerPrevious,
  roleJobDetailCompare,
  roleJobDetailCompareIsFullMax,
  roleJobDetailCompareRoles,
  roleJobDetailCouldNotUnsaveThisRole,
  roleJobDetailDescription,
  roleJobDetailDetails,
  roleJobDetailItSNoLongerIn,
  roleJobDetailMoreLikeThis,
  roleJobDetailOtherCompanies,
  roleJobDetailPostings,
  roleJobDetailQuestionsTheEmployerAddedBeyond,
  roleJobDetailReposted,
  roleJobDetailRole,
  roleJobDetailSameCompany,
  roleJobDetailSimilarity,
  roleJobDetailStatus,
  roleJobDetailTeam,
  roleJobDetailToApply,
  roleJobDetailViewApply,
  roleJobDetailViewPosting,
  roleJobDetailWorkplace,
} from "../../copy/gen/role";
import { Msg } from "../../ui/Msg";
import { Content } from "../../ui/Content";
import { shellLoadRoleFailed, shellLoadingRole } from "../../copy/gen/shell";

/** Whether the role requirements panel stands above the description. */
const SHOW_REQUIREMENTS: boolean = false;

/** Whether the posting's level is one to show: a level it never stated, or
 *  one that could not be placed, is kept for sorting only (`BandBadge`). */
const stated = (job: Job): boolean => job.level_basis !== "none" && job.level_basis !== "unmapped";

/** Similar positions shown per category (same company / other companies). */
const SIMILAR_PER_CATEGORY = 3;

/** The pipeline's part of the posting, which the route composes in (a feature
 *  never imports another): the bar's control for the role's place in the
 *  pipeline, the side column's Pipeline section, and whether the person has
 *  applied. Called as a hook, so the route passes one function for the life of
 *  the screen. */
export type UsePostingPipeline = (
  job: Job | null,
  options: {
    showSaved: (on: boolean) => void;
    paintPosting: (stage: PursuitStage) => void;
    rereadPosting: () => void;
    onSave: () => void;
    now: Date;
    /** The side column, which the section's history opens across. */
    column: HTMLElement | null;
  },
) => { control: ReactNode; section: ReactNode; applied: boolean };

/* Full-screen opportunity detail. Rendered by JobRoute at /job/:id — as a routed
   overlay over the current page (in-app navigation) or standalone (direct link /
   refresh). onBack pops history back to wherever the user came from. */
export function JobDetail({
  jobId,
  onBack,
  onOpen,
  onCompare = () => {},
  compareOn,
  compareCount,
  compareDisabled,
  compareCap,
  onToggleCompare,
  onViewCompare,
  onCompanyResolved,
  usePipeline,
  pager,
  returning = false,
  asOverlay = false,
}: {
  jobId: number;
  onBack: () => void;
  onOpen: (id: number, companySlug?: string | null) => void;
  /** Replace the selection with these roles and go to Compare. The twin deck's
   *  verb: "compare this posting with its twins" is a whole comparison, not an
   *  addition to one. */
  onCompare?: (ids: number[]) => void;
  /** This role is in the standing compare selection. */
  compareOn: boolean;
  /** How many roles the selection holds, this one included. The reader who
   *  picks while reading needs to know what they are picking INTO — one is a
   *  comparison still waiting for its other half, two is one they can go and
   *  read. */
  compareCount: number;
  /** The selection is at the cap. Only blocks ADDING; a selected role can
   *  always be taken back out. */
  compareDisabled: boolean;
  /** How many roles the comparison holds, so a blocked toggle can say why. */
  compareCap: number;
  onToggleCompare: () => void;
  /** Go to the comparison. Offered only once there is one to see (>= 2). */
  onViewCompare: () => void;
  /** True when this covers a page that is still mounted underneath (opened from
   *  a list). Then it is a modal dialog; reached by a direct link it is the
   *  page itself and must NOT claim to be one. */
  asOverlay?: boolean;
  // Reports the loaded job's company slug so a bare /job/:id URL can
  // canonicalize to /company/:slug/job/:id.
  onCompanyResolved?: (companySlug: string) => void;
  usePipeline: UsePostingPipeline;
  /** The posting's place in the list it was opened from, and the way to the
   *  postings on either side; absent when it was not opened from a list. A
   *  step is undefined at the list's end. */
  pager?: {
    position: number;
    count: number;
    onPrevious?: () => void;
    onNext?: () => void;
    /** The posting `onNext` opens, as the list holds it. */
    next?: { title?: string; company?: string | null };
  };
  /** The posting was reached by going back or forward in history. */
  returning?: boolean;
}) {
  // On the shared resource, which aborts the request it supersedes: a slow
  // /jobs/:id for the PREVIOUS position never lands after the next one.
  const detail = useAsyncResource<Job>((signal) => api.job(jobId, signal), [jobId]);
  const compareFull = compareDisabled && !compareOn;
  const fullReasonId = useId();
  const { data: fresh, mutate: setJobData, refresh: refreshJob, error: notFoundError, loading, retry: retryJob } = detail;
  // Its estimate moved with a reference change: re-read it.
  const { referenceVersion } = useSyncEpoch();
  useRefetchOn(referenceVersion, refreshJob);
  const notFound = notFoundError != null;
  // The posting drawn: the one the route names, or, between two postings,
  // the last one until the next has loaded and the reading area turns to it.
  const scrollRef = useRef<HTMLDivElement>(null);
  const { job, turning } = useShownPosting(fresh, {
    wanted: jobId, loading, failed: notFound, place: pager?.position ?? null, box: scrollRef, returning,
  });
  // Three per category, fetched as three: more near-identical rows under the
  // two category labels read as one wall of text. The cap is a reading limit, not a ranking one: applied at the request so nothing is
  // fetched to be hidden, and again on the response so the reader never sees
  // more than three even if a source ignores `limit`.
  const capped = (r: { items: SimilarJob[] }) => r.items.slice(0, SIMILAR_PER_CATEGORY);
  const similarWithin = useAsyncResource<SimilarJob[]>(
    (signal) => api.similar(jobId, "within", SIMILAR_PER_CATEGORY, signal).then(capped),
    [jobId],
  );
  const similarCross = useAsyncResource<SimilarJob[]>(
    (signal) => api.similar(jobId, "cross", SIMILAR_PER_CATEGORY, signal).then(capped),
    [jobId],
  );
  // The similar rows show pay too: a source switch re-reads them with the job.
  useRefetchOn(referenceVersion, similarWithin.refresh);
  useRefetchOn(referenceVersion, similarCross.refresh);
  const { toast } = useToast();
  // A confirmed save refreshes the counts and tells every reader of saved
  // state, the comparison under this cover included.
  const saveRole = useSaveCommand();
  // The rows of the posting on show, not of the one still loading.
  const within = useHeld(similarWithin.data, turning) ?? [];
  const cross = useHeld(similarCross.data, turning) ?? [];

  // One clock per render, so the stage's days and every due date agree.
  const now = new Date();
  const showSaved = useCallback(
    (on: boolean) => setJobData((prev) => prev && { ...prev, is_favorite: on }),
    [setJobData],
  );
  const paintPosting = useCallback(
    (stage: PursuitStage) => setJobData((prev) => prev?.pursuit ? { ...prev, pursuit: { ...prev.pursuit, stage } } : prev),
    [setJobData],
  );
  /** Reads the posting again: its star and stage as the server holds them. */
  const rereadPosting = useCallback(() => void refreshJob({ preserveData: true }), [refreshJob]);
  /** Saves a role that is not in the pipeline. Once it is, the star becomes
   *  the stage control, which is the way out. */
  const saveFav = () => {
    if (!job) return;
    // One writer per role across every surface. A failed write that
    // is still the newest rolls the star back to what the server holds at
    // once, rather than leaving it lit until the next load; only that one
    // rejects, so reading the posting back here never undoes a newer write.
    // The read catches a stage set elsewhere while the posting was open.
    saveRole({ jobId: job.id, was: job.is_favorite, next: true, show: showSaved, send: () => api.setFavorite(job.id, true) })
      .catch(() => {
        rereadPosting();
        toast({ key: "job", text: roleJobDetailCouldNotUnsaveThisRole({ choice: "yes" }) });
      });
  };

  /** The side column, which the histories open across. */
  const [aside, setAside] = useState<HTMLElement | null>(null);
  // More like this is for choosing where to go next, so it stands open at the
  // top of a posting and folds once the person is reading (the pay panel has
  // left and its copy stands in the column), leaving the role's own facts
  // beside the text. Opened while reading, it stays open for that posting.
  // Folded at the top, it is folded everywhere: the choice this browser keeps.
  const [similarFolded, setSimilarFolded] = useState(readSimilarFolded);
  const [reading, setReading] = useState(false);
  const [openedWhileReading, setOpenedWhileReading] = useState<number | null>(null);
  const similarShut = similarFolded || (reading && openedWhileReading !== job?.id);
  const foldSimilar = () => {
    if (reading) {
      setOpenedWhileReading(similarShut ? job?.id ?? null : null);
      if (similarFolded) {
        writeSimilarFolded(false);
        setSimilarFolded(false);
      }
      return;
    }
    writeSimilarFolded(!similarFolded);
    setSimilarFolded(!similarFolded);
  };
  // Where the person stands with the role, read as the pipeline reads it.
  const pipeline = usePipeline(job, { showSaved, paintPosting, rereadPosting, onSave: saveFav, now, column: aside });
  const { applied } = pipeline;
  const team = job && postingTeam(job);
  const workplace = job && postingWorkplace(job);

  // Once the job is loaded, report its company so a bare /job/:id URL can
  // canonicalize to the company-scoped position path.
  useEffect(() => {
    if (fresh) onCompanyResolved?.(fresh.company);
  }, [fresh, onCompanyResolved]);

  // Read what applying asks from the posting's own page, once, AFTER
  // the page is shown, so an open never waits on the source. The server says
  // whether there is anything to read; a failure shows nothing and the next
  // open may try again. It cannot loop: success clears the flag, and a failure
  // leaves the dependencies unchanged.
  const formReadable = job != null && "application_form_readable" in job && job.application_form_readable;
  const jobIdLoaded = job?.id;
  // The header's place line: the first few places, which its tags must not
  // repeat. The server's tidied list (one label an office, countries in
  // words); the source's own when it names nothing that list can hold.
  const places = job ? (job.places?.length ? job.places : postingPlaces(job.locations)).slice(0, 4) : [];
  // One ask per posting per open, whatever the detail says afterwards: the
  // refresh below reads the flag again, and a server that kept saying
  // "readable" must not turn that into a loop.
  const askedFor = useRef<number | null>(null);
  /** This cover's posting stack, for its History's "Compare the postings". */
  const lineageRef = useRef<HTMLElement>(null);
  useEffect(() => {
    if (!formReadable || jobIdLoaded == null || askedFor.current === jobIdLoaded) return;
    askedFor.current = jobIdLoaded;
    let live = true;
    api
      .readPostingPage(jobIdLoaded)
      .then((result) => {
        if (!live) return;
        setJobData((prev) =>
          prev && prev.id === jobIdLoaded
            ? { ...prev, application_form: result.application_form, application_form_readable: false }
            : prev,
        );
        // The page may also state the pay the text left out, which changes
        // the pay panel and the pay floor line: read the detail again, keeping
        // what is shown until it lands.
        if (result.outcome === "read") void refreshJob({ preserveData: true });
      })
      .catch(() => undefined);
    return () => {
      live = false;
    };
  }, [formReadable, jobIdLoaded, setJobData, refreshJob]);

  // The elements that answer the scroll: the heading and the bar's copy of
  // it, the main column (for its pay panel) and the panel's small copy.
  const [titleEl, setTitleEl] = useState<HTMLElement | null>(null);
  const [mainEl, setMainEl] = useState<HTMLElement | null>(null);
  const [dockEl, setDockEl] = useState<HTMLElement | null>(null);
  const [roleEl, setRoleEl] = useState<HTMLElement | null>(null);
  useReadingChrome(scrollRef, { title: titleEl, main: mainEl, dock: dockEl, role: roleEl }, setReading);

  // J and K step through the list, as they move through its rows: only while
  // the keyboard is on the posting itself, never in a field, a menu or a
  // dialog opened over it, and never with a modifier.
  const onPrevious = pager?.onPrevious;
  const onNext = pager?.onNext;
  useEffect(() => {
    if (!onPrevious && !onNext) return;
    const onKey = (event: KeyboardEvent) => {
      if (event.defaultPrevented || event.metaKey || event.ctrlKey || event.altKey) return;
      const key = event.key.toLowerCase();
      if (key !== "j" && key !== "k") return;
      const target = event.target as HTMLElement | null;
      if (target && (target.isContentEditable || ["INPUT", "TEXTAREA", "SELECT"].includes(target.tagName))) return;
      // On the posting: focus in the cover, on the dialog that holds it, or
      // nowhere. Focus left on the list under the cover (the row that opened
      // it) is nowhere too: that page is inert.
      const cover = scrollRef.current?.closest(".cover");
      const active = document.activeElement;
      const onPosting = !active || active === document.body
        || !!cover && (cover.contains(active) || active.contains(cover))
        || !!active.closest("[inert]");
      if (!onPosting) return;
      const go = key === "j" ? onNext : onPrevious;
      if (!go) return;
      event.preventDefault();
      go();
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [onPrevious, onNext]);

  const label = roleJobDetailRole({ choice: (job) ? "yes" : "no", title: (job) ? String(job.title) : "" });

  /* The screen's body. Identical in both shells — only the CONTAINER differs,
     because the two are different things to a keyboard and a screen reader:
     opened over a list this is a modal dialog, reached by a direct link it is
     the page itself. */
  const bar = (
    <>
        <Button onClick={onBack} aria-label={roleJobDetailBack2()}>
          <Icon name="arrowLeft" size={15} /> {roleJobDetailBack()}
        </Button>
        {/* The bar's middle: empty while the posting's heading is in view,
            then the role, where the heading stood. A copy for the eye; the
            heading itself is the one a screen reader reads. */}
        {job ? (
          <div className="jd-bar-role" ref={setRoleEl} aria-hidden="true">
            <span className="jd-bar-title"><Content text={job.title} /></span>
            <span className="jd-bar-sub">
              {companyName(job.company)}
              {stated(job) && <> · {BAND_LABEL[job.level_band] ?? job.level_band}</>}
            </span>
          </div>
        ) : (
          <div className="cover-bar-spacer" />
        )}
        {/* The standing selection, stated where the gesture is. Leaving the
            cover does not end it — it is server-backed — so the
            reader who picks here needs to be told what happens next: at one
            the comparison is waiting for its other half, at two it can be
            read. Without this the count lives only in the rail badge, and the
            beacon that would say it does not raise until the second role. */}
        {/* The place in the list the posting was opened from, and the rows on
            either side: it opens the bar's right-hand group, apart from the
            actions on this posting. */}
        {pager && (
          <div className="jd-pager" role="group" aria-label={roleJobDetailPager()}>
            <Button
              variant="icon"
              size="sm"
              aria-label={roleJobDetailPagerPrevious()}
              aria-keyshortcuts="K"
              aria-disabled={!pager.onPrevious || undefined}
              onClick={() => pager.onPrevious?.()}
            >
              <Icon name="chevronLeft" size={15} />
            </Button>
            <span className="jd-pager-place">{roleJobDetailPagerPlace({ place: pager.position, count: pager.count })}</span>
            <Button
              variant="icon"
              size="sm"
              aria-label={roleJobDetailPagerNext()}
              aria-keyshortcuts="J"
              aria-disabled={!pager.onNext || undefined}
              onClick={() => pager.onNext?.()}
            >
              <Icon name="chevronRight" size={15} />
            </Button>
          </div>
        )}
        {/* What acts on this posting. Between two postings the one drawn is
            not the one the route names, so its controls take no input; each
            posting gets its own, so a menu left open does not follow. */}
        <div className="jd-bar-actions" key={job?.id ?? 0} inert={turning}>
        {job && compareCount === 1 && (
          <span className="jd-compare-state" role="status">
            {roleJobDetail1InComparePickOne()}
          </span>
        )}
        {job && compareCount >= 2 && (
          <Button variant="link" onClick={onViewCompare}>
            <Msg of={roleJobDetailCompareRoles} elems={{ compareCount: compareCount }} /> <Icon name="arrowRight" size={13} />
          </Button>
        )}
        {job && (
          /* Visible text IS the accessible name, and `aria-pressed` carries the
             state — the row's icon-only twin has to spell both into a label,
             but here there is room to say it once. */
          <>
            {/* Full: still focusable, with the reason as its description. */}
            <Button
              onClick={() => { if (!compareFull) onToggleCompare(); }}
              aria-pressed={compareOn}
              aria-disabled={compareFull || undefined}
              aria-describedby={compareFull ? fullReasonId : undefined}
              title={compareFull ? roleJobDetailCompareIsFullMax({ compareCap: compareCap }) : undefined}
            >
              <Icon name={compareOn ? "check" : "columns"} size={15} />{" "}
              {roleJobDetailCompare({ choice: (compareOn) ? "yes" : "no" })}
            </Button>
            {compareFull && (
              <span id={fullReasonId} className="sr-only">{roleJobDetailCompareIsFullMax({ compareCap: compareCap })}</span>
            )}
          </>
        )}
        {pipeline.control}
        {/* Once applied, the employer's page is something to read again, not an action. */}
        {job && (
          <a
            className={`ui-btn ${applied ? "ui-btn-ghost ui-btn-strong" : "ui-btn-primary"} ui-btn-md`}
            href={job.url}
            target="_blank"
            rel="noreferrer"
          >
            {applied ? roleJobDetailViewPosting() : roleJobDetailViewApply()} <Icon name="external" size={15} />
          </a>
        )}
        </div>
        {/* The next posting is still on its way: a line along the bar's foot,
            drawn only once the wait outlasts a quick load. */}
        {turning && <span className="jd-waiting" aria-hidden="true" />}
    </>
  );

  const body = (
    <>
        {loading && !job && (
          <div className="jd-container">
            <ResourceLoadState error={null} loading={shellLoadingRole()} />
          </div>
        )}
        {notFound && (
          <div className="jd-container">
            {/* One error card app-wide, with a way out, never a bare "Not
                found" label with no retry. */}
            <ResourceLoadState
              error={notFoundError ?? new Error("not found")}
              failed={shellLoadRoleFailed()}
              onRetry={retryJob}
              gone={isNotFound(notFoundError) ? roleJobDetailItSNoLongerIn() : undefined}
            />
          </div>
        )}
        {job && (
          /* Keyed by the posting: what a posting opened (a history, a deck)
             belongs to it and does not carry over to the next. */
          <div className="jd-container" key={job.id} inert={turning}>
            <header className="jd-hero">
              <div style={{ display: "flex", gap: 6, flexWrap: "wrap", alignItems: "center" }}>
                <CompanyChip slug={job.company} />
                <BandBadge band={job.level_band} confidence={job.level_confidence} basis={job.level_basis} />
                {(job.lineage_size ?? 0) > 1 ? (
                  <Badge shape="tag" variant="tint" tone="warning"><Msg of={roleJobDetailPostings} elems={{ lineage_size: job.lineage_size }} /></Badge>
                ) : (
                  job.repost_count > 0 && (
                    <Badge shape="tag" variant="tint" tone="warning"><Msg of={roleJobDetailReposted} elems={{ repost_count: job.repost_count }} /></Badge>
                  )
                )}
              </div>
              <h1 ref={setTitleEl}><Content text={job.title} /></h1>
              <div className="job-meta">
                {places.map((l, i) => (
                  <span key={i} style={{ display: "inline-flex", alignItems: "center", gap: 4 }}>
                    {i === 0 && <Icon name="pin" size={13} />} <Content text={l} />
                  </span>
                ))}
                {placeGroupsBeyond(job.location_groups, places).map((g) => (
                  <LocBadge key={g} slug={g} />
                ))}
              </div>
              {job.company_unfollowed && (
                <p className="jd-unfollowed">{unfollowedSentence(job)}</p>
              )}
            </header>

            {(job.lineage_size ?? 0) > 1 && <LineageStack ref={lineageRef} jobId={job.id} />}
            {/* The deck shows direct twins only, and the row counts them: a role
                with none asks for nothing. */}
            {job.twin_count > 0 && <TwinDeck jobId={job.id} onOpen={onOpen} onCompare={onCompare} />}
            <PlaceSetSection jobId={job.id} onOpen={onOpen} />

            <div className="jd-grid">
              <div className="jd-main" ref={setMainEl}>
                {/* ONE total, not two. The market median is a reconciliation line
                    inside the package, not a peer panel with its own headline, so a
                    disagreement is stated rather than left for the reader to
                    arbitrate. */}
                <JobCompPanel job={job} />

                {/* Off the posting while its worth there is decided: the read
                    starts under the pay panel. */}
                {SHOW_REQUIREMENTS && (
                  <JobRequirementsPanel
                    requirements={job.requirements}
                    onShowSection={(key) =>
                      scrollRef.current
                        ?.querySelector(`.jd-section-${key}`)
                        ?.scrollIntoView({ behavior: "smooth", block: "start" })
                    }
                  />
                )}

                <div className="section-title">{roleJobDetailDescription()}</div>
                <JobDescription
                  sections={job.description_sections}
                  fallback={job.description_text}
                />

                {/* The read ends on the way on: the next posting in the list
                    it was opened from, the step J takes. */}
                {pager?.onNext && (
                  <footer className="jd-end">
                    <button type="button" className="jd-next" aria-keyshortcuts="J" onClick={pager.onNext}>
                      <span className="jd-next-kicker">{roleJobDetailNextPosting()}</span>
                      {pager.next?.title && (
                        <span className="jd-next-title"><Content text={pager.next.title} /></span>
                      )}
                      <span className="jd-next-meta">
                        {pager.next?.company && <>{companyName(pager.next.company)} · </>}
                        {roleJobDetailPagerPlace({ place: pager.position + 1, count: pager.count })}
                      </span>
                      <Icon name="arrowRight" size={16} />
                    </button>
                  </footer>
                )}
              </div>

              <aside className="jd-aside" ref={setAside}>
                {/* The pay panel's small copy, grown by the scroll once the
                    panel has left. The panel is the one a screen reader reads. */}
                <div className="jd-dock" ref={setDockEl} aria-hidden="true">
                  <div className="jd-dock-in"><JobCompDock job={job} /></div>
                </div>

                {pipeline.section}

                <div className="section-title">{roleJobDetailDetails()}</div>
                <dl className="kv">
                  {team && (
                    <>
                      <dt>{roleJobDetailTeam()}</dt>
                      <dd><Content text={team} /></dd>
                    </>
                  )}
                  {workplace && (
                    <>
                      <dt>{roleJobDetailWorkplace()}</dt>
                      <dd>{workplace}</dd>
                    </>
                  )}
                  {/* One age, with where it counts from; the dates behind it
                      are the history, on demand. */}
                  <ListingAge
                    job={job}
                    column={aside}
                    onOpen={(id) => onOpen(id)}
                    onShowPostings={() => lineageRef.current?.scrollIntoView({ block: "start" })}
                  />
                  <dt>{roleJobDetailStatus()}</dt>
                  <dd style={{ textTransform: "capitalize" }}>{statusName(job.status) ?? <Content text={job.status} />}</dd>
                  {/* Read from the posting's own page; absent until read. */}
                  {"application_form" in job && job.application_form && (
                    <>
                      <dt>{roleJobDetailToApply()}</dt>
                      <dd title={roleJobDetailQuestionsTheEmployerAddedBeyond()}>
                        {applyAsk(job.application_form)}
                      </dd>
                    </>
                  )}
                </dl>

                <PostingReality reality={job.posting_reality} />

                {(within.length > 0 || cross.length > 0) && (
                  <>
                    {/* The whole heading line folds the section away, for a
                        column of the role's own facts only: the kicker's
                        words, then a chevron at the line's end. */}
                    <div className="section-title">
                      <button type="button" className="jd-fold" aria-expanded={!similarShut} onClick={foldSimilar}>
                        {roleJobDetailMoreLikeThis()}
                        <Icon name="chevronDown" size={14} />
                      </button>
                    </div>
                    {/* The rows stay in the page while folded, out of sight and out
                        of reach, so the fold closes as smoothly as it opens. */}
                    <div className="similar-fold" data-shut={similarShut || undefined} inert={similarShut}>
                      <div className="similar-groups">
                        {cross.length > 0 && (
                          <div className="similar-group">
                            <div data-selection="chrome" className="similar-label">{roleJobDetailOtherCompanies()}</div>
                            {cross.map((s) => (
                              <SimilarRow key={s.id} job={s} onOpen={onOpen} />
                            ))}
                          </div>
                        )}
                        {within.length > 0 && (
                          <div className="similar-group">
                            <div data-selection="chrome" className="similar-label"><Msg of={roleJobDetailSameCompany} elems={{ company: companyName(job.company) }} /></div>
                            {within.map((s) => (
                              <SimilarRow key={s.id} job={s} onOpen={onOpen} />
                            ))}
                          </div>
                        )}
                      </div>
                    </div>
                  </>
                )}
              </aside>
            </div>
          </div>
        )}
    </>
  );

  /* The shell is patterns/Cover: opened from a list it is a modal
     dialog over the page still mounted underneath; reached by URL it is the
     page. This screen keeps `job-detail` on the root for its scoped rules.
     It is a reading cover, so a large window draws it larger. */
  return (
    <Cover label={label} asOverlay={asOverlay} onBack={onBack} bar={bar} className="job-detail" scrollRef={scrollRef}>
      {body}
    </Cover>
  );
}

function SimilarRow({ job, onOpen }: { job: SimilarJob; onOpen: (id: number, companySlug?: string | null) => void }) {
  const pay = payPoint(job, usePayCoverage());
  return (
    <JobLinkRow className="mini-job similar-row" jobId={job.id} company={job.company} onOpen={onOpen}>
      <div>
        <div className="mj-title" data-selection="content"><Content text={job.title} /></div>
        <div className="mj-meta">
          {companyName(job.company)}
          {pay.text !== "—" && <> · <span title={pay.hint}>{pay.text}</span></>}
        </div>
      </div>
      <span className="similar-score" title={roleJobDetailSimilarity()}>
        {Math.round(job.score * 100)}%
      </span>
    </JobLinkRow>
  );
}

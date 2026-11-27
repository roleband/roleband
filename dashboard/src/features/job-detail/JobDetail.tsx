import "../../patterns/jobs/job-row.css";
import { ResourceLoadState } from "../../ui/ResourceLoadState";
import { Badge } from "../../ui/Badge";
import { Button } from "../../ui/Button";
import { TabBar } from "../../ui/TabBar";
import { type MouseEvent as ReactMouseEvent, type ReactNode, useCallback, useEffect, useId, useLayoutEffect, useRef, useState } from "react";
import { useSyncEpoch } from "../../context/SyncState";
import { useAsyncResource, useRefetchOn } from "../../hooks/useAsyncResource";
import { useSaveCommand } from "../../context/useSaveCommand";
import { useToast } from "../../ui/Toast";
import { Job, PostingTextResult, PursuitStage, SimilarJob, api, isNotFound } from "../../api";
import { statusName } from "../../copy/vocab";
import { BAND_LABEL, companyName } from "../../format";
import { payPoint } from "../../payShown";
import { usePayCoverage } from "../../payCoverage";
import JobCompPanel, { JobCompDock } from "./JobCompPanel";
import { useReadingChrome } from "./readingChrome";
import { useStuckTabs } from "./stuckHeadings";
import { useHeld, useShownPosting } from "./postingTurn";
import { JobDescription } from "./JobDescription";
import { usePostingText } from "./postingText";
import { JobRequirementsPanel } from "./JobRequirementsPanel";
import { LineageStack } from "./LineageStack";
import { ListingAge } from "./ListingAge";
import { postingTeam, postingWorkplace } from "./detailFacts";
import { PostingReality } from "./PostingReality";
import { unfollowedSentence } from "../../patterns/jobs/unfollowed";
import { applyAsk } from "./applyAsk";
import { PlaceSetSection } from "./PlaceSetSection";
import { TwinDeck } from "./TwinDeck";
import { TailorCvPopover } from "./TailorCv";
import { readSimilarFolded, writeSimilarFolded } from "./similarFold";
import { Icon } from "../../ui/Icon";
import { CompanyChip } from "../../patterns/companies/CompanyChip";
import { BandBadge } from "../../patterns/jobs/JobBadges";
import "./job-detail.css";
import { JobLinkRow } from "../../patterns/jobs/JobLinkRow";
import { Cover } from "../../patterns/Cover";
import { postingPlaces } from "../../patterns/jobs/location";
import {
  roleJobDetail1InComparePickOne,
  roleJobDetailBack,
  roleJobDetailBack2,
  roleJobDetailBackTo,
  roleJobDetailTabPosting,
  roleJobDetailTabWorkspace,
  roleJobDetailTabs,
  roleJobDetailNextApplyTitle,
  roleJobDetailNextKicker,
  roleJobDetailNextSaves,
  roleJobDetailNextTailorMeta,
  roleJobDetailNextTailorTitle,
  roleJobDetailTailorCv,
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
/** Where applying is tracked. */

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
    paintNotes: (notes: string | null) => void;
    rereadPosting: () => void;
    onSave: () => void;
    now: Date;
    /** The side column, which the section's history opens across. */
    column: HTMLElement | null;
    /** Where the Workspace draws the blocks that stand beside its writing. */
    beside?: HTMLElement | null;
    /** The tab the address asks for. */
    tab: PostingTab | null;
    onTab: (tab: PostingTab) => void;
  },
) => {
  control: ReactNode;
  section: ReactNode;
  applied: boolean;
  /** The tab on screen for a role in the pipeline; null for one outside it. */
  tab: PostingTab | null;
  /** The main column while the Workspace tab is on screen. */
  workspace: ReactNode;
};

/** A role in the pipeline reads in two tabs: the posting, and the person's
 *  own work on it. */
export type PostingTab = "posting" | "workspace";

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
  returning = false,
  asOverlay = false,
  besideRail = false,
  tab: askedTab = null,
  onTab = () => {},
  backTo = null,
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
  /** Opened from a Pipeline view: the cover opens beside the rail, which
   *  stays live (patterns/Cover). */
  besideRail?: boolean;
  // Reports the loaded job's company slug so a bare /job/:id URL can
  // canonicalize to /company/:slug/job/:id.
  onCompanyResolved?: (companySlug: string) => void;
  usePipeline: UsePostingPipeline;
  /** The posting was reached by going back or forward in history. */
  returning?: boolean;
  /** The tab the address asks for. */
  tab?: PostingTab | null;
  onTab?: (tab: PostingTab) => void;
  /** The name of the view Back returns to, when it has one. */
  backTo?: string | null;
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
    wanted: jobId, loading, failed: notFound, box: scrollRef, returning,
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
  const paintNotes = useCallback(
    (notes: string | null) => setJobData((prev) => prev?.pursuit ? { ...prev, pursuit: { ...prev.pursuit, notes } } : prev),
    [setJobData],
  );
  /** Reads the posting again: its star and stage as the server holds them. */
  const rereadPosting = useCallback(() => void refreshJob({ preserveData: true }), [refreshJob]);
  /** Saves a role that is not in the pipeline. Once it is, the star becomes
   *  the stage control, which is the way out. Settles true once this write
   *  landed, false when it failed: told when it was the newest, and silent
   *  when a newer write for the role was asked for and decides instead. */
  const saveFav = (): Promise<boolean> => {
    if (!job) return Promise.resolve(false);
    // One writer per role across every surface. A failed write that
    // is still the newest rolls the star back to what the server holds at
    // once, rather than leaving it lit until the next load; only that one
    // rejects, so reading the posting back here never undoes a newer write.
    // The read catches a stage set elsewhere while the posting was open.
    return saveRole({ jobId: job.id, was: job.is_favorite, next: true, show: showSaved, send: () => api.setFavorite(job.id, true) })
      .then(({ outcome }) => outcome === "saved", () => {
        rereadPosting();
        toast({ key: "job", text: roleJobDetailCouldNotUnsaveThisRole({ choice: "yes" }) });
        return false;
      });
  };
  /** Tailor CV, from the bar or the end of the read: hands the role to the
   *  person's assistant in a popover under the control that asked. Like
   *  Apply, it saves the role first. */
  const [tailorAt, setTailorAt] = useState<HTMLElement | null>(null);
  // A popover asked for on one posting does not follow to the next.
  const shownId = job?.id;
  useEffect(() => setTailorAt(null), [shownId]);
  const startTailor = (at: HTMLElement) => {
    if (job && !job.is_favorite) void saveFav();
    setTailorAt(at);
  };
  /** Apply, in the bar or at the end: the employer's form opens at the click,
   *  in a new tab, and the role is saved behind it, so the pipeline holds what
   *  the person applied to. */
  const applyAndSave = (event: ReactMouseEvent<HTMLAnchorElement>) => {
    if (event.type === "auxclick" && event.button !== 1) return;
    if (job && !job.is_favorite) void saveFav();
  };

  /** Another tab. Held under the bar, the tabs stay held and the other tab
   *  opens from its start; above, the page stays where it is. */
  const keepTabs = useRef<number | null>(null);
  function showTab(next: PostingTab) {
    const box = scrollRef.current;
    const tabs = box?.querySelector<HTMLElement>(".jd-tabs");
    const hero = box?.querySelector<HTMLElement>(".jd-hero");
    if (box && tabs && hero) {
      // Where the tabs stand unheld: right under the hero.
      const natural = hero.getBoundingClientRect().bottom - box.getBoundingClientRect().top + box.scrollTop;
      keepTabs.current = box.scrollTop > natural ? natural : null;
    }
    onTab(next);
  }

  /** The side column, which the histories open across. */
  const [aside, setAside] = useState<HTMLElement | null>(null);
  /** The room in the side column for the Workspace's short lists. */
  const [beside, setBeside] = useState<HTMLElement | null>(null);
  // More like this is for choosing where to go next, so it stands open at the
  // top of a posting and folds once the person is reading (the pay panel has
  // left and its copy stands in the column), leaving the role's own facts
  // beside the text. Opened while reading, it stays open for that posting.
  // Folded at the top, it is folded everywhere: a choice kept with the person's settings.
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
  const pipeline = usePipeline(job, {
    showSaved, paintPosting, paintNotes, rereadPosting, onSave: saveFav, now, column: aside, beside, tab: askedTab, onTab: showTab,
  });
  const { applied, tab } = pipeline;
  const onWorkspace = tab === "workspace";
  // Tabs are held under the bar once scrolled to, on either tab: the columns
  // under them reach at least the window's foot, so a short tab (a Workspace
  // with little in it yet) scrolls as far as a long posting does instead of
  // stopping with the hero's last line at the top. Measured again for each
  // tab: the posting's related roles sit between its tabs and its columns,
  // and the Workspace has nothing there.
  useLayoutEffect(() => {
    const box = scrollRef.current;
    if (!box || tab == null) return;
    let sized: HTMLElement | null = null;
    const fit = () => {
      // From the hero's foot, where the tabs stand unheld: held, they sit at
      // the top however far the columns under them have scrolled.
      const hero = box.querySelector<HTMLElement>(".jd-hero");
      const grid = box.querySelector<HTMLElement>(".jd-grid");
      if (sized && sized !== grid) sized.style.minHeight = "";
      sized = grid;
      if (hero && grid) {
        grid.style.minHeight = `${box.clientHeight - (grid.getBoundingClientRect().top - hero.getBoundingClientRect().bottom)}px`;
      }
    };
    fit();
    const watch = new ResizeObserver(fit);
    watch.observe(box);
    return () => {
      watch.disconnect();
      if (sized) sized.style.minHeight = "";
    };
  }, [tab, job?.id, scrollRef]);
  // After the columns are measured for the new tab, so a short one already
  // reaches far enough down for the scroll to land.
  useLayoutEffect(() => {
    const box = scrollRef.current;
    const held = keepTabs.current;
    // Rounded up: a scroll lands on whole device pixels, and one short of
    // the line would leave the tabs a pixel under the bar.
    if (box && held != null) box.scrollTop = Math.ceil(held);
    keepTabs.current = null;
  }, [askedTab]);
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
  // The header's place line: the first few places, as the posting names them.
  // The server's tidied list (one label an office, countries in words); the
  // source's own when it names nothing that list can hold.
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

  // A posting that opened with no text: its text is read from the employer's
  // site after the page is shown, and lands in the posting on screen.
  const showText = useCallback(
    (id: number, result: PostingTextResult) =>
      setJobData((prev) =>
        prev && prev.id === id
          ? {
              ...prev,
              description_text: result.description_text,
              description_sections: result.description_sections,
              description_readable: false,
            }
          : prev,
      ),
    [setJobData],
  );
  const { read: textRead, arrived: textArrived } = usePostingText(job, showText, rereadPosting);

  // The elements that answer the scroll: the heading and the bar's copy of
  // it, the main column (for its pay panel) and the panel's small copy.
  const [titleEl, setTitleEl] = useState<HTMLElement | null>(null);
  const [mainEl, setMainEl] = useState<HTMLElement | null>(null);
  const [dockEl, setDockEl] = useState<HTMLElement | null>(null);
  const [roleEl, setRoleEl] = useState<HTMLElement | null>(null);
  const [tabsEl, setTabsEl] = useState<HTMLElement | null>(null);
  useStuckTabs(tabsEl);
  useReadingChrome(
    scrollRef,
    { title: titleEl, main: mainEl, dock: dockEl, role: roleEl, under: tabsEl },
    setReading,
  );

  const label = roleJobDetailRole({ choice: (job) ? "yes" : "no", title: (job) ? String(job.title) : "" });

  /* The screen's body. Identical in both shells — only the CONTAINER differs,
     because the two are different things to a keyboard and a screen reader:
     opened over a list this is a modal dialog, reached by a direct link it is
     the page itself. */
  const bar = (
    <>
        <Button onClick={onBack} aria-label={backTo ? roleJobDetailBackTo({ view: backTo }) : roleJobDetailBack2()}>
          <Icon name="arrowLeft" size={15} /> {backTo ?? roleJobDetailBack()}
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
        {/* Two groups: the tools, Compare and the star, as icons, the Radar
            row's own pair; then the path to applying, in the order it is
            done, with Apply the one filled button. Once applied, the path
            leaves and the tools stay. */}
        {job && (
          <>
            {/* Full: still focusable, with the reason as its description. */}
            <Button
              variant="icon"
              size="sm"
              onClick={() => { if (!compareFull) onToggleCompare(); }}
              aria-pressed={compareOn}
              aria-disabled={compareFull || undefined}
              aria-describedby={compareFull ? fullReasonId : undefined}
              aria-label={roleJobDetailCompare({ choice: compareOn ? "yes" : "no" })}
              title={compareFull ? roleJobDetailCompareIsFullMax({ compareCap: compareCap }) : roleJobDetailCompare({ choice: compareOn ? "yes" : "no" })}
            >
              <Icon name={compareOn ? "check" : "compare"} size={16} />
            </Button>
            {compareFull && (
              <span id={fullReasonId} className="sr-only">{roleJobDetailCompareIsFullMax({ compareCap: compareCap })}</span>
            )}
          </>
        )}
        {pipeline.control}
        {job && !applied && (
          <>
            <Button className="jd-tailor" aria-expanded={tailorAt != null} aria-haspopup="dialog"
                    onClick={(event) => startTailor(event.currentTarget)}>
              <Icon name="sparkle" size={15} /> {roleJobDetailTailorCv()}
            </Button>
            <a className="ui-btn ui-btn-primary ui-btn-md" href={job.url} target="_blank" rel="noreferrer"
               onClick={applyAndSave} onAuxClick={applyAndSave}>
              {roleJobDetailViewApply()} <Icon name="external" size={15} />
            </a>
          </>
        )}
        {job && <TailorCvPopover job={job} anchor={tailorAt} onClose={() => setTailorAt(null)} />}
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
          <div className="jd-container" key={job.id} inert={turning} data-tabbed={tab ? "" : undefined}>
            <header className="jd-hero">
              {/* Who, at what level, and where: one line over the title. */}
              <div className="jd-hero-line">
                <CompanyChip slug={job.company} />
                <BandBadge band={job.level_band} confidence={job.level_confidence} basis={job.level_basis} />
                {(job.lineage_size ?? 0) > 1 ? (
                  <Badge shape="tag" variant="tint" tone="warning"><Msg of={roleJobDetailPostings} elems={{ lineage_size: job.lineage_size }} /></Badge>
                ) : (
                  job.repost_count > 0 && (
                    <Badge shape="tag" variant="tint" tone="warning"><Msg of={roleJobDetailReposted} elems={{ repost_count: job.repost_count }} /></Badge>
                  )
                )}
                {places.length > 0 && (
                  <div className="job-meta">
                    {places.map((l, i) => (
                      <span key={i} style={{ display: "inline-flex", alignItems: "center", gap: 4 }}>
                        {i === 0 && <Icon name="pin" size={13} />} <Content text={l} />
                      </span>
                    ))}
                  </div>
                )}
              </div>
              <h1 ref={setTitleEl}><Content text={job.title} /></h1>
              {job.company_unfollowed && (
                <p className="jd-unfollowed">{unfollowedSentence(job)}</p>
              )}
            </header>

            {/* A role in the pipeline: its posting and the person's own work
                on it, in two tabs held under the bar once scrolled to. */}
            {tab && (
              <div className="jd-tabs" ref={setTabsEl}>
                <TabBar<PostingTab>
                  className="jd-tabbar"
                  look="words"
                  label={roleJobDetailTabs()}
                  value={tab}
                  onChange={showTab}
                  idPrefix="jd"
                  controls="jd-tab-panel"
                  tabs={[
                    { id: "posting", label: roleJobDetailTabPosting() },
                    { id: "workspace", label: roleJobDetailTabWorkspace() },
                  ]}
                />
              </div>
            )}

            {!onWorkspace && (
              <>
                {(job.lineage_size ?? 0) > 1 && <LineageStack ref={lineageRef} jobId={job.id} />}
                {/* The deck shows direct twins only, and the row counts them: a role
                    with none asks for nothing. */}
                {job.twin_count > 0 && <TwinDeck jobId={job.id} onOpen={onOpen} onCompare={onCompare} />}
                <PlaceSetSection jobId={job.id} onOpen={onOpen} />
              </>
            )}

            <div className="jd-grid">
              <div
                className="jd-main"
                ref={setMainEl}
                {...(tab ? { id: "jd-tab-panel", role: "tabpanel", "aria-labelledby": `jd-tab-${tab}` } : {})}
              >
                {onWorkspace ? pipeline.workspace : (<>
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
                {/* Held under the tabs when there are tabs: its headings
                    measure where they stick once, as they arrive. */}
                <JobDescription
                  key={tab ? "tabbed" : "plain"}
                  sections={job.description_sections}
                  fallback={job.description_text}
                  read={textRead}
                  arrived={textArrived}
                  company={companyName(job.company)}
                  postingUrl={job.url}
                />

                {/* The read ends on the way on: two steps in the order they
                    are done, each a raised row the whole of which is its one
                    control (docs/ui.md, a clickable card). Once applied there
                    is nothing to suggest. */}
                {!applied && (
                  <footer className="jd-end">
                    <div className="jd-next-head">
                      <h2 className="jd-next-kicker">{roleJobDetailNextKicker()}</h2>
                      {!job.is_favorite && <span className="jd-next-note">{roleJobDetailNextSaves()}</span>}
                    </div>
                    <ol className="jd-next-steps">
                      <li className="jd-next" data-next="">
                        <span className="jd-next-mark" aria-hidden="true">1</span>
                        <span className="jd-next-text">
                          <Button variant="link" className="jd-next-title" aria-haspopup="dialog"
                                  onClick={(event) => startTailor(event.currentTarget.closest("li") ?? event.currentTarget)}>
                            {roleJobDetailNextTailorTitle()}
                          </Button>
                          <span className="jd-next-meta">{roleJobDetailNextTailorMeta()}</span>
                        </span>
                        <span className="jd-next-go" aria-hidden="true"><Icon name="arrowRight" size={17} /></span>
                      </li>
                      <li className="jd-next">
                        <span className="jd-next-mark" aria-hidden="true">2</span>
                        <span className="jd-next-text">
                          <a className="jd-next-title" href={job.url} target="_blank" rel="noreferrer"
                             onClick={applyAndSave} onAuxClick={applyAndSave}>
                            {roleJobDetailNextApplyTitle({ company: companyName(job.company) })}
                          </a>
                          {"application_form" in job && job.application_form && (
                            <span className="jd-next-meta">{applyAsk(job.application_form)}</span>
                          )}
                        </span>
                        <span className="jd-next-go" aria-hidden="true"><Icon name="external" size={17} /></span>
                      </li>
                    </ol>
                  </footer>
                )}
                </>)}
              </div>

              <aside className="jd-aside" ref={setAside}>
                {/* The pay panel's small copy, grown by the scroll once the
                    panel has left. The panel is the one a screen reader reads. */}
                {!onWorkspace && (
                  <div className="jd-dock" ref={setDockEl} aria-hidden="true">
                    <div className="jd-dock-in"><JobCompDock job={job} /></div>
                  </div>
                )}

                {/* The Workspace's short lists, beside its writing. */}
                {onWorkspace && <div className="jd-ws-beside" ref={setBeside} />}

                {pipeline.section}

                {/* The Workspace is the person's own work: the column keeps
                    where the role stands, and the posting's facts stay on the
                    posting's tab. */}
                {!onWorkspace && (<>
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
                </>)}
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
    <Cover label={label} asOverlay={asOverlay} besideRail={besideRail} onBack={onBack} bar={bar} className="job-detail" scrollRef={scrollRef}>
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

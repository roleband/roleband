import { useEffect, useState } from "react";
import { Link, useLocation } from "react-router-dom";
import { isNotFound, type ApplicationDetail, type ApplicationInterview, type InterviewWrite, type JobDetail } from "../../api";
import { useJobActions } from "../../context/JobWorkspace";
import { STAGE_LABEL, type StageSlug } from "../../copy/vocabulary";
import { companyName } from "../../format";
import { JobLinkRow } from "../../patterns/jobs/JobLinkRow";
import { postingPlaces } from "../../patterns/jobs/location";
import { AsyncBoundary, Button, CompanyIcon, Content, Icon, Kbd, Menu, MenuGroup, MenuItem, useToast } from "../../ui";
import { errorApplicationNotFound } from "../../copy/gen/errors";
import {
  applicationsCrossingClosed,
  applicationsCrossingDismiss,
  applicationsCrossingPay,
  applicationsCrossingReopened,
  applicationsLinkCopied,
  applicationsLinkCopyFailed,
  applicationsPageBack,
  applicationsPageBar,
  applicationsPageBackBoard,
  applicationsPageCopyLink,
  applicationsPageLoadFailed,
  applicationsPageMore,
  applicationsPageMoreLabel,
  applicationsPageNext,
  applicationsPagePlace,
  applicationsPagePrevious,
  applicationsPageWithdraw,
  applicationsInterviewAdd,
  applicationsReadPosting,
  applicationsStageButton,
  applicationsStageMenuLabel,
} from "../../copy/gen/applications";
import { ActivityFeed } from "./ActivityFeed";
import { ApplicationFacts } from "./ApplicationFacts";
import { NextPanel, NotesBlock } from "./ApplicationPanels";
import { applicationPath, CLOSED_STAGES, daysInStage, placeInColumn } from "./board";
import { crossingKey, latestCrossing, readDismissed, writeDismissed, type Crossing } from "./crossings";
import { InterviewDialog } from "./InterviewDialog";
import { backOf } from "./pageOrigin";
import { StageMenu } from "./StageMenu";
import { useApplicationController } from "./useApplicationController";
import "./applications.css";

type Asking =
  | { kind: "move" }
  | { kind: "add" }
  | { kind: "edit"; interview: ApplicationInterview };

const CROSSING_TEXT: Record<Crossing["kind"], (args: { days: number }) => string> = {
  closed: applicationsCrossingClosed,
  reopened: applicationsCrossingReopened,
  pay: applicationsCrossingPay,
};

/** A typed key belongs to the field it is typed into, and while a dialog is
 *  open the keyboard is the dialog's. */
function pageKey(event: KeyboardEvent): boolean {
  if (event.metaKey || event.ctrlKey || event.altKey) return false;
  if (document.querySelector('[aria-modal="true"]')) return false;
  const target = event.target as HTMLElement | null;
  return !(target?.isContentEditable || target?.closest("input, textarea, select"));
}

/**
 * One application, opened from the pipeline: where it stands, the next
 * thing to do, and what happened. The posting is one link away, in the
 * cover the radar opens it in. S opens the stage menu and I adds an
 * interview.
 */
export function ApplicationPage({ jobId }: { jobId: number }) {
  const { openJob } = useJobActions();
  const { toast } = useToast();
  const ctl = useApplicationController(jobId);
  const { card, detail, activity, posting, board, move } = ctl;
  const [stageButton, setStageButton] = useState<HTMLButtonElement | null>(null);
  const [stageOpen, setStageOpen] = useState(false);
  const [moreButton, setMoreButton] = useState<HTMLButtonElement | null>(null);
  const [moreOpen, setMoreOpen] = useState(false);
  const [asking, setAsking] = useState<Asking | null>(null);
  const [dismissed, setDismissed] = useState(readDismissed);
  const { state: arrived } = useLocation();
  const back = backOf(arrived);
  // One clock per render, so every fact on the page measures from the same instant.
  const now = new Date();

  useEffect(() => {
    if (!card) return;
    const onKey = (event: KeyboardEvent) => {
      if (!pageKey(event)) return;
      const key = event.key.toLowerCase();
      if (key === "s") {
        event.preventDefault();
        setMoreOpen(false);
        setStageOpen(true);
      } else if (key === "i") {
        event.preventDefault();
        setAsking({ kind: "add" });
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [card]);

  if (detail.error && isNotFound(detail.error)) {
    return (
      <main className="main app-main app-page" data-design-system="app">
        <div className="app-page-gone">
          <p>{errorApplicationNotFound()}</p>
          <Link className="ui-btn ui-btn-ghost ui-btn-md ui-btn-strong" to="/pipeline/board">{applicationsPageBackBoard()}</Link>
        </div>
      </main>
    );
  }

  const choose = (stage: StageSlug) => {
    setStageOpen(false);
    if (!card) return;
    if (stage === "interviewing" && card.stage !== "interviewing") setAsking({ kind: "move" });
    else void move(card, stage);
  };

  const submitInterview = (interview: InterviewWrite) => {
    const was = asking;
    setAsking(null);
    if (!card || !was) return;
    if (was.kind === "move") void move(card, "interviewing", interview);
    else if (was.kind === "add") void ctl.addInterview(interview);
    else void ctl.saveInterview(was.interview.id, interview);
  };

  const copyLink = async () => {
    setMoreOpen(false);
    try {
      await navigator.clipboard.writeText(new URL(applicationPath(jobId), window.location.origin).href);
      toast({ key: "applications", text: applicationsLinkCopied() });
    } catch {
      toast({ key: "applications", tone: "error", text: applicationsLinkCopyFailed() });
    }
  };

  const dismiss = (key: string) => {
    const next = new Set(dismissed).add(key);
    writeDismissed(next);
    setDismissed(next);
  };

  return (
    <main className="main app-main app-page" data-design-system="app">
      <AsyncBoundary resource={detail} failed={applicationsPageLoadFailed()} skeleton={<div className="app-page-skeleton" aria-hidden="true" />}>
        {(data: ApplicationDetail) => {
          const shown = card ?? data.application;
          const days = daysInStage(shown, now);
          const place = board.data ? placeInColumn(board.data.applications, jobId, now) : null;
          const job: JobDetail | null = posting.data ?? null;
          const crossing = job ? latestCrossing(job.lifecycle, data.stages_reached) : null;
          const crossingId = crossing ? crossingKey(jobId, crossing) : null;
          const company = companyName(shown.company);
          const city = job ? postingPlaces(job.locations)[0] : undefined;
          const reached = new Map(data.stages_reached.map((step) => [step.stage, step.at] as const));
          const ended = shown.stage === "withdrawn" || (CLOSED_STAGES as readonly string[]).includes(shown.stage);

          return (
            <>
              <nav className="app-page-bar" aria-label={applicationsPageBar()}>
                <Link
                  className="ui-btn ui-btn-ghost ui-btn-sm app-page-back"
                  to={{ pathname: back.pathname, search: back.search }}
                  state={back.state}
                >
                  <Icon name="arrowLeft" size={14} />
                  {applicationsPageBack({ view: back.view })}
                </Link>
                <span className="app-tile-spacer" />
                {place && place.total > 1 && (
                  <>
                    <span className="app-page-place">{applicationsPagePlace({ index: place.index + 1, total: place.total })}</span>
                    {place.previous ? (
                      <Link
                        className="ui-btn ui-btn-icon ui-btn-sm"
                        to={applicationPath(place.previous.job_id)}
                        state={arrived}
                        aria-label={applicationsPagePrevious({ title: place.previous.title })}
                      >
                        <Icon name="arrowUp" size={14} />
                      </Link>
                    ) : <span className="app-page-arrow" aria-hidden="true" />}
                    {place.next ? (
                      <Link
                        className="ui-btn ui-btn-icon ui-btn-sm"
                        to={applicationPath(place.next.job_id)}
                        state={arrived}
                        aria-label={applicationsPageNext({ title: place.next.title })}
                      >
                        <Icon name="arrowDown" size={14} />
                      </Link>
                    ) : <span className="app-page-arrow" aria-hidden="true" />}
                  </>
                )}
                <Button
                  ref={setMoreButton}
                  variant="icon"
                  size="sm"
                  aria-label={applicationsPageMore()}
                  aria-haspopup="dialog"
                  aria-expanded={moreOpen}
                  onClick={() => setMoreOpen((open) => !open)}
                >
                  <Icon name="more" size={16} />
                </Button>
              </nav>

              <header className="app-page-head">
                <CompanyIcon slug={shown.company} display={company} size={32} />
                <div className="app-page-name">
                  <h1><Content text={shown.title} /></h1>
                  <p className="app-page-meta">
                    <span>{company}</span>
                    {city && <span><Content text={city} /></span>}
                  </p>
                </div>
                <Button
                  ref={setStageButton}
                  variant="ghost"
                  className="ui-btn-strong app-stage-button"
                  aria-haspopup="dialog"
                  aria-expanded={stageOpen}
                  aria-keyshortcuts="s"
                  onClick={() => setStageOpen((open) => !open)}
                >
                  {applicationsStageButton({ stage: STAGE_LABEL[shown.stage], days: days ?? 0 })}
                  <Icon name="chevronDown" size={14} />
                </Button>
              </header>

              {crossing && crossingId && !dismissed.has(crossingId) && (
                <div className="app-alert" role="status">
                  <Icon name="info" size={16} />
                  <span className="app-alert-text">{CROSSING_TEXT[crossing.kind]({ days: crossing.days })}</span>
                  <JobLinkRow jobId={jobId} company={shown.company} onOpen={openJob} className="ui-btn ui-btn-link">
                    {applicationsReadPosting()}
                  </JobLinkRow>
                  <Button variant="icon" size="sm" aria-label={applicationsCrossingDismiss()} onClick={() => dismiss(crossingId)}>
                    <Icon name="close" size={14} />
                  </Button>
                </div>
              )}

              <div className="app-page-grid">
                <div className="app-page-main">
                  <NextPanel
                    card={shown}
                    interviews={data.interviews}
                    now={now}
                    onSetNext={ctl.setNextStep}
                    onEditInterview={(interview) => setAsking({ kind: "edit", interview })}
                  />
                  <NotesBlock notes={job?.pursuit?.notes ?? null} onSave={ctl.saveNotes} />
                  <ActivityFeed
                    items={activity.data?.items ?? []}
                    now={now}
                    onAdd={ctl.addComment}
                    onEdit={ctl.editComment}
                    onDelete={ctl.deleteComment}
                  />
                </div>
                <ApplicationFacts
                  card={shown}
                  detail={data}
                  posting={job}
                  now={now}
                  onPriority={(priority) => void ctl.setPriority(priority)}
                  onOpenPosting={openJob}
                  onAddInterview={() => setAsking({ kind: "add" })}
                  onEditInterview={(interview) => setAsking({ kind: "edit", interview })}
                />
              </div>

              <StageMenu
                current={shown.stage}
                label={applicationsStageMenuLabel({ title: shown.title })}
                anchor={stageButton}
                isOpen={stageOpen}
                onClose={() => setStageOpen(false)}
                onMove={choose}
                reached={reached}
              />
              <Menu isOpen={moreOpen} onClose={() => setMoreOpen(false)} anchor={moreButton} label={applicationsPageMoreLabel()}>
                <MenuGroup>
                  <MenuItem
                    shortcut="i"
                    detail={<Kbd>I</Kbd>}
                    onSelect={() => {
                      setMoreOpen(false);
                      setAsking({ kind: "add" });
                    }}
                  >
                    {applicationsInterviewAdd()}
                  </MenuItem>
                  <MenuItem onSelect={() => void copyLink()}>{applicationsPageCopyLink()}</MenuItem>
                  {!ended && (
                    <MenuItem
                      onSelect={() => {
                        setMoreOpen(false);
                        void move(shown, "withdrawn");
                      }}
                    >
                      {applicationsPageWithdraw()}
                    </MenuItem>
                  )}
                </MenuGroup>
              </Menu>
              {asking && (
                <InterviewDialog
                  card={shown}
                  moving={asking.kind === "move"}
                  interview={asking.kind === "edit" ? asking.interview : undefined}
                  onCancel={() => setAsking(null)}
                  onSubmit={submitInterview}
                  onDelete={asking.kind === "edit"
                    ? () => {
                      const id = asking.interview.id;
                      setAsking(null);
                      void ctl.deleteInterview(id);
                    }
                    : undefined}
                />
              )}
            </>
          );
        }}
      </AsyncBoundary>
    </main>
  );
}

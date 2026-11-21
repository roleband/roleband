import { Suspense, lazy, useEffect, useState, type ReactNode } from "react";
import type { ApplicationInterview, InterviewWrite, Job } from "../../api";
import type { StageSlug } from "../../copy/vocabulary";
import { PipelineSection } from "./PipelineSection";
import { PostingStage } from "./PostingStage";
import { usePostingApplication } from "./usePostingApplication";
import { usePostingWorkspace } from "./usePostingWorkspace";

const InterviewDialog = lazy(() => import("./InterviewDialogLazy"));
const PostingWorkspace = lazy(() => import("./PostingWorkspace"));

/** The stages before the person has applied: the employer's page is still
 *  where they apply. */
const BEFORE_APPLYING: ReadonlySet<StageSlug> = new Set(["saved", "researching", "networking"]);

export type PostingTab = "posting" | "workspace";

/** What the posting shows of its role's place in the pipeline. */
export interface PostingPipeline {
  /** The bar's control: the star off the board, the stage on it. */
  control: ReactNode;
  /** The Pipeline section of the side column; null off the board. */
  section: ReactNode;
  /** The person has applied, or the application has ended. */
  applied: boolean;
  /** The tab on screen for a role in the pipeline; null for one outside it,
   *  which has no tabs. */
  tab: PostingTab | null;
  /** The Workspace, the main column's while its tab is on screen. */
  workspace: ReactNode;
}

type Asking = { kind: "add" } | { kind: "edit"; interview: ApplicationInterview };

/** A typed key belongs to the field it is typed into, and while a dialog is
 *  open over the posting the keyboard is the dialog's. The posting itself is
 *  a modal cover when it is opened over a page, so its own dialog does not
 *  count. */
function postingKey(event: KeyboardEvent): boolean {
  if (event.defaultPrevented || event.metaKey || event.ctrlKey || event.altKey) return false;
  const over = Array.from(document.querySelectorAll('[aria-modal="true"]')).some((modal) => !modal.querySelector(".cover-scroll"));
  if (over) return false;
  const target = event.target as HTMLElement | null;
  return !(target?.isContentEditable || target?.closest("input, textarea, select"));
}

/**
 * The pipeline's part of a posting, composed into it by its route: the
 * posting knows nothing of stages, and the pipeline keeps its menu, its moves,
 * its interview form and the Workspace in one place.
 *
 * A role in the pipeline reads in two tabs: the posting, and the Workspace,
 * the person's own work on it. The tab asked for is the posting's unless the
 * address names the Workspace. M opens the stage menu and I adds an interview.
 */
export function usePostingPipeline(
  job: Job | null,
  { showSaved, paintPosting, paintNotes, rereadPosting, onSave, now, column, tab: asked, onTab }: {
    /** Paints the posting's star. */
    showSaved: (on: boolean) => void;
    /** Paints the posting's own copy of its stage. */
    paintPosting: (stage: StageSlug) => void;
    /** Paints the posting's own copy of the notes. */
    paintNotes: (notes: string | null) => void;
    /** Reads the posting again, after a write that failed. */
    rereadPosting: () => void;
    /** Saves a role that is not on the board. */
    onSave: () => void;
    now: Date;
    /** The side column the section sits in, for its history to open across. */
    column: HTMLElement | null;
    /** The tab the address asks for. */
    tab: PostingTab | null;
    onTab: (tab: PostingTab) => void;
  },
): PostingPipeline {
  const application = usePostingApplication(job, { showSaved, paintPosting, rereadPosting });
  const { card, history, detail } = application;
  const tab: PostingTab | null = card ? asked ?? "posting" : null;
  const actions = usePostingWorkspace(application, { showing: tab === "workspace", paintNotes, rereadPosting });
  const [stageOpen, setStageOpen] = useState(false);
  const [asking, setAsking] = useState<Asking | null>(null);

  const onBoard = card != null;
  useEffect(() => {
    if (!onBoard) return;
    const onKey = (event: KeyboardEvent) => {
      if (!postingKey(event)) return;
      const key = event.key.toLowerCase();
      if (key === "m") {
        event.preventDefault();
        setStageOpen(true);
      } else if (key === "i") {
        event.preventDefault();
        setAsking({ kind: "add" });
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onBoard]);

  // The form waits for its save and closes only once it has landed.
  const submitInterview = async (interview: InterviewWrite) => {
    const was = asking;
    if (!was) return false;
    const saved = was.kind === "add"
      ? await actions.addInterview(interview)
      : await actions.saveInterview(was.interview.id, interview);
    if (saved) setAsking(null);
    return saved;
  };

  const workspace = tab === "workspace" && card && job && (
    <Suspense fallback={<div className="jd-workspace-wait" aria-hidden="true" />}>
      {detail ? (
        <PostingWorkspace
          job={job}
          onShowPosting={() => onTab("posting")}
          card={card}
          detail={detail}
          notes={job.pursuit?.notes ?? null}
          activity={actions.activity}
          now={now}
          onSetNext={actions.setNextStep}
          onFinishStep={actions.finishStep}
          onSaveNotes={actions.saveNotes}
          onAddInterview={() => setAsking({ kind: "add" })}
          onEditInterview={(interview) => setAsking({ kind: "edit", interview })}
          onOutcome={actions.setOutcome}
          onEditComment={actions.editComment}
          onDeleteComment={actions.deleteComment}
        />
      ) : (
        <div className="jd-workspace-wait" aria-hidden="true" />
      )}
    </Suspense>
  );

  return {
    control: job ? <PostingStage application={application} onSave={onSave} open={stageOpen} onOpen={setStageOpen} /> : null,
    section: card && (
      <>
        <PipelineSection
          card={card}
          history={history}
          now={now}
          column={column}
          workspace={tab === "workspace"}
          onPriority={(priority) => void actions.setPriority(priority)}
        />
        {asking && (
          <Suspense fallback={null}>
            <InterviewDialog
              card={card}
              moving={false}
              interview={asking.kind === "edit" ? asking.interview : undefined}
              onCancel={() => setAsking(null)}
              onSubmit={submitInterview}
              onDelete={asking.kind === "edit"
                ? () => {
                  const id = asking.interview.id;
                  setAsking(null);
                  void actions.deleteInterview(id);
                }
                : undefined}
            />
          </Suspense>
        )}
      </>
    ),
    applied: card != null && !BEFORE_APPLYING.has(card.stage),
    tab,
    workspace: workspace || null,
  };
}

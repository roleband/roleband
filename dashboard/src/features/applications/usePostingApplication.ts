import { useCallback, useMemo, useRef } from "react";
import { api, isNotFound, type ApplicationCard, type ApplicationDetail, type Job } from "../../api";
import { useJobWorkspace } from "../../context/JobWorkspace";
import { useSaveCommand } from "../../context/useSaveCommand";
import type { StageSlug } from "../../copy/vocabulary";
import { useAsyncResource, useRefetchOn, type AsyncResource } from "../../hooks/useAsyncResource";
import { useToast } from "../../ui";
import {
  applicationsMoveUndo,
  applicationsRemoveFailed,
  applicationsRemoved,
  applicationsUndoFailed,
} from "../../copy/gen/applications";
import { movedCard } from "./board";
import { useRoleWrite, type RoleWrite } from "./useRoleWrite";
import { useStageMove, type PursuitWrite } from "./useStageMove";

/** Whether the board shows the role, from what the posting knows: starred, or
 *  pursued past Considering. A role pursued in Considering without its star is
 *  not on the board, and so not in the pipeline here either. */
function onBoardByPosting(job: Pick<Job, "is_favorite" | "pursuit">): boolean {
  return job.is_favorite || (job.pursuit != null && job.pursuit.stage !== "saved");
}

/** The card the board would draw, built from the posting while the
 *  application itself is still on its way. */
function provisionalCard(job: Job): ApplicationCard {
  const pursuit = job.pursuit;
  return {
    job_id: job.id,
    pursuit_id: pursuit?.id ?? null,
    stage: pursuit?.stage ?? "saved",
    priority: pursuit?.priority ?? 3,
    // The posting's read does not say whether one was chosen; the board's
    // read, which replaces this card, does.
    priority_set: false,
    starred: job.is_favorite,
    company: job.company,
    title: job.title,
    level_band: job.level_band,
    posting_status: job.status,
    next_action: pursuit?.next_action ?? null,
    next_action_due: pursuit?.next_action_due ?? null,
    // The posting's read names the soonest step only; the application's read
    // that replaces this card lists them all.
    steps: [],
    next_interview: null,
    awaiting_outcome: null,
    comment_count: 0,
    stage_since: null,
    last_activity_at: null,
    ended_at_stage: null,
  };
}

export interface PostingApplication {
  /** The board shows the role. */
  onBoard: boolean;
  /** The application as the board draws it; null when the role is not on it. */
  card: ApplicationCard | null;
  /** When the application last entered each stage. */
  reached: ReadonlyMap<StageSlug, string>;
  /** The application's history: its stages in the order reached and its
   *  interviews. Empty until the application has loaded. */
  history: Pick<ApplicationDetail, "stages_reached" | "interviews">;
  /** A stage move, the pipeline's own: it paints, writes, offers Undo. */
  move: ReturnType<typeof useStageMove>;
  /** Takes a role in Considering out of the pipeline, with Undo. */
  remove: () => void;
  /** The application as read, once it has loaded; null before and off the board. */
  detail: ApplicationDetail | null;
  /** The read of `detail`, for a screen that says it is loading or failed and
   *  offers Try again. A failed read again after a write is not an error
   *  here: the application last read stays. */
  load: Pick<AsyncResource<ApplicationDetail>, "data" | "error" | "loading" | "retry">;
  /** Paints the application read here, ahead of the write that changes it. */
  paintDetail: (change: (current: ApplicationDetail) => ApplicationDetail) => void;
  /** Reads the application again. */
  reread: () => Promise<unknown>;
  /** Reads the application again if the role is still the one open: what a
   *  change made on an earlier role asks for once it has failed. */
  rereadRole: (jobId: number) => Promise<unknown>;
  /** The pursuit write, through the save command. */
  write: PursuitWrite;
  /** Any other write to the role's pursuit (a next step), through the save
   *  command, so every reader of the role follows. */
  writeRole: RoleWrite;
}

/**
 * The posting's view of its application: the same application the pipeline
 * reads (`GET /api/applications/{id}`), so its stage, how long it has been
 * there, the dates each stage was reached and the next interview are the
 * board's. Read only while the role is on the board.
 *
 * Every write goes through the save command, so the board and an application
 * page this posting covers re-read it, and so does this: the application's
 * read has this one owner, the announcement of a write that landed. The posting's own star and pursuit are
 * kept in step through `showSaved` and `paintPosting`: the card falls back to
 * them while the application loads, and after it leaves the board.
 */
export function usePostingApplication(
  job: Job | null,
  { showSaved, paintPosting, rereadPosting }: {
    showSaved: (on: boolean) => void;
    paintPosting: (stage: StageSlug) => void;
    /** Reads the posting again, its stage and star as the server holds them. */
    rereadPosting: () => void;
  },
): PostingApplication {
  const { favVersion } = useJobWorkspace();
  const saveRole = useSaveCommand();
  const { toast } = useToast();
  const jobId = job?.id ?? null;
  // A write made on one role can settle after another is open: what it paints
  // and reads then is the role it was made on, or nothing.
  const openJob = useRef(jobId);
  openJob.current = jobId;
  const wanted = job != null && onBoardByPosting(job);

  const detail = useAsyncResource<ApplicationDetail | null>(
    (signal) =>
      jobId == null || !wanted
        ? Promise.resolve(null)
        : api.application(jobId, signal).catch((error: unknown) => {
          if (isNotFound(error)) return null;
          throw error;
        }),
    [jobId, wanted],
  );
  const { mutate, refresh } = detail;
  const reread = useCallback(() => refresh({ preserveData: true }), [refresh]);
  const rereadRole = useCallback(
    (target: number) => (openJob.current === target ? reread() : Promise.resolve()),
    [reread],
  );
  // A star or a stage set on any other surface changes the application.
  useRefetchOn(favVersion, reread);

  const loaded = detail.data && detail.data.application.job_id === jobId ? detail.data : null;
  const card = useMemo(() => {
    if (!job) return null;
    const base = loaded?.application ?? provisionalCard(job);
    // The star is the posting's: it paints first, the application follows.
    return { ...base, starred: job.is_favorite };
  }, [job, loaded]);
  const onBoard = card != null && (card.starred || card.stage !== "saved");

  const paint = useCallback(
    (target: number, stage: StageSlug) => {
      if (openJob.current !== target) return;
      const now = new Date().toISOString();
      mutate((current) => current && {
        ...current,
        application: movedCard(current.application, stage, now),
      });
      paintPosting(stage);
    },
    [mutate, paintPosting],
  );

  const show = useCallback(
    (target: number, saved: boolean) => {
      if (openJob.current === target) showSaved(saved);
    },
    [showSaved],
  );
  // The posting painted the stage it asked for, and whether the role is on the
  // board follows that stage: a failed write reads back the one the server
  // kept, or a role left unstarred would drop off the posting.
  const failed = useCallback(
    (target: number) => {
      if (openJob.current === target) rereadPosting();
    },
    [rereadPosting],
  );
  const { writeRole, write } = useRoleWrite({ show, failed });
  const move = useStageMove({ paint, refresh: reread, write });

  const title = card?.title ?? "";
  const remove = useCallback(() => {
    if (jobId == null) return;
    saveRole({ jobId, was: true, next: false, show: (on) => show(jobId, on), send: () => api.setFavorite(jobId, false) })
      .then(({ outcome }) => {
        if (outcome !== "saved") return;
        toast({
          key: "job",
          text: applicationsRemoved({ title }),
          action: {
            label: applicationsMoveUndo(),
            onClick: () => {
              saveRole({ jobId, was: false, next: true, show: (on) => show(jobId, on), send: () => api.setFavorite(jobId, true) })
                .catch(() => toast({ key: "job", tone: "error", text: applicationsUndoFailed({ title }) }));
            },
          },
        });
      })
      .catch(() => toast({ key: "job", tone: "error", text: applicationsRemoveFailed({ title }) }));
  }, [jobId, saveRole, show, toast, title]);

  const reached = useMemo(
    () => new Map((loaded?.stages_reached ?? []).map((step) => [step.stage, step.at] as const)),
    [loaded],
  );

  const history = useMemo(
    () => ({ stages_reached: loaded?.stages_reached ?? [], interviews: loaded?.interviews ?? [] }),
    [loaded],
  );

  const paintDetail = useCallback(
    (change: (current: ApplicationDetail) => ApplicationDetail) => mutate((current) => current && change(current)),
    [mutate],
  );

  return {
    onBoard,
    card: onBoard ? card : null,
    reached,
    history,
    move,
    remove,
    detail: onBoard ? loaded : null,
    load: { data: onBoard ? loaded : null, error: detail.error, loading: detail.loading, retry: detail.retry },
    paintDetail,
    reread,
    rereadRole,
    write,
    writeRole,
  };
}

import { useCallback, useMemo } from "react";
import { api, isNotFound, type ApplicationCard, type ApplicationDetail, type Job } from "../../api";
import { useJobWorkspace } from "../../context/JobWorkspace";
import { useSaveCommand } from "../../context/useSaveCommand";
import type { StageSlug } from "../../copy/vocabulary";
import { useAsyncResource, useRefetchOn } from "../../hooks/useAsyncResource";
import { useToast } from "../../ui";
import {
  applicationsMoveUndo,
  applicationsRemoveFailed,
  applicationsRemoved,
  applicationsUndoFailed,
} from "../../copy/gen/applications";
import { movedCard } from "./board";
import { useStageMove, type PursuitWrite } from "./useStageMove";

/** Whether the board shows the role, from what the posting knows: starred, or
 *  pursued past Considering. A role pursued in Considering without its star is
 *  not on the board, and so not in the pipeline here either. */
export function onBoardByPosting(job: Pick<Job, "is_favorite" | "pursuit">): boolean {
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
    starred: job.is_favorite,
    company: job.company,
    title: job.title,
    level_band: job.level_band,
    posting_status: job.status,
    next_action: pursuit?.next_action ?? null,
    next_action_due: pursuit?.next_action_due ?? null,
    next_interview: null,
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
}

/**
 * The posting's view of its application: the same application the pipeline
 * reads (`GET /api/applications/{id}`), so its stage, how long it has been
 * there, the dates each stage was reached and the next interview are the
 * board's. Read only while the role is on the board.
 *
 * Every write goes through the save command, so the board and an application
 * page this posting covers re-read it. The posting's own star and pursuit are
 * kept in step through `showSaved` and `paintPosting`: the card falls back to
 * them while the application loads, and after it leaves the board.
 */
export function usePostingApplication(
  job: Job | null,
  { showSaved, paintPosting }: {
    showSaved: (on: boolean) => void;
    paintPosting: (stage: StageSlug) => void;
  },
): PostingApplication {
  const { favVersion } = useJobWorkspace();
  const saveRole = useSaveCommand();
  const { toast } = useToast();
  const jobId = job?.id ?? null;
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
    (_jobId: number, stage: StageSlug) => {
      const now = new Date().toISOString();
      mutate((current) => current && {
        ...current,
        application: movedCard(current.application, stage, now),
      });
      paintPosting(stage);
    },
    [mutate, paintPosting],
  );

  const write = useCallback<PursuitWrite>(
    async (target, update) => {
      const { outcome } = await saveRole({
        jobId: target.job_id,
        was: target.starred,
        next: true,
        show: showSaved,
        send: () => api.setPursuit(target.job_id, update),
      });
      if (outcome !== "saved") throw new Error("The pursuit write failed behind a newer write for the role.");
    },
    [saveRole, showSaved],
  );
  const move = useStageMove({ paint, refresh: reread, write });

  const title = card?.title ?? "";
  const remove = useCallback(() => {
    if (jobId == null) return;
    saveRole({ jobId, was: true, next: false, show: showSaved, send: () => api.setFavorite(jobId, false) })
      .then(({ outcome }) => {
        if (outcome !== "saved") return;
        toast({
          key: "job",
          text: applicationsRemoved({ title }),
          action: {
            label: applicationsMoveUndo(),
            onClick: () => {
              saveRole({ jobId, was: false, next: true, show: showSaved, send: () => api.setFavorite(jobId, true) })
                .catch(() => toast({ key: "job", tone: "error", text: applicationsUndoFailed({ title }) }));
            },
          },
        });
      })
      .catch(() => toast({ key: "job", tone: "error", text: applicationsRemoveFailed({ title }) }));
  }, [jobId, saveRole, showSaved, toast, title]);

  const reached = useMemo(
    () => new Map((loaded?.stages_reached ?? []).map((step) => [step.stage, step.at] as const)),
    [loaded],
  );

  const history = useMemo(
    () => ({ stages_reached: loaded?.stages_reached ?? [], interviews: loaded?.interviews ?? [] }),
    [loaded],
  );

  return { onBoard, card: onBoard ? card : null, reached, history, move, remove };
}

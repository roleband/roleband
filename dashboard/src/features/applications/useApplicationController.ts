import { useCallback } from "react";
import {
  api,
  type ApplicationBoard,
  type ApplicationCard,
  type ApplicationDetail,
  type InterviewWrite,
  type JobDetail,
} from "../../api";
import { useJobWorkspace } from "../../context/JobWorkspace";
import type { StageSlug } from "../../copy/vocabulary";
import { useAsyncResource, useRefetchOn } from "../../hooks/useAsyncResource";
import { useToast } from "../../ui";
import {
  applicationsChangeFailed,
  applicationsCommentDeleteFailed,
  applicationsCommentFailed,
  applicationsInterviewDeleteFailed,
  applicationsInterviewFailed,
} from "../../copy/gen/applications";
import { usePursuitWrite, useStageMove } from "./useStageMove";

type PursuitUpdate = Parameters<typeof api.setPursuit>[1];

/**
 * One application's page: the application, its feed, the posting it
 * applies to, and the board (for its place in its column). Every write
 * paints at once where it can, and re-reads what it changed; a failure
 * says so and re-reads, so the page never shows what the server refused.
 */
export function useApplicationController(jobId: number) {
  const { favVersion } = useJobWorkspace();
  const { toast } = useToast();
  const write = usePursuitWrite();

  const detail = useAsyncResource<ApplicationDetail>((signal) => api.application(jobId, signal), [jobId]);
  const activity = useAsyncResource((signal) => api.activity(jobId, signal), [jobId]);
  const posting = useAsyncResource<JobDetail>((signal) => api.job(jobId, signal), [jobId]);
  const board = useAsyncResource<ApplicationBoard>((signal) => api.applications(signal), []);
  const { mutate: mutateDetail, refresh: refreshDetail } = detail;
  const { refresh: refreshActivity } = activity;
  const { mutate: mutatePosting, refresh: refreshPosting } = posting;
  const { refresh: refreshBoard } = board;

  const reread = useCallback(
    async () => {
      await Promise.all([
        refreshDetail({ preserveData: true }),
        refreshActivity({ preserveData: true }),
        refreshBoard({ preserveData: true }),
      ]);
    },
    [refreshDetail, refreshActivity, refreshBoard],
  );
  // A star or a stage set on any other surface changes the application.
  useRefetchOn(favVersion, reread);

  const paint = useCallback(
    (change: Partial<ApplicationCard>) =>
      mutateDetail((current) => current && { ...current, application: { ...current.application, ...change } }),
    [mutateDetail],
  );
  const paintStage = useCallback(
    (_jobId: number, stage: StageSlug) => {
      const now = new Date().toISOString();
      paint({ stage, stage_since: now, last_activity_at: now });
    },
    [paint],
  );
  const move = useStageMove({ paint: paintStage, refresh: reread });

  const card = detail.data?.application ?? null;

  /** One pursuit write: paint, send, re-read. True when it saved. */
  const update = useCallback(
    async (change: PursuitUpdate, painted: Partial<ApplicationCard>): Promise<boolean> => {
      if (!card) return false;
      paint(painted);
      try {
        await write(card, change);
      } catch {
        toast({ key: "applications", tone: "error", text: applicationsChangeFailed({ title: card.title }) });
        await reread();
        return false;
      }
      void reread();
      return true;
    },
    [card, paint, write, toast, reread],
  );

  const setPriority = useCallback((priority: number) => update({ priority }, { priority }), [update]);

  const setNextStep = useCallback(
    (text: string | null, due: string | null) =>
      update({ next_action: text, next_action_due: due }, { next_action: text, next_action_due: due }),
    [update],
  );

  /** The notes live on the pursuit, which the posting's own read carries. */
  const saveNotes = useCallback(
    async (notes: string): Promise<boolean> => {
      if (!card) return false;
      const value = notes.trim() ? notes : null;
      mutatePosting((current) => current && current.pursuit
        ? { ...current, pursuit: { ...current.pursuit, notes: value } }
        : current);
      try {
        await write(card, { notes: value });
      } catch {
        toast({ key: "applications", tone: "error", text: applicationsChangeFailed({ title: card.title }) });
        await refreshPosting({ preserveData: true });
        return false;
      }
      void refreshPosting({ preserveData: true });
      void reread();
      return true;
    },
    [card, mutatePosting, write, toast, refreshPosting, reread],
  );

  /** A comment write and the re-read after it. True when it saved. */
  const commentWrite = useCallback(
    async (send: () => Promise<unknown>, failed: string): Promise<boolean> => {
      try {
        await send();
      } catch {
        toast({ key: "applications", tone: "error", text: failed });
        return false;
      }
      void reread();
      return true;
    },
    [toast, reread],
  );
  const addComment = useCallback(
    (body: string) => commentWrite(() => api.addComment(jobId, body), applicationsCommentFailed()),
    [commentWrite, jobId],
  );
  const editComment = useCallback(
    (id: number, body: string) => commentWrite(() => api.editComment(jobId, id, body), applicationsCommentFailed()),
    [commentWrite, jobId],
  );
  const deleteComment = useCallback(
    (id: number) => commentWrite(() => api.deleteComment(jobId, id), applicationsCommentDeleteFailed()),
    [commentWrite, jobId],
  );

  const interviewWrite = useCallback(
    (send: () => Promise<unknown>) => commentWrite(send, applicationsInterviewFailed()),
    [commentWrite],
  );
  const addInterview = useCallback(
    (interview: InterviewWrite) => interviewWrite(() => api.addInterview(jobId, interview)),
    [interviewWrite, jobId],
  );
  const saveInterview = useCallback(
    (id: number, interview: InterviewWrite) => interviewWrite(() => api.updateInterview(jobId, id, interview)),
    [interviewWrite, jobId],
  );
  const deleteInterview = useCallback(
    (id: number) => commentWrite(() => api.deleteInterview(jobId, id), applicationsInterviewDeleteFailed()),
    [commentWrite, jobId],
  );

  return {
    card,
    detail,
    activity,
    posting,
    board,
    move,
    setPriority,
    setNextStep,
    saveNotes,
    addComment,
    editComment,
    deleteComment,
    addInterview,
    saveInterview,
    deleteInterview,
  };
}

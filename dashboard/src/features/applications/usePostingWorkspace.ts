import { useCallback } from "react";
import { api, type ActivityItem, type ApplicationDetail, type ApplicationInterview, type InterviewWrite } from "../../api";
import { useAsyncResource } from "../../hooks/useAsyncResource";
import { useToast } from "../../ui";
import {
  applicationsChangeFailed,
  applicationsCommentDeleteFailed,
  applicationsCommentFailed,
  applicationsInterviewDeleteFailed,
  applicationsMoveUndo,
  applicationsUpnextDone,
  applicationsUpnextOutcomeSet,
  applicationsUpnextUndoFailed,
} from "../../copy/gen/applications";
import { OUTCOME_LABEL } from "./interviewWords";
import type { PostingApplication } from "./usePostingApplication";

type PursuitUpdate = Parameters<typeof api.setPursuit>[1];

export interface PostingWorkspaceActions {
  /** The application's feed; read only while the Workspace shows. */
  activity: readonly ActivityItem[];
  setPriority: (priority: number) => Promise<boolean>;
  setNextStep: (text: string | null, due: string | null) => Promise<boolean>;
  finishStep: () => void;
  setOutcome: (interview: ApplicationInterview, outcome: NonNullable<ApplicationInterview["outcome"]>) => void;
  saveNotes: (notes: string) => Promise<boolean>;
  editComment: (id: number, body: string) => Promise<boolean>;
  deleteComment: (id: number) => Promise<boolean>;
  addInterview: (interview: InterviewWrite) => Promise<boolean>;
  saveInterview: (id: number, interview: InterviewWrite) => Promise<boolean>;
  deleteInterview: (id: number) => Promise<boolean>;
}

/**
 * The writes of a role's Workspace, on the posting's own read of its
 * application. Every write paints at once where it can and reads again what
 * it changed; a failure says so and reads again, so the posting never shows
 * what the server refused. Pursuit writes go through the save command, so
 * the board and every other reader of the role follow.
 */
export function usePostingWorkspace(
  application: PostingApplication,
  { showing, paintNotes, rereadPosting }: {
    /** The Workspace is on screen, so its feed is read. */
    showing: boolean;
    /** Paints the posting's own copy of the notes. */
    paintNotes: (notes: string | null) => void;
    rereadPosting: () => void;
  },
): PostingWorkspaceActions {
  const { toast } = useToast();
  const { card, paintDetail, reread: rereadApplication, write } = application;
  const jobId = card?.job_id ?? null;
  const feed = useAsyncResource(
    (signal) => (jobId != null && showing ? api.activity(jobId, signal) : Promise.resolve(null)),
    [jobId, showing],
  );
  const { refresh: refreshFeed } = feed;

  const reread = useCallback(
    async () => {
      await Promise.all([rereadApplication(), refreshFeed({ preserveData: true })]);
    },
    [rereadApplication, refreshFeed],
  );

  /** One pursuit write: paint, send, read again. True when it saved. */
  const update = useCallback(
    async (change: PursuitUpdate, painted: Partial<ApplicationDetail["application"]>): Promise<boolean> => {
      if (!card) return false;
      paintDetail((current) => ({ ...current, application: { ...current.application, ...painted } }));
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
    [card, paintDetail, write, toast, reread],
  );

  /** A priority the person picks is a chosen one, whatever its number. */
  const setPriority = useCallback(
    (priority: number) => update({ priority }, { priority, priority_set: true }),
    [update],
  );

  const setNextStep = useCallback(
    (text: string | null, due: string | null) =>
      update({ next_action: text, next_action_due: due }, { next_action: text, next_action_due: due }),
    [update],
  );

  /** A change made in one click: it paints at once, and its toast takes it
   *  back. A failure reads again rather than restoring a remembered copy. */
  const quickChange = useCallback(
    async ({ painted, send, undo, text }: {
      painted: (current: ApplicationDetail) => ApplicationDetail;
      send: () => Promise<unknown>;
      undo: () => Promise<unknown>;
      text: string;
    }) => {
      if (!card) return;
      const title = card.title;
      paintDetail(painted);
      try {
        await send();
      } catch {
        toast({ key: "applications", tone: "error", text: applicationsChangeFailed({ title }) });
        await reread();
        return;
      }
      void reread();
      toast({
        key: "applications",
        text,
        action: {
          label: applicationsMoveUndo(),
          onClick: () => {
            void undo()
              .catch(() => toast({ key: "applications", tone: "error", text: applicationsUpnextUndoFailed({ title }) }))
              .finally(() => void reread());
          },
        },
      });
    },
    [card, paintDetail, toast, reread],
  );

  /** The next step is done: it is cleared, and its toast puts it back. */
  const finishStep = useCallback(() => {
    if (!card?.next_action) return;
    const { next_action: step, next_action_due: due } = card;
    void quickChange({
      painted: (current) => ({ ...current, application: { ...current.application, next_action: null, next_action_due: null } }),
      send: () => write(card, { next_action: null, next_action_due: null }),
      undo: () => write(card, { next_action: step, next_action_due: due }),
      text: applicationsUpnextDone({ step }),
    });
  }, [card, quickChange, write]);

  /** How a round went, in one click; its toast takes it back. */
  const setOutcome = useCallback(
    (interview: ApplicationInterview, outcome: NonNullable<ApplicationInterview["outcome"]>) => {
      if (jobId == null) return;
      const was = interview.outcome;
      void quickChange({
        painted: (current) => ({
          ...current,
          interviews: current.interviews.map((one) => (one.id === interview.id ? { ...one, outcome } : one)),
        }),
        send: () => api.updateInterview(jobId, interview.id, { outcome }),
        undo: () => api.updateInterview(jobId, interview.id, { outcome: was }),
        text: applicationsUpnextOutcomeSet({ label: interview.label, outcome: OUTCOME_LABEL[outcome]() }),
      });
    },
    [jobId, quickChange],
  );

  /** The notes live on the pursuit, which the posting's own read carries. */
  const saveNotes = useCallback(
    async (notes: string): Promise<boolean> => {
      if (!card) return false;
      const value = notes.trim() ? notes : null;
      paintNotes(value);
      try {
        await write(card, { notes: value });
      } catch {
        toast({ key: "applications", tone: "error", text: applicationsChangeFailed({ title: card.title }) });
        rereadPosting();
        return false;
      }
      rereadPosting();
      void reread();
      return true;
    },
    [card, paintNotes, write, toast, rereadPosting, reread],
  );

  /** A comment or interview write and the read after it. True when it
   *  saved. An interview's form says a failure itself, so it is not told. */
  const send = useCallback(
    async (call: () => Promise<unknown>, failed: string | null): Promise<boolean> => {
      try {
        await call();
      } catch {
        if (failed) toast({ key: "applications", tone: "error", text: failed });
        return false;
      }
      void reread();
      return true;
    },
    [toast, reread],
  );
  const editComment = useCallback(
    (id: number, body: string) => (jobId == null ? Promise.resolve(false) : send(() => api.editComment(jobId, id, body), applicationsCommentFailed())),
    [send, jobId],
  );
  const deleteComment = useCallback(
    (id: number) => (jobId == null ? Promise.resolve(false) : send(() => api.deleteComment(jobId, id), applicationsCommentDeleteFailed())),
    [send, jobId],
  );
  const addInterview = useCallback(
    (interview: InterviewWrite) => (jobId == null ? Promise.resolve(false) : send(() => api.addInterview(jobId, interview), null)),
    [send, jobId],
  );
  const saveInterview = useCallback(
    (id: number, interview: InterviewWrite) => (jobId == null ? Promise.resolve(false) : send(() => api.updateInterview(jobId, id, interview), null)),
    [send, jobId],
  );
  const deleteInterview = useCallback(
    (id: number) => (jobId == null ? Promise.resolve(false) : send(() => api.deleteInterview(jobId, id), applicationsInterviewDeleteFailed())),
    [send, jobId],
  );

  return {
    activity: feed.data?.items ?? [],
    setPriority,
    setNextStep,
    finishStep,
    setOutcome,
    saveNotes,
    editComment,
    deleteComment,
    addInterview,
    saveInterview,
    deleteInterview,
  };
}

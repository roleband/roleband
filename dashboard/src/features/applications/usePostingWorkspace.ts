import { useCallback, useRef } from "react";
import { api, type ActivityItem, type ApplicationDetail, type ApplicationInterview, type ApplicationStep, type InterviewWrite } from "../../api";
import { useJobWorkspace } from "../../context/JobWorkspace";
import { useAsyncResource, useRefetchOn } from "../../hooks/useAsyncResource";
import { useToast } from "../../ui";
import {
  applicationsCommentDeleteFailed,
  applicationsCommentFailed,
  applicationsInterviewDeleteFailed,
  applicationsUpnextDone,
  applicationsUpnextOutcomeSet,
} from "../../copy/gen/applications";
import { withStep, withoutStep } from "./board";
import { OUTCOME_LABEL } from "./interviewWords";
import type { PostingApplication } from "./usePostingApplication";
import { useQuickChange } from "./useQuickChange";

const NO_ACTIVITY: readonly ActivityItem[] = [];

export interface PostingWorkspaceActions {
  /** The application's feed; read only while the Workspace shows. */
  activity: readonly ActivityItem[];
  setPriority: (priority: number) => Promise<boolean>;
  addStep: (text: string, due: string | null) => Promise<boolean>;
  editStep: (step: ApplicationStep, text: string, due: string | null) => Promise<boolean>;
  finishStep: (step: ApplicationStep) => void;
  removeStep: (step: ApplicationStep) => Promise<boolean>;
  setOutcome: (interview: ApplicationInterview, outcome: NonNullable<ApplicationInterview["outcome"]>) => void;
  saveNotes: (notes: string) => Promise<boolean>;
  addComment: (body: string) => Promise<boolean>;
  editComment: (id: number, body: string) => Promise<boolean>;
  deleteComment: (id: number) => Promise<boolean>;
  addInterview: (interview: InterviewWrite) => Promise<boolean>;
  saveInterview: (id: number, interview: InterviewWrite) => Promise<boolean>;
  deleteInterview: (id: number) => Promise<boolean>;
}

/**
 * The writes of a role's Workspace, on the posting's own read of its
 * application. Every write paints at once where it can; a failure says so and
 * reads again, so the posting never shows what the server refused. Pursuit
 * writes (steps, priority, notes, an interview's outcome) and the comments
 * and interviews beside them go through the save command, whose announcement
 * makes the application and the feed read again, once each, with the board
 * and every other reader of the role.
 */
export function usePostingWorkspace(
  application: PostingApplication,
  { showing, paintNotes }: {
    /** The Workspace is on screen, so its feed is read. */
    showing: boolean;
    /** Paints the posting's own copy of the notes. */
    paintNotes: (notes: string | null) => void;
  },
): PostingWorkspaceActions {
  const { toast } = useToast();
  const { favVersion } = useJobWorkspace();
  const { card, paintDetail, rereadRole, writeRole } = application;
  const jobId = card?.job_id ?? null;
  const openJob = useRef(jobId);
  openJob.current = jobId;

  // Keyed on the role alone: showing the Workspace again keeps the answer it
  // had while the feed reads once more.
  const feed = useAsyncResource(
    (signal) => (jobId != null && showing ? api.activity(jobId, signal) : Promise.resolve(null)),
    [jobId],
  );
  const { refresh: refreshFeed } = feed;
  const readFeed = useCallback(
    () => (showing ? refreshFeed({ preserveData: true }) : Promise.resolve()),
    [showing, refreshFeed],
  );
  // The feed's owners: the Workspace coming on screen, and a write that landed.
  useRefetchOn(showing, readFeed);
  useRefetchOn(favVersion, readFeed);

  /** The application and the feed of `target`, if it is still the open role. */
  const readBoth = useCallback(
    async (target: number) => {
      if (openJob.current !== target) return;
      await Promise.all([rereadRole(target), readFeed()]);
    },
    [rereadRole, readFeed],
  );
  const change = useQuickChange(readBoth);

  const paintApplication = useCallback(
    (paint: (current: ApplicationDetail["application"]) => Partial<ApplicationDetail["application"]>) =>
      paintDetail((current) => ({ ...current, application: { ...current.application, ...paint(current.application) } })),
    [paintDetail],
  );

  /** One pursuit write through the role's save command: paint, send. True
   *  when it saved; a failure says so and reads again. */
  const stepWrite = useCallback(
    async (send: () => Promise<unknown>, paint?: () => void): Promise<boolean> => {
      if (!card) return false;
      return change({ jobId: card.job_id, title: card.title, paint, send: () => writeRole(card, send) });
    },
    [card, change, writeRole],
  );

  /** A priority the person picks is a chosen one, whatever its number. */
  const setPriority = useCallback(
    (priority: number) =>
      jobId == null
        ? Promise.resolve(false)
        : stepWrite(
          () => api.setPursuit(jobId, { priority }),
          () => paintApplication(() => ({ priority, priority_set: true })),
        ),
    [jobId, stepWrite, paintApplication],
  );

  const addStep = useCallback(
    (text: string, due: string | null) => (jobId == null ? Promise.resolve(false) : stepWrite(() => api.addStep(jobId, { text, due }))),
    [jobId, stepWrite],
  );

  /** A changed step is painted at once, in its place in the order. */
  const editStep = useCallback(
    (step: ApplicationStep, text: string, due: string | null) => {
      if (jobId == null) return Promise.resolve(false);
      return stepWrite(
        () => api.updateStep(jobId, step.id, { text, due }),
        () => paintApplication((current) => withStep(current, { ...step, text, due })),
      );
    },
    [jobId, stepWrite, paintApplication],
  );

  const removeStep = useCallback(
    (step: ApplicationStep) => {
      if (jobId == null) return Promise.resolve(false);
      return stepWrite(
        () => api.deleteStep(jobId, step.id),
        () => paintApplication((current) => withoutStep(current, step.id)),
      );
    },
    [jobId, stepWrite, paintApplication],
  );

  /** A step is done: it leaves the list, and its toast opens it again. */
  const finishStep = useCallback((step: ApplicationStep) => {
    if (!card) return;
    void change({
      jobId: card.job_id,
      title: card.title,
      paint: () => paintApplication((current) => withoutStep(current, step.id)),
      send: () => writeRole(card, () => api.updateStep(card.job_id, step.id, { done: true })),
      undo: () => writeRole(card, () => api.updateStep(card.job_id, step.id, { done: false })),
      text: applicationsUpnextDone({ step: step.text }),
    });
  }, [card, change, writeRole, paintApplication]);

  /** How a round went, in one click; its toast takes it back. */
  const setOutcome = useCallback(
    (interview: ApplicationInterview, outcome: NonNullable<ApplicationInterview["outcome"]>) => {
      if (!card) return;
      const was = interview.outcome;
      void change({
        jobId: card.job_id,
        title: card.title,
        paint: () => paintDetail((current) => ({
          ...current,
          interviews: current.interviews.map((one) => (one.id === interview.id ? { ...one, outcome } : one)),
        })),
        send: () => writeRole(card, () => api.updateInterview(card.job_id, interview.id, { outcome })),
        undo: () => writeRole(card, () => api.updateInterview(card.job_id, interview.id, { outcome: was })),
        text: applicationsUpnextOutcomeSet({ label: interview.label, outcome: OUTCOME_LABEL[outcome]() }),
      });
    },
    [card, change, writeRole, paintDetail],
  );

  /** The notes live on the pursuit, which the posting's own read carries. */
  const saveNotes = useCallback(
    (notes: string): Promise<boolean> => {
      if (!card) return Promise.resolve(false);
      const value = notes.trim() ? notes : null;
      return stepWrite(() => api.setPursuit(card.job_id, { notes: value }), () => paintNotes(value));
    },
    [card, stepWrite, paintNotes],
  );

  /** A comment or interview write, in order with the role's others; its
   *  announcement reads the role again everywhere it shows. True when it
   *  saved. An interview's form says a failure itself, so it is not told. */
  const send = useCallback(
    async (call: (jobId: number) => Promise<unknown>, failed: string | null): Promise<boolean> => {
      if (!card) return false;
      try {
        await writeRole(card, () => call(card.job_id));
      } catch {
        if (failed) toast({ key: "applications", tone: "error", text: failed });
        return false;
      }
      return true;
    },
    [card, writeRole, toast],
  );
  const addComment = useCallback(
    (body: string) => send((job) => api.addComment(job, body), applicationsCommentFailed()),
    [send],
  );
  const editComment = useCallback(
    (id: number, body: string) => send((job) => api.editComment(job, id, body), applicationsCommentFailed()),
    [send],
  );
  const deleteComment = useCallback(
    (id: number) => send((job) => api.deleteComment(job, id), applicationsCommentDeleteFailed()),
    [send],
  );
  const addInterview = useCallback(
    (interview: InterviewWrite) => send((job) => api.addInterview(job, interview), null),
    [send],
  );
  const saveInterview = useCallback(
    (id: number, interview: InterviewWrite) => send((job) => api.updateInterview(job, id, interview), null),
    [send],
  );
  const deleteInterview = useCallback(
    (id: number) => send((job) => api.deleteInterview(job, id), applicationsInterviewDeleteFailed()),
    [send],
  );

  return {
    activity: feed.data?.items ?? NO_ACTIVITY,
    setPriority,
    addStep,
    editStep,
    finishStep,
    removeStep,
    setOutcome,
    saveNotes,
    addComment,
    editComment,
    deleteComment,
    addInterview,
    saveInterview,
    deleteInterview,
  };
}

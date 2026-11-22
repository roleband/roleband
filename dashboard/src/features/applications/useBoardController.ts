import { useCallback } from "react";
import { api, type ApplicationBoard, type ApplicationCard, type ApplicationCardInterview, type ApplicationStep, type InterviewUpdate } from "../../api";
import { useJobWorkspace } from "../../context/JobWorkspace";
import { useSaveCommand } from "../../context/useSaveCommand";
import type { StageSlug } from "../../copy/vocabulary";
import { useAsyncResource, useRefetchOn } from "../../hooks/useAsyncResource";
import { useToast } from "../../ui";
import {
  applicationsChangeFailed,
  applicationsMoveUndo,
  applicationsRemoveFailed,
  applicationsRemoved,
  applicationsListNotForMe,
  applicationsUndoFailed,
  applicationsUpnextDone,
  applicationsUpnextOutcomeSet,
} from "../../copy/gen/applications";
import { movedCard, withoutStep } from "./board";
import { OUTCOME_LABEL } from "./interviewWords";
import { useQuickChange } from "./useQuickChange";
import { useRoleWrite } from "./useRoleWrite";
import { useStageMove } from "./useStageMove";

type Outcome = NonNullable<InterviewUpdate["outcome"]>;

/**
 * The board's state: every application, and the things a card can be asked to
 * do from it: move to another stage, tick a next step, say how a round went,
 * or leave the pipeline.
 *
 * Every write goes through the save command, one at a time per role and in
 * the order asked for, as the posting's do; a write that landed is announced,
 * and this re-reads the board on every announcement, whichever surface sent
 * it. A move is `useStageMove`, the same as the application page's. Leaving
 * the pipeline removes the star; Not for me also records the verdict on the
 * posting, as Radar's does. `said` words the move's toast, so the board can
 * say a card left for a column it hides.
 */
export function useBoardController({ said }: { said?: (title: string, stage: StageSlug) => string } = {}) {
  const { favVersion } = useJobWorkspace();
  const { toast } = useToast();
  const saveRole = useSaveCommand();

  const board = useAsyncResource<ApplicationBoard>((signal) => api.applications(signal), []);
  const { mutate, refresh } = board;
  // A star, a stage or a step set on any surface changes the board.
  useRefetchOn(favVersion, refresh);

  const paint = useCallback(
    (jobId: number, stage: StageSlug) => {
      const now = new Date().toISOString();
      mutate((current) => current && {
        applications: current.applications.map((card) =>
          card.job_id === jobId ? movedCard(card, stage, now) : card,
        ),
      });
    },
    [mutate],
  );

  const reread = useCallback(() => refresh({ preserveData: true }), [refresh]);
  const { writeRole, write } = useRoleWrite();
  const move = useStageMove({ paint, refresh: reread, said, write });
  const change = useQuickChange(reread);

  const patch = useCallback(
    (jobId: number, changed: Partial<ApplicationCard>) =>
      mutate((current) => current && {
        applications: current.applications.map((card) => (card.job_id === jobId ? { ...card, ...changed } : card)),
      }),
    [mutate],
  );

  const drop = useCallback(
    (jobId: number) => mutate((current) => current && {
      applications: current.applications.filter((other) => other.job_id !== jobId),
    }),
    [mutate],
  );

  /** A next step is done: its row leaves Up next, and the card's next step
   *  is the soonest of the rest. Undo opens it again. */
  const finishStep = useCallback(
    (card: ApplicationCard, step: ApplicationStep) =>
      void change({
        jobId: card.job_id,
        title: card.title,
        paint: () => patch(card.job_id, withoutStep(card, step.id)),
        send: () => writeRole(card, () => api.updateStep(card.job_id, step.id, { done: true })),
        undo: () => writeRole(card, () => api.updateStep(card.job_id, step.id, { done: false })),
        text: applicationsUpnextDone({ step: step.text }),
      }),
    [change, patch, writeRole],
  );

  /** How a round went. The round leaves the ones waiting for an outcome; the
   *  read that follows brings any earlier one that still waits. A round a
   *  card names has no outcome yet, which is what Undo puts back. */
  const setOutcome = useCallback(
    (card: ApplicationCard, interview: ApplicationCardInterview, outcome: Outcome) => {
      const was: InterviewUpdate["outcome"] = null;
      void change({
        jobId: card.job_id,
        title: card.title,
        paint: () => patch(card.job_id, { awaiting_outcome: null }),
        send: () => writeRole(card, () => api.updateInterview(card.job_id, interview.id, { outcome })),
        undo: () => writeRole(card, () => api.updateInterview(card.job_id, interview.id, { outcome: was })),
        text: applicationsUpnextOutcomeSet({ label: interview.label, outcome: OUTCOME_LABEL[outcome]() }),
      });
    },
    [change, patch, writeRole],
  );

  /** Takes a role in Considering off the board by removing its star. Past
   *  Considering the server refuses, and the menu offers Withdrawn instead. */
  const remove = useCallback(
    (card: ApplicationCard) => {
      const { job_id: jobId, title } = card;
      saveRole({
        jobId, was: true, next: false,
        show: (on) => (on ? void reread() : drop(jobId)),
        send: () => api.setFavorite(jobId, false),
      })
        .then(({ outcome }) => {
          if (outcome !== "saved") return;
          toast({
            key: "applications",
            text: applicationsRemoved({ title }),
            action: {
              label: applicationsMoveUndo(),
              onClick: () => {
                saveRole({
                  jobId, was: false, next: true, show: () => undefined,
                  send: () => api.setFavorite(jobId, true),
                }).catch(() => {
                  toast({ key: "applications", tone: "error", text: applicationsUndoFailed({ title }) });
                  return reread();
                });
              },
            },
          });
        })
        .catch(() => {
          toast({ key: "applications", tone: "error", text: applicationsRemoveFailed({ title }) });
        });
    },
    [drop, reread, saveRole, toast],
  );

  /** Not for me on a role in Considering: the posting is marked, as on Radar,
   *  and the role leaves the pipeline, in one write in order with the role's
   *  others. One Undo takes back both. A failure part way puts back what was
   *  done and reads again. */
  const dismiss = useCallback(
    (card: ApplicationCard) => {
      const { job_id: jobId, title } = card;
      saveRole({
        jobId, was: true, next: false,
        show: (on) => (on ? void reread() : drop(jobId)),
        send: async () => {
          await api.dismissJob(jobId);
          try {
            await api.setFavorite(jobId, false);
          } catch (error) {
            await api.undismissJob(jobId).catch(() => undefined);
            throw error;
          }
        },
      })
        .then(({ outcome }) => {
          if (outcome !== "saved") return;
          toast({
            key: "applications",
            text: applicationsListNotForMe({ title }),
            action: {
              label: applicationsMoveUndo(),
              onClick: () => {
                saveRole({
                  jobId, was: false, next: true, show: () => undefined,
                  send: async () => {
                    await api.undismissJob(jobId);
                    try {
                      await api.setFavorite(jobId, true);
                    } catch (error) {
                      await api.dismissJob(jobId).catch(() => undefined);
                      throw error;
                    }
                  },
                }).catch(() => {
                  toast({ key: "applications", tone: "error", text: applicationsUndoFailed({ title }) });
                  return reread();
                });
              },
            },
          });
        })
        .catch(() => {
          toast({ key: "applications", tone: "error", text: applicationsChangeFailed({ title }) });
        });
    },
    [drop, reread, saveRole, toast],
  );

  return {
    cards: board.data?.applications ?? [],
    resource: board,
    move,
    remove,
    dismiss,
    finishStep,
    setOutcome,
  };
}

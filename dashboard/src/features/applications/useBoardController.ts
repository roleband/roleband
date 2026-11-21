import { useCallback } from "react";
import { api, type ApplicationBoard, type ApplicationCard, type ApplicationCardInterview, type InterviewUpdate } from "../../api";
import { useJobWorkspace } from "../../context/JobWorkspace";
import { useMissionActions } from "../../context/MissionState";
import type { StageSlug } from "../../copy/vocabulary";
import { useAsyncResource, useRefetchOn } from "../../hooks/useAsyncResource";
import { useRoleSaves } from "../../hooks/useRoleSaves";
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
  applicationsUpnextUndoFailed,
} from "../../copy/gen/applications";
import { movedCard } from "./board";
import { OUTCOME_LABEL } from "./interviewWords";
import { usePursuitWrite, useStageMove } from "./useStageMove";

type Outcome = NonNullable<InterviewUpdate["outcome"]>;

/**
 * The board's state: every application, and the two things a card can be
 * asked to do from it, move to another stage or leave the pipeline.
 *
 * A move is `useStageMove`, the same as the application page's. Leaving
 * the pipeline removes the star, in order with every other write to the role;
 * Not for me also records the verdict on the posting, as Radar's does.
 * `said` words the move's toast, so the board can say a card left for a
 * column it hides.
 */
export function useBoardController({ said }: { said?: (title: string, stage: StageSlug) => string } = {}) {
  const { favVersion } = useJobWorkspace();
  const { refreshStats } = useMissionActions();
  const { toast } = useToast();
  const saveRole = useRoleSaves();

  const board = useAsyncResource<ApplicationBoard>((signal) => api.applications(signal), []);
  const { mutate, refresh } = board;
  // A star or a stage set on any other surface changes the board.
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
  const move = useStageMove({ paint, refresh: reread, said });
  const write = usePursuitWrite();

  const patch = useCallback(
    (jobId: number, change: Partial<ApplicationCard>) =>
      mutate((current) => current && {
        applications: current.applications.map((card) => (card.job_id === jobId ? { ...card, ...change } : card)),
      }),
    [mutate],
  );

  /** A change Up next makes in one click: it paints at once, and its toast
   *  takes it back. A failure re-reads rather than restoring a remembered
   *  copy, as a move does. */
  const quickChange = useCallback(
    async ({ card, painted, send, undo, text }: {
      card: ApplicationCard;
      painted: Partial<ApplicationCard>;
      send: () => Promise<unknown>;
      undo: () => Promise<unknown>;
      text: string;
    }) => {
      const title = card.title;
      patch(card.job_id, painted);
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
              .catch(() => {
                toast({ key: "applications", tone: "error", text: applicationsUpnextUndoFailed({ title }) });
              })
              .finally(() => void reread());
          },
        },
      });
    },
    [patch, reread, toast],
  );

  /** The next step is done: it is cleared, and the row leaves Up next. */
  const finishStep = useCallback(
    (card: ApplicationCard) => {
      const { next_action: step, next_action_due: due } = card;
      void quickChange({
        card,
        painted: { next_action: null, next_action_due: null },
        send: () => write(card, { next_action: null, next_action_due: null }),
        undo: () => write(card, { next_action: step, next_action_due: due }),
        text: applicationsUpnextDone({ step: step ?? "" }),
      });
    },
    [quickChange, write],
  );

  /** How a round went. The round leaves the ones waiting for an outcome; the
   *  re-read brings any earlier one that still waits. */
  const setOutcome = useCallback(
    (card: ApplicationCard, interview: ApplicationCardInterview, outcome: Outcome) =>
      void quickChange({
        card,
        painted: { awaiting_outcome: null },
        send: () => api.updateInterview(card.job_id, interview.id, { outcome }),
        undo: () => api.updateInterview(card.job_id, interview.id, { outcome: null }),
        text: applicationsUpnextOutcomeSet({ label: interview.label, outcome: OUTCOME_LABEL[outcome]() }),
      }),
    [quickChange],
  );

  /** Takes a role in Considering off the board by removing its star. Past
   *  Considering the server refuses, and the menu offers Withdrawn instead. */
  const remove = useCallback(
    (card: ApplicationCard) => {
      const title = card.title;
      const show = (on: boolean) => {
        if (on) void refresh({ preserveData: true });
        else mutate((current) => current && {
          applications: current.applications.filter((other) => other.job_id !== card.job_id),
        });
      };
      saveRole({ jobId: card.job_id, was: true, next: false, show, send: () => api.setFavorite(card.job_id, false) })
        .then(() => {
          refreshStats();
          toast({
            key: "applications",
            text: applicationsRemoved({ title }),
            action: {
              label: applicationsMoveUndo(),
              onClick: () => {
                void saveRole({
                  jobId: card.job_id, was: false, next: true, show: () => undefined,
                  send: () => api.setFavorite(card.job_id, true),
                })
                  .catch(() => {
                    toast({ key: "applications", tone: "error", text: applicationsUndoFailed({ title }) });
                  })
                  .finally(() => {
                    refreshStats();
                    void refresh({ preserveData: true });
                  });
              },
            },
          });
        })
        .catch(() => {
          toast({ key: "applications", tone: "error", text: applicationsRemoveFailed({ title }) });
        });
    },
    [mutate, refresh, refreshStats, saveRole, toast],
  );

  /** Not for me on a role in Considering: the posting is marked, as on Radar,
   *  and the role leaves the pipeline. One Undo takes back both. A failure
   *  part way puts back what was done and re-reads. */
  const dismiss = useCallback(
    (card: ApplicationCard) => {
      const { job_id: jobId, title } = card;
      const drop = () => mutate((current) => current && {
        applications: current.applications.filter((other) => other.job_id !== jobId),
      });
      const unstar = () => saveRole({
        jobId, was: true, next: false,
        show: (on) => (on ? void refresh({ preserveData: true }) : drop()),
        send: () => api.setFavorite(jobId, false),
      });
      drop();
      api.dismissJob(jobId)
        .then(() => unstar().catch((error: unknown) => {
          void api.undismissJob(jobId).catch(() => undefined);
          throw error;
        }))
        .then(() => {
          refreshStats();
          toast({
            key: "applications",
            text: applicationsListNotForMe({ title }),
            action: {
              label: applicationsMoveUndo(),
              onClick: () => {
                void api.undismissJob(jobId)
                  .then(() => saveRole({
                    jobId, was: false, next: true, show: () => undefined,
                    send: () => api.setFavorite(jobId, true),
                  }))
                  .catch(() => {
                    toast({ key: "applications", tone: "error", text: applicationsUndoFailed({ title }) });
                  })
                  .finally(() => {
                    refreshStats();
                    void refresh({ preserveData: true });
                  });
              },
            },
          });
        })
        .catch(() => {
          void refresh({ preserveData: true });
          toast({ key: "applications", tone: "error", text: applicationsRemoveFailed({ title }) });
        });
    },
    [mutate, refresh, refreshStats, saveRole, toast],
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

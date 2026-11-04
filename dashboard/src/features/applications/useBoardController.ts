import { useCallback } from "react";
import { api, type ApplicationBoard, type ApplicationCard } from "../../api";
import { useJobWorkspace } from "../../context/JobWorkspace";
import { useMissionActions } from "../../context/MissionState";
import type { StageSlug } from "../../copy/vocabulary";
import { useAsyncResource, useRefetchOn } from "../../hooks/useAsyncResource";
import { useRoleSaves } from "../../hooks/useRoleSaves";
import { useToast } from "../../ui";
import {
  applicationsMoveUndo,
  applicationsRemoveFailed,
  applicationsRemoved,
  applicationsUndoFailed,
} from "../../copy/gen/applications";
import { useStageMove } from "./useStageMove";

/**
 * The board's state: every application, and the two things a card can be
 * asked to do from it, move to another stage or leave the pipeline.
 *
 * A move is `useStageMove`, the same as the application page's. Leaving
 * the pipeline removes the star, in order with every other write to the role.
 */
export function useBoardController() {
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
          card.job_id === jobId ? { ...card, stage, stage_since: now, last_activity_at: now } : card,
        ),
      });
    },
    [mutate],
  );

  const reread = useCallback(() => refresh({ preserveData: true }), [refresh]);
  const move = useStageMove({ paint, refresh: reread });

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

  return {
    cards: board.data?.applications ?? [],
    resource: board,
    move,
    remove,
  };
}

import { useCallback } from "react";
import { api, type ApplicationCard, type InterviewWrite } from "../../api";
import { useMissionActions } from "../../context/MissionState";
import { STAGE_LABEL, type StageSlug } from "../../copy/vocabulary";
import { useRoleSaves } from "../../hooks/useRoleSaves";
import { useToast } from "../../ui";
import {
  applicationsMoveFailed,
  applicationsMoveUndo,
  applicationsMoved,
  applicationsUndoFailed,
} from "../../copy/gen/applications";

/** Writes one pursuit field set for a role. A pursuit write saves the role
 *  (server rule), so it goes through `useRoleSaves` with the star's own
 *  writes, in the order they were asked for. */
export function usePursuitWrite() {
  const saveRole = useRoleSaves();
  return useCallback(
    (card: Pick<ApplicationCard, "job_id" | "starred">, update: Parameters<typeof api.setPursuit>[1]) =>
      saveRole({
        jobId: card.job_id,
        was: card.starred,
        next: true,
        show: () => undefined,
        send: () => api.setPursuit(card.job_id, update),
      }),
    [saveRole],
  );
}

/**
 * A stage move, the same from a board card and from the application page.
 * It paints at once and the server catches up. Undo is one move back, and
 * takes back the interview the move added. A failure re-reads rather than
 * restoring a remembered copy: another tab may have changed it.
 */
export function useStageMove({ paint, refresh }: {
  paint: (jobId: number, stage: StageSlug) => void;
  refresh: () => unknown;
}) {
  const { refreshStats } = useMissionActions();
  const { toast } = useToast();
  const write = usePursuitWrite();

  return useCallback(
    async (card: ApplicationCard, stage: StageSlug, interview?: InterviewWrite) => {
      if (card.stage === stage) return;
      const from = card.stage;
      const title = card.title;
      paint(card.job_id, stage);
      let added: number | null = null;
      try {
        await write(card, { stage });
        if (interview) added = (await api.addInterview(card.job_id, interview)).interview.id;
      } catch {
        toast({ key: "applications", tone: "error", text: applicationsMoveFailed({ title }) });
        await refresh();
        return;
      }
      refreshStats();
      void refresh();
      toast({
        key: "applications",
        text: applicationsMoved({ title, stage: STAGE_LABEL[stage] }),
        action: {
          label: applicationsMoveUndo(),
          onClick: () => {
            paint(card.job_id, from);
            void write(card, { stage: from })
              .then(() => (added == null ? undefined : api.deleteInterview(card.job_id, added)))
              .catch(() => {
                toast({ key: "applications", tone: "error", text: applicationsUndoFailed({ title }) });
              })
              .finally(() => {
                refreshStats();
                void refresh();
              });
          },
        },
      });
    },
    [paint, write, refresh, refreshStats, toast],
  );
}

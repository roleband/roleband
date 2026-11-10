import { useCallback } from "react";
import { api, type ApplicationCard, type InterviewWrite } from "../../api";
import { useMissionActions } from "../../context/MissionState";
import { STAGE_LABEL, type StageSlug } from "../../copy/vocabulary";
import { useRoleSaves } from "../../hooks/useRoleSaves";
import { useToast } from "../../ui";
import {
  applicationsMoveFailed,
  applicationsMoveFailedInterviewKept,
  applicationsMoveUndo,
  applicationsMoved,
  applicationsUndoFailed,
} from "../../copy/gen/applications";
import { boardStage } from "./board";

/** Writes one pursuit field set for a role. A pursuit write saves the role
 *  (server rule), so it goes through `useRoleSaves` with the star's own
 *  writes, in the order they were asked for. It rejects whenever the write
 *  failed: a pursuit write sets only the fields it names, so a newer write
 *  for the role never carries this one's change, and a failure behind it is
 *  still lost. */
export type PursuitWrite = (
  card: Pick<ApplicationCard, "job_id" | "starred">,
  update: Parameters<typeof api.setPursuit>[1],
) => Promise<void>;

export function usePursuitWrite(): PursuitWrite {
  const saveRole = useRoleSaves();
  return useCallback(
    async (card: Pick<ApplicationCard, "job_id" | "starred">, update: Parameters<typeof api.setPursuit>[1]) => {
      const outcome = await saveRole({
        jobId: card.job_id,
        was: card.starred,
        next: true,
        show: () => undefined,
        send: () => api.setPursuit(card.job_id, update),
      });
      if (outcome !== "saved") throw new Error("The pursuit write failed behind a newer write for the role.");
    },
    [saveRole],
  );
}

const moved = (title: string, stage: StageSlug) => applicationsMoved({ title, stage: STAGE_LABEL[stage] });

/**
 * A stage move, the same from a board card and from the application page.
 * It paints at once and the server catches up. Undo is one move back, and
 * takes back the interview the move added. A failed move re-reads rather
 * than restoring a remembered copy: another tab may have changed it.
 *
 * An interview the move asks for is saved first, while its form is still
 * open: if it fails nothing has changed, and the form keeps what was typed
 * and says so. The card moves once the interview is in. Resolves true when
 * the move landed.
 *
 * `write` stands in for the pipeline's own pursuit write on a surface that
 * must also tell every other reader of the role (the posting, which can be
 * open over the pipeline page that shows the same application).
 */
export function useStageMove({ paint, refresh, said = moved, write: given }: {
  paint: (jobId: number, stage: StageSlug) => void;
  refresh: () => unknown;
  /** What the toast says once the move lands. */
  said?: (title: string, stage: StageSlug) => string;
  write?: PursuitWrite;
}) {
  const { refreshStats } = useMissionActions();
  const { toast } = useToast();
  const own = usePursuitWrite();
  const write = given ?? own;

  return useCallback(
    async (card: ApplicationCard, stage: StageSlug, interview?: InterviewWrite): Promise<boolean> => {
      // Networking shows as Researching, so picking Researching changes nothing.
      if (boardStage(card.stage) === stage) return true;
      const from = card.stage;
      const title = card.title;
      let added: number | null = null;
      if (interview) {
        try {
          added = (await api.addInterview(card.job_id, interview)).interview.id;
        } catch {
          return false;
        }
      }
      paint(card.job_id, stage);
      try {
        await write(card, { stage });
      } catch {
        // The form that asked for the interview says the failure itself,
        // unless the interview it saved could not be taken back: then the
        // person is told it is there, so a second try does not add another
        // without them knowing.
        if (added == null) toast({ key: "applications", tone: "error", text: applicationsMoveFailed({ title }) });
        else {
          await api.deleteInterview(card.job_id, added).catch(() => {
            toast({ key: "applications", tone: "error", text: applicationsMoveFailedInterviewKept({ title }) });
          });
        }
        await refresh();
        return false;
      }
      refreshStats();
      void refresh();
      toast({
        key: "applications",
        text: said(title, stage),
        action: {
          label: applicationsMoveUndo(),
          onClick: () => {
            paint(card.job_id, from);
            // The interview goes only once the move back has landed; a move
            // back that failed rejects, and the interview stays.
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
      return true;
    },
    [paint, write, refresh, refreshStats, toast, said],
  );
}

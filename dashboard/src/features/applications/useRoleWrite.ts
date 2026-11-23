import { useCallback } from "react";
import { api, type ApplicationCard } from "../../api";
import { useSaveCommand } from "../../context/useSaveCommand";
import type { PursuitWrite } from "./useStageMove";

export type RoleWrite = (
  target: Pick<ApplicationCard, "job_id" | "starred">,
  send: () => Promise<unknown>,
) => Promise<void>;

/**
 * Every write to a role's pursuit, from the board and from the posting: it
 * goes through the save command, one at a time per role and in the order
 * asked for, and a write that landed is announced, so every reader of the
 * role (the board, the posting, an application page) reads it again. It
 * rejects whenever the write did not land: a failure, or one behind a newer
 * write for the role, whose change a pursuit write never carries.
 *
 * `show` paints the role's star as the write asks and as the server answers;
 * `failed` runs after every write that did not land, the one behind a newer
 * write included, for what the screen painted ahead: the newer write may not
 * touch what this one painted.
 */
export function useRoleWrite({ show, failed }: {
  show?: (jobId: number, saved: boolean) => void;
  failed?: (jobId: number) => void;
} = {}): { writeRole: RoleWrite; write: PursuitWrite } {
  const saveRole = useSaveCommand();
  const writeRole = useCallback<RoleWrite>(
    async (target, send) => {
      const jobId = target.job_id;
      const { outcome } = await saveRole({
        jobId,
        was: target.starred,
        next: true,
        show: (saved) => show?.(jobId, saved),
        send,
      }).catch((error: unknown) => {
        failed?.(jobId);
        throw error;
      });
      if (outcome !== "saved") {
        failed?.(jobId);
        throw new Error("The pursuit write failed behind a newer write for the role.");
      }
    },
    [saveRole, show, failed],
  );
  const write = useCallback<PursuitWrite>(
    (target, update) => writeRole(target, () => api.setPursuit(target.job_id, update)),
    [writeRole],
  );
  return { writeRole, write };
}

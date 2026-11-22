import { useCallback } from "react";
import { useToast } from "../../ui";
import { applicationsChangeFailed, applicationsMoveUndo, applicationsUpnextUndoFailed } from "../../copy/gen/applications";

/** One change a person makes to a role in a click. */
export interface QuickChange {
  jobId: number;
  title: string;
  /** Paints the change ahead of the write; the surface decides where (the
   *  board's card, the posting's application). */
  paint?: () => void;
  send: () => Promise<unknown>;
  /** What the toast's Undo does. With `text`, the change is offered back. */
  undo?: () => Promise<unknown>;
  /** What the toast says once the write landed; none, no toast. */
  text?: string;
}

/**
 * The write, toast and Undo every one-click change shares, on the board and
 * on the posting. A failure says so and reads again rather than restoring a
 * remembered copy, since another surface may have changed the role; a failed
 * Undo says so and reads again. A write that landed reads nothing here: the
 * write path that sent it announces it, and every reader of the role follows.
 * `reread` is told the role the change was made on, so a surface that has
 * moved on to another role reads nothing.
 *
 * Resolves true when the write landed.
 */
export function useQuickChange(reread: (jobId: number) => unknown) {
  const { toast } = useToast();
  return useCallback(
    async ({ jobId, title, paint, send, undo, text }: QuickChange): Promise<boolean> => {
      paint?.();
      try {
        await send();
      } catch {
        toast({ key: "applications", tone: "error", text: applicationsChangeFailed({ title }) });
        await reread(jobId);
        return false;
      }
      if (undo && text) {
        toast({
          key: "applications",
          text,
          action: {
            label: applicationsMoveUndo(),
            onClick: () => {
              void undo().catch(() => {
                toast({ key: "applications", tone: "error", text: applicationsUpnextUndoFailed({ title }) });
                return reread(jobId);
              });
            },
          },
        });
      }
      return true;
    },
    [reread, toast],
  );
}

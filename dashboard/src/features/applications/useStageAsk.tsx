import { useState, type ReactNode } from "react";
import type { ApplicationCard, InterviewWrite } from "../../api";
import type { StageSlug } from "../../copy/vocabulary";
import { InterviewDialog } from "./InterviewDialog";
import type { useBoardController } from "./useBoardController";

/** A move as every pipeline view makes it. Interviewing asks for the
 *  interview's date first: it is the stage's entry condition. Every other
 *  move is immediate. `dialog` is the question, for the view to draw. */
export function useStageAsk(move: ReturnType<typeof useBoardController>["move"]): {
  ask: (card: ApplicationCard, stage: StageSlug) => void;
  dialog: ReactNode;
} {
  const [asking, setAsking] = useState<ApplicationCard | null>(null);
  const ask = (card: ApplicationCard, stage: StageSlug) => {
    if (stage === "interviewing" && card.stage !== "interviewing") setAsking(card);
    else void move(card, stage);
  };
  // The form waits for the move, and closes only once it has landed.
  const confirm = async (interview: InterviewWrite) => {
    const card = asking;
    if (!card) return false;
    const moved = await move(card, "interviewing", interview);
    if (moved) setAsking(null);
    return moved;
  };
  const dialog = asking
    ? <InterviewDialog card={asking} moving onCancel={() => setAsking(null)} onSubmit={confirm} />
    : null;
  return { ask, dialog };
}

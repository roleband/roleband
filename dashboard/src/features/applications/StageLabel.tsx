import type { ApplicationCard } from "../../api";
import { STAGE_LABEL } from "../../copy/vocabulary";
import { applicationsCardEnded } from "../../copy/gen/applications";
import { boardStage } from "./board";

/** How an ended application ended, "Rejected at Applied"; null while it moves. */
export function endingName(card: Pick<ApplicationCard, "stage" | "ended_at_stage">): string | null {
  const from = card.ended_at_stage;
  return from ? applicationsCardEnded({ ending: STAGE_LABEL[card.stage], stage: STAGE_LABEL[boardStage(from)] }) : null;
}

/** The stage's name as the pipeline says it: the ending for an ended one. */
export function stageName(card: Pick<ApplicationCard, "stage" | "ended_at_stage">): string {
  return endingName(card) ?? STAGE_LABEL[card.stage];
}

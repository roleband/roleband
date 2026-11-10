import type { ApplicationCard } from "../../api";
import { STAGE_LABEL } from "../../copy/vocabulary";
import { Msg } from "../../ui";
import { Abbr } from "../../ui/Abbr";
import {
  applicationsCardEnded,
  applicationsCardDaysInStage,
  applicationsCardDaysShort,
  applicationsStageButton,
} from "../../copy/gen/applications";
import { boardStage, daysToSay } from "./board";

/** How an ended application ended, "Rejected at Applied"; null while it moves. */
export function endingName(card: Pick<ApplicationCard, "stage" | "ended_at_stage">): string | null {
  const from = card.ended_at_stage;
  return from ? applicationsCardEnded({ ending: STAGE_LABEL[card.stage], stage: STAGE_LABEL[boardStage(from)] }) : null;
}

/** The stage's name as the pipeline says it: the ending for an ended one. */
export function stageName(card: Pick<ApplicationCard, "stage" | "ended_at_stage">): string {
  return endingName(card) ?? STAGE_LABEL[card.stage];
}

/** The application page's stage button words: the stage, and from the day
 *  after the move the board's short count (12d), whose full words are what a
 *  screen reader hears. The posting's button says the stage alone; its days
 *  are its Pipeline section's. */
export function StageLabel({ card, now }: { card: ApplicationCard; now: Date }) {
  const stage = STAGE_LABEL[card.stage];
  const days = daysToSay(card, now);
  if (days == null) return <>{stage}</>;
  return (
    <Msg
      of={applicationsStageButton}
      elems={{
        stage,
        days: <Abbr short={applicationsCardDaysShort({ days })} full={applicationsCardDaysInStage({ days })} />,
      }}
    />
  );
}

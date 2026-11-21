import type { StageSlug } from "../../copy/vocabulary";
import { Icon } from "../../ui";
import { CLOSED_STAGES, DECIDED_STAGES, boardStage } from "./board";

/** How far along the moving stages a stage is, in quarters: the ring fills a
 *  quarter per stage after Considering, and is whole at Offer. */
const QUARTERS: Partial<Record<StageSlug, number>> = { researching: 1, applied: 2, interviewing: 3, offer: 4 };

const RADIUS = 9;
const AROUND = 2 * Math.PI * RADIUS;

/** A stage's mark: a ring that fills as the stage advances. Considering is the
 *  dashed circle the rail draws for it; an ending is a closed circle with how
 *  it closed, chosen or not. It decorates a stage's name and never stands for
 *  it. */
export function StageRing({ stage, size = 14 }: { stage: StageSlug; size?: number }) {
  const glyph = (name: "circleDashed" | "checkCircle" | "xCircle", ended: boolean) => (
    <span className="app-stage-ring" data-ended={ended || undefined} aria-hidden="true">
      <Icon name={name} size={size} />
    </span>
  );
  if (stage === "saved") return glyph("circleDashed", false);
  if ((DECIDED_STAGES as readonly StageSlug[]).includes(stage)) return glyph("checkCircle", true);
  if ((CLOSED_STAGES as readonly StageSlug[]).includes(stage)) return glyph("xCircle", true);
  const quarters = QUARTERS[boardStage(stage)] ?? 0;
  return (
    <svg className="app-stage-ring" viewBox="0 0 24 24" width={size} height={size} aria-hidden="true" data-quarters={quarters}>
      <circle className="app-stage-ring-track" cx="12" cy="12" r={RADIUS} />
      <circle
        className="app-stage-ring-fill"
        cx="12"
        cy="12"
        r={RADIUS}
        strokeDasharray={`${(AROUND * quarters) / 4} ${AROUND}`}
        transform="rotate(-90 12 12)"
      />
    </svg>
  );
}

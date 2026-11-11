import { Suspense, lazy, useState } from "react";
import type { InterviewWrite } from "../../api";
import type { StageSlug } from "../../copy/vocabulary";
import { StarButton } from "../../patterns/jobs/JobControls";
import { Button, Icon, MenuItem } from "../../ui";
import {
  applicationsMenuRemove,
  applicationsStageMenuLabel,
} from "../../copy/gen/applications";
import { StageMenu } from "./StageMenu";
import { stageName } from "./StageLabel";
import type { PostingApplication } from "./usePostingApplication";

const InterviewDialog = lazy(() => import("./InterviewDialogLazy"));

/**
 * The posting bar's one control for where the person stands with the role.
 * Off the board it is the star, the way in. On it, the star becomes the
 * pipeline's stage button in the same place: the same words, the same menu,
 * and the same rule for leaving (only from Considering; past it the way out
 * is Withdrawn). The bar holds controls only: how long the role has stood
 * in its stage, and what waits, are read in the posting's Pipeline section.
 */
export function PostingStage({
  application,
  onSave,
}: {
  application: PostingApplication;
  /** Saves a role that is not on the board. */
  onSave: () => void;
}) {
  const { card, reached, move, remove } = application;
  const [anchor, setAnchor] = useState<HTMLButtonElement | null>(null);
  const [open, setOpen] = useState(false);
  const [asking, setAsking] = useState(false);

  if (!card) return <StarButton on={false} onToggle={onSave} size={20} />;

  const ending = card.ended_at_stage;
  const label = stageName(card);

  const choose = (stage: StageSlug) => {
    setOpen(false);
    // Interviewing asks for the interview's date first, as everywhere in the pipeline.
    if (stage === "interviewing" && card.stage !== "interviewing") setAsking(true);
    else void move(card, stage);
  };
  const submitInterview = async (interview: InterviewWrite) => {
    const moved = await move(card, "interviewing", interview);
    if (moved) setAsking(false);
    return moved;
  };

  return (
    <>
      <Button
        ref={setAnchor}
        variant="ghost"
        className="ui-btn-strong jd-stage"
        data-ended={ending ? "" : undefined}
        aria-haspopup="dialog"
        aria-expanded={open}
        onClick={() => setOpen((was) => !was)}
      >
        {/* The saved star, as the radar row draws it: the role is in the
            pipeline because it is saved, at every stage and after an ending. */}
        <span className="jd-stage-star">
          <Icon name="star" size={15} filled />
        </span>
        {label}
        <Icon name="chevronDown" size={14} />
      </Button>
      <StageMenu
        current={card.stage}
        label={applicationsStageMenuLabel({ title: card.title })}
        anchor={anchor}
        isOpen={open}
        onClose={() => setOpen(false)}
        onMove={choose}
        reached={reached}
      >
        {card.stage === "saved" && card.starred && (
          <MenuItem
            onSelect={() => {
              setOpen(false);
              remove();
            }}
          >
            {applicationsMenuRemove()}
          </MenuItem>
        )}
      </StageMenu>
      {asking && (
        <Suspense fallback={null}>
          <InterviewDialog card={card} moving onCancel={() => setAsking(false)} onSubmit={submitInterview} />
        </Suspense>
      )}
    </>
  );
}

import type { ReactNode } from "react";
import { useLocation } from "react-router-dom";
import type { Job } from "../../api";
import type { StageSlug } from "../../copy/vocabulary";
import { PipelineSection } from "./PipelineSection";
import { PostingStage } from "./PostingStage";
import { applicationPath } from "./board";
import { usePostingApplication } from "./usePostingApplication";

/** The stages before the person has applied: the employer's page is still
 *  where they apply. */
const BEFORE_APPLYING: ReadonlySet<StageSlug> = new Set(["saved", "researching", "networking"]);

/** What the posting shows of its role's place in the pipeline. */
export interface PostingPipeline {
  /** The bar's control: the star off the board, the stage on it. */
  control: ReactNode;
  /** The Pipeline section of the side column; null off the board. */
  section: ReactNode;
  /** The person has applied, or the application has ended. */
  applied: boolean;
}

/**
 * The pipeline's part of a posting, composed into it by its route: the
 * posting knows nothing of stages, and the pipeline keeps its menu, its moves
 * and its interview form in one place.
 */
export function usePostingPipeline(
  job: Job | null,
  { showSaved, paintPosting, onSave, now, column }: {
    /** Paints the posting's star. */
    showSaved: (on: boolean) => void;
    /** Paints the posting's own copy of its stage. */
    paintPosting: (stage: StageSlug) => void;
    /** Saves a role that is not on the board. */
    onSave: () => void;
    now: Date;
    /** The side column the section sits in, for its history to open across. */
    column: HTMLElement | null;
  },
): PostingPipeline {
  const application = usePostingApplication(job, { showSaved, paintPosting });
  const { state } = useLocation();
  // Opened over the application's own page, the section would repeat the page under it.
  const under = (state as { backgroundLocation?: { pathname?: string } } | null)?.backgroundLocation?.pathname;
  const overItsPage = job != null && under === applicationPath(job.id);
  const { card, history } = application;
  return {
    control: job ? <PostingStage application={application} onSave={onSave} /> : null,
    section: card && !overItsPage
      ? <PipelineSection card={card} history={history} now={now} column={column} />
      : null,
    applied: card != null && !BEFORE_APPLYING.has(card.stage),
  };
}

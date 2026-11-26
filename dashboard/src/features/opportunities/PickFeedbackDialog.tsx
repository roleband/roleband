import { useEffect, useRef } from "react";
import type { Job } from "../../api";
import {
  picksWhyCompany,
  picksWhyKeep,
  picksWhyLevel,
  picksWhyNote,
  picksWhyOther,
  picksWhyPay,
  picksWhyPlace,
  picksWhyRole,
  picksWhySkip,
  picksWhyTitle,
  picksWhyWork,
} from "../../copy/gen/picks";
import { companyName } from "../../format";
import { Button, Content, Dialog, Msg } from "../../ui";
import "../../design/materials/register-material.css";
import "./top-picks.css";

/** The reasons a person can give, as the codes the feedback call stores and
 *  the assistant reads. */
const PICK_FEEDBACK_REASONS = [
  ["pay_too_low", picksWhyPay],
  ["wrong_level", picksWhyLevel],
  ["wrong_role", picksWhyWork],
  ["company", picksWhyCompany],
  ["wrong_place", picksWhyPlace],
  ["other", picksWhyOther],
] as const;

export type PickFeedbackReason = (typeof PICK_FEEDBACK_REASONS)[number][0];

/** Not for me on a pick asks why before anything happens. A reason removes
 *  the role at once, as does Skip the reason with none; Keep it, Escape and the
 *  scrim leave it a pick. The safe answer takes the focus. */
export function PickFeedbackDialog({
  job,
  onRemove,
  onKeep,
}: {
  /** The pick being asked about; null keeps the dialog closed. */
  job: Job | null;
  onRemove: (job: Job, reason: PickFeedbackReason | null) => void;
  onKeep: () => void;
}) {
  const keepRef = useRef<HTMLButtonElement>(null);
  // A child's effect runs before the Overlay's, which keeps focus it finds
  // already inside.
  useEffect(() => {
    if (job) keepRef.current?.focus();
  }, [job]);

  return (
    <Dialog isOpen={job != null} onClose={onKeep} label={picksWhyTitle()} width={560} className="app-overlay pick-feedback">
      {job && (
        <div className="ledger-form ledger-confirm">
          <h3>{picksWhyTitle()}</h3>
          <p className="pick-feedback-role">
            <Msg of={picksWhyRole} elems={{ title: <Content text={job.title} />, company: <Content text={companyName(job.company)} /> }} />
          </p>
          <div className="pick-feedback-reasons">
            {PICK_FEEDBACK_REASONS.map(([code, label]) => (
              <Button key={code} size="sm" className="ui-btn-strong" onClick={() => onRemove(job, code)}>
                {label()}
              </Button>
            ))}
          </div>
          <p className="pick-feedback-note">{picksWhyNote()}</p>
          <div className="ledger-form-actions pick-feedback-actions">
            <Button variant="link" className="is-leading" onClick={() => onRemove(job, null)}>{picksWhySkip()}</Button>
            <Button ref={keepRef} onClick={onKeep}>{picksWhyKeep()}</Button>
          </div>
        </div>
      )}
    </Dialog>
  );
}

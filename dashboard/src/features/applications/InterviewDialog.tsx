import { FormEvent, useState } from "react";
import type { ApplicationCard, ApplicationInterview, InterviewWrite } from "../../api";
import { STAGE_LABEL } from "../../copy/vocabulary";
import { companyName } from "../../format";
import { Button, Dialog, Select } from "../../ui";
import "../../design/materials/register-material.css";
import {
  applicationsInterviewAdd,
  applicationsInterviewAddTitle,
  applicationsInterviewCancel,
  applicationsInterviewDate,
  applicationsInterviewDelete,
  applicationsInterviewEditSubmit,
  applicationsInterviewEditTitle,
  applicationsInterviewDefaultLabel,
  applicationsInterviewFormat,
  applicationsInterviewFormatNone,
  applicationsInterviewFormatOnsite,
  applicationsInterviewFormatPhone,
  applicationsInterviewFormatVideo,
  applicationsInterviewLink,
  applicationsInterviewLinkPlaceholder,
  applicationsInterviewMoves,
  applicationsInterviewNotes,
  applicationsInterviewOutcome,
  applicationsInterviewOutcomeCancelled,
  applicationsInterviewOutcomeNone,
  applicationsInterviewOutcomeNotPassed,
  applicationsInterviewOutcomePassed,
  applicationsInterviewRound,
  applicationsInterviewSubmit,
  applicationsInterviewTime,
  applicationsInterviewTitle,
} from "../../copy/gen/applications";

type FormatChoice = "" | "video" | "phone" | "onsite";
type OutcomeChoice = "" | "passed" | "not_passed" | "cancelled";

const pad = (n: number) => String(n).padStart(2, "0");

/** A stored interview as the form's fields: its day and clock in the
 *  reader's own zone, and no clock for an all-day one. */
function fieldsOf(interview: ApplicationInterview) {
  const at = new Date(interview.scheduled_at);
  return {
    label: interview.label,
    day: `${at.getFullYear()}-${pad(at.getMonth() + 1)}-${pad(at.getDate())}`,
    clock: interview.all_day ? "" : `${pad(at.getHours())}:${pad(at.getMinutes())}`,
    format: (interview.format ?? "") as FormatChoice,
    link: interview.link ?? "",
    outcome: (interview.outcome ?? "") as OutcomeChoice,
    notes: interview.notes ?? "",
  };
}

/** The interview a move into Interviewing records. A date with no time is an
 *  all-day interview, held at the reader's own midnight so no zone moves its
 *  day. Exported for the tests: the instant sent is the contract. */
export function interviewFrom(fields: {
  label: string;
  day: string;
  clock: string;
  format: FormatChoice;
  link: string;
}): InterviewWrite {
  const [year, month, dayOfMonth] = fields.day.split("-").map(Number);
  const [hours, minutes] = fields.clock ? fields.clock.split(":").map(Number) : [0, 0];
  const at = new Date(year, month - 1, dayOfMonth, hours, minutes);
  return {
    label: fields.label.trim() || applicationsInterviewDefaultLabel(),
    scheduled_at: at.toISOString(),
    all_day: !fields.clock,
    format: fields.format || null,
    link: fields.link.trim() || null,
  };
}

export interface InterviewDialogProps {
  card: ApplicationCard;
  /** The interview to change. Absent, the dialog adds one. */
  interview?: ApplicationInterview;
  /** The interview is the condition of a move into Interviewing. */
  moving?: boolean;
  onCancel: () => void;
  onSubmit: (interview: InterviewWrite) => void;
  /** Offered only when changing a stored interview. */
  onDelete?: () => void;
}

/** One interview's form, in three uses: the entry condition of a move into
 *  Interviewing (Cancel leaves the card where it was), adding one, and
 *  changing one, where its outcome and notes are recorded. */
export function InterviewDialog({ card, interview, moving = false, onCancel, onSubmit, onDelete }: InterviewDialogProps) {
  const [initial] = useState(() => (interview ? fieldsOf(interview) : null));
  const [label, setLabel] = useState(initial?.label ?? "");
  const [day, setDay] = useState(initial?.day ?? "");
  const [clock, setClock] = useState(initial?.clock ?? "");
  const [format, setFormat] = useState<FormatChoice>(initial?.format ?? "");
  const [link, setLink] = useState(initial?.link ?? "");
  const [outcome, setOutcome] = useState<OutcomeChoice>(initial?.outcome ?? "");
  const [notes, setNotes] = useState(initial?.notes ?? "");
  const editing = interview != null;
  const title = moving ? applicationsInterviewTitle() : editing ? applicationsInterviewEditTitle() : applicationsInterviewAddTitle();

  const submit = (event: FormEvent) => {
    event.preventDefault();
    if (!day) return;
    const write = interviewFrom({ label, day, clock, format, link });
    onSubmit(editing ? { ...write, outcome: outcome || null, notes: notes.trim() || null } : write);
  };

  return (
    <Dialog isOpen onClose={onCancel} label={title} width={440} className="app-overlay">
      <form className="ledger-form app-interview-form" onSubmit={submit}>
        <h3>{title}</h3>
        {moving && (
          <p className="app-interview-note">
            {applicationsInterviewMoves({
              company: companyName(card.company),
              title: card.title,
              stage: STAGE_LABEL.interviewing,
            })}
          </p>
        )}
        <div>
          <label htmlFor="app-interview-round">{applicationsInterviewRound()}</label>
          <input
            id="app-interview-round"
            value={label}
            maxLength={120}
            placeholder={applicationsInterviewDefaultLabel()}
            onChange={(event) => setLabel(event.target.value)}
          />
        </div>
        <div className="app-interview-when">
          <div>
            <label htmlFor="app-interview-day">{applicationsInterviewDate()}</label>
            <input id="app-interview-day" type="date" required value={day} onChange={(event) => setDay(event.target.value)} />
          </div>
          <div>
            <label htmlFor="app-interview-clock">{applicationsInterviewTime()}</label>
            <input id="app-interview-clock" type="time" value={clock} onChange={(event) => setClock(event.target.value)} />
          </div>
        </div>
        <div>
          <label htmlFor="app-interview-format">{applicationsInterviewFormat()}</label>
          <Select
            id="app-interview-format"
            label={applicationsInterviewFormat()}
            value={format}
            onChange={setFormat}
            options={[
              { value: "", label: applicationsInterviewFormatNone() },
              { value: "video", label: applicationsInterviewFormatVideo() },
              { value: "phone", label: applicationsInterviewFormatPhone() },
              { value: "onsite", label: applicationsInterviewFormatOnsite() },
            ]}
          />
        </div>
        <div>
          <label htmlFor="app-interview-link">{applicationsInterviewLink()}</label>
          <input
            id="app-interview-link"
            type="url"
            value={link}
            placeholder={applicationsInterviewLinkPlaceholder()}
            onChange={(event) => setLink(event.target.value)}
          />
        </div>
        {editing && (
          <>
            <div>
              <label htmlFor="app-interview-outcome">{applicationsInterviewOutcome()}</label>
              <Select
                id="app-interview-outcome"
                label={applicationsInterviewOutcome()}
                value={outcome}
                onChange={setOutcome}
                options={[
                  { value: "", label: applicationsInterviewOutcomeNone() },
                  { value: "passed", label: applicationsInterviewOutcomePassed() },
                  { value: "not_passed", label: applicationsInterviewOutcomeNotPassed() },
                  { value: "cancelled", label: applicationsInterviewOutcomeCancelled() },
                ]}
              />
            </div>
            <div>
              <label htmlFor="app-interview-notes">{applicationsInterviewNotes()}</label>
              <textarea
                id="app-interview-notes"
                rows={4}
                maxLength={20_000}
                value={notes}
                onChange={(event) => setNotes(event.target.value)}
              />
            </div>
          </>
        )}
        <div className="app-interview-actions">
          {editing && onDelete && (
            <Button variant="ghost" className="app-interview-delete" onClick={onDelete}>
              {applicationsInterviewDelete()}
            </Button>
          )}
          <Button variant="ghost" onClick={onCancel}>{applicationsInterviewCancel()}</Button>
          <Button variant="primary" type="submit">
            {moving
              ? applicationsInterviewSubmit({ stage: STAGE_LABEL.interviewing })
              : editing ? applicationsInterviewEditSubmit() : applicationsInterviewAdd()}
          </Button>
        </div>
      </form>
    </Dialog>
  );
}

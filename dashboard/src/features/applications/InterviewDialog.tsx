import { FormEvent, KeyboardEvent, useEffect, useId, useRef, useState } from "react";
import type { ApplicationCard, ApplicationInterview, InterviewWrite } from "../../api";
import { timeZone, timestamp } from "../../copy/format";
import { STAGE_LABEL } from "../../copy/vocabulary";
import { companyName } from "../../format";
import { Button, Dialog, FilterChip, Icon, Select, useEscapeLayer } from "../../ui";
import "../../design/materials/register-material.css";
import {
  applicationsInterviewAdd,
  applicationsInterviewAddTitle,
  applicationsInterviewCancel,
  applicationsInterviewDayMissing,
  applicationsInterviewDefaultLabel,
  applicationsCommentDelete,
  applicationsInterviewDelete,
  applicationsInterviewDeleteConfirm,
  applicationsInterviewEditSubmit,
  applicationsInterviewEditTitle,
  applicationsInterviewFor,
  applicationsInterviewFormat,
  applicationsInterviewFormatOnsite,
  applicationsInterviewFormatPhone,
  applicationsInterviewFormatVideo,
  applicationsInterviewLink,
  applicationsInterviewLinkPlaceholder,
  applicationsInterviewMoves,
  applicationsInterviewNotes,
  applicationsInterviewOptional,
  applicationsInterviewOutcome,
  applicationsInterviewOutcomeCancelled,
  applicationsInterviewOutcomeNone,
  applicationsInterviewOutcomeNotPassed,
  applicationsInterviewOutcomePassed,
  applicationsInterviewPickDay,
  applicationsInterviewRound,
  applicationsInterviewRoundAdd,
  applicationsInterviewRoundFinal,
  applicationsInterviewRoundHiringManager,
  applicationsInterviewRoundName,
  applicationsInterviewRoundPanel,
  applicationsInterviewRoundRecruiter,
  applicationsInterviewRoundTechnical,
  applicationsInterviewSubmit,
  applicationsInterviewTitle,
  applicationsInterviewWhenDay,
  applicationsInterviewWhenTimed,
  applicationsInterviewZone,
} from "../../copy/gen/applications";
import { ClockPicker } from "./ClockPicker";
import { clockLabel, parseClock } from "./clock";
import { DayPicker } from "./DayPicker";
import { fromDayKey } from "./monthGrid";

type FormatChoice = "" | "video" | "phone" | "onsite";
type OutcomeChoice = "" | "passed" | "not_passed" | "cancelled";

const pad = (n: number) => String(n).padStart(2, "0");

const FORMATS: readonly [Exclude<FormatChoice, "">, () => string][] = [
  ["video", applicationsInterviewFormatVideo],
  ["phone", applicationsInterviewFormatPhone],
  ["onsite", applicationsInterviewFormatOnsite],
];

const ROUNDS = [
  applicationsInterviewRoundRecruiter,
  applicationsInterviewRoundHiringManager,
  applicationsInterviewRoundTechnical,
  applicationsInterviewRoundPanel,
  applicationsInterviewRoundFinal,
];

/** A stored interview as the form's fields: its day and clock in the
 *  reader's own zone, and no clock for an all-day one. The name saved for a
 *  round left unnamed reads as no round, so it is not offered as one. */
function fieldsOf(interview: ApplicationInterview) {
  const at = new Date(interview.scheduled_at);
  return {
    label: interview.label === applicationsInterviewDefaultLabel() ? "" : interview.label,
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

/**
 * One interview's form, in three uses: the entry condition of a move into
 * Interviewing (Cancel leaves the card where it was), adding one, and
 * changing one, where its outcome and notes are recorded.
 *
 * When comes first and is all it asks for: a day from the month and, beside
 * it, a time or none yet. Under Optional, the round and the format are one
 * click each: a plus after the common rounds names another in place, and a
 * video interview opens the field for its link. The head and the actions hold
 * still while the middle scrolls, so the way to save is always in reach.
 */
export function InterviewDialog({ card, interview, moving = false, onCancel, onSubmit, onDelete }: InterviewDialogProps) {
  const [now] = useState(() => new Date());
  const [initial] = useState(() => (interview ? fieldsOf(interview) : null));
  const [label, setLabel] = useState(initial?.label ?? "");
  const [day, setDay] = useState(initial?.day ?? "");
  const [clockText, setClockText] = useState(initial?.clock ? clockLabel(initial.clock) : "");
  const [format, setFormat] = useState<FormatChoice>(initial?.format ?? "");
  const [link, setLink] = useState(initial?.link ?? "");
  const [outcome, setOutcome] = useState<OutcomeChoice>(initial?.outcome ?? "");
  const [notes, setNotes] = useState(initial?.notes ?? "");
  const [naming, setNaming] = useState(false);
  const [draft, setDraft] = useState("");
  const addRound = useRef<HTMLButtonElement>(null);
  const nameField = useRef<HTMLInputElement>(null);
  const backToPlus = useRef(false);
  const [tried, setTried] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const keepButton = useRef<HTMLButtonElement>(null);
  const deleteButton = useRef<HTMLButtonElement>(null);
  const deleteAsked = useRef(false);
  const roundId = useId();
  const formatId = useId();
  const dayErrorId = useId();
  const editing = interview != null;
  const title = moving ? applicationsInterviewTitle() : editing ? applicationsInterviewEditTitle() : applicationsInterviewAddTitle();

  const clock = clockText.trim() ? parseClock(clockText) : "";
  const missingDay = tried && !day;
  const badClock = tried && clock == null;

  const summary = !day
    ? applicationsInterviewPickDay()
    : clock
      ? applicationsInterviewWhenTimed({
        date: timestamp(fromDayKey(day), { weekday: "short", month: "short", day: "numeric" }),
        time: clockLabel(clock),
      })
      : applicationsInterviewWhenDay({ date: timestamp(fromDayKey(day), { weekday: "short", month: "short", day: "numeric" }) });

  const submit = (event: FormEvent) => {
    event.preventDefault();
    setTried(true);
    if (!day || clock == null) return;
    const write = interviewFrom({ label, day, clock, format, link });
    onSubmit(editing ? { ...write, outcome: outcome || null, notes: notes.trim() || null } : write);
  };
  const rounds = ROUNDS.map((round) => round());
  const named = label.trim();
  const custom = named && !rounds.includes(named) ? named : "";
  const toggleRound = (name: string) => setLabel(named === name ? "" : name);
  // A name typed after the plus is kept on Enter or on leaving the field.
  // While the field is open it is the topmost Escape layer, so Escape drops
  // the name and leaves the dialog open. A key that closes the field hands
  // focus back to the plus, which takes its place.
  useEffect(() => {
    if (naming) {
      nameField.current?.focus();
    } else if (backToPlus.current) {
      backToPlus.current = false;
      addRound.current?.focus();
    }
  }, [naming]);
  const keepName = () => {
    if (draft.trim()) setLabel(draft.trim());
    setDraft("");
    setNaming(false);
  };
  useEscapeLayer(naming, () => {
    backToPlus.current = true;
    setDraft("");
    setNaming(false);
  });
  // Deleting asks first, in the actions' place: the question takes the
  // safe answer's focus, Escape answers it, and either answer hands focus
  // back to where the reader was.
  useEffect(() => {
    if (deleting) {
      deleteAsked.current = true;
      keepButton.current?.focus();
    } else if (deleteAsked.current) {
      deleteAsked.current = false;
      deleteButton.current?.focus();
    }
  }, [deleting]);
  useEscapeLayer(deleting, () => setDeleting(false));

  const onNameKey = (event: KeyboardEvent<HTMLInputElement>) => {
    if (event.key !== "Enter") return;
    event.preventDefault();
    backToPlus.current = true;
    keepName();
  };

  return (
    <Dialog isOpen onClose={onCancel} label={title} width={560} className="app-overlay app-interview-dialog">
      <form className="ledger-form app-interview-form" onSubmit={submit} noValidate>
        <header className="app-interview-head">
          <h3>{title}</h3>
          <p className="app-interview-note">
            {moving
              ? applicationsInterviewMoves({ company: companyName(card.company), title: card.title, stage: STAGE_LABEL.interviewing })
              : applicationsInterviewFor({ company: companyName(card.company), title: card.title })}
          </p>
          <p className="app-interview-summary" data-empty={!day || undefined} aria-live="polite">
            <Icon name="calendar" size={18} />
            <span>{summary}</span>
          </p>
        </header>

        <div className="app-interview-body">
          <div className="app-interview-when">
            <div>
              <DayPicker value={day} onChange={setDay} now={now} />
              {missingDay && (
                <p id={dayErrorId} className="app-interview-error" role="alert">{applicationsInterviewDayMissing()}</p>
              )}
            </div>
            <ClockPicker text={clockText} onText={setClockText} invalid={badClock} />
          </div>
          <p className="app-interview-zone">{applicationsInterviewZone({ zone: timeZone(now) })}</p>

          <section className="app-interview-optional" aria-label={applicationsInterviewOptional()}>
            <p className="app-interview-optional-head" aria-hidden="true">{applicationsInterviewOptional()}</p>
            <div className="app-interview-field">
              <p id={roundId} className="app-interview-label">{applicationsInterviewRound()}</p>
              <div className="app-interview-picks" role="group" aria-labelledby={roundId}>
                {rounds.map((name) => (
                  <FilterChip key={name} selected={named === name} onClick={() => toggleRound(name)}>{name}</FilterChip>
                ))}
                {custom && (
                  <FilterChip selected className="app-interview-custom" title={custom} onClick={() => setLabel("")}>
                    <span>{custom}</span>
                  </FilterChip>
                )}
                {naming ? (
                  <input
                    ref={nameField}
                    className="app-interview-name"
                    value={draft}
                    maxLength={120}
                    aria-label={applicationsInterviewRoundName()}
                    placeholder={applicationsInterviewRoundName()}
                    onChange={(event) => setDraft(event.target.value)}
                    onKeyDown={onNameKey}
                    onBlur={keepName}
                  />
                ) : (
                  <Button
                    ref={addRound}
                    size="sm"
                    className="app-interview-add"
                    aria-label={applicationsInterviewRoundAdd()}
                    title={applicationsInterviewRoundAdd()}
                    onClick={() => setNaming(true)}
                  >
                    <Icon name="plus" size={14} />
                  </Button>
                )}
              </div>
            </div>
            <div className="app-interview-field">
              <p id={formatId} className="app-interview-label">{applicationsInterviewFormat()}</p>
              <div className="app-interview-picks" role="group" aria-labelledby={formatId}>
                {FORMATS.map(([value, name]) => (
                  <FilterChip key={value} selected={format === value} onClick={() => setFormat(format === value ? "" : value)}>
                    {name()}
                  </FilterChip>
                ))}
              </div>
              {(format === "video" || link) && (
                <input
                  type="url"
                  value={link}
                  aria-label={applicationsInterviewLink()}
                  placeholder={applicationsInterviewLinkPlaceholder()}
                  onChange={(event) => setLink(event.target.value)}
                />
              )}
            </div>
            {editing && (
              <>
                <div className="app-interview-field">
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
                <div className="app-interview-field">
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
          </section>
        </div>

        {deleting && onDelete ? (
          <div className="app-interview-actions" role="group" aria-label={applicationsInterviewDeleteConfirm()}>
            <p className="app-interview-confirm">{applicationsInterviewDeleteConfirm()}</p>
            <Button ref={keepButton} variant="ghost" onClick={() => setDeleting(false)}>{applicationsInterviewCancel()}</Button>
            <Button variant="danger" onClick={onDelete}>{applicationsCommentDelete()}</Button>
          </div>
        ) : (
          <div className="app-interview-actions">
            {editing && onDelete && (
              <Button ref={deleteButton} variant="ghost" className="app-interview-delete" onClick={() => setDeleting(true)}>
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
        )}
      </form>
    </Dialog>
  );
}

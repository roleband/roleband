import { FormEvent, useEffect, useRef, useState } from "react";
import type { ApplicationCard, ApplicationInterview } from "../../api";
import { date as formatDate, time as formatTime } from "../../copy/format";
import { Button, Content, ExternalLink } from "../../ui";
import {
  applicationsInterviewAdd,
  applicationsInterviewFormatOnsite,
  applicationsInterviewFormatPhone,
  applicationsInterviewFormatVideo,
  applicationsNextDone,
  applicationsNextDue,
  applicationsNextEdit,
  applicationsNextEmpty,
  applicationsNextInterviewAllDay,
  applicationsNextInterviewAt,
  applicationsNextInterviewEdit,
  applicationsNextInterviewJoin,
  applicationsNextInterviewJoinLabel,
  applicationsNextInterviewMeta,
  applicationsNextInterviewNone,
  applicationsNextPrompt,
  applicationsNextRequired,
  applicationsNextSave,
  applicationsNextSet,
  applicationsNextTitle,
  applicationsInterviewCancel,
  applicationsNotesAdd,
  applicationsNotesEdit,
  applicationsNotesEmpty,
  applicationsNotesLabel,
  applicationsNotesLess,
  applicationsNotesMore,
  applicationsNotesSave,
  applicationsNotesTitle,
} from "../../copy/gen/applications";
import { DueBadge } from "./DueBadge";
import { useFocusAfter } from "./focusAfter";

const FORMAT_LABEL: Record<NonNullable<ApplicationInterview["format"]>, () => string> = {
  video: applicationsInterviewFormatVideo,
  phone: applicationsInterviewFormatPhone,
  onsite: applicationsInterviewFormatOnsite,
};

const pad = (n: number) => String(n).padStart(2, "0");

/** A field that takes focus when the form around it opens, so the person
 *  types where they asked to. */
export function useFocusWhen<T extends HTMLElement>(open: boolean) {
  const ref = useRef<T>(null);
  useEffect(() => {
    if (open) ref.current?.focus();
  }, [open]);
  return ref;
}

/** A due date picked as a day is due by that day's end in the reader's own
 *  zone: a step due today is not overdue this morning. */
function dueFromDay(day: string): string {
  const [year, month, dayOfMonth] = day.split("-").map(Number);
  return new Date(year, month - 1, dayOfMonth, 23, 59).toISOString();
}

function dayOf(iso: string): string {
  const at = new Date(iso);
  return `${at.getFullYear()}-${pad(at.getMonth() + 1)}-${pad(at.getDate())}`;
}

/** When an interview is, in words: the day, and the time unless it is all day. */
export function interviewWhen(interview: Pick<ApplicationInterview, "scheduled_at" | "all_day">): string {
  const day = formatDate(interview.scheduled_at, "weekday");
  return interview.all_day
    ? applicationsNextInterviewAllDay({ date: day })
    : applicationsNextInterviewAt({ date: day, time: formatTime(interview.scheduled_at) });
}

export interface NextPanelProps {
  card: ApplicationCard;
  interviews: readonly ApplicationInterview[];
  now: Date;
  onSetNext: (text: string | null, due: string | null) => Promise<boolean>;
  onEditInterview: (interview: ApplicationInterview) => void;
  onAddInterview: () => void;
}

/** What the application waits on: its next interview and its one next step.
 *  Mark done is the page's one filled button, and it asks at once what comes
 *  next; Cancel leaves the slot empty. */
export function NextPanel({ card, interviews, now, onSetNext, onEditInterview, onAddInterview }: NextPanelProps) {
  const [asking, setAsking] = useState(false);
  const [text, setText] = useState("");
  const [day, setDay] = useState("");
  const [empty, setEmpty] = useState(false);
  const textField = useFocusWhen<HTMLInputElement>(asking);
  // The form stands where its opener was; closing it hands focus to the
  // row's first control, so the reader is not dropped at the page's top.
  const stepRow = useRef<HTMLDivElement>(null);
  const focusAfter = useFocusAfter();
  const close = () => {
    focusAfter(() => stepRow.current?.querySelector<HTMLElement>("button"));
    setAsking(false);
  };
  const next = card.next_interview ? interviews.find((one) => one.id === card.next_interview!.id) ?? null : null;

  const openForm = (fromCurrent: boolean) => {
    setText(fromCurrent ? card.next_action ?? "" : "");
    setDay(fromCurrent && card.next_action_due ? dayOf(card.next_action_due) : "");
    setEmpty(false);
    setAsking(true);
  };

  const markDone = async () => {
    if (await onSetNext(null, null)) openForm(false);
  };

  const save = async (event: FormEvent) => {
    event.preventDefault();
    if (!text.trim()) {
      setEmpty(true);
      textField.current?.focus();
      return;
    }
    if (await onSetNext(text.trim(), day ? dueFromDay(day) : null)) close();
  };

  const due = card.next_action_due ? { kind: "step" as const, at: new Date(card.next_action_due), on: new Date(card.next_action_due) } : null;

  return (
    <section className="app-panel app-next" aria-labelledby="app-next-title">
      <h2 id="app-next-title" className="app-panel-title">{applicationsNextTitle()}</h2>

      <div className="app-next-row">
        {next ? (
          <>
            <div className="app-next-what">
              <span className="app-next-name"><Content text={next.label} /></span>
              <span className="app-next-meta">
                {next.format
                  ? applicationsNextInterviewMeta({ when: interviewWhen(next), format: FORMAT_LABEL[next.format]() })
                  : interviewWhen(next)}
              </span>
            </div>
            {next.link && (
              <ExternalLink href={next.link} label={applicationsNextInterviewJoinLabel({ label: next.label })}>
                {applicationsNextInterviewJoin()}
              </ExternalLink>
            )}
            <Button variant="ghost" size="sm" onClick={() => onEditInterview(next)}>{applicationsNextInterviewEdit()}</Button>
          </>
        ) : (
          <>
            <p className="app-next-empty">{applicationsNextInterviewNone()}</p>
            <Button variant="ghost" size="sm" className="ui-btn-strong" onClick={onAddInterview}>
              {applicationsInterviewAdd()}
            </Button>
          </>
        )}
      </div>

      <div className="app-next-row" ref={stepRow}>
        {asking ? (
          <form className="app-next-form" onSubmit={save}>
            <label htmlFor="app-next-text">{applicationsNextPrompt()}</label>
            <input
              id="app-next-text"
              ref={textField}
              value={text}
              maxLength={2_000}
              aria-invalid={empty || undefined}
              aria-describedby={empty ? "app-next-required" : undefined}
              onChange={(event) => {
                setText(event.target.value);
                if (event.target.value.trim()) setEmpty(false);
              }}
            />
            {empty && <p id="app-next-required" className="app-interview-error" role="alert">{applicationsNextRequired()}</p>}
            <label htmlFor="app-next-due">{applicationsNextDue()}</label>
            <input id="app-next-due" type="date" value={day} onChange={(event) => setDay(event.target.value)} />
            <div className="app-next-actions">
              <Button variant="ghost" size="sm" onClick={close}>{applicationsInterviewCancel()}</Button>
              <Button variant="primary" size="sm" type="submit">{applicationsNextSave()}</Button>
            </div>
          </form>
        ) : card.next_action ? (
          <>
            <div className="app-next-what">
              <span className="app-next-name"><Content text={card.next_action} /></span>
              {due && <DueBadge due={due} now={now} />}
            </div>
            <Button variant="ghost" size="sm" onClick={() => openForm(true)}>{applicationsNextEdit()}</Button>
            <Button variant="primary" size="sm" onClick={() => void markDone()}>{applicationsNextDone()}</Button>
          </>
        ) : (
          <>
            <p className="app-next-empty">{applicationsNextEmpty()}</p>
            <Button variant="ghost" size="sm" className="ui-btn-strong" onClick={() => openForm(false)}>
              {applicationsNextSet()}
            </Button>
          </>
        )}
      </div>
    </section>
  );
}

/** Notes long enough to clamp at three lines get a way to read them whole. */
const LONG_NOTES = 240;

/** The application's notes: one text the person keeps current, pinned above
 *  the feed, separate from the comments that record what happened. */
export function NotesBlock({ notes, onSave }: { notes: string | null; onSave: (notes: string) => Promise<boolean> }) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState("");
  const [whole, setWhole] = useState(false);
  const field = useFocusWhen<HTMLTextAreaElement>(editing);
  const opener = useRef<HTMLButtonElement>(null);
  const focusAfter = useFocusAfter();
  const close = () => {
    focusAfter(() => opener.current);
    setEditing(false);
  };
  const long = notes != null && (notes.length > LONG_NOTES || notes.split("\n").length > 3);

  const save = async (event: FormEvent) => {
    event.preventDefault();
    if (await onSave(draft)) close();
  };

  return (
    <section className="app-panel app-notes" aria-labelledby="app-notes-title">
      <div className="app-panel-head">
        <h2 id="app-notes-title" className="app-panel-title">{applicationsNotesTitle()}</h2>
        {!editing && (
          <Button
            ref={opener}
            variant="ghost"
            size="sm"
            onClick={() => {
              setDraft(notes ?? "");
              setEditing(true);
            }}
          >
            {notes ? applicationsNotesEdit() : applicationsNotesAdd()}
          </Button>
        )}
      </div>
      {editing ? (
        <form className="app-notes-form" onSubmit={save}>
          <textarea
            aria-label={applicationsNotesLabel()}
            ref={field}
            rows={6}
            maxLength={20_000}
            value={draft}
            onChange={(event) => setDraft(event.target.value)}
          />
          <div className="app-next-actions">
            <Button variant="ghost" size="sm" onClick={close}>{applicationsInterviewCancel()}</Button>
            <Button variant="ghost" size="sm" className="ui-btn-strong" type="submit">{applicationsNotesSave()}</Button>
          </div>
        </form>
      ) : notes ? (
        <>
          <p className="app-notes-text" data-clamped={long && !whole ? true : undefined}><Content text={notes} /></p>
          {long && (
            <Button variant="link" className="ui-btn-quiet" aria-expanded={whole} onClick={() => setWhole((open) => !open)}>
              {whole ? applicationsNotesLess() : applicationsNotesMore()}
            </Button>
          )}
        </>
      ) : (
        <p className="app-next-empty">{applicationsNotesEmpty()}</p>
      )}
    </section>
  );
}

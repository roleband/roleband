import { FormEvent, useEffect, useId, useRef, useState, type ReactNode } from "react";
import type { ActivityItem, ApplicationCard, ApplicationDetail, ApplicationInterview } from "../../api";
import { date as formatDate } from "../../copy/format";
import { STAGE_LABEL } from "../../copy/vocabulary";
import { Button, Content, ExternalLink, Icon, Menu, MenuCheck, MenuGroup, MenuItem } from "../../ui";
import {
  applicationsFactsInterviews,
  applicationsInterviewAdd,
  applicationsInterviewEditLabel,
  applicationsInterviewOutcome,
  applicationsNextInterviewJoin,
  applicationsNextInterviewJoinLabel,
  applicationsNextInterviewMeta,
  applicationsNextInterviewNone,
  applicationsNextSave,
  applicationsNotesLabel,
  applicationsNotesTitle,
  applicationsUpnextDoneLabel,
  applicationsUpnextOutcomeLabel,
  applicationsWsAskOutcome,
  applicationsWsHistory,
  applicationsWsNext,
  applicationsWsNextAdd,
  applicationsWsNextDue,
  applicationsWsNextEdit,
  applicationsWsNotesHint,
  applicationsWsSections,
  applicationsWsSectionsLabel,
  applicationsInterviewCancel,
} from "../../copy/gen/applications";
import { CommentItem } from "./ActivityFeed";
import type { ActivityComment } from "./activity";
import { interviewWhen } from "./ApplicationPanels";
import { boardStage, stepDue } from "./board";
import { DueBadge } from "./DueBadge";
import { useFocusAfter } from "./focusAfter";
import { FORMAT_LABEL, OUTCOME_LABEL } from "./interviewWords";
import { endingName } from "./StageLabel";
import {
  offeredSections,
  readHiddenSections,
  workspaceStage,
  writeHiddenSections,
  type WorkspaceSection,
} from "./workspaceSections";

type Outcome = NonNullable<ApplicationInterview["outcome"]>;

const pad = (n: number) => String(n).padStart(2, "0");

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

const SECTION_LABEL: Record<WorkspaceSection, () => string> = {
  interviews: applicationsFactsInterviews,
  next: applicationsWsNext,
  notes: applicationsNotesTitle,
  outcome: applicationsInterviewOutcome,
  history: applicationsWsHistory,
};

/** One labelled row of the Workspace: its name in the margin, its body beside. */
function Row({ section, children }: { section: WorkspaceSection; children: ReactNode }) {
  const id = `app-ws-${section}`;
  return (
    <section className="app-ws-row" data-section={section} aria-labelledby={id}>
      <h2 id={id} className="app-ws-label">{SECTION_LABEL[section]()}</h2>
      <div className="app-ws-body">{children}</div>
    </section>
  );
}

/* ---- Next step ---------------------------------------------------------- */

function StepForm({ text: initialText, day: initialDay, placeholder, label, focusFirst, onSave, onCancel }: {
  text: string;
  day: string;
  placeholder?: string;
  label: string;
  focusFirst: boolean;
  onSave: (text: string, day: string) => Promise<boolean>;
  onCancel?: () => void;
}) {
  const [text, setText] = useState(initialText);
  const [day, setDay] = useState(initialDay);
  const [saving, setSaving] = useState(false);
  const field = useRef<HTMLInputElement>(null);
  const dueId = useId();

  useEffect(() => {
    if (focusFirst) field.current?.focus();
  }, [focusFirst]);

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    if (!text.trim() || saving) return;
    setSaving(true);
    const saved = await onSave(text.trim(), day);
    setSaving(false);
    if (saved && !onCancel) {
      setText("");
      setDay("");
    }
  };

  return (
    <form className="app-ws-step-form" onSubmit={submit}>
      <input
        ref={field}
        className="app-ws-step-input"
        aria-label={label}
        placeholder={placeholder}
        maxLength={2_000}
        value={text}
        onChange={(event) => setText(event.target.value)}
      />
      {(text.trim() || day) && (
        <>
          <label className="sr-only" htmlFor={dueId}>{applicationsWsNextDue()}</label>
          <input id={dueId} className="app-ws-step-day" type="date" value={day} onChange={(event) => setDay(event.target.value)} />
          {onCancel && <Button variant="ghost" size="sm" onClick={onCancel}>{applicationsInterviewCancel()}</Button>}
          <Button variant="ghost" size="sm" className="ui-btn-strong" type="submit" disabled={!text.trim() || saving}>
            {applicationsNextSave()}
          </Button>
        </>
      )}
    </form>
  );
}

/** The one next step: a tick to finish it, its words to change it, its day at
 *  the end. With none, the line is where the next one is typed. */
function NextStep({ card, now, onSetNext, onFinish }: {
  card: ApplicationCard;
  now: Date;
  onSetNext: (text: string | null, due: string | null) => Promise<boolean>;
  onFinish: () => void;
}) {
  const [editing, setEditing] = useState(false);
  const edit = useRef<HTMLButtonElement>(null);
  const focusAfter = useFocusAfter();
  const save = (text: string, day: string) => onSetNext(text, day ? dueFromDay(day) : null);

  if (!card.next_action) {
    return <StepForm key="add" text="" day="" placeholder={applicationsWsNextAdd()} label={applicationsWsNextAdd()} focusFirst={false} onSave={save} />;
  }
  if (editing) {
    return (
      <StepForm
        key="edit"
        text={card.next_action}
        day={card.next_action_due ? dayOf(card.next_action_due) : ""}
        label={applicationsWsNext()}
        focusFirst
        onSave={async (text, day) => {
          const saved = await save(text, day);
          if (saved) {
            focusAfter(() => edit.current);
            setEditing(false);
          }
          return saved;
        }}
        onCancel={() => {
          focusAfter(() => edit.current);
          setEditing(false);
        }}
      />
    );
  }
  const due = stepDue(card);
  return (
    <div className="app-ws-step">
      <Button
        variant="icon"
        size="sm"
        className="ui-btn-tick app-upnext-tick"
        aria-label={applicationsUpnextDoneLabel({ step: card.next_action })}
        onClick={onFinish}
      >
        <Icon name="check" size={12} />
      </Button>
      <span className="app-ws-step-words"><Content text={card.next_action} /></span>
      {due && <DueBadge due={due} now={now} />}
      <Button
        ref={edit}
        variant="icon"
        size="sm"
        aria-label={applicationsWsNextEdit({ step: card.next_action })}
        onClick={() => setEditing(true)}
      >
        <Icon name="edit" size={14} />
      </Button>
    </div>
  );
}

/* ---- Interviews --------------------------------------------------------- */

function OutcomeAsk({ interview, onOutcome }: { interview: ApplicationInterview; onOutcome: (outcome: Outcome) => void }) {
  const [anchor, setAnchor] = useState<HTMLButtonElement | null>(null);
  const [open, setOpen] = useState(false);
  return (
    <>
      <Button
        ref={setAnchor}
        variant="ghost"
        size="sm"
        className="ui-btn-strong app-ws-ask"
        aria-haspopup="dialog"
        aria-expanded={open}
        onClick={() => setOpen((was) => !was)}
      >
        {applicationsWsAskOutcome()}
      </Button>
      <Menu isOpen={open} onClose={() => setOpen(false)} anchor={anchor} label={applicationsUpnextOutcomeLabel({ label: interview.label })}>
        <MenuGroup>
          {(Object.keys(OUTCOME_LABEL) as Outcome[]).map((outcome) => (
            <MenuItem
              key={outcome}
              onSelect={() => {
                setOpen(false);
                onOutcome(outcome);
              }}
            >
              {OUTCOME_LABEL[outcome]()}
            </MenuItem>
          ))}
        </MenuGroup>
      </Menu>
    </>
  );
}

/** Every round: the ones to come first, soonest first, then the past ones,
 *  latest first. A round to come offers its call link; a past one asks how
 *  it went until the person says. */
function Interviews({ interviews, now, onEdit, onAdd, onOutcome }: {
  interviews: readonly ApplicationInterview[];
  now: Date;
  onEdit: (interview: ApplicationInterview) => void;
  onAdd: () => void;
  onOutcome: (interview: ApplicationInterview, outcome: Outcome) => void;
}) {
  const at = (one: ApplicationInterview) => new Date(one.scheduled_at).getTime();
  const coming = interviews.filter((one) => at(one) >= now.getTime()).sort((a, b) => at(a) - at(b));
  const past = interviews.filter((one) => at(one) < now.getTime()).sort((a, b) => at(b) - at(a));

  if (interviews.length === 0) {
    return (
      <div className="app-ws-empty">
        <p className="app-next-empty">{applicationsNextInterviewNone()}</p>
        <Button variant="ghost" size="sm" className="ui-btn-strong" onClick={onAdd}>{applicationsInterviewAdd()}</Button>
      </div>
    );
  }

  return (
    <>
      <ul className="app-ws-rounds">
        {[...coming, ...past].map((interview) => {
          const upcoming = at(interview) >= now.getTime();
          const when = interview.format
            ? applicationsNextInterviewMeta({ when: interviewWhen(interview), format: FORMAT_LABEL[interview.format]() })
            : interviewWhen(interview);
          return (
            <li key={interview.id} className="app-ws-round" data-past={upcoming ? undefined : true}>
              <div className="app-ws-round-head">
                <span className="app-ws-round-name"><Content text={interview.label} /></span>
                <span className="app-ws-round-when">{when}</span>
                <Button
                  variant="icon"
                  size="sm"
                  aria-label={applicationsInterviewEditLabel({ label: interview.label })}
                  onClick={() => onEdit(interview)}
                >
                  <Icon name="edit" size={14} />
                </Button>
                <span className="app-tile-spacer" />
                {upcoming && interview.link && (
                  <ExternalLink href={interview.link} label={applicationsNextInterviewJoinLabel({ label: interview.label })}>
                    {applicationsNextInterviewJoin()}
                  </ExternalLink>
                )}
                {!upcoming && !interview.outcome && <OutcomeAsk interview={interview} onOutcome={(outcome) => onOutcome(interview, outcome)} />}
                {interview.outcome && <span className="app-ws-round-outcome">{OUTCOME_LABEL[interview.outcome]()}</span>}
              </div>
              {interview.notes && <p className="app-ws-round-notes"><Content text={interview.notes} /></p>}
            </li>
          );
        })}
      </ul>
      <Button variant="ghost" size="sm" className="app-ws-add" onClick={onAdd}>
        <Icon name="plus" size={14} />
        {applicationsInterviewAdd()}
      </Button>
    </>
  );
}

/* ---- Notes -------------------------------------------------------------- */

const SAVE_AFTER_MS = 800;

/** The role's notes page, saved as it is typed: a pause or leaving the field
 *  saves it. While the field has focus, what the person types wins over a
 *  re-read that lands meanwhile. */
function Notes({ notes, onSave }: { notes: string | null; onSave: (notes: string) => Promise<boolean> }) {
  const [draft, setDraft] = useState(notes ?? "");
  const [focused, setFocused] = useState(false);
  const field = useRef<HTMLTextAreaElement>(null);
  const timer = useRef<number | null>(null);
  const sent = useRef(notes ?? "");

  useEffect(() => {
    if (!focused) {
      setDraft(notes ?? "");
      sent.current = notes ?? "";
    }
  }, [notes, focused]);

  // The field grows with its text, so the page scrolls, not the field.
  useEffect(() => {
    const element = field.current;
    if (!element) return;
    element.style.height = "auto";
    element.style.height = `${element.scrollHeight}px`;
  }, [draft]);

  const flush = (value: string) => {
    if (timer.current != null) window.clearTimeout(timer.current);
    timer.current = null;
    if (value === sent.current) return;
    sent.current = value;
    void onSave(value);
  };

  useEffect(() => () => {
    if (timer.current != null) window.clearTimeout(timer.current);
  }, []);

  return (
    <textarea
      ref={field}
      className="app-ws-notes"
      aria-label={applicationsNotesLabel()}
      placeholder={applicationsWsNotesHint()}
      rows={3}
      maxLength={20_000}
      value={draft}
      onFocus={() => setFocused(true)}
      onBlur={() => {
        setFocused(false);
        flush(draft);
      }}
      onChange={(event) => {
        const value = event.target.value;
        setDraft(value);
        if (timer.current != null) window.clearTimeout(timer.current);
        timer.current = window.setTimeout(() => flush(value), SAVE_AFTER_MS);
      }}
    />
  );
}

/* ---- Outcome and history ------------------------------------------------ */

function OutcomeLine({ card }: { card: ApplicationCard }) {
  return (
    <p className="app-ws-outcome">
      <strong>{endingName(card) ?? STAGE_LABEL[card.stage]}</strong>
      {card.stage_since && <span className="app-ws-round-when">{formatDate(card.stage_since, "full")}</span>}
    </p>
  );
}

/** The stages the role reached, in order, then the comments written on it,
 *  newest first. */
function History({ detail, items, now, onEditComment, onDeleteComment }: {
  detail: ApplicationDetail;
  items: readonly ActivityItem[];
  now: Date;
  onEditComment: (id: number, body: string) => Promise<boolean>;
  onDeleteComment: (id: number) => Promise<boolean>;
}) {
  const reached = [...detail.stages_reached].sort((a, b) => new Date(a.at).getTime() - new Date(b.at).getTime());
  const comments = items.filter((item): item is ActivityComment => item.kind === "comment");
  return (
    <>
      <ol className="app-ws-path">
        {reached.map((step) => (
          <li key={`${step.stage}-${step.at}`}>
            <span className="app-ws-path-dot" aria-hidden="true" />
            <span className="app-ws-path-stage">{STAGE_LABEL[boardStage(step.stage)]}</span>
            <time className="app-ws-round-when" dateTime={step.at}>{formatDate(step.at, "day")}</time>
          </li>
        ))}
      </ol>
      {comments.length > 0 && (
        <ol className="app-feed-list app-ws-comments">
          {comments.map((comment) => (
            <CommentItem key={comment.id} comment={comment} now={now} onEdit={onEditComment} onDelete={onDeleteComment} />
          ))}
        </ol>
      )}
    </>
  );
}

/* ---- The Workspace ------------------------------------------------------ */

export interface WorkspaceProps {
  card: ApplicationCard;
  detail: ApplicationDetail;
  notes: string | null;
  activity: readonly ActivityItem[];
  now: Date;
  onSetNext: (text: string | null, due: string | null) => Promise<boolean>;
  onFinishStep: () => void;
  onSaveNotes: (notes: string) => Promise<boolean>;
  onAddInterview: () => void;
  onEditInterview: (interview: ApplicationInterview) => void;
  onOutcome: (interview: ApplicationInterview, outcome: Outcome) => void;
  onEditComment: (id: number, body: string) => Promise<boolean>;
  onDeleteComment: (id: number) => Promise<boolean>;
}

/** The person's own work on the role: the fixed sections the stage asks for,
 *  each a labelled row, and the notes page. Sections shows and hides them,
 *  per stage, in this browser. */
export function Workspace(props: WorkspaceProps) {
  const { card, detail, notes, activity, now } = props;
  const stage = workspaceStage(card);
  const [hidden, setHidden] = useState(() => readHiddenSections(stage));
  const [menuAnchor, setMenuAnchor] = useState<HTMLButtonElement | null>(null);
  const [menuOpen, setMenuOpen] = useState(false);

  // A move to another stage brings that stage's own choice.
  useEffect(() => setHidden(readHiddenSections(stage)), [stage]);

  const offered = offeredSections(stage);
  const shown = offered.filter((section) => !hidden.includes(section));
  const toggle = (section: WorkspaceSection, on: boolean) => {
    const next = on ? hidden.filter((one) => one !== section) : [...hidden, section];
    // The Workspace always shows one section.
    if (offered.every((one) => next.includes(one))) return;
    writeHiddenSections(stage, next);
    setHidden(next);
  };

  const body: Record<WorkspaceSection, () => ReactNode> = {
    interviews: () => (
      <Interviews
        interviews={detail.interviews}
        now={now}
        onEdit={props.onEditInterview}
        onAdd={props.onAddInterview}
        onOutcome={props.onOutcome}
      />
    ),
    next: () => <NextStep card={card} now={now} onSetNext={props.onSetNext} onFinish={props.onFinishStep} />,
    notes: () => <Notes notes={notes} onSave={props.onSaveNotes} />,
    outcome: () => <OutcomeLine card={card} />,
    history: () => (
      <History
        detail={detail}
        items={activity}
        now={now}
        onEditComment={props.onEditComment}
        onDeleteComment={props.onDeleteComment}
      />
    ),
  };

  return (
    <div className="app-ws">
      {shown.map((section) => <Row key={section} section={section}>{body[section]()}</Row>)}
      <div className="app-ws-foot">
        <Button
          ref={setMenuAnchor}
          variant="ghost"
          size="sm"
          className="app-ws-sections"
          aria-haspopup="dialog"
          aria-expanded={menuOpen}
          onClick={() => setMenuOpen((open) => !open)}
        >
          <Icon name="sliders" size={14} />
          {applicationsWsSections()}
        </Button>
        <Menu isOpen={menuOpen} onClose={() => setMenuOpen(false)} anchor={menuAnchor} align="start" label={applicationsWsSectionsLabel()}>
          <MenuGroup>
            {offered.map((section) => (
              <MenuCheck key={section} checked={!hidden.includes(section)} onChange={(on) => toggle(section, on)}>
                {SECTION_LABEL[section]()}
              </MenuCheck>
            ))}
          </MenuGroup>
        </Menu>
      </div>
    </div>
  );
}

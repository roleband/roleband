import { FormEvent, useEffect, useId, useRef, useState } from "react";
import type { ApplicationStep } from "../../api";
import { date as formatDate } from "../../copy/format";
import { recordDay } from "./recordDays";
import { Button, Content, Icon, useEscapeLayer } from "../../ui";
import {
  applicationsInterviewCancel,
  applicationsNextSave,
  applicationsUpnextDoneLabel,
  applicationsWsNextAdd,
  applicationsWsNextDelete,
  applicationsWsNextDeleteConfirm,
  applicationsWsNextDeleteLabel,
  applicationsWsNextDoneFold,
  applicationsWsNextEdit,
  applicationsWsNextRemove,
} from "../../copy/gen/applications";
import { dueOfStep } from "./board";
import { DueBadge } from "./DueBadge";
import { DueField } from "./DueField";
import { useFocusAfter } from "./focusAfter";
import { GrowField } from "./GrowField";
import { dayKey, dueFromDay } from "./monthGrid";

function StepForm({ id, text: initialText, day: initialDay, now, placeholder, label, focusFirst, onSave, onSaved, onCancel, onRemove }: {
  /** The words field's id, for a label beside the form. */
  id?: string;
  text: string;
  day: string;
  now: Date;
  placeholder?: string;
  label: string;
  focusFirst: boolean;
  onSave: (text: string, day: string) => Promise<boolean>;
  /** An edit's close, once its save landed with nothing typed since; without
   *  it the form is the add line, which clears instead. */
  onSaved?: () => void;
  onCancel?: () => void;
  /** Takes the step off the list with nothing kept: for one added by mistake. */
  onRemove?: () => void;
}) {
  const [text, setText] = useState(initialText);
  const [day, setDay] = useState(initialDay);
  const [saving, setSaving] = useState(false);
  // Read by the handler, not the render: two quick Enters save once.
  const inFlight = useRef(false);
  // What the fields hold now, for a save that lands after more was typed.
  const typed = useRef({ text, day });
  typed.current = { text, day };
  const field = useRef<HTMLTextAreaElement>(null);
  const dueId = useId();

  useEffect(() => {
    if (focusFirst) field.current?.focus();
  }, [focusFirst]);

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    if (!text.trim() || inFlight.current) return;
    inFlight.current = true;
    setSaving(true);
    const sent = { text, day };
    try {
      const saved = await onSave(text.trim(), day);
      // What was typed while it saved stays, for the next save: the add line
      // clears and an edit closes only when nothing was.
      if (saved && typed.current.text === sent.text && typed.current.day === sent.day) {
        if (onSaved) onSaved();
        else {
          setText("");
          setDay("");
        }
      }
    } finally {
      inFlight.current = false;
      setSaving(false);
    }
  };
  // While an edit is open, Escape leaves it as it was, and the posting under
  // it stays.
  useEscapeLayer(onCancel != null, onCancel);

  // The words take the whole width and grow with what is typed; the day and
  // the buttons wait on the line below.
  return (
    <form className="app-ws-step-form" onSubmit={submit}>
      <GrowField
        id={id}
        fieldRef={field}
        className="app-ws-step-input"
        aria-label={label}
        placeholder={placeholder}
        rows={1}
        maxLength={2_000}
        value={text}
        onChange={setText}
      />
      {/* An edit always offers its way out, whatever is typed. */}
      {(text.trim() || day || onCancel) && (
        <div className="app-ws-step-actions">
          <DueField id={dueId} day={day} onDay={setDay} now={now} />
          <span className="app-tile-spacer" />
          {onRemove && <Button variant="ghost" size="sm" onClick={onRemove}>{applicationsWsNextRemove()}</Button>}
          {onCancel && <Button variant="ghost" size="sm" onClick={onCancel}>{applicationsInterviewCancel()}</Button>}
          <Button variant="ghost" size="sm" className="ui-btn-strong" type="submit" disabled={!text.trim() || saving}>
            {applicationsNextSave()}
          </Button>
        </div>
      )}
    </form>
  );
}

/** One open step: a tick to finish it, its words, its day and the button
 *  that changes it. Long words wrap in their own column; the tick, the day and
 *  the button stay level with the first line. */
function StepRow({ step, now, editRef, onFinish, onEdit }: {
  step: ApplicationStep;
  now: Date;
  editRef: (button: HTMLButtonElement | null) => void;
  onFinish: () => void;
  onEdit: () => void;
}) {
  const due = dueOfStep(step);
  return (
    <div className="app-ws-step">
      <Button
        variant="icon"
        size="sm"
        className="ui-btn-tick app-upnext-tick"
        aria-label={applicationsUpnextDoneLabel({ step: step.text })}
        aria-pressed={false}
        onClick={onFinish}
      >
        <Icon name="check" size={12} />
      </Button>
      <span className="app-ws-step-words"><Content text={step.text} /></span>
      {due && <span className="app-ws-step-due"><DueBadge due={due} now={now} /></span>}
      <Button
        ref={editRef}
        variant="icon"
        size="sm"
        className="app-row-tool"
        aria-label={applicationsWsNextEdit({ step: step.text })}
        onClick={onEdit}
      >
        <Icon name="edit" size={14} />
      </Button>
    </div>
  );
}

/** One step that is done: its tick, pressed, opens it again; its words are
 *  struck through, with the day it was done; its delete asks first. */
function DoneRow({ step, now, onReopen, onDelete }: {
  step: ApplicationStep;
  now: Date;
  onReopen: () => void;
  onDelete: () => void;
}) {
  const [confirming, setConfirming] = useState(false);
  const bin = useRef<HTMLButtonElement>(null);
  // Leaving the question puts the focus back on the bin that asked it, as the
  // question's own buttons go with it.
  const keep = () => {
    setConfirming(false);
    bin.current?.focus();
  };
  // While the delete question is open, Escape leaves just that.
  useEscapeLayer(confirming, keep);
  return (
    <>
      <div className="app-ws-step" data-done="">
        <Button
          variant="icon"
          size="sm"
          className="ui-btn-tick app-upnext-tick"
          aria-label={applicationsUpnextDoneLabel({ step: step.text })}
          aria-pressed
          onClick={onReopen}
        >
          <Icon name="check" size={12} />
        </Button>
        <span className="app-ws-step-words"><Content text={step.text} /></span>
        {step.done_at && (
          <time className="app-ws-step-when" dateTime={step.done_at} title={formatDate(step.done_at, "full")}>
            {recordDay(step.done_at, now)}
          </time>
        )}
        <Button
          ref={bin}
          variant="icon"
          size="sm"
          className="app-row-tool"
          aria-label={applicationsWsNextDeleteLabel({ step: step.text })}
          onClick={() => setConfirming(true)}
        >
          <Icon name="trash" size={14} />
        </Button>
      </div>
      {confirming && (
        <div className="app-comment-confirm app-ws-step-confirm" role="group" aria-label={applicationsWsNextDeleteConfirm()}>
          <span>{applicationsWsNextDeleteConfirm()}</span>
          <Button variant="ghost" size="sm" onClick={keep}>{applicationsInterviewCancel()}</Button>
          <Button
            variant="danger"
            size="sm"
            onClick={() => {
              setConfirming(false);
              onDelete();
            }}
          >
            {applicationsWsNextDelete()}
          </Button>
        </div>
      )}
    </>
  );
}

/** The steps already done, the latest first, folded under one line that says
 *  how many. */
function DoneSteps({ done, now, onReopen, onRemove, outside }: {
  done: readonly ApplicationStep[];
  now: Date;
  onReopen: (step: ApplicationStep) => Promise<boolean>;
  onRemove: (step: ApplicationStep) => Promise<boolean>;
  /** Where the keyboard goes once no done step is left. */
  outside: () => HTMLElement | null;
}) {
  const [open, setOpen] = useState(false);
  const listId = useId();
  const box = useRef<HTMLDivElement>(null);
  const focusAfter = useFocusAfter();
  /** Where the keyboard goes when a step leaves this list: the done step after
   *  it, else the one before, else out of the list. */
  const nextFocus = (step: ApplicationStep) => {
    const at = done.findIndex((one) => one.id === step.id);
    const neighbour = done[at + 1] ?? done[at - 1];
    return () =>
      (neighbour && box.current?.querySelector<HTMLElement>(`[data-step-id="${neighbour.id}"] .ui-btn-tick`)) || outside();
  };
  if (done.length === 0) return null;
  return (
    <div className="app-ws-done" ref={box}>
      <Button
        variant="link"
        className="ui-btn-quiet app-ws-done-toggle"
        aria-expanded={open}
        aria-controls={open ? listId : undefined}
        onClick={() => setOpen((was) => !was)}
      >
        <Icon name={open ? "chevronDown" : "chevronRight"} size={12} />
        {applicationsWsNextDoneFold({ count: done.length })}
      </Button>
      {open && (
        <ul id={listId} className="app-ws-step-list">
          {done.map((step) => (
            <li key={step.id} data-step-id={step.id}>
              <DoneRow
                now={now}
                step={step}
                onReopen={() => {
                  focusAfter(nextFocus(step));
                  void onReopen(step);
                }}
                onDelete={() => {
                  focusAfter(nextFocus(step));
                  void onRemove(step);
                }}
              />
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

/** Every open next step, soonest first, steps with no day last in the order
 *  added; one at a time is changed in place. The line under the last is where
 *  the next one is typed. A ticked step moves to the done steps folded under
 *  it, where its tick opens it again and its delete takes it off for good. */
export function NextSteps({ steps, done, now, onAdd, onEdit, onFinish, onReopen, onRemove }: {
  steps: readonly ApplicationStep[];
  done: readonly ApplicationStep[];
  now: Date;
  onAdd: (text: string, due: string | null) => Promise<boolean>;
  onEdit: (step: ApplicationStep, text: string, due: string | null) => Promise<boolean>;
  onFinish: (step: ApplicationStep) => void;
  onReopen: (step: ApplicationStep) => Promise<boolean>;
  onRemove: (step: ApplicationStep) => Promise<boolean>;
}) {
  // The step whose edit is open, and which opening of it: an edit left and
  // opened again is a new session, which a save sent from the old one never
  // closes.
  const [editing, setEditing] = useState<{ id: number; session: number } | null>(null);
  const sessions = useRef(0);
  // Read when a save lands: the person may have left that edit for another.
  const editingNow = useRef(editing);
  editingNow.current = editing;
  const edits = useRef(new Map<number, HTMLButtonElement>());
  const box = useRef<HTMLDivElement>(null);
  const addId = useId();
  const focusAfter = useFocusAfter();
  const addField = () => box.current?.querySelector<HTMLElement>(".app-ws-step-add textarea") ?? null;
  /** Where the keyboard goes when a step leaves the list: the step after it,
   *  else the one before, else the line that adds one. */
  const nextFocus = (step: ApplicationStep) => {
    const at = steps.findIndex((one) => one.id === step.id);
    const neighbour = steps[at + 1] ?? steps[at - 1];
    return () =>
      (neighbour && box.current?.querySelector<HTMLElement>(`[data-step-id="${neighbour.id}"] .ui-btn-tick`)) || addField();
  };
  const open = (step: ApplicationStep) => {
    sessions.current += 1;
    setEditing({ id: step.id, session: sessions.current });
  };
  /** Closes the step's edit, if it is still the one open (and, given a
   *  session, still that opening of it). */
  const close = (step: ApplicationStep, session?: number) => {
    const now = editingNow.current;
    if (now?.id !== step.id || (session != null && now.session !== session)) return;
    focusAfter(() => edits.current.get(step.id) ?? addField());
    setEditing(null);
  };

  return (
    <div className="app-ws-steps" ref={box}>
      {steps.length > 0 && (
        <ul className="app-ws-step-list">
          {steps.map((step) => (
            <li key={step.id} data-step-id={step.id}>
              {editing?.id === step.id ? (
                <StepForm
                  text={step.text}
                  day={step.due ? dayKey(new Date(step.due)) : ""}
                  now={now}
                  label={applicationsWsNextEdit({ step: step.text })}
                  focusFirst
                  onSave={(text, day) => onEdit(step, text, day ? dueFromDay(day) : null)}
                  onSaved={() => close(step, editing.session)}
                  onCancel={() => close(step)}
                  onRemove={async () => {
                    focusAfter(nextFocus(step));
                    if (await onRemove(step)) setEditing((shown) => (shown?.id === step.id ? null : shown));
                  }}
                />
              ) : (
                <StepRow
                  step={step}
                  now={now}
                  editRef={(button) => {
                    if (button) edits.current.set(step.id, button);
                    else edits.current.delete(step.id);
                  }}
                  onFinish={() => {
                    focusAfter(nextFocus(step));
                    onFinish(step);
                  }}
                  onEdit={() => open(step)}
                />
              )}
            </li>
          ))}
        </ul>
      )}
      {/* The line that adds a step is a row of the list: a plus stands where a
          step's tick does, so the field reads as one more step, never as part
          of the step above. The plus is the field's own label, for the pointer. */}
      <div className="app-ws-step-add">
        <label className="app-ws-step-plus" htmlFor={addId} aria-hidden="true">
          <Icon name="plus" size={14} />
        </label>
        <StepForm
          id={addId}
          text=""
          day=""
          now={now}
          placeholder={applicationsWsNextAdd()}
          label={applicationsWsNextAdd()}
          focusFirst={false}
          onSave={(text, day) => onAdd(text, day ? dueFromDay(day) : null)}
        />
      </div>
      <DoneSteps done={done} now={now} onReopen={onReopen} onRemove={onRemove} outside={addField} />
    </div>
  );
}

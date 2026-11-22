import { FormEvent, useEffect, useId, useRef, useState } from "react";
import type { ApplicationStep } from "../../api";
import { Button, Content, Icon, useEscapeLayer } from "../../ui";
import {
  applicationsInterviewCancel,
  applicationsNextSave,
  applicationsUpnextDoneLabel,
  applicationsWsNextAdd,
  applicationsWsNextDue,
  applicationsWsNextEdit,
  applicationsWsNextRemove,
} from "../../copy/gen/applications";
import { dueOfStep } from "./board";
import { DueBadge } from "./DueBadge";
import { useFocusAfter } from "./focusAfter";
import { GrowField } from "./GrowField";
import { dayKey, dueFromDay } from "./monthGrid";

function StepForm({ text: initialText, day: initialDay, placeholder, label, focusFirst, onSave, onCancel, onRemove }: {
  text: string;
  day: string;
  placeholder?: string;
  label: string;
  focusFirst: boolean;
  onSave: (text: string, day: string) => Promise<boolean>;
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
      // The add line clears what it sent, and keeps a next step typed while it saved.
      if (saved && !onCancel && typed.current.text === sent.text && typed.current.day === sent.day) {
        setText("");
        setDay("");
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
          <label className="app-ws-step-due-label" htmlFor={dueId}>{applicationsWsNextDue()}</label>
          <input id={dueId} className="app-ws-step-day" type="date" value={day} onChange={(event) => setDay(event.target.value)} />
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

/** Every open next step, soonest first, steps with no day last in the order
 *  added; one at a time is changed in place. The line under the last is where
 *  the next one is typed. A ticked step leaves the list and stays in the
 *  role's history; its toast puts it back. */
export function NextSteps({ steps, now, onAdd, onEdit, onFinish, onRemove }: {
  steps: readonly ApplicationStep[];
  now: Date;
  onAdd: (text: string, due: string | null) => Promise<boolean>;
  onEdit: (step: ApplicationStep, text: string, due: string | null) => Promise<boolean>;
  onFinish: (step: ApplicationStep) => void;
  onRemove: (step: ApplicationStep) => Promise<boolean>;
}) {
  const [editing, setEditing] = useState<number | null>(null);
  // Read when a save lands: the person may have left that edit for another.
  const editingNow = useRef(editing);
  editingNow.current = editing;
  const edits = useRef(new Map<number, HTMLButtonElement>());
  const box = useRef<HTMLDivElement>(null);
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
  /** Closes the step's edit, if it is still the one open. */
  const close = (step: ApplicationStep) => {
    if (editingNow.current !== step.id) return;
    focusAfter(() => edits.current.get(step.id) ?? addField());
    setEditing(null);
  };

  return (
    <div className="app-ws-steps" ref={box}>
      {steps.length > 0 && (
        <ul className="app-ws-step-list">
          {steps.map((step) => (
            <li key={step.id} data-step-id={step.id}>
              {editing === step.id ? (
                <StepForm
                  text={step.text}
                  day={step.due ? dayKey(new Date(step.due)) : ""}
                  label={applicationsWsNextEdit({ step: step.text })}
                  focusFirst
                  onSave={async (text, day) => {
                    const saved = await onEdit(step, text, day ? dueFromDay(day) : null);
                    if (saved) close(step);
                    return saved;
                  }}
                  onCancel={() => close(step)}
                  onRemove={async () => {
                    focusAfter(nextFocus(step));
                    if (await onRemove(step)) setEditing((open) => (open === step.id ? null : open));
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
                  onEdit={() => setEditing(step.id)}
                />
              )}
            </li>
          ))}
        </ul>
      )}
      <div className="app-ws-step-add">
        <StepForm
          text=""
          day=""
          placeholder={applicationsWsNextAdd()}
          label={applicationsWsNextAdd()}
          focusFirst={false}
          onSave={(text, day) => onAdd(text, day ? dueFromDay(day) : null)}
        />
      </div>
    </div>
  );
}

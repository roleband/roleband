// Card: Top picks, once it is set up. The person's own assistant reads the
// new roles of each scan through the `roleband` command and keeps the few
// worth a move. This card is where the person pauses it, sees which assistant
// checks and when it last did, reads what it looks for, bounds how much it
// reads a day, and takes back what they gave it.
//
// The card is drawn only once Top picks is set up: before that, the Top picks
// screen is where a person starts, and an empty card here would offer nothing
// to change. A failed read draws nothing either, for the same reason.
import { useCallback, useEffect, useId, useRef, useState, type FormEvent } from "react";
import { api, type PicksState } from "../../api";
import { errorText } from "../../api/errorText";
import { numberInput, parseNumber, relative } from "../../copy/format";
import {
  aiAimLineCancel,
  aiAssistantsCardClipboardAccessWasBlockedSelect,
  aiAssistantsCardCopy,
  aiTopPicksCardBrief,
  aiTopPicksCardBriefNone,
  aiTopPicksCardCheck,
  aiTopPicksCardCheckNote,
  aiTopPicksCardCopySentence,
  aiTopPicksCardLimit,
  aiTopPicksCardLimitFailed,
  aiTopPicksCardLimitNote,
  aiTopPicksCardLimitRange,
  aiTopPicksCardPauseFailed,
  aiTopPicksCardRemove,
  aiTopPicksCardRemoveConfirm,
  aiTopPicksCardRemoveConfirmTitle,
  aiTopPicksCardRemoveFailed,
  aiTopPicksCardRemoveNote,
  aiTopPicksCardRemoveTitle,
  aiTopPicksCardRemoved,
  aiTopPicksCardSentence,
  aiTopPicksCardStatus,
} from "../../copy/gen/ai";
import { picksHost, picksResumeFailed } from "../../copy/gen/picks";
import { shellNavTopPicks } from "../../copy/gen/shell";
import { Button, Content, Dialog, Icon, Switch, useToast } from "../../ui";
import { OriginBadge } from "./OriginBadge";

/** The status line's case. */
export type StatusCase =
  | "checked" | "first" | "late" | "stopped"
  | "disconnected" | "asks" | "read-only"
  | "paused-checked" | "paused";

/** Which case the status line says. Off says only that, with the last check
 *  when there was one. On, a connection that keeps the checks from running
 *  comes first, since nothing else on the line can change until it is put
 *  right; then how the last check ended; then whether one has finished. */
export function statusCase(state: PicksState): StatusCase {
  const check = state.last_check;
  if (state.state !== "on") return check ? "paused-checked" : "paused";
  if (state.routine_host && state.routine_host_connection === null) return "disconnected";
  if (state.routine_host_connection === "rule_missing") return "asks";
  if (state.routine_host_connection === "read_only") return "read-only";
  if (!check || state.health === "never_ran") return "first";
  if (state.health === "stopped_early") return "stopped";
  if (state.health === "late") return "late";
  return "checked";
}

/** The cases that need the person's eye, which wear the warning dot. */
const NEEDS_ATTENTION: ReadonlySet<StatusCase> = new Set(["late", "stopped", "disconnected", "asks", "read-only"]);
/** The cases where the checks run as they should, which end with the
 *  schedule, in the assistant's own words. */
const SAYS_SCHEDULE: ReadonlySet<StatusCase> = new Set(["checked", "first"]);
/** The cases that say when the last check was, and so name who made it. */
const SAYS_WHEN: ReadonlySet<StatusCase> = new Set(["checked", "late", "stopped", "paused-checked"]);

const ago = (at: string) => relative((Date.parse(at) - Date.now()) / 1000);

/** A daily limit as typed, or null when it is not a whole number from 1 to
 *  `max` (the route refuses anything else). */
function readLimit(text: string, max: number): number | null {
  const value = parseNumber(text);
  return Number.isInteger(value) && value >= 1 && value <= max ? value : null;
}

export function TopPicksCard() {
  const [state, setState] = useState<PicksState | null>(null);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [removing, setRemoving] = useState(false);
  const headingId = useId();

  // Counts the requests started. A read answers only if nothing started after
  // it: a save started or finished after it answers with the mode as saved,
  // which the read may predate.
  const requests = useRef(0);
  useEffect(() => {
    const ticket = ++requests.current;
    api.picksState()
      .then((next) => {
        if (requests.current === ticket) setState(next);
      })
      .catch(() => undefined);
  }, []);

  const save = useCallback(async (write: () => Promise<PicksState>, failed: string) => {
    requests.current += 1;
    setSaving(true);
    setError(null);
    try {
      const next = await write();
      requests.current += 1;
      setState(next);
    } catch (e) {
      setError(errorText(e, failed));
    } finally {
      setSaving(false);
    }
  }, []);

  const onRemoved = useCallback(() => {
    requests.current += 1;
    setRemoving(false);
    setState(null);
  }, []);

  if (state == null || state.state === "never_set_up") return null;

  const on = state.state === "on";
  const toggle = (next: boolean) => next
    ? save(() => api.setPicksMode("on"), picksResumeFailed())
    : save(() => api.setPicksMode("off"), aiTopPicksCardPauseFailed());
  const saveLimit = (limit: number) => save(() => api.setPicksDailyLimit(limit), aiTopPicksCardLimitFailed());

  return (
    <section className="intel-card" aria-labelledby={headingId} data-testid="top-picks-card">
      <div className="intel-head">
        <div className="intel-head-title">
          <h2 id={headingId}>{shellNavTopPicks()}</h2>
          <OriginBadge origin="cloud" />
        </div>
        <StatusLine state={state} />
      </div>

      <div className="intel-picks-gate">
        <Switch
          checked={on}
          disabled={saving}
          onChange={(next) => void toggle(next)}
          label={aiTopPicksCardCheck()}
        />
        <div className="intel-access-gate-copy">
          <b className="intel-grant-name">{aiTopPicksCardCheck()}</b>
          <span className="intel-access-gate-note">{aiTopPicksCardCheckNote()}</span>
        </div>
      </div>

      <div className="intel-picks-row">
        <div className="intel-picks-row-copy">
          <h3 className="intel-picks-row-name">{aiTopPicksCardBrief()}</h3>
          {state.brief_summary ? (
            <Content className="intel-picks-row-note intel-picks-brief" text={state.brief_summary} />
          ) : (
            <span className="intel-picks-row-note">{aiTopPicksCardBriefNone()}</span>
          )}
        </div>
        <CopySentence />
      </div>

      <DailyLimit value={state.daily_limit} max={state.daily_limit_max} saving={saving} onSave={saveLimit} />

      <div className="intel-picks-row">
        <div className="intel-picks-row-copy">
          <h3 className="intel-picks-row-name">{aiTopPicksCardRemoveTitle()}</h3>
          <span className="intel-picks-row-note">{aiTopPicksCardRemoveNote()}</span>
        </div>
        <Button variant="danger" disabled={saving} onClick={() => setRemoving(true)}>
          {aiTopPicksCardRemove()}
        </Button>
      </div>

      {error && <div className="intel-error" role="alert">{error}</div>}

      {removing && <RemoveDialog onCancel={() => setRemoving(false)} onRemoved={onRemoved} />}
    </section>
  );
}

/** Which assistant checks and when it last did, in the card's head. */
function StatusLine({ state }: { state: PicksState }) {
  const kind = statusCase(state);
  const check = state.last_check;
  const when = SAYS_WHEN.has(kind) && check ? check : null;
  const host = picksHost({ host: when?.host ?? state.routine_host ?? check?.host ?? "" });
  const schedule = SAYS_SCHEDULE.has(kind) ? state.schedule?.trim() : null;
  return (
    <span className="intel-aside intel-picks-status" data-status={kind}>
      {NEEDS_ATTENTION.has(kind) && <span className="intel-dot is-warn" aria-hidden="true" />}
      <span>
        {aiTopPicksCardStatus({ state: kind, host, when: when ? ago(when.finished_at) : "" })}
        {schedule && <>{" · "}<Content text={schedule} /></>}
      </span>
    </span>
  );
}

/** The sentence the person says to their assistant to change what it looks
 *  for, as one control that copies it. */
function CopySentence() {
  const [copied, setCopied] = useState(false);
  const [failed, setFailed] = useState(false);
  const sentence = aiTopPicksCardSentence();
  const name = aiTopPicksCardCopySentence({ sentence });
  const copy = async () => {
    try {
      await navigator.clipboard.writeText(sentence);
      setCopied(true);
      setFailed(false);
    } catch {
      setCopied(false);
      setFailed(true);
    }
  };
  return (
    <div className="intel-picks-copy">
      <Button className="ui-btn-strong intel-picks-sentence" aria-label={name} title={name} onClick={() => void copy()}>
        <code>{sentence}</code>
        <Icon name={copied ? "check" : "copy"} size={15} />
      </Button>
      <span className="sr-only" role="status">{copied ? aiAssistantsCardCopy({ choice: "yes" }) : ""}</span>
      {failed && <span className="intel-picks-field-note" role="alert">{aiAssistantsCardClipboardAccessWasBlockedSelect()}</span>}
    </div>
  );
}

/** How many roles the assistant reads in a day, at most. Saved on Enter or
 *  on leaving the field, and only as a whole number the route takes; a draft
 *  it would refuse is marked and said under the field, and never sent. */
function DailyLimit({ value, max, saving, onSave }: {
  value: number;
  max: number;
  saving: boolean;
  onSave: (limit: number) => void;
}) {
  const [draft, setDraft] = useState(() => numberInput(value));
  // The saved limit replaces the draft: after a save, or when the assistant
  // changed it.
  useEffect(() => setDraft(numberInput(value)), [value]);
  const id = useId();
  const noteId = useId();
  const rangeId = useId();
  const read = readLimit(draft, max);
  // Nothing is sent while any save of the card is on its way: each answers
  // with the whole state, so two at once could land out of order. Enter and
  // then leaving the field therefore write once, and what was typed stays to
  // send once the other save is done.
  const commit = () => {
    if (saving || read == null || read === value) return;
    onSave(read);
  };
  const submit = (event: FormEvent) => {
    event.preventDefault();
    commit();
  };
  return (
    <form className="intel-picks-row" onSubmit={submit}>
      <div className="intel-picks-row-copy">
        <label className="intel-picks-row-name" htmlFor={id}>{aiTopPicksCardLimit()}</label>
        <span className="intel-picks-row-note" id={noteId}>{aiTopPicksCardLimitNote()}</span>
        {read == null && (
          <span className="intel-picks-field-note" id={rangeId} role="alert">
            {aiTopPicksCardLimitRange({ max })}
          </span>
        )}
      </div>
      <input
        id={id}
        className="intel-picks-limit"
        type="text"
        inputMode="numeric"
        autoComplete="off"
        value={draft}
        // Read-only, not disabled, while it saves: a disabled field drops the
        // keyboard's place.
        readOnly={saving}
        aria-invalid={read == null || undefined}
        aria-describedby={[noteId, read == null ? rangeId : null].filter(Boolean).join(" ")}
        onChange={(event) => setDraft(event.target.value)}
        onBlur={commit}
      />
    </form>
  );
}

/** Remove, asked first: it deletes what cannot be brought back. The card is
 *  gone once it is done, so a toast says it was. */
function RemoveDialog({ onCancel, onRemoved }: { onCancel: () => void; onRemoved: () => void }) {
  const { toast } = useToast();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const remove = async () => {
    setBusy(true);
    setError(null);
    try {
      await api.removePicksSetup();
      toast({ key: "top-picks", text: aiTopPicksCardRemoved() });
      onRemoved();
    } catch (e) {
      setError(errorText(e, aiTopPicksCardRemoveFailed()));
      setBusy(false);
    }
  };
  return (
    <Dialog
      isOpen
      onClose={busy ? () => undefined : onCancel}
      label={aiTopPicksCardRemoveConfirmTitle()}
      width={440}
      closeOnScrim={false}
      className="app-overlay"
    >
      <div className="ledger-form ledger-confirm">
        <h3>{aiTopPicksCardRemoveConfirmTitle()}</h3>
        <p>{aiTopPicksCardRemoveConfirm()}</p>
        {error && <p className="ledger-form-error" role="alert">{error}</p>}
        <div className="ledger-form-actions">
          <Button onClick={onCancel} disabled={busy}>{aiAimLineCancel()}</Button>
          <Button variant="danger" onClick={() => void remove()} disabled={busy}>{aiTopPicksCardRemove()}</Button>
        </div>
      </div>
    </Dialog>
  );
}

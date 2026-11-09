import { useEffect, useId, useMemo, useRef, useState } from "react";
import { time } from "../copy/format";
import { sharedTimeFieldChoose, sharedTimeFieldTimes } from "../copy/gen/shared";
import { Button } from "./Button";
import { Icon } from "./Icon";
import { Popover } from "./Popover";
import "./TimeField.css";

const DAY = 24 * 60;
/** The list offers every half hour; a time between them is typed. */
const LIST_STEP = 30;
/** Where the list opens when the field holds no time yet. */
const EMPTY_OPENS_AT = 8 * 60;
/** How far PageUp and PageDown move: about one screen of the list. */
const PAGE = 8;

const wholeMinute = (minute: number) => ((Math.round(minute) % DAY) + DAY) % DAY;

/** A minute of the day as a time input's value: "07:30". */
const inputValue = (minute: number) => {
  const whole = wholeMinute(minute);
  return `${String(Math.floor(whole / 60)).padStart(2, "0")}:${String(whole % 60).padStart(2, "0")}`;
};

/** A minute of the day as the reader's clock writes it ("7:30 AM", "07:30"). */
export const clockText = (minute: number) => {
  const whole = wholeMinute(minute);
  return time(new Date(2000, 0, 1, Math.floor(whole / 60), whole % 60));
};

/** The list's times: every half hour, plus the field's own time when it falls
 *  between two of them, so the time the field holds is always in the list. */
export const listMinutes = (current: number | null) => {
  const steps = Array.from({ length: DAY / LIST_STEP }, (_, index) => index * LIST_STEP);
  if (current === null || current % LIST_STEP === 0) return steps;
  return [...steps, current].sort((a, b) => a - b);
};

export interface TimeFieldProps {
  /** The field's accessible name. */
  label: string;
  /** Minutes after midnight: the persisted time, or a live drag position;
   *  null shows an empty field (nothing set yet), and any time typed commits. */
  minute: number | null;
  /** The typed field's step, in seconds. */
  step: number;
  /** Not an editable control at all: no typing, no list. */
  locked: boolean;
  /** A save is out: the field keeps focus but takes no edit. */
  saving: boolean;
  onCommit: (minute: number) => void;
  /** A muted note beside each time in the list, such as when a scan done by
   *  that time starts. */
  hint?: (minute: number) => string;
  /** Draws the field's own edge. Off where the row around it is the control
   *  and carries the edge itself. */
  framed?: boolean;
}

/* A time of day: typed, or picked from a list of times.
 *
 * Typing commits on blur or Enter, never on `change`. A time input fires
 * `change` for every segment edit that leaves the value complete, so
 * committing there would persist the first keystroke of an edit: in a 12-hour
 * locale a single "1" typed into the hour of "10:00 PM" is already a complete
 * "01:00 PM". Held by tests/ux/schedule.spec.ts, which types rather than
 * filling: `fill()` never passes through a partial value.
 *
 * The browser's own picker is hidden (TimeField.css): the button beside the
 * field opens the list instead, so the choice looks like the rest of the app
 * and takes one click. Picking a time commits it at once.
 *
 * `readOnly` rather than `disabled` while the save is in flight: a disabled
 * field drops focus, and Enter commits with the caret still in the field.
 * `disabled` stays for the locked case, where the field is genuinely not an
 * editable control.
 */
export function TimeField({
  label,
  minute,
  step,
  locked,
  saving,
  onCommit,
  hint,
  framed = false,
}: TimeFieldProps) {
  const [typed, setTyped] = useState<string | null>(null);
  const [open, setOpen] = useState(false);
  const [active, setActive] = useState(0);
  const [field, setField] = useState<HTMLSpanElement | null>(null);
  const listRef = useRef<HTMLDivElement | null>(null);
  const opening = useRef(false);
  const id = useId();

  const current = minute === null ? null : wholeMinute(minute);
  const minutes = useMemo(() => listMinutes(current), [current]);

  const commit = () => {
    if (typed === null) return;
    setTyped(null);
    const [hour, minutePart] = typed.split(":").map(Number);
    if (Number.isNaN(hour) || Number.isNaN(minutePart)) return;
    const next = hour * 60 + minutePart;
    // Tabbing out of a field nobody changed is not a reschedule.
    if (next === minute) return;
    onCommit(next);
  };

  const openList = () => {
    const target = current ?? EMPTY_OPENS_AT;
    const at = minutes.findIndex((each) => each >= target);
    setActive(at === -1 ? minutes.length - 1 : at);
    opening.current = true;
    setOpen(true);
  };

  const pick = (next: number) => {
    // A typed time is still being saved: `current` is the time before it, so
    // a pick now could be judged "unchanged" and lose to the typed one.
    if (saving) return;
    setOpen(false);
    setTyped(null);
    if (next === current) return;
    onCommit(next);
  };

  // Keep the active time in view: centred as the list opens, so the times on
  // either side of the current one show too, then only as far as needed. The
  // list scrolls itself: `scrollIntoView` would scroll the page under it too.
  //
  // The list takes focus here, in this component's effect, and not in a
  // callback ref or the list's own effect: the overlay's effect runs before
  // this one and notes the focused element as the one to hand focus back to
  // on close, which has to be the button, not the list.
  useEffect(() => {
    const list = listRef.current;
    if (!open || !list) return;
    const option = list.children[active] as HTMLElement | undefined;
    if (!option) return;
    const top = option.offsetTop;
    const bottom = top + option.offsetHeight;
    if (opening.current) {
      list.focus();
      list.scrollTop = top - (list.clientHeight - option.offsetHeight) / 2;
    } else if (top < list.scrollTop) {
      list.scrollTop = top;
    } else if (bottom > list.scrollTop + list.clientHeight) {
      list.scrollTop = bottom - list.clientHeight;
    }
    opening.current = false;
  }, [open, active]);

  const onListKey = (key: React.KeyboardEvent) => {
    const last = minutes.length - 1;
    const moves: Record<string, (at: number) => number> = {
      ArrowDown: (at) => Math.min(at + 1, last),
      ArrowUp: (at) => Math.max(at - 1, 0),
      PageDown: (at) => Math.min(at + PAGE, last),
      PageUp: (at) => Math.max(at - PAGE, 0),
      Home: () => 0,
      End: () => last,
    };
    const move = moves[key.key];
    if (move) {
      key.preventDefault();
      setActive(move);
    } else if (key.key === "Enter" || key.key === " ") {
      key.preventDefault();
      pick(minutes[active]);
    }
  };

  return (
    <span ref={setField} className={`ui-timefield${framed ? " ui-timefield-framed" : ""}`}>
      <input
        type="time"
        step={step}
        aria-label={label}
        value={typed ?? (minute === null ? "" : inputValue(minute))}
        disabled={locked}
        readOnly={saving}
        aria-busy={saving || undefined}
        onChange={(change) => setTyped(change.target.value)}
        onBlur={commit}
        // Enter commits; abandoning an edit needs no key of its own, because
        // an inspector's own Escape closes it and React fires no blur on
        // unmount, so the pending value goes with it.
        onKeyDown={(key) => {
          if (key.key !== "Enter") return;
          key.preventDefault();
          commit();
        }}
      />
      {!locked && (
        <Button
          variant="icon"
          size="sm"
          className="ui-timefield-choose"
          aria-label={sharedTimeFieldChoose()}
          aria-haspopup="listbox"
          aria-expanded={open}
          // Not `disabled`: a keyboard pick starts the save in the same
          // render that closes the list, and focus goes back to this button,
          // which a disabled button would refuse.
          aria-disabled={saving || undefined}
          onClick={() => {
            if (saving) return;
            if (open) setOpen(false);
            else openList();
          }}
        >
          <Icon name="chevronDown" size={14} />
        </Button>
      )}
      <Popover
        isOpen={open}
        onClose={() => setOpen(false)}
        anchor={field}
        label={sharedTimeFieldTimes()}
        className="ui-timefield-pop"
      >
        <div
          ref={listRef}
          className="ui-timefield-list"
          role="listbox"
          aria-label={sharedTimeFieldTimes()}
          aria-activedescendant={`${id}-option-${active}`}
          tabIndex={0}
          onKeyDown={onListKey}
        >
          {minutes.map((each, index) => (
            // An option row of a listbox: the keyboard stays on the list
            // (`aria-activedescendant`), so a row is never a Tab stop.
            <button
              key={each}
              type="button"
              id={`${id}-option-${index}`}
              role="option"
              tabIndex={-1}
              aria-selected={each === current}
              className="ui-timefield-option"
              data-cursor={index === active || undefined}
              onClick={() => pick(each)}
              onMouseEnter={() => setActive(index)}
            >
              <span className="ui-timefield-mark" aria-hidden="true">
                {each === current && <Icon name="check" size={12} />}
              </span>
              <span className="ui-timefield-clock">{clockText(each)}</span>
              {/* Collapsed by the flex row; it keeps the time and its note
                  two words apart in the option's name. */}
              {hint && <>{" "}<span className="ui-timefield-hint">{hint(each)}</span></>}
            </button>
          ))}
        </div>
      </Popover>
    </span>
  );
}

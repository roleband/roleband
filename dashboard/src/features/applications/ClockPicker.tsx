import { useEffect, useId, useRef, type KeyboardEvent } from "react";
import {
  applicationsInterviewNoTime,
  applicationsInterviewTime,
  applicationsInterviewTimeInvalid,
  applicationsInterviewTimes,
} from "../../copy/gen/applications";
import { Button } from "../../ui";
import { QUARTER_HOURS, anchorClock, clockLabel, parseClock } from "./clock";

/** The time beside the month: a field that reads a typed time, and under it
 *  every quarter hour to pick from, with No time yet first. The field's text
 *  is the one state; a pick writes it, so what the field says is what is
 *  saved. A text that names no time is said under the field. */
export function ClockPicker({ text, onText, invalid }: {
  text: string;
  onText: (text: string) => void;
  /** The text named no time when the form was sent. */
  invalid: boolean;
}) {
  const fieldId = useId();
  const errorId = useId();
  const list = useRef<HTMLDivElement>(null);
  const chosen = text.trim() ? parseClock(text) : "";
  const anchor = chosen == null ? "09:00" : anchorClock(chosen);
  const tabStop = chosen === "" ? "" : anchor;

  // The list opens on the chosen time, or on the morning, and follows a time
  // typed into the field. Its own scroll moves, never the dialog's.
  useEffect(() => {
    const box = list.current;
    // The quarter before it heads the list, whole, so the time has context.
    const row = box?.querySelector<HTMLElement>(`[data-clock="${anchor}"]`);
    const head = row?.previousElementSibling as HTMLElement | null | undefined;
    if (box && head) box.scrollTop = head.offsetTop - box.clientTop - 2;
  }, [anchor]);

  const choose = (clock: string) => onText(clock ? clockLabel(clock) : "");
  const order = ["", ...QUARTER_HOURS];
  const move = (event: KeyboardEvent<HTMLButtonElement>, from: string) => {
    const at = order.indexOf(from);
    const to = { ArrowUp: at - 1, ArrowDown: at + 1, Home: 0, End: order.length - 1 }[event.key];
    if (to == null) return;
    event.preventDefault();
    const next = order[Math.max(0, Math.min(order.length - 1, to))];
    choose(next);
    list.current?.querySelector<HTMLButtonElement>(`[data-clock="${next}"]`)?.focus();
  };
  const slot = (clock: string) => (
    <Button
      key={clock || "none"}
      variant="icon"
      size="sm"
      className="app-clock-slot"
      data-clock={clock}
      aria-pressed={chosen === clock}
      tabIndex={clock === tabStop ? 0 : -1}
      onClick={() => choose(clock)}
      onKeyDown={(event) => move(event, clock)}
    >
      <span className="app-clock-label">{clock ? clockLabel(clock) : applicationsInterviewNoTime()}</span>
    </Button>
  );

  return (
    <div className="app-clock">
      <label htmlFor={fieldId}>{applicationsInterviewTime()}</label>
      <input
        id={fieldId}
        value={text}
        autoComplete="off"
        placeholder={clockLabel("14:30")}
        aria-invalid={invalid || undefined}
        aria-describedby={invalid ? errorId : undefined}
        onChange={(event) => onText(event.target.value)}
        onBlur={() => {
          const typed = parseClock(text);
          if (typed) onText(clockLabel(typed));
        }}
      />
      {invalid && (
        <p id={errorId} className="app-interview-error" role="alert">
          {applicationsInterviewTimeInvalid({ example: clockLabel("14:30") })}
        </p>
      )}
      <div className="app-clock-list" ref={list} role="group" aria-label={applicationsInterviewTimes()}>
        {order.map(slot)}
      </div>
    </div>
  );
}

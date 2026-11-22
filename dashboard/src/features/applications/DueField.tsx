import { useEffect, useId, useRef, useState } from "react";
import { date as formatDate } from "../../copy/format";
import { applicationsWsNextDue, applicationsWsNextDueClear, applicationsWsNextDueNone } from "../../copy/gen/applications";
import { Button, Icon, Popover } from "../../ui";
import { DayPicker } from "./DayPicker";
import { fromDayKey } from "./monthGrid";

/** A step's day: a field that shows the day, the whole of it a button that
 *  opens the month the interview form picks its day from. A click on a day
 *  takes it and closes the month; the arrows walk the days first. A day set
 *  can be cleared from under the month. */
export function DueField({ id, day, onDay, now }: {
  /** The field's id, for the label beside it. */
  id: string;
  /** "YYYY-MM-DD", or "" for no day. */
  day: string;
  onDay: (day: string) => void;
  now: Date;
}) {
  const [open, setOpen] = useState(false);
  const [anchor, setAnchor] = useState<HTMLButtonElement | null>(null);
  const month = useRef<HTMLDivElement>(null);
  const labelId = useId();
  const valueId = useId();

  // The month opens with the keyboard on its one day stop: the day set, else
  // today. The popover has already noted this field as where focus goes back.
  useEffect(() => {
    if (open) month.current?.querySelector<HTMLElement>('.app-month-day[tabindex="0"]')?.focus();
  }, [open]);

  return (
    <>
      <label id={labelId} className="app-ws-step-due-label" htmlFor={id}>{applicationsWsNextDue()}</label>
      <button
        ref={setAnchor}
        id={id}
        type="button"
        className="app-ws-due-field"
        aria-haspopup="dialog"
        aria-expanded={open}
        aria-labelledby={`${labelId} ${valueId}`}
        data-empty={!day || undefined}
        onClick={() => setOpen((was) => !was)}
      >
        <Icon name="calendar" size={14} />
        <span id={valueId} className="app-ws-due-value">
          {day ? formatDate(fromDayKey(day), "weekday") : applicationsWsNextDueNone()}
        </span>
        <Icon name="chevronDown" size={14} />
      </button>
      <Popover isOpen={open} onClose={() => setOpen(false)} anchor={anchor} label={applicationsWsNextDue()} className="app-overlay app-ws-due-pop">
        <div ref={month}>
          <DayPicker
            value={day}
            onChange={onDay}
            onChoose={() => setOpen(false)}
            now={now}
          />
        </div>
        {day && (
          <div className="app-ws-due-foot">
            <Button
              variant="link"
              className="ui-btn-quiet"
              onClick={() => {
                onDay("");
                setOpen(false);
              }}
            >
              {applicationsWsNextDueClear()}
            </Button>
          </div>
        )}
      </Popover>
    </>
  );
}

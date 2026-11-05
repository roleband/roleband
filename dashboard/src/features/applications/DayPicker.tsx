import { useEffect, useId, useRef, useState, type KeyboardEvent } from "react";
import { date as formatDate, timestamp, weekday } from "../../copy/format";
import { applicationsMonthNext, applicationsMonthPrev } from "../../copy/gen/applications";
import { Button, Icon } from "../../ui";
import { dayKey, fromDayKey, monthOf, monthWeeks, shiftDay, shiftMonth } from "./monthGrid";

/** A month to pick one day from, drawn as the month beside Up next is. A
 *  click picks; the arrows walk the days, across months, and pick as they
 *  go, so the summary above follows the keyboard. Past days stay pickable:
 *  a round already held is recorded too. */
export function DayPicker({ value, onChange, now }: {
  /** The picked day as "YYYY-MM-DD", or "" for none yet. */
  value: string;
  onChange: (day: string) => void;
  now: Date;
}) {
  const today = dayKey(now);
  const [month, setMonth] = useState(() => monthOf(value ? fromDayKey(value) : now));
  const titleId = useId();
  const grid = useRef<HTMLTableElement>(null);
  const focusDay = useRef<string | null>(null);
  useEffect(() => {
    if (!focusDay.current) return;
    grid.current?.querySelector<HTMLButtonElement>(`[data-day="${focusDay.current}"]`)?.focus();
    focusDay.current = null;
  }, [value, month]);

  const pick = (day: Date, { focus = false } = {}) => {
    const key = dayKey(day);
    onChange(key);
    if (day.getMonth() !== month.getMonth() || day.getFullYear() !== month.getFullYear()) setMonth(monthOf(day));
    if (focus) focusDay.current = key;
  };
  const move = (event: KeyboardEvent<HTMLButtonElement>, from: Date) => {
    const by = { ArrowLeft: -1, ArrowRight: 1, ArrowUp: -7, ArrowDown: 7 }[event.key];
    if (by == null) return;
    event.preventDefault();
    pick(shiftDay(from, by), { focus: true });
  };
  const weeks = monthWeeks(month);
  // One Tab stop in the grid: the picked day when this month shows it, else
  // today when it does, else the month's first day.
  const inMonth = (key: string) => key.slice(0, 7) === dayKey(month).slice(0, 7);
  const tabStop = value && inMonth(value) ? value : inMonth(today) ? today : dayKey(month);

  return (
    <div className="app-daypicker">
      <div className="app-month-head">
        <p id={titleId} className="app-daypicker-title" aria-live="polite">
          {timestamp(month, { month: "long", year: "numeric" })}
        </p>
        <div className="app-month-nav">
          <Button variant="icon" size="sm" aria-label={applicationsMonthPrev()} onClick={() => setMonth(shiftMonth(month, -1))}>
            <Icon name="chevronLeft" size={16} />
          </Button>
          <Button variant="icon" size="sm" aria-label={applicationsMonthNext()} onClick={() => setMonth(shiftMonth(month, 1))}>
            <Icon name="chevronRight" size={16} />
          </Button>
        </div>
      </div>
      <table className="app-month-grid" ref={grid} aria-labelledby={titleId}>
        <thead>
          <tr>
            {Array.from({ length: 7 }, (_, i) => (
              <th key={i} scope="col" abbr={weekday(i)}>{weekday(i)}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {weeks.map((week) => (
            <tr key={dayKey(week[0])}>
              {week.map((day) => {
                const key = dayKey(day);
                return (
                  <td key={key}>
                    <Button
                      variant="icon"
                      size="md"
                      className="app-month-day"
                      data-day={key}
                      data-outside={day.getMonth() !== month.getMonth() || undefined}
                      data-past={key < today || undefined}
                      aria-current={key === today ? "date" : undefined}
                      aria-pressed={key === value}
                      aria-label={formatDate(day, "weekday")}
                      tabIndex={key === tabStop ? 0 : -1}
                      onClick={() => pick(day)}
                      onKeyDown={(event) => move(event, day)}
                    >
                      <span className="app-month-num">{day.getDate()}</span>
                    </Button>
                  </td>
                );
              })}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

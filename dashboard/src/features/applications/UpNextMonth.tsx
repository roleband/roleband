import { useEffect, useId, useMemo, useRef, useState, type KeyboardEvent } from "react";
import { Link } from "react-router-dom";
import { api, type ApplicationCalendarItem, type ApplicationCard } from "../../api";
import { date as formatDate, list, time as formatTime, timestamp, weekday } from "../../copy/format";
import {
  applicationsInterviewOutcomeCancelled,
  applicationsInterviewOutcomeNotPassed,
  applicationsInterviewOutcomePassed,
  applicationsMonthDay,
  applicationsMonthDayEmpty,
  applicationsMonthFailed,
  applicationsMonthInterviews,
  applicationsMonthLabel,
  applicationsMonthLegendInterview,
  applicationsMonthLegendStep,
  applicationsMonthNext,
  applicationsMonthPrev,
  applicationsMonthSteps,
  applicationsMonthToday,
  applicationsNextInterviewAllDay,
  applicationsUpnextInterview,
  applicationsUpnextStep,
  applicationsUpnextStepWhen,
} from "../../copy/gen/applications";
import { companyName } from "../../format";
import { useAsyncResource, useRefetchOn } from "../../hooks/useAsyncResource";
import { commonTryAgain } from "../../copy/gen/common";
import { Badge, Button, CompanyIcon, Content, Icon } from "../../ui";
import { useOriginState } from "./pageOrigin";
import { applicationPath } from "./board";
import { dayKey, fromDayKey, itemsByDay, monthOf, monthSpan, monthWeeks, shiftDay, shiftMonth } from "./monthGrid";

const OUTCOME = {
  passed: applicationsInterviewOutcomePassed,
  not_passed: applicationsInterviewOutcomeNotPassed,
  cancelled: applicationsInterviewOutcomeCancelled,
} as const;

function DayItem({ item, card, match }: { item: ApplicationCalendarItem; card: ApplicationCard; match?: boolean }) {
  const origin = useOriginState();
  const company = companyName(card.company);
  const at = new Date(item.at);
  const when = item.kind === "interview"
    ? item.all_day ? applicationsNextInterviewAllDay({ date: formatDate(at, "weekday") }) : formatTime(at)
    : applicationsUpnextStepWhen();
  return (
    <li className="app-upnext-item" data-match={match == null ? undefined : String(match)}>
      <span className="app-upnext-when">{when}</span>
      <div className="app-upnext-what">
        <span className="app-next-name">
          {item.kind === "interview"
            ? applicationsUpnextInterview({ label: item.label })
            : applicationsUpnextStep({ step: item.step })}
        </span>
        <Link to={applicationPath(card.job_id)} state={origin} className="app-tile-open app-upnext-role">
          <CompanyIcon slug={card.company} display={company} size={16} />
          <span>{company}</span>
          <span className="app-upnext-title"><Content text={card.title} /></span>
        </Link>
      </div>
      {item.kind === "interview" && item.outcome && (
        <Badge tone={item.outcome === "passed" ? "success" : "neutral"} size="sm">{OUTCOME[item.outcome]()}</Badge>
      )}
    </li>
  );
}

/** The month beside Up next: every interview and dated next step by the day
 *  it falls on, past days included. Picking a day tells Up next, which brings
 *  that day's items into view and marks them; what Up next does not list (a
 *  past round, a later round of the same role) is listed under the grid. It
 *  reads its own span; a role is named from the board's cards, so an item
 *  whose application the board does not show is not drawn. */
export function UpNextMonth({ cards, now, keep, inAgenda, onPickDay }: {
  cards: readonly ApplicationCard[];
  now: Date;
  /** The view's filter: false drops the item's application, undefined keeps
   *  every item, true or false on a highlight dims the ones that miss. */
  keep: (card: ApplicationCard) => { shown: boolean; match?: boolean };
  /** Whether Up next lists this item, so the grid need not. */
  inAgenda: (item: ApplicationCalendarItem) => boolean;
  /** A day picked: `scroll` for a click, Enter or Today, which brings the day
   *  into view; an arrow walking the grid only moves the mark. */
  onPickDay: (day: Date, how: { scroll: boolean }) => void;
}) {
  const today = dayKey(now);
  const [month, setMonth] = useState(() => monthOf(now));
  const [picked, setPicked] = useState(today);
  const grid = useRef<HTMLTableElement>(null);
  const titleId = useId();
  // The day an arrow moved to, focused once its month has rendered.
  const focusDay = useRef<string | null>(null);
  useEffect(() => {
    if (!focusDay.current) return;
    grid.current?.querySelector<HTMLButtonElement>(`[data-day="${focusDay.current}"]`)?.focus();
    focusDay.current = null;
  }, [picked, month]);
  const span = monthSpan(month);
  const resource = useAsyncResource(
    (signal) => api.calendar(span.start, span.end, signal),
    [span.start.getTime(), span.end.getTime()],
  );
  // A write that reloads the board reads the month again, in place: its marks
  // stay up until the new answer lands.
  useRefetchOn(cards, resource.refresh);
  const byJob = useMemo(() => new Map(cards.map((card) => [card.job_id, card])), [cards]);
  const days = itemsByDay((resource.data?.items ?? []).filter((item) => {
    const card = byJob.get(item.job_id);
    return card != null && keep(card).shown;
  }));
  const weeks = monthWeeks(month);

  const pick = (day: Date, { scroll = true, focus = false } = {}) => {
    const key = dayKey(day);
    setPicked(key);
    if (day.getMonth() !== month.getMonth() || day.getFullYear() !== month.getFullYear()) setMonth(monthOf(day));
    onPickDay(day, { scroll });
    if (focus) focusDay.current = key;
  };
  const move = (event: KeyboardEvent<HTMLButtonElement>, from: Date) => {
    const by = { ArrowLeft: -1, ArrowRight: 1, ArrowUp: -7, ArrowDown: 7 }[event.key];
    if (by == null) return;
    event.preventDefault();
    pick(shiftDay(from, by), { scroll: false, focus: true });
  };
  const describe = (key: string, day: Date) => {
    const items = days.get(key) ?? [];
    const interviews = items.filter((item) => item.kind === "interview").length;
    const steps = items.length - interviews;
    const parts = [
      ...(interviews ? [applicationsMonthInterviews({ count: interviews })] : []),
      ...(steps ? [applicationsMonthSteps({ count: steps })] : []),
    ];
    const name = formatDate(day, "weekday");
    return parts.length ? applicationsMonthDay({ date: name, summary: list(parts) }) : name;
  };
  // The picked day stays the one Tab stop in the grid; when the month shown
  // does not hold it, its first day is.
  const tabStop = weeks.flat().some((day) => dayKey(day) === picked && day.getMonth() === month.getMonth())
    ? picked
    : dayKey(month);
  const pickedItems = days.get(picked) ?? [];
  const elsewhere = pickedItems.filter((item) => !inAgenda(item));
  const pickedDay = fromDayKey(picked);

  return (
    <section className="app-panel app-month" aria-label={applicationsMonthLabel()}>
      <header className="app-month-head">
        <h2 id={titleId} className="app-panel-title" aria-live="polite">
          {timestamp(month, { month: "long", year: "numeric" })}
        </h2>
        <div className="app-month-nav">
          <Button variant="icon" size="sm" aria-label={applicationsMonthPrev()} onClick={() => setMonth(shiftMonth(month, -1))}>
            <Icon name="chevronLeft" size={16} />
          </Button>
          <Button variant="ghost" size="sm" onClick={() => pick(now)}>{applicationsMonthToday()}</Button>
          <Button variant="icon" size="sm" aria-label={applicationsMonthNext()} onClick={() => setMonth(shiftMonth(month, 1))}>
            <Icon name="chevronRight" size={16} />
          </Button>
        </div>
      </header>
      {resource.error && (
        <p className="app-month-failed" role="alert">
          {applicationsMonthFailed()}{" "}
          <Button variant="link" onClick={resource.retry}>{commonTryAgain()}</Button>
        </p>
      )}
      {/* The grid stands while a month loads: its marks arrive, the weeks do
          not move. */}
          <table className="app-month-grid" ref={grid} aria-labelledby={titleId} aria-busy={resource.loading || undefined}>
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
                    const items = days.get(key) ?? [];
                    const interviews = items.some((item) => item.kind === "interview");
                    const steps = items.some((item) => item.kind === "step");
                    return (
                      <td key={key}>
                        <Button
                          variant="icon"
                          size="lg"
                          className="app-month-day"
                          data-day={key}
                          data-outside={day.getMonth() !== month.getMonth() || undefined}
                          data-past={key < today || undefined}
                          aria-current={key === today ? "date" : undefined}
                          aria-pressed={key === picked}
                          aria-label={describe(key, day)}
                          tabIndex={key === tabStop ? 0 : -1}
                          onClick={() => pick(day)}
                          onKeyDown={(event) => move(event, day)}
                        >
                          <span className="app-month-num">{day.getDate()}</span>
                          <span className="app-month-marks" aria-hidden="true">
                            {interviews && <span className="app-month-mark" data-kind="interview" />}
                            {steps && <span className="app-month-mark" data-kind="step" />}
                          </span>
                        </Button>
                      </td>
                    );
                  })}
                </tr>
              ))}
            </tbody>
          </table>
      <p className="app-month-legend" aria-hidden="true">
        <span><span className="app-month-mark" data-kind="interview" />{applicationsMonthLegendInterview()}</span>
        <span><span className="app-month-mark" data-kind="step" />{applicationsMonthLegendStep()}</span>
      </p>
      {/* A day whose every item Up next lists is answered there, marked;
          the grid lists only what Up next does not. */}
      {(pickedItems.length === 0 || elsewhere.length > 0) && (
        <div className="app-month-picked">
          <h3 className="app-panel-title">{formatDate(pickedDay, "weekday")}</h3>
          {elsewhere.length === 0 ? (
            <p className="app-month-empty">{applicationsMonthDayEmpty()}</p>
          ) : (
            <ul data-highlight={elsewhere.some((item) => keep(byJob.get(item.job_id)!).match !== undefined) ? "" : undefined}>
              {elsewhere.map((item) => {
                const card = byJob.get(item.job_id)!;
                return (
                  <DayItem
                    key={item.kind === "interview" ? `i-${item.interview_id}` : `s-${item.job_id}`}
                    item={item}
                    card={card}
                    match={keep(card).match}
                  />
                );
              })}
            </ul>
          )}
        </div>
      )}
    </section>
  );
}

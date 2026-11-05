import { useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import type { ApplicationBoard, ApplicationCalendarItem, ApplicationCard } from "../../api";
import { date as formatDate, time as formatTime } from "../../copy/format";
import { companyName } from "../../format";
import type { AsyncResource } from "../../hooks/useAsyncResource";
import { AsyncBoundary, Badge, CompanyIcon, Content } from "../../ui";
import {
  applicationsBoardLoadFailed,
  applicationsCardOverdue,
  applicationsNextInterviewAllDay,
  applicationsUpnextDay,
  applicationsUpnextEmpty,
  applicationsUpnextInterview,
  applicationsUpnextNoMatches,
  applicationsUpnextOverdue,
  applicationsUpnextStep,
  applicationsUpnextStepWhen,
} from "../../copy/gen/applications";
import { applicationPath, daysOverdue } from "./board";
import { upNext, type UpNextDay, type UpNextItem } from "./dueByDay";
import { VIEW_FILTERS, isFiltering, matches, quickCounts } from "./filters";
import { dayKey } from "./monthGrid";
import { PipelineToolbar } from "./PipelineToolbar";
import { UpNextMonth } from "./UpNextMonth";
import { useViewFilter } from "./useViewFilter";

/** The key a calendar item and an Up next row share when they are one thing. */
const itemKey = (item: UpNextItem) =>
  item.kind === "interview" ? `interview-${item.card.next_interview?.id}` : `step-${item.card.job_id}`;
const calendarKey = (item: ApplicationCalendarItem) =>
  item.kind === "interview" ? `interview-${item.interview_id}` : `step-${item.job_id}`;

function ItemRow({ item, now, match, picked }: { item: UpNextItem; now: Date; match?: boolean; picked: boolean }) {
  const { card } = item;
  const company = companyName(card.company);
  const interview = item.kind === "interview" ? card.next_interview : null;
  const overdue = item.kind === "step" && item.at.getTime() < now.getTime();
  // An interview says its time; a step is due by its day's end, and an
  // overdue one says the day it was due.
  const when = interview
    ? interview.all_day ? applicationsNextInterviewAllDay({ date: formatDate(item.at, "weekday") }) : formatTime(item.at)
    : overdue ? formatDate(item.at, "weekday") : applicationsUpnextStepWhen();
  return (
    <li
      className="app-upnext-item"
      data-job-id={card.job_id}
      data-match={match == null ? undefined : String(match)}
      data-picked={picked || undefined}
    >
      <span className="app-upnext-when">{when}</span>
      <div className="app-upnext-what">
        <span className="app-next-name">
          {interview
            ? applicationsUpnextInterview({ label: interview.label })
            : applicationsUpnextStep({ step: card.next_action ?? "" })}
        </span>
        <Link to={applicationPath(card.job_id)} className="app-tile-open app-upnext-role">
          <CompanyIcon slug={card.company} display={company} size={16} />
          <span>{company}</span>
          <span className="app-upnext-title"><Content text={card.title} /></span>
        </Link>
      </div>
      {overdue && (
        <Badge tone="danger" variant="solid" size="sm">
          {applicationsCardOverdue({ days: daysOverdue({ kind: "step", at: item.at, on: item.at }, now) })}
        </Badge>
      )}
    </li>
  );
}

/** The pipeline's daily door: every interview and dated next step, by the
 *  day it falls on, with what is overdue first, beside the month they fall
 *  in. A day picked in the month marks its rows here and, on a click, brings
 *  the first of them into view. Each row opens its application. It owns its
 *  filter, which matches a row by the application it belongs to, in the list
 *  and the month alike; the page lends it only the applications. */
export function UpNext({ resource, now }: {
  resource: AsyncResource<ApplicationBoard>;
  /** The page's clock, so a row says the same day the board's card does. */
  now: Date;
}) {
  const [filter, setFilter] = useViewFilter("up_next");
  const filtering = isFiltering(filter);
  const highlight = filtering && filter.mode === "highlight";
  const hits = (item: UpNextItem) => matches(item.card, filter, now);
  // The quick filters count the applications that have a row here.
  const due = upNext(resource.data?.applications ?? [], now).flatMap((day) => day.items.map((item) => item.card));
  const keep = (card: ApplicationCard) => {
    if (!filtering) return { shown: true };
    const hit = matches(card, filter, now);
    return highlight ? { shown: true, match: hit } : { shown: hit };
  };
  // The day picked in the month, and how many times a pick asked to be
  // scrolled to: picking the same day again brings it back into view.
  const [picked, setPicked] = useState<{ day: string; scrolls: number } | null>(null);
  const agendaRef = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!picked?.scrolls) return;
    const row = agendaRef.current?.querySelector<HTMLElement>(".app-upnext-item[data-picked]");
    row?.closest("section")?.scrollIntoView({
      block: "start",
      behavior: window.matchMedia("(prefers-reduced-motion: reduce)").matches ? "auto" : "smooth",
    });
  }, [picked?.scrolls]);
  const pickDay = (day: Date, { scroll }: { scroll: boolean }) =>
    setPicked((was) => ({ day: dayKey(day), scrolls: (was?.scrolls ?? 0) + (scroll ? 1 : 0) }));

  const shownDays = (board: ApplicationBoard): UpNextDay[] => {
    const all = upNext(board.applications, now);
    return filtering && !highlight
      ? all.map((day) => ({ ...day, items: day.items.filter(hits) })).filter((day) => day.items.length > 0)
      : all;
  };

  return (
    <>
      <PipelineToolbar filter={filter} onFilter={setFilter} quickCounts={quickCounts([...new Set(due)], now, VIEW_FILTERS.up_next)} />
      <AsyncBoundary resource={resource} failed={applicationsBoardLoadFailed()}>
        {(board) => (
          <div className="app-upnext-split">
            <div className="app-upnext-list" ref={agendaRef}>{agenda(board)}</div>
            <UpNextMonth
              cards={board.applications}
              now={now}
              keep={keep}
              inAgenda={inAgenda(board)}
              onPickDay={pickDay}
            />
          </div>
        )}
      </AsyncBoundary>
    </>
  );

  function inAgenda(board: ApplicationBoard) {
    const listed = new Set(shownDays(board).flatMap((day) => day.items.map(itemKey)));
    return (item: ApplicationCalendarItem) => listed.has(calendarKey(item));
  }

  function agenda(board: ApplicationBoard) {
    if (upNext(board.applications, now).length === 0) {
      return <p className="app-column-empty app-upnext-empty">{applicationsUpnextEmpty()}</p>;
    }
    const days = shownDays(board);
    if (days.length === 0) return <p className="app-column-empty app-upnext-empty">{applicationsUpnextNoMatches()}</p>;
    return (
      <div className="app-upnext" data-highlight={highlight ? "" : undefined}>
        {days.map((day) => {
          const first = day.items[0].at;
          const heading = day.key === "overdue"
            ? applicationsUpnextOverdue()
            : applicationsUpnextDay({ offset: day.key, date: formatDate(first, "weekday") });
          const id = `app-upnext-${day.key}`;
          return (
            <section key={String(day.key)} className="app-upnext-day" aria-labelledby={id} data-overdue={day.key === "overdue" || undefined}>
              <h2 id={id} className="app-panel-title">{heading}</h2>
              <ul>
                {day.items.map((item) => (
                  <ItemRow
                    key={`${item.kind}-${item.card.job_id}`}
                    item={item}
                    now={now}
                    match={highlight ? hits(item) : undefined}
                    picked={picked?.day === dayKey(item.at)}
                  />
                ))}
              </ul>
            </section>
          );
        })}
      </div>
    );
  }
}

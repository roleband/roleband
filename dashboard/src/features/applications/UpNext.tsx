import { useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import type { ApplicationBoard, ApplicationCalendarItem, ApplicationCard, ApplicationCardInterview } from "../../api";
import { date as formatDate, time as formatTime } from "../../copy/format";
import { companyName } from "../../format";
import type { AsyncResource } from "../../hooks/useAsyncResource";
import { useMeasuredCssSize } from "../../hooks/useMeasuredCssSize";
import { AsyncBoundary, Button, CompanyIcon, Content, ExternalLink, Icon } from "../../ui";
import {
  applicationsBoardLoadFailed,
  applicationsMonthLegendInterview,
  applicationsNextInterviewJoin,
  applicationsNextInterviewJoinLabel,
  applicationsNextInterviewMeta,
  applicationsUpnextAllDay,
  applicationsUpnextDay,
  applicationsUpnextDoneLabel,
  applicationsUpnextEmpty,
  applicationsUpnextOutcome,
  applicationsUpnextOutcomeLabel,
  applicationsUpnextOverdue,
  applicationsUpnextStepWhen,
} from "../../copy/gen/applications";
import { useRoleLink } from "./roleLink";
import { NoMatches, PipelineEmpty } from "./PipelineEmpty";
import { DueBadge } from "./DueBadge";
import { upNext, type UpNextDay, type UpNextItem } from "./dueByDay";
import { FORMAT_LABEL, OUTCOME_LABEL } from "./interviewWords";
import { VIEW_FILTERS, isFiltering, matches, quickCounts } from "./filters";
import { dayKey } from "./monthGrid";
import { PipelineToolbar } from "./PipelineToolbar";
import { UpNextMonth } from "./UpNextMonth";
import { useViewFilter } from "./useViewFilter";

/** The key a calendar item and an Up next row share when they are one thing. */
const itemKey = (item: UpNextItem) =>
  item.kind === "step" ? `step-${item.card.job_id}` : `interview-${item.interview.id}`;
const calendarKey = (item: ApplicationCalendarItem) =>
  item.kind === "interview" ? `interview-${item.interview_id}` : `step-${item.job_id}`;

type Outcome = keyof typeof OUTCOME_LABEL;

/** What Up next can do to a row in place; the page lends it the board's own
 *  writes. */
export interface UpNextActions {
  onFinishStep: (card: ApplicationCard) => void;
  onSetOutcome: (card: ApplicationCard, interview: ApplicationCardInterview, outcome: Outcome) => void;
}

/** The right side of a row: when it falls, and the one thing to do there. A
 *  row sits under its day, so a coming round says only its time; a step says
 *  it is due by the day's end, or how late it is. */
function RowSide({ item, now, actions }: { item: UpNextItem; now: Date; actions: UpNextActions }) {
  if (item.kind === "step") {
    return item.at.getTime() < now.getTime()
      ? <DueBadge due={{ kind: "step", at: item.at, on: item.at }} now={now} />
      : <span className="app-upnext-when">{applicationsUpnextStepWhen()}</span>;
  }
  const { interview, card } = item;
  if (item.kind === "outcome") {
    return (
      <>
        <span className="app-upnext-when">{formatDate(item.at, "weekday")}</span>
        <div className="app-upnext-outcomes" role="group" aria-label={applicationsUpnextOutcomeLabel({ label: interview.label })}>
          {(Object.keys(OUTCOME_LABEL) as Outcome[]).map((outcome) => (
            <Button key={outcome} variant="ghost" size="sm" onClick={() => actions.onSetOutcome(card, interview, outcome)}>
              {OUTCOME_LABEL[outcome]()}
            </Button>
          ))}
        </div>
      </>
    );
  }
  const when = interview.all_day ? applicationsUpnextAllDay() : formatTime(item.at);
  return (
    <>
      <span className="app-upnext-when">
        {interview.format ? applicationsNextInterviewMeta({ when, format: FORMAT_LABEL[interview.format]() }) : when}
      </span>
      {interview.link && (
        <ExternalLink href={interview.link} label={applicationsNextInterviewJoinLabel({ label: interview.label })}>
          {applicationsNextInterviewJoin()}
        </ExternalLink>
      )}
    </>
  );
}

function ItemRow({ item, now, match, picked, actions }: {
  item: UpNextItem;
  now: Date;
  match?: boolean;
  picked: boolean;
  actions: UpNextActions;
}) {
  const role = useRoleLink();
  const { card } = item;
  const company = companyName(card.company);
  const step = card.next_action ?? "";
  return (
    <li
      className="app-upnext-item"
      data-kind={item.kind}
      data-job-id={card.job_id}
      data-match={match == null ? undefined : String(match)}
      data-picked={picked || undefined}
    >
      {item.kind === "step" ? (
        <Button
          variant="icon"
          size="sm"
          className="ui-btn-tick app-upnext-tick"
          aria-label={applicationsUpnextDoneLabel({ step })}
          onClick={() => actions.onFinishStep(card)}
        >
          <Icon name="check" size={14} />
        </Button>
      ) : (
        <span className="app-upnext-mark" role="img" aria-label={applicationsMonthLegendInterview()}>
          <Icon name="calendar" size={14} />
        </span>
      )}
      <div className="app-upnext-what">
        <span className="app-upnext-name">
          <Content text={item.kind === "step" ? step : item.interview.label} />
        </span>
        <Link {...role(card, "workspace")} className="app-tile-open app-upnext-role">
          <CompanyIcon slug={card.company} display={company} size={16} />
          <span>{company}</span>
          <span className="app-upnext-title"><Content text={card.title} /></span>
        </Link>
      </div>
      <div className="app-upnext-side">
        <RowSide item={item} now={now} actions={actions} />
      </div>
    </li>
  );
}

/** The pipeline's daily door: every interview and dated next step, by the
 *  day it falls on, with what is overdue first, beside the month they fall
 *  in. A day picked in the month marks its rows here and, on a click, brings
 *  the first of them into view. Each row opens its application. It owns its
 *  filter, which matches a row by the application it belongs to, in the list
 *  and the month alike; the page lends it only the applications. */
export function UpNext({ resource, now, actions }: {
  resource: AsyncResource<ApplicationBoard>;
  /** The page's clock, so a row says the same day the board's card does. */
  now: Date;
  actions: UpNextActions;
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
  // The month and a picked day's heading sit under the docked toolbar.
  const toolbar = useRef<HTMLDivElement>(null);
  const split = useRef<HTMLDivElement>(null);
  useMeasuredCssSize({ rootRef: split, elementRef: toolbar, property: "--app-upnext-toolbar-h" });
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
      <PipelineToolbar toolbarRef={toolbar} filter={filter} onFilter={setFilter} quickCounts={quickCounts([...new Set(due)], now, VIEW_FILTERS.up_next)} />
      <AsyncBoundary
        resource={resource}
        failed={applicationsBoardLoadFailed()}
        isEmpty={(data) => data.applications.length === 0}
        empty={<PipelineEmpty />}
      >
        {(board) => (
          <div className="app-upnext-split" ref={split}>
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
    if (days.length === 0) return <NoMatches />;
    return (
      <div className="app-upnext" data-highlight={highlight ? "" : undefined}>
        {days.map((day) => {
          const first = day.items[0].at;
          const heading = day.key === "overdue"
            ? applicationsUpnextOverdue()
            : day.key === "outcome"
              ? applicationsUpnextOutcome()
              : applicationsUpnextDay({ offset: day.key, date: formatDate(first, "weekday") });
          const id = `app-upnext-${day.key}`;
          return (
            <section key={String(day.key)} className="app-upnext-day" aria-labelledby={id} data-overdue={day.key === "overdue" || undefined}>
              <h2 id={id} className="app-upnext-day-name">{heading}</h2>
              <ul>
                {day.items.map((item) => (
                  <ItemRow
                    key={`${item.kind}-${item.card.job_id}`}
                    item={item}
                    now={now}
                    actions={actions}
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

import { Link } from "react-router-dom";
import type { ApplicationBoard } from "../../api";
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
import { upNext, type UpNextItem } from "./dueByDay";
import { isFiltering, matches, type BoardFilter } from "./filters";

function ItemRow({ item, now, match }: { item: UpNextItem; now: Date; match?: boolean }) {
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
    <li className="app-upnext-item" data-job-id={card.job_id} data-match={match == null ? undefined : String(match)}>
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
 *  day it falls on, with what is overdue first. Each row opens its
 *  application. The board's filters apply here too, by the application a
 *  row belongs to. */
export function UpNext({ resource, filter, now }: {
  resource: AsyncResource<ApplicationBoard>;
  filter: BoardFilter;
  /** The board's clock, so a row and the toolbar's count agree. */
  now: Date;
}) {
  const filtering = isFiltering(filter);
  const highlight = filtering && filter.mode === "highlight";
  const hits = (item: UpNextItem) => matches(item.card, filter, now);
  return (
    <AsyncBoundary resource={resource} failed={applicationsBoardLoadFailed()}>
      {(board) => {
        const all = upNext(board.applications, now);
        if (all.length === 0) return <p className="app-column-empty app-upnext-empty">{applicationsUpnextEmpty()}</p>;
        const days = filtering && !highlight
          ? all.map((day) => ({ ...day, items: day.items.filter(hits) })).filter((day) => day.items.length > 0)
          : all;
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
                      />
                    ))}
                  </ul>
                </section>
              );
            })}
          </div>
        );
      }}
    </AsyncBoundary>
  );
}

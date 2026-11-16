import { Link, useSearchParams } from "react-router-dom";
import type { ActivityEntry, ActivityPage } from "../../../api/agentActivity";
import { time, timestamp } from "../../../copy/format";
import { Badge, Button } from "../../../ui";
import { categoryName, entryText, groupName } from "./activityText";
import {
  activityDayToday,
  activityDayYesterday,
  activityList,
  activityNewer,
  activityOlder,
  activityPageRange,
  activityTagChange,
  activityTagNotShared,
  activityTagTurnedOff,
} from "../../../copy/gen/activity";

/** The reader's own calendar day of an instant, as `YYYY-MM-DD`. */
function localDay(iso: string): string {
  const at = new Date(iso);
  return `${at.getFullYear()}-${String(at.getMonth() + 1).padStart(2, "0")}-${String(at.getDate()).padStart(2, "0")}`;
}

/** The entries of one page in runs of one local day, newest first, as the page holds them. */
export function byDay(items: readonly ActivityEntry[]): { day: string; items: ActivityEntry[] }[] {
  const days: { day: string; items: ActivityEntry[] }[] = [];
  for (const item of items) {
    const day = localDay(item.occurred_at);
    const last = days[days.length - 1];
    if (last?.day === day) last.items.push(item);
    else days.push({ day, items: [item] });
  }
  return days;
}

/** A day heading's two parts: what the reader calls the day, and its date. */
export function dayHeading(iso: string, now: Date = new Date()): { name: string; date: string } {
  const at = new Date(iso);
  const today = new Date(now.getFullYear(), now.getMonth(), now.getDate());
  const day = new Date(at.getFullYear(), at.getMonth(), at.getDate());
  const daysAgo = Math.round((today.getTime() - day.getTime()) / 86_400_000);
  const year = at.getFullYear() === now.getFullYear() ? {} : { year: "numeric" as const };
  if (daysAgo === 0 || daysAgo === 1) {
    return {
      name: daysAgo === 0 ? activityDayToday() : activityDayYesterday(),
      date: timestamp(at, { weekday: "long", day: "numeric", month: "long", ...year }),
    };
  }
  return { name: timestamp(at, { weekday: "long" }), date: timestamp(at, { day: "numeric", month: "long", ...year }) };
}

/** The tag at a row's end: a refusal says why, a change its group, a read
 *  the kind of data it led with. */
function Tag({ entry }: { entry: ActivityEntry }) {
  if (entry.kind === "refused") {
    return (
      <Badge shape="tag" tone="danger" variant="outline">
        {entry.refusal === "category_disabled" ? activityTagNotShared() : activityTagTurnedOff()}
      </Badge>
    );
  }
  if (entry.kind === "change") {
    return <Badge shape="tag" variant="outline">{entry.action_group ? groupName(entry.action_group) : activityTagChange()}</Badge>;
  }
  const lead = entry.categories[0];
  return lead ? <Badge shape="tag" variant="outline">{categoryName(lead)}</Badge> : null;
}

export function ActivityList({ page, first, selectedId, onOlder, onNewer }: {
  page: ActivityPage;
  /** The position of the page's first entry, counted from the newest. */
  first: number;
  selectedId: number;
  onOlder?: () => void;
  onNewer?: () => void;
}) {
  const [searchParams] = useSearchParams();
  const linkTo = (id: number) => {
    const next = new URLSearchParams(searchParams);
    next.set("entry", String(id));
    return { search: `?${next.toString()}` };
  };

  return (
    <section className="activity-list" aria-label={activityList()}>
      {byDay(page.items).map(({ day, items }) => {
        const heading = dayHeading(items[0].occurred_at);
        return (
          <div key={day} className="activity-day-group">
            <h2 className="activity-day">
              <span className="activity-day-name">{heading.name}</span>
              <span className="activity-day-date">{heading.date}</span>
            </h2>
            <ul className="activity-rows">
              {items.map((entry) => (
                <li key={entry.id}>
                  {/* The picked entry is an address (`?entry=`), so the row is a link to it. */}
                  <Link
                    className="activity-row"
                    to={linkTo(entry.id)}
                    replace
                    preventScrollReset
                    aria-current={entry.id === selectedId ? "true" : undefined}
                    data-kind={entry.kind}
                  >
                    <span className="activity-time">{time(entry.occurred_at)}</span>
                    <span className="activity-what">{entryText(entry)}</span>
                    <span className="activity-tag"><Tag entry={entry} /></span>
                  </Link>
                </li>
              ))}
            </ul>
          </div>
        );
      })}
      <div className="activity-pager" data-selection="chrome">
        <span className="activity-page-range">
          {activityPageRange({ first, last: first + page.items.length - 1 })}
        </span>
        {onNewer && <Button size="sm" onClick={onNewer}>{activityNewer()}</Button>}
        {onOlder && <Button size="sm" onClick={onOlder}>{activityOlder()}</Button>}
      </div>
    </section>
  );
}

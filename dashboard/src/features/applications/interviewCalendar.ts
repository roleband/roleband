import type { ApplicationCard, ApplicationInterview } from "../../api";
import {
  applicationsInterviewCalendarTitle,
  applicationsInterviewFor,
} from "../../copy/gen/applications";
import { companyName } from "../../format";
import { positionPath } from "../../routing/paths";
import { FORMAT_LABEL } from "./interviewWords";

/* One interview as a calendar file (RFC 5545), for the person's own calendar
 * app to import. The event's UID is the round's, so importing the file again
 * after the round moves updates the event instead of adding a second one.
 * A round holds no length: a timed one is given an hour, which the person
 * changes in their calendar; an all-day one is that whole day. */

const HOUR = 3_600_000;
const CRLF = "\r\n";

/** Text as a property value: backslash, semicolon, comma and line breaks escaped. */
const escaped = (value: string) =>
  value.replace(/\\/g, "\\\\").replace(/;/g, "\\;").replace(/,/g, "\\,").replace(/\r\n|\r|\n/g, "\\n");

/** An instant in UTC, as 20261125T150000Z. */
const instant = (at: Date) => at.toISOString().replace(/[-:]/g, "").replace(/\.\d{3}/, "");

/** A calendar day on the reader's own clock, as 20261125. */
const calendarDay = (at: Date) =>
  `${at.getFullYear()}${String(at.getMonth() + 1).padStart(2, "0")}${String(at.getDate()).padStart(2, "0")}`;

/** A content line folded so no line passes 75 octets: each continuation
 *  starts with a space, and no character is split across lines. */
function folded(line: string): string {
  const encoder = new TextEncoder();
  let out = "";
  let width = 0;
  for (const character of line) {
    const size = encoder.encode(character).length;
    if (width + size > 75) {
      out += `${CRLF} `;
      width = 1;
    }
    out += character;
    width += size;
  }
  return out;
}

type Role = Pick<ApplicationCard, "job_id" | "company" | "title">;
/** What a round needs to be a calendar event: the board's card holds as much. */
type Round = Pick<ApplicationInterview, "id" | "label" | "scheduled_at" | "all_day" | "format" | "link">;

/** The calendar file for one round of `role`, stamped at `now`; `origin` is
 *  where the app is served, for the link back to the role. */
export function interviewCalendar(interview: Round, role: Role, origin: string, now: Date): string {
  const start = new Date(interview.scheduled_at);
  const company = companyName(role.company);
  const when = interview.all_day
    ? [`DTSTART;VALUE=DATE:${calendarDay(start)}`, `DTEND;VALUE=DATE:${calendarDay(new Date(start.getFullYear(), start.getMonth(), start.getDate() + 1))}`]
    : [`DTSTART:${instant(start)}`, `DTEND:${instant(new Date(start.getTime() + HOUR))}`];
  const about = [
    applicationsInterviewFor({ title: role.title, company }),
    interview.format ? FORMAT_LABEL[interview.format]() : null,
    interview.link,
    `${origin}${positionPath(role.company, role.job_id)}?tab=workspace`,
  ].filter((line): line is string => !!line);
  const lines = [
    "BEGIN:VCALENDAR",
    "VERSION:2.0",
    "PRODID:-//RoleBand//Interviews//EN",
    "CALSCALE:GREGORIAN",
    "METHOD:PUBLISH",
    "BEGIN:VEVENT",
    /* not copy */ `UID:interview-${interview.id}@roleband`,
    `DTSTAMP:${instant(now)}`,
    ...when,
    `SUMMARY:${escaped(applicationsInterviewCalendarTitle({ label: interview.label, company }))}`,
    `DESCRIPTION:${escaped(about.join("\n"))}`,
    ...(interview.link ? [`LOCATION:${escaped(interview.link)}`, `URL:${interview.link}`] : []),
    "END:VEVENT",
    "END:VCALENDAR",
  ];
  return lines.map(folded).join(CRLF) + CRLF;
}

/** The file's name: the company and the round, in letters and digits. */
export function interviewCalendarName(interview: Pick<Round, "label">, role: Pick<Role, "company">): string {
  const words = `${role.company} ${interview.label}`
    .normalize("NFKD")
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "");
  return `${words || "interview"}.ics`;
}

/** Hands the file to the browser to save or open, as a download. Its type
 *  names the method the file states: RFC 5545 has the two agree. */
export function saveCalendarFile(name: string, body: string): void {
  const url = URL.createObjectURL(new Blob([body], { type: "text/calendar;charset=utf-8;method=PUBLISH" }));
  const link = document.createElement("a");
  link.href = url;
  link.download = name;
  link.hidden = true;
  document.body.append(link);
  link.click();
  link.remove();
  // After the click has handed the file over.
  window.setTimeout(() => URL.revokeObjectURL(url), 1_000);
}

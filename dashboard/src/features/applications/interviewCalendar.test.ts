import { describe, expect, it } from "vitest";
import type { ApplicationInterview } from "../../api";
import { companyName } from "../../format";
import { msg } from "../../test/msg";
import { interviewCalendar, interviewCalendarName } from "./interviewCalendar";

/* A round as a calendar file: the calendar app shows it at the round's own
 * time, under a title that names the round and the company, and importing it
 * again updates the same event. Read back the way a calendar app reads it:
 * folded lines joined, then each property's escapes undone. */

const NOW = new Date("2026-11-21T12:00:00Z");
const ORIGIN = "http://127.0.0.1:8010";
const role = { job_id: 202, company: "stripe", title: "Principal Engineering Manager, Payments" };
const COMPANY = companyName(role.company);

const round = (over: Partial<ApplicationInterview> = {}): ApplicationInterview => ({
  id: 41,
  label: "Hiring manager",
  scheduled_at: "2026-11-25T15:30:00Z",
  all_day: false,
  format: "video",
  link: "https://meet.example.com/abc-defg",
  outcome: null,
  notes: "Ask about the team; and the roadmap",
  ...over,
} as ApplicationInterview);

/** The file's properties, as a calendar app reads them. */
function read(file: string): Map<string, string> {
  const lines = file.replace(/\r\n /g, "").split("\r\n").filter(Boolean);
  return new Map(lines.map((line) => {
    const at = line.indexOf(":");
    const value = line.slice(at + 1).replace(/\\n/g, "\n").replace(/\\([,;\\])/g, "$1");
    return [line.slice(0, at), value];
  }));
}

describe("an interview's calendar file", () => {
  it("is one event at the round's time, an hour long, titled with the round and the company", () => {
    const file = interviewCalendar(round(), role, ORIGIN, NOW);
    expect(file.startsWith("BEGIN:VCALENDAR\r\n")).toBe(true);
    expect(file.match(/BEGIN:VEVENT/g)).toHaveLength(1);
    const event = read(file);
    expect(event.get("DTSTART")).toBe("20261125T153000Z");
    expect(event.get("DTEND")).toBe("20261125T163000Z");
    expect(event.get("SUMMARY")).toBe(msg("applications-interview-calendar-title", { label: "Hiring manager", company: COMPANY }));
    expect(event.get("DTSTAMP")).toBe("20261121T120000Z");
  });

  it("keeps the round's own id, so a second import updates the event instead of adding one", () => {
    const first = read(interviewCalendar(round(), role, ORIGIN, NOW)).get("UID");
    const moved = read(interviewCalendar(round({ scheduled_at: "2026-11-27T10:00:00Z" }), role, ORIGIN, NOW)).get("UID");
    const other = read(interviewCalendar(round({ id: 42 }), role, ORIGIN, NOW)).get("UID");
    expect(moved).toBe(first);
    expect(other).not.toBe(first);
  });

  it("says the role, the format and the call link, links back to the role, and leaves the person's notes out", () => {
    const event = read(interviewCalendar(round(), role, ORIGIN, NOW));
    expect(event.get("DESCRIPTION")!.split("\n")).toEqual([
      msg("applications-interview-for", { title: role.title, company: COMPANY }),
      msg("applications-interview-format-video"),
      "https://meet.example.com/abc-defg",
      `${ORIGIN}/company/stripe/job/202?tab=workspace`,
    ]);
    expect(event.get("LOCATION")).toBe("https://meet.example.com/abc-defg");
    expect(event.get("URL")).toBe("https://meet.example.com/abc-defg");
    expect(interviewCalendar(round(), role, ORIGIN, NOW)).not.toContain("roadmap");
  });

  it("has no place or address when the round has no link", () => {
    const event = read(interviewCalendar(round({ link: null, format: "onsite" }), role, ORIGIN, NOW));
    expect(event.has("LOCATION")).toBe(false);
    expect(event.has("URL")).toBe(false);
  });

  it("puts an all-day round on its own day, the whole day", () => {
    const event = read(interviewCalendar(round({ all_day: true, scheduled_at: new Date(2026, 10, 30).toISOString() }), role, ORIGIN, NOW));
    expect(event.has("DTSTART")).toBe(false);
    expect(event.get("DTSTART;VALUE=DATE")).toBe("20261130");
    expect(event.get("DTEND;VALUE=DATE"), "the next day, across the month's end").toBe("20261201");
  });

  it("escapes what the format reserves, so a comma or semicolon in a name stays in it", () => {
    const file = interviewCalendar(round({ label: "Panel; system design, part 2\\3" }), role, ORIGIN, NOW);
    expect(file).toContain("Panel\\; system design\\, part 2\\\\3");
    expect(read(file).get("SUMMARY")).toBe(msg("applications-interview-calendar-title", { label: "Panel; system design, part 2\\3", company: COMPANY }));
  });

  it("ends every line with CRLF and keeps each within 75 octets, never splitting a character", () => {
    const label = `${"面试".repeat(30)} with the whole team`;
    const file = interviewCalendar(round({ label }), role, ORIGIN, NOW);
    expect(file.endsWith("\r\n")).toBe(true);
    expect(file.replace(/\r\n/g, "")).not.toMatch(/[\r\n]/);
    const encoder = new TextEncoder();
    for (const line of file.split("\r\n")) expect(encoder.encode(line).length).toBeLessThanOrEqual(75);
    expect(read(file).get("SUMMARY")).toContain(label);
  });
});

describe("the calendar file's name", () => {
  it("names the company and the round in plain letters", () => {
    expect(interviewCalendarName(round({ label: "Hiring manager: Café / onsite" }), role)).toBe("stripe-hiring-manager-cafe-onsite.ics");
    expect(interviewCalendarName(round({ label: "面试" }), { ...role, company: "" })).toBe("interview.ics");
  });
});

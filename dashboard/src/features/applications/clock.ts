/* A time of day as the interview form keeps it: "HH:MM" on a 24-hour clock,
 * in the reader's own zone, or "" for none. The list offers every quarter
 * hour; the field reads what a person types. */

import { time as formatTime } from "../../copy/format";

const pad = (n: number) => String(n).padStart(2, "0");

/** Every quarter hour of a day, "00:00" to "23:45". */
export const QUARTER_HOURS: readonly string[] = Array.from({ length: 96 }, (_, i) => `${pad(Math.floor(i / 4))}:${pad((i % 4) * 15)}`);

/** A clock as the reader's language writes it ("2:30 PM", "14:30"). */
export function clockLabel(clock: string): string {
  const [hours, minutes] = clock.split(":").map(Number);
  return formatTime(new Date(2000, 0, 1, hours, minutes));
}

/**
 * The clock a typed time names, or null when it names none. Reads "2", "2pm",
 * "2:30 pm", "2.30p", "14:30", "1430" and "14h30", and anything written the
 * way the list writes it in the reader's language. An hour with no am or pm
 * is taken as written, on a 24-hour clock.
 */
export function parseClock(text: string): string | null {
  const typed = text.trim().toLowerCase().replace(/\s+/g, " ");
  if (!typed) return null;
  const listed = QUARTER_HOURS.find((clock) => clockLabel(clock).toLowerCase() === typed);
  if (listed) return listed;
  const match = /^(\d{1,2})(?:[:.h ]?(\d{2}))? ?([ap])?\.?(?:m\.?)?$/.exec(typed);
  if (!match) return null;
  let hours = Number(match[1]);
  const minutes = match[2] == null ? 0 : Number(match[2]);
  const half = match[3];
  if (minutes > 59) return null;
  if (half) {
    if (hours < 1 || hours > 12) return null;
    hours = (hours % 12) + (half === "p" ? 12 : 0);
  } else if (hours > 23) {
    return null;
  }
  return `${pad(hours)}:${pad(minutes)}`;
}

/** The quarter hour a list opens on: the chosen clock's, or nine in the
 *  morning when none is chosen. */
export function anchorClock(clock: string): string {
  if (!clock) return "09:00";
  const [hours, minutes] = clock.split(":").map(Number);
  return QUARTER_HOURS[hours * 4 + Math.floor(minutes / 15)];
}

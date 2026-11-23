/* Formatting implementation. Public API: ../format.ts. Its own module, apart
   from display.ts, because the app shell loads display.ts: a function living
   there ships in the shell as soon as any lazy screen calls it. */
import {wordsLanguage} from "../runtime";
import {intl, mark} from "./core";

/** "today", "yesterday", "10 days ago": a count of whole days, never rounded
 *  up to weeks or months, for a column read down where the counts compare. */
export const daysAgo = (days: number): string =>
  mark(intl(Intl.RelativeTimeFormat, wordsLanguage(), { numeric: "auto" }).format(-days, "day"));

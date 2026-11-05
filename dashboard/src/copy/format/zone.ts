/* Formatting implementation. Public API: ../format.ts. */
import {intl, mark, wordsTag} from "./core";


/** The reader's own time zone by its long name in the words' language
 *  ("Pacific Standard Time"), or its id where the runtime has no name. */
export const timeZone = (at: Date = new Date()): string =>
  mark(
    intl(Intl.DateTimeFormat, wordsTag(), { timeZoneName: "long" }).formatToParts(at).find((part) => part.type === "timeZoneName")?.value
      ?? intl(Intl.DateTimeFormat, wordsTag()).resolvedOptions().timeZone,
  );

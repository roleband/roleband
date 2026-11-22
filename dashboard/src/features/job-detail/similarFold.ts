/* Whether the posting's "More like this" section is folded to its heading:
 * one of the person's view choices (hooks/viewChoices), the same for every
 * posting and in any browser. A failed save keeps it for this visit. */

import { setViewChoice, viewChoice } from "../../hooks/viewChoices";

const CHOICE = "posting.similar-folded";

export const readSimilarFolded = (): boolean => viewChoice(CHOICE) === true;

export function writeSimilarFolded(folded: boolean): void {
  void setViewChoice(CHOICE, folded);
}

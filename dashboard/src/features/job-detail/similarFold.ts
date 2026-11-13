/* Whether the posting's "More like this" section is folded to its heading.
 * A preference of this browser, as the theme is, never a setting, and the
 * same for every posting. Storage can throw on access (blocked site data, a
 * private window), so a failed read shows the section and a failed write is
 * dropped: the choice still holds for this visit. */

const KEY = "roleband.posting-similar-folded";

export function readSimilarFolded(): boolean {
  try {
    return localStorage.getItem(KEY) === "1";
  } catch {
    return false;
  }
}

export function writeSimilarFolded(folded: boolean): void {
  try {
    if (folded) localStorage.setItem(KEY, "1");
    else localStorage.removeItem(KEY);
  } catch {
    // Not remembered: the next visit shows the section.
  }
}

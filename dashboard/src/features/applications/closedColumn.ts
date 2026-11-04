/* Whether the Closed column is hidden: a preference of this browser, as the
 * theme is, never a setting. Storage can throw on access (blocked site data,
 * a private window), so a failed read shows the column and a failed write is
 * dropped: the button still works for this visit. */

const KEY = "roleband.pipeline-closed-hidden";

export function readClosedHidden(): boolean {
  try {
    return localStorage.getItem(KEY) === "1";
  } catch {
    return false;
  }
}

export function writeClosedHidden(hidden: boolean): void {
  try {
    if (hidden) localStorage.setItem(KEY, "1");
    else localStorage.removeItem(KEY);
  } catch {
    // Not remembered: the next visit shows the column.
  }
}

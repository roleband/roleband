/* Where a browser kept the person's view choices before they moved to the
 * database, and how each key's text becomes those choices. Read once per
 * page, after the database answers (`viewChoices.ts`); nothing writes these
 * keys any more. Names a later version no longer has are dropped here, so the
 * database's check never refuses a choice and leaves it in the browser. */

const WORKSPACE_STAGES = ["saved", "researching", "applied", "interviewing", "offer", "accepted", "ended"];
const WORKSPACE_BLOCKS = ["interviews", "next", "notes", "outcome", "activity"];
const BOARD_COLUMNS = ["saved", "researching", "applied", "interviewing", "offer", "decided", "closed"];
const LIST_COLUMNS = ["role", "pay", "location", "level", "posting", "saved", "next", "priority", "activity"];
const FILTER_KEYS = [
  "board", "board:open", "companies", "companies:open", "notifications:open", "notifications:params",
  "pipeline-list:params", "pipeline-board:params", "pipeline-up-next:params",
];
const MAX_DISMISSED = 500;

/** Keys that held choices, and the choices they held. The keys leave the
 *  browser once every one of those choices is in the database. */
export interface BrowserChoices {
  keys: string[];
  choices: Record<string, unknown>;
}

function stored(key: string): { found: boolean; value: unknown } {
  let text: string | null;
  try {
    text = localStorage.getItem(key);
  } catch {
    return { found: false, value: undefined };
  }
  if (text === null) return { found: false, value: undefined };
  try {
    return { found: true, value: JSON.parse(text) };
  } catch {
    return { found: true, value: undefined };
  }
}

const isRecord = (value: unknown): value is Record<string, unknown> =>
  typeof value === "object" && value !== null && !Array.isArray(value);

const known = (value: unknown, names: readonly string[]): string[] =>
  Array.isArray(value) ? [...new Set(value.filter((one): one is string => typeof one === "string" && names.includes(one)))] : [];

export function browserChoices(): BrowserChoices[] {
  const groups: BrowserChoices[] = [];
  const group = (keys: string[], choices: Record<string, unknown>) => groups.push({ keys, choices });

  const hidden = stored("roleband.pipeline-hidden-columns");
  // The one choice the board offered before, hiding Closed, is the default too.
  const closed = stored("roleband.pipeline-closed-hidden");
  if (hidden.found || closed.found) {
    group(["roleband.pipeline-hidden-columns", "roleband.pipeline-closed-hidden"],
      hidden.found && Array.isArray(hidden.value) ? { "pipeline.board-hidden": known(hidden.value, BOARD_COLUMNS) } : {});
  }

  const list = stored("roleband.pipeline-list-columns");
  if (list.found) {
    group(["roleband.pipeline-list-columns"], isRecord(list.value)
      ? { "pipeline.list-layout": { order: known(list.value.order, LIST_COLUMNS), hidden: known(list.value.hidden, LIST_COLUMNS) } }
      : {});
  }

  const dismissed = stored("roleband.pipeline-crossings-dismissed");
  if (dismissed.found) {
    const keys = Array.isArray(dismissed.value)
      ? dismissed.value.filter((key): key is string => typeof key === "string" && key.length > 0 && key.length <= 120)
      : [];
    group(["roleband.pipeline-crossings-dismissed"], keys.length ? { "pipeline.crossings-dismissed": keys.slice(-MAX_DISMISSED) } : {});
  }

  try {
    const folded = localStorage.getItem("roleband.posting-similar-folded");
    if (folded !== null) group(["roleband.posting-similar-folded"], folded === "1" ? { "posting.similar-folded": true } : {});
  } catch {
    // Storage that cannot be read holds nothing to move.
  }

  try {
    const view = localStorage.getItem("roleband.insights-view");
    if (view !== null) group(["roleband.insights-view"], view === "basic" || view === "advanced" ? { "insights.view": view } : {});
  } catch {
    // Storage that cannot be read holds nothing to move.
  }

  const workspaceHidden = stored("roleband.pipeline-workspace-hidden");
  const workspaceOrder = stored("roleband.pipeline-workspace-order");
  if (workspaceHidden.found || workspaceOrder.found) {
    const byStage = (value: unknown) => (isRecord(value) ? value : {});
    const hiddenBy = byStage(workspaceHidden.value);
    const orderBy = byStage(workspaceOrder.value);
    group(["roleband.pipeline-workspace-hidden", "roleband.pipeline-workspace-order"], Object.fromEntries(
      WORKSPACE_STAGES.filter((stage) => stage in hiddenBy || stage in orderBy).map((stage) => [
        `workspace.${stage}`,
        { hidden: known(hiddenBy[stage], WORKSPACE_BLOCKS), order: known(orderBy[stage], WORKSPACE_BLOCKS) },
      ]),
    ));
  }

  for (const key of FILTER_KEYS) {
    const filters = stored(`roleband.filters.v1:${key}`);
    if (filters.found) group([`roleband.filters.v1:${key}`], isRecord(filters.value) ? { [`filters.${key}`]: filters.value } : {});
  }
  return groups;
}

export function forgetBrowserKeys(keys: readonly string[]): void {
  try {
    keys.forEach((key) => localStorage.removeItem(key));
  } catch {
    // Storage that cannot be read holds nothing to move.
  }
}

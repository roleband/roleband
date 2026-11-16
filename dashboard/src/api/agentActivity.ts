/* Agent activity: every read, change and refusal by a connected assistant app,
   newest first, for the Activity screen. One domain of the typed client;
   `index.ts` composes `api`. */

import type { operations } from "../api.gen";
import type { Schemas } from "./schemas";
import { getJSON, qs } from "./transport";

type ActivityQuery = NonNullable<operations["agent_activity_api_agent_activity_get"]["parameters"]["query"]>;

/** One entry. `subject.topic` names what it says; the subject's other keys
 *  are the facts it is said from (a role's `title` and `company`, a `count`,
 *  a `stage` slug). `summary` is the same sentence in English. */
export type ActivityEntry = Schemas["ActivityEntry"];
/** One page, and the cursor of the next, older one (null on the last). */
export type ActivityPage = Schemas["ActivityPageResponse"];
export type ActivityKind = ActivityEntry["kind"];
/** A data category slug, as the list filters by it. */
export type ActivityCategory = NonNullable<ActivityQuery["category"]>;

export interface ActivityParams {
  q?: string | null;
  kind?: "all" | ActivityKind;
  /** The entries that read this category, or asked for it. */
  category?: ActivityCategory | null;
  /** ISO instants: `since` inclusive, `until` exclusive. */
  since?: string | null;
  until?: string | null;
  cursor?: string | null;
}

export const agentActivityApi = {
  agentActivity: (params: ActivityParams, signal?: AbortSignal) =>
    getJSON<ActivityPage>(`/api/agent-activity?${qs(params)}`, signal),
};

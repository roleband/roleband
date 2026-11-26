/* Top picks: what the rail and the screen read of the mode, and the screen's
   way to resume the checks. One domain of the typed client; the two calls the
   shell makes live in `startup.ts`. The list is `/api/jobs?top_picks=true`. */

import type { Schemas } from "./schemas";
import { getJSON, putJSON } from "./transport";

/** `GET /api/picks/state`: the mode, the last check, and whether a pick
 *  arrived since the person last opened Top picks (`unseen_pick`). */
export type PicksState = Schemas["PicksStateResponse"];

/** `GET /api/picks/passed`: what the assistant read this week and did not
 *  pick, and what the hard rules ruled out before any reading. */
export type PassedOver = Schemas["PassedOverResponse"];
/** Why a role was passed. */
export type PassCode = PassedOver["passes"][number]["code"];
/** `GET /api/picks/removed`: the picks the person marked Not for me. */
export type RemovedPicks = Schemas["RemovedPicksResponse"];

export const picksApi = {
  /** Pause or resume the checks. */
  setPicksMode: (state: "on" | "off") => putJSON<PicksState>("/api/picks/mode", { state }),
  picksPassed: (signal?: AbortSignal) => getJSON<PassedOver>("/api/picks/passed", signal),
  picksRemoved: (signal?: AbortSignal) => getJSON<RemovedPicks>("/api/picks/removed", signal),
};

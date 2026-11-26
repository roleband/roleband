/* Top picks: what the rail and the screen read of the mode, the screen's way
   to resume the checks, and what the Settings card changes. One domain of the
   typed client; the two calls the shell makes live in `startup.ts`. The list
   is `/api/jobs?top_picks=true`. */

import type { Schemas } from "./schemas";
import { deleteJSON, getJSON, putJSON } from "./transport";

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
/** `DELETE /api/picks/setup`: how much was deleted. */
export type PicksSetupRemoved = Schemas["PicksRemovedResponse"];

export const picksApi = {
  /** Pause or resume the checks. */
  setPicksMode: (state: "on" | "off") => putJSON<PicksState>("/api/picks/mode", { state }),
  picksPassed: (signal?: AbortSignal) => getJSON<PassedOver>("/api/picks/passed", signal),
  picksRemoved: (signal?: AbortSignal) => getJSON<RemovedPicks>("/api/picks/removed", signal),
  /** The most roles read in a day, from 1 to the state's `daily_limit_max`. */
  setPicksDailyLimit: (daily_limit: number) => putJSON<PicksState>("/api/picks/mode", { daily_limit }),
  /** Delete the CV, what was read from it, the brief and the reasons on past
   *  picks; the mode goes back to never set up. */
  removePicksSetup: () => deleteJSON<PicksSetupRemoved>("/api/picks/setup"),
};

/* Top picks: what the rail and the screen read of the mode, and the screen's
   way to resume the checks. One domain of the typed client; the two calls the
   shell makes live in `startup.ts`. The list is `/api/jobs?top_picks=true`. */

import type { Schemas } from "./schemas";
import { putJSON } from "./transport";

/** `GET /api/picks/state`: the mode, the last check, and whether a pick
 *  arrived since the person last opened Top picks (`unseen_pick`). */
export type PicksState = Schemas["PicksStateResponse"];

export const picksApi = {
  /** Pause or resume the checks. */
  setPicksMode: (state: "on" | "off") => putJSON<PicksState>("/api/picks/mode", { state }),
};

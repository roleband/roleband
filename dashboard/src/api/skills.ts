/* Skills: the leaderboard.
   One domain of the typed client; `index.ts` composes `api`. */

import type { Schemas } from "./schemas";
import { qs, getJSON } from "./transport";
import { type InsightsScope, scoped } from "./statistics";

/** A concept by the open roles requiring it; `specificity` is their mean importance, 0 to 1. */
export type TopSkill = Schemas["TopSkill"];

export type TopSkills = Schemas["TopSkillsResponse"];

export interface SkillsQuery {
  company?: string[];
  family?: string[];
  location_group?: string[];
  limit?: number;
}

export const skillsApi = {
  skillsTop: (q: SkillsQuery = {}, signal?: AbortSignal, scope?: InsightsScope) =>
    getJSON<TopSkills>(scoped(`/api/skills/top?${qs(q)}`, scope), signal),
};

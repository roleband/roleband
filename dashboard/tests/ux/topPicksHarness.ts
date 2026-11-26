/* Top picks as a person with picks sees it: the Radar's routes, the checks on
   and healthy, and a list of picks with their reasons. The list and the
   facets answer the Top picks lens only (`top_picks=true`); the Radar's own
   reads keep the board harness's answers, so a spec that opens both screens
   sees each list where it belongs. */

import type { Page } from "@playwright/test";
import type { Job, JobList, PicksState } from "../../src/api";
import { facetsFixture, jobFixture, jobListFixture, picksStateFixture } from "../../src/test/fixtures";
import { mockApi, mockGet } from "./fixtures";
import { installBoardRoutes } from "./boardHarness";

type Row = JobList["items"][number];
type Reason = NonNullable<Job["pick_reasons"]>[number];

const REASONS: Reason[] = [
  { opening: "Staff level", rest: " at a company that pays at the top of your band." },
  { opening: "Remote", rest: " across the EU, as you asked." },
  { opening: "", rest: "A small product team that ships weekly." },
];

export const pickFixture = (over: Partial<Row> = {}): Row => ({
  ...jobFixture,
  new_listing: true,
  viewed_at: null,
  pick_reasons: REASONS,
  picked_at: "2026-11-25T08:00:00Z",
  ...over,
});

/** Two picks: the first unread, the second read. */
export const picksList = (items: Row[] = [
  pickFixture({ id: 501, title: "Staff Product Manager, API" }),
  pickFixture({ id: 502, title: "Principal Product Manager, Platform", viewed_at: "2026-11-24T09:00:00Z" }),
]): JobList => ({ ...jobListFixture, total: items.length, items });

export const healthyState = (over: Partial<PicksState> = {}): PicksState => picksStateFixture({
  state: "on",
  health: "healthy",
  routine_host: "claude-code",
  routine_host_connection: "connected",
  read_this_week: 222,
  passed_this_week: 41,
  last_check: { host: "claude-code", finished_at: new Date(Date.now() - 2 * 3_600_000).toISOString(), outcome: "finished", note: null },
  ...over,
});

const isLens = (url: string) => new URL(url).searchParams.get("top_picks") === "true";

/** The Radar's routes, then Top picks' own. Returns the opening count. */
export async function installTopPicksRoutes(
  page: Page,
  { state = healthyState(), list = picksList(), opened = state }: { state?: PicksState; list?: JobList; opened?: PicksState } = {},
) {
  await installBoardRoutes(page);
  const seen = { opened: 0 };
  await mockGet(page, "/api/picks/state", (route) => route.fulfill({ json: state }));
  await mockApi(page, "POST", "/api/picks/opened", (route) => {
    seen.opened += 1;
    return route.fulfill({ json: { ...opened, unseen_pick: false } });
  });
  await mockGet(page, "/api/jobs?**", (route) =>
    isLens(route.request().url()) ? route.fulfill({ json: list }) : route.fallback());
  await mockGet(page, "/api/facets?**", (route) =>
    isLens(route.request().url()) ? route.fulfill({ json: facetsFixture }) : route.fallback());
  return seen;
}

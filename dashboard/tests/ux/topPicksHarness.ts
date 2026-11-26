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

type PassedOver = Awaited<ReturnType<typeof import("../../src/api").api.picksPassed>>;
type RemovedPick = Awaited<ReturnType<typeof import("../../src/api").api.picksRemoved>>["picks"][number];

/** A week with one removed pick, four near misses, passes by why and what a
 *  checkable rule ruled out. Rows 601 to 605 answer the reads by id. */
const passedOverRows = (): Row[] => [
  { ...jobFixture, id: 601, title: "Principal Product Manager, Platform", company: "linear", viewed_at: null },
  { ...jobFixture, id: 602, title: "Group Product Manager, Enterprise", company: "notion", viewed_at: null },
  { ...jobFixture, id: 603, title: "Staff Product Manager, Observability", company: "datadog", viewed_at: null },
  { ...jobFixture, id: 604, title: "Principal Product Manager, AI", company: "notion", viewed_at: null },
  { ...jobFixture, id: 605, title: "Staff Product Manager, Issues", company: "linear", viewed_at: null },
];

const removedPickFixture = (over: Partial<RemovedPick> = {}): RemovedPick => ({
  job_id: 601, title: "Principal Product Manager, Platform", company: "Linear", company_slug: "linear", is_open: true,
  reasons: [], reason: "pay_too_low", reason_text: null, removed_at: "2026-11-25T10:00:00Z", judged_at: "2026-11-25T08:00:00Z",
  ...over,
});

export const passedOverFixture = (over: Partial<PassedOver> = {}): PassedOver => ({
  passed_this_week: 41,
  near_misses: [
    { job_id: 602, reason: { opening: "Mostly people management", rest: ", eight reports and little product work." }, judged_at: "2026-11-25T08:00:00Z" },
    { job_id: 603, reason: { opening: "Infrastructure", rest: ", further from customers than you asked for." }, judged_at: "2026-11-25T08:00:00Z" },
    { job_id: 604, reason: { opening: "Base around 240,000", rest: ", close to your floor." }, judged_at: "2026-11-25T08:00:00Z" },
    { job_id: 605, reason: { opening: "Same level as today", rest: ", with a smaller product." }, judged_at: "2026-11-25T08:00:00Z" },
  ],
  passes: [{ code: "hard_rule", count: 30 }, { code: "below_level", count: 5 }, { code: "off_direction", count: 2 }],
  judged_rules: ["No on-call"],
  ruled_out: 12,
  ruled_out_by_rule: [{ rule: "Base under 200,000", count: 12 }],
  ...over,
});

/** Passed over's reads, on top of Top picks' routes: the week, the removed
 *  picks, and the rows by id. */
export async function installPassedOverRoutes(
  page: Page,
  { passed = passedOverFixture(), removed = [removedPickFixture()], rows = passedOverRows() }:
    { passed?: PassedOver; removed?: RemovedPick[]; rows?: Row[] } = {},
) {
  await installTopPicksRoutes(page);
  await mockGet(page, "/api/picks/passed", (route) => route.fulfill({ json: passed }));
  await mockGet(page, "/api/picks/removed", (route) => route.fulfill({ json: { picks: removed } }));
  await mockGet(page, "/api/jobs?**", (route) => {
    const ids = new URL(route.request().url()).searchParams.getAll("ids").map(Number);
    if (ids.length === 0) return route.fallback();
    const items = rows.filter((row) => ids.includes(row.id));
    return route.fulfill({ json: { ...jobListFixture, total: items.length, items } });
  });
}

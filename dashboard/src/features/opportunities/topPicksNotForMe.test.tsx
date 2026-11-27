import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, useLocation } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { api, type Filters, type JobList } from "../../api";
import { facetsFixture, jobFixture, jobListFixture, picksStateFixture } from "../../test/fixtures";
import { msg } from "../../test/msg";
import { ToastProvider } from "../../ui";
import { TopPicksScreen } from "./TopPicksScreen";

/* Top picks' Showing control: its picks, or the picks the person marked Not
   for me, each with the assistant's reasons, what the person said and the way
   back. */

const app = vi.hoisted(() => ({
  search: "", newSignalsOnly: false, repostsOnly: false, favVersion: 0,
  refreshStats: vi.fn(), clearNewSignals: vi.fn(), clearReposts: vi.fn(),
  viewedIds: new Set<number>(), compareIds: new Set<number>(), compareFull: false, compareCap: 4,
  openJob: vi.fn(), toggleCompare: vi.fn(),
}));
vi.mock("../../context/MissionState", () => ({
  useMissionState: () => app,
  useBoardQuery: () => app,
  useMissionActions: () => app,
  useMissionStats: () => null,
}));
vi.mock("../../context/SyncState", async (importOriginal) => ({
  ...(await importOriginal<typeof import("../../context/SyncState")>()),
  useSyncEpoch: () => ({ notificationVersion: 0, referenceVersion: 0, runVersion: 0 }),
  useReferenceVersion: () => 0,
  useSyncStatus: () => ({ status: null, statusFailed: false, syncing: false, syncingCompanies: [] }),
}));
vi.mock("../../context/JobWorkspace", () => ({ useJobWorkspace: () => app, useJobActions: () => app }));

const picksOn = picksStateFixture({
  state: "on", health: "healthy", routine_host: "claude-code", routine_host_connection: "connected",
  passed_this_week: 6,
  last_check: { host: "claude-code", finished_at: "2026-11-27T08:00:00Z", outcome: "finished", note: null },
});

type Row = JobList["items"][number];

const WORDS = "The base is under what I hold today, and the team is mostly on call at weekends";
const pick: Row = {
  ...jobFixture, id: 1, title: "Staff Platform Engineer",
  pick_reasons: [{ opening: "Staff level", rest: ", one step above your role today." }],
};
const removed = (id: number, title: string, dismiss_reason: string | null, dismiss_reason_text: string | null): Row => ({
  ...jobFixture, id, title, is_dismissed: true,
  pick_reasons: [{ opening: "Leads risk", rest: " for the whole company." }],
  dismiss_reason, dismiss_reason_text,
});
const payPick = removed(7, "Principal Engineer, Payments", "pay_too_low", WORDS);
const otherPick = removed(8, "Head of Data Platform", "other", null);
const list = (items: Row[]) => ({ ...jobListFixture, items, total: items.length });

/** The rows a list request reads: the removed picks on Not for me, the picks otherwise. */
function serve(removedRows: Row[], picks: Row[] = [pick]) {
  vi.mocked(api.jobs).mockImplementation(async (filters: Filters) => list(filters.dismissed_only ? removedRows : picks));
}
const listReads = () => vi.mocked(api.jobs).mock.calls.map(([filters]) => filters).filter((f) => f.limit !== 1);
const lastRead = () => listReads().slice(-1)[0];

let address = "";
function Address() {
  const location = useLocation();
  address = `${location.pathname}${location.search}`;
  return null;
}

function mount(at = "/top-picks") {
  render(
    <MemoryRouter initialEntries={[at]}>
      <ToastProvider><Address /><TopPicksScreen /></ToastProvider>
    </MemoryRouter>,
  );
}

async function showing() {
  const user = userEvent.setup();
  await user.click(await screen.findByRole("button", { name: /^Filters/ }));
  if (!screen.queryByRole("group", { name: msg("radar-filter-showing") })) {
    await user.click(screen.getByRole("button", { name: msg("radar-filter-more") }));
  }
  return { user, group: screen.getByRole("group", { name: msg("radar-filter-showing") }) };
}

const rowOf = (title: string) => screen.getByText(title).closest<HTMLElement>(".job-card, .job-row, li, [data-job-id]")!;

beforeEach(() => {
  app.openJob.mockReset();
  vi.spyOn(api, "facets").mockResolvedValue(facetsFixture);
  vi.spyOn(api, "jobs");
  serve([payPick, otherPick]);
  vi.spyOn(api, "picksState").mockResolvedValue(picksOn);
  vi.spyOn(api, "picksOpened").mockResolvedValue(picksOn);
  vi.spyOn(api, "undismissJob").mockResolvedValue({} as never);
  vi.spyOn(api, "dismissJob").mockResolvedValue({} as never);
});
afterEach(() => vi.restoreAllMocks());

describe("Showing on Top picks", () => {
  it("offers the picks and the picks marked Not for me, with no count on either", async () => {
    mount();
    expect(await screen.findByText("Staff Platform Engineer")).toBeVisible();
    const { group } = await showing();
    const positions = within(group).getAllByRole("button");
    expect(positions.map((b) => b.textContent)).toEqual([msg("shell-nav-top-picks"), msg("shared-not-for-me")]);
    expect(within(group).getByRole("button", { name: msg("shell-nav-top-picks") })).toHaveAttribute("aria-pressed", "true");
    // The Radar's Closed is not a position here.
    expect(within(group).queryByRole("button", { name: msg("radar-mode-closed") })).toBeNull();
  });

  it("switches through the address to the removed picks, whatever their postings' status", async () => {
    mount();
    await screen.findByText("Staff Platform Engineer");
    const { user, group } = await showing();
    await user.click(within(group).getByRole("button", { name: msg("shared-not-for-me") }));

    await waitFor(() => expect(lastRead()).toMatchObject({ top_picks: true, dismissed_only: true, status: "" }));
    expect(address).toBe("/top-picks?show=not-for-me");
    expect(await screen.findByText("Principal Engineer, Payments")).toBeVisible();
    expect(screen.queryByText("Staff Platform Engineer")).toBeNull();
  });

  it("reads an address that names another of the Radar's lists as the picks", async () => {
    mount("/top-picks?show=closed");
    expect(await screen.findByText("Staff Platform Engineer")).toBeVisible();
    expect(lastRead()).toMatchObject({ top_picks: true, dismissed_only: false, status: "open" });
  });

  it("counts the removed picks as a list of their own, never as a fraction, and Show all goes back", async () => {
    mount("/top-picks?show=not-for-me");
    await screen.findByText("Principal Engineer, Payments");
    const count = document.querySelector<HTMLElement>(".results-count")!;
    expect(count).toHaveTextContent(msg("radar-count-not-for-me"));
    expect(count.textContent).not.toMatch(/\bof\b/);

    await userEvent.click(within(count).getByRole("button", { name: msg("radar-show-all") }));
    await waitFor(() => expect(address).toBe("/top-picks"));
    expect(await screen.findByText("Staff Platform Engineer")).toBeVisible();
  });
});

describe("a pick marked Not for me", () => {
  it("keeps the assistant's reasons, and says what the person said, in their own words, beside them", async () => {
    mount("/top-picks?show=not-for-me");
    await screen.findByText("Principal Engineer, Payments");
    const row = rowOf("Principal Engineer, Payments");
    expect(within(row).getByText("Leads risk")).toHaveClass("pick-reason-opening");
    const said = row.querySelector<HTMLElement>(".pick-said")!;
    expect(said.textContent).toBe(
      `${msg("picks-removed-said", { reason: "pay_too_low" })} ${msg("picks-removed-words", { words: WORDS })} ${msg("picks-removed-put-back")}`,
    );
    // The person's words are theirs: content, never translated.
    expect(within(said).getByText(WORDS)).toHaveAttribute("data-copy", "content");
  });

  it("ends the person's words once, though they ended them with a full stop", async () => {
    serve([removed(9, "Staff Engineer, Ledger", "company", "  Not this company again. ")]);
    mount("/top-picks?show=not-for-me");
    await screen.findByText("Staff Engineer, Ledger");
    const said = rowOf("Staff Engineer, Ledger").querySelector<HTMLElement>(".pick-said")!;
    expect(said.textContent).toBe(
      `${msg("picks-removed-said", { reason: "company" })} ${msg("picks-removed-words", { words: "Not this company again" })} ${msg("picks-removed-put-back")}`,
    );
    expect(said.textContent).not.toMatch(/\.\S?\./u);
  });

  it("says only the way back for something else with no words", async () => {
    mount("/top-picks?show=not-for-me");
    await screen.findByText("Head of Data Platform");
    expect(rowOf("Head of Data Platform").querySelector(".pick-said")?.textContent).toBe(msg("picks-removed-put-back"));
  });

  it("names every reason code a dismissal can store in words of its own, none of them the catch-all", () => {
    const codes = ["pay_too_low", "wrong_level", "wrong_role", "company", "wrong_place", "wrong_domain"];
    const said = codes.map((reason) => msg("picks-removed-said", { reason }));
    expect(new Set(said).size).toBe(codes.length);
    expect(said).not.toContain(msg("picks-removed-said", { reason: "unknown" }));
  });

  it("goes back with Put it back: Not for me is cleared, the row leaves the list and the role does not open", async () => {
    mount("/top-picks?show=not-for-me");
    await screen.findByText("Principal Engineer, Payments");
    const row = rowOf("Principal Engineer, Payments");
    await userEvent.click(within(row).getByRole("button", { name: msg("picks-removed-put-back-name", { title: "Principal Engineer, Payments" }) }));

    expect(api.undismissJob).toHaveBeenCalledExactlyOnceWith(7);
    await waitFor(() => expect(screen.queryByText("Principal Engineer, Payments")).toBeNull());
    expect(app.openJob).not.toHaveBeenCalled();
    expect(api.dismissJob).not.toHaveBeenCalled();
  });

  it("offers one way back, the link, which names the role and is reached by Tab; the row has no Restore", async () => {
    mount("/top-picks?show=not-for-me");
    await screen.findByText("Head of Data Platform");
    for (const title of ["Principal Engineer, Payments", "Head of Data Platform"]) {
      const row = rowOf(title);
      expect(within(row).queryByRole("button", { name: msg("jobs-restore") })).toBeNull();
      expect(within(row).queryByRole("button", { name: msg("shared-not-for-me") })).toBeNull();
      expect(within(row).getAllByRole("button", { name: new RegExp(msg("picks-removed-put-back")) })).toHaveLength(1);
    }
    // Keyboard: Tab reaches the link, Enter puts the role back without asking why.
    const link = within(rowOf("Head of Data Platform")).getByRole("button", { name: msg("picks-removed-put-back-name", { title: "Head of Data Platform" }) });
    for (let step = 0; step < 60 && document.activeElement !== link; step++) await userEvent.tab();
    expect(link).toHaveFocus();
    await userEvent.keyboard("{Enter}");
    expect(api.undismissJob).toHaveBeenCalledExactlyOnceWith(8);
    expect(screen.queryByRole("heading", { name: msg("picks-why-title") })).toBeNull();
    await waitFor(() => expect(screen.queryByText("Head of Data Platform")).toBeNull());
  });

  it("keeps Not for me on the open picks' rows", async () => {
    mount("/top-picks");
    await screen.findByText("Staff Platform Engineer");
    expect(within(rowOf("Staff Platform Engineer")).getByRole("button", { name: msg("shared-not-for-me") })).toBeVisible();
  });

  it("comes back to the list when it could not be put back", async () => {
    vi.mocked(api.undismissJob).mockRejectedValue(new Error("engine away"));
    mount("/top-picks?show=not-for-me");
    await screen.findByText("Principal Engineer, Payments");
    const reads = listReads().length;
    await userEvent.click(within(rowOf("Principal Engineer, Payments")).getByRole("button", { name: msg("picks-removed-put-back-name", { title: "Principal Engineer, Payments" }) }));

    await waitFor(() => expect(listReads().length).toBeGreaterThan(reads));
    expect(await screen.findByText("Principal Engineer, Payments")).toBeVisible();
  });

  it("still asks why before a pick on the picks list is removed", async () => {
    mount();
    await screen.findByText("Staff Platform Engineer");
    await userEvent.click(within(rowOf("Staff Platform Engineer")).getByRole("button", { name: msg("shared-not-for-me") }));
    expect(await screen.findByRole("heading", { name: msg("picks-why-title") })).toBeVisible();
    expect(api.dismissJob).not.toHaveBeenCalled();
    expect(api.undismissJob).not.toHaveBeenCalled();
  });
});

describe("the Not for me list's edges", () => {
  it("says, in the house empty box, that nothing is marked, with the way back to the picks", async () => {
    serve([]);
    mount("/top-picks?show=not-for-me");
    const title = await screen.findByText(msg("picks-removed-empty-title"));
    const box = title.closest<HTMLElement>(".empty")!;
    expect(box).not.toBeNull();
    expect(box).toHaveTextContent(msg("picks-removed-empty"));
    await userEvent.click(within(box).getByRole("button", { name: msg("radar-show-all") }));
    await waitFor(() => expect(address).toBe("/top-picks"));
  });

  it("says a filter emptied it, not that nothing is marked, and Reset all clears the filter on this list", async () => {
    serve([]);
    mount("/top-picks?show=not-for-me&company=stripe");
    const title = await screen.findByText(msg("picks-empty-filtered-title"));
    expect(screen.queryByText(msg("picks-removed-empty-title"))).toBeNull();
    await userEvent.click(within(title.closest<HTMLElement>(".empty")!).getByRole("button", { name: msg("radar-reset") }));
    await waitFor(() => expect(lastRead().company ?? []).toEqual([]));
    expect(lastRead().dismissed_only).toBe(true);
    expect(address).toMatch(/show=not-for-me/);
  });

  it("says the search found nothing, not that nothing is marked", async () => {
    serve([]);
    mount("/top-picks?show=not-for-me");
    await screen.findByText(msg("picks-removed-empty-title"));
    await userEvent.type(screen.getByRole("searchbox"), "ledger");
    expect(await screen.findByText(msg("picks-empty-search-title"))).toBeVisible();
    expect(screen.queryByText(msg("picks-removed-empty-title"))).toBeNull();
  });

  it("ends without the picks' end line, which is about the checks", async () => {
    mount("/top-picks?show=not-for-me");
    await screen.findByText("Principal Engineer, Payments");
    expect(screen.queryByText(msg("picks-end-passed", { count: 6 }))).toBeNull();
    expect(document.querySelector(".board-list-end")).toBeNull();
  });

  it("keeps the end line under the picks", async () => {
    mount();
    await screen.findByText("Staff Platform Engineer");
    expect(screen.getByRole("link", { name: msg("picks-end-passed", { count: 6 }) })).toHaveAttribute("href", "/top-picks/passed");
  });
});

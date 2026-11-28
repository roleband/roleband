import { act, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { ReactElement } from "react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { api } from "../../api";
import { facetsFixture, jobFixture, jobListFixture, picksStateFixture } from "../../test/fixtures";
import { msg } from "../../test/msg";
import { ToastProvider } from "../../ui";
import { BoardScreen } from "./BoardScreen";
import { TopPicksScreen } from "./TopPicksScreen";

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
const epoch = vi.hoisted(() => ({ notificationVersion: 0, referenceVersion: 0, runVersion: 0 }));
vi.mock("../../context/SyncState", async (importOriginal) => ({
  ...(await importOriginal<typeof import("../../context/SyncState")>()),
  useSyncEpoch: () => epoch,
  useReferenceVersion: () => epoch.referenceVersion,
  useSyncStatus: () => ({ status: null, statusFailed: false, syncing: false, syncingCompanies: [] }),
}));
vi.mock("../../context/JobWorkspace", () => ({ useJobWorkspace: () => app, useJobActions: () => app }));

const picksOn = picksStateFixture({
  state: "on", health: "healthy", routine_host: "claude-code", routine_host_connection: "connected",
});
const listed = { ...jobListFixture, items: [{ ...jobFixture, title: "Staff Platform Engineer" }], total: 1 };
const listCalls = () => vi.mocked(api.jobs).mock.calls.filter(([params]) => params.limit !== 1).length;

beforeEach(() => {
  epoch.referenceVersion = 0;
  epoch.runVersion = 0;
  vi.spyOn(api, "facets").mockResolvedValue(facetsFixture);
  vi.spyOn(api, "jobs").mockResolvedValue(listed);
  vi.spyOn(api, "picksState").mockResolvedValue(picksOn);
  vi.spyOn(api, "picksOpened").mockResolvedValue(picksOn);
});
afterEach(() => vi.restoreAllMocks());

const radar = (mode: "open" | "closed" = "open") =>
  <BoardScreen companyParam={[]} onCompanyParamChange={vi.fn()} mode={mode} onModeChange={vi.fn()} />;

function mount(screenUnderTest: () => ReactElement) {
  const tree = () => <MemoryRouter><ToastProvider>{screenUnderTest()}</ToastProvider></MemoryRouter>;
  const view = render(tree());
  return () => view.rerender(tree());
}

const screens: Array<[string, () => ReactElement, string]> = [
  ["the Radar", radar, msg("radar-refresh-failed")],
  ["Top picks", () => <TopPicksScreen />, msg("picks-refresh-failed")],
];

describe.each(screens)("a background refresh of the list on %s", (_name, screenUnderTest, failed) => {
  /* Estimates moving together re-read the page in place; that read failing is
     the background failure this screen has to say. */
  async function failARefresh(rerender: () => void) {
    vi.mocked(api.jobs).mockRejectedValue(new Error("engine away"));
    const before = listCalls();
    epoch.referenceVersion += 1;
    act(rerender);
    await waitFor(() => expect(listCalls()).toBeGreaterThan(before));
  }

  it("keeps the rows and says the update failed, with Try again", async () => {
    const rerender = mount(screenUnderTest);
    expect(await screen.findByText("Staff Platform Engineer")).toBeVisible();
    expect(screen.queryByText(failed)).toBeNull();

    await failARefresh(rerender);

    // The line is announced, and its Try again sits in it.
    const line = (await screen.findByText(failed)).closest<HTMLElement>("[role=status]");
    expect(line).not.toBeNull();
    expect(line).toBeVisible();
    expect(within(line!).getByRole("button", { name: msg("common-try-again") })).toBeVisible();
    expect(screen.getByText("Staff Platform Engineer")).toBeVisible();
  });

  it("keeps the rows when Try again fails too, and takes the new list once it answers", async () => {
    const user = userEvent.setup();
    const rerender = mount(screenUnderTest);
    await screen.findByText("Staff Platform Engineer");
    await failARefresh(rerender);
    await screen.findByText(failed);

    let before = listCalls();
    await user.click(screen.getByRole("button", { name: msg("common-try-again") }));
    await waitFor(() => expect(listCalls()).toBeGreaterThan(before));
    expect(await screen.findByText(failed)).toBeVisible();
    expect(screen.getByText("Staff Platform Engineer")).toBeVisible();
    expect(screen.queryByText(msg("radar-load-failed"))).toBeNull();

    vi.mocked(api.jobs).mockResolvedValue({ ...listed, items: [{ ...jobFixture, title: "Principal Engineer" }] });
    before = listCalls();
    await user.click(screen.getByRole("button", { name: msg("common-try-again") }));

    expect(await screen.findByText("Principal Engineer")).toBeVisible();
    expect(listCalls()).toBeGreaterThan(before);
    expect(screen.queryByText(failed)).toBeNull();
  });
});

describe("a scan finishes while Radar is open", () => {
  const failed = msg("radar-refresh-failed");
  const showUpdate = msg("radar-board-fresh-show");
  const newer = {
    ...listed, total: 2, items: [{ ...jobFixture, id: 202, title: "Principal Engineer" }, ...listed.items],
  };

  it("keeps the list and focus through failed retries and offers the successful read", async () => {
    const user = userEvent.setup();
    const rerender = mount(radar);
    await screen.findByText("Staff Platform Engineer");
    const row = screen.getByRole("article");
    row.focus();

    vi.mocked(api.jobs).mockRejectedValueOnce(new Error("scan update unavailable"));
    epoch.runVersion += 1;
    act(rerender);
    const notice = (await screen.findByText(failed)).closest<HTMLElement>("[role=status]")!;
    const retry = within(notice).getByRole("button", { name: msg("common-try-again") });
    expect(row).toHaveFocus();

    let failRetry!: (error: Error) => void;
    const pending = new Promise<never>((_resolve, reject) => { failRetry = reject; });
    vi.mocked(api.jobs).mockReturnValueOnce(pending);
    const before = listCalls();
    retry.focus();
    await user.keyboard("{Enter}");
    expect(listCalls()).toBe(before + 1);
    expect(screen.getByRole("article")).toBe(row);
    expect(retry).toHaveFocus();
    await act(async () => failRetry(new Error("still unavailable")));
    expect(retry).toBeVisible();
    expect(retry).toHaveFocus();

    vi.mocked(api.jobs).mockResolvedValueOnce(newer);
    await user.keyboard("{Enter}");
    const accept = await screen.findByRole("button", { name: showUpdate });
    expect(accept).toHaveFocus();
    expect(screen.getByRole("article")).toBe(row);
    expect(screen.queryByText("Principal Engineer")).toBeNull();
    await user.keyboard("{Enter}");
    expect(await screen.findByText("Principal Engineer")).toBeVisible();
    expect(screen.queryByText(failed)).toBeNull();
  });

  it.each([
    { next: "with a newer offer", offer: true },
    { next: "without a newer offer", offer: false },
  ])("ignores a read that fails after Showing changes, $next", async ({ offer }) => {
    let mode: "open" | "closed" = "open";
    const rerender = mount(() => radar(mode));
    await screen.findByText("Staff Platform Engineer");
    let failOlder!: (error: Error) => void;
    const pending = new Promise<never>((_resolve, reject) => { failOlder = reject; });
    vi.mocked(api.jobs).mockReturnValueOnce(pending);
    const before = listCalls();
    epoch.runVersion += 1;
    act(rerender);
    expect(listCalls()).toBe(before + 1);

    const closedRow = { ...jobFixture, id: 301, status: "closed", title: "Closed position" };
    vi.mocked(api.jobs).mockResolvedValueOnce({ ...listed, items: [closedRow] });
    mode = "closed";
    act(rerender);
    expect(await screen.findByText(closedRow.title)).toBeVisible();
    expect(screen.queryByText(failed)).toBeNull();

    if (offer) {
      vi.mocked(api.jobs).mockResolvedValueOnce({ ...newer, items: [newer.items[0], closedRow] });
      epoch.runVersion += 1;
      act(rerender);
      await screen.findByRole("button", { name: showUpdate });
    }

    await act(async () => failOlder(new Error("obsolete scan update")));
    expect(screen.queryByText(failed)).toBeNull();
    expect(screen.queryByText("Principal Engineer")).toBeNull();
    if (offer) {
      await userEvent.click(screen.getByRole("button", { name: showUpdate }));
      expect(await screen.findByText("Principal Engineer")).toBeVisible();
    } else {
      expect(screen.queryByRole("button", { name: showUpdate })).toBeNull();
    }
  });
});

import { act, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useState, type ReactElement } from "react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { api } from "../../api";
import { usePicksDot } from "../../hooks/picksDot";
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

/** The state after the check that closed at `hour` (o'clock today). */
const picksOn = (unseen_pick: boolean, hour = 8) => picksStateFixture({
  state: "on", health: "healthy", routine_host: "claude-code", routine_host_connection: "connected", unseen_pick,
  last_check: { host: "claude-code", finished_at: `2026-11-27T${String(hour).padStart(2, "0")}:00:00Z`, outcome: "finished", note: null },
});
const job = (id: number, title: string) => ({ ...jobFixture, id, title });
const firstPick = job(1, "Staff Platform Engineer");
const newPick = job(2, "Principal Engineer");
const onePick = { ...jobListFixture, items: [firstPick], total: 1 };
const twoPicks = { ...jobListFixture, items: [newPick, firstPick], total: 2 };
const laterPick = job(3, "Head of Data Platform");
const threePicks = { ...jobListFixture, items: [laterPick, newPick, firstPick], total: 3 };

/** A promise the test settles when it chooses. */
function deferred<T>() {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>((res) => { resolve = res; });
  return { promise, resolve };
}
const listCalls = () => vi.mocked(api.jobs).mock.calls.filter(([params]) => params.limit !== 1).length;

/* The rail, as far as this needs it: the dot and the read behind it. A new key
   remounts it, and a remount reads the picks state at once, as the minute's
   read or coming back to the tab does. */
let readAgain: () => void = () => {};
function Rail() {
  const [key, setKey] = useState(0);
  readAgain = () => setKey((k) => k + 1);
  return <Dot key={key} />;
}
function Dot() {
  return <span data-testid="dot">{usePicksDot() ? "lit" : "out"}</span>;
}

function mount(screenUnderTest: ReactElement) {
  render(<MemoryRouter><ToastProvider><Rail />{screenUnderTest}</ToastProvider></MemoryRouter>);
}

/** A check finishes at `hour` and makes a pick: the next read of the state says so. */
async function aCheckMakesAPick(hour = 9) {
  vi.mocked(api.picksState).mockResolvedValue(picksOn(true, hour));
  const reads = vi.mocked(api.picksState).mock.calls.length;
  act(() => readAgain());
  await waitFor(() => expect(vi.mocked(api.picksState).mock.calls.length).toBeGreaterThan(reads));
  await waitFor(() => expect(screen.getByTestId("dot")).toHaveTextContent("lit"));
}
const offerLine = (count: number) => screen.findByText(msg("picks-fresh-more", { count }), { exact: false });

beforeEach(() => {
  epoch.runVersion = 0;
  vi.spyOn(api, "facets").mockResolvedValue(facetsFixture);
  vi.spyOn(api, "jobs").mockResolvedValue(onePick);
  vi.spyOn(api, "picksState").mockResolvedValue(picksOn(false));
  vi.spyOn(api, "picksOpened").mockResolvedValue(picksOn(false));
});
afterEach(() => vi.restoreAllMocks());

describe("a check that makes a pick while Top picks is open", () => {
  it("offers the new pick without moving the rows, and taking it shows the pick and puts the dot out", async () => {
    const user = userEvent.setup();
    mount(<TopPicksScreen />);
    expect(await screen.findByText("Staff Platform Engineer")).toBeVisible();
    await waitFor(() => expect(api.picksOpened).toHaveBeenCalledOnce());

    vi.mocked(api.jobs).mockResolvedValue(twoPicks);
    await aCheckMakesAPick();

    const offer = (await screen.findByText(msg("picks-fresh-more", { count: 1 }), { exact: false }))
      .closest<HTMLElement>("[role=status]");
    expect(offer).not.toBeNull();
    // The list on screen stays as it was until the person takes the update.
    expect(screen.queryByText("Principal Engineer")).toBeNull();

    await user.click(screen.getByRole("button", { name: msg("radar-board-fresh-show") }));

    expect(await screen.findByText("Principal Engineer")).toBeVisible();
    expect(screen.getByText("Staff Platform Engineer")).toBeVisible();
    expect(screen.queryByRole("button", { name: msg("radar-board-fresh-show") })).toBeNull();
    // Taking the update is opening Top picks: it is recorded, and the dot goes out.
    expect(api.picksOpened).toHaveBeenCalledTimes(2);
    await waitFor(() => expect(screen.getByTestId("dot")).toHaveTextContent("out"));
  });

  it("offers nothing when the list it reads back is the one on screen", async () => {
    mount(<TopPicksScreen />);
    await screen.findByText("Staff Platform Engineer");
    const before = listCalls();

    await aCheckMakesAPick();

    // The list was read again, found unchanged, and nothing is offered.
    await waitFor(() => expect(listCalls()).toBeGreaterThan(before));
    expect(screen.queryByRole("button", { name: msg("radar-board-fresh-show") })).toBeNull();
  });
});

describe("picks that arrive close together", () => {
  it("a second check that makes a pick while the first is still offered widens the offer", async () => {
    const user = userEvent.setup();
    mount(<TopPicksScreen />);
    await screen.findByText("Staff Platform Engineer");

    vi.mocked(api.jobs).mockResolvedValue(twoPicks);
    await aCheckMakesAPick(9);
    await offerLine(1);

    // The dot is already lit; the later check is what says another pick may have come.
    vi.mocked(api.jobs).mockResolvedValue(threePicks);
    await aCheckMakesAPick(10);
    await offerLine(2);

    await user.click(screen.getByRole("button", { name: msg("radar-board-fresh-show") }));
    expect(await screen.findByText("Head of Data Platform")).toBeVisible();
    expect(screen.getByText("Principal Engineer")).toBeVisible();
  });

  it("a pick that arrives before the first list is on screen is offered once it is", async () => {
    const first = deferred<typeof onePick>();
    vi.mocked(api.jobs).mockImplementationOnce(() => first.promise).mockResolvedValue(twoPicks);
    mount(<TopPicksScreen />);
    await waitFor(() => expect(listCalls()).toBe(1));

    await aCheckMakesAPick(9);
    // The first list answers with what was read before the pick was made.
    await act(async () => first.resolve(onePick));
    expect(await screen.findByText("Staff Platform Engineer")).toBeVisible();

    await offerLine(1);
    expect(screen.queryByText("Principal Engineer")).toBeNull();
  });

  it("an older background read that answers last does not replace the newer offer", async () => {
    mount(<TopPicksScreen />);
    await screen.findByText("Staff Platform Engineer");
    const older = deferred<typeof twoPicks>();
    vi.mocked(api.jobs).mockImplementationOnce(() => older.promise).mockResolvedValueOnce(threePicks);

    await aCheckMakesAPick(9);
    await aCheckMakesAPick(10);
    await offerLine(2);

    await act(async () => older.resolve(twoPicks));
    expect(screen.getByText(msg("picks-fresh-more", { count: 2 }), { exact: false })).toBeVisible();
    expect(screen.queryByText(msg("picks-fresh-more", { count: 1 }), { exact: false })).toBeNull();
  });
});

describe("a pick that arrives while the Radar is open", () => {
  it("leaves the Radar's list alone: only the rail's dot says so", async () => {
    mount(<BoardScreen companyParam={[]} onCompanyParamChange={vi.fn()} mode="open" onModeChange={vi.fn()} />);
    await screen.findByText("Staff Platform Engineer");
    const before = listCalls();

    vi.mocked(api.jobs).mockResolvedValue(twoPicks);
    await aCheckMakesAPick();

    expect(listCalls()).toBe(before);
    expect(screen.queryByRole("button", { name: msg("radar-board-fresh-show") })).toBeNull();
  });
});

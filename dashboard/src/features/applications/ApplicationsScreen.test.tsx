import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes, useLocation, useParams } from "react-router-dom";
import type { ReactElement } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { api, type ApplicationCard } from "../../api";
import { ToastProvider } from "../../ui/Toast";
import { applicationCardFixture } from "../../test/fixtures";
import { msg } from "../../test/msg";
import { ApplicationsScreen } from "./ApplicationsScreen";
import { interviewFrom } from "./InterviewDialog";

/* The board's contracts: every move is reachable from a card's menu, lands at
 * once, says so with a way back, and Undo puts back exactly what the move
 * changed. Interviewing asks for its date first. A failed move does not leave
 * the card where the server never put it. */

vi.mock("../../api", async (importOriginal) => ({
  ...(await importOriginal<typeof import("../../api")>()),
  api: {
    applications: vi.fn(),
    calendar: vi.fn(async () => ({ items: [] })),
    setPursuit: vi.fn(),
    setFavorite: vi.fn(),
    addInterview: vi.fn(),
    deleteInterview: vi.fn(),
    jobs: vi.fn(),
  },
}));

const appState = {
  openJob: vi.fn(), refreshStats: vi.fn(), favVersion: 0,
  compareIds: new Set<number>(), viewedIds: new Set<number>(), compareFull: false, compareCap: 3, toggleCompare: vi.fn(),
};
vi.mock("../../context/JobWorkspace", () => ({ useJobWorkspace: () => appState, useJobActions: () => appState }));
vi.mock("../../context/MissionState", () => ({ useMissionActions: () => appState }));

const considering = applicationCardFixture({ job_id: 1, title: "Staff Product Manager, API" });
const applied = applicationCardFixture({
  job_id: 2, pursuit_id: 20, stage: "applied", title: "Principal Engineering Manager", company: "stripe",
});
const rejected = applicationCardFixture({
  job_id: 3, pursuit_id: 30, stage: "rejected", ended_at_stage: "interviewing", title: "Head of Platform",
});

/** On the Board: the pipeline opens on its List, and these are the Board's contracts. */
const withProviders = (ui: ReactElement) => (
  <ToastProvider>
    <MemoryRouter initialEntries={["/pipeline/board"]}>
      <Routes><Route path="/pipeline/:tab" element={ui} /></Routes>
    </MemoryRouter>
  </ToastProvider>
);

const column = (name: string) => screen.getByRole("region", { name });
const tileOf = (card: ApplicationCard) => document.querySelector<HTMLElement>(`.app-tile[data-job-id="${card.job_id}"]`)!;
const openMenu = async (card: ApplicationCard) => {
  await userEvent.click(screen.getByRole("button", { name: msg("applications-card-actions", { title: card.title }) }));
  return screen.findByRole("dialog", { name: msg("applications-menu-label", { title: card.title }) });
};

/* The server's side of the board: a write changes what the next read says,
 * so a re-read after a move shows the move, as the real route does. */
let stored: ApplicationCard[] = [];

beforeEach(() => {
  vi.clearAllMocks();
  localStorage.clear();
  stored = [considering, applied, rejected];
  vi.mocked(api.applications).mockImplementation(async () => ({ applications: stored.map((card) => ({ ...card })) }));
  vi.mocked(api.setPursuit).mockImplementation(async (jobId, update) => {
    stored = stored.map((card) => (card.job_id === jobId && update.stage ? { ...card, stage: update.stage } : card));
    return {
    pursuit: {
      id: jobId * 10, stage: update.stage ?? "saved", priority: 3, notes: null,
      next_action: null, next_action_due: null, updated_at: "2026-11-04T12:00:00Z",
    },
    } as Awaited<ReturnType<typeof api.setPursuit>>;
  });
  vi.mocked(api.setFavorite).mockImplementation(async (id, on) => ({ job_id: id, is_favorite: on }));
  vi.mocked(api.addInterview).mockImplementation(async (_jobId, interview) => ({
    interview: { id: 77, ...interview, outcome: null, notes: null, link: interview.link ?? null, format: interview.format ?? null,
      created_at: "2026-11-04T12:00:00Z", updated_at: "2026-11-04T12:00:00Z" },
  }) as Awaited<ReturnType<typeof api.addInterview>>);
  vi.mocked(api.deleteInterview).mockImplementation(async (_jobId, id) => ({ id, deleted: true }));
});

describe("the board", () => {
  it("puts each card in its stage's column, and an ending in its section with the stage it ended at", async () => {
    render(withProviders(<ApplicationsScreen />));
    await screen.findByText("Staff Product Manager, API");
    expect(within(column("Considering")).getByText("Staff Product Manager, API")).toBeInTheDocument();
    expect(within(column("Applied")).getByText("Principal Engineering Manager")).toBeInTheDocument();
    const closed = column(msg("applications-column-closed"));
    expect(within(closed).getByRole("group", { name: "Rejected" })).toHaveTextContent("Head of Platform");
    expect(within(closed).getByText(msg("applications-card-ended", { ending: "Rejected", stage: "Interviewing" })))
      .toBeInTheDocument();
    expect(within(column("Researching")).getByText(msg("applications-column-empty"))).toBeInTheDocument();
  });

  it("moves a card from its menu at once, and Undo moves it back", async () => {
    render(withProviders(<ApplicationsScreen />));
    await screen.findByText("Staff Product Manager, API");

    const menu = await openMenu(considering);
    await userEvent.click(within(menu).getByRole("button", { name: "Researching" }));

    expect(within(column("Researching")).getByText("Staff Product Manager, API")).toBeInTheDocument();
    expect(within(column("Considering")).queryByText("Staff Product Manager, API")).toBeNull();
    await waitFor(() => expect(api.setPursuit).toHaveBeenCalledWith(1, { stage: "researching" }));

    const toast = await screen.findByText(msg("applications-moved", { title: considering.title, stage: "Researching" }));
    await userEvent.click(within(toast.closest("[role=status], .ui-toast")! as HTMLElement)
      .getByRole("button", { name: msg("applications-move-undo") }));
    await waitFor(() => expect(api.setPursuit).toHaveBeenLastCalledWith(1, { stage: "saved" }));
    expect(api.setPursuit).toHaveBeenCalledTimes(2);
  });

  it("writes nothing when a Networking card is moved to Researching, the column it already shows in", async () => {
    const networking = applicationCardFixture({ job_id: 4, pursuit_id: 40, stage: "networking", title: "Director of Product" });
    stored = [...stored, networking];
    render(withProviders(<ApplicationsScreen />));
    await screen.findByText("Director of Product");

    const menu = await openMenu(networking);
    await userEvent.click(within(menu).getByRole("button", { name: "Researching" }));

    expect(within(column("Researching")).getByText("Director of Product")).toBeInTheDocument();
    expect(api.setPursuit).not.toHaveBeenCalled();
    expect(screen.queryByRole("button", { name: msg("applications-move-undo") })).toBeNull();
  });

  it("re-reads the board when a move fails, and says the move did not happen", async () => {
    render(withProviders(<ApplicationsScreen />));
    await screen.findByText("Principal Engineering Manager");
    vi.mocked(api.setPursuit).mockRejectedValueOnce(new Error("offline"));
    const reads = vi.mocked(api.applications).mock.calls.length;

    await userEvent.click(within(await openMenu(applied)).getByRole("button", { name: "Offer" }));

    expect(await screen.findByText(msg("applications-move-failed", { title: applied.title }))).toBeInTheDocument();
    await waitFor(() => expect(vi.mocked(api.applications).mock.calls.length).toBeGreaterThan(reads));
    expect(within(column("Applied")).getByText("Principal Engineering Manager")).toBeInTheDocument();
  });

  it("offers to leave the pipeline only in Considering", async () => {
    render(withProviders(<ApplicationsScreen />));
    await screen.findByText("Staff Product Manager, API");

    const first = await openMenu(considering);
    expect(within(first).getByRole("button", { name: msg("applications-menu-remove") })).toBeInTheDocument();
    await userEvent.keyboard("{Escape}");

    const second = await openMenu(applied);
    expect(within(second).queryByRole("button", { name: msg("applications-menu-remove") })).toBeNull();
    expect(within(second).getByRole("button", { name: "Withdrawn" })).toBeInTheDocument();
  });
});

describe("moving into Interviewing", () => {
  // The month the form opens on is the clock's: fix the date, nothing else.
  beforeEach(() => {
    vi.useFakeTimers({ toFake: ["Date"] });
    vi.setSystemTime(new Date(2026, 10, 4, 10, 0));
  });
  afterEach(() => vi.useRealTimers());

  it("asks when the interview is first, and Cancel writes nothing", async () => {
    render(withProviders(<ApplicationsScreen />));
    await screen.findByText("Principal Engineering Manager");

    await userEvent.click(within(await openMenu(applied)).getByRole("button", { name: "Interviewing" }));
    const dialog = await screen.findByRole("dialog", { name: msg("applications-interview-title") });
    await userEvent.click(within(dialog).getByRole("button", { name: msg("applications-interview-cancel") }));

    expect(api.setPursuit).not.toHaveBeenCalled();
    expect(within(column("Applied")).getByText("Principal Engineering Manager")).toBeInTheDocument();
  });

  it("moves the card and records the interview, and Undo takes both back", async () => {
    render(withProviders(<ApplicationsScreen />));
    await screen.findByText("Principal Engineering Manager");

    await userEvent.click(within(await openMenu(applied)).getByRole("button", { name: "Interviewing" }));
    const dialog = await screen.findByRole("dialog", { name: msg("applications-interview-title") });
    await userEvent.type(within(dialog).getByLabelText(msg("applications-interview-round")), "Hiring manager call");
    await userEvent.click(within(dialog).getByRole("button", { name: "Thu, Nov 12" }));
    await userEvent.click(within(dialog).getByRole("button", {
      name: msg("applications-interview-submit", { stage: "Interviewing" }),
    }));

    await waitFor(() => expect(api.addInterview).toHaveBeenCalledTimes(1));
    expect(api.setPursuit).toHaveBeenCalledWith(2, { stage: "interviewing" });
    expect(vi.mocked(api.addInterview).mock.calls[0]).toEqual([2, {
      label: "Hiring manager call",
      scheduled_at: new Date(2026, 10, 12).toISOString(),
      all_day: true,
      format: null,
      link: null,
    }]);
    expect(within(column("Interviewing")).getByText("Principal Engineering Manager")).toBeInTheDocument();

    await userEvent.click(await screen.findByRole("button", { name: msg("applications-move-undo") }));
    await waitFor(() => expect(api.deleteInterview).toHaveBeenCalledWith(2, 77));
    expect(api.setPursuit).toHaveBeenLastCalledWith(2, { stage: "applied" });
  });

  it("keeps the move when only its interview fails to save, says which, and Undo still moves it back", async () => {
    render(withProviders(<ApplicationsScreen />));
    await screen.findByText("Principal Engineering Manager");
    vi.mocked(api.addInterview).mockRejectedValueOnce(new Error("offline"));

    await userEvent.click(within(await openMenu(applied)).getByRole("button", { name: "Interviewing" }));
    const dialog = await screen.findByRole("dialog", { name: msg("applications-interview-title") });
    await userEvent.click(within(dialog).getByRole("button", { name: "Thu, Nov 12" }));
    await userEvent.click(within(dialog).getByRole("button", {
      name: msg("applications-interview-submit", { stage: "Interviewing" }),
    }));

    expect(await screen.findByText(msg("applications-move-interview-failed", { title: applied.title }))).toBeInTheDocument();
    expect(screen.getByText(msg("applications-moved", { title: applied.title, stage: "Interviewing" }))).toBeInTheDocument();
    expect(screen.queryByText(msg("applications-move-failed", { title: applied.title }))).toBeNull();
    await waitFor(() => expect(within(column("Interviewing")).getByText("Principal Engineering Manager")).toBeInTheDocument());

    await userEvent.click(screen.getByRole("button", { name: msg("applications-move-undo") }));
    await waitFor(() => expect(api.setPursuit).toHaveBeenLastCalledWith(2, { stage: "applied" }));
    expect(api.deleteInterview).not.toHaveBeenCalled();
  });

  it("sends a timed interview at the reader's own clock time, and a blank round as Interview", () => {
    const sent = interviewFrom({ label: " ", day: "2026-11-12", clock: "14:30", format: "video", link: "" });
    expect(sent).toEqual({
      label: msg("applications-interview-default-label"),
      scheduled_at: new Date(2026, 10, 12, 14, 30).toISOString(),
      all_day: false,
      format: "video",
      link: null,
    });
  });
});

const atRoute = (path: string) => (
  <ToastProvider>
    <MemoryRouter initialEntries={[path]}>
      <Routes><Route path="/pipeline/:tab" element={<ApplicationsScreen />} /></Routes>
    </MemoryRouter>
  </ToastProvider>
);
/** As the app mounts a screen: anew on every path, since its route boundary
 *  is keyed on the path. Whatever a tab must remember has to outlive that. */
function RemountedOnPath() {
  return <ApplicationsScreen key={useLocation().pathname} />;
}
const atRouteRemounting = (path: string) => (
  <ToastProvider>
    <MemoryRouter initialEntries={[path]}>
      <Routes><Route path="/pipeline/:tab" element={<RemountedOnPath />} /></Routes>
    </MemoryRouter>
  </ToastProvider>
);
const columnsButton = () => screen.getByRole("button", { name: /^Columns/ });
const openColumnsMenu = async () => {
  await userEvent.click(columnsButton());
  return screen.findByRole("dialog", { name: msg("applications-columns") });
};
const openFilterMenu = async () => {
  await userEvent.click(screen.getByRole("button", { name: msg("shared-filters") }));
  return screen.findByRole("dialog", { name: msg("applications-filter-menu") });
};

describe("hiding columns", () => {
  it("hides a column from its own menu, leaving no trace on the board, and remembers it on the next visit", async () => {
    const { unmount } = render(withProviders(<ApplicationsScreen />));
    await screen.findByText("Head of Platform");
    const closedName = msg("applications-column-closed");

    await userEvent.click(screen.getByRole("button", { name: msg("applications-column-menu", { column: closedName }) }));
    const menu = await screen.findByRole("dialog", { name: msg("applications-column-menu", { column: closedName }) });
    await userEvent.click(within(menu).getByRole("button", { name: msg("applications-column-hide") }));

    expect(screen.queryByRole("region", { name: closedName })).toBeNull();
    expect(screen.queryByText("Head of Platform")).toBeNull();
    expect(columnsButton()).toHaveAccessibleName(msg("applications-columns-hidden", { count: 1 }));
    unmount();

    render(withProviders(<ApplicationsScreen />));
    await screen.findByText("Staff Product Manager, API");
    expect(screen.queryByRole("region", { name: closedName })).toBeNull();
    const columns = await openColumnsMenu();
    await userEvent.click(within(columns).getByRole("checkbox", { name: new RegExp(`^${closedName}`) }));
    expect(within(column(closedName)).getByText("Head of Platform")).toBeInTheDocument();
    expect(columnsButton()).toHaveAccessibleName(msg("applications-columns"));
  });

  it("keeps the last shown column: its box and its Hide are off", async () => {
    render(withProviders(<ApplicationsScreen />));
    await screen.findByText("Staff Product Manager, API");
    const columns = await openColumnsMenu();
    const boxes = within(columns).getAllByRole("checkbox");
    for (const box of boxes.slice(1)) await userEvent.click(box);

    expect(screen.getAllByRole("region")).toHaveLength(1);
    expect(boxes[0]).toBeChecked();
    expect(boxes[0]).toBeDisabled();
    await userEvent.click(within(columns).getByRole("button", { name: msg("applications-columns-show-all") }));
    expect(screen.getAllByRole("region")).toHaveLength(7);
  });

  it("says so when a move sends a card into a hidden column, and keeps its Undo", async () => {
    localStorage.setItem("roleband.pipeline-hidden-columns", JSON.stringify(["offer"]));
    render(withProviders(<ApplicationsScreen />));
    await screen.findByText("Principal Engineering Manager");

    await userEvent.click(within(await openMenu(applied)).getByRole("button", { name: "Offer" }));

    expect(await screen.findByText(msg("applications-moved-hidden", { title: applied.title, stage: "Offer", column: "Offer" })))
      .toBeInTheDocument();
    expect(screen.queryByText("Principal Engineering Manager")).toBeNull();
    expect(screen.getByRole("button", { name: msg("applications-move-undo") })).toBeInTheDocument();
  });

  it("on the List a move says only where the role went: the hidden columns are the Board's", async () => {
    localStorage.setItem("roleband.pipeline-hidden-columns", JSON.stringify(["researching"]));
    vi.mocked(api.jobs).mockResolvedValue({ items: [], total: 0, limit: 500, offset: 0 } as never);
    render(atRoute("/pipeline/list"));
    await screen.findByText(considering.title);

    await userEvent.click(screen.getByRole("button", { name: msg("applications-card-actions", { title: considering.title }) }));
    const menu = await screen.findByRole("dialog", { name: msg("applications-menu-label", { title: considering.title }) });
    await userEvent.click(within(menu).getByRole("button", { name: "Researching" }));

    expect(await screen.findByText(msg("applications-moved", { title: considering.title, stage: "Researching" }))).toBeInTheDocument();
    expect(screen.queryByText(msg("applications-moved-hidden", { title: considering.title, stage: "Researching", column: "Researching" }))).toBeNull();
  });
});

describe("filtering", () => {
  const due = applicationCardFixture({
    job_id: 4, pursuit_id: 40, stage: "applied", title: "Director of Product", company: "notion",
    next_action: "Send the case study", next_action_due: new Date(Date.now() - 2 * 86_400_000).toISOString(),
  });
  beforeEach(() => {
    stored = [considering, applied, due, rejected];
  });

  it("shows only the matches, counts each column as matches of all, and says a column emptied by it has no matches", async () => {
    render(atRoute("/pipeline/board"));
    await screen.findByText("Director of Product");

    const menu = await openFilterMenu();
    await userEvent.click(within(menu).getByRole("checkbox", { name: new RegExp(`^${msg("applications-quick-overdue")}`) }));
    await userEvent.keyboard("{Escape}");

    expect(screen.queryByText("Principal Engineering Manager")).toBeNull();
    expect(within(column("Applied")).getByText("Director of Product")).toBeInTheDocument();
    expect(within(column("Applied")).getByText(msg("applications-column-count-of", { count: 1, total: 2 }))).toBeInTheDocument();
    expect(within(column("Considering")).getByText(msg("applications-column-no-matches"))).toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: msg("applications-filter-remove", { filter: msg("applications-quick-overdue") }) }));
    expect(screen.getByText("Principal Engineering Manager")).toBeInTheDocument();
    expect(screen.queryByText(msg("applications-column-no-matches"))).toBeNull();
  });

  it("highlights instead: every card stays, the matches marked and the rest not", async () => {
    render(atRoute("/pipeline/board?only=overdue"));
    await screen.findByText("Director of Product");
    expect(screen.queryByText("Principal Engineering Manager")).toBeNull();

    await userEvent.click(screen.getByRole("button", { name: msg("applications-filter-highlight-instead") }));

    expect(tileOf(due)).toHaveAttribute("data-match", "true");
    expect(tileOf(applied)).toHaveAttribute("data-match", "false");
    expect(tileOf(considering)).toHaveAttribute("data-match", "false");
    await userEvent.click(screen.getByRole("button", { name: msg("applications-mode-only") }));
    expect(screen.queryByText("Principal Engineering Manager")).toBeNull();
  });

  it("searches the company and the title, and Reset all clears it", async () => {
    render(atRoute("/pipeline/board"));
    await screen.findByText("Director of Product");

    await userEvent.type(screen.getByRole("searchbox", { name: msg("applications-search-label") }), "stripe");
    expect(screen.getByText("Principal Engineering Manager")).toBeInTheDocument();
    expect(screen.queryByText("Director of Product")).toBeNull();

    await userEvent.click(screen.getByRole("button", { name: msg("applications-filter-reset") }));
    expect(screen.getByText("Director of Product")).toBeInTheDocument();
    expect(screen.getByRole("searchbox", { name: msg("applications-search-label") })).toHaveValue("");
  });

  it("keeps each view's filter to itself: the board's is not on Up next, and each tab finds its own again", async () => {
    render(atRouteRemounting("/pipeline/board"));
    await screen.findByText("Director of Product");
    const search = () => screen.getByRole("searchbox", { name: msg("applications-search-label") });

    await userEvent.type(search(), "stripe");
    expect(screen.queryByText("Director of Product")).toBeNull();

    // Up next holds Notion's overdue step, which the board's search hides.
    await userEvent.click(screen.getByRole("tab", { name: msg("shell-tab-pipeline-up-next") }));
    expect(await screen.findByText(msg("applications-upnext-step", { step: "Send the case study" }))).toBeInTheDocument();
    expect(search()).toHaveValue("");
    expect(screen.queryByRole("button", { name: msg("applications-filter-reset") })).toBeNull();
    await userEvent.type(search(), "zzz");
    expect(screen.getByText(msg("applications-upnext-no-matches"))).toBeInTheDocument();

    await userEvent.click(screen.getByRole("tab", { name: msg("shell-tab-pipeline-board") }));
    expect(search()).toHaveValue("stripe");
    expect(await screen.findByText("Principal Engineering Manager")).toBeInTheDocument();
    expect(screen.queryByText("Director of Product")).toBeNull();

    await userEvent.click(screen.getByRole("tab", { name: msg("shell-tab-pipeline-up-next") }));
    expect(search()).toHaveValue("zzz");
    expect(screen.getByText(msg("applications-upnext-no-matches"))).toBeInTheDocument();
  });

  it("opens the board with Needs a next step from the summary, from Up next too, keeping the board's own search", async () => {
    render(atRouteRemounting("/pipeline/board"));
    await screen.findByText("Director of Product");
    const search = () => screen.getByRole("searchbox", { name: msg("applications-search-label") });
    await userEvent.type(search(), "stripe");
    await userEvent.click(screen.getByRole("tab", { name: msg("shell-tab-pipeline-up-next") }));
    await userEvent.type(search(), "notion");

    await userEvent.click(screen.getByRole("button", { name: msg("applications-board-need-next", { count: 1 }) }));

    expect(screen.getByRole("tab", { name: msg("shell-tab-pipeline-board") })).toHaveAttribute("aria-selected", "true");
    expect(search()).toHaveValue("stripe");
    expect(screen.getByRole("button", { name: msg("applications-filter-remove", { filter: msg("applications-quick-needs-next") }) }))
      .toBeInTheDocument();
    expect(await screen.findByText("Principal Engineering Manager")).toBeInTheDocument();
    // The board shows the filter, so the summary's count is no longer a way to it.
    expect(screen.queryByRole("button", { name: msg("applications-board-need-next", { count: 1 }) })).toBeNull();

    await userEvent.click(screen.getByRole("tab", { name: msg("shell-tab-pipeline-up-next") }));
    expect(search()).toHaveValue("notion");
    expect(screen.queryByRole("button", { name: /^Columns/ })).toBeNull();
  });

  it("offers each view only the filters that can match there, and drops one the address carries that the view does not", async () => {
    function Address() {
      return <output data-testid="address">{useLocation().search}</output>;
    }
    vi.mocked(api.jobs).mockResolvedValue({ items: [], total: 0, limit: 500, offset: 0 } as never);
    render(
      <ToastProvider>
        <MemoryRouter initialEntries={["/pipeline/list?only=quiet,high_priority"]}>
          <Routes><Route path="/pipeline/:tab" element={<><ApplicationsScreen /><Address /></>} /></Routes>
        </MemoryRouter>
      </ToastProvider>,
    );
    const offered = async () => {
      // The button counts the filters on, so its name starts with Filters.
      await userEvent.click(screen.getByRole("button", { name: new RegExp(`^${msg("shared-filters")}`) }));
      const menu = await screen.findByRole("dialog", { name: msg("applications-filter-menu") });
      const names = within(menu).getAllByRole("checkbox").map((box) => box.getAttribute("aria-label") ?? box.textContent ?? "");
      await userEvent.keyboard("{Escape}");
      return names;
    };
    const has = (names: string[], label: string) => names.some((name) => name.startsWith(label));
    const highPriority = msg("applications-quick-high-priority");
    const quiet = msg("applications-quick-quiet");
    const needsNext = msg("applications-quick-needs-next");
    const chip = (label: string) => screen.queryByRole("button", { name: msg("applications-filter-remove", { filter: label }) });

    // The List: roles in Considering never go quiet and are owed no next step yet.
    await screen.findByRole("tab", { name: msg("shell-tab-pipeline-list"), selected: true });
    expect(chip(highPriority)).toBeInTheDocument();
    expect(chip(quiet)).toBeNull();
    const list = await offered();
    for (const label of [msg("applications-quick-overdue"), msg("applications-quick-due-week"), highPriority, msg("applications-card-posting-closed")]) {
      expect(has(list, label), label).toBe(true);
    }
    expect(has(list, quiet)).toBe(false);
    expect(has(list, needsNext)).toBe(false);
    expect(list).toHaveLength(4);

    // The next change writes only what the List holds.
    await userEvent.click(chip(highPriority)!);
    expect(screen.getByTestId("address").textContent).toBe("");

    // Up next: every row has a date, so none needs a next step.
    await userEvent.click(screen.getByRole("tab", { name: msg("shell-tab-pipeline-up-next") }));
    const upNext = await offered();
    expect(has(upNext, needsNext)).toBe(false);
    expect(has(upNext, quiet)).toBe(true);
    expect(upNext).toHaveLength(5);

    await userEvent.click(screen.getByRole("tab", { name: msg("shell-tab-pipeline-board") }));
    expect(await offered()).toHaveLength(6);
  });

  it("draws no count in the toolbar, filtering or not: the views show what they hold", async () => {
    render(atRoute("/pipeline/board?only=overdue"));
    await screen.findByText("Director of Product");
    const toolbar = document.querySelector<HTMLElement>(".app-pipeline-toolbar")!;
    expect(toolbar.textContent).not.toMatch(/\d+ of \d+|\bapplications?\b|things? due/);
    expect(within(toolbar).getByRole("button", { name: msg("applications-filter-reset") })).toBeInTheDocument();
  });
});

describe("the cards and the tabs", () => {
  it("links each card's title to its application's page", async () => {
    render(withProviders(<ApplicationsScreen />));
    const title = await screen.findByText("Principal Engineering Manager");
    expect(title.closest("a")).toHaveAttribute("href", "/pipeline/2");
  });

  it("lists what is due by day under Up next, overdue first, each row opening its application", async () => {
    const now = Date.now();
    stored = [
      { ...considering, next_action: "Ask for an intro", next_action_due: new Date(now - 3 * 86_400_000).toISOString() },
      { ...applied, next_interview: {
        id: 5, label: "Hiring manager call", scheduled_at: new Date(now + 7 * 86_400_000).toISOString(), all_day: false, format: "video",
      } },
      rejected,
    ];
    render(
      <ToastProvider>
        <MemoryRouter initialEntries={["/pipeline/up-next"]}>
          <Routes><Route path="/pipeline/:tab" element={<ApplicationsScreen />} /></Routes>
        </MemoryRouter>
      </ToastProvider>,
    );
    expect(await screen.findByRole("tab", { name: msg("shell-tab-pipeline-up-next") })).toHaveAttribute("aria-selected", "true");
    const days = await screen.findAllByRole("region");
    expect(days[0]).toHaveAccessibleName(msg("applications-upnext-overdue"));
    expect(within(days[0]).getByText(msg("applications-upnext-step", { step: "Ask for an intro" }))).toBeInTheDocument();
    expect(within(days[1]).getByText(msg("applications-upnext-interview", { label: "Hiring manager call" }))).toBeInTheDocument();
    expect(within(days[1]).getByRole("link")).toHaveAttribute("href", "/pipeline/2");
    expect(screen.queryByText("Head of Platform")).toBeNull();
  });

  it("brings a day picked in the month into view in Up next and marks its rows; an arrow moves the mark without scrolling", async () => {
    const today = new Date();
    const late = new Date(today.getFullYear(), today.getMonth(), today.getDate(), 23, 58);
    stored = [
      { ...considering, next_action: "Ask for an intro", next_action_due: new Date(Date.now() - 3 * 86_400_000).toISOString() },
      { ...applied, next_interview: { id: 5, label: "Hiring manager call", scheduled_at: late.toISOString(), all_day: false, format: "video" } },
    ];
    const scrolled: Element[] = [];
    Element.prototype.scrollIntoView = vi.fn(function (this: Element) { scrolled.push(this); });
    render(
      <ToastProvider>
        <MemoryRouter initialEntries={["/pipeline/up-next"]}>
          <Routes><Route path="/pipeline/:tab" element={<ApplicationsScreen />} /></Routes>
        </MemoryRouter>
      </ToastProvider>,
    );
    const row = (text: string) => screen.getByText(text).closest("li")!;
    await screen.findByText(msg("applications-upnext-interview", { label: "Hiring manager call" }));
    const interview = row(msg("applications-upnext-interview", { label: "Hiring manager call" }));
    const overdue = row(msg("applications-upnext-step", { step: "Ask for an intro" }));
    // Nothing is marked until a day is picked.
    expect(interview).not.toHaveAttribute("data-picked");

    const key = `${today.getFullYear()}-${String(today.getMonth() + 1).padStart(2, "0")}-${String(today.getDate()).padStart(2, "0")}`;
    const cell = document.querySelector<HTMLElement>(`[data-day="${key}"]`)!;
    await userEvent.click(cell);

    expect(interview).toHaveAttribute("data-picked");
    expect(overdue).not.toHaveAttribute("data-picked");
    expect(scrolled).toEqual([interview.closest("section")]);

    // The arrow walks to tomorrow: today's row is no longer marked, and nothing scrolls.
    await userEvent.keyboard("{ArrowRight}");
    await waitFor(() => expect(interview).not.toHaveAttribute("data-picked"));
    expect(scrolled).toHaveLength(1);
  });
});

/* jsdom lays nothing out, so the board's geometry is drawn here: a column
 * every 264px from the left, 252px wide, and a split column's sections
 * stacked 200px apart from y 40. */
const COLUMN_ORDER = ["saved", "researching", "applied", "interviewing", "offer", "decided", "closed"];
const box = (x: number, y: number, width: number, height: number) =>
  ({ x, y, width, height, left: x, top: y, right: x + width, bottom: y + height, toJSON: () => ({}) }) as DOMRect;

function layOut() {
  vi.spyOn(Element.prototype, "getBoundingClientRect").mockImplementation(function (this: Element) {
    if (this.classList.contains("app-board-scroll")) return box(0, 0, 2400, 900);
    const columnElement = this.closest<HTMLElement>("[data-drop-column]");
    if (!columnElement) return box(0, 0, 0, 0);
    const left = COLUMN_ORDER.indexOf(columnElement.dataset.dropColumn!) * 264;
    if (this === columnElement) return box(left, 0, 252, 900);
    const sections = [...columnElement.querySelectorAll("[data-drop-stage]")];
    const index = sections.indexOf(this);
    return index >= 0 ? box(left, 40 + index * 200, 252, 180) : box(left, 40, 252, 100);
  });
}

/** The middle of a column, or of one of its sections. */
const over = (columnId: string, section = 0) => ({
  clientX: COLUMN_ORDER.indexOf(columnId) * 264 + 126,
  clientY: 40 + section * 200 + 90,
});
const nextFrame = () => act(() => new Promise<void>((resolve) => requestAnimationFrame(() => resolve())));

/** Press a card, carry it to `to`, and let a frame draw it there. */
async function carry(card: ApplicationCard, to: { clientX: number; clientY: number }) {
  const tile = tileOf(card);
  fireEvent.pointerDown(tile, { pointerId: 1, button: 0, clientX: 900, clientY: 100 });
  fireEvent.pointerMove(tile, { pointerId: 1, ...to });
  await nextFrame();
  return tile;
}

/** The board, or a stand-in for the application page a press opens. */
function BoardOrOpened() {
  return /^\d+$/.test(useParams().tab ?? "") ? <p>Opened the application</p> : <ApplicationsScreen />;
}
const renderRouted = () => render(
  <ToastProvider>
    <MemoryRouter initialEntries={["/pipeline/board"]}>
      <Routes>
        <Route path="/pipeline/:tab" element={<BoardOrOpened />} />
      </Routes>
    </MemoryRouter>
  </ToastProvider>,
);

describe("dragging a card", () => {
  const capture = vi.fn();
  beforeEach(() => {
    layOut();
    capture.mockClear();
    Element.prototype.setPointerCapture = capture;
  });
  afterEach(() => {
    vi.restoreAllMocks();
    delete (Element.prototype as Partial<Element>).setPointerCapture;
  });

  it("marks the column a drop would land in, and moves the card there at once, with Undo", async () => {
    renderRouted();
    await screen.findByText(applied.title);
    const tile = await carry(applied, over("offer"));
    expect(tile).toHaveAttribute("data-dragging");
    expect(column("Offer")).toHaveAttribute("data-drop-target");
    expect(column("Applied")).not.toHaveAttribute("data-drop-target");

    fireEvent.pointerUp(tile, { pointerId: 1, ...over("offer") });
    expect(within(column("Offer")).getByText(applied.title)).toBeInTheDocument();
    expect(column("Offer")).not.toHaveAttribute("data-drop-target");
    await waitFor(() => expect(api.setPursuit).toHaveBeenCalledWith(2, { stage: "offer" }));
    expect(await screen.findByRole("button", { name: msg("applications-move-undo") })).toBeInTheDocument();
  });

  it("does not open the application the drop ends on, while a press that barely moves still opens it", async () => {
    renderRouted();
    await screen.findByText(applied.title);
    const tile = await carry(applied, over("offer"));
    expect(capture).toHaveBeenCalledTimes(1);
    fireEvent.pointerUp(tile, { pointerId: 1, ...over("offer") });
    fireEvent.click(within(column("Offer")).getByText(applied.title));
    expect(screen.queryByText("Opened the application")).toBeNull();

    capture.mockClear();
    const link = within(column("Offer")).getByRole("link", { name: applied.title });
    fireEvent.pointerDown(link, { pointerId: 2, button: 0, clientX: 1446, clientY: 100 });
    fireEvent.pointerMove(link, { pointerId: 2, clientX: 1448, clientY: 101 });
    fireEvent.pointerUp(link, { pointerId: 2, clientX: 1448, clientY: 101 });
    // Captured on the press, the click would go to the card and not its link.
    expect(capture).not.toHaveBeenCalled();
    fireEvent.click(link);
    expect(await screen.findByText("Opened the application")).toBeInTheDocument();
  });

  it("asks for the interview's date when dropped on Interviewing, and Cancel leaves the card where it was", async () => {
    renderRouted();
    await screen.findByText(applied.title);
    const tile = await carry(applied, over("interviewing"));
    fireEvent.pointerUp(tile, { pointerId: 1, ...over("interviewing") });

    const dialog = await screen.findByRole("dialog", { name: msg("applications-interview-title") });
    expect(api.setPursuit).not.toHaveBeenCalled();
    await userEvent.click(within(dialog).getByRole("button", { name: msg("applications-interview-cancel") }));
    expect(api.setPursuit).not.toHaveBeenCalled();
    expect(within(column("Applied")).getByText(applied.title)).toBeInTheDocument();
  });

  it("lands in the section under the pointer in a split column", async () => {
    renderRouted();
    await screen.findByText(applied.title);
    const tile = await carry(applied, over("decided", 2));
    const decided = column(msg("applications-column-decided"));
    expect(within(decided).getByRole("group", { name: "Withdrawn" })).toHaveAttribute("data-drop-target");
    expect(decided).not.toHaveAttribute("data-drop-target");

    fireEvent.pointerUp(tile, { pointerId: 1, ...over("decided", 2) });
    await waitFor(() => expect(api.setPursuit).toHaveBeenCalledWith(2, { stage: "withdrawn" }));
  });

  it("changes nothing dropped back on its own column, or given up with Escape", async () => {
    renderRouted();
    await screen.findByText(applied.title);
    let tile = await carry(applied, over("applied"));
    expect(column("Applied")).not.toHaveAttribute("data-drop-target");
    fireEvent.pointerUp(tile, { pointerId: 1, ...over("applied") });

    tile = await carry(applied, over("offer"));
    fireEvent.keyDown(window, { key: "Escape" });
    expect(tile).not.toHaveAttribute("data-dragging");
    expect(column("Offer")).not.toHaveAttribute("data-drop-target");
    fireEvent.pointerUp(tile, { pointerId: 1, ...over("offer") });
    fireEvent.click(within(tile).getByRole("link"));

    expect(api.setPursuit).not.toHaveBeenCalled();
    expect(within(column("Applied")).getByText(applied.title)).toBeInTheDocument();
    expect(screen.queryByText("Opened the application")).toBeNull();
  });

  it("leaves the card's menu button to its own press", async () => {
    renderRouted();
    await screen.findByText(applied.title);
    const button = screen.getByRole("button", { name: msg("applications-card-actions", { title: applied.title }) });
    fireEvent.pointerDown(button, { pointerId: 1, button: 0, clientX: 900, clientY: 100 });
    fireEvent.pointerMove(button, { pointerId: 1, ...over("offer") });
    await nextFrame();
    expect(tileOf(applied)).not.toHaveAttribute("data-dragging");
    expect(column("Offer")).not.toHaveAttribute("data-drop-target");
    fireEvent.pointerUp(button, { pointerId: 1, ...over("offer") });
    expect(within(column("Applied")).getByText(applied.title)).toBeInTheDocument();
    expect(api.setPursuit).not.toHaveBeenCalled();
  });
});

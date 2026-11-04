import { createEvent, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes, useLocation } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { api, type ApplicationCard, type Job, type JobList } from "../../api";
import { ToastProvider } from "../../ui/Toast";
import { applicationCardFixture, jobFixture } from "../../test/fixtures";
import { msg } from "../../test/msg";
import { ApplicationsScreen } from "./ApplicationsScreen";

/* The List's contracts: one row per application, in the board's stage order,
 * each with its posting's facts beside it; a row's stage holds the same moves
 * a card's menu does; its last cell holds Radar's row actions, which take a
 * role in Considering off the pipeline and say why a role past it stays; a
 * header sorts and the sort lives in the address; a header moves, by its
 * menu or a drag, and hides, and the layout stays; its filter is its own;
 * and a postings read that fails leaves the applications on screen. */

vi.mock("../../api", async (importOriginal) => ({
  ...(await importOriginal<typeof import("../../api")>()),
  api: {
    applications: vi.fn(),
    jobs: vi.fn(),
    setPursuit: vi.fn(),
    setFavorite: vi.fn(),
    dismissJob: vi.fn(),
    undismissJob: vi.fn(),
    addInterview: vi.fn(),
    deleteInterview: vi.fn(),
  },
}));

const appState = {
  openJob: vi.fn(),
  refreshStats: vi.fn(),
  favVersion: 0,
  viewedIds: new Set<number>(),
  compareIds: new Set<number>(),
  compareFull: false,
  compareCap: undefined,
  compareSyncFailed: false,
  toggleCompare: vi.fn(),
  clearCompare: vi.fn(),
  setCompare: vi.fn(),
  dropCompare: vi.fn(),
  openCompare: vi.fn(),
};
vi.mock("../../context/JobWorkspace", () => ({ useJobWorkspace: () => appState, useJobActions: () => appState }));
vi.mock("../../context/MissionState", () => ({ useMissionActions: () => appState }));

const considering = applicationCardFixture({ job_id: 1, title: "Staff Product Manager, API", company: "openai" });
const applied = applicationCardFixture({
  job_id: 2, pursuit_id: 20, stage: "applied", title: "Principal Engineering Manager", company: "stripe",
});
const rejected = applicationCardFixture({
  job_id: 3, pursuit_id: 30, stage: "rejected", ended_at_stage: "interviewing", title: "Head of Platform",
  company: "notion", posting_status: "closed",
});

const posting = (over: Partial<Job> & { id: number }): Job => ({ ...jobFixture, ...over });
const postings = [
  posting({
    id: 1, locations: ["San Francisco, CA", "New York, NY"], level_band: "staff", level_basis: "title",
    posted_base: { min: 240_000, max: 300_000, period: "year", currency: "USD" }, listed_days: 4,
  }),
  posting({ id: 2, locations: ["Dublin, Ireland"], level_band: "mid", level_basis: "none", posted_base: null, comp_base_median: null }),
  posting({ id: 3, status: "closed", locations: ["Remote"], posted_base: null, comp_base_median: null }),
];
const page = (items: Job[]): JobList => ({ items, total: items.length, limit: 500, offset: 0 }) as JobList;

let stored: ApplicationCard[] = [];

/** Where the List lives, remounted on each path as the app mounts a screen. */
function Screen() {
  return <ApplicationsScreen key={useLocation().pathname} />;
}
function Address() {
  const { search } = useLocation();
  return <output data-testid="address">{search}</output>;
}
const at = (path = "/pipeline/list") => (
  <ToastProvider>
    <MemoryRouter initialEntries={[path]}>
      <Routes><Route path="/pipeline/:tab" element={<><Screen /><Address /></>} /></Routes>
    </MemoryRouter>
  </ToastProvider>
);

const table = () => screen.getByRole("table");
const rowOf = (card: ApplicationCard) => document.querySelector<HTMLElement>(`tr[data-job-id="${card.job_id}"]`)!;
const rowOrder = () => [...table().querySelectorAll<HTMLElement>("tbody tr")].map((tr) => Number(tr.dataset.jobId));
const headers = () => [...table().querySelectorAll<HTMLElement>("thead th[data-col]")].map((th) => th.dataset.col);
const header = (column: string) => table().querySelector<HTMLElement>(`thead th[data-col="${column}"]`)!;
const sortButton = (column: string) => header(column).querySelector<HTMLElement>("button.col-sort")!;
const cellOf = (card: ApplicationCard, column: string) => rowOf(card).querySelector<HTMLElement>(`[data-col="${column}"]`);
const stageButton = (card: ApplicationCard, stage: string) =>
  screen.getByRole("button", { name: msg("applications-list-stage", { stage, title: card.title }) });
const openColumns = async () => {
  await userEvent.click(screen.getByRole("button", { name: /^Columns/ }));
  return screen.findByRole("dialog", { name: msg("applications-columns") });
};

beforeEach(() => {
  vi.clearAllMocks();
  localStorage.clear();
  stored = [rejected, applied, considering];
  vi.mocked(api.applications).mockImplementation(async () => ({ applications: stored.map((card) => ({ ...card })) }));
  vi.mocked(api.jobs).mockResolvedValue(page(postings));
  vi.mocked(api.setPursuit).mockImplementation(async (jobId, update) => {
    stored = stored.map((card) => (card.job_id === jobId && update.stage ? { ...card, stage: update.stage } : card));
    return {
      pursuit: {
        id: jobId * 10, stage: update.stage ?? "saved", priority: 3, notes: null,
        next_action: null, next_action_due: null, updated_at: "2026-11-04T12:00:00Z",
      },
    } as Awaited<ReturnType<typeof api.setPursuit>>;
  });
  vi.mocked(api.setFavorite).mockImplementation(async (id, on) => {
    if (!on) stored = stored.filter((card) => card.job_id !== id);
    return { job_id: id, is_favorite: on };
  });
  vi.mocked(api.dismissJob).mockImplementation(async (id) => ({ job_id: id, is_dismissed: true }) as Awaited<ReturnType<typeof api.dismissJob>>);
  vi.mocked(api.undismissJob).mockImplementation(async (id) => ({ job_id: id, is_dismissed: false }));
});

describe("the List's rows", () => {
  it("lists every application in the board's stage order, each with its posting's facts", async () => {
    render(at());
    await waitFor(() => expect(cellOf(considering, "pay")?.textContent).toMatch(/240/));

    expect(rowOrder()).toEqual([1, 2, 3]);
    expect(within(rowOf(considering)).getByRole("rowheader")).toHaveTextContent(/OpenAI/);
    expect(within(rowOf(considering)).getByRole("link", { name: considering.title }))
      .toHaveAttribute("href", "/pipeline/1");
    expect(cellOf(considering, "location")).toHaveTextContent("San Francisco, CA +1");
    expect(cellOf(considering, "level")).toHaveTextContent("Staff");
    // A level the posting does not state is not shown as one.
    expect(cellOf(applied, "level")).toHaveTextContent("");
    expect(cellOf(applied, "pay")).toHaveTextContent("");
    expect(within(cellOf(rejected, "posting")!).getByText(msg("applications-card-posting-closed"))).toBeInTheDocument();
  });

  it("asks for the postings by id, every status, in one read", async () => {
    render(at());
    await screen.findByText("Head of Platform");
    await waitFor(() => expect(api.jobs).toHaveBeenCalled());
    expect(vi.mocked(api.jobs).mock.calls[0][0]).toMatchObject({ ids: [1, 2, 3], status: "", limit: 500 });
  });

  it("still lists the applications when the postings read fails, without their facts", async () => {
    vi.mocked(api.jobs).mockRejectedValue(new Error("offline"));
    render(at());
    await screen.findByText("Head of Platform");
    await waitFor(() => expect(api.jobs).toHaveBeenCalled());

    expect(rowOrder()).toEqual([1, 2, 3]);
    expect(cellOf(considering, "pay")).toHaveTextContent("");
    expect(cellOf(considering, "location")).toHaveTextContent("");
    // The application's own facts do not wait on the posting.
    expect(within(cellOf(rejected, "posting")!).getByText(msg("applications-card-posting-closed"))).toBeInTheDocument();
  });

  it("asks for no postings, and says how to start, when nothing is in the pipeline", async () => {
    stored = [];
    render(at());
    expect(await screen.findByText(msg("applications-list-empty"))).toBeInTheDocument();
    expect(api.jobs).not.toHaveBeenCalled();
    expect(screen.queryByRole("table")).toBeNull();
  });
});

describe("moving from a row", () => {
  it("opens every move from the row's stage, and a move lands at once", async () => {
    render(at());
    await screen.findByText("Principal Engineering Manager");

    await userEvent.click(stageButton(applied, "Applied"));
    const menu = await screen.findByRole("dialog", { name: msg("applications-menu-label", { title: applied.title }) });
    // Only Considering offers to leave the pipeline.
    expect(within(menu).queryByRole("button", { name: msg("applications-menu-remove") })).toBeNull();
    await userEvent.click(within(menu).getByRole("button", { name: "Offer" }));

    expect(stageButton(applied, "Offer")).toBeInTheDocument();
    await waitFor(() => expect(api.setPursuit).toHaveBeenCalledWith(2, { stage: "offer" }));
  });

  it("asks for the interview's date before moving into Interviewing, and Cancel writes nothing", async () => {
    render(at());
    await screen.findByText("Principal Engineering Manager");

    await userEvent.click(stageButton(applied, "Applied"));
    const menu = await screen.findByRole("dialog", { name: msg("applications-menu-label", { title: applied.title }) });
    await userEvent.click(within(menu).getByRole("button", { name: "Interviewing" }));
    const ask = await screen.findByRole("dialog", { name: msg("applications-interview-title") });
    await userEvent.click(within(ask).getByRole("button", { name: msg("applications-interview-cancel") }));

    expect(api.setPursuit).not.toHaveBeenCalled();
    expect(stageButton(applied, "Applied")).toBeInTheDocument();
  });

  it("removes a starred role in Considering from the pipeline", async () => {
    render(at());
    await screen.findByText("Staff Product Manager, API");

    await userEvent.click(stageButton(considering, "Considering"));
    const menu = await screen.findByRole("dialog", { name: msg("applications-menu-label", { title: considering.title }) });
    await userEvent.click(within(menu).getByRole("button", { name: msg("applications-menu-remove") }));

    await waitFor(() => expect(api.setFavorite).toHaveBeenCalledWith(1, false));
  });
});

describe("sorting the List", () => {
  it("sorts by a header, marks it, keeps the sort in the address, and turns it round on a second press", async () => {
    render(at());
    await waitFor(() => expect(cellOf(considering, "pay")?.textContent).toMatch(/240/));
    const role = header("role");

    const sortBy = () => sortButton("role");
    await userEvent.click(sortBy());
    expect(role).toHaveAttribute("aria-sort", "ascending");
    expect(screen.getByTestId("address")).toHaveTextContent("sort=role&order=asc");
    // Notion, OpenAI, Stripe: by the company's name.
    expect(rowOrder()).toEqual([3, 1, 2]);

    await userEvent.click(sortBy());
    expect(role).toHaveAttribute("aria-sort", "descending");
    expect(rowOrder()).toEqual([2, 1, 3]);
    expect(header("stage")).not.toHaveAttribute("aria-sort");
  });

  it("opens on the sort the address names", async () => {
    render(at("/pipeline/list?sort=pay&order=desc"));
    await waitFor(() => expect(cellOf(considering, "pay")?.textContent).toMatch(/240/));
    expect(header("pay")).toHaveAttribute("aria-sort", "descending");
    expect(rowOrder()[0]).toBe(1);
  });
});

describe("the List's columns", () => {
  const menuOf = async (name: string) => {
    await userEvent.click(screen.getByRole("button", { name: msg("applications-column-menu", { column: name }) }));
    return screen.findByRole("dialog", { name: msg("applications-column-menu", { column: name }) });
  };

  it("hides priority, days in stage and last activity at first, and remembers what a reader hides", async () => {
    const { unmount } = render(at());
    await screen.findByText("Head of Platform");
    expect(headers()).toEqual(["role", "stage", "pay", "location", "level", "next", "posting"]);

    const columns = await openColumns();
    await userEvent.click(within(columns).getByRole("checkbox", { name: msg("jobs-head-location") }));
    await userEvent.click(within(columns).getByRole("checkbox", { name: msg("applications-fact-priority") }));
    expect(headers()).not.toContain("location");
    expect(cellOf(considering, "location")).toBeNull();
    expect(headers()).toContain("priority");
    unmount();

    render(at());
    await screen.findByText("Head of Platform");
    expect(headers()).not.toContain("location");
    expect(headers()).toContain("priority");
  });

  it("moves a column from its header's menu, over the hidden ones, and keeps the order on the next visit", async () => {
    const { unmount } = render(at());
    await screen.findByText("Head of Platform");

    let menu = await menuOf(msg("jobs-head-pay"));
    await userEvent.click(within(menu).getByRole("button", { name: msg("applications-list-column-left") }));
    menu = await menuOf(msg("jobs-head-pay"));
    await userEvent.click(within(menu).getByRole("button", { name: msg("applications-list-column-left") }));
    expect(headers().slice(0, 3)).toEqual(["pay", "role", "stage"]);
    // The row's cells follow their headers.
    expect([...rowOf(considering).querySelectorAll<HTMLElement>("[data-col]")].map((cell) => cell.dataset.col).slice(0, 3))
      .toEqual(["pay", "role", "stage"]);
    menu = await menuOf(msg("jobs-head-pay"));
    expect(within(menu).getByRole("button", { name: msg("applications-list-column-left") })).toBeDisabled();
    await userEvent.keyboard("{Escape}");

    // Posting is the last shown; Right steps past nothing it could land beside.
    menu = await menuOf(msg("applications-facts-posting"));
    expect(within(menu).getByRole("button", { name: msg("applications-list-column-right") })).toBeDisabled();
    await userEvent.click(within(menu).getByRole("button", { name: msg("applications-column-hide") }));
    expect(headers()).not.toContain("posting");
    unmount();

    render(at());
    await screen.findByText("Head of Platform");
    expect(headers()).toEqual(["pay", "role", "stage", "location", "level", "next"]);
  });

  it("never offers to hide the role, which names the row", async () => {
    render(at());
    await screen.findByText("Head of Platform");
    const menu = await menuOf(msg("jobs-head-role"));
    expect(within(menu).queryByRole("button", { name: msg("applications-column-hide") })).toBeNull();
    expect(within(await openColumns()).queryByRole("checkbox", { name: msg("jobs-head-role") })).toBeNull();
  });

  it("moves a column where its header is dropped: before the header it lands on, or after", async () => {
    render(at());
    await screen.findByText("Head of Platform");
    const th = (column: string) => table().querySelector<HTMLElement>(`thead th[data-col="${column}"]`)!;
    const box = (left: number) => ({ left, right: left + 100, width: 100, top: 0, bottom: 30, height: 30, x: left, y: 0, toJSON: () => ({}) });
    vi.spyOn(th("role"), "getBoundingClientRect").mockReturnValue(box(0));
    vi.spyOn(th("level"), "getBoundingClientRect").mockReturnValue(box(400));
    const dataTransfer = { setData: vi.fn(), effectAllowed: "", dropEffect: "" };
    // jsdom has no DragEvent, so a pointer position has to be put on the event.
    const dragAt = (el: HTMLElement, type: "dragOver" | "drop", clientX: number) => {
      const event = createEvent[type](el, { dataTransfer });
      Object.defineProperty(event, "clientX", { value: clientX });
      fireEvent(el, event);
    };

    fireEvent.dragStart(th("level"), { dataTransfer });
    dragAt(th("role"), "dragOver", 10);
    expect(th("role")).toHaveAttribute("data-drop", "before");
    dragAt(th("role"), "drop", 10);
    expect(headers().slice(0, 2)).toEqual(["level", "role"]);

    fireEvent.dragStart(th("level"), { dataTransfer });
    dragAt(th("role"), "dragOver", 90);
    expect(th("role")).toHaveAttribute("data-drop", "after");
    dragAt(th("role"), "drop", 90);
    expect(headers().slice(0, 3)).toEqual(["role", "level", "stage"]);
    expect(table().querySelector("[data-drop]")).toBeNull();
  });

  it("lets every column go but the role, and Reset columns puts back the first layout", async () => {
    render(at());
    await screen.findByText("Head of Platform");
    const columns = await openColumns();
    const reset = within(columns).getByRole("button", { name: msg("applications-list-columns-reset") });
    expect(reset).toBeDisabled();
    for (const box of within(columns).getAllByRole("checkbox")) {
      expect(box).toBeEnabled();
      if ((box as HTMLInputElement).checked) await userEvent.click(box);
    }
    expect(headers()).toEqual(["role"]);
    expect(within(rowOf(considering)).getByRole("link", { name: considering.title })).toBeInTheDocument();

    await userEvent.click(reset);
    expect(headers()).toEqual(["role", "stage", "pay", "location", "level", "next", "posting"]);
    expect(reset).toBeDisabled();
  });
});

describe("a row's actions", () => {
  const actionsOf = (card: ApplicationCard) => within(rowOf(card).querySelector<HTMLElement>(".app-list-actions")!);

  it("holds Radar's three, in Radar's order: Not for me, Compare, the star", async () => {
    render(at());
    await screen.findByText("Head of Platform");
    const names = actionsOf(considering).getAllByRole("button").map((button) => button.getAttribute("aria-label"));
    expect(names).toEqual([msg("shared-not-for-me"), msg("jobs-compare"), msg("jobs-save")]);
    expect(actionsOf(considering).getByRole("button", { name: msg("jobs-save") })).toHaveAttribute("aria-pressed", "true");
  });

  it("takes a role in Considering off the pipeline from its star, and Undo puts it back", async () => {
    render(at());
    await screen.findByText("Staff Product Manager, API");

    await userEvent.click(actionsOf(considering).getByRole("button", { name: msg("jobs-save") }));
    await waitFor(() => expect(rowOf(considering)).toBeNull());
    expect(api.setFavorite).toHaveBeenCalledWith(1, false);
    await userEvent.click(await screen.findByRole("button", { name: msg("applications-move-undo") }));
    await waitFor(() => expect(api.setFavorite).toHaveBeenLastCalledWith(1, true));
  });

  it("marks Not for me and takes the role off the pipeline, and Undo takes back both", async () => {
    render(at());
    await screen.findByText("Staff Product Manager, API");

    await userEvent.click(actionsOf(considering).getByRole("button", { name: msg("shared-not-for-me") }));
    expect(rowOf(considering)).toBeNull();
    await waitFor(() => expect(api.setFavorite).toHaveBeenCalledWith(1, false));
    expect(api.dismissJob).toHaveBeenCalledWith(1);
    expect(await screen.findByText(msg("applications-list-not-for-me", { title: considering.title }))).toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: msg("applications-move-undo") }));
    await waitFor(() => expect(api.setFavorite).toHaveBeenLastCalledWith(1, true));
    expect(api.undismissJob).toHaveBeenCalledWith(1);
  });

  it("puts the role back, and says so, when its Not for me cannot finish", async () => {
    vi.mocked(api.setFavorite).mockRejectedValueOnce(new Error("offline"));
    render(at());
    await screen.findByText("Staff Product Manager, API");

    await userEvent.click(actionsOf(considering).getByRole("button", { name: msg("shared-not-for-me") }));
    expect(await screen.findByText(msg("applications-remove-failed", { title: considering.title }))).toBeInTheDocument();
    await waitFor(() => expect(api.undismissJob).toHaveBeenCalledWith(1));
    await waitFor(() => expect(rowOf(considering)).not.toBeNull());
  });

  it("keeps a role under way, writes nothing, and offers Withdrawn as the way out", async () => {
    render(at());
    await screen.findByText("Principal Engineering Manager");

    await userEvent.click(actionsOf(applied).getByRole("button", { name: msg("jobs-save") }));
    expect(await screen.findByText(msg("error-application-under-way"))).toBeInTheDocument();
    await userEvent.click(actionsOf(applied).getByRole("button", { name: msg("shared-not-for-me") }));
    expect(api.setFavorite).not.toHaveBeenCalled();
    expect(api.dismissJob).not.toHaveBeenCalled();

    await userEvent.click(screen.getByRole("button", { name: msg("applications-page-withdraw") }));
    await waitFor(() => expect(api.setPursuit).toHaveBeenCalledWith(2, { stage: "withdrawn" }));
  });

  it("says an ended application stays, with no way out to offer", async () => {
    render(at());
    await screen.findByText("Head of Platform");
    await userEvent.click(actionsOf(rejected).getByRole("button", { name: msg("jobs-save") }));
    expect(await screen.findByText(msg("applications-list-ended"))).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: msg("applications-page-withdraw") })).toBeNull();
    expect(api.setFavorite).not.toHaveBeenCalled();
  });

  it("adds a role to compare from its row", async () => {
    render(at());
    await screen.findByText("Head of Platform");
    await userEvent.click(actionsOf(applied).getByRole("button", { name: msg("jobs-compare") }));
    expect(appState.toggleCompare).toHaveBeenCalledWith(2);
  });
});

describe("the List's filter", () => {
  const search = () => screen.getByRole("searchbox", { name: msg("applications-search-label") });

  it("shows only the matches, and says when none match", async () => {
    render(at());
    await screen.findByText("Head of Platform");
    await userEvent.type(search(), "stripe");
    expect(rowOrder()).toEqual([2]);
    await userEvent.type(search(), "zzz");
    expect(screen.getByText(msg("applications-list-no-matches"))).toBeInTheDocument();
  });

  it("keeps its filter to itself: the board does not take it, and the List finds it again", async () => {
    render(at());
    await screen.findByText("Head of Platform");
    await userEvent.type(search(), "stripe");

    await userEvent.click(screen.getByRole("tab", { name: msg("shell-tab-pipeline-board") }));
    expect(search()).toHaveValue("");
    expect(await screen.findByText("Head of Platform")).toBeInTheDocument();

    await userEvent.click(screen.getByRole("tab", { name: msg("shell-tab-pipeline-list") }));
    expect(search()).toHaveValue("stripe");
    expect(rowOrder()).toEqual([2]);
  });
});

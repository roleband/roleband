import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
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
    setPursuit: vi.fn(),
    setFavorite: vi.fn(),
    addInterview: vi.fn(),
    deleteInterview: vi.fn(),
  },
}));

const appState = { openJob: vi.fn(), refreshStats: vi.fn(), favVersion: 0 };
vi.mock("../../context/JobWorkspace", () => ({ useJobWorkspace: () => appState, useJobActions: () => appState }));
vi.mock("../../context/MissionState", () => ({ useMissionActions: () => appState }));

const considering = applicationCardFixture({ job_id: 1, title: "Staff Product Manager, API" });
const applied = applicationCardFixture({
  job_id: 2, pursuit_id: 20, stage: "applied", title: "Principal Engineering Manager", company: "stripe",
});
const rejected = applicationCardFixture({
  job_id: 3, pursuit_id: 30, stage: "rejected", ended_at_stage: "interviewing", title: "Head of Platform",
});

const withProviders = (ui: ReactElement) => (
  <ToastProvider>
    <MemoryRouter>{ui}</MemoryRouter>
  </ToastProvider>
);

const column = (name: string) => screen.getByRole("region", { name });
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
    await userEvent.click(within(menu).getByRole("button", { name: "Networking" }));

    expect(within(column("Networking")).getByText("Staff Product Manager, API")).toBeInTheDocument();
    expect(within(column("Considering")).queryByText("Staff Product Manager, API")).toBeNull();
    await waitFor(() => expect(api.setPursuit).toHaveBeenCalledWith(1, { stage: "networking" }));

    const toast = await screen.findByText(msg("applications-moved", { title: considering.title, stage: "Networking" }));
    await userEvent.click(within(toast.closest("[role=status], .ui-toast")! as HTMLElement)
      .getByRole("button", { name: msg("applications-move-undo") }));
    await waitFor(() => expect(api.setPursuit).toHaveBeenLastCalledWith(1, { stage: "saved" }));
    expect(api.setPursuit).toHaveBeenCalledTimes(2);
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
    await userEvent.type(within(dialog).getByLabelText(msg("applications-interview-date")), "2026-11-12");
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

describe("the Closed column", () => {
  it("hides on request and stays hidden on the next visit, folded to a button with its count", async () => {
    const { unmount } = render(withProviders(<ApplicationsScreen />));
    await screen.findByText("Head of Platform");

    await userEvent.click(screen.getByRole("button", { name: msg("applications-closed-hide-label") }));
    expect(screen.queryByRole("region", { name: msg("applications-column-closed") })).toBeNull();
    const show = screen.getByRole("button", { name: msg("applications-closed-show") });
    expect(show).toHaveTextContent("1");
    unmount();

    render(withProviders(<ApplicationsScreen />));
    await screen.findByText("Staff Product Manager, API");
    expect(screen.queryByText("Head of Platform")).toBeNull();
    await userEvent.click(screen.getByRole("button", { name: msg("applications-closed-show") }));
    expect(within(column(msg("applications-column-closed"))).getByText("Head of Platform")).toBeInTheDocument();
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
});

/* jsdom lays nothing out, so the board's geometry is drawn here: a column
 * every 264px from the left, 252px wide, and a split column's sections
 * stacked 200px apart from y 40. */
const COLUMN_ORDER = ["saved", "researching", "networking", "applied", "interviewing", "offer", "decided", "closed"];
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
const tileOf = (card: ApplicationCard) => document.querySelector<HTMLElement>(`.app-tile[data-job-id="${card.job_id}"]`)!;

/** Press a card, carry it to `to`, and let a frame draw it there. */
async function carry(card: ApplicationCard, to: { clientX: number; clientY: number }) {
  const tile = tileOf(card);
  fireEvent.pointerDown(tile, { pointerId: 1, button: 0, clientX: 900, clientY: 100 });
  fireEvent.pointerMove(tile, { pointerId: 1, ...to });
  await nextFrame();
  return tile;
}

const renderRouted = () => render(
  <ToastProvider>
    <MemoryRouter initialEntries={["/pipeline/board"]}>
      <Routes>
        <Route path="/pipeline/board" element={<ApplicationsScreen />} />
        <Route path="/pipeline/:id" element={<p>Opened the application</p>} />
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

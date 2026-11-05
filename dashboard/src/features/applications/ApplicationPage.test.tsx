import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { api, type ActivityItem, type ApplicationDetail, type JobDetail } from "../../api";
import { ApiError } from "../../api/transport";
import { ToastProvider } from "../../ui/Toast";
import { applicationCardFixture, applicationDetailFixture, jobDetailFixture } from "../../test/fixtures";
import { msg } from "../../test/msg";
import { ApplicationsScreen } from "./ApplicationsScreen";

/* One application's page: the stage button moves it (and its number keys),
 * Mark done asks at once for the next step, the feed takes a comment and
 * folds recorded changes, the priority edits in place, and a posting change
 * after applying is said once until dismissed. The API is a small store, so
 * a re-read after a write shows the write. */

vi.mock("../../api", async (importOriginal) => ({
  ...(await importOriginal<typeof import("../../api")>()),
  api: {
    applications: vi.fn(),
    application: vi.fn(),
    activity: vi.fn(),
    job: vi.fn(),
    setPursuit: vi.fn(),
    setFavorite: vi.fn(),
    addComment: vi.fn(),
    editComment: vi.fn(),
    deleteComment: vi.fn(),
    addInterview: vi.fn(),
    updateInterview: vi.fn(),
    deleteInterview: vi.fn(),
  },
}));

const appState = { openJob: vi.fn(), refreshStats: vi.fn(), favVersion: 0 };
vi.mock("../../context/JobWorkspace", () => ({ useJobWorkspace: () => appState, useJobActions: () => appState }));
vi.mock("../../context/MissionState", () => ({ useMissionActions: () => appState }));

const TITLE = "Staff Product Manager, API";
let detail: ApplicationDetail;
let items: ActivityItem[];
let posting: JobDetail;

const at = (iso: string) => iso;

beforeEach(() => {
  vi.clearAllMocks();
  localStorage.clear();
  detail = applicationDetailFixture({
    application: applicationCardFixture({
      job_id: 101, pursuit_id: 10, stage: "applied", title: TITLE, next_action: "Follow up with the recruiter",
      next_action_due: "2099-01-10T23:59:00Z",
    }),
  });
  items = [
    { kind: "comment", id: 7, created_at: at("2026-11-03T10:00:00Z"), actor: "agent", source: "mcp", body: "Found the hiring manager.", edited_at: null },
    { kind: "event", id: 6, created_at: at("2026-11-02T10:00:00Z"), actor: "user", source: "app", event_type: "updated", from_stage: "researching", to_stage: "applied", changed: ["stage"] },
    { kind: "event", id: 5, created_at: at("2026-11-01T10:00:00Z"), actor: "user", source: "app", event_type: "updated", from_stage: "researching", to_stage: "researching", changed: ["priority"] },
  ];
  posting = jobDetailFixture({
    id: 101,
    company: "openai",
    title: TITLE,
    lifecycle: [{ event_type: "changed", detail: { disclosed_base: {} }, at: "2026-11-03T09:00:00Z" }],
    pursuit: {
      id: 10, job_id: 101, stage: "applied", priority: 3, notes: "Referral from Sam.", next_action: null,
      next_action_due: null, created_at: "2026-10-20T09:00:00Z", updated_at: "2026-11-01T09:00:00Z",
    },
  });
  vi.mocked(api.application).mockImplementation(async () => structuredClone(detail));
  vi.mocked(api.activity).mockImplementation(async () => ({ items: structuredClone(items) }));
  vi.mocked(api.job).mockImplementation(async () => structuredClone(posting));
  vi.mocked(api.applications).mockImplementation(async () => ({ applications: [structuredClone(detail.application)] }));
  vi.mocked(api.setPursuit).mockImplementation(async (_jobId, update) => {
    detail = { ...detail, application: { ...detail.application, ...update } as ApplicationDetail["application"] };
    return { pursuit: {
      id: 10, stage: detail.application.stage, priority: detail.application.priority, notes: null,
      next_action: detail.application.next_action, next_action_due: detail.application.next_action_due,
      updated_at: "2026-11-04T12:00:00Z",
    } } as Awaited<ReturnType<typeof api.setPursuit>>;
  });
  vi.mocked(api.addComment).mockImplementation(async (_jobId, body) => {
    const comment = {
      kind: "comment" as const, id: 8, created_at: "2026-11-04T11:00:00Z", actor: "user" as const, source: "app", body, edited_at: null,
    };
    items = [comment, ...items];
    return { comment };
  });
});

function renderPage(path = "/pipeline/101") {
  return render(
    <ToastProvider>
      <MemoryRouter initialEntries={[path]}>
        <Routes>
          <Route path="/pipeline/:tab" element={<ApplicationsScreen />} />
        </Routes>
      </MemoryRouter>
    </ToastProvider>,
  );
}

/* The stage button is named by what it shows: the stage, then the days in it. */
const stageNamed = (stage: string) => new RegExp(`^${stage} · \\d+ days?$`);
const stageButton = () => screen.getByRole("button", { name: stageNamed("Applied") });

describe("the application page", () => {
  it("opens on the role, with its stage and, reached by its address, a way back to the board", async () => {
    renderPage();
    expect(await screen.findByRole("heading", { level: 1, name: TITLE })).toBeInTheDocument();
    expect(stageButton()).toBeInTheDocument();
    expect(screen.getByRole("link", { name: msg("applications-page-back", { view: msg("shell-tab-pipeline-board") }) }))
      .toHaveAttribute("href", "/pipeline/board");
  });

  it("goes back to the view it was opened from, with that view's filter", async () => {
    renderPage("/pipeline/board?q=product");
    await userEvent.click(await screen.findByRole("link", { name: TITLE }));
    await screen.findByRole("heading", { level: 1, name: TITLE });
    const back = screen.getByRole("link", { name: msg("applications-page-back", { view: msg("shell-tab-pipeline-board") }) });
    expect(back).toHaveAttribute("href", "/pipeline/board?q=product");

    await userEvent.click(back);
    expect(await screen.findByRole("tab", { name: msg("shell-tab-pipeline-board"), selected: true })).toBeInTheDocument();
    expect(screen.getByRole("searchbox")).toHaveValue("product");
  });

  it("moves the application from the stage button, and the number keys pick a moving stage", async () => {
    renderPage();
    await screen.findByRole("heading", { level: 1, name: TITLE });
    await userEvent.click(stageButton());
    const menu = await screen.findByRole("dialog", { name: msg("applications-stage-menu-label", { title: TITLE }) });
    expect(within(menu).getByRole("button", { name: /Applied/ })).toHaveAttribute("aria-current", "true");
    await userEvent.keyboard("6");
    expect(api.setPursuit).not.toHaveBeenCalled();
    await userEvent.keyboard("5");
    await waitFor(() => expect(api.setPursuit).toHaveBeenCalledWith(101, { stage: "offer" }));
    expect(await screen.findByRole("button", { name: stageNamed("Offer") }))
      .toBeInTheDocument();
  });

  it("opens the stage menu on S, but not while the person types", async () => {
    renderPage();
    await screen.findByRole("heading", { level: 1, name: TITLE });
    await userEvent.click(screen.getByRole("textbox", { name: msg("applications-comment-label") }));
    await userEvent.keyboard("s");
    expect(screen.queryByRole("dialog", { name: msg("applications-stage-menu-label", { title: TITLE }) })).toBeNull();
    (document.activeElement as HTMLElement).blur();
    await userEvent.keyboard("s");
    expect(await screen.findByRole("dialog", { name: msg("applications-stage-menu-label", { title: TITLE }) }))
      .toBeInTheDocument();
  });

  it("asks for the next step as soon as one is marked done, and Not now leaves it empty", async () => {
    renderPage();
    await screen.findByText("Follow up with the recruiter");
    await userEvent.click(screen.getByRole("button", { name: msg("applications-next-done") }));
    await waitFor(() => expect(api.setPursuit).toHaveBeenCalledWith(101, { next_action: null, next_action_due: null }));
    const prompt = await screen.findByLabelText(msg("applications-next-prompt"));
    expect(prompt).toHaveFocus();
    await userEvent.click(screen.getByRole("button", { name: msg("applications-next-not-now") }));
    expect(await screen.findByText(msg("applications-next-empty"))).toBeInTheDocument();
    expect(api.setPursuit).toHaveBeenCalledTimes(1);
  });

  it("saves the next step it asks for, due by the end of the day picked", async () => {
    renderPage();
    await screen.findByText("Follow up with the recruiter");
    await userEvent.click(screen.getByRole("button", { name: msg("applications-next-done") }));
    await userEvent.type(await screen.findByLabelText(msg("applications-next-prompt")), "Send the portfolio");
    await userEvent.type(screen.getByLabelText(msg("applications-next-due")), "2026-11-12");
    await userEvent.click(screen.getByRole("button", { name: msg("applications-next-save") }));
    await waitFor(() => expect(api.setPursuit).toHaveBeenLastCalledWith(101, {
      next_action: "Send the portfolio",
      next_action_due: new Date(2026, 10, 12, 23, 59).toISOString(),
    }));
    expect(await screen.findByText("Send the portfolio")).toBeInTheDocument();
  });

  it("sets the priority where it is shown", async () => {
    renderPage();
    await screen.findByRole("heading", { level: 1, name: TITLE });
    const priority = screen.getByRole("group", { name: msg("applications-fact-priority") });
    await userEvent.click(within(priority).getByRole("button", { name: "5" }));
    await waitFor(() => expect(api.setPursuit).toHaveBeenCalledWith(101, { priority: 5 }));
    expect(within(priority).getByRole("button", { name: "5" })).toHaveAttribute("aria-pressed", "true");
  });
});

describe("the feed", () => {
  it("folds the changes after a comment into one line that names them, and opens it on request", async () => {
    renderPage();
    const fold = await screen.findByRole("button", {
      name: msg("applications-feed-fold", {
        count: 2,
        changes: `${msg("applications-feed-moved", { stage: "Applied" })} and ${msg("applications-feed-priority")}`,
      }),
    });
    await userEvent.click(fold);
    expect(screen.getByText(msg("applications-feed-moved", { stage: "Applied" }))).toBeInTheDocument();
    expect(screen.getByText(msg("applications-feed-priority"))).toBeInTheDocument();
  });

  it("keeps a run the person opened open when their next change joins it at the top", async () => {
    // The newest entries are changes, so the person's next write lands in the run they opened.
    items = [
      items[1],
      items[2],
      { kind: "comment", id: 4, created_at: at("2026-10-30T10:00:00Z"), actor: "user", source: "app", body: "Applied through the referral.", edited_at: null },
    ];
    const write = vi.mocked(api.setPursuit).getMockImplementation()!;
    vi.mocked(api.setPursuit).mockImplementation(async (jobId, update) => {
      items = [
        { kind: "event", id: 9, created_at: at("2026-11-04T12:00:00Z"), actor: "user", source: "app", event_type: "updated", from_stage: "applied", to_stage: "applied", changed: ["priority"] },
        ...items,
      ];
      return write(jobId, update);
    });
    renderPage();
    const changes = `${msg("applications-feed-moved", { stage: "Applied" })} and ${msg("applications-feed-priority")}`;
    await userEvent.click(await screen.findByRole("button", { name: msg("applications-feed-fold", { count: 2, changes }) }));

    const priority = screen.getByRole("group", { name: msg("applications-fact-priority") });
    await userEvent.click(within(priority).getByRole("button", { name: "5" }));

    await waitFor(() => expect(screen.getAllByText(msg("applications-feed-priority"))).toHaveLength(2));
    expect(screen.getByText(msg("applications-feed-moved", { stage: "Applied" }))).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: msg("applications-feed-fold", { count: 3, changes }) })).toBeNull();
  });

  it("posts a comment from the composer above the newest entry", async () => {
    renderPage();
    const box = await screen.findByRole("textbox", { name: msg("applications-comment-label") });
    await userEvent.type(box, "Recruiter replied, call on Monday.");
    await userEvent.click(screen.getByRole("button", { name: msg("applications-comment-submit") }));
    await waitFor(() => expect(api.addComment).toHaveBeenCalledWith(101, "Recruiter replied, call on Monday."));
    expect(await screen.findByText("Recruiter replied, call on Monday.")).toBeInTheDocument();
    expect(box).toHaveValue("");
  });

  it("lets the person change their own comments and not an agent's", async () => {
    renderPage();
    const agentComment = (await screen.findByText("Found the hiring manager.")).closest("li")!;
    expect(within(agentComment as HTMLElement).queryByRole("button", { name: msg("applications-comment-edit") })).toBeNull();
    expect(within(agentComment as HTMLElement).getByText(msg("applications-comment-author-agent"))).toBeInTheDocument();
  });
});

describe("an interview on the page", () => {
  beforeEach(() => {
    detail = {
      ...detail,
      interviews: [{
        id: 31, label: "Panel", scheduled_at: "2099-01-12T15:00:00Z", all_day: false, format: null, link: null,
        outcome: null, notes: null, created_at: "2026-11-01T09:00:00Z", updated_at: "2026-11-01T09:00:00Z",
      }],
    };
  });

  it("is deleted only after the form asks, and a failed delete says it was the delete that failed", async () => {
    vi.mocked(api.deleteInterview).mockRejectedValueOnce(new Error("offline"));
    renderPage();
    await userEvent.click(await screen.findByRole("button", { name: msg("applications-interview-edit-label", { label: "Panel" }) }));
    const dialog = await screen.findByRole("dialog");
    await userEvent.click(within(dialog).getByRole("button", { name: msg("applications-interview-delete") }));
    expect(api.deleteInterview).not.toHaveBeenCalled();

    await userEvent.click(within(dialog).getByRole("button", { name: msg("applications-comment-delete") }));
    expect(api.deleteInterview).toHaveBeenCalledWith(101, 31);
    expect(await screen.findByText(msg("applications-interview-delete-failed"))).toBeInTheDocument();
    expect(screen.queryByText(msg("applications-interview-failed"))).toBeNull();
  });
});

describe("the posting beside the application", () => {
  it("says once that the pay changed after applying, until the person dismisses it", async () => {
    const { unmount } = renderPage();
    const line = await screen.findByText(msg("applications-crossing-pay", { days: 2 }));
    await userEvent.click(within(line.closest("[role=status]") as HTMLElement)
      .getByRole("button", { name: msg("applications-crossing-dismiss") }));
    expect(screen.queryByText(msg("applications-crossing-pay", { days: 2 }))).toBeNull();
    unmount();
    renderPage();
    await screen.findByRole("heading", { level: 1, name: TITLE });
    expect(screen.queryByText(msg("applications-crossing-pay", { days: 2 }))).toBeNull();
  });

  it("shows the notes kept on the pursuit", async () => {
    renderPage();
    expect(await screen.findByText("Referral from Sam.")).toBeInTheDocument();
  });
});

it("says a role that left the pipeline is gone, with a way back to the board", async () => {
  vi.mocked(api.application).mockRejectedValue(new ApiError("gone", 404, "application-not-found"));
  renderPage();
  expect(await screen.findByText(msg("error-application-not-found"))).toBeInTheDocument();
  expect(screen.getByRole("link", { name: msg("applications-page-back-board") })).toHaveAttribute("href", "/pipeline/board");
});

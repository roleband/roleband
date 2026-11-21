import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useCallback, useState } from "react";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { api, type ApplicationDetail, type Job, type JobDetail, type PursuitStage } from "../../api";
import { ApiError } from "../../api/transport";
import { ToastProvider } from "../../ui/Toast";
import { applicationCardFixture, applicationDetailFixture, jobDetailFixture } from "../../test/fixtures";
import { msg } from "../../test/msg";
import { interviewWhen } from "./ApplicationPanels";
import { usePostingPipeline, type PostingTab } from "./usePostingPipeline";

/* The pipeline's part of a posting. Off the board it is the star and nothing
 * else, and the posting has no tabs; on it, the star's place holds the
 * pipeline's own stage button, menu and moves, the side column gains a
 * Pipeline section (the stage, the priority, its days with the application's
 * history, and what waits), the posting reads in two tabs, the posting and the
 * Workspace, and it knows whether the person has applied. The API is a small
 * store, so a re-read after a write shows the write. */

vi.mock("../../api", async (importOriginal) => ({
  ...(await importOriginal<typeof import("../../api")>()),
  api: {
    application: vi.fn(),
    setPursuit: vi.fn(),
    setFavorite: vi.fn(),
    addInterview: vi.fn(),
    deleteInterview: vi.fn(),
    activity: vi.fn(),
  },
}));

const appState = { refreshStats: vi.fn(), savedChanged: vi.fn(), favVersion: 0 };
vi.mock("../../context/JobWorkspace", () => ({ useJobWorkspace: () => appState, useJobActions: () => appState }));
vi.mock("../../context/MissionState", () => ({ useMissionActions: () => appState }));

const TITLE = "Staff Product Manager, API";
const DAY = 86_400_000;
const daysAgo = (days: number) => new Date(Date.now() - days * DAY).toISOString();
/** Tomorrow at noon, the reader's time: "tomorrow" whatever the hour now. */
const tomorrowNoon = () => {
  const d = new Date();
  return new Date(d.getFullYear(), d.getMonth(), d.getDate() + 1, 12).toISOString();
};

let detail: ApplicationDetail | null;

function posting(overrides: Partial<JobDetail> = {}): JobDetail {
  return jobDetailFixture({ id: 101, company: "openai", title: TITLE, is_favorite: false, pursuit: null, ...overrides });
}

function pursuit(stage: PursuitStage) {
  return {
    id: 10, job_id: 101, stage, priority: 3, notes: null, next_action: null, next_action_due: null,
    created_at: daysAgo(20), updated_at: daysAgo(9),
  };
}

/** The posting's bar, its side column and whether it reads as applied, as the
 *  posting screen draws them, around the posting's own state. */
function Posting({ initial, asked = null }: { initial: Job; asked?: PostingTab | null }) {
  const [job, setJob] = useState<Job | null>(initial);
  const [tab, setTab] = useState<PostingTab | null>(asked);
  const [column, setColumn] = useState<HTMLElement | null>(null);
  const showSaved = useCallback((on: boolean) => setJob((prev) => prev && { ...prev, is_favorite: on }), []);
  const paintPosting = useCallback(
    (stage: PursuitStage) =>
      setJob((prev) => (prev?.pursuit ? { ...prev, pursuit: { ...prev.pursuit, stage } } : prev)),
    [],
  );
  const onSave = () => {
    void api.setFavorite(initial.id, true);
    showSaved(true);
  };
  // The server's copy of the posting is the one the screen opened on: these
  // specs' failed writes change nothing there.
  const rereadPosting = useCallback(() => setJob(initial), [initial]);
  const paintNotes = useCallback(
    (notes: string | null) => setJob((prev) => (prev?.pursuit ? { ...prev, pursuit: { ...prev.pursuit, notes } } : prev)),
    [],
  );
  const pipeline = usePostingPipeline(job, {
    showSaved, paintPosting, paintNotes, rereadPosting, onSave, now: new Date(), column, tab, onTab: setTab,
  });
  return (
    <>
      <nav aria-label="Posting bar">{pipeline.control}</nav>
      <p data-testid="tab">{pipeline.tab ?? "no tabs"}</p>
      <main aria-label="Main column">{pipeline.tab === "workspace" ? pipeline.workspace : "The posting"}</main>
      <aside aria-label="Side column" ref={setColumn}>{pipeline.section}</aside>
      <p>{pipeline.applied ? "View posting" : "View & apply"}</p>
    </>
  );
}

function renderPosting(job: JobDetail, asked: PostingTab | null = null) {
  return render(
    <ToastProvider>
      <MemoryRouter initialEntries={["/company/openai/job/101"]}>
        <Posting initial={job} asked={asked} />
      </MemoryRouter>
    </ToastProvider>,
  );
}

const bar = () => screen.getByRole("navigation", { name: "Posting bar" });
const column = () => screen.getByRole("complementary", { name: "Side column" });
const main = () => screen.getByRole("main", { name: "Main column" });
const stageNamed = (stage: string) => new RegExp(`^${stage}$`);
const menuOf = () => screen.findByRole("dialog", { name: msg("applications-stage-menu-label", { title: TITLE }) });

/** The Pipeline section's value for `term`, or undefined when the row is not shown. */
function row(term: string): HTMLElement | undefined {
  const dt = within(column()).queryAllByRole("term").find((t) => t.textContent === term);
  return (dt?.nextElementSibling as HTMLElement | null) ?? undefined;
}
async function findRow(term: string): Promise<HTMLElement> {
  await waitFor(() => expect(row(term), `the ${term} row`).toBeDefined());
  return row(term)!;
}

beforeEach(() => {
  vi.clearAllMocks();
  detail = null;
  vi.mocked(api.application).mockImplementation(async () => {
    if (!detail) throw new ApiError("not on the board", 404);
    return structuredClone(detail);
  });
  vi.mocked(api.setPursuit).mockImplementation(async (_jobId, update) => {
    if (detail) detail = { ...detail, application: { ...detail.application, ...update } as ApplicationDetail["application"] };
    return { pursuit: { ...pursuit("saved"), ...update } } as Awaited<ReturnType<typeof api.setPursuit>>;
  });
  vi.mocked(api.activity).mockResolvedValue({ items: [] } as Awaited<ReturnType<typeof api.activity>>);
  vi.mocked(api.setFavorite).mockImplementation(async (_jobId, on) => {
    if (detail) detail = on ? { ...detail, application: { ...detail.application, starred: true } } : null;
    return { job_id: 101, is_favorite: on };
  });
});

describe("a posting off the board", () => {
  it("shows the star alone: no stage, no Pipeline section, and applying is still the action", async () => {
    renderPosting(posting());
    expect(within(bar()).getByRole("button", { name: msg("jobs-save"), pressed: false })).toBeInTheDocument();
    expect(within(column()).queryByText(msg("applications-posting-row"))).toBeNull();
    expect(screen.queryByRole("link")).toBeNull();
    expect(screen.getByText("View & apply")).toBeInTheDocument();
    expect(screen.getByTestId("tab"), "a role outside the pipeline reads as one posting").toHaveTextContent("no tabs");
    expect(api.application, "a role off the board asks the pipeline nothing").not.toHaveBeenCalled();
  });

  it("treats a role pursued in Considering without its star as off the board, as the board does", async () => {
    renderPosting(posting({ pursuit: pursuit("saved") }), "workspace");
    expect(screen.getByTestId("tab"), "an address naming the Workspace gives a role off the board no tabs").toHaveTextContent("no tabs");
    expect(within(bar()).getByRole("button", { name: msg("jobs-save"), pressed: false })).toBeInTheDocument();
    expect(within(column()).queryByText(msg("applications-posting-row"))).toBeNull();
    expect(api.application).not.toHaveBeenCalled();
  });

  it("turns the star into Considering in the same place once saved, and adds the section", async () => {
    renderPosting(posting());
    detail = applicationDetailFixture({
      application: applicationCardFixture({ stage: "saved", starred: true, stage_since: daysAgo(0) }),
      stages_reached: [{ stage: "saved", at: daysAgo(0) }],
    });
    await userEvent.click(within(bar()).getByRole("button", { name: msg("jobs-save") }));
    expect(api.setFavorite).toHaveBeenCalledWith(101, true);
    expect(await within(bar()).findByRole("button", { name: stageNamed("Considering") })).toBeInTheDocument();
    expect(within(bar()).queryByRole("button", { name: msg("jobs-save") }), "no second star beside the stage").toBeNull();
    expect((await findRow(msg("applications-posting-stage"))).textContent).toBe(msg("taxonomy-stage-saved"));
    expect(await findRow(msg("applications-fact-days")), "saved just now: no count of zero days")
      .toHaveTextContent(new RegExp(`^${msg("applications-posting-since-today")}`));
    expect(row(msg("applications-posting-next-step")), "no step set, no Next step row").toBeUndefined();
    expect(row(msg("applications-posting-interview")), "no interview booked, no Interview row").toBeUndefined();
    expect(screen.getByText("View & apply")).toBeInTheDocument();
  });
});

describe("a posting on the board", () => {
  it("names the stage alone in the bar, and its days in the section", async () => {
    detail = applicationDetailFixture({
      application: applicationCardFixture({ pursuit_id: 10, stage: "applied", stage_since: daysAgo(12) }),
    });
    renderPosting(posting({ is_favorite: true, pursuit: pursuit("applied") }));
    const days = await findRow(msg("applications-fact-days"));
    expect(days).toHaveTextContent(/^12 days/);
    expect(within(bar()).getByRole("button", { name: "Applied" }), "the bar holds the stage, never its age")
      .toHaveTextContent(/^Applied$/);
    expect(within(bar()).queryByText(/\d+d\b|days/)).toBeNull();
    expect(screen.getByText("View posting")).toBeInTheDocument();
  });

  it("says what waits in rows of their own, in plain words with nothing to press but the history", async () => {
    detail = applicationDetailFixture({
      application: applicationCardFixture({
        pursuit_id: 10, stage: "applied", stage_since: daysAgo(3),
        next_action: "Email the recruiter", next_action_due: tomorrowNoon(),
      }),
    });
    const { unmount } = renderPosting(posting({ is_favorite: true, pursuit: pursuit("applied") }));
    const tomorrow = msg("applications-posting-due-day", { offset: 1, date: "" });
    const step = await findRow(msg("applications-posting-next-step"));
    expect(step.textContent, "the step alone: its date has a row of its own").toBe("Email the recruiter");
    const due = row(msg("applications-posting-due"))!;
    expect(due.textContent).toBe(tomorrow);
    expect(due, "a date still to come is plain").not.toHaveClass("jd-pipeline-late");
    expect(column().querySelector(".ui-badge"), "no pill in the section").toBeNull();
    // The stage is read here and changed in the bar: the rows hold two
    // controls, the priority and the history, and lead nowhere else: the
    // Workspace is a tab of this same screen.
    expect(row(msg("applications-posting-stage"))!.textContent).toBe(msg("taxonomy-stage-applied"));
    expect(within(column()).queryAllByRole("link"), "no way out to another page").toEqual([]);
    expect(within(column()).getAllByRole("button").map((button) => button.getAttribute("aria-label") ?? button.textContent))
      .toEqual([
        msg("applications-card-priority", { level: msg("applications-priority-none") }),
        msg("applications-posting-history-title"),
      ]);
    expect(row(msg("applications-posting-interview")), "no interview booked, no Interview row").toBeUndefined();
    expect(within(bar()).queryByText(tomorrow), "due tomorrow: the section says it, the bar does not").toBeNull();
    unmount();

    // A step with no date has no Due row.
    detail = applicationDetailFixture({
      application: applicationCardFixture({
        pursuit_id: 10, stage: "applied", stage_since: daysAgo(3), next_action: "Email the recruiter", next_action_due: null,
      }),
    });
    const undated = renderPosting(posting({ is_favorite: true, pursuit: pursuit("applied") }));
    expect((await findRow(msg("applications-posting-next-step"))).textContent).toBe("Email the recruiter");
    expect(row(msg("applications-posting-due")), "no date set, no Due row").toBeUndefined();
    undated.unmount();

    // Overdue, the one state the board paints red.
    detail = applicationDetailFixture({
      application: applicationCardFixture({
        pursuit_id: 10, stage: "applied", stage_since: daysAgo(3),
        next_action: "Email the recruiter", next_action_due: daysAgo(2),
      }),
    });
    const second = renderPosting(posting({ is_favorite: true, pursuit: pursuit("applied") }));
    const late = msg("applications-card-overdue", { days: 2 });
    await findRow(msg("applications-posting-next-step"));
    expect(row(msg("applications-posting-due"))!.textContent).toBe(late);
    expect(row(msg("applications-posting-due")), "the one row that takes a colour").toHaveClass("jd-pipeline-late");
    expect(within(bar()).queryByText(late)).toBeNull();
    second.unmount();

    // A booked interview gets its own row beside the step: when it is, and
    // nothing else. The round is the application page's to say.
    const interview = { id: 1, label: "Hiring manager", scheduled_at: tomorrowNoon(), all_day: false, format: "video" as const, link: null };
    detail = applicationDetailFixture({
      application: applicationCardFixture({
        pursuit_id: 10, stage: "interviewing", stage_since: daysAgo(3),
        next_action: "Email the recruiter", next_action_due: daysAgo(-5), next_interview: interview,
      }),
    });
    renderPosting(posting({ is_favorite: true, pursuit: pursuit("interviewing") }));
    const booked = await findRow(msg("applications-posting-interview"));
    expect(booked.textContent, "when, as the application page says it, and only that").toBe(interviewWhen(interview));
    expect(within(column()).queryByText(/Hiring manager/), "the round stays on the application page").toBeNull();
    expect(row(msg("applications-posting-next-step"))).toHaveTextContent("Email the recruiter");
  });

  it("opens the application's history from its days: each stage, the interviews held, then today", async () => {
    detail = applicationDetailFixture({
      application: applicationCardFixture({ pursuit_id: 10, stage: "applied", stage_since: daysAgo(12) }),
      stages_reached: [{ stage: "saved", at: daysAgo(15) }, { stage: "applied", at: daysAgo(12) }],
      interviews: [
        { id: 3, label: "Hiring manager", scheduled_at: tomorrowNoon(), all_day: false, format: null, link: null, outcome: null, notes: null, created_at: daysAgo(1), updated_at: daysAgo(1) },
        { id: 2, label: "Team lunch", scheduled_at: daysAgo(6), all_day: false, format: null, link: null, outcome: "cancelled", notes: null, created_at: daysAgo(8), updated_at: daysAgo(6) },
        { id: 1, label: "Recruiter screen", scheduled_at: daysAgo(5), all_day: false, format: "phone", link: null, outcome: "passed", notes: null, created_at: daysAgo(10), updated_at: daysAgo(5) },
      ],
    });
    renderPosting(posting({ is_favorite: true, pursuit: pursuit("applied") }));
    const days = await findRow(msg("applications-fact-days"));
    // The clock carries no word: its name says which history it opens.
    const clock = within(days).getByRole("button", { name: msg("applications-posting-history-title") });
    expect(clock).toHaveTextContent("");
    expect(clock).toHaveAttribute("title", msg("applications-posting-history-title"));
    await userEvent.click(clock);
    const history = await screen.findByRole("dialog", { name: msg("applications-posting-history-title") });
    const lines = within(history).getAllByRole("listitem").map((line) => line.textContent);
    expect(lines).toHaveLength(4);
    expect(lines[0]).toMatch(/Considering$/);
    expect(lines[1]).toMatch(/Applied$/);
    expect(lines[2], "a held interview, by its round").toMatch(/Recruiter screen interview$/);
    expect(lines[3]).toBe(`${msg("applications-posting-history-today")}${msg("applications-posting-history-now", { stage: "Applied", days: 12 })}`);
    expect(lines.join(" "), "an interview still to come is the Interview row's, and a cancelled one never happened")
      .not.toMatch(/Hiring manager|Team lunch/);
  });

  it("asks for the interview before a move into Interviewing, and moves nothing on Cancel", async () => {
    detail = applicationDetailFixture({
      application: applicationCardFixture({ pursuit_id: 10, stage: "applied", stage_since: daysAgo(2) }),
    });
    renderPosting(posting({ is_favorite: true, pursuit: pursuit("applied") }));
    await userEvent.click(await within(bar()).findByRole("button", { name: stageNamed("Applied") }));
    const menu = await menuOf();
    await userEvent.click(within(menu).getByRole("button", { name: /Interviewing/ }));
    const form = await screen.findByRole("dialog", { name: msg("applications-interview-title") });
    expect(api.setPursuit, "no move without the interview's date").not.toHaveBeenCalled();
    await userEvent.click(within(form).getByRole("button", { name: msg("applications-interview-cancel") }));
    await waitFor(() => expect(screen.queryByRole("dialog", { name: msg("applications-interview-title") })).toBeNull());
    expect(api.setPursuit).not.toHaveBeenCalled();
    expect(within(bar()).getByRole("button", { name: stageNamed("Applied") })).toBeInTheDocument();
  });

  it("names a move into or out of an ending at once, before the server answers", async () => {
    // The write never lands, so only the move's own paint is on screen.
    vi.mocked(api.setPursuit).mockImplementation(() => new Promise(() => {}));
    detail = applicationDetailFixture({
      application: applicationCardFixture({ pursuit_id: 10, stage: "rejected", ended_at_stage: "applied", stage_since: daysAgo(4) }),
    });
    const ended = renderPosting(posting({ is_favorite: true, pursuit: pursuit("rejected") }));
    await userEvent.click(await within(bar()).findByRole("button", { name: stageNamed("Rejected at Applied") }));
    await userEvent.click(within(await menuOf()).getByRole("button", { name: /Applied/ }));
    expect(await within(bar()).findByRole("button", { name: stageNamed("Applied") }), "moving again, not \"Applied at Applied\"")
      .toBeInTheDocument();
    expect(row(msg("applications-posting-stage"))!.textContent).toBe(msg("taxonomy-stage-applied"));
    ended.unmount();

    detail = applicationDetailFixture({
      application: applicationCardFixture({ pursuit_id: 10, stage: "applied", stage_since: daysAgo(4) }),
    });
    renderPosting(posting({ is_favorite: true, pursuit: pursuit("applied") }));
    await userEvent.click(await within(bar()).findByRole("button", { name: stageNamed("Applied") }));
    await userEvent.click(within(await menuOf()).getByRole("button", { name: /Rejected/ }));
    expect(await within(bar()).findByRole("button", { name: stageNamed("Rejected at Applied") }), "the stage it ended from")
      .toBeInTheDocument();
  });

  it("keeps an unstarred role on the posting when its move back to Considering fails", async () => {
    // Off the star, a role is on the board only past Considering, so a stage
    // painted and never saved would drop it off the posting.
    vi.mocked(api.setPursuit).mockRejectedValue(new ApiError("down", 500));
    detail = applicationDetailFixture({
      application: applicationCardFixture({ pursuit_id: 10, stage: "applied", starred: false, stage_since: daysAgo(4) }),
    });
    renderPosting(posting({ is_favorite: false, pursuit: pursuit("applied") }));
    await userEvent.click(await within(bar()).findByRole("button", { name: stageNamed("Applied") }));
    await userEvent.click(within(await menuOf()).getByRole("button", { name: /Considering/ }));
    await waitFor(() => expect(api.setPursuit).toHaveBeenCalledWith(101, { stage: "saved" }));
    expect(await within(bar()).findByRole("button", { name: stageNamed("Applied") }), "the stage the server kept").toBeInTheDocument();
    expect(within(bar()).queryByRole("button", { name: msg("jobs-save") })).toBeNull();
    expect((await findRow(msg("applications-posting-stage"))).textContent).toBe(msg("taxonomy-stage-applied"));
  });

  it("moves to another stage from the menu, the pipeline's own way, and announces the save", async () => {
    detail = applicationDetailFixture({
      application: applicationCardFixture({ pursuit_id: 10, stage: "saved", stage_since: daysAgo(4) }),
    });
    renderPosting(posting({ is_favorite: true, pursuit: pursuit("saved") }));
    await userEvent.click(await within(bar()).findByRole("button", { name: stageNamed("Considering") }));
    await userEvent.click(within(await menuOf()).getByRole("button", { name: /Applied/ }));
    await waitFor(() => expect(api.setPursuit).toHaveBeenCalledWith(101, { stage: "applied" }));
    expect(await within(bar()).findByRole("button", { name: stageNamed("Applied") })).toBeInTheDocument();
    await waitFor(() => expect(row(msg("applications-posting-stage"))?.textContent, "the section follows the move").toBe(msg("taxonomy-stage-applied")));
    expect(screen.getByText("View posting")).toBeInTheDocument();
    expect(appState.savedChanged, "the board and an application page under the posting re-read")
      .toHaveBeenCalledWith({ jobId: 101, saved: true });
  });

  it("offers Remove only in Considering, and Undo puts the role back", async () => {
    detail = applicationDetailFixture({
      application: applicationCardFixture({ pursuit_id: null, stage: "saved", stage_since: daysAgo(1) }),
    });
    renderPosting(posting({ is_favorite: true }));
    await userEvent.click(await within(bar()).findByRole("button", { name: stageNamed("Considering") }));
    await userEvent.click(within(await menuOf()).getByRole("button", { name: msg("applications-menu-remove") }));
    await waitFor(() => expect(api.setFavorite).toHaveBeenCalledWith(101, false));
    expect(await within(bar()).findByRole("button", { name: msg("jobs-save"), pressed: false })).toBeInTheDocument();
    expect(within(column()).queryByText(msg("applications-posting-row")), "the section leaves with the role").toBeNull();

    await userEvent.click(await screen.findByRole("button", { name: msg("applications-move-undo") }));
    await waitFor(() => expect(api.setFavorite).toHaveBeenLastCalledWith(101, true));
    expect(await within(bar()).findByRole("button", { name: stageNamed("Considering") })).toBeInTheDocument();
  });

  it("has no Remove past Considering: there the way out is Withdrawn", async () => {
    detail = applicationDetailFixture({
      application: applicationCardFixture({ pursuit_id: 10, stage: "applied", stage_since: daysAgo(5) }),
    });
    renderPosting(posting({ is_favorite: true, pursuit: pursuit("applied") }));
    await userEvent.click(await within(bar()).findByRole("button", { name: stageNamed("Applied") }));
    const menu = await menuOf();
    expect(within(menu).queryByRole("button", { name: msg("applications-menu-remove") })).toBeNull();
    expect(within(menu).getByRole("button", { name: /Withdrawn/ })).toBeInTheDocument();
  });

  it("says how and when an ended application ended, with nothing waiting", async () => {
    detail = applicationDetailFixture({
      application: applicationCardFixture({
        pursuit_id: 10, stage: "rejected", ended_at_stage: "applied", stage_since: "2026-11-03T12:00:00Z",
        next_action: "Email the recruiter",
      }),
      stages_reached: [{ stage: "applied", at: "2026-10-20T09:00:00Z" }, { stage: "rejected", at: "2026-11-03T12:00:00Z" }],
    });
    renderPosting(posting({ is_favorite: true, pursuit: pursuit("rejected") }));
    const ended = msg("applications-card-ended", { ending: "Rejected", stage: "Applied" });
    expect(await within(bar()).findByRole("button", { name: ended })).toBeInTheDocument();
    expect(await findRow(msg("applications-posting-stage"))).toHaveTextContent(ended);
    const when = await findRow(msg("applications-posting-ended"));
    expect(when).toHaveTextContent(/Nov 3/);
    expect(row(msg("applications-fact-days"))).toBeUndefined();
    expect(row(msg("applications-posting-next-step")), "an ended application has nothing waiting").toBeUndefined();

    await userEvent.click(within(when).getByRole("button", { name: msg("applications-posting-history-title") }));
    const history = await screen.findByRole("dialog", { name: msg("applications-posting-history-title") });
    const lines = within(history).getAllByRole("listitem");
    expect(lines.map((line) => line.textContent), "the ending is the last line: no today line").toHaveLength(2);
    expect(lines[1]).toHaveTextContent(/Rejected$/);
    expect(lines[1]).toHaveClass("is-closed");
    expect(screen.getByText("View posting")).toBeInTheDocument();
  });

  it("sets the priority from its row, painting it before the server answers", async () => {
    detail = applicationDetailFixture({
      application: applicationCardFixture({ pursuit_id: 10, stage: "applied", stage_since: daysAgo(2), priority: 3, priority_set: false }),
    });
    renderPosting(posting({ is_favorite: true, pursuit: pursuit("applied") }));
    const priority = await findRow(msg("applications-fact-priority"));
    // Named with its row, as a card's mark is: "High" alone says nothing.
    await userEvent.click(within(priority).getByRole("button", {
      name: msg("applications-card-priority", { level: msg("applications-priority-none") }),
    }));
    const menu = await screen.findByRole("dialog", { name: msg("applications-priority-menu", { title: TITLE }) });
    vi.mocked(api.setPursuit).mockImplementationOnce(() => new Promise(() => {}));
    await userEvent.click(within(menu).getByRole("button", { name: new RegExp(msg("applications-priority-high")) }));
    expect(api.setPursuit).toHaveBeenCalledWith(101, { priority: 4 });
    expect(within(row(msg("applications-fact-priority"))!).getByRole("button"), "painted at once")
      .toHaveTextContent(msg("applications-priority-high"));
  });

  it("has no priority once the application has ended: nothing waits to be ranked", async () => {
    detail = applicationDetailFixture({
      application: applicationCardFixture({ pursuit_id: 10, stage: "rejected", ended_at_stage: "applied", stage_since: daysAgo(2) }),
    });
    renderPosting(posting({ is_favorite: true, pursuit: pursuit("rejected") }));
    await findRow(msg("applications-posting-stage"));
    expect(row(msg("applications-fact-priority"))).toBeUndefined();
  });
});

describe("a role's two tabs", () => {
  const applied = () => applicationDetailFixture({
    application: applicationCardFixture({
      pursuit_id: 10, stage: "applied", stage_since: daysAgo(3),
      next_action: "Email the recruiter", next_action_due: tomorrowNoon(),
    }),
  });

  it("opens on the posting unless the address names the Workspace, and reads the feed only there", async () => {
    detail = applied();
    const first = renderPosting(posting({ is_favorite: true, pursuit: pursuit("applied") }));
    await findRow(msg("applications-posting-next-step"));
    expect(screen.getByTestId("tab")).toHaveTextContent("posting");
    expect(main()).toHaveTextContent("The posting");
    expect(api.activity, "the feed is the Workspace's").not.toHaveBeenCalled();
    first.unmount();

    renderPosting(posting({ is_favorite: true, pursuit: pursuit("applied") }), "workspace");
    expect(screen.getByTestId("tab")).toHaveTextContent("workspace");
    expect(await within(main()).findByText(msg("applications-ws-next"))).toBeInTheDocument();
    await waitFor(() => expect(api.activity).toHaveBeenCalledWith(101, expect.anything()));
  });

  it("leaves the next step and its day to the Workspace while it is on screen, and keeps the rest", async () => {
    detail = applied();
    renderPosting(posting({ is_favorite: true, pursuit: pursuit("applied") }), "workspace");
    await within(main()).findByText(msg("applications-ws-next"));
    expect(row(msg("applications-posting-stage"))).toBeDefined();
    expect(row(msg("applications-fact-priority"))).toBeDefined();
    expect(row(msg("applications-fact-days"))).toBeDefined();
    expect(row(msg("applications-posting-next-step")), "said once, in the main column").toBeUndefined();
    expect(row(msg("applications-posting-due"))).toBeUndefined();
    expect(within(main()).getByText("Email the recruiter")).toBeInTheDocument();
  });

  it("opens the stage menu on M and the interview form on I, but not while typing", async () => {
    detail = applied();
    renderPosting(posting({ is_favorite: true, pursuit: pursuit("applied") }));
    await findRow(msg("applications-posting-stage"));
    await userEvent.keyboard("m");
    expect(await menuOf()).toBeInTheDocument();
    await userEvent.keyboard("{Escape}");
    await waitFor(() => expect(screen.queryByRole("dialog", { name: msg("applications-stage-menu-label", { title: TITLE }) })).toBeNull());
    await userEvent.keyboard("i");
    const form = await screen.findByRole("dialog", { name: msg("applications-interview-add-title") });
    await userEvent.type(within(form).getAllByRole("textbox")[0], "mi");
    expect(screen.queryByRole("dialog", { name: msg("applications-stage-menu-label", { title: TITLE }) }), "a key typed into a field is the field's")
      .toBeNull();
  });

  it("answers no key for a role outside the pipeline", async () => {
    renderPosting(posting());
    await userEvent.keyboard("mi");
    expect(screen.queryByRole("dialog")).toBeNull();
  });
});

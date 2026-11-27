import { act, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useCallback, useEffect, useState } from "react";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { api, type ApplicationDetail, type Job, type JobDetail, type PursuitStage } from "../../api";
import { ApiError } from "../../api/transport";
import { ToastProvider } from "../../ui/Toast";
import { applicationCardFixture, applicationDetailFixture, jobDetailFixture } from "../../test/fixtures";
import { msg } from "../../test/msg";
import { interviewWhen } from "./interviewWords";
import type { RoleTab } from "./roleLink";
import { usePostingPipeline } from "./usePostingPipeline";

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
    updateStep: vi.fn(),
  },
}));

/* A write that landed bumps the version every reader of the role re-reads on,
 * and the screen draws again, as the provider does. */
let redraw: () => void = () => undefined;
const appState = {
  refreshStats: vi.fn(),
  savedChanged: vi.fn(() => {
    appState.favVersion += 1;
    redraw();
  }),
  favVersion: 0,
};
vi.mock("../../context/JobWorkspace", () => ({ useJobWorkspace: () => appState, useJobActions: () => appState }));
vi.mock("../../context/MissionState", () => ({ useMissionActions: () => appState }));

/* The notes page's editor stands in here: it keeps every save it is handed, so
 * a spec can call the one a role's page held after another role opened, as
 * the page's last save does when it closes on a role switch. */
const notesSaves: ((notes: string, was: string) => Promise<unknown>)[] = [];
vi.mock("./NotesEditor", () => ({
  default: ({ onSave }: { onSave: (notes: string, was: string) => Promise<unknown> }) => {
    notesSaves.push(onSave);
    return <p>Notes page</p>;
  },
}));

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
function Posting({ initial, other, asked = null }: { initial: Job; other?: Job; asked?: RoleTab | null }) {
  const [job, setJob] = useState<Job | null>(initial);
  const [tab, setTab] = useState<RoleTab | null>(asked);
  const [, setDrawn] = useState(0);
  useEffect(() => {
    redraw = () => setDrawn((n) => n + 1);
    return () => { redraw = () => undefined; };
  }, []);
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
      <nav aria-label="Roles and tabs">
        {other && <button type="button" onClick={() => setJob(other)}>Open the other role</button>}
        {other && <button type="button" onClick={() => setJob(initial)}>Back to the first role</button>}
        <button type="button" onClick={() => setTab("posting")}>Tab: posting</button>
        <button type="button" onClick={() => setTab("workspace")}>Tab: workspace</button>
      </nav>
      <p data-testid="tab">{pipeline.tab ?? "no tabs"}</p>
      <p data-testid="notes">{job?.pursuit?.notes ?? ""}</p>
      <main aria-label="Main column">{pipeline.tab === "workspace" ? pipeline.workspace : "The posting"}</main>
      <aside aria-label="Side column" ref={setColumn}>{pipeline.section}</aside>
      <p>{pipeline.applied ? "View posting" : "View & apply"}</p>
    </>
  );
}

function renderPosting(job: JobDetail, asked: RoleTab | null = null, other?: JobDetail) {
  return render(
    <ToastProvider>
      <MemoryRouter initialEntries={["/company/openai/job/101"]}>
        <Posting initial={job} other={other} asked={asked} />
      </MemoryRouter>
    </ToastProvider>,
  );
}

const bar = () => screen.getByRole("navigation", { name: "Posting bar" });
const column = () => screen.getByRole("complementary", { name: "Side column" });
const main = () => screen.getByRole("main", { name: "Main column" });
/** The saved star in the bar: it carries the stage in its label alone. */
const stageNamed = (stage: string) => msg("applications-stage-star", { stage });
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
  appState.favVersion = 0;
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
  it("names the stage in the star's label alone, and its days in the section", async () => {
    detail = applicationDetailFixture({
      application: applicationCardFixture({ pursuit_id: 10, stage: "applied", stage_since: daysAgo(12) }),
    });
    renderPosting(posting({ is_favorite: true, pursuit: pursuit("applied") }));
    const days = await findRow(msg("applications-fact-days"));
    expect(days).toHaveTextContent(/^12 days/);
    expect(within(bar()).getByRole("button", { name: stageNamed("Applied") }), "the bar holds controls, not the stage's word")
      .toHaveTextContent("");
    expect(within(bar()).queryByText("Applied")).toBeNull();
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
    expect(booked.textContent, "when, as the application page says it, and only that").toBe(interviewWhen(interview, new Date()));
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
    expect(await within(bar()).findByRole("button", { name: stageNamed(ended) })).toBeInTheDocument();
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

describe("one write, one read", () => {
  const step = (id: number, text: string, due: string | null) => ({
    id, text, due, created_at: daysAgo(2), done_at: null,
  });
  const comment = {
    kind: "comment" as const, id: 1, created_at: daysAgo(1), actor: "user" as const, source: "app" as const,
    body: "Call went well", edited_at: null,
  };
  const appliedWith = (jobId: number, steps = [step(jobId * 10 + 1, "Email the recruiter", tomorrowNoon())]) =>
    applicationDetailFixture({
      application: applicationCardFixture({ job_id: jobId, pursuit_id: 10, stage: "applied", stage_since: daysAgo(3), steps }),
    });
  const pursuedPosting = (id: number, title: string) =>
    posting({ id, title, is_favorite: true, pursuit: { ...pursuit("applied"), job_id: id } });
  // The reads and writes here chain on promises alone, with no timer: one
  // turn of the event loop runs every step they have queued.
  const settle = () => act(async () => { await new Promise((resolve) => setTimeout(resolve, 0)); });

  it("says the workspace could not load, and Try again reads it again", async () => {
    detail = appliedWith(101);
    vi.mocked(api.application).mockRejectedValueOnce(new ApiError("down", 500));
    renderPosting(pursuedPosting(101, TITLE), "workspace");
    const failed = await within(main()).findByRole("alert");
    expect(failed).toHaveTextContent(msg("applications-ws-load-failed"));

    await userEvent.click(within(failed).getByRole("button", { name: msg("common-try-again") }));
    expect(await within(main()).findByText(msg("applications-ws-next"))).toBeInTheDocument();
    expect(within(main()).queryByRole("alert")).toBeNull();
  });

  it("says the activity could not load, never that there is none, and Try again reads it again", async () => {
    detail = appliedWith(101);
    vi.mocked(api.activity)
      .mockRejectedValueOnce(new ApiError("down", 500))
      .mockResolvedValue({ items: [comment] } as Awaited<ReturnType<typeof api.activity>>);
    renderPosting(pursuedPosting(101, TITLE), "workspace");
    const failed = await within(main()).findByRole("alert");
    expect(failed).toHaveTextContent(msg("applications-feed-load-failed"));
    expect(within(main()).queryByText(msg("applications-feed-empty"))).toBeNull();

    await userEvent.click(within(failed).getByRole("button", { name: msg("common-try-again") }));
    expect(await within(main()).findByText("Call went well")).toBeInTheDocument();
    expect(within(main()).queryByRole("alert")).toBeNull();
  });

  it("paints notes saved from the role left behind on that role alone", async () => {
    vi.mocked(api.application).mockImplementation(async (jobId) => structuredClone(appliedWith(jobId)));
    renderPosting(pursuedPosting(101, TITLE), "workspace", pursuedPosting(102, "Other role"));
    await within(main()).findByText("Notes page");
    const firstRolesSave = notesSaves[notesSaves.length - 1];

    await userEvent.click(screen.getByRole("button", { name: "Open the other role" }));
    await waitFor(() => expect(api.application).toHaveBeenCalledWith(102, expect.anything()));
    await act(async () => { await firstRolesSave("Call Sam on Friday", ""); });
    expect(api.setPursuit).toHaveBeenLastCalledWith(101, expect.objectContaining({ notes: "Call Sam on Friday" }));
    expect(screen.getByTestId("notes").textContent, "the open role keeps its own notes").toBe("");
  });

  it("reads the application once and the feed once for a pursuit write that landed", async () => {
    detail = appliedWith(101);
    renderPosting(pursuedPosting(101, TITLE), "workspace");
    await within(main()).findByText(msg("applications-ws-next"));
    await settle();
    expect(api.application).toHaveBeenCalledTimes(1);
    expect(api.activity).toHaveBeenCalledTimes(1);

    const priority = await findRow(msg("applications-fact-priority"));
    await userEvent.click(within(priority).getByRole("button"));
    const menu = await screen.findByRole("dialog", { name: msg("applications-priority-menu", { title: TITLE }) });
    await userEvent.click(within(menu).getByRole("button", { name: new RegExp(msg("applications-priority-high")) }));
    await waitFor(() => expect(appState.savedChanged).toHaveBeenCalledWith({ jobId: 101, saved: true }));
    await waitFor(() => expect(api.application).toHaveBeenCalledTimes(2));
    await settle();

    expect(api.application, "the announcement's read, and no second one by hand").toHaveBeenCalledTimes(2);
    expect(api.activity, "the feed follows the same announcement once").toHaveBeenCalledTimes(2);
  });

  it("announces an interview deleted on the posting, so the board under it reads the role again", async () => {
    const round = {
      id: 3, label: "Hiring manager", scheduled_at: tomorrowNoon(), all_day: false, format: null, link: null,
      outcome: null, notes: null, created_at: daysAgo(1), updated_at: daysAgo(1),
    };
    detail = applicationDetailFixture({
      application: applicationCardFixture({ job_id: 101, pursuit_id: 10, stage: "interviewing", stage_since: daysAgo(3) }),
      interviews: [round],
    });
    vi.mocked(api.deleteInterview).mockImplementation(async () => {
      if (detail) detail = { ...detail, interviews: [] };
      return undefined as never;
    });
    renderPosting(posting({ id: 101, title: TITLE, is_favorite: true, pursuit: { ...pursuit("interviewing"), job_id: 101 } }), "workspace");
    await userEvent.click(await within(main()).findByRole("button", {
      name: msg("applications-interview-edit-label", { label: "Hiring manager" }),
    }));
    const form = await screen.findByRole("dialog", { name: msg("applications-interview-edit-title") });
    await userEvent.click(within(form).getByRole("button", { name: msg("applications-interview-delete") }));
    await userEvent.click(within(form).getByRole("button", { name: msg("applications-comment-delete") }));

    await waitFor(() => expect(appState.savedChanged).toHaveBeenCalledWith({ jobId: 101, saved: true }));
    await settle();
    expect(api.deleteInterview).toHaveBeenCalledExactlyOnceWith(101, 3);
    expect(api.application, "the first read and the announcement's, none by hand").toHaveBeenCalledTimes(2);
  });

  it("keeps the feed on screen while it reads again after a tab toggle, instead of clearing it", async () => {
    detail = appliedWith(101);
    vi.mocked(api.activity).mockResolvedValue({ items: [comment] } as Awaited<ReturnType<typeof api.activity>>);
    renderPosting(pursuedPosting(101, TITLE), "workspace");
    expect(await within(main()).findByText("Call went well")).toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: "Tab: posting" }));
    // The next read never answers: what is on screen is the answer it had.
    vi.mocked(api.activity).mockImplementation(() => new Promise(() => undefined));
    await userEvent.click(screen.getByRole("button", { name: "Tab: workspace" }));
    await waitFor(() => expect(api.activity).toHaveBeenCalledTimes(2));
    expect(within(main()).getByText("Call went well"), "the feed is not cleared to read again").toBeInTheDocument();
  });

  it("leaves the role it did not write to alone when an Undo fails after another role was opened", async () => {
    detail = appliedWith(101, [step(1011, "Email the recruiter", tomorrowNoon()), step(1012, "Ask Sam", null)]);
    vi.mocked(api.application).mockImplementation(async (jobId) => structuredClone(jobId === 101 ? detail! : appliedWith(102)));
    vi.mocked(api.updateStep).mockResolvedValueOnce({} as Awaited<ReturnType<typeof api.updateStep>>);
    vi.mocked(api.updateStep).mockRejectedValueOnce(new ApiError("down", 500));
    renderPosting(pursuedPosting(101, TITLE), "workspace", pursuedPosting(102, "Other role"));
    await userEvent.click(await screen.findByRole("button", { name: msg("applications-upnext-done-label", { step: "Email the recruiter" }) }));
    const undo = await screen.findByRole("button", { name: msg("applications-move-undo") });
    expect(api.updateStep).toHaveBeenCalledWith(101, 1011, { done: true });

    await userEvent.click(screen.getByRole("button", { name: "Open the other role" }));
    await waitFor(() => expect(api.application).toHaveBeenCalledWith(102, expect.anything()));
    await settle();
    const before = vi.mocked(api.application).mock.calls.length;

    await userEvent.click(undo);
    expect(await screen.findByText(msg("applications-upnext-undo-failed", { title: TITLE }))).toBeInTheDocument();
    await settle();
    expect(api.application, "the open role is not read for a change made on another").toHaveBeenCalledTimes(before);
    expect(api.updateStep).toHaveBeenLastCalledWith(101, 1011, { done: false });
  });
});

describe("a role switch", () => {
  it("closes the interview form and the stage menu opened on the role left behind", async () => {
    detail = applicationDetailFixture({
      application: applicationCardFixture({ pursuit_id: 10, stage: "applied", stage_since: daysAgo(3) }),
    });
    vi.mocked(api.application).mockImplementation(async () => structuredClone(detail!));
    const other = posting({ id: 102, title: "Other role", is_favorite: true, pursuit: { ...pursuit("applied"), job_id: 102 } });
    renderPosting(posting({ is_favorite: true, pursuit: pursuit("applied") }), null, other);
    await findRow(msg("applications-posting-stage"));

    await userEvent.keyboard("i");
    await screen.findByRole("dialog", { name: msg("applications-interview-add-title") });
    await userEvent.click(screen.getByRole("button", { name: "Open the other role" }));
    await waitFor(() => expect(screen.queryByRole("dialog", { name: msg("applications-interview-add-title") }),
      "an interview form for the old role must not write against the new one").toBeNull());

    await userEvent.keyboard("m");
    await screen.findByRole("dialog", { name: msg("applications-stage-menu-label", { title: "Other role" }) });
  });

  it("closes a stage menu opened on the role left behind", async () => {
    detail = applicationDetailFixture({
      application: applicationCardFixture({ pursuit_id: 10, stage: "applied", stage_since: daysAgo(3) }),
    });
    vi.mocked(api.application).mockImplementation(async () => structuredClone(detail!));
    const other = posting({ id: 102, title: "Other role", is_favorite: true, pursuit: { ...pursuit("applied"), job_id: 102 } });
    renderPosting(posting({ is_favorite: true, pursuit: pursuit("applied") }), null, other);
    await findRow(msg("applications-posting-stage"));

    await userEvent.keyboard("m");
    await menuOf();
    await userEvent.click(screen.getByRole("button", { name: "Open the other role" }));
    await waitFor(() => expect(screen.queryByRole("dialog", { name: /stage/i })).toBeNull());
    expect(screen.queryByRole("dialog", { name: msg("applications-stage-menu-label", { title: "Other role" }) })).toBeNull();
  });

  it("leaves the interview form open on the new role when a save sent from the old one lands late", async () => {
    detail = applicationDetailFixture({
      application: applicationCardFixture({ pursuit_id: 10, stage: "applied", stage_since: daysAgo(3) }),
    });
    vi.mocked(api.application).mockImplementation(async () => structuredClone(detail!));
    let land!: () => void;
    vi.mocked(api.addInterview).mockImplementationOnce(() => new Promise((resolve) => { land = () => resolve(undefined as never); }));
    const other = posting({ id: 102, title: "Other role", is_favorite: true, pursuit: { ...pursuit("applied"), job_id: 102 } });
    renderPosting(posting({ is_favorite: true, pursuit: pursuit("applied") }), null, other);
    await findRow(msg("applications-posting-stage"));
    const form = () => screen.queryByRole("dialog", { name: msg("applications-interview-add-title") });

    await userEvent.keyboard("i");
    const first = await screen.findByRole("dialog", { name: msg("applications-interview-add-title") });
    const today = within(first).getAllByRole("button").find((day) => day.getAttribute("aria-current") === "date")!;
    await userEvent.click(today);
    await userEvent.click(within(first).getByRole("button", { name: msg("applications-interview-add") }));
    await waitFor(() => expect(api.addInterview).toHaveBeenCalledTimes(1));
    expect(vi.mocked(api.addInterview).mock.calls[0][0], "the save is the first role's").toBe(101);

    await userEvent.click(screen.getByRole("button", { name: "Open the other role" }));
    await waitFor(() => expect(form()).toBeNull());
    await userEvent.keyboard("i");
    await screen.findByRole("dialog", { name: msg("applications-interview-add-title") });

    await act(async () => land());
    // The save chains on promises alone: one turn of the event loop ends it.
    await act(async () => { await new Promise((resolve) => setTimeout(resolve, 0)); });
    expect(form(), "the first role's save closes only its own form").not.toBeNull();
  });

  it("opens no form left open on a role when the person comes back to it", async () => {
    detail = applicationDetailFixture({
      application: applicationCardFixture({ pursuit_id: 10, stage: "applied", stage_since: daysAgo(3) }),
    });
    vi.mocked(api.application).mockImplementation(async () => structuredClone(detail!));
    const other = posting({ id: 102, title: "Other role", is_favorite: true, pursuit: { ...pursuit("applied"), job_id: 102 } });
    renderPosting(posting({ is_favorite: true, pursuit: pursuit("applied") }), null, other);
    await findRow(msg("applications-posting-stage"));

    await userEvent.keyboard("i");
    await screen.findByRole("dialog", { name: msg("applications-interview-add-title") });
    await userEvent.click(screen.getByRole("button", { name: "Open the other role" }));
    await waitFor(() => expect(screen.queryByRole("dialog", { name: msg("applications-interview-add-title") })).toBeNull());
    await userEvent.click(screen.getByRole("button", { name: "Back to the first role" }));
    await findRow(msg("applications-posting-stage"));
    expect(screen.queryByRole("dialog", { name: msg("applications-interview-add-title") }), "a form left behind stays closed").toBeNull();
  });
});

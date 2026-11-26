import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { Filters, JobList, PassedOver, RemovedPicks } from "../../api";
import { number } from "../../copy/format";
import { jobFixture } from "../../test/fixtures";
import { msg } from "../../test/msg";
import { ToastProvider } from "../../ui";
import { PassedOverScreen } from "./PassedOverScreen";

const picksPassed = vi.fn<() => Promise<PassedOver>>();
const picksRemoved = vi.fn<() => Promise<RemovedPicks>>();
const jobs = vi.fn<(filters: Filters) => Promise<JobList>>();
const undismissJob = vi.fn<(id: number) => Promise<unknown>>();
const setFavorite = vi.fn<(id: number, on: boolean) => Promise<unknown>>();
vi.mock("../../api", async (importOriginal) => ({
  ...(await importOriginal<typeof import("../../api")>()),
  api: {
    picksPassed: () => picksPassed(),
    picksRemoved: () => picksRemoved(),
    jobs: (filters: Filters) => jobs(filters),
    undismissJob: (id: number) => undismissJob(id),
    setFavorite: (id: number, on: boolean) => setFavorite(id, on),
  },
}));

const openJob = vi.fn();
vi.mock("../../context/JobWorkspace", () => ({
  useJobWorkspace: () => ({ viewedIds: new Set(), compareIds: new Set(), compareFull: false, compareCap: 4 }),
  useJobActions: () => ({ openJob, toggleCompare: vi.fn() }),
}));

const role = (id: number, title: string, company = "stripe"): JobList["items"][number] => ({ ...jobFixture, id, title, company, viewed_at: null });
const ROLES = [
  role(1, "Principal Product Manager, Platform", "linear"),
  role(2, "Staff Product Manager, Search"),
  role(11, "Group Product Manager, Enterprise", "notion"),
  role(12, "Staff Product Manager, Observability", "datadog"),
  role(13, "Principal Product Manager, AI", "notion"),
  role(14, "Staff Product Manager, Issues", "linear"),
];

const removedPick = (job_id: number, reason: string | null, reason_text: string | null = null): RemovedPicks["picks"][number] => ({
  job_id, title: ROLES.find((r) => r.id === job_id)!.title, company: "Linear", company_slug: "linear", is_open: true,
  reasons: [], reason, reason_text, removed_at: "2026-11-25T10:00:00Z", judged_at: "2026-11-25T08:00:00Z",
});

const nearMiss = (job_id: number, opening: string, rest: string) => ({
  job_id, reason: { opening, rest }, judged_at: "2026-11-25T08:00:00Z",
});

function passedOver(over: Partial<PassedOver> = {}): PassedOver {
  return {
    passed_this_week: 8,
    near_misses: [
      nearMiss(11, "Mostly people management", ", eight reports and little product work."),
      nearMiss(12, "Infrastructure", ", further from customers than you asked for."),
      nearMiss(13, "Base around 240,000", ", close to your floor."),
      nearMiss(14, "Same level as today", ", with a smaller product."),
    ],
    passes: [{ code: "hard_rule", count: 2 }, { code: "below_level", count: 1 }, { code: "off_direction", count: 1 }],
    judged_rules: ["No on-call"],
    ruled_out: 2,
    ruled_out_by_rule: [{ rule: "Base under 200,000", count: 2 }],
    ...over,
  };
}

beforeEach(() => {
  picksPassed.mockReset().mockResolvedValue(passedOver());
  picksRemoved.mockReset().mockResolvedValue({ picks: [] });
  jobs.mockReset().mockImplementation(async (filters) => {
    const items = ROLES.filter((r) => filters.ids?.includes(r.id));
    return { total: items.length, limit: 25, offset: 0, items };
  });
  undismissJob.mockReset().mockResolvedValue({});
  setFavorite.mockReset().mockResolvedValue({});
  openJob.mockReset();
});

function renderPage() {
  return render(
    <MemoryRouter initialEntries={["/top-picks/passed"]}>
      <ToastProvider>
        <PassedOverScreen />
      </ToastProvider>
    </MemoryRouter>,
  );
}

/** The page's parts, by the name each is given. */
const headings = () => screen.queryAllByRole("region").map((part) => part.getAttribute("aria-labelledby"))
  .map((id) => document.getElementById(id!)?.textContent);
const rowTitles = (region: HTMLElement) => [...region.querySelectorAll(".job-title")].map((t) => t.textContent);

describe("PassedOverScreen", () => {
  it("names the page in one heading that takes no room, and gives the week's count with the way back", async () => {
    renderPage();
    const title = screen.getByRole("heading", { level: 1, name: msg("picks-passed-heading") });
    expect(title).toHaveClass("sr-only");
    expect(await screen.findByText(msg("picks-passed-summary", { count: 8 }))).toBeVisible();
    expect(screen.getByRole("link", { name: msg("picks-passed-back") })).toHaveAttribute("href", "/top-picks");
  });

  it("reads the removed picks and the near misses by id, whatever their status", async () => {
    picksRemoved.mockResolvedValue({ picks: [removedPick(1, "pay_too_low")] });
    renderPage();
    await screen.findByText(msg("picks-passed-summary", { count: 8 }));
    expect(jobs).toHaveBeenCalledOnce();
    const filters = jobs.mock.calls[0][0];
    expect(filters.ids).toEqual([1, 11, 12, 13, 14]);
    expect(filters.status).toBe("");
  });

  it("lists what the person removed first, then what came close, then the tallies", async () => {
    picksRemoved.mockResolvedValue({ picks: [removedPick(1, "pay_too_low")] });
    renderPage();
    await screen.findByText(msg("picks-passed-summary", { count: 8 }));
    expect(headings()).toEqual([
      msg("picks-passed-removed", { count: 1 }),
      msg("picks-passed-close", { count: 4 }),
      msg("picks-passed-read", { count: 4 }),
      msg("picks-passed-ruled", { count: 2 }),
    ]);
    // Short lists under their own heads: no column head over the rows.
    expect(document.querySelector(".list-head")).toBeNull();
  });

  it("says why the person removed each pick, in their words when they gave them", async () => {
    picksRemoved.mockResolvedValue({ picks: [
      removedPick(1, "pay_too_low", "Below what I make now"),
      removedPick(2, "other"),
    ] });
    renderPage();
    const removed = await screen.findByRole("region", { name: msg("picks-passed-removed", { count: 2 }) });
    const [first, second] = removed.querySelectorAll(".passed-said");
    expect(first).toHaveTextContent(
      `${msg("picks-passed-said", { reason: "pay_too_low" })} ${msg("picks-passed-words", { words: "Below what I make now" })} ${msg("picks-passed-put-back")}`,
    );
    // Something else with no words says nothing but the way back.
    expect(second.textContent).toBe(msg("picks-passed-put-back"));
    // The person's words are theirs: content, never translated.
    expect(within(first as HTMLElement).getByText("Below what I make now")).toHaveAttribute("data-copy", "content");
  });

  it("names every reason code a dismissal can store in words of its own, none of them the catch-all", () => {
    const codes = ["pay_too_low", "wrong_level", "wrong_role", "company", "wrong_place", "wrong_domain"];
    const said = codes.map((reason) => msg("picks-passed-said", { reason }));
    expect(new Set(said).size).toBe(codes.length);
    expect(said).not.toContain(msg("picks-passed-said", { reason: "unknown" }));
  });

  it("says a reason given elsewhere than the question in its own words", async () => {
    picksRemoved.mockResolvedValue({ picks: [removedPick(1, "wrong_domain")] });
    renderPage();
    const removed = await screen.findByRole("region", { name: msg("picks-passed-removed", { count: 1 }) });
    expect(removed.querySelector(".passed-said")?.textContent).toBe(
      `${msg("picks-passed-said", { reason: "wrong_domain" })} ${msg("picks-passed-put-back")}`,
    );
  });

  it("saves a role from the page, and puts the star back and says so when the save fails", async () => {
    setFavorite.mockRejectedValue(new Error("engine away"));
    renderPage();
    const close = await screen.findByRole("region", { name: msg("picks-passed-close", { count: 4 }) });
    const star = within(close).getAllByRole("button", { name: msg("jobs-save") })[0];
    await userEvent.click(star);
    expect(setFavorite).toHaveBeenCalledExactlyOnceWith(11, true);
    const status = await screen.findByRole("status");
    expect(status).toHaveTextContent(msg("radar-save-failed", { title: "Group Product Manager, Enterprise" }));
    expect(within(status).getByText("Group Product Manager, Enterprise")).toHaveAttribute("data-copy", "content");
    expect(star).toHaveAttribute("aria-pressed", "false");
  });

  it("leaves the star as the server holds it when a save and its undo both fail", async () => {
    const pending: Array<(error: Error) => void> = [];
    setFavorite.mockImplementation(() => new Promise((_, reject) => { pending.push(reject); }));
    renderPage();
    const close = await screen.findByRole("region", { name: msg("picks-passed-close", { count: 4 }) });
    const star = within(close).getAllByRole("button", { name: msg("jobs-save") })[0];
    await userEvent.click(star);
    await userEvent.click(star);
    expect(star).toHaveAttribute("aria-pressed", "false");
    // The undo waits for the save: one write at a time for a role.
    expect(pending).toHaveLength(1);
    pending[0](new Error("engine away"));
    await vi.waitFor(() => expect(pending).toHaveLength(2));
    expect(setFavorite.mock.calls).toEqual([[11, true], [11, false]]);
    pending[1](new Error("engine away"));
    expect(await screen.findByRole("status")).toHaveTextContent(
      msg("radar-unsave-failed", { title: "Group Product Manager, Enterprise" }),
    );
    expect(star).toHaveAttribute("aria-pressed", "false");
  });

  it("puts a removed pick back, and takes it off the page", async () => {
    picksRemoved.mockResolvedValue({ picks: [removedPick(1, "wrong_level")] });
    renderPage();
    const removed = await screen.findByRole("region", { name: msg("picks-passed-removed", { count: 1 }) });
    await userEvent.click(within(removed).getByRole("button", { name: msg("picks-passed-put-back") }));
    expect(undismissJob).toHaveBeenCalledExactlyOnceWith(1);
    await vi.waitFor(() => expect(screen.queryByRole("region", { name: msg("picks-passed-removed", { count: 1 }) })).toBeNull());
    // Putting it back does not open the role.
    expect(openJob).not.toHaveBeenCalled();
  });

  it("keeps a pick that could not be put back, and says so", async () => {
    undismissJob.mockRejectedValue(new Error("engine away"));
    picksRemoved.mockResolvedValue({ picks: [removedPick(1, "wrong_level")] });
    renderPage();
    const removed = await screen.findByRole("region", { name: msg("picks-passed-removed", { count: 1 }) });
    await userEvent.click(within(removed).getByRole("button", { name: msg("picks-passed-put-back") }));
    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent(msg("picks-passed-put-back-failed", { title: "Principal Product Manager, Platform" }));
    // The role's title is the employer's: content inside the sentence.
    expect(within(alert).getByText("Principal Product Manager, Platform")).toHaveAttribute("data-copy", "content");
    expect(rowTitles(removed)).toEqual(["Principal Product Manager, Platform"]);
  });

  it("shows the first three near misses, each with what failed, and the rest on Show all", async () => {
    renderPage();
    const close = await screen.findByRole("region", { name: msg("picks-passed-close", { count: 4 }) });
    expect(rowTitles(close)).toEqual([
      "Group Product Manager, Enterprise", "Staff Product Manager, Observability", "Principal Product Manager, AI",
    ]);
    expect(within(close).getByText("Mostly people management")).toHaveClass("pick-reason-opening");
    await userEvent.click(within(close).getByRole("button", { name: msg("picks-passed-show-all", { count: 4 }) }));
    expect(rowTitles(close)).toHaveLength(4);
    expect(within(close).queryByRole("button", { name: msg("picks-passed-show-all", { count: 4 }) })).toBeNull();
  });

  it("offers no Show all for three near misses or fewer", async () => {
    picksPassed.mockResolvedValue(passedOver({ near_misses: passedOver().near_misses.slice(0, 3) }));
    renderPage();
    const close = await screen.findByRole("region", { name: msg("picks-passed-close", { count: 3 }) });
    expect(rowTitles(close)).toHaveLength(3);
    expect(within(close).queryByRole("button", { name: /Show all/ })).toBeNull();
  });

  it("opens a row's role from the page", async () => {
    renderPage();
    const close = await screen.findByRole("region", { name: msg("picks-passed-close", { count: 4 }) });
    await userEvent.click(within(close).getByText("Group Product Manager, Enterprise"));
    expect(openJob).toHaveBeenCalledWith(11, "notion");
  });

  it("tallies the passes by why, naming the rules only reading can check", async () => {
    picksPassed.mockResolvedValue(passedOver({ judged_rules: ["No on-call", "No travel"] }));
    renderPage();
    const read = await screen.findByRole("region", { name: msg("picks-passed-read", { count: 4 }) });
    expect(within(read).getAllByRole("listitem").map((line) => line.textContent)).toEqual([
      `${msg("picks-pass-hard-rule-named", { rules: "No on-call or No travel" })}2`,
      `${msg("picks-pass-below-level")}1`,
      `${msg("picks-pass-off-direction")}1`,
    ]);
    expect(within(read).getByText("No on-call or No travel")).toHaveAttribute("data-copy", "content");
  });

  it("writes each tally's count for the reader's region", async () => {
    picksPassed.mockResolvedValue(passedOver({
      passes: [{ code: "below_level", count: 12345 }],
      ruled_out: 2345, ruled_out_by_rule: [{ rule: "Not Google", count: 2345 }],
    }));
    renderPage();
    const read = await screen.findByRole("region", { name: msg("picks-passed-read", { count: 12345 }) });
    expect(within(read).getByRole("listitem")).toHaveTextContent(`${msg("picks-pass-below-level")}${number(12345)}`);
    const ruled = screen.getByRole("region", { name: msg("picks-passed-ruled", { count: 2345 }) });
    expect(within(ruled).getByRole("listitem").textContent).toBe(`Not Google${number(2345)}`);
    expect(number(12345)).toBe("12,345");
  });

  it("says a hard rule was broken without naming one when the brief has none only reading checks", async () => {
    picksPassed.mockResolvedValue(passedOver({ judged_rules: [] }));
    renderPage();
    const read = await screen.findByRole("region", { name: msg("picks-passed-read", { count: 4 }) });
    expect(within(read).getAllByRole("listitem")[0]).toHaveTextContent(`${msg("picks-pass-hard-rule")}2`);
  });

  it("lists what each checkable rule ruled out before any reading", async () => {
    picksPassed.mockResolvedValue(passedOver({
      ruled_out: 5, ruled_out_by_rule: [{ rule: "Base under 200,000", count: 3 }, { rule: "Not Google", count: 2 }],
    }));
    renderPage();
    const ruled = await screen.findByRole("region", { name: msg("picks-passed-ruled", { count: 5 }) });
    expect(within(ruled).getAllByRole("listitem").map((line) => line.textContent)).toEqual([
      "Base under 200,0003", "Not Google2",
    ]);
    expect(within(ruled).getByText("Not Google")).toHaveAttribute("data-copy", "content");
  });

  it("leaves out each part that has nothing in it", async () => {
    picksPassed.mockResolvedValue(passedOver({ passed_this_week: 1, near_misses: [], passes: [{ code: "not_real", count: 1 }], ruled_out: 0, ruled_out_by_rule: [] }));
    renderPage();
    await screen.findByText(msg("picks-passed-summary", { count: 1 }));
    expect(headings()).toEqual([msg("picks-passed-read", { count: 1 })]);
    expect(jobs).not.toHaveBeenCalled();
  });

  it("says nothing was passed over when nothing was, with the way back and no count", async () => {
    picksPassed.mockResolvedValue(passedOver({ passed_this_week: 0, near_misses: [], passes: [], ruled_out: 0, ruled_out_by_rule: [] }));
    renderPage();
    expect(await screen.findByText(msg("picks-passed-empty-title"))).toBeVisible();
    expect(screen.getByText(msg("picks-passed-empty"))).toBeVisible();
    expect(screen.getByRole("link", { name: msg("picks-passed-back") })).toBeVisible();
    expect(screen.queryByText(/^\d+ roles? passed over this week$/)).toBeNull();
  });

  it("says the read failed in place of the page", async () => {
    picksPassed.mockRejectedValue(new Error("engine away"));
    renderPage();
    expect(await screen.findByText(msg("picks-passed-load-failed"))).toBeVisible();
    expect(headings()).toEqual([]);
  });
});

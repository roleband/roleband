import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { Filters, JobList, PassedOver } from "../../api";
import { number } from "../../copy/format";
import { jobFixture } from "../../test/fixtures";
import { msg } from "../../test/msg";
import { ToastProvider } from "../../ui";
import { PassedOverScreen } from "./PassedOverScreen";

const picksPassed = vi.fn<() => Promise<PassedOver>>();
const jobs = vi.fn<(filters: Filters) => Promise<JobList>>();
const setFavorite = vi.fn<(id: number, on: boolean) => Promise<unknown>>();
vi.mock("../../api", async (importOriginal) => ({
  ...(await importOriginal<typeof import("../../api")>()),
  api: {
    picksPassed: () => picksPassed(),
    jobs: (filters: Filters) => jobs(filters),
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
  role(11, "Group Product Manager, Enterprise", "notion"),
  role(12, "Staff Product Manager, Observability", "datadog"),
  role(13, "Principal Product Manager, AI", "notion"),
  role(14, "Staff Product Manager, Issues", "linear"),
];

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
  jobs.mockReset().mockImplementation(async (filters) => {
    const items = ROLES.filter((r) => filters.ids?.includes(r.id));
    return { total: items.length, limit: 25, offset: 0, items };
  });
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

  it("reads the near misses by id, whatever their status", async () => {
    renderPage();
    await screen.findByText(msg("picks-passed-summary", { count: 8 }));
    expect(jobs).toHaveBeenCalledOnce();
    const filters = jobs.mock.calls[0][0];
    expect(filters.ids).toEqual([11, 12, 13, 14]);
    expect(filters.status).toBe("");
  });

  it("lists what came close, then the tallies, and nothing the person removed", async () => {
    renderPage();
    await screen.findByText(msg("picks-passed-summary", { count: 8 }));
    expect(headings()).toEqual([
      msg("picks-passed-close", { count: 4 }),
      msg("picks-passed-read", { count: 4 }),
      msg("picks-passed-ruled", { count: 2 }),
    ]);
    // The picks the person removed live on Top picks' Not for me: no way back is offered here.
    expect(screen.queryByRole("button", { name: msg("picks-removed-put-back") })).toBeNull();
    // Short lists under their own heads: no column head over the rows.
    expect(document.querySelector(".list-head")).toBeNull();
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

import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { api, type ApplicationCalendarItem, type ApplicationCard } from "../../api";
import { applicationCardFixture } from "../../test/fixtures";
import { msg } from "../../test/msg";
import { UpNextMonth } from "./UpNextMonth";

/* The month beside Up next: a day says what falls on it, picking it lists
 * that day's items under the grid, past days included, the arrows walk the
 * days and cross into the next month, a month reads only its own span, and
 * the view's filter drops a role from the month as it does from the list. */

vi.mock("../../api", async (importOriginal) => ({
  ...(await importOriginal<typeof import("../../api")>()),
  api: { calendar: vi.fn() },
}));
const calendar = vi.mocked(api.calendar);

const now = new Date(2026, 10, 4, 10, 0);
const openai = applicationCardFixture({ job_id: 1, title: "Staff Product Manager, API", company: "openai" });
const stripe = applicationCardFixture({
  job_id: 2, pursuit_id: 20, stage: "interviewing", title: "Principal Engineering Manager", company: "stripe",
});
const cards: ApplicationCard[] = [openai, stripe];

const interview = (jobId: number, at: Date, label: string, outcome: "passed" | null = null): ApplicationCalendarItem => ({
  kind: "interview", job_id: jobId, at: at.toISOString(), interview_id: at.getTime() % 100000, label,
  all_day: false, format: "video", outcome,
});
const step = (jobId: number, at: Date, text: string): ApplicationCalendarItem => ({
  kind: "step", job_id: jobId, at: at.toISOString(), step: text,
});

const items = [
  interview(2, new Date(2026, 10, 2, 15, 0), "Recruiter screen", "passed"),
  interview(2, new Date(2026, 10, 6, 14, 0), "Hiring manager"),
  step(1, new Date(2026, 10, 6, 23, 59), "Send references"),
  // A role the board does not show: never drawn.
  interview(99, new Date(2026, 10, 9, 9, 0), "Someone else's round"),
];

function renderMonth(keep: (card: ApplicationCard) => { shown: boolean; match?: boolean } = () => ({ shown: true })) {
  const onPickDay = vi.fn();
  render(
    <MemoryRouter>
      <UpNextMonth cards={cards} now={now} keep={keep} onPickDay={onPickDay} />
    </MemoryRouter>,
  );
  return { onPickDay };
}

const day = (name: RegExp) => screen.getByRole("button", { name });
const picked = () => screen.getByRole("heading", { level: 3 }).parentElement!;

beforeEach(() => {
  calendar.mockReset();
  calendar.mockResolvedValue({ items });
});

describe("UpNextMonth", () => {
  it("names what falls on each day, and draws nothing for a role off the board", async () => {
    renderMonth();
    await waitFor(() => expect(day(/^Fri, Nov 6: /)).toBeInTheDocument());
    expect(day(/^Fri, Nov 6: /)).toHaveAccessibleName(
      `Fri, Nov 6: ${msg("applications-month-interviews", { count: 1 })} and ${msg("applications-month-steps", { count: 1 })}`,
    );
    expect(day(/^Mon, Nov 2: /)).toHaveAccessibleName(`Mon, Nov 2: ${msg("applications-month-interviews", { count: 1 })}`);
    // The round on the 9th belongs to a role the board does not show.
    expect(day(/^Mon, Nov 9$/)).toBeInTheDocument();
  });

  it("opens on today, picked, and reads the grid's whole span once", async () => {
    renderMonth();
    await waitFor(() => expect(calendar).toHaveBeenCalledTimes(1));
    const [start, end] = calendar.mock.calls[0];
    expect(start).toEqual(new Date(2026, 9, 26));
    expect(end).toEqual(new Date(2026, 11, 7));
    expect(day(/^Wed, Nov 4/)).toHaveAttribute("aria-pressed", "true");
    expect(day(/^Wed, Nov 4/)).toHaveAttribute("aria-current", "date");
    expect(within(picked()).getByText(msg("applications-month-day-empty"))).toBeInTheDocument();
  });

  it("lists a picked day's items under the grid, a past round with its outcome, and tells the list", async () => {
    const user = userEvent.setup();
    const { onPickDay } = renderMonth();
    await waitFor(() => expect(day(/^Mon, Nov 2: /)).toBeInTheDocument());

    await user.click(day(/^Mon, Nov 2: /));

    expect(day(/^Mon, Nov 2: /)).toHaveAttribute("aria-pressed", "true");
    expect(day(/^Wed, Nov 4/)).toHaveAttribute("aria-pressed", "false");
    const list = within(picked());
    expect(list.getByText(msg("applications-upnext-interview", { label: "Recruiter screen" }))).toBeInTheDocument();
    expect(list.getByText(msg("applications-interview-outcome-passed"))).toBeInTheDocument();
    expect(list.getByRole("link", { name: /Principal Engineering Manager/ })).toHaveAttribute("href", "/pipeline/2");
    expect(onPickDay).toHaveBeenCalledWith(new Date(2026, 10, 2));
  });

  it("walks the days with the arrows, one Tab stop at a time, into the next month", async () => {
    const user = userEvent.setup();
    const { onPickDay } = renderMonth();
    await waitFor(() => expect(day(/^Wed, Nov 4/)).toHaveAttribute("tabindex", "0"));
    expect(screen.getAllByRole("button").filter((b) => b.dataset.day && b.tabIndex === 0)).toHaveLength(1);

    day(/^Wed, Nov 4/).focus();
    await user.keyboard("{ArrowRight}{ArrowRight}");
    expect(day(/^Fri, Nov 6: /)).toHaveFocus();
    expect(within(picked()).getByText(msg("applications-upnext-step", { step: "Send references" }))).toBeInTheDocument();

    // Four weeks down from the 6th is 4 December: the grid turns the page.
    await user.keyboard("{ArrowDown}{ArrowDown}{ArrowDown}{ArrowDown}");
    await waitFor(() => expect(screen.getByRole("heading", { level: 2 })).toHaveTextContent("December 2026"));
    await waitFor(() => expect(day(/^Fri, Dec 4/)).toHaveFocus());
    expect(calendar).toHaveBeenLastCalledWith(new Date(2026, 10, 30), new Date(2027, 0, 4), expect.anything());
    // Walking is not picking: the list is not scrolled on every step.
    expect(onPickDay).not.toHaveBeenCalled();
  });

  it("pages months with its buttons, and Today comes back", async () => {
    const user = userEvent.setup();
    renderMonth();
    await waitFor(() => expect(calendar).toHaveBeenCalledTimes(1));

    await user.click(screen.getByRole("button", { name: msg("applications-month-prev") }));
    expect(screen.getByRole("heading", { level: 2 })).toHaveTextContent("October 2026");
    await waitFor(() => expect(calendar).toHaveBeenLastCalledWith(new Date(2026, 8, 28), new Date(2026, 10, 2), expect.anything()));

    await user.click(screen.getByRole("button", { name: msg("applications-month-today") }));
    expect(screen.getByRole("heading", { level: 2 })).toHaveTextContent("November 2026");
    expect(day(/^Wed, Nov 4/)).toHaveAttribute("aria-pressed", "true");
  });

  it("drops a role the view's filter leaves out, from the days and the picked list", async () => {
    const user = userEvent.setup();
    renderMonth((card) => ({ shown: card.job_id !== 2 }));
    await waitFor(() => expect(day(/^Fri, Nov 6: /)).toBeInTheDocument());

    expect(day(/^Fri, Nov 6: /)).toHaveAccessibleName(`Fri, Nov 6: ${msg("applications-month-steps", { count: 1 })}`);
    expect(day(/^Mon, Nov 2$/)).toBeInTheDocument();
    await user.click(day(/^Fri, Nov 6: /));
    expect(within(picked()).queryByText(msg("applications-upnext-interview", { label: "Hiring manager" }))).toBeNull();
  });

  it("says so when the month cannot load, and keeps its grid", async () => {
    calendar.mockRejectedValue(new Error("offline"));
    renderMonth();

    expect(await screen.findByRole("alert")).toHaveTextContent(msg("applications-month-failed"));
    expect(day(/^Wed, Nov 4/)).toBeInTheDocument();
  });
});

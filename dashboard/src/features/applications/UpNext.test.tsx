import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useState } from "react";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { api, type ApplicationBoard, type ApplicationCard } from "../../api";
import type { AsyncResource } from "../../hooks/useAsyncResource";
import { applicationCardFixture, stepFixture } from "../../test/fixtures";
import { msg } from "../../test/msg";
import * as dueByDay from "./dueByDay";
import { UpNext } from "./UpNext";

/* Up next beside its month: every dated row has its own key, so two steps of
 * one role on one day are two rows; the day picked is Up next's own, today
 * from the first paint, so the grid and the list never disagree about it; and
 * the grouping of the board is worked out once per board and clock. */

vi.mock("../../api", async (importOriginal) => ({
  ...(await importOriginal<typeof import("../../api")>()),
  api: { calendar: vi.fn() },
}));
vi.mock("../../context/MissionState", () => ({ useMissionActions: () => ({ screenSearchRef: { current: null } }) }));
vi.mock("./dueByDay", async (importOriginal) => {
  const real = await importOriginal<typeof import("./dueByDay")>();
  return { ...real, upNext: vi.fn(real.upNext) };
});

const now = new Date(2026, 10, 4, 10, 0);
const today = new Date(2026, 10, 4, 23, 59).toISOString();

const openai = applicationCardFixture({
  job_id: 1,
  stage: "applied",
  title: "Staff Product Manager, API",
  steps: [
    stepFixture({ id: 11, text: "Send references", due: today }),
    stepFixture({ id: 12, text: "Book the flight", due: today }),
  ],
});
const stripe = applicationCardFixture({
  job_id: 2,
  pursuit_id: 20,
  stage: "interviewing",
  title: "Principal Engineering Manager",
  company: "stripe",
  next_interview: {
    id: 5, label: "Hiring manager", scheduled_at: new Date(2026, 10, 6, 14, 0).toISOString(),
    all_day: false, format: "video", link: null,
  },
});

const resource = (applications: ApplicationCard[]): AsyncResource<ApplicationBoard> => ({
  data: { applications },
  error: null,
  loading: false,
  refreshing: false,
  refreshError: null,
  mutate: vi.fn(),
  retry: vi.fn(),
  refresh: vi.fn(),
} as unknown as AsyncResource<ApplicationBoard>);

/** A role whose round has taken place and waits for its outcome. */
const awaiting = (job_id: number, id: number, label: string, day: number) =>
  applicationCardFixture({
    job_id,
    pursuit_id: job_id * 10,
    stage: "interviewing",
    title: `${label} role`,
    awaiting_outcome: {
      id, label, scheduled_at: new Date(2026, 10, day, 14, 0).toISOString(), all_day: false, format: null, link: null,
    },
  });

/** Up next over a board that drops a step when it is ticked, and a round
 *  once its outcome is set, as the page's does. */
function Page({ cards }: { cards: ApplicationCard[] }) {
  const [board, setBoard] = useState(cards);
  const [, tick] = useState(0);
  const change = (card: ApplicationCard, edit: (card: ApplicationCard) => ApplicationCard) =>
    setBoard((was) => was.map((one) => (one.job_id === card.job_id ? edit(one) : one)));
  return (
    <MemoryRouter>
      <button onClick={() => tick((n) => n + 1)}>again</button>
      <UpNext
        resource={resource(board)}
        now={now}
        actions={{
          onFinishStep: (card, step) => change(card, (one) => ({ ...one, steps: one.steps.filter((s) => s.id !== step.id) })),
          onSetOutcome: (card) => change(card, (one) => ({ ...one, awaiting_outcome: null })),
        }}
      />
    </MemoryRouter>
  );
}

const rows = () => screen.getAllByRole("listitem").filter((row) => row.classList.contains("app-upnext-item"));
const tickOf = (step: string) => screen.getByRole("button", { name: msg("applications-upnext-done-label", { step }) });

beforeEach(() => {
  // jsdom has no layout: the scroll a pick asks for is a stub.
  Element.prototype.scrollIntoView = vi.fn();
  vi.mocked(api.calendar).mockReset();
  vi.mocked(api.calendar).mockResolvedValue({ items: [] });
  vi.mocked(dueByDay.upNext).mockClear();
});

describe("Up next", () => {
  it("leaves a ticked step out of the month while the month reads again", async () => {
    const user = userEvent.setup();
    const step = (id: number, text: string) => ({ kind: "step" as const, job_id: 1, at: today, step: text, step_id: id });
    vi.mocked(api.calendar)
      .mockResolvedValueOnce({ items: [step(11, "Send references"), step(12, "Book the flight")] })
      // The month's next read never answers: what it shows is the first answer.
      .mockImplementation(() => new Promise(() => undefined));
    render(<Page cards={[openai]} />);
    const month = screen.getByRole("region", { name: msg("applications-month-label") });
    const day = () => within(month).getByRole("button", { name: /^Wed, Nov 4/ });
    await waitFor(() => expect(day()).toHaveAccessibleName(new RegExp(msg("applications-month-steps", { count: 2 }))));

    await user.click(tickOf("Send references"));

    expect(api.calendar, "the month reads again").toHaveBeenCalledTimes(2);
    expect(within(month).queryByText(/Send references/), "the ticked step is not listed beside Up next").toBeNull();
    expect(day()).toHaveAccessibleName(new RegExp(msg("applications-month-steps", { count: 1 })));
  });

  it("lists two steps of one role on one day as two rows, and ticking one leaves the other", async () => {
    const user = userEvent.setup();
    const errors = vi.spyOn(console, "error").mockImplementation(() => {});
    render(<Page cards={[openai]} />);
    expect(tickOf("Send references")).toBeInTheDocument();
    expect(tickOf("Book the flight")).toBeInTheDocument();

    await user.click(tickOf("Send references"));

    expect(screen.queryByRole("button", { name: msg("applications-upnext-done-label", { step: "Send references" }) })).toBeNull();
    expect(tickOf("Book the flight")).toBeInTheDocument();
    expect(errors.mock.calls.flat().join(" ")).not.toMatch(/same key/);
    errors.mockRestore();
  });

  it("marks today's rows from the first paint, matching the grid's pressed day", () => {
    render(<Page cards={[openai, stripe]} />);
    const marked = rows().filter((row) => row.hasAttribute("data-picked"));
    expect(marked.map((row) => within(row).getByRole("button").getAttribute("aria-label"))).toEqual([
      msg("applications-upnext-done-label", { step: "Send references" }),
      msg("applications-upnext-done-label", { step: "Book the flight" }),
    ]);
    expect(screen.getByRole("button", { name: /^Wed, Nov 4/ })).toHaveAttribute("aria-pressed", "true");
  });

  it("offers a round to come as a file for the person's calendar, naming its role", async () => {
    const files: Blob[] = [];
    URL.createObjectURL = vi.fn((file: Blob) => {
      files.push(file);
      return "blob:calendar";
    });
    URL.revokeObjectURL = vi.fn();
    const click = vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(() => {});
    render(<Page cards={[openai, stripe]} />);
    await userEvent.click(screen.getByRole("button", { name: msg("applications-interview-calendar-label", { label: "Hiring manager" }) }));
    expect(files).toHaveLength(1);
    const body = await files[0].text();
    expect(body).toContain("UID:interview-5@roleband");
    expect(body.replace(/\r\n /g, "")).toContain("Principal Engineering Manager");
    click.mockRestore();
  });

  it("moves the mark to the day picked in the month", async () => {
    const user = userEvent.setup();
    render(<Page cards={[openai, stripe]} />);

    await user.click(screen.getByRole("button", { name: /^Fri, Nov 6/ }));

    const marked = rows().filter((row) => row.hasAttribute("data-picked"));
    expect(marked).toHaveLength(1);
    expect(marked[0]).toHaveTextContent("Hiring manager");
    expect(screen.getByRole("button", { name: /^Wed, Nov 4/ })).toHaveAttribute("aria-pressed", "false");
  });

  it("hands the keyboard to the next row when a tick takes its row away, else to the row before", async () => {
    const user = userEvent.setup();
    const { unmount } = render(<Page cards={[openai]} />);
    tickOf("Send references").focus();
    await user.keyboard("{Enter}");
    expect(tickOf("Book the flight")).toHaveFocus();
    unmount();

    render(<Page cards={[openai]} />);
    tickOf("Book the flight").focus();
    await user.keyboard("{Enter}");
    expect(tickOf("Send references")).toHaveFocus();
  });

  it("hands the keyboard to the next row when an outcome takes its round away", async () => {
    const user = userEvent.setup();
    render(<Page cards={[awaiting(3, 7, "Panel", 2), awaiting(4, 8, "Onsite", 3)]} />);
    // A past round asks once; the three outcomes open from the question.
    const panel = rows().find((row) => row.textContent?.includes("Panel"))!;
    expect(within(panel).getAllByRole("button"), "one question, not three buttons").toHaveLength(1);
    await user.click(within(panel).getByRole("button", { name: msg("applications-ws-ask-outcome") }));
    const outcomes = await screen.findByRole("dialog", { name: msg("applications-upnext-outcome-label", { label: "Panel" }) });
    expect(within(outcomes).getAllByRole("button").map((one) => one.textContent)).toEqual([
      msg("applications-interview-outcome-passed"),
      msg("applications-interview-outcome-not-passed"),
      msg("applications-interview-outcome-cancelled"),
    ]);
    await user.click(within(outcomes).getByRole("button", { name: msg("applications-interview-outcome-passed") }));

    await waitFor(() => expect(rows().some((row) => row.textContent?.includes("Panel role"))).toBe(false));
    const onsite = rows().find((row) => row.textContent?.includes("Onsite"));
    expect(onsite).toBeDefined();
    expect(onsite).toContainElement(document.activeElement as HTMLElement);
  });

  it("groups the board once, however often it draws again", async () => {
    const user = userEvent.setup();
    render(<Page cards={[openai, stripe]} />);
    expect(dueByDay.upNext).toHaveBeenCalledTimes(1);

    await user.click(screen.getByRole("button", { name: "again" }));
    await user.click(screen.getByRole("button", { name: /^Fri, Nov 6/ }));

    expect(dueByDay.upNext).toHaveBeenCalledTimes(1);
  });
});

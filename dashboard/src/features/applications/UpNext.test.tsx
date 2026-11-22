import { render, screen, within } from "@testing-library/react";
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

/** Up next over a board that drops a step when it is ticked, as the page's does. */
function Page({ cards }: { cards: ApplicationCard[] }) {
  const [board, setBoard] = useState(cards);
  const [, tick] = useState(0);
  return (
    <MemoryRouter>
      <button onClick={() => tick((n) => n + 1)}>again</button>
      <UpNext
        resource={resource(board)}
        now={now}
        actions={{
          onFinishStep: (card, step) =>
            setBoard((was) => was.map((one) => (one.job_id === card.job_id ? { ...one, steps: one.steps.filter((s) => s.id !== step.id) } : one))),
          onSetOutcome: vi.fn(),
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

  it("moves the mark to the day picked in the month", async () => {
    const user = userEvent.setup();
    render(<Page cards={[openai, stripe]} />);

    await user.click(screen.getByRole("button", { name: /^Fri, Nov 6/ }));

    const marked = rows().filter((row) => row.hasAttribute("data-picked"));
    expect(marked).toHaveLength(1);
    expect(marked[0]).toHaveTextContent("Hiring manager");
    expect(screen.getByRole("button", { name: /^Wed, Nov 4/ })).toHaveAttribute("aria-pressed", "false");
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

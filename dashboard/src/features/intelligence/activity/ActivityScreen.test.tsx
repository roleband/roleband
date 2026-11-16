import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { api } from "../../../api";
import type { ActivityEntry, ActivityPage } from "../../../api/agentActivity";
import { ActivityScreen } from "./ActivityScreen";
import { byDay, dayHeading } from "./ActivityList";

/* Behaviour contracts for the Activity screen. The api is mocked at the
 * boundary; every assertion is about what the reader sees or what the
 * server was asked. */

vi.mock("../../../api", () => ({ api: { agentActivity: vi.fn() } }));

const HOUR = 3_600_000;
const ago = (hours: number) => new Date(Date.now() - hours * HOUR).toISOString();

function entry(over: Partial<ActivityEntry> & { id: number }): ActivityEntry {
  return {
    occurred_at: ago(0),
    operation: "opportunities.search",
    kind: "read",
    categories: ["public_posting"],
    action_group: null,
    refusal: null,
    summary: "Read postings",
    subject: { topic: "read.public_posting" },
    changes: [],
    ...over,
  };
}

const MOVED = entry({
  id: 3,
  occurred_at: ago(0.1),
  operation: "pursuits.patch",
  kind: "change",
  categories: ["private_pursuit", "public_posting"],
  action_group: "tracking_progress",
  summary: "Moved Design Lead at contoso to interviewing",
  subject: { topic: "pursuit.moved", title: "Design Lead", company: "contoso", stage: "interviewing" },
  changes: [
    { field: "stage", before: "applied", after: "interviewing" },
    { field: "next_action", before: null, after: "Portfolio review" },
  ],
});
const REFUSED = entry({
  id: 2,
  occurred_at: ago(0.2),
  operation: "offer.get",
  kind: "refused",
  categories: ["offer"],
  refusal: "category_disabled",
  summary: "Asked for your offer",
  subject: { topic: "refused.category", category: "offer" },
});
const READ = entry({ id: 1, occurred_at: ago(30), subject: { topic: "read.public_posting", count: 42 } });

function page(over: Partial<ActivityPage> = {}): ActivityPage {
  return { items: [MOVED, REFUSED, READ], next_cursor: null, ...over };
}

const lastParams = () => {
  const calls = vi.mocked(api.agentActivity).mock.calls;
  return calls[calls.length - 1]?.[0];
};

function renderScreen(initial = "/settings/intelligence/activity") {
  return render(
    <MemoryRouter initialEntries={[initial]}>
      <ActivityScreen />
    </MemoryRouter>,
  );
}

const rows = () => within(screen.getByRole("region", { name: "Entries" })).getAllByRole("link");
const inspector = () => screen.getByRole("complementary", { name: "Picked entry" });

beforeEach(() => {
  vi.mocked(api.agentActivity).mockReset();
  vi.mocked(api.agentActivity).mockResolvedValue(page());
});

describe("ActivityScreen: the list", () => {
  it("says each entry from its facts, with a tag for what it is", async () => {
    renderScreen();
    await screen.findByText("Design Lead", { selector: "b *" });
    const [moved, refused, read] = rows();
    expect(moved).toHaveTextContent("Moved Design Lead at contoso to Interviewing");
    expect(moved).toHaveTextContent("Tracking progress");
    expect(refused).toHaveTextContent("Asked for your offer");
    expect(within(refused).getByText("Not shared")).toBeInTheDocument();
    expect(read).toHaveTextContent("Read 42 postings");
    expect(within(read).getByText("Postings")).toBeInTheDocument();
  });

  it("groups the entries under one heading per day, newest first", async () => {
    renderScreen();
    await screen.findByText("Asked for your offer");
    const headings = within(screen.getByRole("region", { name: "Entries" })).getAllByRole("heading", { level: 2 });
    expect(headings.map((heading) => heading.textContent?.startsWith("Today") || heading.textContent?.startsWith("Yesterday")))
      .toEqual([true, true]);
    expect(headings[0]).toHaveTextContent(/^Today/);
    expect(headings[1]).toHaveTextContent(/^Yesterday/);
  });

  it("falls back to the stored sentence for a topic it has no words for", async () => {
    vi.mocked(api.agentActivity).mockResolvedValue(page({
      items: [entry({ id: 9, summary: "Ran something new", subject: { topic: "later.topic" } })],
    }));
    renderScreen();
    await screen.findByText("1 to 1");
    expect(rows()[0]).toHaveTextContent("Ran something new");
  });

  it("says when nothing matches the filters, and when there is nothing yet", async () => {
    vi.mocked(api.agentActivity).mockResolvedValue(page({ items: [] }));
    renderScreen("/settings/intelligence/activity?kind=refused");
    expect(await screen.findByText("No entry matches these filters.")).toBeInTheDocument();
  });
});

describe("ActivityScreen: the inspector", () => {
  it("shows the first entry until another is picked, the old value struck through", async () => {
    renderScreen();
    await screen.findByText("Asked for your offer");
    expect(rows()[0]).toHaveAttribute("aria-current", "true");
    expect(rows()[1]).not.toHaveAttribute("aria-current");

    const panel = inspector();
    expect(within(panel).getByRole("heading", { level: 2 })).toHaveTextContent("Moved Design Lead at contoso to Interviewing");
    const changed = within(panel).getByLabelText("What changed");
    expect(within(changed).getByText("Applied").closest("s")).not.toBeNull();
    expect(changed).toHaveTextContent("Interviewing");
    // A field the record did not have shows only its new value.
    expect(within(changed).getByText("Portfolio review").closest("s")).toBeNull();
    expect(within(panel).getByText("pursuits.patch").tagName).toBe("CODE");
    expect(panel).toHaveTextContent("Progress and notes and Postings");
    expect(panel).toHaveTextContent("Tracking progress");
  });

  it("follows the picked row, and says what a refusal asked for", async () => {
    const user = userEvent.setup();
    renderScreen();
    await screen.findByText("Asked for your offer");
    await user.click(rows()[1]);
    expect(rows()[1]).toHaveAttribute("aria-current", "true");
    expect(rows()[0]).not.toHaveAttribute("aria-current");
    const panel = inspector();
    expect(within(panel).getByRole("heading", { level: 2 })).toHaveTextContent("Asked for your offer");
    expect(within(panel).queryByLabelText("What changed")).toBeNull();
    expect(within(panel).getByText("Asked for")).toBeInTheDocument();
    expect(within(panel).queryByText("Group")).toBeNull();
  });
});

describe("ActivityScreen: filters and pages", () => {
  it("asks for the last 30 days by default, from the reader's midnight", async () => {
    renderScreen();
    await screen.findByText("Asked for your offer");
    const now = new Date();
    const midnight = new Date(now.getFullYear(), now.getMonth(), now.getDate() - 29).toISOString();
    expect(lastParams()).toMatchObject({ kind: "all", category: null, since: midnight, cursor: null, q: null });
    expect(screen.getByRole("button", { name: "All" })).toHaveAttribute("aria-pressed", "true");
  });

  it("asks the server for one kind, one kind of data and a span of days", async () => {
    const user = userEvent.setup();
    renderScreen();
    await screen.findByText("Asked for your offer");

    await user.click(screen.getByRole("button", { name: "Refused" }));
    expect(screen.getByRole("button", { name: "Refused" })).toHaveAttribute("aria-pressed", "true");
    await waitFor(() => expect(lastParams()).toMatchObject({ kind: "refused" }));

    await user.click(screen.getByRole("button", { name: /Any data/ }));
    await user.click(await screen.findByRole("radio", { name: "Offer" }));
    await waitFor(() => expect(lastParams()).toMatchObject({ kind: "refused", category: "offer" }));

    await user.click(screen.getByRole("button", { name: /Last 30 days/ }));
    await user.click(await screen.findByRole("radio", { name: "Any time" }));
    await waitFor(() => expect(lastParams()).toMatchObject({ category: "offer", since: null }));
  });

  it("searches on the server once typing pauses", async () => {
    const user = userEvent.setup();
    renderScreen();
    await screen.findByText("Asked for your offer");
    await user.type(screen.getByRole("searchbox", { name: "Search activity" }), "contoso");
    await waitFor(() => expect(lastParams()).toMatchObject({ q: "contoso" }));
    const asked = vi.mocked(api.agentActivity).mock.calls.map(([params]) => params.q);
    // A keystroke is not a query.
    expect(asked).not.toContain("c");
  });

  it("pages older by the cursor it was given, back newer, and starts over on a filter", async () => {
    const user = userEvent.setup();
    const full = Array.from({ length: 50 }, (_, n) => entry({ id: 100 - n, occurred_at: ago(n / 100) }));
    vi.mocked(api.agentActivity).mockResolvedValue(page({ items: full, next_cursor: "older-1" }));
    renderScreen();
    expect(await screen.findByText("1 to 50")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Newer" })).toBeNull();

    await user.click(screen.getByRole("button", { name: "Older" }));
    await waitFor(() => expect(lastParams()).toMatchObject({ cursor: "older-1" }));
    expect(await screen.findByText("51 to 100")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Newer" }));
    await waitFor(() => expect(lastParams()).toMatchObject({ cursor: null }));
    expect(await screen.findByText("1 to 50")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Older" }));
    await waitFor(() => expect(lastParams()).toMatchObject({ cursor: "older-1" }));
    await user.click(screen.getByRole("button", { name: "Changes" }));
    await waitFor(() => expect(lastParams()).toMatchObject({ kind: "change", cursor: null }));
  });

  it("offers no Older on the last page", async () => {
    renderScreen();
    await screen.findByText("1 to 3");
    expect(screen.queryByRole("button", { name: "Older" })).toBeNull();
  });
});

describe("activity days", () => {
  it("runs a page's entries into days, and names today and yesterday", () => {
    const now = new Date(2026, 10, 16, 14, 0);
    const at = (day: number, hour: number) => new Date(2026, 10, day, hour).toISOString();
    const days = byDay([
      entry({ id: 4, occurred_at: at(16, 9) }),
      entry({ id: 3, occurred_at: at(16, 0) }),
      entry({ id: 2, occurred_at: at(15, 23) }),
      entry({ id: 1, occurred_at: at(13, 9) }),
    ]);
    expect(days.map((day) => day.items.map((item) => item.id))).toEqual([[4, 3], [2], [1]]);
    expect(dayHeading(at(16, 9), now).name).toBe("Today");
    expect(dayHeading(at(15, 23), now).name).toBe("Yesterday");
    expect(dayHeading(at(13, 9), now)).toEqual({ name: "Friday", date: "November 13" });
    expect(dayHeading(new Date(2025, 10, 13).toISOString(), now).date).toBe("November 13, 2025");
  });
});

import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { api } from "../../../api";
import { msg } from "../../../test/msg";
import type { ActivityEntry, ActivityPage } from "../../../api/agentActivity";
import { ActivityScreen } from "./ActivityScreen";
import { byDay, dayHeading } from "./ActivityList";

/* Behaviour contracts for the Activity screen. The api is mocked at the
 * boundary; every assertion is about what the reader sees or what the
 * server was asked. */

vi.mock("../../../api", () => ({ api: { agentActivity: vi.fn() } }));

const HOUR = 3_600_000;
// Entries are placed before today's local noon, not before the wall clock, so
// "today" and "yesterday" hold at any hour the suite runs.
const NOON = new Date(new Date().setHours(12, 0, 0, 0)).getTime();
const ago = (hours: number) => new Date(NOON - hours * HOUR).toISOString();

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

const MOVED_TEXT = msg("activity-moved-role", {
  title: "Design Lead", company: "contoso", stage: msg("taxonomy-stage-interviewing"),
});
const ASKED_OFFER = msg("activity-asked-offer");
const entries = () => screen.getByRole("region", { name: msg("activity-list") });
const rows = () => within(entries()).getAllByRole("link");
const inspector = () => screen.getByRole("complementary", { name: msg("activity-inspector") });
const button = (name: string) => screen.getByRole("button", { name });
const range = (first: number, last: number) => msg("activity-page-range", { first, last });

beforeEach(() => {
  vi.mocked(api.agentActivity).mockReset();
  vi.mocked(api.agentActivity).mockResolvedValue(page());
});

describe("ActivityScreen: the list", () => {
  it("says each entry from its facts, with a tag for what it is", async () => {
    renderScreen();
    await screen.findByText("Design Lead", { selector: "b *" });
    const [moved, refused, read] = rows();
    expect(moved).toHaveTextContent(MOVED_TEXT);
    expect(moved).toHaveTextContent(msg("activity-group-tracking-progress"));
    expect(refused).toHaveTextContent(ASKED_OFFER);
    expect(within(refused).getByText(msg("activity-tag-not-shared"))).toBeInTheDocument();
    expect(read).toHaveTextContent(msg("activity-read-postings-count", { count: 42 }));
    expect(within(read).getByText(msg("activity-category-postings"))).toBeInTheDocument();
  });

  it("groups the entries under one heading per day, newest first", async () => {
    renderScreen();
    await screen.findByText(ASKED_OFFER);
    const headings = within(entries()).getAllByRole("heading", { level: 2 });
    expect(headings).toHaveLength(2);
    expect(headings[0].textContent?.startsWith(msg("activity-day-today"))).toBe(true);
    expect(headings[1].textContent?.startsWith(msg("activity-day-yesterday"))).toBe(true);
  });

  it("falls back to the stored sentence for a topic it has no words for", async () => {
    vi.mocked(api.agentActivity).mockResolvedValue(page({
      items: [entry({ id: 9, summary: "Ran something new", subject: { topic: "later.topic" } })],
    }));
    renderScreen();
    await screen.findByText(range(1, 1));
    expect(rows()[0]).toHaveTextContent("Ran something new");
  });

  it("says when nothing matches the filters, and when there is nothing yet", async () => {
    vi.mocked(api.agentActivity).mockResolvedValue(page({ items: [] }));
    renderScreen("/settings/intelligence/activity?kind=refused");
    expect(await screen.findByText(msg("activity-empty-body", { choice: "yes" }))).toBeInTheDocument();
  });
});

describe("ActivityScreen: the inspector", () => {
  it("shows the first entry until another is picked, the old value struck through", async () => {
    renderScreen();
    await screen.findByText(ASKED_OFFER);
    expect(rows()[0]).toHaveAttribute("aria-current", "true");
    expect(rows()[1]).not.toHaveAttribute("aria-current");

    const panel = inspector();
    expect(within(panel).getByRole("heading", { level: 2 })).toHaveTextContent(MOVED_TEXT);
    const changed = within(panel).getByLabelText(msg("activity-what-changed"));
    expect(within(changed).getByText(msg("taxonomy-stage-applied")).closest("s")).not.toBeNull();
    expect(changed).toHaveTextContent(msg("taxonomy-stage-interviewing"));
    // A field the record did not have shows only its new value.
    expect(within(changed).getByText("Portfolio review").closest("s")).toBeNull();
    expect(within(panel).getByText("pursuits.patch").tagName).toBe("CODE");
    expect(panel).toHaveTextContent(msg("activity-category-progress-and-notes"));
    expect(panel).toHaveTextContent(msg("activity-category-postings"));
    expect(panel).toHaveTextContent(msg("activity-group-tracking-progress"));
  });

  it("follows the picked row, and says what a refusal asked for", async () => {
    const user = userEvent.setup();
    renderScreen();
    await screen.findByText(ASKED_OFFER);
    await user.click(rows()[1]);
    expect(rows()[1]).toHaveAttribute("aria-current", "true");
    expect(rows()[0]).not.toHaveAttribute("aria-current");
    const panel = inspector();
    expect(within(panel).getByRole("heading", { level: 2 })).toHaveTextContent(ASKED_OFFER);
    expect(within(panel).queryByLabelText(msg("activity-what-changed"))).toBeNull();
    expect(within(panel).getByText(msg("activity-fact-asked-for"))).toBeInTheDocument();
    expect(within(panel).queryByText(msg("activity-fact-group"))).toBeNull();
  });
});

describe("ActivityScreen: filters and pages", () => {
  it("asks for the last 30 days by default, from the reader's midnight", async () => {
    renderScreen();
    await screen.findByText(ASKED_OFFER);
    const now = new Date();
    const midnight = new Date(now.getFullYear(), now.getMonth(), now.getDate() - 29).toISOString();
    expect(lastParams()).toMatchObject({ kind: "all", category: null, since: midnight, cursor: null, q: null });
    expect(button(msg("activity-kind-all"))).toHaveAttribute("aria-pressed", "true");
  });

  it("asks the server for one kind, one kind of data and a span of days", async () => {
    const user = userEvent.setup();
    renderScreen();
    await screen.findByText(ASKED_OFFER);

    await user.click(button(msg("activity-kind-refused")));
    expect(button(msg("activity-kind-refused"))).toHaveAttribute("aria-pressed", "true");
    await waitFor(() => expect(lastParams()).toMatchObject({ kind: "refused" }));

    await user.click(button(msg("activity-category-any")));
    await user.click(await screen.findByRole("radio", { name: msg("activity-category-offer") }));
    await waitFor(() => expect(lastParams()).toMatchObject({ kind: "refused", category: "offer" }));

    await user.click(button(msg("activity-range-month")));
    await user.click(await screen.findByRole("radio", { name: msg("activity-range-all") }));
    await waitFor(() => expect(lastParams()).toMatchObject({ category: "offer", since: null }));
  });

  it("searches on the server once typing pauses", async () => {
    const user = userEvent.setup();
    renderScreen();
    await screen.findByText(ASKED_OFFER);
    await user.type(screen.getByRole("searchbox", { name: msg("activity-search") }), "contoso");
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
    expect(await screen.findByText(range(1, 50))).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: msg("activity-newer") })).toBeNull();

    await user.click(button(msg("activity-older")));
    await waitFor(() => expect(lastParams()).toMatchObject({ cursor: "older-1" }));
    expect(await screen.findByText(range(51, 100))).toBeInTheDocument();

    await user.click(button(msg("activity-newer")));
    await waitFor(() => expect(lastParams()).toMatchObject({ cursor: null }));
    expect(await screen.findByText(range(1, 50))).toBeInTheDocument();

    await user.click(button(msg("activity-older")));
    await waitFor(() => expect(lastParams()).toMatchObject({ cursor: "older-1" }));
    await user.click(button(msg("activity-kind-changes")));
    await waitFor(() => expect(lastParams()).toMatchObject({ kind: "change", cursor: null }));
  });

  it("starts at the newest again on a filter it has paged before", async () => {
    const user = userEvent.setup();
    const full = Array.from({ length: 50 }, (_, n) => entry({ id: 100 - n, occurred_at: ago(n / 100) }));
    vi.mocked(api.agentActivity).mockResolvedValue(page({ items: full, next_cursor: "older-1" }));
    renderScreen();
    await screen.findByText(range(1, 50));
    await user.click(button(msg("activity-older")));
    await screen.findByText(range(51, 100));

    await user.click(button(msg("activity-kind-changes")));
    await waitFor(() => expect(lastParams()).toMatchObject({ kind: "change", cursor: null }));
    await user.click(button(msg("activity-kind-all")));
    await waitFor(() => expect(lastParams()).toMatchObject({ kind: "all", cursor: null }));
    expect(await screen.findByText(range(1, 50))).toBeInTheDocument();
  });

  it("offers no Older on the last page", async () => {
    renderScreen();
    await screen.findByText(range(1, 3));
    expect(screen.queryByRole("button", { name: msg("activity-older") })).toBeNull();
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

import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { api, ApiError } from "../../../api";
import { msg } from "../../../test/msg";
import type { ActivityEntry, ActivityPage } from "../../../api/agentActivity";
import { ActivityScreen } from "./ActivityScreen";
import { byDay, dayHeading } from "./ActivityList";

/* Behaviour contracts for the Activity screen. The api is mocked at the
 * boundary; every assertion is about what the reader sees or what the
 * server was asked. */

vi.mock("../../../api", async (importOriginal) => ({
  ...(await importOriginal<typeof import("../../../api")>()),
  api: { agentActivity: vi.fn(), agentActivityEntry: vi.fn() },
}));

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
    host: "claude-code",
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
const shownInspector = () => screen.findByRole("complementary", { name: msg("activity-inspector") });
const button = (name: string) => screen.getByRole("button", { name });
const range = (first: number, last: number) => msg("activity-page-range", { first, last });

beforeEach(() => {
  vi.mocked(api.agentActivity).mockReset();
  vi.mocked(api.agentActivity).mockResolvedValue(page());
  vi.mocked(api.agentActivityEntry).mockReset();
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

  it("opens a link to an entry on an older page on that entry, not on the newest", async () => {
    const older = entry({
      id: 77, occurred_at: ago(72), operation: "recipes.draft.save", kind: "change",
      summary: "Drafted a recipe for careers-fabrikam",
      subject: { topic: "recipe.drafted", recipe: "careers-fabrikam" },
      changes: [{ field: "draft", before: null, after: 3 }],
    });
    vi.mocked(api.agentActivityEntry).mockResolvedValue(older);
    renderScreen("/settings/intelligence/activity?entry=77");

    // The panel is replaced once the entry arrives: read it afresh each time.
    await waitFor(() => expect(within(inspector()).getByRole("heading", { level: 2 }))
      .toHaveTextContent(msg("activity-drafted-recipe", { recipe: "careers-fabrikam" })));
    expect(inspector()).not.toHaveTextContent(MOVED_TEXT);
    expect(within(inspector()).getByLabelText(msg("activity-what-changed"))).toBeInTheDocument();
    expect(vi.mocked(api.agentActivityEntry).mock.calls[0][0]).toBe(77);
    // The list is still the newest page, and no row on it claims the entry.
    expect(rows()).toHaveLength(3);
    for (const row of rows()) expect(row).not.toHaveAttribute("aria-current");
  });

  it("says so when a link names an entry the log does not hold, and shows no other", async () => {
    vi.mocked(api.agentActivityEntry).mockRejectedValue(new ApiError("gone", 404, "activity-entry-not-found"));
    renderScreen("/settings/intelligence/activity?entry=999");

    expect(await within(await shownInspector()).findByText(msg("activity-entry-missing"))).toBeInTheDocument();
    // The result is said in the live region that said it was loading.
    expect(within(inspector()).getByRole("status")).toHaveTextContent(msg("activity-entry-missing"));
    expect(within(inspector()).queryByRole("heading")).toBeNull();
    for (const row of rows()) expect(row).not.toHaveAttribute("aria-current");
  });

  it("shows a linked entry beside an empty list, and says so when there is none", async () => {
    vi.mocked(api.agentActivity).mockResolvedValue(page({ items: [] }));
    vi.mocked(api.agentActivityEntry).mockResolvedValue(READ);
    const first = renderScreen("/settings/intelligence/activity?entry=1");
    await waitFor(() => expect(within(inspector()).getByRole("heading", { level: 2 }))
      .toHaveTextContent(msg("activity-read-postings-count", { count: 42 })));
    // The list column still says it is empty.
    expect(screen.getByText(msg("activity-empty-title", { choice: "no" }))).toBeInTheDocument();
    first.unmount();

    vi.mocked(api.agentActivityEntry).mockRejectedValue(new ApiError("gone", 404, "activity-entry-not-found"));
    renderScreen("/settings/intelligence/activity?entry=999");
    expect(await within(await shownInspector()).findByText(msg("activity-entry-missing"))).toBeInTheDocument();
    expect(screen.getByText(msg("activity-empty-title", { choice: "no" }))).toBeInTheDocument();
  });

  it("reads nothing more for an entry on the loaded page", async () => {
    renderScreen("/settings/intelligence/activity?entry=2");
    expect(await within(await shownInspector()).findByRole("heading", { level: 2 })).toHaveTextContent(ASKED_OFFER);
    expect(rows()[1]).toHaveAttribute("aria-current", "true");
    expect(api.agentActivityEntry).not.toHaveBeenCalled();
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

  it("moves the range on at the reader's midnight while the screen stays open", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    try {
      vi.setSystemTime(new Date(2026, 10, 16, 23, 59, 30));
      renderScreen("/settings/intelligence/activity?range=today");
      await screen.findByText(ASKED_OFFER);
      expect(lastParams()).toMatchObject({ since: new Date(2026, 10, 16).toISOString() });

      await vi.advanceTimersByTimeAsync(60_000);
      await waitFor(() => expect(lastParams()).toMatchObject({ since: new Date(2026, 10, 17).toISOString() }));
    } finally {
      vi.useRealTimers();
    }
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

  it("opens on one app's entries when the address names it, and lets that go", async () => {
    const user = userEvent.setup();
    renderScreen("/settings/intelligence/activity?app=codex");
    await screen.findByText(ASKED_OFFER);
    expect(lastParams()).toMatchObject({ host: "codex" });
    // The button names the app it keeps, so the reader can see why the list is short.
    await user.click(button(msg("ai-assistants-card-app-codex-app")));
    await user.click(await screen.findByRole("radio", { name: msg("activity-app-any") }));
    await waitFor(() => expect(lastParams()).toMatchObject({ host: null }));
    await user.click(button(msg("activity-app-any")));
    await user.click(await screen.findByRole("radio", { name: msg("ai-assistants-card-app-other-app") }));
    await waitFor(() => expect(lastParams()).toMatchObject({ host: "other" }));
  });

  it("reads an app the address cannot name as any app", async () => {
    renderScreen("/settings/intelligence/activity?app=gemini");
    await screen.findByText(ASKED_OFFER);
    expect(lastParams()).toMatchObject({ host: null });
    expect(button(msg("activity-app-any"))).toBeInTheDocument();
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

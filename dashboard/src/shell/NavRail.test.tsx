import { act, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, useLocation } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { NavRail } from "./NavRail";
import { forgetViewChoices, setViewChoice } from "../hooks/viewChoices";
import { fakeViewChoiceServer } from "../test/viewChoicesServer";
import { msg } from "../test/msg";
import { PreferencesSection } from "../features/settings/PreferencesSection";

vi.mock("../context/JobWorkspace", () => ({
  useJobWorkspace: () => ({ compareIds: new Set<number>() }),
}));

// Mutable so a test can put the rail in front of a real queue depth.
let stats: Record<string, number> = { notif_unread: 0, review_pending: 0 };
vi.mock("../context/MissionState", () => ({
  useMissionStats: () => stats,
}));

beforeEach(() => {
  stats = { notif_unread: 0, review_pending: 0 };
  localStorage.clear();
});

const rail = (expanded = false) =>
  render(
    <MemoryRouter>
      <NavRail expanded={expanded} onToggleExpanded={vi.fn()} theme="dark" onToggleTheme={vi.fn()} />
    </MemoryRouter>
  );

describe("NavRail", () => {
  it("starts as an icon rail and expands only from the rail toggle", async () => {
    const user = userEvent.setup();
    const onToggleExpanded = vi.fn();

    render(
      <MemoryRouter>
        <NavRail expanded={false} onToggleExpanded={onToggleExpanded} theme="dark" onToggleTheme={vi.fn()} />
      </MemoryRouter>
    );

    expect(screen.getByRole("navigation", { name: "Main" })).toHaveClass("collapsed");
    expect(screen.getByRole("button", { name: "Expand navigation" })).toHaveAttribute("aria-expanded", "false");
    expect(screen.getByRole("link", { name: "Radar" })).toHaveAttribute("data-tip", "Radar");

    await user.click(screen.getByRole("button", { name: "Expand navigation" }));
    expect(onToggleExpanded).toHaveBeenCalledTimes(1);
  });

  it("marks the rail with the product mark, hidden from readers, not a letter", () => {
    const { container } = rail();
    const tile = container.querySelector(".brand-mark");
    const mark = tile?.querySelector("svg[data-brand-mark]");
    expect(mark).not.toBeNull();
    expect(mark).toHaveAttribute("aria-hidden", "true");
    expect(mark?.querySelectorAll("circle[r='43.9'], circle[r='28.6'], circle[r='13.2']")).toHaveLength(3);
    expect(tile).toHaveTextContent(/^$/);
  });

  it("exposes a collapse control when expanded", () => {
    render(
      <MemoryRouter>
        <NavRail expanded onToggleExpanded={vi.fn()} theme="dark" onToggleTheme={vi.fn()} />
      </MemoryRouter>
    );

    expect(screen.getByRole("navigation", { name: "Main" })).toHaveClass("expanded");
    expect(screen.getByRole("button", { name: "Collapse navigation" })).toHaveAttribute("aria-expanded", "true");
  });

  const names = (group: string) =>
    Array.from(screen.getByRole("navigation", { name: "Main" }).querySelectorAll(`${group} .rail-item`)).map((item) =>
      item.getAttribute("aria-label"));

  it("lists the work at the top and the person and the app at the foot, and neither Duplicates nor Notifications", () => {
    rail();
    expect(names(".rail-top")).toEqual(["Radar", "Top picks", "Pipeline", "Insights", "Companies"]);
    expect(names(".rail-bottom")).toEqual(["Profile", "Settings", msg("shell-theme-aria")]);
    expect(screen.queryByRole("link", { name: /Duplicates|Notifications/ })).toBeNull();
  });

  it("lists Duplicates once the person turns it on, with no count however long its queue", () => {
    stats = { notif_unread: 7, review_pending: 342 };
    forgetViewChoices({ "sidebar.duplicates": true });
    rail();
    const review = screen.getByRole("link", { name: "Duplicates" });
    expect(review.querySelector(".rail-badge")).toBeNull();
    expect(names(".rail-top")).toEqual(["Radar", "Top picks", "Pipeline", "Insights", "Companies", "Duplicates"]);
  });

  it("follows the switches of Settings › Preferences at once", async () => {
    fakeViewChoiceServer({});
    const user = userEvent.setup();
    render(
      <MemoryRouter initialEntries={["/settings/preferences"]}>
        <NavRail expanded={false} onToggleExpanded={vi.fn()} theme="dark" onToggleTheme={vi.fn()} />
        <PreferencesSection />
      </MemoryRouter>,
    );
    const nav = within(screen.getByRole("navigation", { name: "Main" }));
    const card = within(screen.getByRole("region", { name: msg("settings-side-bar-title") }));
    expect(nav.queryByRole("link", { name: "Duplicates" })).toBeNull();
    await user.click(card.getByRole("checkbox", { name: "Duplicates" }));
    expect(nav.getByRole("link", { name: "Duplicates" })).toBeInTheDocument();
    await user.click(card.getByRole("checkbox", { name: "Insights" }));
    expect(nav.queryByRole("link", { name: "Insights" })).toBeNull();
  });

  it("takes a place off the moment the person turns it off elsewhere on the page", async () => {
    const server = fakeViewChoiceServer({});
    rail();
    expect(await screen.findByRole("link", { name: "Insights" })).toBeInTheDocument();
    await act(() => setViewChoice("sidebar.insights", false));
    expect(screen.queryByRole("link", { name: "Insights" })).toBeNull();
    expect(server.saved()).toEqual({ "sidebar.insights": false });
  });
});

/* The Pipeline is a star. Collapsed, the star stands alone and the page's
 * tabs switch between the views; expanded, the views are named under it. How
 * they drop in is the stylesheet's (pinned in tests/ux/pipeline-rail.spec.ts). */
describe("the Pipeline in the rail", () => {
  function Where() {
    return <output data-testid="where">{useLocation().pathname}</output>;
  }
  const rail = (path: string, expanded = false) => (
    <MemoryRouter initialEntries={[path]}>
      <NavRail expanded={expanded} onToggleExpanded={vi.fn()} theme="dark" onToggleTheme={vi.fn()} />
      <Where />
    </MemoryRouter>
  );
  const at = (path: string, expanded = false) => render(rail(path, expanded));
  const nav = () => within(screen.getByRole("navigation", { name: "Main" }));
  const star = () => nav().getByRole("link", { name: "Pipeline" });
  const views = () => ["Considering", "Board", "Up next"].filter((name) => nav().queryByRole("link", { name }) != null);

  it("collapsed, shows the star alone, inside the Pipeline and out", () => {
    const { unmount } = at("/");
    expect(star().querySelector("svg")).not.toBeNull();
    expect(views()).toEqual([]);
    unmount();
    at("/pipeline/board");
    expect(star()).toHaveAttribute("aria-current", "true");
    expect(views(), "the page's tabs name the view, not the rail").toEqual([]);
  });

  it("goes into the Pipeline at Considering when the star is pressed, and marks the star as the place", async () => {
    const user = userEvent.setup();
    at("/");
    expect(star()).not.toHaveAttribute("aria-current");
    await user.click(star());
    expect(screen.getByTestId("where")).toHaveTextContent("/pipeline/list");
    // The place is the Pipeline; the page is its view.
    expect(star()).toHaveAttribute("aria-current", "true");
  });

  it("expanded, names the star and its three views in order, outside the Pipeline too", () => {
    at("/", true);
    expect(star()).toHaveTextContent("Pipeline");
    expect(star()).not.toHaveAttribute("aria-current");
    expect(views()).toEqual(["Considering", "Board", "Up next"]);
    expect(nav().getByRole("link", { name: "Board" })).toHaveTextContent("Board");
    for (const name of views()) expect(nav().getByRole("link", { name })).not.toHaveAttribute("aria-current");
  });

  it("expanded in the Pipeline, marks the star and the view on screen, and only it", () => {
    at("/pipeline/board", true);
    expect(star()).toHaveAttribute("aria-current", "true");
    expect(nav().getByRole("link", { name: "Board" })).toHaveAttribute("aria-current", "page");
    expect(nav().getByRole("link", { name: "Considering" })).not.toHaveAttribute("aria-current");
    expect(nav().getByRole("link", { name: "Up next" })).not.toHaveAttribute("aria-current");
    expect(nav().getByRole("link", { name: "Radar" })).not.toHaveAttribute("aria-current");
  });

  it("drops the views when the rail widens and takes them away when it narrows", () => {
    const { rerender } = at("/pipeline/list");
    expect(views()).toEqual([]);
    rerender(rail("/pipeline/list", true));
    expect(views()).toEqual(["Considering", "Board", "Up next"]);
    rerender(rail("/pipeline/list", false));
    expect(views()).toEqual([]);
  });
});

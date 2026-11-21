import { act, fireEvent, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, useLocation } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { NavRail } from "./NavRail";

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

  /* The badge policy, at the two counts that decide it.
   *
   * `review_pending` is the pending duplicate queue, which can sit in the
   * hundreds — so a saturated `99+` badge would be the one rail item that
   * never settles and never says anything. */
  it("shows a count a user can act on as the number it is", () => {
    stats = { notif_unread: 0, review_pending: 12 };
    rail();

    const review = screen.getByRole("link", { name: "Duplicates, 12 pending" });
    const badge = review.querySelector(".rail-badge")!;
    expect(badge).toHaveTextContent("12");
    expect(badge).not.toHaveClass("rail-badge-dot");
  });

  it("stops claiming to be a count past the cap, keeping the exact number", () => {
    stats = { notif_unread: 0, review_pending: 342 };
    rail();

    // The number is on the item — as its name, its hover tooltip collapsed
    // (`data-tip`) and expanded (`title`) — not saturated inside the badge.
    const review = screen.getByRole("link", { name: "Duplicates, 342 pending" });
    expect(review).toHaveAttribute("data-tip", "Duplicates, 342 pending");
    expect(review).toHaveAttribute("title", "Duplicates, 342 pending");

    const badge = review.querySelector(".rail-badge")!;
    expect(badge).toHaveClass("rail-badge-dot");
    expect(badge).toHaveTextContent("");
    expect(review).not.toHaveTextContent("99+");
  });

  it("leaves an item with nothing pending unbadged and unrenamed", () => {
    rail();

    const review = screen.getByRole("link", { name: "Duplicates" });
    expect(review.querySelector(".rail-badge")).toBeNull();
    expect(screen.getByRole("link", { name: "Notifications" })).toBeTruthy();
  });

});

/* The Pipeline is a star with its views under it, folded away until the
 * pointer rests on the star or the star is pressed, at either rail width.
 * Whether the well is drawn is the stylesheet's (pinned in
 * tests/ux/pipeline-rail.spec.ts); here the state is what the star says. */
describe("the Pipeline in the rail", () => {
  function Where() {
    return <output data-testid="where">{useLocation().pathname}</output>;
  }
  const at = (path: string, expanded = false) =>
    render(
      <MemoryRouter initialEntries={[path]}>
        <NavRail expanded={expanded} onToggleExpanded={vi.fn()} theme="dark" onToggleTheme={vi.fn()} />
        <Where />
      </MemoryRouter>
    );
  const star = () => screen.getByRole("button", { name: "Pipeline" });
  const views = () => within(screen.getByRole("navigation", { name: "Main" }));

  afterEach(() => {
    vi.useRealTimers();
  });

  it("shows the star alone, closed, and a press opens its views until one is picked", async () => {
    const user = userEvent.setup();
    at("/");
    expect(star()).toHaveAttribute("aria-expanded", "false");
    expect(star().querySelector("svg")).not.toBeNull();
    expect(screen.queryByRole("link", { name: "Pipeline" }), "collapsed, the star opens; it does not go").toBeNull();

    await user.click(star());
    expect(star()).toHaveAttribute("aria-expanded", "true");
    expect(document.getElementById(star().getAttribute("aria-controls")!)).toContainElement(views().getByRole("link", { name: "Up next" }));

    await user.click(views().getByRole("link", { name: "Up next" }));
    expect(screen.getByTestId("where")).toHaveTextContent("/pipeline/up-next");
    expect(star()).toHaveAttribute("aria-expanded", "false");
    expect(views().getByRole("link", { name: "Up next" })).toHaveAttribute("aria-current", "page");
  });

  it("folds a well the star opened on a second press, a press elsewhere, or Escape, which hands the star its focus", async () => {
    const user = userEvent.setup();
    at("/");
    await user.click(star());
    await user.click(star());
    expect(star()).toHaveAttribute("aria-expanded", "false");

    await user.click(star());
    await user.click(document.body);
    expect(star()).toHaveAttribute("aria-expanded", "false");

    await user.click(star());
    views().getByRole("link", { name: "Board" }).focus();
    await user.keyboard("{Escape}");
    expect(star()).toHaveAttribute("aria-expanded", "false");
    expect(star()).toHaveFocus();
  });

  it("opens when the pointer rests on the star, not when it crosses it, and closes once it leaves", () => {
    vi.useFakeTimers();
    at("/pipeline/board");
    const family = star().parentElement!;

    fireEvent.pointerEnter(family, { pointerType: "mouse" });
    act(() => vi.advanceTimersByTime(60));
    expect(star(), "a pointer crossing the rail opens nothing").toHaveAttribute("aria-expanded", "false");
    fireEvent.pointerLeave(family, { pointerType: "mouse" });
    act(() => vi.advanceTimersByTime(500));
    expect(star()).toHaveAttribute("aria-expanded", "false");

    fireEvent.pointerEnter(family, { pointerType: "mouse" });
    act(() => vi.advanceTimersByTime(200));
    expect(star()).toHaveAttribute("aria-expanded", "true");

    // Away for a moment, as on the way from the star down into its views.
    fireEvent.pointerLeave(family, { pointerType: "mouse" });
    act(() => vi.advanceTimersByTime(100));
    fireEvent.pointerEnter(family, { pointerType: "mouse" });
    act(() => vi.advanceTimersByTime(500));
    expect(star()).toHaveAttribute("aria-expanded", "true");

    fireEvent.pointerLeave(family, { pointerType: "mouse" });
    act(() => vi.advanceTimersByTime(500));
    expect(star()).toHaveAttribute("aria-expanded", "false");
  });

  it("leaves a touch to the press: a finger on the star does not open it twice over", async () => {
    at("/");
    const family = star().parentElement!;
    fireEvent.pointerEnter(family, { pointerType: "touch" });
    await new Promise((done) => setTimeout(done, 200));
    expect(star()).toHaveAttribute("aria-expanded", "false");
  });

  it("marks the view on screen, and only it", () => {
    at("/pipeline/board");
    expect(views().getByRole("link", { name: "Board" })).toHaveAttribute("aria-current", "page");
    expect(views().getByRole("link", { name: "Considering" })).not.toHaveAttribute("aria-current");
    expect(views().getByRole("link", { name: "Radar" })).not.toHaveAttribute("aria-current");
  });

  it("folds the views away in the expanded rail too, where the star is named and a press drops them in named", async () => {
    const user = userEvent.setup();
    at("/pipeline/board", true);
    expect(star()).toHaveAttribute("aria-expanded", "false");
    expect(star()).toHaveTextContent("Pipeline");
    expect(screen.queryByRole("link", { name: "Pipeline" }), "the star opens; it does not go").toBeNull();

    await user.click(star());
    expect(star()).toHaveAttribute("aria-expanded", "true");
    expect(views().getByRole("link", { name: "Considering" })).toHaveTextContent("Considering");
    expect(views().getByRole("link", { name: "Board" })).toHaveAttribute("aria-current", "page");
  });

  it("folds the views away when the rail changes width", async () => {
    const user = userEvent.setup();
    const { rerender } = at("/");
    await user.click(star());
    expect(star()).toHaveAttribute("aria-expanded", "true");
    rerender(
      <MemoryRouter initialEntries={["/"]}>
        <NavRail expanded onToggleExpanded={vi.fn()} theme="dark" onToggleTheme={vi.fn()} />
      </MemoryRouter>
    );
    expect(star()).toHaveAttribute("aria-expanded", "false");
  });
});

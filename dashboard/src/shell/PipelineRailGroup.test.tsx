import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, useLocation } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { NavRail } from "./NavRail";

vi.mock("../context/JobWorkspace", () => ({
  useJobWorkspace: () => ({ compareIds: new Set<number>() }),
}));

vi.mock("../context/MissionState", () => ({
  useMissionStats: () => ({ notif_unread: 0, review_pending: 0 }),
}));

/* A role opened from a Pipeline view opens beside the rail, so the expanded
 * rail says where the person is: the Pipeline, and the view under the role.
 * Its address sits under the company, which must not light Companies. */

beforeEach(() => localStorage.clear());

function Where() {
  const location = useLocation();
  return <output data-testid="where">{location.pathname + location.search}</output>;
}

const role = "/company/microsoft/job/239";

const behind = (under: string) => ({ backgroundLocation: { pathname: under, search: "?filter=kept", state: null } });

function railOver(under: string | null) {
  const entries = [
    // The view as it was left, with a search; a fresh press opens it without.
    ...(under ? [`${under}?filter=kept`] : []),
    // The postings stepped through since all carry the same view under them.
    ...(under ? [{ pathname: "/company/stripe/job/7", state: behind(under) }] : []),
    { pathname: role, state: under ? behind(under) : null },
  ];
  render(
    <MemoryRouter initialEntries={entries} initialIndex={entries.length - 1}>
      <NavRail expanded onToggleExpanded={vi.fn()} theme="light" onToggleTheme={vi.fn()} />
      <Where />
    </MemoryRouter>,
  );
  return within(screen.getByRole("navigation"));
}

describe("the rail beside a role opened from the Pipeline", () => {
  it("marks the Pipeline and the view under the role as the place, and no other entry", () => {
    const rail = railOver("/pipeline/board");
    expect(rail.getByRole("link", { name: "Pipeline" })).toHaveAttribute("aria-current", "true");
    expect(rail.getByRole("link", { name: "Board" })).toHaveAttribute("aria-current", "true");
    expect(rail.getByRole("link", { name: "Up next" })).not.toHaveAttribute("aria-current");
    // The role's address is under its company; Companies is not the place.
    expect(rail.getByRole("link", { name: "Companies" })).not.toHaveAttribute("aria-current");
  });

  it("goes to the view as it was left, filter included, not to the posting stepped from", async () => {
    const rail = railOver("/pipeline/up-next");
    await userEvent.click(rail.getByRole("link", { name: "Up next" }));
    expect(screen.getByTestId("where")).toHaveTextContent(/^\/pipeline\/up-next\?filter=kept$/);
  });

  it("opens another view afresh when that one is pressed", async () => {
    const rail = railOver("/pipeline/board");
    await userEvent.click(rail.getByRole("link", { name: "Considering" }));
    expect(screen.getByTestId("where")).toHaveTextContent(/^\/pipeline\/list$/);
  });

  it("leaves the Pipeline unmarked for a posting opened from the Radar, where the cover hides the rail", () => {
    const rail = railOver("/");
    expect(rail.getByRole("link", { name: "Pipeline" })).not.toHaveAttribute("aria-current");
  });
});

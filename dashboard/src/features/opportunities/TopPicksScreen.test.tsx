import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { PicksState } from "../../api";
import { ToastProvider } from "../../ui";
import { forgetPicksDot } from "../../hooks/picksDot";
import { relative } from "../../copy/format";
import { picksStateFixture } from "../../test/fixtures";
import { msg } from "../../test/msg";
import { PickReasons, PicksEnd, PicksNotes, TopPicksScreen } from "./TopPicksScreen";

const picksState = vi.fn<() => Promise<PicksState>>();
const picksOpened = vi.fn<() => Promise<PicksState>>();
const setPicksMode = vi.fn<(state: "on" | "off") => Promise<PicksState>>();
vi.mock("../../api", async (importOriginal) => ({
  ...(await importOriginal<typeof import("../../api")>()),
  api: {
    picksState: () => picksState(),
    picksOpened: () => picksOpened(),
    setPicksMode: (state: "on" | "off") => setPicksMode(state),
  },
}));

beforeEach(() => {
  forgetPicksDot();
  picksState.mockReset();
  picksOpened.mockReset().mockResolvedValue(picksStateFixture());
  setPicksMode.mockReset();
});

const HOURS = 3_600_000;
const hoursAgo = (n: number) => new Date(Date.now() - n * HOURS).toISOString();
const lastCheck = (over: Partial<NonNullable<PicksState["last_check"]>> = {}) => ({
  host: "claude-code", finished_at: hoursAgo(2), outcome: "finished" as const, note: null, ...over,
});

function renderNotes(picks: PicksState, onPicksChange = vi.fn()) {
  render(
    <MemoryRouter>
      <ToastProvider>
        <PicksNotes picks={picks} onPicksChange={onPicksChange} />
      </ToastProvider>
    </MemoryRouter>,
  );
  return onPicksChange;
}

const notes = () => screen.queryAllByRole("note").map((note) => note.textContent);

describe("TopPicksScreen", () => {
  it("records the opening once, which puts out the rail's dot", async () => {
    picksState.mockResolvedValue(picksStateFixture());
    const { rerender } = render(<TopPicksScreen />);
    rerender(<TopPicksScreen />);
    await screen.findByText(msg("picks-not-set-up"));
    expect(picksOpened).toHaveBeenCalledOnce();
  });

  it("names the page in one heading that takes no room, and draws no title block", async () => {
    picksState.mockResolvedValue(picksStateFixture());
    const { container } = render(<TopPicksScreen />);
    const title = screen.getByRole("heading", { level: 1, name: msg("shell-nav-top-picks") });
    expect(title).toHaveClass("sr-only");
    expect(screen.getAllByRole("heading", { level: 1 })).toHaveLength(1);
    expect(container.querySelector(".page-hero")).toBeNull();
  });

  it("says it is not set up until the assistant has set it up", async () => {
    picksState.mockResolvedValue(picksStateFixture({ state: "never_set_up" }));
    render(<TopPicksScreen />);
    expect(await screen.findByText(msg("picks-not-set-up"))).toBeVisible();
  });

  it("says the read failed in place of the body", async () => {
    picksState.mockRejectedValue(new Error("engine away"));
    render(<TopPicksScreen />);
    expect(await screen.findByText(msg("picks-load-failed"))).toBeVisible();
    expect(screen.queryByText(msg("picks-not-set-up"))).toBeNull();
  });
});

describe("PickReasons", () => {
  it("sets each reason's opening fact apart from the rest of its line, with no label", () => {
    const { container } = render(
      <PickReasons reasons={[
        { opening: "Staff level", rest: " at a company that pays at the top of your band." },
        { opening: "Remote", rest: " across the EU, as you asked." },
      ]} />,
    );
    const lines = screen.getAllByRole("listitem");
    expect(lines.map((line) => line.textContent)).toEqual([
      "Staff level at a company that pays at the top of your band.",
      "Remote across the EU, as you asked.",
    ]);
    expect(within(lines[0]).getByText("Staff level")).toHaveClass("pick-reason-opening");
    expect(container.textContent).not.toMatch(/why|catch/i);
  });

  it("marks every word of a reason as the assistant's, never to be translated", () => {
    render(<PickReasons reasons={[{ opening: "Staff level", rest: " at a company that pays at the top of your band." }]} />);
    const parts = [...screen.getByRole("listitem").childNodes];
    expect(parts.map((part) => (part as HTMLElement).dataset?.copy)).toEqual(["content", "content"]);
    expect(parts.every((part) => (part as HTMLElement).getAttribute("translate") === "no")).toBe(true);
  });

  it("renders a reason with no opening as a plain line", () => {
    const { container } = render(<PickReasons reasons={[{ opening: "", rest: "Your kind of team, small and senior." }]} />);
    expect(screen.getByRole("listitem")).toHaveTextContent("Your kind of team, small and senior.");
    expect(container.querySelector(".pick-reason-opening")).toBeNull();
  });
});

describe("PicksNotes", () => {
  it("says nothing while the checks are healthy and connected", () => {
    renderNotes(picksStateFixture({ state: "on", health: "healthy", routine_host: "claude-code", routine_host_connection: "connected", last_check: lastCheck() }));
    expect(notes()).toEqual([]);
  });

  it("offers to resume paused checks, and shows the state the resume returns", async () => {
    const resumed = picksStateFixture({ state: "on", health: "healthy" });
    setPicksMode.mockResolvedValue(resumed);
    const onPicksChange = renderNotes(picksStateFixture({ state: "off", health: "off" }));
    expect(notes()).toEqual([`${msg("picks-note-paused")} ${msg("picks-resume")}`]);
    await userEvent.click(screen.getByRole("button", { name: msg("picks-resume") }));
    expect(setPicksMode).toHaveBeenCalledWith("on");
    await vi.waitFor(() => expect(onPicksChange).toHaveBeenCalledWith(resumed));
  });

  it("says a resume failed and leaves the note in place", async () => {
    setPicksMode.mockRejectedValue(new Error("engine away"));
    const onPicksChange = renderNotes(picksStateFixture({ state: "off", health: "off" }));
    await userEvent.click(screen.getByRole("button", { name: msg("picks-resume") }));
    expect(await screen.findByText(msg("picks-resume-failed"))).toBeVisible();
    expect(onPicksChange).not.toHaveBeenCalled();
    expect(screen.getByRole("button", { name: msg("picks-resume") })).toBeEnabled();
  });

  it("says the host asks before each command, with the way to fix it", () => {
    renderNotes(picksStateFixture({ state: "on", health: "healthy", routine_host: "claude-code", routine_host_connection: "rule_missing" }));
    expect(notes()).toEqual([`${msg("picks-note-asks", { host: "Claude Code" })} ${msg("picks-note-fix")}`]);
    expect(screen.getByRole("link", { name: msg("picks-note-fix") })).toHaveAttribute("href", "/settings/intelligence");
  });

  it("says the host is no longer connected when it runs the checks with no connection", () => {
    renderNotes(picksStateFixture({ state: "on", health: "healthy", routine_host: "codex", routine_host_connection: null }));
    expect(notes()).toEqual([`${msg("picks-note-disconnected", { host: "Codex" })} ${msg("picks-note-connect")}`]);
    expect(screen.getByRole("link", { name: msg("picks-note-connect") })).toHaveAttribute("href", "/settings/intelligence");
  });

  it.each([
    ["late", { health: "late" as const, waiting: 14, last_check: lastCheck({ finished_at: hoursAgo(72) }) }],
    ["stopped early", { health: "stopped_early" as const, last_check: lastCheck({ outcome: "stopped", note: "plan limit reached." }) }],
  ])("raises no note while the checks are %s: nothing there asks for an action", (_, over) => {
    renderNotes(picksStateFixture({ state: "on", routine_host: "claude-code", routine_host_connection: "connected", ...over }));
    expect(notes()).toEqual([]);
  });

  it("keeps the note that asks for an action while the checks are also late", () => {
    renderNotes(picksStateFixture({
      state: "on", health: "late", waiting: 3, routine_host: "claude-code", routine_host_connection: "rule_missing",
      last_check: lastCheck({ finished_at: hoursAgo(48) }),
    }));
    expect(notes()).toEqual([`${msg("picks-note-asks", { host: "Claude Code" })} ${msg("picks-note-fix")}`]);
  });
});

describe("PicksEnd", () => {
  const renderEnd = (picks: PicksState) => render(<MemoryRouter><PicksEnd picks={picks} /></MemoryRouter>);
  const checked = (hours: number, host = "claude-code") =>
    msg("picks-end-checked", { when: relative(-hours * 3600), host: msg("picks-host", { host }) });

  it("names the last check and how many roles were passed over this week, as plain text", () => {
    renderEnd(picksStateFixture({ state: "on", passed_this_week: 41, last_check: lastCheck({ host: "codex" }) }));
    expect(screen.getByRole("note")).toHaveTextContent(`${checked(2, "codex")} ${msg("picks-end-passed", { count: 41 })}`);
    expect(screen.queryByRole("link")).toBeNull();
  });

  it("says nothing of what was passed over when nothing was", () => {
    renderEnd(picksStateFixture({ state: "on", passed_this_week: 0, last_check: lastCheck() }));
    expect(screen.getByRole("note").textContent).toBe(checked(2));
  });

  it("says, after the last check, how many roles wait while the checks are late", () => {
    renderEnd(picksStateFixture({
      state: "on", health: "late", waiting: 14, passed_this_week: 41,
      last_check: lastCheck({ finished_at: hoursAgo(72) }),
    }));
    expect(screen.getByRole("note")).toHaveTextContent(
      `${checked(72)} ${msg("picks-end-waiting", { count: 14 })} ${msg("picks-end-passed", { count: 41 })}`,
    );
  });

  it("names no waiting roles while the checks keep up", () => {
    renderEnd(picksStateFixture({ state: "on", health: "healthy", waiting: 14, passed_this_week: 0, last_check: lastCheck() }));
    expect(screen.getByRole("note").textContent).toBe(checked(2));
  });

  it("gives why the last check stopped in the assistant's words, ending the sentence once", () => {
    renderEnd(picksStateFixture({
      state: "on", health: "stopped_early", passed_this_week: 0,
      last_check: lastCheck({ outcome: "stopped", note: "plan limit reached." }),
    }));
    const line = screen.getByRole("note").textContent;
    expect(line).toBe(`${checked(2)} ${msg("picks-end-stopped", { reason: "plan limit reached" })}`);
    expect(line).not.toContain("..");
    // The assistant's words sit in the sentence as content; the sentence around them is copy.
    expect(screen.getByText("plan limit reached")).toHaveAttribute("data-copy", "content");
  });

  it("says a check stopped plainly when it gave no reason", () => {
    renderEnd(picksStateFixture({
      state: "on", health: "stopped_early", passed_this_week: 0,
      last_check: lastCheck({ outcome: "stopped", note: "  " }),
    }));
    expect(screen.getByRole("note")).toHaveTextContent(msg("picks-end-stopped-plain"));
  });

  it("says nothing before any check has run or passed a role over", () => {
    renderEnd(picksStateFixture({ state: "on", passed_this_week: 0, last_check: null }));
    expect(screen.queryByRole("note")).toBeNull();
  });
});

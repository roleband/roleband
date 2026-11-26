import { act, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { AgentAccessState, PicksState, Stats } from "../../api";
import { ToastProvider } from "../../ui";
import { agentAccessFixture, picksSetupFixture, picksStateFixture } from "../../test/fixtures";
import { msg } from "../../test/msg";
import { ONBOARD_POLL_MS, TopPicksOnboarding, setupRows } from "./TopPicksOnboarding";

const picksState = vi.fn<() => Promise<PicksState>>();
const agentAccess = vi.fn<() => Promise<AgentAccessState>>();
const setAgentAccess = vi.fn<(access: { enabled: boolean; allow_writes?: boolean }) => Promise<AgentAccessState>>();
vi.mock("../../api", async (importOriginal) => ({
  ...(await importOriginal<typeof import("../../api")>()),
  api: {
    picksState: () => picksState(),
    agentAccess: () => agentAccess(),
    setAgentAccess: (access: { enabled: boolean; allow_writes?: boolean }) => setAgentAccess(access),
  },
}));

let stats: Pick<Stats, "new_today"> | null = null;
vi.mock("../../context/MissionState", () => ({ useMissionStats: () => stats }));

const SENTENCE = msg("picks-onboard-sentence");
const SHORT = msg("picks-onboard-sentence-connected");
const copyField = (text: string) => screen.getByRole("button", { name: msg("shared-copy-text", { text }) });
const queryCopyField = (text: string) => screen.queryByRole("button", { name: msg("shared-copy-text", { text }) });

/** Access on, and each named app in the state given. */
function access(apps: Partial<Record<"claude-code" | "codex" | "other", Partial<AgentAccessState["apps"][number]>>> = {}, enabled = true): AgentAccessState {
  return {
    ...agentAccessFixture,
    enabled,
    allow_writes: enabled,
    apps: agentAccessFixture.apps.map((app) => ({ ...app, ...apps[app.app] })),
  };
}

beforeEach(() => {
  stats = { new_today: 534 };
  picksState.mockReset().mockReturnValue(new Promise(() => {}));
  agentAccess.mockReset().mockResolvedValue(access());
  setAgentAccess.mockReset();
});

function renderOnboarding(picks: PicksState = picksStateFixture(), onPicksChange = vi.fn()) {
  const view = render(
    <ToastProvider>
      <TopPicksOnboarding picks={picks} onPicksChange={onPicksChange} />
    </ToastProvider>,
  );
  return { ...view, onPicksChange };
}

/** Lets the first poll's answers land. */
const settle = () => act(async () => {});

describe("setupRows", () => {
  it("lists the saved connection, the stage being asked and the one after it, and nothing further", () => {
    expect(setupRows(picksSetupFixture("background", { started: true }))).toEqual([
      { id: "connect", state: "saved" },
      { id: "background", state: "now" },
      { id: "situation", state: "next" },
    ]);
  });

  it("keeps every saved stage, in order, before the one being asked", () => {
    expect(setupRows(picksSetupFixture("rules")).map((row) => `${row.id}:${row.state}`)).toEqual([
      "connect:saved", "background:saved", "situation:saved", "bar:saved", "rules:now", "tradeoffs:next",
    ]);
  });

  it("names a stage that needs roles as waiting where it falls, while setup goes on past it", () => {
    const setup = picksSetupFixture("budget", {
      saved: ["connect", "background", "situation", "bar", "rules", "tradeoffs", "targets"],
      deferred: ["calibration", "trial"],
    });
    expect(setupRows(setup).map((row) => `${row.id}:${row.state}`)).toEqual([
      "connect:saved", "background:saved", "situation:saved", "bar:saved", "rules:saved", "tradeoffs:saved",
      "targets:saved", "calibration:waits", "budget:now", "confirm:next",
    ]);
  });

  it("ends at the last stage, never listing the closing step as a stage", () => {
    const rows = setupRows(picksSetupFixture("routine"));
    expect(rows[rows.length - 1]).toEqual({ id: "routine", state: "now" });
    expect(rows.map((row) => row.id)).not.toContain("done");
  });
});

describe("TopPicksOnboarding before the conversation saves anything", () => {
  it("introduces Top picks and gives the one sentence to say, connecting and starting setup", async () => {
    renderOnboarding();
    await settle();
    expect(screen.getByRole("heading", { level: 2, name: msg("picks-onboard-headline") })).toBeVisible();
    expect(screen.getByText(msg("picks-onboard-line"))).toBeVisible();
    expect(copyField(SENTENCE)).toHaveTextContent("roleband connect --apply");
    expect(screen.getByText(msg("picks-onboard-waiting"))).toHaveAttribute("role", "status");
    expect(screen.getByText(msg("picks-onboard-footnote"))).toBeVisible();
    const steps = screen.getByRole("list", { name: msg("shared-onboard-steps") });
    const items = within(steps).getAllByRole("listitem");
    expect(items.map((item) => item.textContent)).toEqual([
      `1${msg("picks-onboard-step-say")}`, `2${msg("picks-onboard-step-arrive")}`,
    ]);
    expect(items[0]).toHaveAttribute("aria-current", "step");
    expect(items[1]).not.toHaveAttribute("aria-current");
  });

  it("never promises that nothing comes until new roles arrive", async () => {
    const { container } = renderOnboarding();
    await settle();
    expect(container.textContent).not.toMatch(/until new/i);
  });

  it("draws today's count of new roles over the field, and leaves both out when none is counted", async () => {
    const { unmount } = renderOnboarding();
    await settle();
    expect(screen.getByText("534")).toBeVisible();
    expect(screen.getByText(msg("picks-onboard-count", { count: 534 }))).toBeVisible();
    unmount();

    stats = { new_today: 0 };
    renderOnboarding();
    await settle();
    expect(screen.queryByText(msg("picks-onboard-count", { count: 0 }))).toBeNull();
    expect(screen.queryByText("0")).toBeNull();
  });

  it("shows an example pick's two reasons, each with its first fact set apart", async () => {
    renderOnboarding();
    await settle();
    const lead = screen.getByText(msg("picks-onboard-reason-work-lead"));
    expect(lead.tagName).toBe("B");
    expect(lead.closest("li")).toHaveTextContent(
      msg("picks-onboard-reason-work", { lead: msg("picks-onboard-reason-work-lead") }),
    );
    expect(screen.getByText(msg("picks-onboard-reason-more-lead")).closest("li")).toHaveTextContent(
      msg("picks-onboard-reason-more", { lead: msg("picks-onboard-reason-more-lead") }),
    );
  });

  it("asks a connected assistant only for setup, and says it is connected", async () => {
    agentAccess.mockResolvedValue(access({ "claude-code": { connection: "connected" } }));
    renderOnboarding();
    await settle();
    expect(copyField(SHORT)).toBeVisible();
    expect(queryCopyField(SENTENCE)).toBeNull();
    expect(screen.getByText(msg("picks-onboard-connected", { host: "Claude Code" }))).toBeVisible();
    expect(screen.queryByText(msg("picks-onboard-waiting"))).toBeNull();
    expect(screen.queryByRole("button", { name: msg("picks-onboard-terminal") })).toBeNull();
  });

  it("keeps the whole sentence for an assistant whose connection needs the command again", async () => {
    agentAccess.mockResolvedValue(access({ "claude-code": { connection: "rule_missing" }, codex: { connection: "outdated" } }));
    renderOnboarding();
    await settle();
    expect(copyField(SENTENCE)).toBeVisible();
    expect(screen.getByText(msg("picks-onboard-waiting"))).toBeVisible();
  });

  it("offers the switch for assistant apps first while it is off, and turns it on as Settings does", async () => {
    agentAccess.mockResolvedValue(access({}, false));
    setAgentAccess.mockResolvedValue(access());
    renderOnboarding();
    await settle();
    const allow = screen.getByRole("checkbox", { name: msg("ai-assistants-card-allow-assistant-apps-to-connect") });
    expect(allow).not.toBeChecked();
    expect(copyField(SENTENCE)).toBeVisible();
    await userEvent.click(allow);
    expect(setAgentAccess).toHaveBeenCalledExactlyOnceWith({ enabled: true, allow_writes: true });
    expect(screen.queryByRole("checkbox")).toBeNull();
  });

  it("shows no switch while access is unknown or on", async () => {
    agentAccess.mockRejectedValue(new Error("engine away"));
    renderOnboarding();
    await settle();
    expect(screen.queryByRole("checkbox")).toBeNull();
    expect(copyField(SENTENCE)).toBeVisible();
  });

  it("offers Terminal as the fallback: the engine's command for the chosen assistant, then setup in it", async () => {
    agentAccess.mockResolvedValue({
      ...access(),
      connect: [
        { host: "claude-code", command: "roleband connect claude-code --apply" },
        { host: "codex", command: "roleband connect codex --apply" },
      ],
    });
    renderOnboarding();
    await settle();
    await userEvent.click(screen.getByRole("button", { name: msg("picks-onboard-terminal") }));
    expect(queryCopyField(SENTENCE)).toBeNull();
    expect(copyField("roleband connect claude-code --apply")).toBeVisible();
    expect(screen.getByText(msg("picks-onboard-in-host", { host: "Claude Code" }))).toBeVisible();
    expect(copyField(SHORT)).toBeVisible();

    await userEvent.selectOptions(screen.getByRole("combobox", { name: msg("picks-onboard-terminal-host") }), "codex");
    expect(copyField("roleband connect codex --apply")).toBeVisible();
    expect(screen.getByText(msg("picks-onboard-in-host", { host: "Codex" }))).toBeVisible();

    await userEvent.click(screen.getByRole("button", { name: msg("picks-onboard-back") }));
    expect(copyField(SENTENCE)).toBeVisible();
    expect(queryCopyField("roleband connect codex --apply")).toBeNull();
  });
});

describe("TopPicksOnboarding while setup is under way", () => {
  const underWay = (next: PicksState["setup"]["next_step"] = "rules") =>
    picksStateFixture({ setup: picksSetupFixture(next, { started: true }) });

  it("mirrors what the conversation saved, stage by stage, naming the stage it is at", async () => {
    renderOnboarding(underWay("rules"));
    await settle();
    expect(screen.getByRole("heading", { level: 2, name: msg("picks-onboard-under-way") })).toBeVisible();
    const steps = screen.getByRole("list", { name: msg("shared-onboard-steps") });
    const [saved] = screen.getAllByRole("list").filter((list) => list !== steps);
    const rows = within(saved!).getAllByRole("listitem");
    expect(rows.map((row) => row.querySelector("b")?.textContent)).toEqual([
      msg("picks-onboard-row", { step: "connect", host: "Your assistant" }),
      msg("picks-onboard-row", { step: "background", host: "Your assistant" }),
      msg("picks-onboard-row", { step: "situation", host: "Your assistant" }),
      msg("picks-onboard-row", { step: "bar", host: "Your assistant" }),
      msg("picks-onboard-row", { step: "rules", host: "Your assistant" }),
      msg("picks-onboard-row", { step: "tradeoffs", host: "Your assistant" }),
    ]);
    const now = rows.find((row) => row.getAttribute("aria-current") === "step");
    expect(now).toHaveTextContent(msg("picks-onboard-row-now", { step: "rules" }));
    expect(rows.filter((row) => row.textContent?.includes(msg("picks-onboard-row-saved")))).toHaveLength(4);
  });

  it("names the assistant holding the conversation: the one that called last", async () => {
    agentAccess.mockResolvedValue(access({
      "claude-code": { connection: "connected", last_call_at: "2026-11-26T09:00:00Z" },
      codex: { connection: "connected", last_call_at: "2026-11-26T10:00:00Z" },
    }));
    renderOnboarding(underWay("background"));
    await settle();
    expect(screen.getByText(msg("picks-onboard-under-way-line", { host: "Codex" }))).toBeVisible();
    expect(screen.getByText(msg("picks-onboard-row", { step: "connect", host: "Codex" }))).toBeVisible();
  });

  it("gives the sentence that carries setup on in any chat, and no longer the first sentence", async () => {
    renderOnboarding(underWay());
    await settle();
    expect(screen.getByText(msg("picks-onboard-resume"))).toBeVisible();
    expect(copyField(SHORT)).toBeVisible();
    expect(queryCopyField(SENTENCE)).toBeNull();
    expect(screen.queryByRole("heading", { name: msg("picks-onboard-headline") })).toBeNull();
  });
});

describe("TopPicksOnboarding's reads", () => {
  it("reads the state again while on screen and hands each answer to the screen", async () => {
    vi.useFakeTimers();
    try {
      const saved = picksStateFixture({ setup: picksSetupFixture("situation") });
      picksState.mockResolvedValueOnce(picksStateFixture()).mockResolvedValueOnce(saved);
      const { onPicksChange } = renderOnboarding();
      await settle();
      expect(picksState).toHaveBeenCalledTimes(1);
      await act(async () => {
        vi.advanceTimersByTime(ONBOARD_POLL_MS);
      });
      expect(picksState).toHaveBeenCalledTimes(2);
      expect(onPicksChange).toHaveBeenLastCalledWith(saved);
    } finally {
      vi.useRealTimers();
    }
  });

  it("drops an answer that a later read overtook", async () => {
    vi.useFakeTimers();
    try {
      let answerFirst: (state: PicksState) => void = () => {};
      const stale = picksStateFixture();
      const fresh = picksStateFixture({ state: "on" });
      picksState
        .mockReturnValueOnce(new Promise((resolve) => { answerFirst = resolve; }))
        .mockResolvedValueOnce(fresh);
      const { onPicksChange } = renderOnboarding();
      await act(async () => {
        vi.advanceTimersByTime(ONBOARD_POLL_MS);
      });
      expect(onPicksChange).toHaveBeenCalledExactlyOnceWith(fresh);
      await act(async () => answerFirst(stale));
      expect(onPicksChange).toHaveBeenCalledExactlyOnceWith(fresh);
    } finally {
      vi.useRealTimers();
    }
  });
});

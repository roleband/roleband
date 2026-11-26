import { cleanup, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { api, type PicksState } from "../../api";
import { relative } from "../../copy/format";
import { picksStateFixture } from "../../test/fixtures";
import { msg } from "../../test/msg";
import { ToastProvider } from "../../ui";
import { statusCase, TopPicksCard } from "./TopPicksCard";

vi.mock("../../api", () => ({
  api: {
    picksState: vi.fn(),
    setPicksMode: vi.fn(),
    setPicksDailyLimit: vi.fn(),
    removePicksSetup: vi.fn(),
  },
}));

const mocked = vi.mocked(api);

const HOURS = 3_600_000;
const hoursAgo = (n: number) => new Date(Date.now() - n * HOURS).toISOString();

const BRIEF = "Beats a Senior Director of Engineering offer at 352,000 base. Principal or director level and above.";

/** Top picks set up and checking: Claude Code checked two hours ago. */
function setUp(overrides: Partial<PicksState> = {}): PicksState {
  return picksStateFixture({
    state: "on",
    routine_host: "claude-code",
    schedule: "daily 09:30 and 17:30",
    last_check: { host: "claude-code", finished_at: hoursAgo(2), outcome: "finished", note: null },
    brief_summary: BRIEF,
    health: "healthy",
    routine_host_connection: "connected",
    daily_limit: 1000,
    daily_limit_max: 5000,
    ...overrides,
  });
}

const claude = () => msg("picks-host", { host: "claude-code" });
const twoHoursAgo = () => relative(-2 * 3600);

function mount() {
  return render(
    <ToastProvider>
      <TopPicksCard />
    </ToastProvider>,
  );
}

/** Mounts the card and waits for it to read its state. */
async function card() {
  mount();
  return screen.findByRole("region", { name: msg("shell-nav-top-picks") });
}

/** Nothing of the card is on screen: no region, no switch, no Remove. */
function expectNoCard() {
  expect(screen.queryByRole("region", { name: msg("shell-nav-top-picks") })).not.toBeInTheDocument();
  expect(screen.queryByRole("checkbox", { name: msg("ai-top-picks-card-check") })).not.toBeInTheDocument();
  expect(screen.queryByRole("button", { name: msg("ai-top-picks-card-remove") })).not.toBeInTheDocument();
}

const theSwitch = (region: HTMLElement) =>
  within(region).getByRole("checkbox", { name: msg("ai-top-picks-card-check") });
const limitField = (region: HTMLElement) =>
  within(region).getByLabelText(msg("ai-top-picks-card-limit"));

beforeEach(() => {
  vi.clearAllMocks();
});

afterEach(cleanup);

describe("TopPicksCard: shown only once Top picks is set up", () => {
  it("draws nothing before setup", async () => {
    mocked.picksState.mockResolvedValue(picksStateFixture({ state: "never_set_up" }));
    mount();
    await waitFor(() => expect(mocked.picksState).toHaveBeenCalledTimes(1));
    // Let the read settle before asserting nothing came of it.
    await new Promise((resolve) => setTimeout(resolve, 0));
    expectNoCard();
  });

  it("draws nothing when the state cannot be read", async () => {
    mocked.picksState.mockRejectedValue(new Error("offline"));
    mount();
    await waitFor(() => expect(mocked.picksState).toHaveBeenCalledTimes(1));
    await new Promise((resolve) => setTimeout(resolve, 0));
    expectNoCard();
  });

  it("draws the five parts once set up, with the brief as read-only text", async () => {
    mocked.picksState.mockResolvedValue(setUp());
    const region = await card();
    expect(theSwitch(region)).toBeChecked();
    expect(within(region).getByText(BRIEF)).toBeInTheDocument();
    // Read-only: nothing on the card edits what the person is looking for.
    expect(within(region).queryByRole("textbox", { name: msg("ai-top-picks-card-brief") })).not.toBeInTheDocument();
    expect(limitField(region)).toHaveValue("1000");
    expect(within(region).getByRole("button", { name: msg("ai-top-picks-card-remove") })).toBeInTheDocument();
    expect(within(region).getByRole("button", {
      name: msg("ai-top-picks-card-copy-sentence", { sentence: msg("ai-top-picks-card-sentence") }),
    })).toBeInTheDocument();
  });

  it("says the assistant has not written the brief down while it has no summary", async () => {
    mocked.picksState.mockResolvedValue(setUp({ brief_summary: null }));
    const region = await card();
    expect(within(region).getByText(msg("ai-top-picks-card-brief-none"))).toBeInTheDocument();
  });
});

describe("TopPicksCard: the switch", () => {
  it("is on while the checks run, and turning it off pauses them", async () => {
    mocked.picksState.mockResolvedValue(setUp());
    mocked.setPicksMode.mockResolvedValue(setUp({ state: "off", health: "off" }));
    const user = userEvent.setup();
    const region = await card();

    await user.click(theSwitch(region));

    expect(mocked.setPicksMode).toHaveBeenCalledExactlyOnceWith("off");
    await waitFor(() => expect(theSwitch(region)).not.toBeChecked());
    expect(region).toHaveTextContent(
      msg("ai-top-picks-card-status", { state: "paused-checked", host: claude(), when: twoHoursAgo() }),
    );
  });

  it("is off while paused, and turning it on resumes the checks", async () => {
    mocked.picksState.mockResolvedValue(setUp({ state: "off", health: "off" }));
    mocked.setPicksMode.mockResolvedValue(setUp());
    const user = userEvent.setup();
    const region = await card();
    expect(theSwitch(region)).not.toBeChecked();

    await user.click(theSwitch(region));

    expect(mocked.setPicksMode).toHaveBeenCalledExactlyOnceWith("on");
    await waitFor(() => expect(theSwitch(region)).toBeChecked());
  });

  it("keeps the saved state and says so when the change fails", async () => {
    mocked.picksState.mockResolvedValue(setUp({ state: "off", health: "off" }));
    mocked.setPicksMode.mockRejectedValue(new Error("refused"));
    const user = userEvent.setup();
    const region = await card();

    await user.click(theSwitch(region));

    expect(await within(region).findByRole("alert")).toHaveTextContent(msg("picks-resume-failed"));
    expect(theSwitch(region)).not.toBeChecked();
  });
});

describe("TopPicksCard: the status line", () => {
  const cases: {
    name: string;
    state: Partial<PicksState>;
    expected: () => string;
    attention: boolean;
    schedule: boolean;
  }[] = [
    {
      name: "a finished check: who checked and when, then the schedule",
      state: {},
      expected: () => msg("ai-top-picks-card-status", { state: "checked", host: claude(), when: twoHoursAgo() }),
      attention: false,
      schedule: true,
    },
    {
      name: "no check yet: who will check, then the schedule",
      state: { last_check: null, health: "never_ran" },
      expected: () => msg("ai-top-picks-card-status", { state: "first", host: claude(), when: "" }),
      attention: false,
      schedule: true,
    },
    {
      name: "late: when the last check was",
      state: { health: "late", waiting: 40 },
      expected: () => msg("ai-top-picks-card-status", { state: "late", host: claude(), when: twoHoursAgo() }),
      attention: true,
      schedule: false,
    },
    {
      name: "the last check stopped early",
      state: {
        health: "stopped_early",
        last_check: { host: "claude-code", finished_at: hoursAgo(2), outcome: "stopped", note: "Usage limit" },
      },
      expected: () => msg("ai-top-picks-card-status", { state: "stopped", host: claude(), when: twoHoursAgo() }),
      attention: true,
      schedule: false,
    },
    {
      name: "the assistant is no longer connected, whatever the last check said",
      state: { routine_host_connection: null },
      expected: () => msg("ai-top-picks-card-status", { state: "disconnected", host: claude(), when: "" }),
      attention: true,
      schedule: false,
    },
    {
      name: "the assistant asks before each command",
      state: { routine_host_connection: "rule_missing", health: "late" },
      expected: () => msg("ai-top-picks-card-status", { state: "asks", host: claude(), when: "" }),
      attention: true,
      schedule: false,
    },
    {
      name: "Codex in read-only mode",
      state: {
        routine_host: "codex",
        routine_host_connection: "read_only",
        last_check: { host: "codex", finished_at: hoursAgo(2), outcome: "finished", note: null },
      },
      expected: () => msg("ai-top-picks-card-status", {
        state: "read-only", host: msg("picks-host", { host: "codex" }), when: "",
      }),
      attention: true,
      schedule: false,
    },
    {
      name: "paused after a check: when it last checked",
      state: { state: "off", health: "off" },
      expected: () => msg("ai-top-picks-card-status", { state: "paused-checked", host: claude(), when: twoHoursAgo() }),
      attention: false,
      schedule: false,
    },
    {
      name: "paused before any check",
      state: { state: "off", health: "off", last_check: null },
      expected: () => msg("ai-top-picks-card-status", { state: "paused", host: claude(), when: "" }),
      attention: false,
      schedule: false,
    },
  ];

  it.each(cases)("$name", async ({ state, expected, attention, schedule }) => {
    mocked.picksState.mockResolvedValue(setUp(state));
    const region = await card();
    const line = expected();
    expect(region).toHaveTextContent(line);
    if (schedule) expect(region).toHaveTextContent(`${line} · daily 09:30 and 17:30`);
    else expect(region).not.toHaveTextContent("daily 09:30 and 17:30");
    // The warning dot marks only a state that needs the person's eye.
    expect(region.querySelector(".intel-dot.is-warn") != null).toBe(attention);
  });

  it("names who made the last check when no assistant is set to run them", async () => {
    mocked.picksState.mockResolvedValue(setUp({
      routine_host: null,
      routine_host_connection: null,
      last_check: { host: "codex", finished_at: hoursAgo(2), outcome: "finished", note: null },
    }));
    const region = await card();
    expect(region).toHaveTextContent(msg("ai-top-picks-card-status", {
      state: "checked", host: msg("picks-host", { host: "codex" }), when: twoHoursAgo(),
    }));
  });

  it("puts a connection that stops the checks before how the last one ended", () => {
    expect(statusCase(setUp({ health: "stopped_early", routine_host_connection: null }))).toBe("disconnected");
    expect(statusCase(setUp({ health: "late", routine_host_connection: "rule_missing" }))).toBe("asks");
    // Off says only that it is off, whatever the connection says.
    expect(statusCase(setUp({ state: "off", routine_host_connection: null }))).toBe("paused-checked");
    // An older skill still runs the checks.
    expect(statusCase(setUp({ routine_host_connection: "outdated" }))).toBe("checked");
  });
});

describe("TopPicksCard: the daily limit", () => {
  async function typeLimit(text: string, end: "{Enter}" | "{Tab}" = "{Enter}") {
    const user = userEvent.setup();
    const region = await card();
    const field = limitField(region);
    await user.clear(field);
    await user.type(field, `${text}${end}`);
    return { region, field };
  }

  beforeEach(() => {
    mocked.picksState.mockResolvedValue(setUp());
    mocked.setPicksDailyLimit.mockImplementation(async (limit) => setUp({ daily_limit: limit }));
  });

  it("saves a whole number in range on Enter", async () => {
    const { field } = await typeLimit("250");
    expect(mocked.setPicksDailyLimit).toHaveBeenCalledExactlyOnceWith(250);
    await waitFor(() => expect(field).toHaveValue("250"));
    expect(field).not.toHaveAttribute("aria-invalid");
  });

  it("saves on leaving the field", async () => {
    await typeLimit("5000", "{Tab}");
    expect(mocked.setPicksDailyLimit).toHaveBeenCalledExactlyOnceWith(5000);
  });

  it("sends a limit once when Enter is followed by leaving the field during the save", async () => {
    let answer!: (state: PicksState) => void;
    mocked.setPicksDailyLimit.mockImplementation(() => new Promise((resolve) => { answer = resolve; }));
    const { field } = await typeLimit("250");
    // The keyboard stays in the field while it saves.
    expect(field).toHaveFocus();
    await userEvent.setup().tab();
    expect(mocked.setPicksDailyLimit).toHaveBeenCalledExactlyOnceWith(250);
    answer(setUp({ daily_limit: 250 }));
    await waitFor(() => expect(field).toHaveValue("250"));
    expect(mocked.setPicksDailyLimit).toHaveBeenCalledOnce();
  });

  it("sends no limit while the switch's change is still saving, and keeps what was typed", async () => {
    mocked.setPicksDailyLimit.mockRejectedValueOnce(new Error("refused"));
    let answer!: (state: PicksState) => void;
    mocked.setPicksMode.mockImplementation(() => new Promise((resolve) => { answer = resolve; }));
    const user = userEvent.setup();
    // The save fails as the person leaves the field, so the pause starts with
    // the field out of focus and what was typed still unsaved.
    const { region, field } = await typeLimit("250", "{Tab}");
    expect(await within(region).findByRole("alert")).toHaveTextContent(msg("ai-top-picks-card-limit-failed"));
    await user.click(within(region).getByRole("checkbox", { name: msg("ai-top-picks-card-check") }));
    expect(mocked.setPicksMode).toHaveBeenCalledExactlyOnceWith("off");
    await user.click(field);
    await user.keyboard("{Enter}");
    expect(mocked.setPicksDailyLimit).toHaveBeenCalledOnce();
    expect(field).toHaveValue("250");
    // Once the switch's change is saved, Enter sends the limit.
    answer(setUp({ state: "off", health: "off" }));
    await waitFor(() => expect(field).not.toHaveAttribute("readonly"));
    mocked.setPicksDailyLimit.mockImplementation(async (limit) => setUp({ state: "off", health: "off", daily_limit: limit }));
    await user.keyboard("{Enter}");
    expect(mocked.setPicksDailyLimit).toHaveBeenCalledTimes(2);
    expect(mocked.setPicksDailyLimit).toHaveBeenLastCalledWith(250);
  });

  it("sends nothing when the limit did not change", async () => {
    await typeLimit("1000");
    expect(mocked.setPicksDailyLimit).not.toHaveBeenCalled();
  });

  it.each([
    ["0", "zero"],
    ["5001", "one above the most it can be"],
    ["2.5", "a fraction"],
    ["-3", "a negative number"],
    ["many", "words"],
    ["", "nothing"],
  ])("refuses %s (%s): marks the field, says the range, sends nothing", async (text) => {
    const { region, field } = await typeLimit(text);
    await userEvent.setup().tab();
    expect(mocked.setPicksDailyLimit).not.toHaveBeenCalled();
    expect(field).toHaveAttribute("aria-invalid", "true");
    expect(within(region).getByRole("alert")).toHaveTextContent(msg("ai-top-picks-card-limit-range", { max: 5000 }));
    expect(field).toHaveAccessibleDescription(expect.stringContaining(msg("ai-top-picks-card-limit-range", { max: 5000 })));
  });

  it("takes the most the state allows, not a fixed number", async () => {
    mocked.picksState.mockResolvedValue(setUp({ daily_limit: 100, daily_limit_max: 300 }));
    const { region } = await typeLimit("301");
    expect(mocked.setPicksDailyLimit).not.toHaveBeenCalled();
    expect(within(region).getByRole("alert")).toHaveTextContent(msg("ai-top-picks-card-limit-range", { max: 300 }));
  });

  it("says when the save fails and keeps what was typed", async () => {
    mocked.setPicksDailyLimit.mockRejectedValue(new Error("refused"));
    const { region, field } = await typeLimit("250");
    expect(await within(region).findByRole("alert")).toHaveTextContent(msg("ai-top-picks-card-limit-failed"));
    expect(field).toHaveValue("250");
  });
});

describe("TopPicksCard: Remove", () => {
  beforeEach(() => {
    mocked.picksState.mockResolvedValue(setUp());
  });

  const dialog = () => screen.getByRole("dialog", { name: msg("ai-top-picks-card-remove-confirm-title") });

  it("asks first, and Cancel deletes nothing", async () => {
    const user = userEvent.setup();
    const region = await card();

    await user.click(within(region).getByRole("button", { name: msg("ai-top-picks-card-remove") }));

    expect(dialog()).toHaveTextContent(msg("ai-top-picks-card-remove-confirm"));
    expect(mocked.removePicksSetup).not.toHaveBeenCalled();

    await user.click(within(dialog()).getByRole("button", { name: msg("ai-aim-line-cancel") }));

    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(mocked.removePicksSetup).not.toHaveBeenCalled();
    expect(region).toBeInTheDocument();
  });

  it("removes on confirm only, then the card is gone and a toast says so", async () => {
    mocked.removePicksSetup.mockResolvedValue({ briefs: 1, readings: 2, documents: 1, verdicts: 18 });
    const user = userEvent.setup();
    const region = await card();

    await user.click(within(region).getByRole("button", { name: msg("ai-top-picks-card-remove") }));
    await user.click(within(dialog()).getByRole("button", { name: msg("ai-top-picks-card-remove") }));

    expect(mocked.removePicksSetup).toHaveBeenCalledTimes(1);
    await waitFor(() => expect(screen.queryByRole("region", { name: msg("shell-nav-top-picks") })).not.toBeInTheDocument());
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(await screen.findByText(msg("ai-top-picks-card-removed"))).toBeInTheDocument();
  });

  it("keeps the card and the question open when Remove fails", async () => {
    mocked.removePicksSetup.mockRejectedValue(new Error("refused"));
    const user = userEvent.setup();
    const region = await card();

    await user.click(within(region).getByRole("button", { name: msg("ai-top-picks-card-remove") }));
    await user.click(within(dialog()).getByRole("button", { name: msg("ai-top-picks-card-remove") }));

    expect(await within(dialog()).findByRole("alert")).toHaveTextContent(msg("ai-top-picks-card-remove-failed"));
    expect(screen.getByRole("region", { name: msg("shell-nav-top-picks") })).toBeInTheDocument();
  });
});

describe("TopPicksCard: the sentence to say", () => {
  const writeText = vi.fn(async (_text: string) => {});

  /** userEvent.setup() installs its own clipboard, so this one lands after it. */
  function setupUser() {
    const user = userEvent.setup();
    Object.defineProperty(navigator, "clipboard", { value: { writeText }, configurable: true, writable: true });
    return user;
  }

  beforeEach(() => {
    writeText.mockReset();
    mocked.picksState.mockResolvedValue(setUp());
  });

  const copyButton = (region: HTMLElement) => within(region).getByRole("button", {
    name: msg("ai-top-picks-card-copy-sentence", { sentence: msg("ai-top-picks-card-sentence") }),
  });

  it("copies the sentence and says it was copied", async () => {
    writeText.mockResolvedValue(undefined);
    const user = setupUser();
    const region = await card();

    await user.click(copyButton(region));

    expect(writeText).toHaveBeenCalledExactlyOnceWith(msg("ai-top-picks-card-sentence"));
    expect(await within(region).findByRole("status")).toHaveTextContent(msg("ai-assistants-card-copy", { choice: "yes" }));
  });

  it("says how to copy it by hand when the clipboard is blocked", async () => {
    writeText.mockRejectedValue(new Error("denied"));
    const user = setupUser();
    const region = await card();

    await user.click(copyButton(region));

    expect(await within(region).findByRole("alert")).toHaveTextContent(msg("ai-assistants-card-clipboard-access-was-blocked-select"));
  });
});

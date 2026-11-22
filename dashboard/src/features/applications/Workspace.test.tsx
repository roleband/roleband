import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useState } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { ActivityItem, ApplicationCard, ApplicationDetail, ApplicationStep } from "../../api";
import { applicationCardFixture, applicationDetailFixture, stepFixture } from "../../test/fixtures";
import { msg } from "../../test/msg";
import { date as formatDate } from "../../copy/format";
import { ToastProvider, useEscapeLayer } from "../../ui";
import { dayKey, dueFromDay } from "./monthGrid";
import { Workspace, type WorkspaceProps } from "./Workspace";
import { readViewChoices } from "../../hooks/viewChoicesRead";
import { fakeViewChoiceServer } from "../../test/viewChoicesServer";

/* A role's Workspace: its blocks, each a card, with the role's activity among
 * them. The handlers stand in for the posting's writes; comments are kept in
 * a small store so a posted one shows. */

const DAY = 86_400_000;
const NOW = new Date("2026-11-21T12:00:00Z");
const changes = () => `${msg("applications-feed-moved", { stage: "Applied" })} and ${msg("applications-feed-priority")}`;
const fold = () => msg("applications-feed-fold", { count: 2, changes: changes() });

/** A month divider's name: the catalogue's jump label around any month. */
const isMonthDivider = (name: string) => {
  const [before, after] = msg("applications-feed-jump-month", { month: "\u0000" }).split("\u0000");
  return name.length > before.length + after.length && name.startsWith(before) && name.endsWith(after);
};

let items: ActivityItem[];
let detail: ApplicationDetail;
let handlers: Pick<
  WorkspaceProps,
  "onAddStep" | "onEditStep" | "onFinishStep" | "onReopenStep" | "onRemoveStep" | "onAddComment" | "onEditComment" | "onDeleteComment" | "onSaveNotes" | "onLoadNotesVersions" | "onEditInterview"
>;

// The person's view choices, the Workspace's layouts among them, read before each test.
beforeEach(async () => {
  fakeViewChoiceServer();
  await readViewChoices();
});

beforeEach(() => {
  localStorage.clear();
  detail = applicationDetailFixture({
    application: applicationCardFixture({ job_id: 101, stage: "applied", next_action: null, next_action_due: null }),
    stages_reached: [
      { stage: "saved", at: "2026-10-20T09:00:00Z" },
      { stage: "applied", at: "2026-11-02T10:00:00Z" },
    ],
  });
  items = [
    { kind: "comment", id: 7, created_at: "2026-11-03T10:00:00Z", actor: "agent", source: "agent_api", body: "Found the hiring manager.", edited_at: null },
    { kind: "event", id: 6, created_at: "2026-11-02T10:00:00Z", actor: "user", source: "app", event_type: "updated", from_stage: "researching", to_stage: "applied", changed: ["stage"] },
    { kind: "event", id: 5, created_at: "2026-11-01T10:00:00Z", actor: "user", source: "app", event_type: "updated", from_stage: "researching", to_stage: "researching", changed: ["priority"] },
  ];
  handlers = {
    onAddStep: vi.fn(async () => true),
    onEditStep: vi.fn(async () => true),
    onFinishStep: vi.fn(),
    onReopenStep: vi.fn(async () => true),
    onRemoveStep: vi.fn(async () => true),
    onAddComment: vi.fn(async () => true),
    onEditComment: vi.fn(async () => true),
    onDeleteComment: vi.fn(async () => true),
    onSaveNotes: vi.fn(async () => true),
    onLoadNotesVersions: vi.fn(async () => []),
    onEditInterview: vi.fn(),
  };
});

/** The Workspace with the screen's own answer to a tick, a reopen or a
 *  removal: a ticked step moves from the card to the done steps and back. */
function Harness({ card: initial, done: initialDone = [] }: { card: ApplicationCard; done?: ApplicationStep[] }) {
  const [feed, setFeed] = useState(items);
  const [card, setCard] = useState(initial);
  const [done, setDone] = useState(initialDone);
  const drop = (step: ApplicationStep) => {
    setCard((was) => ({ ...was, steps: was.steps.filter((one) => one.id !== step.id) }));
    setDone((was) => was.filter((one) => one.id !== step.id));
  };
  return (
    <ToastProvider>
      <Workspace
        card={card}
        detail={{ ...detail, application: card, done_steps: done }}
        notes={null}
        activity={feed}
        now={NOW}
        onAddStep={handlers.onAddStep}
        onEditStep={handlers.onEditStep}
        onFinishStep={(step) => {
          handlers.onFinishStep(step);
          drop(step);
          setDone((was) => [{ ...step, done_at: NOW.toISOString() }, ...was]);
        }}
        onReopenStep={async (step) => {
          const reopened = await handlers.onReopenStep(step);
          if (reopened) {
            drop(step);
            setCard((was) => ({ ...was, steps: [...was.steps, { ...step, done_at: null }] }));
          }
          return reopened;
        }}
        onRemoveStep={async (step) => {
          const removed = await handlers.onRemoveStep(step);
          if (removed) drop(step);
          return removed;
        }}
        onSaveNotes={handlers.onSaveNotes}
        onLoadNotesVersions={handlers.onLoadNotesVersions}
        onAddInterview={vi.fn()}
        onEditInterview={handlers.onEditInterview}
        onOutcome={vi.fn()}
        onAddComment={async (body) => {
          const saved = await handlers.onAddComment(body);
          if (saved) {
            setFeed((was) => [
              { kind: "comment", id: 99, created_at: NOW.toISOString(), actor: "user", source: "app", body, edited_at: null },
              ...was,
            ]);
          }
          return saved;
        }}
        onEditComment={handlers.onEditComment}
        onDeleteComment={handlers.onDeleteComment}
      />
    </ToastProvider>
  );
}

/** The Workspace of the role with these fields changed; a card given a
 *  next step lists it as its one step, as the server's does. */
function renderWorkspace(card: Partial<ApplicationCard> = {}, done: ApplicationStep[] = []) {
  return render(<Harness card={applicationCardFixture({ ...detail.application, steps: undefined, ...card })} done={done} />);
}

const block = (name: string) => screen.getByRole("region", { name });
/** The blocks on the page, in order, by their captions. */
const blockNames = () => Array.from(document.querySelectorAll("[data-section] .app-ws-label"), (caption) => caption.textContent);
const NEXT = () => msg("applications-ws-next");
const NOTES = () => msg("applications-notes-title");
const ACTIVITY = () => msg("applications-feed-title");
const activity = () => block(ACTIVITY());
/** Whether a line can be seen: a folded run keeps its changes on the page
 *  only hidden, or leaves them out. */
const seen = (feed: HTMLElement, text: string) => {
  const line = within(feed).queryByText(text);
  return line != null && line.closest("[hidden]") == null;
};
/** Runs `check` in a browser that can, or cannot, search hidden text. */
async function withHiddenSearch(can: boolean, check: () => Promise<void>) {
  const own = Object.getOwnPropertyDescriptor(HTMLElement.prototype, "onbeforematch");
  if (can) Object.defineProperty(HTMLElement.prototype, "onbeforematch", { configurable: true, writable: true, value: null });
  else delete (HTMLElement.prototype as unknown as Record<string, unknown>).onbeforematch;
  try {
    await check();
  } finally {
    if (own) Object.defineProperty(HTMLElement.prototype, "onbeforematch", own);
    else delete (HTMLElement.prototype as unknown as Record<string, unknown>).onbeforematch;
  }
}
const hideButton = (section: string) => screen.queryByRole("button", { name: msg("applications-ws-hide", { section }) });
const moveButton = (section: string) => screen.queryByRole("button", { name: msg("applications-ws-move", { section }) });
const addButton = () => screen.queryByRole("button", { name: msg("applications-ws-add") });

describe("the Workspace's blocks", () => {
  it("draws the stage's blocks as cards named by their captions, in the stage's order", () => {
    renderWorkspace();
    expect(blockNames()).toEqual([NEXT(), NOTES(), ACTIVITY()]);
    // Nothing is hidden on a first visit, so there is nothing to add back.
    expect(addButton()).toBeNull();
  });

  it("hides a block by its eye, says so with a way back, and hands focus to the next block's eye", async () => {
    renderWorkspace();
    await userEvent.click(hideButton(NOTES())!);
    expect(screen.queryByRole("region", { name: NOTES() })).toBeNull();
    expect(blockNames()).toEqual([NEXT(), ACTIVITY()]);
    await waitFor(() => expect(hideButton(ACTIVITY())).toHaveFocus());

    const status = screen.getByRole("status");
    expect(status).toHaveTextContent(msg("applications-ws-hidden", { section: NOTES() }));
    await userEvent.click(within(status).getByRole("button", { name: msg("applications-move-undo") }));
    expect(blockNames()).toEqual([NEXT(), NOTES(), ACTIVITY()]);
  });

  it("remembers a hidden block for the stage on the next visit", async () => {
    const { unmount } = renderWorkspace();
    await userEvent.click(hideButton(ACTIVITY())!);
    unmount();
    renderWorkspace();
    expect(blockNames()).toEqual([NEXT(), NOTES()]);
  });

  it("brings a hidden block back from the plus, which names what each one holds", async () => {
    renderWorkspace();
    await userEvent.click(hideButton(NOTES())!);
    await userEvent.click(addButton()!);
    const menu = await screen.findByRole("dialog", { name: msg("applications-ws-add") });
    // Only what is hidden is offered.
    expect(within(menu).queryByText(NEXT())).toBeNull();
    expect(within(menu).getByText(msg("applications-ws-about-notes"))).toBeInTheDocument();
    await userEvent.click(within(menu).getByText(NOTES()));

    expect(blockNames()).toEqual([NEXT(), NOTES(), ACTIVITY()]);
    await waitFor(() => expect(hideButton(NOTES())).toHaveFocus());
    // Nothing is left to add back, so the plus goes.
    expect(addButton()).toBeNull();
  });

  it("keeps the last block shown: it has no eye and no grip", async () => {
    renderWorkspace();
    await userEvent.click(hideButton(NOTES())!);
    await userEvent.click(hideButton(ACTIVITY())!);
    expect(blockNames()).toEqual([NEXT()]);
    expect(hideButton(NEXT())).toBeNull();
    expect(moveButton(NEXT())).toBeNull();
  });

  it("hands focus to the caption of the block left alone, which has no eye to take it", async () => {
    renderWorkspace();
    await userEvent.click(hideButton(NOTES())!);
    await userEvent.click(hideButton(ACTIVITY())!);
    expect(blockNames()).toEqual([NEXT()]);
    await waitFor(() => expect(screen.getByRole("heading", { name: NEXT() })).toHaveFocus());
  });

  it("moves a block from its grip's menu, keeps focus on the grip, and remembers the order", async () => {
    const { unmount } = renderWorkspace();
    await userEvent.click(moveButton(NEXT())!);
    const menu = await screen.findByRole("dialog", { name: msg("applications-ws-move", { section: NEXT() }) });
    // The first block cannot go higher.
    expect(within(menu).getByRole("button", { name: msg("applications-ws-move-up") })).toBeDisabled();
    await userEvent.click(within(menu).getByRole("button", { name: msg("applications-ws-move-down") }));

    expect(blockNames()).toEqual([NOTES(), NEXT(), ACTIVITY()]);
    await waitFor(() => expect(moveButton(NEXT())).toHaveFocus());
    unmount();
    renderWorkspace();
    expect(blockNames()).toEqual([NOTES(), NEXT(), ACTIVITY()]);
  });

  it("moves a block past a hidden one, so one step is always one place on the page", async () => {
    renderWorkspace();
    await userEvent.click(hideButton(NOTES())!);
    await userEvent.click(moveButton(NEXT())!);
    const menu = await screen.findByRole("dialog", { name: msg("applications-ws-move", { section: NEXT() }) });
    await userEvent.click(within(menu).getByRole("button", { name: msg("applications-ws-move-down") }));
    expect(blockNames()).toEqual([ACTIVITY(), NEXT()]);
  });

  it("drags a block by its grip to another place", () => {
    renderWorkspace();
    const dataTransfer = { setData: vi.fn(), effectAllowed: "", dropEffect: "" };
    const next = block(NEXT());
    const target = activity();
    fireEvent.pointerDown(moveButton(NEXT())!);
    fireEvent.dragStart(next, { dataTransfer });
    expect(next).toHaveAttribute("data-dragged");
    // jsdom lays nothing out, so every point is past a card's middle: after it.
    fireEvent.dragOver(target, { dataTransfer, clientY: 10 });
    expect(target).toHaveAttribute("data-drop", "after");
    fireEvent.drop(target, { dataTransfer, clientY: 10 });
    fireEvent.dragEnd(next, { dataTransfer });

    expect(blockNames()).toEqual([NOTES(), ACTIVITY(), NEXT()]);
    expect(document.querySelector("[data-dragged], [data-drop]")).toBeNull();
  });

  it("drags nothing from the card itself, so text in it can still be selected", () => {
    renderWorkspace();
    const dataTransfer = { setData: vi.fn(), effectAllowed: "", dropEffect: "" };
    const next = block(NEXT());
    expect(next).toHaveAttribute("draggable", "false");
    fireEvent.dragStart(next, { dataTransfer });
    fireEvent.dragOver(activity(), { dataTransfer, clientY: 10 });
    fireEvent.drop(activity(), { dataTransfer, clientY: 10 });
    expect(blockNames()).toEqual([NEXT(), NOTES(), ACTIVITY()]);

    // A press on the grip that ends without a drag leaves the card as it was.
    fireEvent.pointerDown(moveButton(NEXT())!);
    expect(next).toHaveAttribute("draggable", "true");
    fireEvent.pointerUp(window);
    expect(next).toHaveAttribute("draggable", "false");
  });
});

describe("the Workspace's activity", () => {
  it("is one stream with no view to pick: comments read whole and the changes between them fold into one line", async () => {
    renderWorkspace();
    const feed = activity();
    expect(within(feed).queryAllByRole("button", { pressed: true })).toEqual([]);
    expect(within(feed).queryAllByRole("button", { pressed: false })).toEqual([]);
    expect(within(feed).getByText("Found the hiring manager.")).toBeInTheDocument();
    const toggle = within(feed).getByRole("button", { name: fold() });
    expect(toggle).toHaveAttribute("aria-expanded", "false");
    expect(seen(feed, msg("applications-feed-priority"))).toBe(false);

    await userEvent.click(toggle);
    expect(toggle).toHaveAttribute("aria-expanded", "true");
    expect(seen(feed, msg("applications-feed-moved", { stage: "Applied" }))).toBe(true);
    expect(seen(feed, msg("applications-feed-priority"))).toBe(true);

    await userEvent.click(toggle);
    expect(toggle).toHaveAttribute("aria-expanded", "false");
    expect(seen(feed, msg("applications-feed-priority"))).toBe(false);
  });

  it("keeps a folded run's changes where the browser's find reaches them, and opens the run on a match", async () => {
    await withHiddenSearch(true, async () => {
      renderWorkspace();
      const feed = activity();
      const toggle = within(feed).getByRole("button", { name: fold() });
      const folded = within(feed).getByText(msg("applications-feed-priority")).closest("ol")!;
      expect(folded, "on the page, hidden but searchable").toHaveAttribute("hidden", "until-found");

      act(() => { folded.dispatchEvent(new Event("beforematch")); });
      expect(toggle, "the run a match is found in opens").toHaveAttribute("aria-expanded", "true");
      expect(folded).not.toHaveAttribute("hidden");

      await userEvent.click(toggle);
      expect(folded, "folding again hides it the same way").toHaveAttribute("hidden", "until-found");
    });
  });

  it("leaves a folded run's changes out where the browser cannot search hidden text", async () => {
    await withHiddenSearch(false, async () => {
      renderWorkspace();
      const feed = activity();
      expect(within(feed).queryByText(msg("applications-feed-priority"))).toBeNull();
      await userEvent.click(within(feed).getByRole("button", { name: fold() }));
      expect(seen(feed, msg("applications-feed-priority"))).toBe(true);
    });
  });

  it("offers Comment only once there is a word to post, and posts it, then clears the field", async () => {
    renderWorkspace();
    const submit = () => within(activity()).queryByRole("button", { name: msg("applications-comment-submit") });
    const box = within(activity()).getByRole("textbox", { name: msg("applications-comment-label") });
    expect(box).toHaveAttribute("placeholder", msg("applications-comment-placeholder"));
    expect(submit()).toBeNull();
    await userEvent.type(box, "   ");
    expect(submit()).toBeNull();
    await userEvent.clear(box);
    await userEvent.type(box, "Recruiter replied, call on Monday.");
    await userEvent.click(submit()!);
    expect(handlers.onAddComment).toHaveBeenCalledWith("Recruiter replied, call on Monday.");
    expect(await within(activity()).findByText("Recruiter replied, call on Monday.")).toBeInTheDocument();
    expect(box).toHaveValue("");
    expect(submit()).toBeNull();
  });

  it("posts on Enter, and starts a new line on Shift and Enter instead", async () => {
    renderWorkspace();
    const box = within(activity()).getByRole("textbox", { name: msg("applications-comment-label") });
    await userEvent.type(box, "Panel moved{Shift>}{Enter}{/Shift}to Thursday");
    expect(handlers.onAddComment).not.toHaveBeenCalled();
    expect(box).toHaveValue("Panel moved\nto Thursday");
    await userEvent.type(box, "{Enter}");
    expect(handlers.onAddComment).toHaveBeenCalledWith("Panel moved\nto Thursday");
  });

  it("keeps a comment the server refused in the composer", async () => {
    handlers.onAddComment = vi.fn(async () => false);
    renderWorkspace();
    const box = within(activity()).getByRole("textbox", { name: msg("applications-comment-label") });
    await userEvent.type(box, "Not saved yet.");
    await userEvent.click(within(activity()).getByRole("button", { name: msg("applications-comment-submit") }));
    await waitFor(() => expect(handlers.onAddComment).toHaveBeenCalled());
    expect(box).toHaveValue("Not saved yet.");
  });

  it("draws no month divider while the whole history fits in one month", () => {
    renderWorkspace();
    expect(within(activity()).queryAllByRole("button", { name: isMonthDivider })).toEqual([]);
  });

  it("parts a long history by month, one divider per month, and jumps to when the person applied", async () => {
    items = Array.from({ length: 90 }, (_, n): ActivityItem => n % 2 === 0
      ? { kind: "comment", id: 1000 + n, created_at: new Date(NOW.getTime() - n * DAY).toISOString(), actor: "user", source: "app", body: `Note ${n}`, edited_at: null }
      : { kind: "event", id: 1000 + n, created_at: new Date(NOW.getTime() - n * DAY).toISOString(), actor: "user", source: "app", event_type: "updated", from_stage: "applied", to_stage: "applied", changed: ["priority"] });
    renderWorkspace();
    const dividers = within(activity()).getAllByRole("button", { name: isMonthDivider });
    const localMonth = (iso: string) => {
      const day = new Date(iso);
      return `${day.getFullYear()}-${String(day.getMonth() + 1).padStart(2, "0")}`;
    };
    expect(dividers.map((divider) => divider.getAttribute("data-month"))).toEqual([...new Set(items.map((item) => localMonth(item.created_at)))]);

    await userEvent.click(dividers[0]);
    const menu = await screen.findByRole("dialog", { name: msg("applications-feed-jump-label") });
    await userEvent.click(within(menu).getByRole("button", { name: new RegExp(msg("applications-feed-jump-applied")) }));
    // Applied on Nov 2: the nearest entry is that day's.
    const landed = (await screen.findAllByRole("listitem")).find((entry) => entry.hasAttribute("data-landed"));
    await waitFor(() => expect(document.activeElement).toBe(landed));
  });
});

describe("the next step", () => {
  it("is typed in a field that takes several lines, with its day and Save step after the words", async () => {
    renderWorkspace();
    const field = screen.getByRole("textbox", { name: msg("applications-ws-next-add") });
    expect(field.tagName).toBe("TEXTAREA");
    await userEvent.type(field, "Write to the hiring manager");
    const day = screen.getByLabelText(msg("applications-ws-next-due"));
    const save = screen.getByRole("button", { name: msg("applications-next-save") });
    // The day and the button follow the words, on a line of their own.
    expect(field.compareDocumentPosition(day) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    expect(day.closest(".app-ws-step-actions")).toBe(save.closest(".app-ws-step-actions"));
    expect(field.closest(".app-ws-step-actions")).toBeNull();
  });

  it("takes its day from the month its whole field opens, and clears it again from there", async () => {
    renderWorkspace();
    await userEvent.type(screen.getByRole("textbox", { name: msg("applications-ws-next-add") }), "Write to the hiring manager");
    // The app's own field, never the browser's date input and its picker.
    expect(document.querySelector('input[type="date"]')).toBeNull();
    const none = `${msg("applications-ws-next-due")} ${msg("applications-ws-next-due-none")}`;
    const day = screen.getByRole("button", { name: none });
    expect(day).toHaveAttribute("aria-expanded", "false");
    const month = () => screen.queryByRole("dialog", { name: msg("applications-ws-next-due") });
    const pick = (on: Date) => within(month()!).getByRole("button", { name: formatDate(on, "weekday") });
    const nov25 = new Date(2026, 10, 25);

    // The words beside it open the month too, with the keyboard on today.
    await userEvent.click(screen.getByText(msg("applications-ws-next-due"), { selector: "label" }));
    expect(month()).not.toBeNull();
    expect(day).toHaveAttribute("aria-expanded", "true");
    await waitFor(() => expect(document.activeElement).toHaveAttribute("data-day", dayKey(NOW)));
    // The arrows walk the days and leave the month open; a click answers.
    await userEvent.keyboard("{ArrowRight}");
    expect(month()).not.toBeNull();
    await userEvent.click(pick(nov25));
    await waitFor(() => expect(month()).toBeNull());
    expect(day).toHaveTextContent(formatDate(nov25, "weekday"));
    expect(day).toHaveFocus();

    // Clearing is offered once a day is set, and leaves none.
    await userEvent.click(day);
    await userEvent.click(within(month()!).getByRole("button", { name: msg("applications-ws-next-due-clear") }));
    await waitFor(() => expect(month()).toBeNull());
    expect(screen.getByRole("button", { name: none })).toBe(day);

    await userEvent.click(day);
    expect(within(month()!).queryByRole("button", { name: msg("applications-ws-next-due-clear") })).toBeNull();
    await userEvent.click(pick(nov25));
    await userEvent.click(screen.getByRole("button", { name: msg("applications-next-save") }));
    // A day picked is due by its end, in the reader's zone.
    expect(handlers.onAddStep).toHaveBeenCalledWith("Write to the hiring manager", dueFromDay("2026-11-25"));
  });

  it("closes only the month on Escape, and the edit around it stays open", async () => {
    renderWorkspace({ next_action: "Send the portfolio" });
    await userEvent.click(screen.getByRole("button", { name: msg("applications-ws-next-edit", { step: "Send the portfolio" }) }));
    const day = screen.getByRole("button", { name: new RegExp(`^${msg("applications-ws-next-due")} `) });
    await userEvent.click(day);
    expect(screen.getByRole("dialog", { name: msg("applications-ws-next-due") })).toBeInTheDocument();
    await userEvent.keyboard("{Escape}");
    expect(screen.queryByRole("dialog", { name: msg("applications-ws-next-due") })).toBeNull();
    expect(screen.getByRole("textbox", { name: msg("applications-ws-next-edit", { step: "Send the portfolio" }) })).toBeInTheDocument();
    await waitFor(() => expect(day).toHaveFocus());
    await userEvent.keyboard("{Escape}");
    expect(screen.queryByRole("textbox", { name: msg("applications-ws-next-edit", { step: "Send the portfolio" }) })).toBeNull();
    expect(handlers.onEditStep).not.toHaveBeenCalled();
  });

  it("saves on Enter, and starts a new line on Shift and Enter instead", async () => {
    renderWorkspace();
    const field = screen.getByRole("textbox", { name: msg("applications-ws-next-add") });
    await userEvent.type(field, "Ask who joins{Shift>}{Enter}{/Shift}and what the round covers");
    expect(handlers.onAddStep).not.toHaveBeenCalled();
    expect(field).toHaveValue("Ask who joins\nand what the round covers");
    await userEvent.type(field, "{Enter}");
    expect(handlers.onAddStep).toHaveBeenCalledWith("Ask who joins\nand what the round covers", null);
    // The line is cleared for the step after it.
    await waitFor(() => expect(field).toHaveValue(""));
  });

  it("leaves an edit as it was on Escape, and hands focus back to its edit button", async () => {
    renderWorkspace({ next_action: "Send the portfolio" });
    const edit = screen.getByRole("button", { name: msg("applications-ws-next-edit", { step: "Send the portfolio" }) });
    await userEvent.click(edit);
    const field = screen.getByRole("textbox", { name: msg("applications-ws-next-edit", { step: "Send the portfolio" }) });
    await userEvent.type(field, " today");
    await userEvent.keyboard("{Escape}");
    expect(handlers.onEditStep).not.toHaveBeenCalled();
    expect(screen.getByText("Send the portfolio")).toBeInTheDocument();
    await waitFor(() => expect(screen.getByRole("button", { name: msg("applications-ws-next-edit", { step: "Send the portfolio" }) })).toHaveFocus());
  });

  it("keeps its words apart from its day and edit button, so a long step wraps in its own column", () => {
    const long = `Ask Mo for an ${"introduction".repeat(8)} before the panel`;
    renderWorkspace({ next_action: long, next_action_due: "2026-11-23T22:59:00Z" });
    const words = screen.getByText(long).closest(".app-ws-step-words")!;
    const due = document.querySelector(".app-ws-step-due");
    expect(due).not.toBeNull();
    expect(words.contains(due)).toBe(false);
    expect(words.contains(screen.getByRole("button", { name: msg("applications-ws-next-edit", { step: long }) }))).toBe(false);
  });
});

describe("several next steps", () => {
  const first = stepFixture({ id: 11, text: "Send the portfolio", due: "2026-11-20T22:59:00Z" });
  const second = stepFixture({ id: 12, text: "Ask Sam about the team", due: "2026-11-25T22:59:00Z" });
  const undated = stepFixture({ id: 13, text: "Read the team's blog", due: null });
  const tick = (step: string) => screen.getByRole("button", { name: msg("applications-upnext-done-label", { step }) });
  const rows = () => Array.from(document.querySelectorAll(".app-ws-step-words"), (words) => words.textContent);

  it("lists every open step in the order given, each with its own tick, day and edit, and the add line under the last", () => {
    renderWorkspace({ steps: [first, second, undated] });
    expect(rows()).toEqual([first.text, second.text, undated.text]);
    for (const step of [first, second, undated]) {
      expect(tick(step.text)).toBeInTheDocument();
      expect(screen.getByRole("button", { name: msg("applications-ws-next-edit", { step: step.text }) })).toBeInTheDocument();
    }
    // A dated step says its day; the one with no day says none.
    const days = Array.from(document.querySelectorAll("[data-step-id]"), (row) => row.querySelector(".app-ws-step-due") != null);
    expect(days).toEqual([true, true, false]);
    const add = screen.getByRole("textbox", { name: msg("applications-ws-next-add") });
    const last = screen.getByText(undated.text);
    expect(last.compareDocumentPosition(add) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  });

  it("ticks the step whose tick was pressed, not the first, and hands focus to the step after it", async () => {
    renderWorkspace({ steps: [first, second, undated] });
    await userEvent.click(tick(second.text));
    expect(handlers.onFinishStep).toHaveBeenCalledTimes(1);
    expect(handlers.onFinishStep).toHaveBeenCalledWith(second);
    await waitFor(() => expect(tick(undated.text)).toHaveFocus());
  });

  it("changes one step's words and day in place, leaving the others as they are", async () => {
    renderWorkspace({ steps: [first, second] });
    await userEvent.click(screen.getByRole("button", { name: msg("applications-ws-next-edit", { step: second.text }) }));
    // Only the step being changed is a field; the other stays a row.
    expect(rows()).toEqual([first.text]);
    const field = screen.getByRole("textbox", { name: msg("applications-ws-next-edit", { step: second.text }) });
    await userEvent.clear(field);
    await userEvent.type(field, "Ask Sam who leads the team{Enter}");
    expect(handlers.onEditStep).toHaveBeenCalledWith(second, "Ask Sam who leads the team", expect.stringMatching(/^2026-11-2[56]T/));
    expect(handlers.onAddStep).not.toHaveBeenCalled();
  });

  it("removes a step only from its edit, by its Remove button", async () => {
    renderWorkspace({ steps: [first, second] });
    expect(screen.queryByRole("button", { name: msg("applications-ws-next-remove") })).toBeNull();
    await userEvent.click(screen.getByRole("button", { name: msg("applications-ws-next-edit", { step: first.text }) }));
    await userEvent.click(screen.getByRole("button", { name: msg("applications-ws-next-remove") }));
    expect(handlers.onRemoveStep).toHaveBeenCalledWith(first);
    expect(handlers.onEditStep).not.toHaveBeenCalled();
    expect(handlers.onFinishStep).not.toHaveBeenCalled();
    await waitFor(() => expect(tick(second.text)).toHaveFocus());
    expect(rows()).toEqual([second.text]);
  });

  it("hands focus to the add line when the last step is ticked", async () => {
    renderWorkspace({ steps: [first] });
    await userEvent.click(tick(first.text));
    await waitFor(() => expect(screen.getByRole("textbox", { name: msg("applications-ws-next-add") })).toHaveFocus());
  });
});

describe("the done steps", () => {
  const open = stepFixture({ id: 11, text: "Send the portfolio", due: null });
  const latest = stepFixture({ id: 21, text: "Call the recruiter", done_at: "2026-11-18T10:00:00Z" });
  const earlier = stepFixture({ id: 22, text: "Tailor the CV", done_at: "2026-11-10T10:00:00Z" });
  const fold = (count: number) => screen.queryByRole("button", { name: msg("applications-ws-next-done-fold", { count }) });
  const tick = (step: string) => screen.getByRole("button", { name: msg("applications-upnext-done-label", { step }) });
  const trash = (step: string) => screen.getByRole("button", { name: msg("applications-ws-next-delete-label", { step }) });
  const question = () => screen.queryByRole("group", { name: msg("applications-ws-next-delete-confirm") });
  const doneRows = () => Array.from(document.querySelectorAll(".app-ws-done [data-step-id] .app-ws-step-words"), (words) => words.textContent);
  const openRows = () => Array.from(document.querySelectorAll(".app-ws-step-list:not(.app-ws-done *) .app-ws-step-words"), (words) => words.textContent);

  it("folds the done steps under one line that says how many, and opens them in the order given, each ticked with its day", async () => {
    renderWorkspace({ steps: [open] }, [latest, earlier]);
    const toggle = fold(2)!;
    expect(toggle).toHaveAttribute("aria-expanded", "false");
    expect(screen.queryByText(latest.text)).toBeNull();

    await userEvent.click(toggle);

    expect(toggle).toHaveAttribute("aria-expanded", "true");
    expect(doneRows()).toEqual([latest.text, earlier.text]);
    expect(tick(latest.text)).toHaveAttribute("aria-pressed", "true");
    expect(tick(open.text)).toHaveAttribute("aria-pressed", "false");
    const days = Array.from(document.querySelectorAll(".app-ws-done time"), (time) => time.getAttribute("datetime"));
    expect(days).toEqual([latest.done_at, earlier.done_at]);
    expect(openRows()).toEqual([open.text]);
  });

  it("names the year of a step done in another year, and only then", async () => {
    const lastYear = stepFixture({ id: 51, text: "Send the thank-you note", done_at: "2025-12-30T15:00:00Z" });
    const thisYear = stepFixture({ id: 52, text: "Book the flight", done_at: "2026-01-05T15:00:00Z" });
    renderWorkspace({ steps: [open] }, [thisYear, lastYear]);
    await userEvent.click(fold(2)!);
    const shown = Array.from(document.querySelectorAll(".app-ws-done time"), (time) => time.textContent);
    expect(shown).toEqual([formatDate(thisYear.done_at!, "day"), formatDate(lastYear.done_at!, "full")]);
    expect(shown[1]).toContain("2025");
    expect(shown[0]).not.toContain("2026");
  });

  it("draws no fold line while no step is done", () => {
    renderWorkspace({ steps: [open] });
    expect(document.querySelector(".app-ws-done")).toBeNull();
    expect(screen.queryByRole("button", { name: msg("applications-ws-next-done-fold", { count: 0 }) })).toBeNull();
  });

  it("counts a step ticked just now among the done steps, the first of them", async () => {
    renderWorkspace({ steps: [open] }, [latest]);
    await userEvent.click(tick(open.text));
    await userEvent.click(fold(2)!);
    expect(doneRows()).toEqual([open.text, latest.text]);
    expect(openRows()).toEqual([]);
  });

  it("puts a done step back among the open ones from its ticked tick, and keeps the keyboard in the list", async () => {
    renderWorkspace({ steps: [open] }, [latest, earlier]);
    await userEvent.click(fold(2)!);
    await userEvent.click(tick(latest.text));
    expect(handlers.onReopenStep).toHaveBeenCalledWith(latest);
    expect(handlers.onRemoveStep).not.toHaveBeenCalled();
    expect(openRows()).toEqual([open.text, latest.text]);
    expect(doneRows()).toEqual([earlier.text]);
    expect(fold(1)).toBeInTheDocument();
    await waitFor(() => expect(tick(earlier.text)).toHaveFocus());
  });

  it("keeps a done step in its list when the server refuses to open it again", async () => {
    handlers.onReopenStep = vi.fn(async () => false);
    renderWorkspace({ steps: [] }, [latest]);
    await userEvent.click(fold(1)!);
    await userEvent.click(tick(latest.text));
    expect(doneRows()).toEqual([latest.text]);
    expect(openRows()).toEqual([]);
  });

  it("hands the keyboard to the add line once the last done step leaves", async () => {
    renderWorkspace({ steps: [] }, [latest]);
    await userEvent.click(fold(1)!);
    await userEvent.click(tick(latest.text));
    expect(document.querySelector(".app-ws-done")).toBeNull();
    await waitFor(() => expect(screen.getByRole("textbox", { name: msg("applications-ws-next-add") })).toHaveFocus());
  });

  it("deletes a done step only once its question is answered Delete; Cancel and Escape keep it", async () => {
    renderWorkspace({ steps: [open] }, [latest, earlier]);
    await userEvent.click(fold(2)!);

    await userEvent.click(trash(latest.text));
    expect(question()).toBeInTheDocument();
    await userEvent.click(within(question()!).getByRole("button", { name: msg("applications-interview-cancel") }));
    expect(question()).toBeNull();
    expect(trash(latest.text), "the focus goes back to the bin, not to the page").toHaveFocus();

    await userEvent.click(trash(latest.text));
    within(question()!).getByRole("button", { name: msg("applications-interview-cancel") }).focus();
    await userEvent.keyboard("{Escape}");
    expect(question()).toBeNull();
    expect(trash(latest.text)).toHaveFocus();
    expect(handlers.onRemoveStep).not.toHaveBeenCalled();
    expect(doneRows()).toEqual([latest.text, earlier.text]);

    await userEvent.click(trash(latest.text));
    await userEvent.click(within(question()!).getByRole("button", { name: msg("applications-ws-next-delete") }));
    expect(handlers.onRemoveStep).toHaveBeenCalledTimes(1);
    expect(handlers.onRemoveStep).toHaveBeenCalledWith(latest);
    expect(handlers.onReopenStep).not.toHaveBeenCalled();
    expect(doneRows()).toEqual([earlier.text]);
    expect(openRows()).toEqual([open.text]);
    await waitFor(() => expect(tick(earlier.text)).toHaveFocus());
  });
});

describe("saving once", () => {
  /** Two submits inside one batch, before any render could show the first. */
  const twice = (form: HTMLFormElement | null) => {
    act(() => {
      form!.requestSubmit();
      form!.requestSubmit();
    });
  };

  it("adds a next step once when Enter lands twice before the first save is back", async () => {
    let answer: (saved: boolean) => void = () => {};
    handlers.onAddStep = vi.fn(() => new Promise<boolean>((resolve) => { answer = resolve; }));
    renderWorkspace();
    const field = screen.getByRole("textbox", { name: msg("applications-ws-next-add") });
    await userEvent.type(field, "Write to the hiring manager");

    twice(field.closest("form"));

    expect(handlers.onAddStep).toHaveBeenCalledTimes(1);
    await act(async () => answer(true));
  });

  it("keeps a next step typed while the one before it saves", async () => {
    let answer: (saved: boolean) => void = () => {};
    handlers.onAddStep = vi.fn(() => new Promise<boolean>((resolve) => { answer = resolve; }));
    renderWorkspace();
    const field = screen.getByRole("textbox", { name: msg("applications-ws-next-add") });
    await userEvent.type(field, "Write to the hiring manager{Enter}");
    await userEvent.clear(field);
    await userEvent.type(field, "Ask Sam about the team");

    await act(async () => answer(true));

    expect(field).toHaveValue("Ask Sam about the team");
  });

  it("clears the add line once its step is saved, when nothing more was typed", async () => {
    renderWorkspace();
    const field = screen.getByRole("textbox", { name: msg("applications-ws-next-add") });
    await userEvent.type(field, "Write to the hiring manager{Enter}");
    await waitFor(() => expect(field).toHaveValue(""));
  });

  it("leaves another step's edit open when an edit left before its save landed comes back", async () => {
    const first = stepFixture({ id: 11, text: "Send the portfolio", due: null });
    const second = stepFixture({ id: 12, text: "Ask Sam about the team", due: null });
    let answer: (saved: boolean) => void = () => {};
    handlers.onEditStep = vi.fn(() => new Promise<boolean>((resolve) => { answer = resolve; }));
    renderWorkspace({ steps: [first, second] });
    const edit = (step: string) => screen.getByRole("button", { name: msg("applications-ws-next-edit", { step }) });
    await userEvent.click(edit(first.text));
    await userEvent.type(screen.getByRole("textbox", { name: msg("applications-ws-next-edit", { step: first.text }) }), " today{Enter}");
    await userEvent.click(screen.getByRole("button", { name: msg("applications-interview-cancel") }));
    await userEvent.click(edit(second.text));
    const draft = screen.getByRole("textbox", { name: msg("applications-ws-next-edit", { step: second.text }) });
    await userEvent.type(draft, " and pay");

    await act(async () => answer(true));

    expect(screen.getByRole("textbox", { name: msg("applications-ws-next-edit", { step: second.text }) }))
      .toHaveValue("Ask Sam about the team and pay");
  });

  it("posts a comment once when Enter lands twice before the first post is back", async () => {
    let answer: (saved: boolean) => void = () => {};
    handlers.onAddComment = vi.fn(() => new Promise<boolean>((resolve) => { answer = resolve; }));
    renderWorkspace();
    const box = within(activity()).getByRole("textbox", { name: msg("applications-comment-label") });
    await userEvent.type(box, "Call is on Monday.");

    twice(box.closest("form"));

    expect(handlers.onAddComment).toHaveBeenCalledTimes(1);
    await act(async () => answer(true));
  });
});

describe("an edit that is open", () => {
  const mine = (): ActivityItem => ({
    kind: "comment", id: 8, created_at: "2026-11-04T10:00:00Z", actor: "user", source: "app", body: "Sent the portfolio.", edited_at: null,
  });

  /** The Workspace under a layer an outer page would hold, opened first. */
  function Outer({ onEscape }: { onEscape: () => void }) {
    useEscapeLayer(true, onEscape);
    return null;
  }
  function renderUnder(onEscape: () => void) {
    items = [mine(), ...items];
    render(
      <>
        <Outer onEscape={onEscape} />
        <Harness card={applicationCardFixture({ ...detail.application, steps: undefined })} />
      </>,
    );
  }

  it("leaves a step edit with nothing typed through Cancel or Remove, Save waiting for words", async () => {
    renderWorkspace({ next_action: "Send the portfolio" });
    await userEvent.click(screen.getByRole("button", { name: msg("applications-ws-next-edit", { step: "Send the portfolio" }) }));
    const field = screen.getByRole("textbox", { name: msg("applications-ws-next-edit", { step: "Send the portfolio" }) });

    await userEvent.clear(field);

    expect(screen.getByRole("button", { name: msg("applications-next-save") })).toBeDisabled();
    expect(screen.getByRole("button", { name: msg("applications-ws-next-remove") })).toBeEnabled();
    await userEvent.click(screen.getByRole("button", { name: msg("applications-interview-cancel") }));
    expect(screen.getByText("Send the portfolio")).toBeInTheDocument();
    expect(handlers.onEditStep).not.toHaveBeenCalled();
  });

  it("closes a comment edit on Escape without closing what holds the posting", async () => {
    const outer = vi.fn();
    renderUnder(outer);
    const feed = activity();
    await userEvent.click(within(feed).getByRole("button", { name: msg("applications-comment-edit") }));
    const box = within(feed).getAllByRole("textbox", { name: msg("applications-comment-label") })[1];
    await userEvent.type(box, " Again.");

    await userEvent.keyboard("{Escape}");

    expect(outer).not.toHaveBeenCalled();
    expect(handlers.onEditComment).not.toHaveBeenCalled();
    expect(within(feed).getByText("Sent the portfolio.")).toBeInTheDocument();
    expect(within(feed).getAllByRole("textbox")).toHaveLength(1);
    await userEvent.keyboard("{Escape}");
    expect(outer).toHaveBeenCalledTimes(1);
  });

  it("closes the delete question on Escape without closing what holds the posting", async () => {
    const outer = vi.fn();
    renderUnder(outer);
    const feed = activity();
    await userEvent.click(within(feed).getByRole("button", { name: msg("applications-comment-delete-label") }));
    expect(within(feed).getByRole("group", { name: msg("applications-comment-delete-confirm") })).toBeInTheDocument();

    await userEvent.keyboard("{Escape}");

    expect(outer).not.toHaveBeenCalled();
    expect(within(feed).queryByRole("group", { name: msg("applications-comment-delete-confirm") })).toBeNull();
    expect(handlers.onDeleteComment).not.toHaveBeenCalled();
  });

  it("saves a comment edit on Enter and keeps a new line for Shift and Enter, as the composer does", async () => {
    renderUnder(vi.fn());
    const feed = activity();
    await userEvent.click(within(feed).getByRole("button", { name: msg("applications-comment-edit") }));
    const box = within(feed).getAllByRole("textbox", { name: msg("applications-comment-label") })[1];
    await userEvent.type(box, "{Shift>}{Enter}{/Shift}Second line");
    expect(handlers.onEditComment).not.toHaveBeenCalled();

    await userEvent.type(box, "{Enter}");

    expect(handlers.onEditComment).toHaveBeenCalledWith(8, "Sent the portfolio.\nSecond line");
  });
});

describe("the interviews block", () => {
  const interview = (id: number, label: string, at: Date, all_day: boolean) => ({
    id, label, scheduled_at: at.toISOString(), all_day, format: null, link: null, notes: null, outcome: null,
    created_at: "2026-11-01T09:00:00Z", updated_at: "2026-11-01T09:00:00Z",
  });
  const ask = (label: string) => within(screen.getByText(label).closest("li")!).queryByRole("button", { name: msg("applications-ws-ask-outcome") });

  it("keeps an all-day round today as coming until its day ends, and asks about a timed one once it has begun", () => {
    const midnight = new Date(NOW.getFullYear(), NOW.getMonth(), NOW.getDate());
    detail = { ...detail, interviews: [
      interview(1, "Onsite day", midnight, true),
      interview(2, "Phone screen", new Date(NOW.getTime() - 3_600_000), false),
      interview(3, "Last week", new Date(midnight.getTime() - 7 * DAY), true),
    ] };
    renderWorkspace({ stage: "interviewing" });

    expect(ask("Onsite day")).toBeNull();
    expect(ask("Phone screen")).not.toBeNull();
    expect(ask("Last week")).not.toBeNull();
  });
  it("offers a round to come with nothing written the outline to prepare under, opening its notes; never a past round or one with notes", async () => {
    const tomorrow = new Date(NOW.getTime() + DAY);
    detail = { ...detail, interviews: [
      interview(7, "Hiring manager", tomorrow, false),
      { ...interview(8, "Panel", new Date(NOW.getTime() + 2 * DAY), false), notes: "Ask about on-call" },
      interview(9, "Recruiter call", new Date(NOW.getTime() - 2 * DAY), false),
    ] };
    renderWorkspace({ stage: "interviewing" });
    const prepare = (label: string) => within(screen.getByText(label).closest("li")!)
      .queryByRole("button", { name: msg("applications-ws-round-prepare") });

    expect(prepare("Panel"), "its notes stand in the outline's place").toBeNull();
    expect(within(screen.getByText("Panel").closest("li")!).getByText("Ask about on-call")).toBeInTheDocument();
    expect(prepare("Recruiter call"), "a past round asks how it went instead").toBeNull();
    await userEvent.click(prepare("Hiring manager")!);
    expect(handlers.onEditInterview).toHaveBeenCalledWith(expect.objectContaining({ id: 7 }), "notes");
  });

  it("offers each round to come as a file for the person's calendar, and no past round", async () => {
    const tomorrow = new Date(NOW.getTime() + DAY);
    detail = { ...detail, interviews: [
      interview(7, "Hiring manager", tomorrow, false),
      interview(8, "Recruiter call", new Date(NOW.getTime() - 2 * DAY), false),
    ] };
    const files: Blob[] = [];
    const saved: string[] = [];
    URL.createObjectURL = vi.fn((file: Blob) => {
      files.push(file);
      return "blob:calendar";
    });
    URL.revokeObjectURL = vi.fn();
    const click = vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(function (this: HTMLAnchorElement) {
      saved.push(this.download);
    });
    renderWorkspace({ stage: "interviewing" });
    const add = (label: string) => within(screen.getByText(label).closest("li")!)
      .queryByRole("button", { name: msg("applications-interview-calendar-label", { label }) });

    expect(add("Recruiter call"), "a past round has nothing to add").toBeNull();
    await userEvent.click(add("Hiring manager")!);

    expect(saved).toEqual([expect.stringMatching(/hiring-manager\.ics$/)]);
    expect(files).toHaveLength(1);
    // The type names the method the file states, as calendar apps check.
    expect(files[0].type).toBe("text/calendar;charset=utf-8;method=publish");
    const body = await files[0].text();
    expect(body).toContain("METHOD:PUBLISH");
    expect(body).toContain("UID:interview-7@roleband");
    expect(body).toContain(`DTSTART:${tomorrow.toISOString().replace(/[-:]/g, "").replace(/\.\d{3}/, "")}`);
    expect(document.querySelector("a[download]"), "the link leaves the page once used").toBeNull();
    click.mockRestore();
  });
});

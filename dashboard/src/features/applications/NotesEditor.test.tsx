import { act, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeAll, describe, expect, it, vi } from "vitest";
import { msg } from "../../test/msg";
import NotesEditor, { RETRY_AFTER_MS, blocksFor } from "./NotesEditor";

const page = () => screen.getByRole("textbox", { name: msg("applications-notes-label") });

afterEach(() => vi.useRealTimers());

describe("the notes page", () => {
  it("draws stored Markdown as headings, lists and ticked or open checklist lines", () => {
    render(<NotesEditor notes={"# Prep\n\n- Read the posting\n\n- [ ] Ask about the team\n- [x] Send the portfolio"} onSave={vi.fn(async () => true)} />);
    expect(within(page()).getByRole("heading", { level: 1, name: "Prep" })).toBeInTheDocument();
    expect(within(page()).getByText("Read the posting").closest("ul")).not.toBeNull();
    const boxes = within(page()).getAllByRole("checkbox");
    expect(boxes).toHaveLength(2);
    expect(boxes.map((box) => (box as HTMLInputElement).checked)).toEqual([false, true]);
    // Each box is named by its line and whether it is done, in the app's words.
    expect(boxes[0]).toHaveAccessibleName(msg("applications-notes-check", { line: "Ask about the team", checked: "no" }));
    expect(boxes[1]).toHaveAccessibleName(msg("applications-notes-check", { line: "Send the portfolio", checked: "yes" }));
  });

  it("keeps each line of a plain-text note on its own line", () => {
    render(<NotesEditor notes={"Met Sam\nRecruiter call on Friday"} onSave={vi.fn(async () => true)} />);
    const first = within(page()).getByText(/Met Sam/);
    expect(first.querySelector("br"), "the two lines run into one").not.toBeNull();
    expect(page()).toHaveTextContent("Recruiter call on Friday");
  });

  it("shows the hint on an empty page", () => {
    render(<NotesEditor notes={null} onSave={vi.fn(async () => true)} />);
    expect(page().querySelector("[data-placeholder]")?.getAttribute("data-placeholder")).toBe(msg("applications-ws-notes-hint"));
  });

  it("saves what is written as Markdown once typing pauses, and a checklist ticked by a click", async () => {
    const onSave = vi.fn(async (_notes: string) => true);
    render(<NotesEditor notes={"- [ ] Ask about the team"} onSave={onSave} />);
    await userEvent.click(within(page()).getByRole("checkbox"));
    await waitFor(() => expect(onSave).toHaveBeenCalled(), { timeout: 2000 });
    expect(onSave.mock.lastCall?.[0]).toMatch(/^- \[x\] Ask about the team/);
  });
});

describe("the / menu's blocks", () => {
  it("offers every block for a bare /, in the order a page reads", () => {
    expect(blocksFor("").map((block) => block.key)).toEqual(["text", "h1", "h2", "h3", "bullets", "numbers", "checklist", "quote", "divider"]);
  });

  it("narrows to the blocks whose name holds what was typed, and to none for a word no block has", () => {
    expect(blocksFor("check").map((block) => block.key)).toEqual(["checklist"]);
    expect(blocksFor("HEAD").map((block) => block.key)).toEqual(["h1", "h2", "h3"]);
    expect(blocksFor("list").map((block) => block.key)).toEqual(["bullets", "numbers", "checklist"]);
    expect(blocksFor("table")).toEqual([]);
  });
});

describe("typing / in the page", () => {
  it("opens the blocks by name, and Enter turns the line into the chosen block", async () => {
    const user = userEvent.setup();
    const onSave = vi.fn(async (_notes: string) => true);
    render(<NotesEditor notes={null} onSave={onSave} />);
    // The test page has no layout to place a click by, so the page takes focus directly.
    await act(async () => page().focus());
    await user.keyboard("/check");
    const menu = await screen.findByRole("listbox", { name: msg("applications-notes-blocks") });
    expect(within(menu).getAllByRole("option").map((option) => option.textContent)).toEqual([`${msg("applications-notes-block-checklist")}[ ]`]);
    expect(page()).toHaveAttribute("aria-expanded", "true");
    await user.keyboard("{Enter}");
    await waitFor(() => expect(screen.queryByRole("listbox")).toBeNull());
    expect(within(page()).getByRole("checkbox")).toBeInTheDocument();
    expect(page()).not.toHaveTextContent("/check");
    await act(async () => {
      page().blur();
    });
    await waitFor(() => expect(onSave).toHaveBeenCalled());
    expect(onSave.mock.lastCall?.[0]).toMatch(/^- \[ \]/);
  });

  it("says when no block has that name, and Escape closes the menu leaving the words", async () => {
    const user = userEvent.setup();
    render(<NotesEditor notes={null} onSave={vi.fn(async () => true)} />);
    // The test page has no layout to place a click by, so the page takes focus directly.
    await act(async () => page().focus());
    await user.keyboard("/table");
    const menu = await screen.findByRole("listbox");
    expect(within(menu).queryAllByRole("option")).toHaveLength(0);
    expect(menu).toHaveTextContent(msg("applications-notes-block-none"));
    await user.keyboard("{Escape}");
    await waitFor(() => expect(screen.queryByRole("listbox")).toBeNull());
    expect(page()).toHaveTextContent("/table");
  });
});

describe("a save that fails", () => {
  // jsdom has no layout: typing into text scrolls the caret into view, which
  // asks a range for its rectangles.
  beforeAll(() => {
    Range.prototype.getClientRects = () => ({ length: 0, item: () => null, [Symbol.iterator]: [][Symbol.iterator] }) as unknown as DOMRectList;
    Range.prototype.getBoundingClientRect = () => new DOMRect();
  });

  /** The posting paints what was typed at once and, when the write fails,
   *  reads back the notes the server kept. */
  const paintThenReadBack = (rerender: (ui: React.ReactElement) => void, onSave: (notes: string) => Promise<boolean>, typed: string, kept: string) => {
    rerender(<NotesEditor notes={typed} onSave={onSave} />);
    rerender(<NotesEditor notes={kept} onSave={onSave} />);
  };

  it("keeps what the person wrote when the page loses focus and the re-read brings back the old notes", async () => {
    const user = userEvent.setup();
    const onSave = vi.fn(async (_notes: string) => false);
    const { rerender } = render(<NotesEditor notes={"Met Sam"} onSave={onSave} />);
    await act(async () => page().focus());
    await user.keyboard(" and Pat");
    await act(async () => page().blur());
    await waitFor(() => expect(onSave).toHaveBeenCalledTimes(1));
    const typed = onSave.mock.calls[0][0];
    expect(typed).toContain("and Pat");

    paintThenReadBack(rerender, onSave, typed, "Met Sam");

    expect(page(), "the unsaved text is not replaced by the server's older notes").toHaveTextContent("and Pat");
  });

  it("tries again while the page keeps its focus, and takes the text as saved only once a save lands", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
    const onSave = vi.fn<(notes: string) => Promise<boolean>>()
      .mockResolvedValueOnce(false)
      .mockResolvedValue(true);
    const { rerender } = render(<NotesEditor notes={"Met Sam"} onSave={onSave} />);
    await act(async () => page().focus());
    await user.keyboard(" and Pat");
    await act(async () => { await vi.advanceTimersByTimeAsync(1000); });
    expect(onSave).toHaveBeenCalledTimes(1);
    const typed = onSave.mock.calls[0][0];

    paintThenReadBack(rerender, onSave, typed, "Met Sam");
    expect(page()).toHaveTextContent("and Pat");
    expect(page(), "still the person's page").toHaveFocus();

    await act(async () => { await vi.advanceTimersByTimeAsync(RETRY_AFTER_MS + 100); });
    expect(onSave, "a failed save is not left until the next keystroke").toHaveBeenCalledTimes(2);
    expect(onSave.mock.calls[1][0]).toBe(typed);

    // Saved: the page now follows a re-read again.
    await act(async () => page().blur());
    rerender(<NotesEditor notes={"Rewritten elsewhere"} onSave={onSave} />);
    expect(page()).toHaveTextContent("Rewritten elsewhere");
    expect(onSave).toHaveBeenCalledTimes(2);
  });

  it("saves words put back to the saved ones while another save is out, so the server ends with the page", async () => {
    const user = userEvent.setup();
    let land!: (saved: boolean) => void;
    const onSave = vi.fn<(notes: string) => Promise<boolean>>()
      .mockImplementationOnce(() => new Promise((resolve) => { land = resolve; }))
      .mockResolvedValue(true);
    render(<NotesEditor notes={"Met Sam"} onSave={onSave} />);
    await act(async () => page().focus());
    await user.keyboard(" and Pat");
    await act(async () => page().blur());
    await waitFor(() => expect(onSave).toHaveBeenCalledTimes(1));

    await act(async () => page().focus());
    await user.keyboard("{Backspace>8/}");
    await act(async () => page().blur());
    await act(async () => land(true));

    await waitFor(() => expect(onSave).toHaveBeenCalledTimes(2));
    expect(onSave.mock.calls[1][0]).toBe("Met Sam");
  });

  it("says a page longer than can be kept is not saved, and saves it once it is short enough", async () => {
    const user = userEvent.setup();
    const onSave = vi.fn(async (_notes: string) => true);
    render(<NotesEditor notes={"x".repeat(19_995)} onSave={onSave} />);
    await act(async () => page().focus());
    await user.keyboard("abcdefghijklmn");

    // The pause that would save it says it is not saved.
    expect(await screen.findByRole("alert", undefined, { timeout: 2000 }))
      .toHaveTextContent(msg("applications-notes-too-long", { over: 9 }));
    expect(onSave).not.toHaveBeenCalled();

    await user.keyboard("{Backspace>9/}");
    await act(async () => page().blur());

    await waitFor(() => expect(onSave).toHaveBeenCalledTimes(1));
    expect(onSave.mock.calls[0][0]).toHaveLength(20_000);
    expect(screen.queryByRole("alert")).toBeNull();
  });
});

import { act, cleanup, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { Editor } from "@tiptap/core";
import { Slice } from "@tiptap/pm/model";
import { afterEach, beforeAll, describe, expect, it, vi } from "vitest";
import type { NotesVersion } from "../../api";
import { msg } from "../../test/msg";
import NotesEditor, { RETRY_AFTER_MS, type NotesSaved } from "./NotesEditor";
import { blocksFor } from "./notesBlocks";

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

describe("a mark typed at the start of a line", () => {
  // A list made from a mark scrolls the caret into view, which reads layout
  // the test page does not have.
  beforeAll(() => {
    Range.prototype.getClientRects = () => ({ length: 0, item: () => null, [Symbol.iterator]: [][Symbol.iterator] }) as unknown as DOMRectList;
    Range.prototype.getBoundingClientRect = () => new DOMRect();
  });

  /** Types `text` into an empty page, and reads back the lines it drew. */
  const typeOnPage = async (text: string) => {
    const user = userEvent.setup();
    render(<NotesEditor notes={null} onSave={vi.fn(async () => true)} />);
    await act(async () => page().focus());
    // "[" opens a key's name for the typing helper; doubled it is the key.
    await user.keyboard(text.replaceAll("[", "[["));
    return {
      boxes: within(page()).queryAllByRole("checkbox").map((box) => (box as HTMLInputElement).checked),
      bullets: page().querySelectorAll("ul:not([data-type='taskList']) > li").length,
    };
  };

  it("makes an open checklist line of \"- [ ] \", as of \"[ ] \"", async () => {
    expect(await typeOnPage("- [ ] Ask about the team")).toEqual({ boxes: [false], bullets: 0 });
    expect(page()).toHaveTextContent("Ask about the team");
    expect(page()).not.toHaveTextContent("[ ]");
  });

  it("makes a ticked checklist line of \"- [x] \"", async () => {
    expect(await typeOnPage("- [x] Send the portfolio")).toEqual({ boxes: [true], bullets: 0 });
  });

  it("still makes a checklist line of \"[ ] \" alone", async () => {
    expect(await typeOnPage("[ ] Read the posting")).toEqual({ boxes: [false], bullets: 0 });
  });

  it("leaves \"- \" a bullet, and a box typed later in its line as words", async () => {
    expect(await typeOnPage("- Read the posting")).toEqual({ boxes: [], bullets: 1 });
    cleanup();
    expect(await typeOnPage("- Bring [ ] pens")).toEqual({ boxes: [], bullets: 1 });
    expect(page()).toHaveTextContent("Bring [ ] pens");
  });
});

describe("a paste into the page", () => {
  beforeAll(() => {
    Range.prototype.getClientRects = () => ({ length: 0, item: () => null, [Symbol.iterator]: [][Symbol.iterator] }) as unknown as DOMRectList;
    Range.prototype.getBoundingClientRect = () => new DOMRect();
  });
  /** The page's editor view, which the editor hangs on its element. */
  const view = () => (page() as unknown as { editor: Editor }).editor.view;
  const leftOut = () => screen.queryByRole("status");
  /** Pastes HTML as the browser hands a paste over; the test page has no
   *  clipboard event of its own. */
  const paste = (html: string) => view().pasteHTML(html, new Event("paste") as ClipboardEvent);
  /** Mounts the page and waits for the editor to take its starting text, a
   *  tick after it mounts, as it has long before a person can paste. */
  const mount = async (notes: string | null, onSave = vi.fn(async (_notes: string) => true)) => {
    render(<NotesEditor notes={notes} onSave={onSave} />);
    await act(() => new Promise((done) => setTimeout(done, 0)));
    return onSave;
  };

  it("keeps a table's cells apart as lines, saves them, and says a screenshot in it was left out", async () => {
    const onSave = await mount(null);
    await act(async () => page().focus());
    await act(async () => {
      paste('<table><tr><th>Round</th><th>Who</th></tr><tr><td>Screen</td><td>Sam</td></tr></table><p>Floor <img src="data:image/png;base64,iVBORw0KGgo="></p>');
    });
    expect(within(page()).getByText("Round: Screen · Who: Sam").closest("li")).not.toBeNull();
    expect(page()).not.toHaveTextContent("RoundWho");
    expect(leftOut()).toHaveTextContent(msg("applications-notes-pictures-left-out", { count: 1 }));
    await act(async () => page().blur());
    await waitFor(() => expect(onSave).toHaveBeenCalled());
    expect(onSave.mock.lastCall?.[0]).toMatch(/^- Round: Screen · Who: Sam/);

    // The next edit is the person's own: the word about the paste goes.
    await act(async () => page().focus());
    await userEvent.keyboard("!");
    await waitFor(() => expect(leftOut()).toBeNull());
  });

  it("says a picture pasted as a file alone was left out, and puts nothing on the page", async () => {
    await mount("Met Sam");
    const files = [new File(["png"], "shot.png", { type: "image/png" }), new File(["%PDF"], "cv.pdf", { type: "application/pdf" })];
    const handled = view().someProp("handlePaste", (paste) => paste(view(), { clipboardData: { files } } as unknown as ClipboardEvent, Slice.empty));
    expect(handled).toBe(true);
    expect(await screen.findByRole("status")).toHaveTextContent(msg("applications-notes-pictures-left-out", { count: 1 }));
    expect(page()).toHaveTextContent(/^Met Sam$/);
  });

  it("leaves a paste of words alone, with nothing said", async () => {
    await mount(null);
    await act(async () => page().focus());
    await act(async () => {
      paste("<p>Ask about <strong>the team</strong></p>");
    });
    expect(within(page()).getByText("the team").tagName).toBe("STRONG");
    expect(leftOut()).toBeNull();
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

describe("notes changed elsewhere while the page is written", () => {
  beforeAll(() => {
    Range.prototype.getClientRects = () => ({ length: 0, item: () => null, [Symbol.iterator]: [][Symbol.iterator] }) as unknown as DOMRectList;
    Range.prototype.getBoundingClientRect = () => new DOMRect();
  });

  it("saves over the text it started from, and puts both together when that moved on, losing neither", async () => {
    const user = userEvent.setup();
    const theirs = "Recruiter is Sam\n\nComp band: 210-240k";
    const onSave = vi.fn(async (_notes: string, _was: string): Promise<NotesSaved> => true);
    onSave.mockResolvedValueOnce({ current: theirs });
    render(<NotesEditor notes={"Recruiter is Sam"} onSave={onSave} />);
    // The editor takes its starting text a tick after it mounts.
    await act(() => new Promise((done) => setTimeout(done, 0)));
    // A new line typed under the notes: the test page cannot press Enter
    // in an editable page, so the editor makes the line itself.
    await act(async () => {
      (page() as unknown as { editor: Editor }).editor.chain().focus("end").splitBlock().insertContent("Ask about the team").run();
    });
    await act(async () => page().blur());

    await waitFor(() => expect(onSave).toHaveBeenCalledTimes(2));
    // The first save names the text the page was given; it was refused.
    expect(onSave.mock.calls[0].slice(0, 2)).toEqual(["Recruiter is Sam\n\nAsk about the team", "Recruiter is Sam"]);
    // The second is both, over the notes as they are now.
    expect(onSave.mock.calls[1].slice(0, 2)).toEqual(["Recruiter is Sam\n\nAsk about the team\n\nComp band: 210-240k", theirs]);
    expect(page()).toHaveTextContent("Ask about the team");
    expect(page()).toHaveTextContent("Comp band: 210-240k");
    expect(screen.getByRole("status")).toHaveTextContent(msg("applications-notes-merged"));

    // The next save starts from the merged text the server now holds.
    await act(async () => page().focus());
    await user.keyboard("!");
    await waitFor(() => expect(screen.queryByRole("status")).toBeNull());
    await act(async () => page().blur());
    await waitFor(() => expect(onSave).toHaveBeenCalledTimes(3));
    expect(onSave.mock.calls[2][1]).toBe("Recruiter is Sam\n\nAsk about the team\n\nComp band: 210-240k");
  });

  it("sends a save written while another is out only once that one lands, over the text it confirmed", async () => {
    let land!: (saved: NotesSaved) => void;
    const onSave = vi.fn<(notes: string, was: string, putBack?: boolean) => Promise<NotesSaved>>()
      .mockImplementationOnce(() => new Promise((resolve) => { land = resolve; }))
      .mockResolvedValue(true);
    render(<NotesEditor notes={"Met Sam"} onSave={onSave} />);
    await act(() => new Promise((done) => setTimeout(done, 0)));
    const typeAtEnd = (words: string) => act(async () => {
      (page() as unknown as { editor: Editor }).editor.chain().focus("end").insertContent(words).run();
    });
    await typeAtEnd(" and Pat");
    await act(async () => page().blur());
    await waitFor(() => expect(onSave).toHaveBeenCalledTimes(1));
    expect(onSave.mock.calls[0].slice(0, 2)).toEqual(["Met Sam and Pat", "Met Sam"]);

    await typeAtEnd(" and Lee");
    await act(async () => page().blur());
    // Sent now, it would name "Met Sam" as its starting text, which the first
    // save is about to replace, and be refused.
    expect(onSave).toHaveBeenCalledTimes(1);

    await act(async () => land(true));
    await waitFor(() => expect(onSave).toHaveBeenCalledTimes(2));
    expect(onSave.mock.calls[1].slice(0, 2)).toEqual(["Met Sam and Pat and Lee", "Met Sam and Pat"]);
  });

  it("puts both together and saves them when the page closed before the refusal came back", async () => {
    const theirs = "Recruiter is Sam\n\nComp band: 210-240k";
    let land!: (saved: NotesSaved) => void;
    const onSave = vi.fn<(notes: string, was: string, putBack?: boolean) => Promise<NotesSaved>>()
      .mockImplementationOnce(() => new Promise((resolve) => { land = resolve; }))
      .mockResolvedValue(true);
    const { unmount } = render(<NotesEditor notes={"Recruiter is Sam"} onSave={onSave} />);
    await act(() => new Promise((done) => setTimeout(done, 0)));
    const { editor } = page() as unknown as { editor: Editor };
    await act(async () => {
      editor.chain().focus("end").splitBlock().insertContent("Ask about the team").run();
    });
    // Closing the page saves what was typed since the last save.
    unmount();
    expect(onSave).toHaveBeenCalledTimes(1);
    // The editor goes a moment after the page; the refusal comes after that.
    await waitFor(() => expect(editor.isDestroyed).toBe(true));

    await act(async () => land({ current: theirs }));
    await waitFor(() => expect(onSave).toHaveBeenCalledTimes(2));
    expect(onSave.mock.calls[1].slice(0, 2)).toEqual(["Recruiter is Sam\n\nAsk about the team\n\nComp band: 210-240k", theirs]);
  });
});

describe("the notes' earlier versions", () => {
  beforeAll(() => {
    Range.prototype.getClientRects = () => ({ length: 0, item: () => null, [Symbol.iterator]: [][Symbol.iterator] }) as unknown as DOMRectList;
    Range.prototype.getBoundingClientRect = () => new DOMRect();
  });
  const opener = () => screen.getByRole("button", { name: msg("applications-notes-versions") });
  const list = () => screen.getByRole("dialog", { name: msg("applications-notes-versions") });
  const yesterday: NotesVersion = { at: "2026-11-21T16:30:00Z", actor: "agent", text: "# Prep\n\n- [ ] Ask about the team\n- Comp band: 210-240k" };
  const lastWeek: NotesVersion = { at: "2026-11-14T09:00:00Z", actor: "user", text: "Recruiter is Sam" };

  it("lists them newest first, with when, who and their first lines, read when the list opens", async () => {
    const load = vi.fn(async () => [yesterday, lastWeek]);
    render(<NotesEditor notes={"Today's notes"} onSave={vi.fn(async () => true)} loadVersions={load} />);
    expect(load).not.toHaveBeenCalled();
    await userEvent.click(opener());
    const rows = await within(list()).findAllByRole("listitem");
    expect(load).toHaveBeenCalledTimes(1);
    expect(rows.map((row) => row.querySelector("time")!.getAttribute("datetime"))).toEqual([yesterday.at, lastWeek.at]);
    expect(within(rows[0]).getByText(msg("applications-comment-author-agent"))).toBeInTheDocument();
    expect(within(rows[1]).getByText(msg("applications-comment-author-you"))).toBeInTheDocument();
    // The marks that start a line are left out of the preview.
    // The person's own words, shown as written and never translated.
    expect(within(rows[0]).getByText("Prep · Ask about the team · Comp band: 210-240k")).toHaveAttribute("translate", "no");
  });

  it("tells two versions from the same day apart by their time", async () => {
    const earlier: NotesVersion = { ...yesterday, at: "2026-11-21T11:05:00Z", text: "# Prep" };
    render(<NotesEditor notes={"Today's notes"} onSave={vi.fn(async () => true)} loadVersions={async () => [yesterday, earlier]} />);
    await userEvent.click(opener());
    const shown = (await within(list()).findAllByRole("listitem")).map((row) => row.querySelector("time")!.textContent);
    expect(shown[0]).not.toBe(shown[1]);
  });

  it("puts one back as an edit of the page: saved over the notes as they are, said, and undone by undo", async () => {
    const onSave = vi.fn(async (_notes: string, _was: string): Promise<NotesSaved> => true);
    render(<NotesEditor notes={"Today's notes"} onSave={onSave} loadVersions={async () => [yesterday, lastWeek]} />);
    await act(() => new Promise((done) => setTimeout(done, 0)));
    await userEvent.click(opener());
    const when = within(list()).getAllByRole("listitem")[1].querySelector("time")!.textContent!;
    await userEvent.click(await within(list()).findByRole("button", { name: msg("applications-notes-version-put-back-label", { when }) }));

    expect(screen.queryByRole("dialog", { name: msg("applications-notes-versions") })).toBeNull();
    expect(page()).toHaveTextContent(/^Recruiter is Sam$/);
    // Marked as put back, so the server keeps the notes it replaced as a version.
    await waitFor(() => expect(onSave).toHaveBeenCalledWith("Recruiter is Sam", "Today's notes", true));
    expect(screen.getByRole("status")).toHaveTextContent(msg("applications-notes-version-back", { when }));

    await act(async () => {
      (page() as unknown as { editor: Editor }).editor.commands.undo();
    });
    expect(page()).toHaveTextContent(/^Today's notes$/);
    expect(screen.queryByRole("status")).toBeNull();
  });

  /** Puts last week's version back over today's notes. */
  const putBackLastWeek = async (user: ReturnType<typeof userEvent.setup>) => {
    await user.click(opener());
    const when = (await within(list()).findAllByRole("listitem"))[1].querySelector("time")!.textContent!;
    await user.click(within(list()).getByRole("button", { name: msg("applications-notes-version-put-back-label", { when }) }));
  };

  it("keeps a version put back marked as put back when its save is tried again", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
    const onSave = vi.fn<(notes: string, was: string, putBack?: boolean) => Promise<NotesSaved>>()
      .mockResolvedValueOnce(false)
      .mockResolvedValue(true);
    render(<NotesEditor notes={"Today's notes"} onSave={onSave} loadVersions={async () => [yesterday, lastWeek]} />);
    await putBackLastWeek(user);
    await waitFor(() => expect(onSave).toHaveBeenCalledTimes(1));

    await act(async () => { await vi.advanceTimersByTimeAsync(RETRY_AFTER_MS + 100); });
    expect(onSave).toHaveBeenCalledTimes(2);
    expect(onSave.mock.calls[1], "the retry still starts a writing session of its own").toEqual(["Recruiter is Sam", "Today's notes", true]);
  });

  it("keeps a version put back marked as put back when it is merged with notes written elsewhere", async () => {
    const user = userEvent.setup();
    const onSave = vi.fn<(notes: string, was: string, putBack?: boolean) => Promise<NotesSaved>>()
      .mockResolvedValueOnce({ current: "Today's notes\n\nCall Pat" })
      .mockResolvedValue(true);
    render(<NotesEditor notes={"Today's notes"} onSave={onSave} loadVersions={async () => [yesterday, lastWeek]} />);
    await putBackLastWeek(user);

    await waitFor(() => expect(onSave).toHaveBeenCalledTimes(2));
    expect(onSave.mock.calls[1][2], "the merged save still starts a writing session of its own").toBe(true);
  });

  it("says it is reading them in the app's shared loading state, which a quick read never shows", async () => {
    render(<NotesEditor notes={"Notes"} onSave={vi.fn(async () => true)} loadVersions={() => new Promise(() => {})} />);
    await userEvent.click(opener());
    const reading = within(list()).getByRole("status");
    expect(reading).toHaveTextContent(msg("applications-notes-versions-loading"));
    // The shared state's own class carries the wait before it appears.
    expect(reading).toHaveClass("loading");
  });

  it("says when there is none yet, and when they could not be read", async () => {
    const { unmount } = render(<NotesEditor notes={"Notes"} onSave={vi.fn(async () => true)} loadVersions={async () => []} />);
    await userEvent.click(opener());
    expect(await within(list()).findByText(msg("applications-notes-versions-none"))).toBeInTheDocument();
    unmount();
    render(<NotesEditor notes={"Notes"} onSave={vi.fn(async () => true)} loadVersions={async () => { throw new Error("offline"); }} />);
    await userEvent.click(opener());
    expect(await within(list()).findByRole("alert")).toHaveTextContent(msg("applications-notes-versions-failed"));
  });

  it("is not offered where the page has no way to read them", () => {
    render(<NotesEditor notes={"Notes"} onSave={vi.fn(async () => true)} />);
    expect(screen.queryByRole("button", { name: msg("applications-notes-versions") })).toBeNull();
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

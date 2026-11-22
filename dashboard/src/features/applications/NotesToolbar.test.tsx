import { act, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { Editor } from "@tiptap/core";
import { beforeAll, describe, expect, it, vi } from "vitest";
import { msg } from "../../test/msg";
import { useEscapeLayer } from "../../ui";
import NotesEditor from "./NotesEditor";
import { linkTarget } from "./notesStyles";

const page = () => screen.getByRole("textbox", { name: msg("applications-notes-label") });
const editorOf = () => (page() as unknown as { editor: Editor }).editor;
const bar = () => screen.queryByRole("toolbar", { name: msg("applications-notes-bar") });
const shownBar = () => waitFor(() => expect(bar()).not.toBeNull()).then(() => bar()!);
const markdown = () => editorOf().getMarkdown().trim();
/** The modifier the editor's "Mod" keys are held with on this computer. */
const MOD: KeyboardEventInit = /Mac|iPhone|iPad/.test(navigator.platform) ? { metaKey: true } : { ctrlKey: true };

/** The page with `notes` on it, once the editor holds them. */
async function mount(notes: string) {
  render(<NotesEditor notes={notes} onSave={vi.fn(async () => true)} />);
  await act(() => new Promise((done) => setTimeout(done, 0)));
}

/** Selects the first `words` on the page, as a pointer would, focus and all. */
async function select(words: string) {
  const editor = editorOf();
  let from = -1;
  editor.state.doc.descendants((node, pos) => {
    if (from < 0 && node.isText && node.text!.includes(words)) from = pos + node.text!.indexOf(words);
  });
  await act(async () => {
    editor.chain().focus().setTextSelection({ from, to: from + words.length }).run();
  });
}

/** A key pressed on the page, through the editor's own key handling; true
 *  when the page took it. */
function pressOnPage(key: string, init: KeyboardEventInit = {}) {
  const event = new KeyboardEvent("keydown", { key, bubbles: true, cancelable: true, ...init });
  act(() => {
    page().dispatchEvent(event);
  });
  return event.defaultPrevented;
}

describe("the bar over words selected in the notes", () => {
  beforeAll(() => {
    Range.prototype.getClientRects = () => ({ length: 0, item: () => null, [Symbol.iterator]: [][Symbol.iterator] }) as unknown as DOMRectList;
    Range.prototype.getBoundingClientRect = () => new DOMRect();
  });

  it("shows only while words are selected, and names the kind of line they are on", async () => {
    await mount("## Questions\n\nAsk Sam about the team");
    await act(async () => {
      editorOf().chain().focus().setTextSelection(3).run();
    });
    // A caret alone selects nothing to style.
    await new Promise((done) => setTimeout(done, 150));
    expect(bar()).toBeNull();

    await select("Questions");
    const shown = await shownBar();
    expect(within(shown).getByRole("button", { name: msg("applications-notes-turn-into-label", { block: msg("applications-notes-block-heading", { level: 2 }) }) })).toBeInTheDocument();
    await select("Sam");
    await waitFor(() => expect(within(bar()!).getByRole("button", { name: msg("applications-notes-turn-into-label", { block: msg("applications-notes-block-text") }) })).toBeInTheDocument());
  });

  it("styles the selection from each style button, lights the style it has, and keeps the words selected", async () => {
    await mount("Ask Sam about the team");
    await select("Sam");
    const shown = await shownBar();
    const bold = within(shown).getByRole("button", { name: msg("applications-notes-style-bold") });
    expect(bold).toHaveAttribute("aria-pressed", "false");
    await userEvent.click(bold);
    expect(markdown()).toBe("Ask **Sam** about the team");
    await waitFor(() => expect(bold).toHaveAttribute("aria-pressed", "true"));
    expect(editorOf().state.doc.textBetween(editorOf().state.selection.from, editorOf().state.selection.to)).toBe("Sam");
    // Pressed again, the style comes off.
    await userEvent.click(bold);
    expect(markdown()).toBe("Ask Sam about the team");
    await waitFor(() => expect(bold).toHaveAttribute("aria-pressed", "false"));
  });

  it.each([
    [msg("applications-notes-style-italic"), "Ask *Sam* about the team"],
    [msg("applications-notes-style-strike"), "Ask ~~Sam~~ about the team"],
    [msg("applications-notes-style-code"), "Ask `Sam` about the team"],
  ])("writes %s as its Markdown", async (name, written) => {
    await mount("Ask Sam about the team");
    await select("Sam");
    await userEvent.click(within(await shownBar()).getByRole("button", { name }));
    expect(markdown()).toBe(written);
  });

  // Markdown has no underline, and the person's assistant reads these notes
  // as Markdown: an underline would reach it as a raw `<u>` tag.
  it("offers no underline, ignores its keys, and keeps an old underline's words without the tag", async () => {
    await mount("Ask <u>Sam</u> about the team");
    expect(markdown()).toBe("Ask Sam about the team");
    await select("Sam");
    const shown = await shownBar();
    expect(within(shown).queryByRole("button", { name: /underline/i })).toBeNull();
    pressOnPage("u", MOD);
    expect(markdown()).toBe("Ask Sam about the team");
  });

  it("turns the selected line into another kind and back, naming the kind it is now", async () => {
    await mount("Ask Sam about the team");
    await select("Sam");
    const shown = await shownBar();
    const turn = (name: string) => async () => {
      await userEvent.click(within(bar()!).getByRole("button", { name: /^Turn into/ }));
      const menu = screen.getByRole("dialog", { name: msg("applications-notes-turn-into") });
      await userEvent.click(within(menu).getByRole("button", { name: new RegExp(`^${name}`) }));
      await act(() => new Promise((done) => setTimeout(done, 0)));
    };
    await turn(msg("applications-notes-block-heading", { level: 2 }))();
    expect(markdown()).toBe("## Ask Sam about the team");
    await waitFor(() => expect(within(shown).getByRole("button", { name: msg("applications-notes-turn-into-label", { block: msg("applications-notes-block-heading", { level: 2 }) }) })).toBeInTheDocument());

    await turn(msg("applications-notes-block-checklist"))();
    expect(markdown()).toBe("- [ ] Ask Sam about the team");
    // A list turns into another list, not one nested in it.
    await turn(msg("applications-notes-block-numbers"))();
    expect(markdown()).toBe("1. Ask Sam about the team");
    await turn(msg("applications-notes-block-text"))();
    expect(markdown()).toBe("Ask Sam about the team");
  });

  it("marks the kind the line is now in the Turn into menu, offers no divider there, and takes a quote off a line it turns", async () => {
    await mount("> Ask Sam about the team");
    await select("Sam");
    await userEvent.click(within(await shownBar()).getByRole("button", { name: /^Turn into/ }));
    const menu = screen.getByRole("dialog", { name: msg("applications-notes-turn-into") });
    expect(within(menu).getByRole("button", { name: new RegExp(`^${msg("applications-notes-block-quote")}`) })).toHaveAttribute("aria-current", "true");
    expect(within(menu).queryByRole("button", { name: new RegExp(`^${msg("applications-notes-block-divider")}`) })).toBeNull();
    await userEvent.click(within(menu).getByRole("button", { name: new RegExp(`^${msg("applications-notes-block-heading", { level: 1 })}`) }));
    await act(() => new Promise((done) => setTimeout(done, 0)));
    // A heading, not a heading quoted.
    expect(markdown()).toBe("# Ask Sam about the team");
  });

  it("links the selected words to a web address typed bare, and refuses what is not an address", async () => {
    await mount("Ask Sam about the team");
    await select("team");
    await userEvent.click(within(await shownBar()).getByRole("button", { name: new RegExp(`^${msg("applications-notes-link")}`) }));
    const field = screen.getByRole("textbox", { name: msg("applications-notes-link-field") });
    expect(field).toHaveFocus();

    await userEvent.type(field, "javascript:alert(1){Enter}");
    expect(screen.getByRole("alert")).toHaveTextContent(msg("applications-notes-link-invalid"));
    expect(field).toHaveAttribute("aria-invalid", "true");
    expect(markdown()).toBe("Ask Sam about the team");

    await userEvent.clear(field);
    await userEvent.type(field, "careers.example.com/team{Enter}");
    expect(markdown()).toBe("Ask Sam about the [team](https://careers.example.com/team)");
    expect(screen.queryByRole("textbox", { name: msg("applications-notes-link-field") })).toBeNull();
  });

  it("opens the link field on ⌘ K over selected words, holding their link, and takes the link off", async () => {
    await mount("Ask Sam about the [team](https://careers.example.com/team)");
    await select("team");
    await shownBar();
    expect(pressOnPage("k", MOD)).toBe(true);
    const field = await screen.findByRole("textbox", { name: msg("applications-notes-link-field") });
    expect(field).toHaveValue("https://careers.example.com/team");
    await userEvent.click(screen.getByRole("button", { name: msg("applications-notes-link-remove") }));
    expect(markdown()).toBe("Ask Sam about the team");
  });

  it("leaves ⌘ K to the command palette where no words are selected", async () => {
    await mount("Ask Sam about the team");
    await act(async () => {
      editorOf().chain().focus().setTextSelection(3).run();
    });
    expect(pressOnPage("k", MOD)).toBe(false);
    expect(screen.queryByRole("textbox", { name: msg("applications-notes-link-field") })).toBeNull();
  });

  it("lets go of the selection on Escape on the page, and the surface beneath keeps its Escape", async () => {
    const beneath = vi.fn();
    function Beneath() {
      useEscapeLayer(true, beneath, "cover");
      return null;
    }
    render(<Beneath />);
    await mount("Ask Sam about the team");
    await select("Sam");
    await shownBar();
    expect(pressOnPage("Escape")).toBe(true);
    expect(editorOf().state.selection.empty).toBe(true);
    await waitFor(() => expect(bar()).toBeNull());
    expect(beneath).not.toHaveBeenCalled();
  });

  it("leaves the link field on Escape for the page, the words still selected", async () => {
    await mount("Ask Sam about the team");
    await select("team");
    await userEvent.click(within(await shownBar()).getByRole("button", { name: new RegExp(`^${msg("applications-notes-link")}`) }));
    await userEvent.keyboard("{Escape}");
    expect(screen.queryByRole("textbox", { name: msg("applications-notes-link-field") })).toBeNull();
    expect(editorOf().state.selection.empty).toBe(false);
    expect(within(bar()!).getByRole("button", { name: msg("applications-notes-style-bold") })).toBeInTheDocument();
  });

  it("walks its buttons with the arrows, after Alt F10 moves the keyboard into it", async () => {
    await mount("Ask Sam about the team");
    await select("Sam");
    const shown = await shownBar();
    expect(pressOnPage("F10", { altKey: true })).toBe(true);
    const buttons = within(shown).getAllByRole("button");
    expect(buttons[0]).toHaveFocus();
    // One stop for Tab; the arrows reach the rest.
    expect(buttons.slice(1).every((button) => button.getAttribute("tabindex") === "-1")).toBe(true);
    await userEvent.keyboard("{ArrowRight}");
    expect(buttons[1]).toHaveFocus();
    await userEvent.keyboard("{ArrowLeft}{ArrowLeft}");
    expect(buttons[buttons.length - 1]).toHaveFocus();
    await userEvent.keyboard("{Home}");
    expect(buttons[0]).toHaveFocus();
  });
});

describe("an address typed into the link field", () => {
  it.each([
    ["https://careers.example.com/team", "https://careers.example.com/team"],
    ["http://example.com", "http://example.com"],
    ["careers.example.com/team?ref=1", "https://careers.example.com/team?ref=1"],
    ["  example.co.uk  ", "https://example.co.uk"],
    ["sam@example.com", "mailto:sam@example.com"],
    ["mailto:sam@example.com", "mailto:sam@example.com"],
    ["", ""],
    ["   ", ""],
  ])("keeps %j as %j", (typed, kept) => {
    expect(linkTarget(typed)).toBe(kept);
  });

  it.each(["javascript:alert(1)", "data:text/html,hi", "ftp://example.com", "just words", "example", "https://", "file:///etc/hosts"])(
    "refuses %j",
    (typed) => {
      expect(linkTarget(typed)).toBeNull();
    },
  );
});

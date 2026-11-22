import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { msg } from "../../test/msg";
import { openLink } from "./NotesEditor";
import { NotesHelp } from "./NotesHelp";
import { BLOCKS } from "./notesBlocks";

const opener = () => screen.getByRole("button", { name: msg("applications-notes-help") });
const guide = () => screen.queryByRole("dialog", { name: msg("applications-notes-help-title") });
/** The guide's rows under one of its headings, as name and keys. */
const rowsUnder = (heading: string) => {
  const title = within(guide()!).getByText(heading);
  const list = title.nextElementSibling!;
  return Array.from(list.querySelectorAll(":scope > div"), (row) => [row.querySelector("dt")!.textContent, row.querySelector("dd")!.textContent]);
};

describe("the notes' formatting guide", () => {
  it("is closed until its button is pressed, and the button says whether it is open", async () => {
    render(<NotesHelp />);
    expect(guide()).toBeNull();
    expect(opener()).toHaveAttribute("aria-expanded", "false");
    await userEvent.click(opener());
    expect(guide()).toBeInTheDocument();
    expect(opener()).toHaveAttribute("aria-expanded", "true");
  });

  it("lists every block a mark makes, with the mark, and leaves out the one that has none", async () => {
    render(<NotesHelp />);
    await userEvent.click(opener());
    const rows = rowsUnder(msg("applications-notes-help-lines"));
    const marked = BLOCKS.filter((block) => block.mark);
    expect(rows).toEqual(marked.map((block) => [block.name(), block.mark]));
    // Plain text has no mark: a guide row for it would say nothing.
    expect(BLOCKS.some((block) => !block.mark)).toBe(true);
    expect(rows.map(([name]) => name)).not.toContain(msg("applications-notes-block-text"));
    expect(within(guide()!).getByText(msg("applications-notes-help-slash"))).toBeInTheDocument();
  });

  it("lists the keys that style words, each held with the computer's own modifier", async () => {
    render(<NotesHelp />);
    await userEvent.click(opener());
    const rows = rowsUnder(msg("applications-notes-help-words"));
    expect(rows.map(([name]) => name)).toEqual([
      msg("applications-notes-style-bold"),
      msg("applications-notes-style-italic"),
      msg("applications-notes-style-strike"),
      msg("applications-notes-style-code"),
    ]);
    const mac = /Mac|iPhone|iPad/.test(navigator.platform || navigator.userAgent);
    const mod = mac ? "⌘" : msg("applications-notes-key-ctrl");
    const shift = mac ? "⇧" : msg("applications-notes-key-shift");
    expect(rows.map(([, keys]) => keys)).toEqual([`${mod} B`, `${mod} I`, `${mod} ${shift} S`, `${mod} E`]);
    expect(within(guide()!).getByText(msg("applications-notes-help-links", { key: mod, link: `${mod} K` }))).toBeInTheDocument();
    // The bar over a selection is named too, for a person who reads the guide first.
    expect(within(guide()!).getByText(msg("applications-notes-help-select"))).toBeInTheDocument();
  });

  it("closes on Escape and hands focus back to its button", async () => {
    render(<NotesHelp />);
    await userEvent.click(opener());
    await userEvent.keyboard("{Escape}");
    expect(guide()).toBeNull();
    expect(opener()).toHaveFocus();
  });
});

describe("a link in the notes", () => {
  afterEach(() => {
    vi.restoreAllMocks();
    document.body.innerHTML = "";
  });

  /** Clicks a link to `href` with these keys held; what `openLink` said. */
  const click = (href: string | null, keys: MouseEventInit = {}) => {
    const target: HTMLElement = document.createElement(href == null ? "span" : "a");
    if (href != null) target.setAttribute("href", href);
    const words = document.createElement("strong");
    words.textContent = "the posting";
    target.append(words);
    document.body.append(target);
    let opened: boolean | null = null;
    // A link in an editable page never navigates on its own; the test page's would.
    target.addEventListener("click", (event) => {
      event.preventDefault();
      opened = openLink(event);
    }, { capture: true });
    words.dispatchEvent(new MouseEvent("click", { bubbles: true, ...keys }));
    return opened;
  };

  it("opens in a new tab, cut off from the page, when ⌘ or Ctrl is held", () => {
    const open = vi.spyOn(window, "open").mockReturnValue(null);
    expect(click("https://careers.example.test/job/1", { metaKey: true })).toBe(true);
    expect(click("mailto:sam@example.test", { ctrlKey: true })).toBe(true);
    expect(open.mock.calls).toEqual([
      ["https://careers.example.test/job/1", "_blank", "noopener,noreferrer"],
      ["mailto:sam@example.test", "_blank", "noopener,noreferrer"],
    ]);
  });

  it("only places the caret on a plain click", () => {
    const open = vi.spyOn(window, "open").mockReturnValue(null);
    expect(click("https://careers.example.test/job/1")).toBe(false);
    expect(click("https://careers.example.test/job/1", { shiftKey: true })).toBe(false);
    expect(open).not.toHaveBeenCalled();
  });

  it("opens nothing but a web or mail link, and nothing off a link", () => {
    const open = vi.spyOn(window, "open").mockReturnValue(null);
    expect(click("javascript:void 0", { metaKey: true })).toBe(false);
    expect(click("file:///etc/passwd", { metaKey: true })).toBe(false);
    expect(click(null, { metaKey: true })).toBe(false);
    expect(open).not.toHaveBeenCalled();
  });
});

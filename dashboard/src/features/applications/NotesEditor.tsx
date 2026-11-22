import { useCallback, useEffect, useId, useMemo, useRef, useState } from "react";
import { Extension, type Editor, type Range } from "@tiptap/core";
import { EditorContent, useEditor } from "@tiptap/react";
import StarterKit from "@tiptap/starter-kit";
import { TaskItem, TaskList } from "@tiptap/extension-list";
import { Placeholder } from "@tiptap/extensions";
import { Markdown } from "@tiptap/markdown";
import Suggestion, { type SuggestionProps } from "@tiptap/suggestion";
import {
  applicationsNotesBlockBullets,
  applicationsNotesBlockChecklist,
  applicationsNotesBlockDivider,
  applicationsNotesBlockHeading,
  applicationsNotesBlockNone,
  applicationsNotesBlockNumbers,
  applicationsNotesBlockQuote,
  applicationsNotesBlockText,
  applicationsNotesBlocks,
  applicationsNotesCheck,
  applicationsNotesLabel,
  applicationsNotesTooLong,
  applicationsWsNotesHint,
} from "../../copy/gen/applications";

/** How long typing may pause before what is written is saved. */
const SAVE_AFTER_MS = 800;
/** How long after a failed save the page tries again, while the text it holds
 *  is still not the server's. */
export const RETRY_AFTER_MS = 5_000;
/** The longest note the server keeps, in Markdown characters. */
const NOTES_MAX = 20_000;

/** A kind of block the "/" menu puts in place of the line being typed. The
 *  mark is what the person may type instead, at the start of a line. */
interface Block {
  key: string;
  name: () => string;
  mark: string;
  make: (editor: Editor, range: Range) => void;
}

const at = (editor: Editor, range: Range) => editor.chain().focus().deleteRange(range);

const BLOCKS: Block[] = [
  { key: "text", name: applicationsNotesBlockText, mark: "", make: (e, r) => at(e, r).setParagraph().run() },
  { key: "h1", name: () => applicationsNotesBlockHeading({ level: 1 }), mark: "#", make: (e, r) => at(e, r).setHeading({ level: 1 }).run() },
  { key: "h2", name: () => applicationsNotesBlockHeading({ level: 2 }), mark: "##", make: (e, r) => at(e, r).setHeading({ level: 2 }).run() },
  { key: "h3", name: () => applicationsNotesBlockHeading({ level: 3 }), mark: "###", make: (e, r) => at(e, r).setHeading({ level: 3 }).run() },
  { key: "bullets", name: applicationsNotesBlockBullets, mark: "-", make: (e, r) => at(e, r).toggleBulletList().run() },
  { key: "numbers", name: applicationsNotesBlockNumbers, mark: "1.", make: (e, r) => at(e, r).toggleOrderedList().run() },
  { key: "checklist", name: applicationsNotesBlockChecklist, mark: "[ ]", make: (e, r) => at(e, r).toggleTaskList().run() },
  { key: "quote", name: applicationsNotesBlockQuote, mark: ">", make: (e, r) => at(e, r).toggleBlockquote().run() },
  { key: "divider", name: applicationsNotesBlockDivider, mark: "---", make: (e, r) => at(e, r).setHorizontalRule().run() },
];

/** The blocks whose name holds what was typed after the "/". */
export function blocksFor(query: string): Block[] {
  const wanted = query.trim().toLowerCase();
  return wanted ? BLOCKS.filter((block) => block.name().toLowerCase().includes(wanted)) : BLOCKS;
}

/** The page's element, once the editor has one: before it is mounted the
 *  editor has no view and reading it throws. */
function pageOf(editor: Editor): HTMLElement | null {
  return editor.isInitialized ? editor.view.dom : null;
}

/** What the "/" menu shows while it is open. */
interface Slash {
  items: Block[];
  chosen: number;
  pick: (block: Block) => void;
  mount: SuggestionProps<Block, Block>["mount"];
}

/** The role's notes page: headings, lists, checklists, quotes and dividers,
 *  kept as Markdown in the role's one notes text, so the person's assistant
 *  reads and writes the same page. Typing "/" offers the blocks by name;
 *  Markdown's own marks at the start of a line ("# ", "- ", "[ ] ") make
 *  them too. Saved as it is typed: a pause or leaving the page saves it.
 *  While the page has focus, what the person types wins over a re-read
 *  that lands meanwhile. */
export default function NotesEditor({ notes, onSave }: { notes: string | null; onSave: (notes: string) => Promise<boolean> }) {
  const [slash, setSlash] = useState<Slash | null>(null);
  // Characters past what the server keeps, from the last save tried: such a
  // page is not sent, and says so.
  const [over, setOver] = useState(0);
  const slashNow = useRef<Slash | null>(null);
  slashNow.current = slash;
  // The text the server holds as far as this page knows: what it was given,
  // or what a save confirmed. Text that differs from it is unsaved.
  const sent = useRef(notes ?? "");
  const inFlight = useRef<string | null>(null);
  const timer = useRef<number | null>(null);
  const save = useRef(onSave);
  save.current = onSave;
  const menuId = useId();

  const flush = useCallback((editor: Editor) => {
    if (timer.current != null) window.clearTimeout(timer.current);
    timer.current = null;
    const value = editor.getMarkdown();
    setOver(Math.max(0, value.length - NOTES_MAX));
    // Compared with what the server holds once the save in flight lands: text
    // put back to the last saved words while another save is out still goes.
    if (value === (inFlight.current ?? sent.current) || value.length > NOTES_MAX) return;
    inFlight.current = value;
    void save.current(value)
      .catch(() => false)
      .then((saved) => {
        if (inFlight.current === value) inFlight.current = null;
        if (saved) {
          sent.current = value;
          return;
        }
        if (timer.current == null && !editor.isDestroyed) {
          timer.current = window.setTimeout(() => flush(editor), RETRY_AFTER_MS);
        }
      });
  }, []);

  // The "/" menu: the suggestion plugin finds the "/" and what follows it,
  // and hands its state to this component to draw.
  const slashMenu = useMemo(
    () =>
      Extension.create({
        name: "notesSlash",
        addProseMirrorPlugins() {
          return [
            Suggestion<Block, Block>({
              editor: this.editor,
              char: "/",
              items: ({ query }) => blocksFor(query),
              command: ({ editor, range, props }) => props.make(editor, range),
              render: () => {
                const show = (props: SuggestionProps<Block, Block>) =>
                  setSlash((was) => ({
                    items: props.items,
                    chosen: was && was.items === props.items ? was.chosen : 0,
                    pick: (block) => props.command(block),
                    mount: props.mount,
                  }));
                return {
                  onStart: show,
                  onUpdate: show,
                  onExit: () => setSlash(null),
                  onKeyDown: ({ event }) => {
                    // Escape is the plugin's: it closes the menu and keeps
                    // the press from the layer under the page.
                    const open = slashNow.current;
                    if (!open) return false;
                    const count = open.items.length;
                    if (event.key === "ArrowDown" || event.key === "ArrowUp") {
                      if (count === 0) return true;
                      const step = event.key === "ArrowDown" ? 1 : -1;
                      setSlash({ ...open, chosen: (open.chosen + step + count) % count });
                      return true;
                    }
                    if (event.key === "Enter" || event.key === "Tab") {
                      const block = open.items[open.chosen];
                      if (!block) return false;
                      open.pick(block);
                      return true;
                    }
                    return false;
                  },
                };
              },
            }),
          ];
        },
      }),
    [],
  );

  const editor = useEditor({
    extensions: [
      StarterKit.configure({ heading: { levels: [1, 2, 3] }, link: { openOnClick: false }, codeBlock: false }),
      TaskList,
      TaskItem.configure({
        nested: true,
        a11y: { checkboxLabel: (node, checked) => applicationsNotesCheck({ line: node.textContent, checked: checked ? "yes" : "no" }) },
      }),
      Placeholder.configure({ placeholder: applicationsWsNotesHint() }),
      // A line break is kept as one: notes written as plain text keep their
      // lines rather than running into one paragraph.
      Markdown.configure({ markedOptions: { gfm: true, breaks: true } }),
      slashMenu,
    ],
    content: notes ?? "",
    contentType: "markdown",
    injectCSS: false,
    shouldRerenderOnTransaction: false,
    editorProps: {
      attributes: {
        class: "app-ws-notes",
        role: "textbox",
        "aria-multiline": "true",
        "aria-label": applicationsNotesLabel(),
      },
    },
    // The editor writes Markdown its own way, so what it holds at the start is
    // the page's baseline, whatever the stored text looked like.
    onCreate: ({ editor: made }) => {
      sent.current = made.getMarkdown();
    },
    onUpdate: ({ editor: typed }) => {
      if (timer.current != null) window.clearTimeout(timer.current);
      timer.current = window.setTimeout(() => flush(typed), SAVE_AFTER_MS);
    },
    onBlur: ({ editor: left }) => flush(left),
  });

  // A re-read lands on the page only while the person is not writing in it
  // and everything they wrote has been saved.
  useEffect(() => {
    if (!editor || !pageOf(editor)) return;
    const written = editor.getMarkdown();
    const value = notes ?? "";
    if (editor.isFocused || value === written || written !== sent.current || inFlight.current != null) return;
    editor.commands.setContent(value, { contentType: "markdown", emitUpdate: false });
    sent.current = editor.getMarkdown();
  }, [editor, notes]);

  // Leaving the page saves what is not saved yet.
  useEffect(() => () => {
    if (editor && timer.current != null) flush(editor);
  }, [editor, flush]);

  // The page says which block the keyboard is on while the menu is open.
  const chosenId = slash && slash.items.length > 0 ? `${menuId}-${slash.items[slash.chosen].key}` : null;
  useEffect(() => {
    const dom = editor ? pageOf(editor) : null;
    if (!dom) return;
    if (slash) {
      dom.setAttribute("aria-expanded", "true");
      dom.setAttribute("aria-controls", menuId);
      if (chosenId) dom.setAttribute("aria-activedescendant", chosenId);
      else dom.removeAttribute("aria-activedescendant");
    } else {
      dom.removeAttribute("aria-expanded");
      dom.removeAttribute("aria-controls");
      dom.removeAttribute("aria-activedescendant");
    }
  }, [editor, slash, chosenId, menuId]);

  return (
    <>
      <EditorContent editor={editor} className="app-notes" />
      {over > 0 && <p className="app-notes-over" role="alert">{applicationsNotesTooLong({ over })}</p>}
      {/* Beside the page, not at the document's root: a role opened over a
          list is a dialog, and what stands outside it takes no pointer. */}
      {slash && <SlashMenu id={menuId} slash={slash} onChoose={(chosen) => setSlash({ ...slash, chosen })} />}
    </>
  );
}

function SlashMenu({ id, slash, onChoose }: { id: string; slash: Slash; onChoose: (index: number) => void }) {
  const box = useRef<HTMLDivElement>(null);
  const { mount } = slash;
  useEffect(() => (box.current ? mount(box.current) : undefined), [mount]);
  const at = (target: EventTarget) => {
    const row = (target as HTMLElement).closest<HTMLElement>("[data-index]");
    return row ? Number(row.dataset.index) : -1;
  };
  return (
    <div ref={box} className="app-notes-menu">
      {/* The editor keeps the keyboard, which walks the rows through the
          page's active descendant; the pointer picks without taking focus. */}
      <div
        id={id}
        role="listbox"
        tabIndex={-1}
        aria-label={applicationsNotesBlocks()}
        onMouseDown={(event) => event.preventDefault()}
        onMouseMove={(event) => {
          const index = at(event.target);
          if (index >= 0 && index !== slash.chosen) onChoose(index);
        }}
        onKeyDown={(event) => {
          const block = slash.items[slash.chosen];
          if (event.key === "Enter" && block) slash.pick(block);
        }}
        onClick={(event) => {
          const block = slash.items[at(event.target)];
          if (block) slash.pick(block);
        }}
      >
        {slash.items.map((block, index) => (
          <div
            key={block.key}
            id={`${id}-${block.key}`}
            role="option"
            aria-selected={index === slash.chosen}
            data-active={index === slash.chosen ? "" : undefined}
            data-index={index}
            className="app-notes-option"
          >
            <span>{block.name()}</span>
            {block.mark && <kbd className="app-notes-mark">{block.mark}</kbd>}
          </div>
        ))}
        {slash.items.length === 0 && <p className="app-notes-none">{applicationsNotesBlockNone()}</p>}
      </div>
    </div>
  );
}

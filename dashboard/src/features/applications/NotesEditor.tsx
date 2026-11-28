import { useEffect, useId, useMemo, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { Extension, InputRule, type Editor } from "@tiptap/core";
import { EditorContent, useEditor } from "@tiptap/react";
import StarterKit from "@tiptap/starter-kit";
import { TaskItem, TaskList } from "@tiptap/extension-list";
import { Placeholder } from "@tiptap/extensions";
import { Markdown } from "@tiptap/markdown";
import Suggestion, { type SuggestionProps } from "@tiptap/suggestion";
import {
  applicationsNotesBlockNone,
  applicationsNotesBlocks,
  applicationsNotesCheck,
  applicationsNotesLabel,
  applicationsNotesMerged,
  applicationsNotesPicture,
  applicationsNotesPicturesLeftOut,
  applicationsNotesTooLong,
  applicationsNotesVersionBack,
  applicationsWsNotesHint,
} from "../../copy/gen/applications";
import { blocksFor, type Block } from "./notesBlocks";
import type { NotesVersion } from "../../api";
import { mergeNotes } from "./notesMerge";
import { NotesToolbar, type BarKeys } from "./NotesToolbar";
import { NotesVersions } from "./NotesVersions";
import { pictureFiles, readablePaste } from "./notesPaste";

/** How long typing may pause before what is written is saved. */
const SAVE_AFTER_MS = 800;
/** How long after a failed save the page tries again, while the text it holds
 *  is still not the server's. */
export const RETRY_AFTER_MS = 5_000;
/** The longest note the server keeps, in Markdown characters. */
const NOTES_MAX = 20_000;

/** Opens the web or mail link a click with ⌘ or Ctrl held lands on. True
 *  when it opened one. */
export function openLink(event: MouseEvent): boolean {
  if (!(event.metaKey || event.ctrlKey)) return false;
  const href = (event.target as Element | null)?.closest?.("a[href]")?.getAttribute("href") ?? "";
  if (!/^(?:https?:|mailto:)/i.test(href)) return false;
  window.open(href, "_blank", "noopener,noreferrer");
  return true;
}

/** "- [ ] " makes a checklist line, as "[ ] " does. The "- " has already made
 *  a bullet by the time the box is typed, and the checklist's own rule cannot
 *  put a checklist inside a bullet, so this one turns that bullet into a
 *  checklist line, ticked for "[x]". Anywhere else it steps aside for the
 *  checklist's own rule. */
const checklistFromBullet = Extension.create({
  name: "notesChecklistFromBullet",
  // Ahead of the lists' own rules, which run in priority order.
  priority: 200,
  addInputRules() {
    return [
      new InputRule({
        find: /^\s*\[([ xX])?\]\s$/,
        handler: ({ state, range, match, chain }) => {
          const at = state.doc.resolve(range.from);
          const inBullet = at.depth >= 3
            && at.node(-1).type.name === "listItem"
            && at.node(-2).type.name === "bulletList"
            && at.index(-1) === 0;
          if (!inBullet) return null;
          chain().deleteRange(range).toggleTaskList().updateAttributes("taskItem", { checked: /x/i.test(match[1] ?? "") }).run();
        },
      }),
    ];
  },
});

/** What a save answers: whether it was kept, or the notes as they are now
 *  when they changed since the text the save started from. */
export type NotesSaved = boolean | { current: string };

type SaveNotes = (notes: string, was: string, putBack?: boolean) => Promise<NotesSaved>;

interface NotesDraft {
  base: string;
  sent: string;
  pending: string | null;
  saving: boolean;
  puttingBack: number;
  view: {
    editor: Editor;
    save: SaveNotes;
    merged: () => void;
    flush: () => void;
    retry: () => void;
  } | null;
}

// Unconfirmed notes belong to the role even while its editor is closed.
// Keep them in the current tab until the server confirms them or the tab closes.
const drafts = new Map<number, NotesDraft>();

function retainDraft(jobId: number | undefined, draft: NotesDraft): void {
  if (jobId === undefined) return;
  if (draft.saving || draft.pending !== null) {
    if (!draft.view) drafts.set(jobId, draft);
  } else if (drafts.get(jobId) === draft) {
    drafts.delete(jobId);
  }
}

/** Markdown as this editor writes it: the same words the person's assistant
 *  or another window wrote, in the editor's own marks, so two versions are
 *  compared line by line on what they say. */
function asWritten(editor: Editor, markdown: string): string {
  const manager = editor.markdown;
  if (!manager || !markdown) return markdown;
  try {
    return manager.serialize(editor.schema.nodeFromJSON(manager.parse(markdown)).toJSON());
  } catch {
    return markdown;
  }
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
export default function NotesEditor({ jobId, notes, onSave, loadVersions, tools, focusAtEnd = false }: {
  jobId?: number;
  notes: string | null;
  /** Saves the notes over `was`, the server's text this page last knew;
   *  `putBack` says they start with an earlier version put back. */
  onSave: SaveNotes;
  /** Reads the notes' earlier versions; without it the page offers none. */
  loadVersions?: () => Promise<NotesVersion[]>;
  /** Where the way to earlier versions is drawn: the head of the block the
   *  notes stand in. Null until that head is on the page; unset, the editor
   *  stands alone and draws it under the page. */
  tools?: HTMLElement | null;
  /** The person pressed on the notes before the editor was here: it opens
   *  with the caret at their end. */
  focusAtEnd?: boolean;
}) {
  const [slash, setSlash] = useState<Slash | null>(null);
  // Characters past what the server keeps, from the last save tried: such a
  // page is not sent, and says so.
  const [over, setOver] = useState(0);
  // Pictures the last paste or drop carried that the page cannot keep: said
  // under the page until the next edit.
  const [leftOut, setLeftOut] = useState(0);
  const slashNow = useRef<Slash | null>(null);
  slashNow.current = slash;
  // The starting server text and the last text confirmed by the server
  // can differ when the editor normalizes Markdown.
  const [{ draft, recovering }] = useState(() => {
    const retained = jobId === undefined ? undefined : drafts.get(jobId);
    const original = notes ?? "";
    const draft: NotesDraft = retained ?? {
      base: original, sent: original, pending: null, saving: false, puttingBack: 0, view: null,
    };
    return { draft, recovering: retained !== undefined };
  });
  const [merged, setMerged] = useState(false);
  const [putBack, setPutBack] = useState<string | null>(null);
  const timer = useRef<number | null>(null);
  const save = useRef(onSave);
  save.current = onSave;
  const menuId = useId();
  const barKeys = useRef<BarKeys | null>(null);

  const flush = useMemo(() => {
    const send = (value: string) => {
      draft.saving = true;
      const was = draft.base;
      const putBack = draft.puttingBack;
      const saveNotes = draft.view?.save ?? save.current;
      void saveNotes(value, was, putBack > 0)
        .catch((): NotesSaved => false)
        .then((saved) => {
          draft.saving = false;
          const view = draft.view;
          if (saved === true) {
            draft.puttingBack = Math.max(0, draft.puttingBack - putBack);
            draft.sent = value;
            draft.base = value.trim() ? value : "";
            if (draft.pending === value) {
              draft.pending = null;
              draft.puttingBack = 0;
            }
          } else if (saved !== false) {
            // During a conflict the latest keystrokes can still be waiting
            // for the debounce. Once closed, the last snapshot holds them.
            const editor = view?.editor;
            const written = (text: string) => (editor ? asWritten(editor, text) : text);
            const theirs = written(saved.current);
            const mine = editor?.getMarkdown() ?? draft.pending ?? value;
            const both = mergeNotes(written(was), mine, theirs);
            draft.base = saved.current;
            draft.sent = theirs;
            draft.pending = both === theirs ? null : both;
            if (editor && view) {
              if (both !== mine) {
                const { from, to } = editor.state.selection;
                editor.commands.setContent(both, { contentType: "markdown", emitUpdate: false });
                const end = editor.state.doc.content.size;
                editor.commands.setTextSelection({ from: Math.min(from, end), to: Math.min(to, end) });
              }
              view.merged();
              view.flush();
              return;
            }
          } else {
            view?.retry();
            retainDraft(jobId, draft);
            return;
          }

          const next = draft.pending;
          if (next !== null && next.length <= NOTES_MAX) send(next);
          retainDraft(jobId, draft);
        });
    };

    return (editor: Editor) => {
      if (timer.current != null) window.clearTimeout(timer.current);
      timer.current = null;
      const value = editor.getMarkdown();
      setOver(Math.max(0, value.length - NOTES_MAX));

      // An edit back to the last confirmed text still needs a write if a
      // different value is in flight.
      draft.pending = draft.saving || value !== draft.sent ? value : null;
      if (draft.saving) return;
      if (draft.pending === null) draft.puttingBack = 0;
      else if (value.length <= NOTES_MAX) send(value);
      retainDraft(jobId, draft);
    };
  }, [draft, jobId]);

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

  // ⌘ K links the selected words from the selection bar's field, Alt F10
  // moves the keyboard into the bar, as in other editors' toolbars, and
  // Escape lets go of the selection the bar stands over.
  const barShortcuts = useMemo(
    () =>
      Extension.create({
        name: "notesBarKeys",
        addKeyboardShortcuts() {
          return {
            "Mod-k": () => barKeys.current?.link() ?? false,
            "Alt-F10": () => barKeys.current?.enter() ?? false,
            Escape: () => barKeys.current?.escape() ?? false,
          };
        },
      }),
    [],
  );

  const editor = useEditor({
    extensions: [
      // Markdown has no underline, and the notes are Markdown the person's
      // assistant reads: underline would be saved as a raw `<u>` tag.
      StarterKit.configure({ heading: { levels: [1, 2, 3] }, link: { openOnClick: false }, codeBlock: false, underline: false }),
      TaskList,
      TaskItem.configure({
        nested: true,
        a11y: { checkboxLabel: (node, checked) => applicationsNotesCheck({ line: node.textContent, checked: checked ? "yes" : "no" }) },
      }),
      checklistFromBullet,
      Placeholder.configure({ placeholder: applicationsWsNotesHint() }),
      // A line break is kept as one: notes written as plain text keep their
      // lines rather than running into one paragraph.
      Markdown.configure({ markedOptions: { gfm: true, breaks: true } }),
      slashMenu,
      barShortcuts,
    ],
    content: draft.pending ?? notes ?? "",
    contentType: "markdown",
    autofocus: focusAtEnd ? "end" : false,
    injectCSS: false,
    shouldRerenderOnTransaction: false,
    editorProps: {
      attributes: {
        class: "app-ws-notes",
        role: "textbox",
        "aria-multiline": "true",
        "aria-label": applicationsNotesLabel(),
      },
      // A click places the caret, inside a link too; with ⌘ (Ctrl elsewhere)
      // held it opens the link, in a new tab.
      handleClick: (_view, _pos, event) => openLink(event),
      // A pasted table becomes lines and a picture a link, or is said to be
      // left out (notesPaste).
      transformPastedHTML: (html) => {
        const paste = readablePaste(html, applicationsNotesPicture());
        if (paste.leftOut > 0) setLeftOut(paste.leftOut);
        return paste.html;
      },
      // Pictures pasted or dropped as files alone bring nothing the page keeps.
      handlePaste: (_view, event, slice) => {
        const pictures = pictureFiles(event.clipboardData);
        if (pictures === 0 || slice.content.size > 0) return false;
        setLeftOut(pictures);
        return true;
      },
      handleDrop: (_view, event, slice, moved) => {
        const pictures = pictureFiles(event.dataTransfer);
        if (moved || pictures === 0 || (slice && slice.content.size > 0)) return false;
        setLeftOut(pictures);
        event.preventDefault();
        return true;
      },
    },
    // The editor writes Markdown its own way, so what it holds at the start is
    // the page's baseline, whatever the stored text looked like.
    onCreate: ({ editor: made }) => {
      if (!recovering && !draft.saving && draft.pending === null) draft.sent = made.getMarkdown();
    },
    onUpdate: ({ editor: typed, transaction }) => {
      if (!transaction.getMeta("paste")) setLeftOut(0);
      setMerged(false);
      setPutBack(null);
      if (timer.current != null) window.clearTimeout(timer.current);
      timer.current = window.setTimeout(() => flush(typed), SAVE_AFTER_MS);
    },
    onBlur: ({ editor: left }) => flush(left),
  });

  useEffect(() => {
    if (!editor) return;
    const view: NonNullable<NotesDraft["view"]> = {
      editor,
      save: (...args) => save.current(...args),
      merged: () => setMerged(true),
      flush: () => flush(editor),
      retry: () => {
        if (timer.current == null) timer.current = window.setTimeout(() => flush(editor), RETRY_AFTER_MS);
      },
    };
    draft.view = view;
    if (recovering) {
      const latest = draft.pending ?? draft.sent;
      if (editor.getMarkdown() !== latest) {
        editor.commands.setContent(latest, { contentType: "markdown", emitUpdate: false });
      }
      flush(editor);
    }
    return () => {
      if (timer.current != null) flush(editor);
      if (draft.view === view) draft.view = null;
      retainDraft(jobId, draft);
    };
  }, [editor, draft, flush, jobId, recovering]);

  // A re-read lands on the page only while the person is not writing in it
  // and everything they wrote has been saved.
  useEffect(() => {
    if (!editor || !pageOf(editor)) return;
    const written = editor.getMarkdown();
    const value = notes ?? "";
    if (editor.isFocused || value === written || written !== draft.sent || draft.saving) return;
    editor.commands.setContent(value, { contentType: "markdown", emitUpdate: false });
    draft.sent = editor.getMarkdown();
    draft.base = value;
  }, [editor, notes, draft]);

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
      {editor && <NotesToolbar editor={editor} keys={barKeys} />}
      {over > 0 && <p className="app-notes-over" role="alert">{applicationsNotesTooLong({ over })}</p>}
      {merged && <p className="app-notes-left-out" role="status">{applicationsNotesMerged()}</p>}
      {putBack && <p className="app-notes-left-out" role="status">{applicationsNotesVersionBack({ when: putBack })}</p>}
      {loadVersions && editor && (() => {
        const versions = (
          <NotesVersions
              load={loadVersions}
              onPutBack={(text, when) => {
                // An edit like any other: saved over the notes as they are,
                // and undone with the editor's own undo.
                editor.commands.setContent(text, { contentType: "markdown" });
                setPutBack(when);
                draft.puttingBack += 1;
                flush(editor);
              }}
            />
        );
        if (tools === undefined) return <div className="app-notes-foot">{versions}</div>;
        return tools ? createPortal(versions, tools) : null;
      })()}
      {leftOut > 0 && <p className="app-notes-left-out" role="status">{applicationsNotesPicturesLeftOut({ count: leftOut })}</p>}
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

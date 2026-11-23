import type { Editor, Range } from "@tiptap/core";
import {
  applicationsNotesBlockBullets,
  applicationsNotesBlockChecklist,
  applicationsNotesBlockDivider,
  applicationsNotesBlockHeading,
  applicationsNotesBlockNumbers,
  applicationsNotesBlockQuote,
  applicationsNotesBlockText,
} from "../../copy/gen/applications";

/** A kind of block the notes page holds: the "/" menu puts it in place of the
 *  line being typed, and the formatting guide lists it. The mark is what the
 *  person may type instead, at the start of a line. Kept apart from the editor
 *  so the guide does not load it. */
export interface Block {
  key: string;
  name: () => string;
  mark: string;
  make: (editor: Editor, range: Range) => void;
  /** Turns the selected lines into this block, from the selection bar; a
   *  divider holds no words and is not offered there. */
  turn?: (editor: Editor) => void;
}

const at = (editor: Editor, range: Range) => editor.chain().focus().deleteRange(range);
// The lines are first made plain text, out of any list or quote, so one kind
// of block turns into another rather than into one nested in it.
const into = (editor: Editor) => editor.chain().focus().clearNodes();

export const BLOCKS: Block[] = [
  { key: "text", name: applicationsNotesBlockText, mark: "", make: (e, r) => at(e, r).setParagraph().run(),
    turn: (e) => into(e).setParagraph().run() },
  { key: "h1", name: () => applicationsNotesBlockHeading({ level: 1 }), mark: "#", make: (e, r) => at(e, r).setHeading({ level: 1 }).run(),
    turn: (e) => into(e).setHeading({ level: 1 }).run() },
  { key: "h2", name: () => applicationsNotesBlockHeading({ level: 2 }), mark: "##", make: (e, r) => at(e, r).setHeading({ level: 2 }).run(),
    turn: (e) => into(e).setHeading({ level: 2 }).run() },
  { key: "h3", name: () => applicationsNotesBlockHeading({ level: 3 }), mark: "###", make: (e, r) => at(e, r).setHeading({ level: 3 }).run(),
    turn: (e) => into(e).setHeading({ level: 3 }).run() },
  { key: "bullets", name: applicationsNotesBlockBullets, mark: "-", make: (e, r) => at(e, r).toggleBulletList().run(),
    turn: (e) => into(e).toggleBulletList().run() },
  { key: "numbers", name: applicationsNotesBlockNumbers, mark: "1.", make: (e, r) => at(e, r).toggleOrderedList().run(),
    turn: (e) => into(e).toggleOrderedList().run() },
  { key: "checklist", name: applicationsNotesBlockChecklist, mark: "[ ]", make: (e, r) => at(e, r).toggleTaskList().run(),
    turn: (e) => into(e).toggleTaskList().run() },
  { key: "quote", name: applicationsNotesBlockQuote, mark: ">", make: (e, r) => at(e, r).toggleBlockquote().run(),
    turn: (e) => into(e).toggleBlockquote().run() },
  { key: "divider", name: applicationsNotesBlockDivider, mark: "---", make: (e, r) => at(e, r).setHorizontalRule().run() },
];

/** The blocks whose name holds what was typed after the "/". */
export function blocksFor(query: string): Block[] {
  const wanted = query.trim().toLowerCase();
  return wanted ? BLOCKS.filter((block) => block.name().toLowerCase().includes(wanted)) : BLOCKS;
}

/** The kind of block the selection starts in, as the selection bar names it:
 *  a heading, else the list it is in, else a quote, else plain text. */
export function blockAt(editor: Editor): Block {
  const key = ([1, 2, 3] as const).map((level) => editor.isActive("heading", { level }) && `h${level}`).find(Boolean)
    || (editor.isActive("taskList") && "checklist")
    || (editor.isActive("orderedList") && "numbers")
    || (editor.isActive("bulletList") && "bullets")
    || (editor.isActive("blockquote") && "quote")
    || "text";
  return BLOCKS.find((block) => block.key === key)!;
}

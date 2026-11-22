import type { Editor } from "@tiptap/core";
import {
  applicationsNotesKeyCtrl,
  applicationsNotesKeyShift,
  applicationsNotesStyleBold,
  applicationsNotesStyleCode,
  applicationsNotesStyleItalic,
  applicationsNotesStyleStrike,
} from "../../copy/gen/applications";

/** The keys a shortcut is held with on this computer: a Mac's own, or the
 *  names printed on other keyboards. */
const MAC = typeof navigator !== "undefined" && /Mac|iPhone|iPad/.test(navigator.platform || navigator.userAgent);
export const modKey = () => (MAC ? "⌘" : applicationsNotesKeyCtrl());
const shiftKey = () => (MAC ? "⇧" : applicationsNotesKeyShift());
/** The modifier as `aria-keyshortcuts` names it. */
const MOD = /* not copy */ MAC ? "Meta" : "Control";

/** A style for words: its name, the editor's keys for it, and what the
 *  selection bar's button does. The formatting guide lists the same ones. */
export interface Style {
  key: "bold" | "italic" | "strike" | "code";
  name: () => string;
  /** What its button shows, drawn in the style it gives. */
  letter: string;
  /** The keys as printed for the person. */
  keys: () => string;
  /** The keys as `aria-keyshortcuts` names them. */
  shortcut: string;
  toggle: (editor: Editor) => void;
}

export const STYLES: Style[] = [
  { key: "bold", name: applicationsNotesStyleBold, letter: "B", keys: () => `${modKey()} B`, shortcut: `${MOD}+B`,
    toggle: (e) => e.chain().focus().toggleBold().run() },
  { key: "italic", name: applicationsNotesStyleItalic, letter: "i", keys: () => `${modKey()} I`, shortcut: `${MOD}+I`,
    toggle: (e) => e.chain().focus().toggleItalic().run() },
  { key: "strike", name: applicationsNotesStyleStrike, letter: "S", keys: () => `${modKey()} ${shiftKey()} S`, shortcut: `${MOD}+Shift+S`,
    toggle: (e) => e.chain().focus().toggleStrike().run() },
  { key: "code", name: applicationsNotesStyleCode, letter: "<>", keys: () => `${modKey()} E`, shortcut: `${MOD}+E`,
    toggle: (e) => e.chain().focus().toggleCode().run() },
];

/** The keys that open the link field over selected words. */
export const linkKeys = () => `${modKey()} K`;
export const LINK_SHORTCUT = `${MOD}+K`;

/** What the person typed into the link field as a link the page keeps: a
 *  web or mail address, with `https://` or `mailto:` put in front of a bare
 *  one. "" removes the link; null is not an address. */
export function linkTarget(typed: string): string | null {
  const text = typed.trim();
  if (!text) return "";
  if (/^(?:https?:\/\/[^\s/?#]+|mailto:[^\s@]+@[^\s@]+)\S*$/i.test(text)) return text;
  if (/^[^\s@/:]+@[^\s@/:]+\.[^\s@/:]+$/.test(text)) return `mailto:${text}`;
  if (/^[\w-]+(?:\.[\w-]+)+(?::\d+)?(?:[/?#]\S*)?$/.test(text)) return `https://${text}`;
  return null;
}

import { useCallback, useEffect, useId, useMemo, useRef, useState, type KeyboardEvent, type MutableRefObject } from "react";
import type { Editor } from "@tiptap/core";
import { PluginKey } from "@tiptap/pm/state";
import { useEditorState } from "@tiptap/react";
import { BubbleMenu, type BubbleMenuProps } from "@tiptap/react/menus";
import {
  applicationsNotesBar,
  applicationsNotesLink,
  applicationsNotesLinkField,
  applicationsNotesLinkInvalid,
  applicationsNotesLinkPlaceholder,
  applicationsNotesLinkRemove,
  applicationsNotesStyleTip,
  applicationsNotesTurnInto,
  applicationsNotesTurnIntoLabel,
} from "../../copy/gen/applications";
import { Button, Icon, Kbd, Menu, MenuItem, useEscapeLayer } from "../../ui";
import { BLOCKS, blockAt } from "./notesBlocks";
import { LINK_SHORTCUT, STYLES, linkKeys, linkTarget, type Style } from "./notesStyles";

/** What the page's own keys ask of the bar: ⌘ K opens its link field, Alt
 *  F10 moves the keyboard into it, and Escape lets go of the selection it
 *  stands over. Each is true when the bar took it. */
export interface BarKeys {
  link: () => boolean;
  enter: () => boolean;
  escape: () => boolean;
}

const TURNS = BLOCKS.filter((block) => block.turn);

/** A style's letter on its button, set in the element that gives the style. */
const LETTER_TAG = { bold: "b", italic: "i", strike: "s", code: "code" } as const;
function LetterIn({ style, children }: { style: Style["key"]; children: string }) {
  const Tag = LETTER_TAG[style];
  return (
    <span className="app-notes-bar-letter" aria-hidden="true">
      <Tag>{children}</Tag>
    </span>
  );
}

/** The bar over words selected in the notes: the kind of line they are on,
 *  which it turns into another, a link, and the word styles, each lit while
 *  the selection has it. The pointer keeps the selection, and every button
 *  acts on it; the page's keys do the same without the bar. */
export function NotesToolbar({ editor, keys }: { editor: Editor; keys: MutableRefObject<BarKeys | null> }) {
  const bar = useRef<HTMLDivElement>(null);
  const field = useRef<HTMLInputElement>(null);
  const errorId = useId();
  const [shown, setShown] = useState(false);
  const [turning, setTurning] = useState(false);
  const [turnAnchor, setTurnAnchor] = useState<HTMLButtonElement | null>(null);
  // The address being typed, null while the bar shows its buttons.
  const [link, setLink] = useState<string | null>(null);
  const [invalid, setInvalid] = useState(false);
  // While the person works in the bar or its menu, the bar stays over the
  // selection though the page has lost focus.
  const held = useRef(false);
  held.current = turning || link !== null;
  const shownNow = useRef(false);
  shownNow.current = shown;

  const now = useEditorState({
    editor,
    selector: ({ editor: e }) => ({
      styles: STYLES.map((style) => e.isActive(style.key)),
      linked: e.isActive("link"),
      block: blockAt(e).key,
    }),
  });

  const openLink = useCallback(() => {
    setInvalid(false);
    setLink(String(editor.getAttributes("link").href ?? ""));
  }, [editor]);

  const letGo = useCallback(() => {
    editor.chain().focus().setTextSelection(editor.state.selection.to).run();
  }, [editor]);

  const closeLink = useCallback(() => {
    setLink(null);
    setInvalid(false);
    editor.commands.focus();
  }, [editor]);

  useEffect(() => {
    keys.current = {
      link: () => {
        if (editor.state.selection.empty) return false;
        openLink();
        return true;
      },
      enter: () => {
        const first = bar.current?.querySelector<HTMLElement>("button");
        if (!shownNow.current || !first) return false;
        first.focus();
        return true;
      },
      escape: () => {
        if (!shownNow.current || editor.state.selection.empty) return false;
        letGo();
        return true;
      },
    };
    return () => {
      keys.current = null;
    };
  }, [editor, keys, openLink, letGo]);

  const linking = link !== null;
  useEffect(() => {
    if (linking) field.current?.focus();
  }, [linking]);

  // While a pointer is down in the page the selection is still being made.
  // The bar is placed over the selection's start, which in a drag upward is
  // where the pointer is: shown then, it comes up under the pointer and the
  // drag stops on it. So the page says a selection is under way, and the bar
  // stays out of sight and out of the pointer's reach until the release
  // (applications.css); the plugin goes on placing it meanwhile, so on the
  // release it is already where it belongs.
  useEffect(() => {
    if (editor.isDestroyed) return;
    const page = editor.view.dom;
    const host = page.parentElement;
    if (!host) return;
    const down = (event: PointerEvent) => {
      if (event.button === 0) host.setAttribute("data-selecting", "");
    };
    const up = () => host.removeAttribute("data-selecting");
    page.addEventListener("pointerdown", down);
    window.addEventListener("pointerup", up);
    window.addEventListener("pointercancel", up);
    window.addEventListener("blur", up);
    return () => {
      page.removeEventListener("pointerdown", down);
      window.removeEventListener("pointerup", up);
      window.removeEventListener("pointercancel", up);
      window.removeEventListener("blur", up);
      up();
    };
  }, [editor]);

  // The bar is placed from the selection once, when it shows; a change in its
  // own size (the link field, its error, a longer line name) places it again,
  // so it never grows over the words it styles.
  const barKey = useMemo(() => new PluginKey("notesBar"), []);
  const [row, setRow] = useState<HTMLDivElement | null>(null);
  const holdRow = useCallback((element: HTMLDivElement | null) => {
    bar.current = element;
    setRow(element);
  }, []);
  useEffect(() => {
    if (!row || typeof ResizeObserver === "undefined") return;
    const watch = new ResizeObserver(() => {
      if (!editor.isDestroyed) editor.view.dispatch(editor.state.tr.setMeta(barKey, "updatePosition"));
    });
    watch.observe(row);
    return () => watch.disconnect();
  }, [editor, barKey, row]);

  // From inside the bar, Escape leaves the link field, or the bar, for the
  // page with the selection kept; the role around the page stays open. From
  // the page, the editor's own keys answer it (BarKeys), because ProseMirror
  // claims every Escape pressed in it before a window listener sees it.
  useEscapeLayer(shown, () => {
    if (link !== null) closeLink();
    else if (bar.current?.contains(document.activeElement)) editor.commands.focus();
    else letGo();
  });

  const applyLink = () => {
    const href = linkTarget(link ?? "");
    if (href === null) {
      setInvalid(true);
      field.current?.focus();
      return;
    }
    const chain = editor.chain().focus().extendMarkRange("link");
    (href ? chain.setLink({ href }) : chain.unsetLink()).run();
    setLink(null);
    setInvalid(false);
  };

  // The arrows walk the bar's buttons; Tab leaves it.
  const walk = (event: KeyboardEvent<HTMLDivElement>) => {
    if (event.target instanceof HTMLInputElement || !bar.current) return;
    const buttons = [...bar.current.querySelectorAll<HTMLElement>("button")];
    const at = buttons.indexOf(document.activeElement as HTMLElement);
    const count = buttons.length;
    const next = event.key === "ArrowRight" ? buttons[(at + 1) % count]
      : event.key === "ArrowLeft" ? buttons[(at - 1 + count) % count]
      : event.key === "Home" ? buttons[0]
      : event.key === "End" ? buttons[count - 1]
      : null;
    if (!next) return;
    event.preventDefault();
    next.focus();
  };

  const shouldShow = useCallback<NonNullable<BubbleMenuProps["shouldShow"]>>(({ editor: e, view, state, from, to }) => {
    if (held.current) return true;
    if (!e.isEditable || state.selection.empty || !state.doc.textBetween(from, to).length) return false;
    return view.hasFocus() || !!bar.current?.contains(document.activeElement);
  }, []);
  const options = useMemo<BubbleMenuProps["options"]>(() => ({
    placement: "top-start",
    offset: 8,
    flip: true,
    shift: { padding: 8 },
    onShow: () => setShown(true),
    onHide: () => setShown(false),
  }), []);

  const block = BLOCKS.find((one) => one.key === now.block)!;
  const tip = (name: string, keys: string) => applicationsNotesStyleTip({ name, keys });

  return (
    <>
      <BubbleMenu editor={editor} pluginKey={barKey} shouldShow={shouldShow} options={options} updateDelay={100} className="app-notes-bar">
        <div
          ref={holdRow}
          role="toolbar"
          aria-label={applicationsNotesBar()}
          className="app-notes-bar-row"
          onKeyDown={walk}
          // A press on a button keeps the page's focus, and with it the selection.
          onMouseDown={(event) => {
            if (!(event.target instanceof HTMLInputElement)) event.preventDefault();
          }}
        >
          {link === null ? (
            <>
              <Button
                ref={setTurnAnchor}
                variant="ghost"
                size="sm"
                className="ui-btn-bar"
                aria-label={applicationsNotesTurnIntoLabel({ block: block.name() })}
                aria-haspopup="menu"
                aria-expanded={turning}
                onClick={() => setTurning((was) => !was)}
              >
                {block.name()}
                <Icon name="chevronDown" size={12} />
              </Button>
              <span className="app-notes-bar-rule" aria-hidden="true" />
              <Button
                variant="ghost"
                size="sm"
                className="ui-btn-bar"
                tabIndex={-1}
                aria-pressed={now.linked}
                aria-keyshortcuts={LINK_SHORTCUT}
                title={tip(applicationsNotesLink(), linkKeys())}
                onClick={openLink}
              >
                <Icon name="link" size={14} />
                {applicationsNotesLink()}
              </Button>
              <span className="app-notes-bar-rule" aria-hidden="true" />
              {STYLES.map((style, at) => (
                <Button
                  key={style.key}
                  variant="icon"
                  size="sm"
                  className="ui-btn-bar"
                  tabIndex={-1}
                  aria-label={style.name()}
                  aria-pressed={now.styles[at]}
                  aria-keyshortcuts={style.shortcut}
                  title={tip(style.name(), style.keys())}
                  onClick={() => style.toggle(editor)}
                >
                  <LetterIn style={style.key}>{style.letter}</LetterIn>
                </Button>
              ))}
            </>
          ) : (
            <form
              className="app-notes-bar-link"
              onSubmit={(event) => {
                event.preventDefault();
                applyLink();
              }}
            >
              <input
                ref={field}
                className="app-notes-bar-field"
                type="text"
                inputMode="url"
                autoComplete="off"
                spellCheck={false}
                aria-label={applicationsNotesLinkField()}
                aria-invalid={invalid || undefined}
                aria-describedby={invalid ? errorId : undefined}
                placeholder={applicationsNotesLinkPlaceholder()}
                value={link}
                onChange={(event) => {
                  setLink(event.target.value);
                  setInvalid(false);
                }}
              />
              {now.linked && (
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={() => {
                    editor.chain().focus().extendMarkRange("link").unsetLink().run();
                    setLink(null);
                  }}
                >
                  {applicationsNotesLinkRemove()}
                </Button>
              )}
              {invalid && <p id={errorId} className="app-notes-bar-error" role="alert">{applicationsNotesLinkInvalid()}</p>}
            </form>
          )}
        </div>
      </BubbleMenu>
      <Menu isOpen={turning} onClose={() => setTurning(false)} anchor={turnAnchor} align="start" label={applicationsNotesTurnInto()}>
        {TURNS.map((one) => (
          <MenuItem
            key={one.key}
            current={one.key === now.block}
            detail={one.mark ? <Kbd>{one.mark}</Kbd> : undefined}
            onSelect={() => {
              setTurning(false);
              // After the menu has handed focus back to its button, so the
              // change puts the caret back on the page.
              window.setTimeout(() => one.turn!(editor));
            }}
          >
            {one.name()}
          </MenuItem>
        ))}
      </Menu>
    </>
  );
}

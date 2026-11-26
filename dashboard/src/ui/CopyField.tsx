import { useEffect, useRef, useState } from "react";
import { sharedCopied, sharedCopyFailed, sharedCopyText } from "../copy/gen/shared";
import { Icon } from "./Icon";
import "./CopyField.css";

/** How long a press shows that the text was copied. */
export const COPIED_MS = 2_000;

/* THE copy control (docs/ui.md): text the person copies to use elsewhere, a
   sentence for their assistant or a command, as its own control. The whole
   field is the button, with the copy glyph at its end. For two seconds after a
   press the field wears the action's edge, a tick and "Copied"; a press within
   them starts the two seconds again. When the browser refuses the clipboard,
   the text is selected so the person can copy it, and a line under the field
   says so. The text wraps rather than clip: what is to be said is read whole. */
export function CopyField({ text, className }: { text: string; className?: string }) {
  // What the last press did, and to which text: feedback for a text no longer
  // shown is not shown. Each press is a new object, so a press within the two
  // seconds starts them again.
  const [press, setPress] = useState<{ text: string; copied: boolean } | null>(null);
  const shown = press?.text === text ? press : null;
  const copied = shown?.copied === true;
  const failed = shown?.copied === false;
  const textRef = useRef<HTMLElement>(null);
  const latest = useRef(text);
  useEffect(() => {
    latest.current = text;
  }, [text]);

  useEffect(() => {
    if (!press?.copied) return;
    const timer = window.setTimeout(() => setPress(null), COPIED_MS);
    return () => window.clearTimeout(timer);
  }, [press]);

  const selectText = () => {
    const node = textRef.current;
    const selection = window.getSelection();
    if (!node || !selection) return;
    const range = document.createRange();
    range.selectNodeContents(node);
    selection.removeAllRanges();
    selection.addRange(range);
  };

  const copy = () => {
    const pressed = text;
    // The clipboard answers later: an answer for a text the field no longer
    // holds says nothing.
    const answer = (copiedIt: boolean) => {
      if (latest.current !== pressed) return;
      setPress({ text: pressed, copied: copiedIt });
      if (!copiedIt) selectText();
    };
    // `navigator.clipboard` is missing outside a secure context: that refusal
    // is a failure like any other.
    Promise.resolve()
      .then(() => navigator.clipboard.writeText(pressed))
      .then(() => answer(true), () => answer(false));
  };

  return (
    <div className={`ui-copy-field-host${className ? ` ${className}` : ""}`}>
      <button
        type="button"
        className={`ui-copy-field${copied ? " is-copied" : ""}`}
        aria-label={sharedCopyText({ text })}
        onClick={copy}
      >
        {/* The text stays selectable inside the button, for a refused clipboard. */}
        <code className="ui-copy-field-text" data-selection="content" ref={textRef}>{text}</code>
        {copied && <span className="ui-copy-field-done" aria-hidden="true">{sharedCopied()}</span>}
        <Icon name={copied ? "check" : "copy"} size={15} />
      </button>
      <span className="sr-only" role="status">{copied ? sharedCopied() : ""}</span>
      {failed && <p className="ui-copy-field-failed" role="alert">{sharedCopyFailed()}</p>}
    </div>
  );
}

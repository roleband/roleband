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
  // Counts the presses that copied: each starts the two seconds again.
  const [copied, setCopied] = useState(0);
  const [failed, setFailed] = useState(false);
  const textRef = useRef<HTMLElement>(null);

  useEffect(() => {
    if (copied === 0) return;
    const timer = window.setTimeout(() => setCopied(0), COPIED_MS);
    return () => window.clearTimeout(timer);
  }, [copied]);

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
    // `navigator.clipboard` is missing outside a secure context: that refusal
    // is a failure like any other.
    Promise.resolve()
      .then(() => navigator.clipboard.writeText(text))
      .then(
        () => {
          setFailed(false);
          setCopied((n) => n + 1);
        },
        () => {
          setCopied(0);
          setFailed(true);
          selectText();
        },
      );
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
        {copied > 0 && <span className="ui-copy-field-done" aria-hidden="true">{sharedCopied()}</span>}
        <Icon name={copied ? "check" : "copy"} size={15} />
      </button>
      <span className="sr-only" role="status">{copied ? sharedCopied() : ""}</span>
      {failed && <p className="ui-copy-field-failed" role="alert">{sharedCopyFailed()}</p>}
    </div>
  );
}

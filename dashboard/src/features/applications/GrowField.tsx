import { useEffect, useRef, type KeyboardEvent, type RefObject, type TextareaHTMLAttributes } from "react";

/** Sets the field's height to its text's, so the page scrolls, never the
 *  field. The height counts the field's edge, which `scrollHeight` leaves out. */
function fitHeight(element: HTMLTextAreaElement) {
  element.style.height = "auto";
  element.style.height = `${element.scrollHeight + element.offsetHeight - element.clientHeight}px`;
}

/** A text field that grows with its text and saves on Enter, as a one-line
 *  field would; Shift and Enter starts a new line. Enter submits the form
 *  around it, so the form's own submit is the one place that saves. */
export function GrowField({ value, onChange, fieldRef, onKeyDown, ...rest }: Omit<TextareaHTMLAttributes<HTMLTextAreaElement>, "value" | "onChange"> & {
  value: string;
  onChange: (text: string) => void;
  /** Where the caller reads the field, to focus it. */
  fieldRef?: RefObject<HTMLTextAreaElement | null>;
}) {
  const own = useRef<HTMLTextAreaElement>(null);
  const field = fieldRef ?? own;
  useEffect(() => {
    if (field.current) fitHeight(field.current);
  }, [field, value]);
  // A narrower field wraps the same words onto more lines. Only a change of
  // width measures again: the height this sets is a resize too.
  useEffect(() => {
    const element = field.current;
    if (!element || typeof ResizeObserver === "undefined") return;
    let width = element.clientWidth;
    const watch = new ResizeObserver(() => {
      if (element.clientWidth === width) return;
      width = element.clientWidth;
      fitHeight(element);
    });
    watch.observe(element);
    return () => watch.disconnect();
  }, [field]);
  const keyDown = (event: KeyboardEvent<HTMLTextAreaElement>) => {
    onKeyDown?.(event);
    if (event.defaultPrevented) return;
    if (event.key === "Enter" && !event.shiftKey && !event.nativeEvent.isComposing) {
      event.preventDefault();
      event.currentTarget.form?.requestSubmit();
    }
  };
  return <textarea {...rest} ref={field} value={value} onChange={(event) => onChange(event.target.value)} onKeyDown={keyDown} />;
}

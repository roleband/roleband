import { useRef, type KeyboardEvent, type RefObject, type TextareaHTMLAttributes } from "react";
import { useGrow } from "./useGrow";

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
  useGrow(field, value);
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

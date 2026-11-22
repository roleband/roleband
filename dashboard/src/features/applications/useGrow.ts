import { useEffect, type RefObject } from "react";

/** A text field that grows with its text, so the page scrolls, never the
 *  field. The height counts the field's edge, which `scrollHeight` leaves out. */
export function useGrow(field: RefObject<HTMLTextAreaElement | null>, value: string) {
  useEffect(() => {
    const element = field.current;
    if (!element) return;
    element.style.height = "auto";
    element.style.height = `${element.scrollHeight + element.offsetHeight - element.clientHeight}px`;
  }, [field, value]);
}

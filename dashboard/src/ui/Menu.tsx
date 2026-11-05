import { useEffect, useId, useRef, type ReactNode } from "react";
import { Button } from "./Button";
import { Icon, type IconName } from "./Icon";
import { Popover } from "./Popover";
import "./Menu.css";

/* A dropdown menu: a short list of actions or choices opened from a button.
 *
 * One recipe for every row kind, so a menu never decides its own spacing:
 * the panel pads itself, every row is the 28px control with the small
 * control's inset, and groups part with a hairline. A row is an action
 * (`MenuItem`, a ghost Button), a box that turns something on or off
 * (`MenuCheck`), or one of a few modes (`MenuRadio`).
 *
 * The padding and width live on `.ui-menu-body`, inside the popover's glass.
 * A class passed to `Popover` lands on its unpainted outer box, so padding set
 * there sits outside the border and a width set there does not hold the
 * glass: never size or pad a menu through the Popover's own class.
 *
 * The arrow keys move between rows, Home and End to the first and last.
 * A radio keeps its own arrows, which choose within its group. */

const ROWS = ".ui-menu-item:not(:disabled), .ui-menu-row input:not(:disabled)";

export interface MenuProps {
  isOpen: boolean;
  onClose: () => void;
  /** The button that opens the menu. */
  anchor: HTMLElement | null;
  /** The menu's accessible name. */
  label: string;
  /** Which edge of the anchor the menu lines up with. Default "end". */
  align?: "start" | "end";
  /** A placement or width hook for the menu's body, never its chrome. */
  className?: string;
  children: ReactNode;
}

export function Menu({ isOpen, onClose, anchor, label, align = "end", className, children }: MenuProps) {
  const body = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!isOpen) return;
    const onKeyDown = (event: KeyboardEvent) => {
      const panel = body.current;
      const target = event.target as HTMLElement | null;
      if (!panel || !target) return;
      // The menu's own shell holds focus when it opens, so keys there count too.
      const shell = panel.closest(".ui-overlay-content");
      if (target !== shell && !panel.contains(target)) return;
      if (target instanceof HTMLInputElement && target.type === "radio"
        && ["ArrowDown", "ArrowUp", "ArrowLeft", "ArrowRight"].includes(event.key)) return;
      const rows = [...panel.querySelectorAll<HTMLElement>(ROWS)];
      if (rows.length === 0) return;
      const at = rows.indexOf(target);
      const next = event.key === "ArrowDown" ? rows[(at + 1) % rows.length]
        : event.key === "ArrowUp" ? rows[at <= 0 ? rows.length - 1 : at - 1]
        : event.key === "Home" ? rows[0]
        : event.key === "End" ? rows[rows.length - 1]
        : null;
      if (!next) return;
      event.preventDefault();
      next.focus();
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [isOpen]);

  return (
    <Popover isOpen={isOpen} onClose={onClose} anchor={anchor} align={align} label={label} className="app-overlay ui-menu">
      <div ref={body} className={`ui-menu-body${className ? ` ${className}` : ""}`}>{children}</div>
    </Popover>
  );
}

/** Rows that belong together, under an optional heading. Two groups part
 *  with a hairline. */
export function MenuGroup({ label, children }: { label?: string; children: ReactNode }) {
  return (
    <div className="ui-menu-group" role="group" aria-label={label}>
      {label && <span className="ui-menu-heading" aria-hidden="true">{label}</span>}
      {children}
    </div>
  );
}

export interface MenuItemProps {
  onSelect: () => void;
  children: ReactNode;
  /** Leads the row: a key hint (`<Kbd>`). */
  lead?: ReactNode;
  /** Leads the row in place of `lead`. */
  icon?: IconName;
  /** Quiet text at the row's end, such as a date. */
  detail?: ReactNode;
  /** The option already in force: a tick at the end, and `aria-current`. */
  current?: boolean;
  disabled?: boolean;
  /** Says why a disabled row is off. */
  title?: string;
  /** The key that does this outside the menu. */
  shortcut?: string;
}

export function MenuItem({ onSelect, children, lead, icon, detail, current, disabled, title, shortcut }: MenuItemProps) {
  return (
    <Button
      variant="ghost"
      size="sm"
      className="ui-menu-item"
      aria-current={current || undefined}
      aria-keyshortcuts={shortcut}
      disabled={disabled}
      title={title}
      onClick={onSelect}
    >
      {(icon || lead != null) && (
        <span className="ui-menu-lead" aria-hidden="true">{icon ? <Icon name={icon} size={14} /> : lead}</span>
      )}
      <span className="ui-menu-label">{children}</span>
      {detail != null && <span className="ui-menu-detail">{detail}</span>}
      {current && <Icon name="check" size={14} />}
    </Button>
  );
}

export interface MenuCheckProps {
  checked: boolean;
  onChange: (checked: boolean) => void;
  /** The row's name, and its checkbox's accessible name. */
  children: string;
  /** How many this would show, at the row's end. */
  count?: ReactNode;
  disabled?: boolean;
  /** Says why a disabled row is off. */
  title?: string;
}

export function MenuCheck({ checked, onChange, children, count, disabled, title }: MenuCheckProps) {
  return (
    <label className="ui-menu-row" title={title}>
      <input
        type="checkbox"
        aria-label={children}
        checked={checked}
        disabled={disabled}
        onChange={(event) => onChange(event.target.checked)}
      />
      <span className="ui-menu-label" aria-hidden="true">{children}</span>
      {count != null && <span className="ui-menu-detail ui-menu-count" aria-hidden="true">{count}</span>}
    </label>
  );
}

export interface MenuRadioProps {
  /** The radios of one choice share a name. */
  name: string;
  checked: boolean;
  onChange: () => void;
  children: string;
  /** A line under the name that says what the mode does. */
  hint?: string;
}

export function MenuRadio({ name, checked, onChange, children, hint }: MenuRadioProps) {
  const hintId = useId();
  return (
    <label className="ui-menu-row" data-hinted={hint ? "" : undefined}>
      <input
        type="radio"
        name={name}
        aria-label={children}
        aria-describedby={hint ? hintId : undefined}
        checked={checked}
        onChange={onChange}
      />
      <span className="ui-menu-label" aria-hidden="true">
        {children}
        {hint && <span id={hintId} className="ui-menu-hint">{hint}</span>}
      </span>
    </label>
  );
}

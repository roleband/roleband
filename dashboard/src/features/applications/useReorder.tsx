import { useEffect, useState, type DragEvent } from "react";
import { Button, Icon, Menu, MenuGroup, MenuItem, type IconName } from "../../ui";

/* Reordering a row of things by hand, written once for the Workspace's blocks
 * and the List's columns: a drag that shows where it would land, and a menu
 * whose two steps do what a drag does for a keyboard. Each screen keeps what
 * is its own: the order it stores and where focus goes afterwards. */

export type Side = "before" | "after";

/** What a draggable item carries; spread on the element that drags. */
export interface DragItemProps {
  draggable: boolean;
  "data-dragged"?: true;
  "data-drop"?: Side;
  onDragStart: (event: DragEvent<HTMLElement>) => void;
  onDragOver: (event: DragEvent<HTMLElement>) => void;
  onDrop: (event: DragEvent<HTMLElement>) => void;
  onDragEnd: () => void;
}

/** The drag state of a row of items keyed by `K`.
 *
 *  `axis` is the line the items run along: a drop lands before an item when
 *  the pointer is in its first half. With `grip`, an item drags only after a
 *  press on its grip (`arm`), so the text inside it stays selectable; the
 *  press ends wherever the pointer is released, since a native drag cancels
 *  the pointer instead and a release always means no drag came of it. */
export function useReorder<K extends string>({ axis, grip = false, onPlace }: {
  axis: "x" | "y";
  grip?: boolean;
  /** Called on a drop: `dragged` goes to `side` of `over`. */
  onPlace: (dragged: K, over: K, side: Side) => void;
}) {
  const [armed, setArmed] = useState<K | null>(null);
  const [dragged, setDragged] = useState<K | null>(null);
  const [drop, setDrop] = useState<{ over: K; side: Side } | null>(null);

  useEffect(() => {
    if (armed == null) return;
    const release = () => setArmed(null);
    window.addEventListener("pointerup", release);
    return () => window.removeEventListener("pointerup", release);
  }, [armed]);

  const end = () => {
    setArmed(null);
    setDragged(null);
    setDrop(null);
  };

  const itemProps = (key: K): DragItemProps => ({
    draggable: grip ? armed === key : true,
    "data-dragged": dragged === key || undefined,
    "data-drop": drop?.over === key && dragged !== key ? drop.side : undefined,
    onDragStart: (event) => {
      if (grip && armed !== key) {
        event.preventDefault();
        return;
      }
      event.dataTransfer.effectAllowed = "move";
      event.dataTransfer.setData("text/plain", key);
      setDragged(key);
    },
    onDragOver: (event) => {
      if (dragged == null) return;
      event.preventDefault();
      event.dataTransfer.dropEffect = "move";
      const box = event.currentTarget.getBoundingClientRect();
      const side: Side = axis === "y"
        ? (event.clientY < box.top + box.height / 2 ? "before" : "after")
        : (event.clientX < box.left + box.width / 2 ? "before" : "after");
      if (drop?.over !== key || drop.side !== side) setDrop({ over: key, side });
    },
    onDrop: (event) => {
      event.preventDefault();
      if (dragged != null && drop != null && dragged !== drop.over) onPlace(dragged, drop.over, drop.side);
      end();
    },
    onDragEnd: end,
  });

  return { dragging: dragged != null, arm: (key: K) => setArmed(key), itemProps };
}

/** The menu on an item's handle: one step to each side, and one further
 *  action the screen offers (hide). `first` and `last` disable the step that
 *  has nowhere to go. */
export function ReorderMenu({ label, icon, className, size = 14, align, back, forward, first, last, onStep, onPointerDown, draggable, extra }: {
  /** The handle's name and the menu's. */
  label: string;
  icon: IconName;
  className: string;
  size?: number;
  align?: "start" | "end";
  back: { icon: IconName; text: string };
  forward: { icon: IconName; text: string };
  first: boolean;
  last: boolean;
  onStep: (by: -1 | 1) => void;
  onPointerDown?: () => void;
  draggable?: boolean;
  extra?: { icon: IconName; text: string; onSelect: () => void };
}) {
  const [button, setButton] = useState<HTMLButtonElement | null>(null);
  const [open, setOpen] = useState(false);
  const pick = (act: () => void) => () => {
    setOpen(false);
    act();
  };
  return (
    <>
      <Button
        ref={setButton}
        variant="icon"
        size="sm"
        className={className}
        aria-label={label}
        aria-haspopup="dialog"
        aria-expanded={open}
        draggable={draggable}
        onPointerDown={onPointerDown}
        onClick={() => setOpen((was) => !was)}
      >
        <Icon name={icon} size={size} />
      </Button>
      <Menu isOpen={open} onClose={() => setOpen(false)} anchor={button} label={label} align={align}>
        <MenuGroup>
          <MenuItem icon={back.icon} disabled={first} onSelect={pick(() => onStep(-1))}>{back.text}</MenuItem>
          <MenuItem icon={forward.icon} disabled={last} onSelect={pick(() => onStep(1))}>{forward.text}</MenuItem>
        </MenuGroup>
        {extra && (
          <MenuGroup>
            <MenuItem icon={extra.icon} onSelect={pick(extra.onSelect)}>{extra.text}</MenuItem>
          </MenuGroup>
        )}
      </Menu>
    </>
  );
}

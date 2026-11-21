import { useEffect } from "react";
import { Kbd, Menu, MenuGroup, MenuItem } from "../../ui";
import { PRIORITY_LABEL, PRIORITY_LEVELS, type PriorityLevel } from "./priority";
import "./priority.css";

const BARS: Partial<Record<PriorityLevel, number>> = { high: 3, medium: 2, low: 1 };

/** A level's mark: three dashes for none, a filled square for Urgent, and
 *  three bars, as many lit as the level is high. It decorates the level's
 *  word, or stands for it with the word as its accessible name. */
export function PriorityMark({ level, size = 14, label }: { level: PriorityLevel; size?: number; label?: string }) {
  const named = label ? { role: "img", "aria-label": label } : { "aria-hidden": true as const };
  if (level === "urgent") {
    return (
      <svg className="app-priority-mark" data-level={level} viewBox="0 0 16 16" width={size} height={size} {...named}>
        <rect className="app-priority-urgent" x="1" y="1" width="14" height="14" rx="3" />
        <rect className="app-priority-urgent-glyph" x="7" y="3.5" width="2" height="6" rx="1" />
        <rect className="app-priority-urgent-glyph" x="7" y="11" width="2" height="2" rx="1" />
      </svg>
    );
  }
  if (level === "none") {
    return (
      <svg className="app-priority-mark" data-level={level} viewBox="0 0 16 16" width={size} height={size} {...named}>
        {[1.5, 6.5, 11.5].map((x) => <rect key={x} className="app-priority-dash" x={x} y="7.25" width="3" height="1.5" rx="0.75" />)}
      </svg>
    );
  }
  const lit = BARS[level] ?? 0;
  return (
    <svg className="app-priority-mark" data-level={level} viewBox="0 0 16 16" width={size} height={size} {...named}>
      {[0, 1, 2].map((bar) => (
        <rect
          key={bar}
          className="app-priority-bar"
          data-lit={bar < lit || undefined}
          x={1.5 + bar * 5}
          y={10 - bar * 3.5}
          width="3"
          height={4.5 + bar * 3.5}
          rx="1"
        />
      ))}
    </svg>
  );
}

/** The priority menu: every level with its key, the current one ticked. The
 *  keys 0 to 4 pick a level while it is open. */
export function PriorityMenu({ current, label, anchor, isOpen, onClose, onPick }: {
  current: PriorityLevel;
  label: string;
  anchor: HTMLElement | null;
  isOpen: boolean;
  onClose: () => void;
  onPick: (level: PriorityLevel) => void;
}) {
  useEffect(() => {
    if (!isOpen) return;
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.metaKey || event.ctrlKey || event.altKey) return;
      const level = PRIORITY_LEVELS[Number(event.key)];
      if (!level || !/^[0-4]$/.test(event.key)) return;
      event.preventDefault();
      onPick(level);
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [isOpen, onPick]);

  return (
    <Menu isOpen={isOpen} onClose={onClose} anchor={anchor} label={label} align="start">
      <MenuGroup>
        {PRIORITY_LEVELS.map((level, key) => (
          <MenuItem
            key={level}
            current={level === current}
            shortcut={String(key)}
            lead={<PriorityMark level={level} />}
            detail={<Kbd>{key}</Kbd>}
            onSelect={() => onPick(level)}
          >
            {PRIORITY_LABEL[level]()}
          </MenuItem>
        ))}
      </MenuGroup>
    </Menu>
  );
}

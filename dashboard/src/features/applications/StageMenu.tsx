import { useEffect, type ReactNode } from "react";
import { STAGE_LABEL, type StageSlug } from "../../copy/vocabulary";
import { date as formatDate } from "../../copy/format";
import { Kbd, Menu, MenuGroup, MenuItem } from "../../ui";
import {
  applicationsColumnClosed,
  applicationsColumnDecided,
  applicationsMenuMoveTo,
} from "../../copy/gen/applications";
import { CLOSED_STAGES, DECIDED_STAGES, MOVING_STAGES, boardStage } from "./board";

export interface StageMenuProps {
  current: StageSlug;
  label: string;
  anchor: HTMLElement | null;
  isOpen: boolean;
  onClose: () => void;
  onMove: (stage: StageSlug) => void;
  /** When the application reached each stage. A stage it skipped has no date. */
  reached?: ReadonlyMap<StageSlug, string>;
  /** A last group below the stages, such as leaving the pipeline. */
  children?: ReactNode;
}

/** Every stage an application can move to, the one path that needs no
 *  pointer, shared by a board card and the application page. The moving
 *  stages answer to the number keys 1 to 5 while the menu is open. The
 *  current stage carries a tick, and choosing it changes nothing. */
export function StageMenu({ current, label, anchor, isOpen, onClose, onMove, reached, children }: StageMenuProps) {
  useEffect(() => {
    if (!isOpen) return;
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.metaKey || event.ctrlKey || event.altKey) return;
      const stage = MOVING_STAGES[Number(event.key) - 1];
      if (!stage) return;
      event.preventDefault();
      onMove(stage);
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [isOpen, onMove]);

  const group = (heading: string, stages: readonly StageSlug[], keyed: boolean) => (
    <MenuGroup label={heading}>
      {stages.map((stage, index) => {
        const on = reached?.get(stage);
        return (
          <MenuItem
            key={stage}
            current={stage === boardStage(current)}
            shortcut={keyed ? String(index + 1) : undefined}
            lead={keyed ? <Kbd>{index + 1}</Kbd> : undefined}
            detail={on ? formatDate(on, "day") : undefined}
            onSelect={() => onMove(stage)}
          >
            {STAGE_LABEL[stage]}
          </MenuItem>
        );
      })}
    </MenuGroup>
  );

  return (
    <Menu isOpen={isOpen} onClose={onClose} anchor={anchor} label={label}>
      {group(applicationsMenuMoveTo(), MOVING_STAGES, true)}
      {group(applicationsColumnDecided(), DECIDED_STAGES, false)}
      {group(applicationsColumnClosed(), CLOSED_STAGES, false)}
      {children && <MenuGroup>{children}</MenuGroup>}
    </Menu>
  );
}

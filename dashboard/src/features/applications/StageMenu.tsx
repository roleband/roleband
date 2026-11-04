import { useEffect, type ReactNode } from "react";
import { STAGE_LABEL, type StageSlug } from "../../copy/vocabulary";
import { date as formatDate } from "../../copy/format";
import { Button, Icon, Kbd, Popover } from "../../ui";
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
    <div className="app-menu-group" role="group" aria-label={heading}>
      <span className="app-menu-heading" aria-hidden="true">{heading}</span>
      {stages.map((stage, index) => {
        const chosen = stage === boardStage(current);
        const on = reached?.get(stage);
        return (
          <Button
            key={stage}
            variant="ghost"
            size="sm"
            className="app-menu-option"
            aria-current={chosen || undefined}
            aria-keyshortcuts={keyed ? String(index + 1) : undefined}
            onClick={() => onMove(stage)}
          >
            {keyed && <span className="app-menu-key" aria-hidden="true"><Kbd>{index + 1}</Kbd></span>}
            <span className="app-menu-name">{STAGE_LABEL[stage]}</span>
            {on && <span className="app-menu-reached">{formatDate(on, "day")}</span>}
            {chosen && <Icon name="check" size={14} />}
          </Button>
        );
      })}
    </div>
  );

  return (
    <Popover isOpen={isOpen} onClose={onClose} anchor={anchor} align="end" label={label} className="app-overlay app-menu">
      {group(applicationsMenuMoveTo(), MOVING_STAGES, true)}
      {group(applicationsColumnDecided(), DECIDED_STAGES, false)}
      {group(applicationsColumnClosed(), CLOSED_STAGES, false)}
      {children && <div className="app-menu-group">{children}</div>}
    </Popover>
  );
}

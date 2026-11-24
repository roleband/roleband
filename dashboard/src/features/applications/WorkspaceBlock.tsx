import type { ReactNode } from "react";
import { Button, Icon } from "../../ui";
import {
  applicationsFactsInterviews,
  applicationsFeedTitle,
  applicationsNotesTitle,
  applicationsWsAboutActivity,
  applicationsWsAboutInterviews,
  applicationsWsAboutNext,
  applicationsWsAboutNotes,
  applicationsWsHide,
  applicationsWsMove,
  applicationsWsMoveDown,
  applicationsWsMoveUp,
  applicationsWsNext,
} from "../../copy/gen/applications";
import { ReorderMenu, type DragItemProps } from "./useReorder";
import type { WorkspaceSection } from "./workspaceSections";

export const SECTION_LABEL: Record<WorkspaceSection, () => string> = {
  interviews: applicationsFactsInterviews,
  next: applicationsWsNext,
  notes: applicationsNotesTitle,
  activity: applicationsFeedTitle,
};

/** What each block holds, said where a hidden one is offered back. */
export const SECTION_ABOUT: Record<WorkspaceSection, () => string> = {
  interviews: applicationsWsAboutInterviews,
  next: applicationsWsAboutNext,
  notes: applicationsWsAboutNotes,
  activity: applicationsWsAboutActivity,
};

/** What a block needs of the Workspace to move and hide. */
export interface BlockReorder {
  item: DragItemProps;
  first: boolean;
  last: boolean;
  onArm: () => void;
  onStep: (by: -1 | 1) => void;
  onHide: () => void;
}

/** One block of the Workspace: its caption, its tools at the caption's end,
 *  its content under them, with no frame; a hairline parts it from the block
 *  above. Pointed at or focused, it shows a grip in the margin to move it, an
 *  eye beside its caption to hide it (unless it is the last block shown) and
 *  its own tools. The caption takes focus when
 *  the block is left alone, so the keyboard has a place to stay. */
export function Block({ section, action, alone, children, reorder }: {
  section: WorkspaceSection;
  action?: ReactNode;
  alone: boolean;
  children: ReactNode;
  reorder: BlockReorder;
}) {
  const id = `app-ws-${section}`;
  const label = SECTION_LABEL[section]();
  const grip = applicationsWsMove({ section: label });
  return (
    <section className="app-ws-card" data-section={section} aria-labelledby={id} {...reorder.item}>
      {!alone && (
        <ReorderMenu
          label={grip}
          icon="grip"
          size={16}
          className="app-ws-grip"
          align="start"
          back={{ icon: "arrowUp", text: applicationsWsMoveUp() }}
          forward={{ icon: "arrowDown", text: applicationsWsMoveDown() }}
          first={reorder.first}
          last={reorder.last}
          onStep={reorder.onStep}
          onPointerDown={reorder.onArm}
        />
      )}
      <div className="app-ws-head">
        <h2 id={id} className="app-ws-label" tabIndex={-1}>{label}</h2>
        {!alone && (
          <Button variant="icon" size="sm" className="app-ws-eye" aria-label={applicationsWsHide({ section: label })} onClick={reorder.onHide}>
            <Icon name="eye" size={14} />
          </Button>
        )}
        <span className="app-tile-spacer" />
        {action}
      </div>
      <div className="app-ws-body">{children}</div>
    </section>
  );
}

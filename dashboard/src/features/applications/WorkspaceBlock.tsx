import type { ReactNode } from "react";
import { Button, Icon } from "../../ui";
import {
  applicationsFactsInterviews,
  applicationsFeedTitle,
  applicationsInterviewOutcome,
  applicationsNotesTitle,
  applicationsWsAboutActivity,
  applicationsWsAboutInterviews,
  applicationsWsAboutNext,
  applicationsWsAboutNotes,
  applicationsWsAboutOutcome,
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
  outcome: applicationsInterviewOutcome,
  activity: applicationsFeedTitle,
};

/** What each block holds, said where a hidden one is offered back. */
export const SECTION_ABOUT: Record<WorkspaceSection, () => string> = {
  interviews: applicationsWsAboutInterviews,
  next: applicationsWsAboutNext,
  notes: applicationsWsAboutNotes,
  outcome: applicationsWsAboutOutcome,
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

/** One block of the Workspace, a card: its caption at the top left, its one
 *  action at the top right, its content under them. Pointed at or focused, it
 *  shows a grip in the margin to move it and an eye beside its caption to
 *  hide it, unless it is the last block shown. The caption takes focus when
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

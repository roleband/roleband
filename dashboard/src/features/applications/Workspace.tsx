import { Suspense, lazy, useRef, useState, type ReactNode } from "react";
import type { ActivityItem, ApplicationCard, ApplicationDetail, ApplicationInterview, ApplicationStep, NotesVersion } from "../../api";
import { date as formatDate } from "../../copy/format";
import { STAGE_LABEL } from "../../copy/vocabulary";
import { Button, Icon, Menu, MenuGroup, MenuItem, useToast } from "../../ui";
import {
  applicationsMoveUndo,
  applicationsWsAdd,
  applicationsWsHidden,
  applicationsWsLayoutFailed,
  applicationsWsNotesHint,
} from "../../copy/gen/applications";
import { ActivityFeed } from "./ActivityFeed";
import { useFocusAfter } from "./focusAfter";
import { endingName } from "./StageLabel";
import { NextSteps } from "./NextSteps";
import type { NotesSaved } from "./NotesEditor";
import { NotesHelp } from "./NotesHelp";
import { useReorder } from "./useReorder";
import { useSectionLayout } from "./useSectionLayout";
import { Block, SECTION_ABOUT, SECTION_LABEL, type BlockReorder } from "./WorkspaceBlock";
import { AddInterview, Interviews, type Outcome } from "./WorkspaceInterviews";
import { workspaceStage, type WorkspaceSection } from "./workspaceSections";

const NotesEditor = lazy(() => import("./NotesEditor"));

/** The notes page. Its editor is a chunk of its own, loaded when the page
 *  first shows; until then the notes stand as text where the page will be,
 *  so nothing moves when it arrives. */
function Notes({ notes, onSave, loadVersions }: {
  notes: string | null;
  onSave: (notes: string, was: string) => Promise<NotesSaved>;
  loadVersions: () => Promise<NotesVersion[]>;
}) {
  return (
    <Suspense fallback={<div className="app-notes"><p className="app-ws-notes">{notes || applicationsWsNotesHint()}</p></div>}>
      <NotesEditor notes={notes} onSave={onSave} loadVersions={loadVersions} />
    </Suspense>
  );
}

function OutcomeLine({ card }: { card: ApplicationCard }) {
  return (
    <p className="app-ws-outcome">
      <strong>{endingName(card) ?? STAGE_LABEL[card.stage]}</strong>
      {card.stage_since && <span className="app-ws-round-when">{formatDate(card.stage_since, "full")}</span>}
    </p>
  );
}

export interface WorkspaceProps {
  card: ApplicationCard;
  detail: ApplicationDetail;
  notes: string | null;
  activity: readonly ActivityItem[];
  now: Date;
  onAddStep: (text: string, due: string | null) => Promise<boolean>;
  onEditStep: (step: ApplicationStep, text: string, due: string | null) => Promise<boolean>;
  onFinishStep: (step: ApplicationStep) => void;
  onReopenStep: (step: ApplicationStep) => Promise<boolean>;
  onRemoveStep: (step: ApplicationStep) => Promise<boolean>;
  onSaveNotes: (notes: string, was: string) => Promise<NotesSaved>;
  onLoadNotesVersions: () => Promise<NotesVersion[]>;
  onAddInterview: () => void;
  onEditInterview: (interview: ApplicationInterview, at?: "notes") => void;
  onOutcome: (interview: ApplicationInterview, outcome: Outcome) => void;
  onAddComment: (body: string) => Promise<boolean>;
  onEditComment: (id: number, body: string) => Promise<boolean>;
  onDeleteComment: (id: number) => Promise<boolean>;
}

/** The person's own work on the role: the blocks the stage offers, each a
 *  card, the notes page and the role's activity among them. A block moves by
 *  its grip and hides by its eye; the plus under the last block brings a
 *  hidden one back. Order and what is hidden are kept per stage, with the
 *  person's settings; the blocks are drawn once those are read. */
export function Workspace(props: WorkspaceProps) {
  const { card, detail, notes, activity, now } = props;
  const stage = workspaceStage(card);
  const { toast } = useToast();
  const focusAfter = useFocusAfter();
  const host = useRef<HTMLDivElement>(null);
  const layout = useSectionLayout(stage, () =>
    toast({ key: "workspace-layout", tone: "error", text: applicationsWsLayoutFailed() }),
  );
  const { shown, offeredBack } = layout;
  const [addFrom, setAddFrom] = useState<HTMLButtonElement | null>(null);
  const [adding, setAdding] = useState(false);
  const dnd = useReorder<WorkspaceSection>({ axis: "y", grip: true, onPlace: layout.place });

  const inBlock = (section: WorkspaceSection, control: string) => () =>
    host.current?.querySelector<HTMLElement>(`[data-section="${section}"] ${control}`) ?? null;

  const hide = (section: WorkspaceSection) => {
    // The Workspace always shows one block.
    if (shown.length <= 1) return;
    const at = shown.indexOf(section);
    const next = shown[at + 1] ?? shown[at - 1];
    // A block left alone has no eye: its caption takes focus.
    focusAfter(() => inBlock(next, ".app-ws-eye")() ?? inBlock(next, ".app-ws-label")());
    layout.hide(section);
    toast({
      key: "workspace",
      text: applicationsWsHidden({ section: SECTION_LABEL[section]() }),
      action: { label: applicationsMoveUndo(), onClick: () => layout.show(section) },
    });
  };
  const step = (section: WorkspaceSection, by: -1 | 1) => {
    focusAfter(inBlock(section, ".app-ws-grip"));
    layout.step(section, by);
  };

  const reorderFor = (section: WorkspaceSection, index: number): BlockReorder => ({
    item: dnd.itemProps(section),
    first: index === 0,
    last: index === shown.length - 1,
    onArm: () => dnd.arm(section),
    onStep: (by) => step(section, by),
    onHide: () => hide(section),
  });

  const content: Record<WorkspaceSection, () => ReactNode> = {
    interviews: () => (
      <Interviews interviews={detail.interviews} role={card} now={now} onEdit={props.onEditInterview} onOutcome={props.onOutcome} />
    ),
    next: () => (
      <NextSteps
        steps={card.steps}
        done={detail.done_steps}
        now={now}
        onAdd={props.onAddStep}
        onEdit={props.onEditStep}
        onFinish={props.onFinishStep}
        onReopen={props.onReopenStep}
        onRemove={props.onRemoveStep}
      />
    ),
    notes: () => <Notes notes={notes} onSave={props.onSaveNotes} loadVersions={props.onLoadNotesVersions} />,
    outcome: () => <OutcomeLine card={card} />,
    activity: () => (
      <ActivityFeed
        items={activity}
        detail={detail}
        now={now}
        onAdd={props.onAddComment}
        onEdit={props.onEditComment}
        onDelete={props.onDeleteComment}
      />
    ),
  };
  const action: Partial<Record<WorkspaceSection, ReactNode>> = {
    interviews: <AddInterview onAdd={props.onAddInterview} />,
    notes: <NotesHelp />,
  };

  if (!layout.ready) return <div className="app-ws" aria-busy="true" />;

  return (
    <div className="app-ws" ref={host} data-dragging={dnd.dragging ? "" : undefined}>
      {shown.map((section, index) => (
        <Block key={section} section={section} action={action[section]} alone={shown.length === 1} reorder={reorderFor(section, index)}>
          {content[section]()}
        </Block>
      ))}
      {offeredBack.length > 0 && (
        <div className="app-ws-foot">
          <Button
            ref={setAddFrom}
            variant="ghost"
            className="app-ws-add"
            aria-label={applicationsWsAdd()}
            aria-haspopup="dialog"
            aria-expanded={adding}
            onClick={() => setAdding((was) => !was)}
          >
            <Icon name="plus" size={22} />
          </Button>
          <Menu isOpen={adding} onClose={() => setAdding(false)} anchor={addFrom} label={applicationsWsAdd()}>
            <MenuGroup>
              {offeredBack.map((section) => (
                <MenuItem
                  key={section}
                  onSelect={() => {
                    setAdding(false);
                    focusAfter(inBlock(section, ".app-ws-eye"));
                    layout.show(section);
                  }}
                  hint={SECTION_ABOUT[section]()}
                >
                  {SECTION_LABEL[section]()}
                </MenuItem>
              ))}
            </MenuGroup>
          </Menu>
        </div>
      )}
    </div>
  );
}

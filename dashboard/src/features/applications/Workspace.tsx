import { useEffect, useRef, useState, type ReactNode } from "react";
import { createPortal } from "react-dom";
import type { ActivityItem, ApplicationCard, ApplicationDetail, ApplicationInterview, ApplicationStep, NotesVersion } from "../../api";
import { useMediaQuery } from "../../hooks/useMediaQuery";
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
import { NextSteps } from "./NextSteps";
import type { NotesSaved } from "./NotesEditor";
import { loadNotesEditor, notesEditorNow } from "./notesEditorChunk";
import { NotesHelp } from "./NotesHelp";
import { useReorder } from "./useReorder";
import { useSectionLayout } from "./useSectionLayout";
import { Block, SECTION_ABOUT, SECTION_LABEL, type BlockReorder } from "./WorkspaceBlock";
import { type Outcome } from "./OutcomeAsk";
import { Interviews } from "./WorkspaceInterviews";
import { standsBeside, workspaceStage, type WorkspaceSection } from "./workspaceSections";

/** The notes page. Its editor is a chunk of its own, asked for before the
 *  first Workspace opens (notesEditorChunk), so it is usually here and drawn
 *  from the first frame. Where it is not, the notes stand as text in its
 *  place, so nothing moves when it arrives, and it arrives the moment it has
 *  loaded; a press on that text is a press into the notes, which the editor
 *  takes up with the caret at their end. */
function Notes({ notes, onSave, loadVersions, tools }: {
  notes: string | null;
  onSave: (notes: string, was: string, putBack?: boolean) => Promise<NotesSaved>;
  loadVersions: () => Promise<NotesVersion[]>;
  tools: HTMLElement | null;
}) {
  // Chosen once: the editor is never swapped under what is written in it.
  const [Editor, setEditor] = useState(notesEditorNow);
  const [failed, setFailed] = useState<unknown>(null);
  const pressed = useRef(false);
  useEffect(() => {
    if (Editor) return;
    let waiting = true;
    loadNotesEditor().then(
      (loaded) => {
        if (waiting) setEditor(() => loaded);
      },
      (error: unknown) => {
        if (waiting) setFailed(error ?? new Error("the notes editor did not load"));
      },
    );
    return () => {
      waiting = false;
    };
  }, [Editor]);
  // The press is taken up only if the person is still waiting in the notes:
  // one who went on to write in another field keeps the keyboard there.
  useEffect(() => {
    if (Editor) return;
    const letGo = (event: FocusEvent) => {
      if (event.target instanceof Element && event.target.matches('input, textarea, select, [contenteditable="true"]')) pressed.current = false;
    };
    document.addEventListener("focusin", letGo);
    return () => document.removeEventListener("focusin", letGo);
  }, [Editor]);
  // A chunk that did not load is the page's failure to report, as any is.
  if (failed) throw failed;
  if (!Editor) {
    return (
      <div className="app-notes">
        <p className="app-ws-notes" onPointerDown={() => { pressed.current = true; }}>{notes || applicationsWsNotesHint()}</p>
      </div>
    );
  }
  return <Editor notes={notes} onSave={onSave} loadVersions={loadVersions} tools={tools} focusAtEnd={pressed.current} />;
}

export interface WorkspaceProps {
  card: ApplicationCard;
  detail: ApplicationDetail;
  notes: string | null;
  activity: readonly ActivityItem[];
  /** Set when the feed could not be read: said in its place, with Try again. */
  activityFailed?: Error | null;
  onRetryActivity?: () => void;
  now: Date;
  onAddStep: (text: string, due: string | null) => Promise<boolean>;
  onEditStep: (step: ApplicationStep, text: string, due: string | null) => Promise<boolean>;
  onFinishStep: (step: ApplicationStep) => void;
  onReopenStep: (step: ApplicationStep) => Promise<boolean>;
  onRemoveStep: (step: ApplicationStep) => Promise<boolean>;
  onSaveNotes: (notes: string, was: string, putBack?: boolean) => Promise<NotesSaved>;
  onLoadNotesVersions: () => Promise<NotesVersion[]>;
  onAddInterview: () => void;
  onEditInterview: (interview: ApplicationInterview, at?: "notes") => void;
  onOutcome: (interview: ApplicationInterview, outcome: Outcome) => void;
  onAddComment: (body: string) => Promise<boolean>;
  onEditComment: (id: number, body: string) => Promise<boolean>;
  onDeleteComment: (id: number) => Promise<boolean>;
  /** The role page's side column, where it has one. In a window wide enough
   *  the short lists (next steps, interviews) are drawn there, beside the
   *  writing; without it, or in a narrower window, every block is one list. */
  side?: HTMLElement | null;
}

/** From this width the role page's side column has room for the short lists. */
export const WORKSPACE_TWO_COLUMNS = "(min-width: 1100px)";

/** The person's own work on the role: the blocks the stage offers, the notes
 *  page and the role's activity among them. With two columns the writing
 *  (notes, activity) is the main one and the short lists stand beside it; a
 *  block moves by its grip within its column and hides by its eye; the plus
 *  under the last block brings a hidden one back. Order and what is hidden
 *  are kept per stage as one list, with the person's settings, so a narrower
 *  window shows the same blocks in that order; the blocks are drawn once
 *  those are read. */
export function Workspace(props: WorkspaceProps) {
  const { card, detail, notes, activity, now } = props;
  const stage = workspaceStage(card);
  const { toast } = useToast();
  const focusAfter = useFocusAfter();
  const host = useRef<HTMLDivElement>(null);
  const beside = useRef<HTMLDivElement>(null);
  const wide = useMediaQuery(WORKSPACE_TWO_COLUMNS);
  const split = wide && props.side != null;
  const [notesTools, setNotesTools] = useState<HTMLElement | null>(null);
  const layout = useSectionLayout(stage, () =>
    toast({ key: "workspace-layout", tone: "error", text: applicationsWsLayoutFailed() }),
  );
  const { shown, offeredBack } = layout;
  const [addFrom, setAddFrom] = useState<HTMLButtonElement | null>(null);
  const [adding, setAdding] = useState(false);
  // One order for each column: a block is carried, and steps, among the
  // blocks of its own column.
  const dnd = useReorder<WorkspaceSection>({ axis: "y", grip: true, onPlace: layout.place });
  const dndBeside = useReorder<WorkspaceSection>({ axis: "y", grip: true, onPlace: layout.place });
  const main = split ? shown.filter((section) => !standsBeside(section)) : shown;
  const aside = split ? shown.filter(standsBeside) : [];

  const inBlock = (section: WorkspaceSection, control: string) => () => {
    const find = `[data-section="${section}"] ${control}`;
    return host.current?.querySelector<HTMLElement>(find) ?? beside.current?.querySelector<HTMLElement>(find) ?? null;
  };

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
  const step = (column: readonly WorkspaceSection[], section: WorkspaceSection, by: -1 | 1) => {
    const neighbour = column[column.indexOf(section) + by];
    if (!neighbour) return;
    focusAfter(inBlock(section, ".app-ws-grip"));
    layout.place(section, neighbour, by > 0 ? "after" : "before");
  };

  const reorderFor = (column: readonly WorkspaceSection[], drag: typeof dnd, section: WorkspaceSection, index: number): BlockReorder => ({
    item: drag.itemProps(section),
    first: index === 0,
    last: index === column.length - 1,
    onArm: () => drag.arm(section),
    onStep: (by) => step(column, section, by),
    onHide: () => hide(section),
  });

  const content: Record<WorkspaceSection, () => ReactNode> = {
    interviews: () => (
      <Interviews
        interviews={detail.interviews}
        role={card}
        now={now}
        onAdd={props.onAddInterview}
        onEdit={props.onEditInterview}
        onOutcome={props.onOutcome}
      />
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
    notes: () => <Notes notes={notes} onSave={props.onSaveNotes} loadVersions={props.onLoadNotesVersions} tools={notesTools} />,
    activity: () => (
      <ActivityFeed
        items={activity}
        failed={props.activityFailed}
        onRetry={props.onRetryActivity}
        detail={detail}
        now={now}
        onAdd={props.onAddComment}
        onEdit={props.onEditComment}
        onDelete={props.onDeleteComment}
      />
    ),
  };
  // The notes' own tools: the way to earlier versions, which the editor
  // draws into the block's head, and the guide.
  const action: Partial<Record<WorkspaceSection, ReactNode>> = {
    notes: (
      <>
        <span className="app-ws-tools" ref={setNotesTools} />
        <NotesHelp />
      </>
    ),
  };
  const blocks = (column: readonly WorkspaceSection[], drag: typeof dnd) => column.map((section, index) => (
    <Block
      key={section}
      section={section}
      action={action[section]}
      alone={shown.length === 1}
      reorder={reorderFor(column, drag, section, index)}
    >
      {content[section]()}
    </Block>
  ));

  if (!layout.ready) return <div className="app-ws" aria-busy="true" />;

  return (
    <>
    {split && props.side && aside.length > 0 && createPortal(
      <div className="app-ws" ref={beside} data-dragging={dndBeside.dragging ? "" : undefined}>
        {blocks(aside, dndBeside)}
      </div>,
      props.side,
    )}
    <div className="app-ws" ref={host} data-dragging={dnd.dragging ? "" : undefined}>
      {blocks(main, dnd)}
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
    </>
  );
}

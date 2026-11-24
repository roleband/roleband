import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Navigate, useLocation, useNavigate, useParams } from "react-router-dom";
import { STAGE_LABEL, type StageSlug } from "../../copy/vocabulary";
import { PageHeader } from "../../patterns/PageHeader";
import {
  PIPELINE_VIEW_PARAMS,
  pipelineViewScope,
} from "../../routing/pipelineViews";
import { useRememberedParams } from "../../routing/useRememberedParams";
import { useTabRoute } from "../../routing/useTabRoute";
import { TabBar } from "../../ui";
import { shellNavPipeline, shellTabPipelineBoard, shellTabPipelineList, shellTabPipelineUpNext } from "../../copy/gen/shell";
import { applicationsMoved, applicationsMovedHidden, applicationsTabsLabel } from "../../copy/gen/applications";
import { BoardView } from "./BoardView";
import { ListView } from "./ListView";
import { loadNotesEditor } from "./notesEditorChunk";
import { PipelineRowContext } from "./pipelineRow";
import { roleAddress } from "./roleLink";
import { columnOf } from "./board";
import { columnName, readHiddenColumns } from "./columnView";
import { UpNext } from "./UpNext";
import { useBoardController } from "./useBoardController";
import "./applications.css";

const PIPELINE_SLUGS = ["list", "board", "up-next"] as const;
type PipelineTab = (typeof PIPELINE_SLUGS)[number];
const TAB_LABEL: Record<PipelineTab, () => string> = {
  list: shellTabPipelineList,
  board: shellTabPipelineBoard,
  "up-next": shellTabPipelineUpNext,
};
const isApplication = (slug: string | undefined): slug is string => slug != null && /^\d+$/.test(slug);

/** The application pipeline. A role opens as its posting, so an address
 *  that names one by its job id (`/pipeline/<job id>`) goes to that posting,
 *  on the tab it names; every other slug is one of the pipeline's views. */
export function ApplicationsScreen() {
  const { tab } = useParams();
  const { search } = useLocation();
  if (isApplication(tab)) return <Navigate to={{ pathname: roleAddress(tab), search }} replace />;
  return <PipelineView />;
}

/** The place: its views, and the applications every view reads. One row
 *  leads the page: the views, then the tools of the one on screen, which that
 *  view draws there. The top bar and the rail name the place, so its title is
 *  not drawn. A view is reached from its tab or its rail entry, at a bare
 *  address; each has its own filter in its own address and finds it again on
 *  that arrival. The views share the data and nothing else, so switching
 *  reads nothing again. */
function PipelineView() {
  const { tab } = useTabRoute<PipelineTab>({ base: "/pipeline", slugs: PIPELINE_SLUGS, fallback: "list" });
  const navigate = useNavigate();
  // On the Board, a move's toast reads the columns hidden when it lands, from
  // where the board keeps them: a card that leaves for a hidden column is
  // said to. The hidden columns are the Board's alone, so a move on another
  // tab says only where the role went. Read through a ref, because the toast
  // is worded when the move lands, on whichever tab is open by then.
  const onBoard = useRef(tab === "board");
  onBoard.current = tab === "board";
  const said = useCallback((title: string, stage: StageSlug) => {
    const column = columnOf(stage);
    return onBoard.current && readHiddenColumns().includes(column.id)
      ? applicationsMovedHidden({ title, stage: STAGE_LABEL[stage], column: columnName(column.id) })
      : applicationsMoved({ title, stage: STAGE_LABEL[stage] });
  }, []);
  const board = useBoardController({ said });
  // One clock for every view, to the minute: a keystroke's render keeps the
  // same instant, so what the views derive from it is not computed again.
  const minute = Math.floor(Date.now() / 60_000);
  const now = useMemo(() => new Date(minute * 60_000), [minute]);
  // Every view here leads to a role's Workspace: its notes editor is asked
  // for now, so it is there when one opens. A load that fails is the
  // Workspace's to report, when it asks again.
  useEffect(() => {
    void loadNotesEditor().catch(() => undefined);
  }, []);
  const [row, setRow] = useState<HTMLDivElement | null>(null);
  const [slot, setSlot] = useState<HTMLDivElement | null>(null);
  const place = useMemo(() => ({ row, slot }), [row, slot]);

  return (
    // The List keeps Radar's ledger margin (patterns/jobs/margin.css) for its
    // compare beacon, and the row ends where its rows end; the board's columns
    // and Up next have none.
    <main className={tab === "list" ? "main app-main job-margin-page" : "main app-main"} data-design-system="app" data-view={tab}>
      <ViewMemory key={tab} slug={tab} />
      <PageHeader title={shellNavPipeline()} offScreen />
      <div className="app-toolbar app-pipeline-toolbar" data-selection="chrome" ref={setRow}>
        <TabBar
          className="app-tabbar"
          look="words"
          label={applicationsTabsLabel()}
          idPrefix="pipeline"
          controls="pipeline-tabpanel"
          value={tab}
          // A bare address, as from the rail: the view puts back its own filter.
          onChange={(next) => navigate(`/pipeline/${next}`)}
          tabs={PIPELINE_SLUGS.map((slug) => ({ id: slug, label: TAB_LABEL[slug]() }))}
        />
        <div className="app-pipeline-slot" ref={setSlot} />
      </div>
      <PipelineRowContext.Provider value={place}>
        <div
          id="pipeline-tabpanel"
          className="app-tabpanel"
          role="tabpanel"
          aria-labelledby={`pipeline-tab-${tab}`}
        >
          {tab === "list" && <ListView board={board} now={now} />}
          {tab === "board" && <BoardView board={board} now={now} />}
          {tab === "up-next" && (
            <UpNext
              resource={board.resource}
              now={now}
              actions={{ onFinishStep: board.finishStep, onSetOutcome: board.setOutcome }}
            />
          )}
        </div>
      </PipelineRowContext.Provider>
    </main>
  );
}

/** A view's filter memory. Keyed by the view, so each arrival at one is a
 *  mount, which is when `useRememberedParams` decides whether to restore. */
function ViewMemory({ slug }: { slug: PipelineTab }) {
  useRememberedParams(pipelineViewScope(slug), PIPELINE_VIEW_PARAMS);
  return null;
}

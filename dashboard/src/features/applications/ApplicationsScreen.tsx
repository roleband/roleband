import { useCallback, useRef } from "react";
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

/** The place: its summary, its views, and the applications every view reads.
 *  A view is reached from its tab or its rail entry, at a bare address; each
 *  has its own filter in its own address and finds it again on that arrival.
 *  The views share the data and nothing else, so switching reads nothing again. */
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
  // One clock per render, so every view measures from the same instant.
  const now = new Date();

  return (
    <main className="main app-main" data-design-system="app" data-view={tab}>
      <ViewMemory key={tab} slug={tab} />
      <PageHeader title={shellNavPipeline()} />
      <TabBar
        className="app-tabbar"
        label={applicationsTabsLabel()}
        idPrefix="pipeline"
        controls="pipeline-tabpanel"
        value={tab}
        // A bare address, as from the rail: the view puts back its own filter.
        onChange={(next) => navigate(`/pipeline/${next}`)}
        tabs={PIPELINE_SLUGS.map((slug) => ({ id: slug, label: TAB_LABEL[slug]() }))}
      />
      <div
        id="pipeline-tabpanel"
        // The List keeps Radar's ledger margin (patterns/jobs/margin.css) for
        // its compare beacon; the board's columns and Up next have none.
        className={tab === "list" ? "app-tabpanel job-margin-page" : "app-tabpanel"}
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
    </main>
  );
}

/** A view's filter memory. Keyed by the view, so each arrival at one is a
 *  mount, which is when `useRememberedParams` decides whether to restore. */
function ViewMemory({ slug }: { slug: PipelineTab }) {
  useRememberedParams(pipelineViewScope(slug), PIPELINE_VIEW_PARAMS);
  return null;
}

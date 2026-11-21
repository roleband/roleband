import { useCallback, useRef } from "react";
import { useNavigate, useParams, useSearchParams } from "react-router-dom";
import { STAGE_LABEL, type StageSlug } from "../../copy/vocabulary";
import { PageHeader } from "../../patterns/PageHeader";
import {
  PIPELINE_VIEW_PARAMS,
  pipelineViewScope,
  rememberedPipelineQuery,
} from "../../routing/pipelineViews";
import { useRememberedParams } from "../../routing/useRememberedParams";
import { useTabRoute } from "../../routing/useTabRoute";
import { Button } from "../../ui";
import { Msg } from "../../ui/Msg";
import { shellTabPipelineBoard, shellTabPipelineList, shellTabPipelineUpNext } from "../../copy/gen/shell";
import {
  applicationsBoardNeedNext,
  applicationsBoardSummary,
  applicationsMoved,
  applicationsMovedHidden,
} from "../../copy/gen/applications";
import { ApplicationPage } from "./ApplicationPage";
import { BoardView } from "./BoardView";
import { ListView } from "./ListView";
import { boardCounts, columnOf } from "./board";
import { columnName, readHiddenColumns } from "./columnView";
import { VIEW_FILTERS, readFilter, writeFilter } from "./filters";
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

/** The application pipeline. `/pipeline/<job id>` is one application's page;
 *  every other slug is one of the pipeline's views, each a rail entry. */
export function ApplicationsScreen() {
  const { tab } = useParams();
  // Keyed by the role, so stepping to a neighbour starts its page afresh.
  if (isApplication(tab)) return <ApplicationPage key={tab} jobId={Number(tab)} />;
  return <PipelineView />;
}

/** The view on screen, titled by its rail entry, and the applications every
 *  view reads. Each view has its own filter in its own address, and finds it
 *  again when the rail brings the person back to a bare one; the views share
 *  the data and nothing else, so switching views reads nothing again. */
function PipelineView() {
  const { tab } = useTabRoute<PipelineTab>({ base: "/pipeline", slugs: PIPELINE_SLUGS, fallback: "list" });
  const navigate = useNavigate();
  const [params] = useSearchParams();
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
  const counts = boardCounts(board.cards);

  // A filter change within a view is not a destination.
  const open = (next: PipelineTab, search: string) =>
    navigate({ pathname: `/pipeline/${next}`, search }, { replace: next === tab });
  // The summary's count is the board's: its link opens the board with that
  // filter added to whatever the board was last left with.
  const boardParams = tab === "board" ? new URLSearchParams(params) : rememberedPipelineQuery("board");
  const boardFilter = readFilter(boardParams, VIEW_FILTERS.board);
  const needNext = tab === "board" && boardFilter.quick.includes("needs_next");
  const showNeedNext = () =>
    open("board", writeFilter(boardParams, { ...boardFilter, quick: [...boardFilter.quick, "needs_next"] }).toString());

  return (
    <main className="main app-main" data-design-system="app" data-view={tab}>
      <ViewMemory key={tab} slug={tab} />
      <PageHeader title={TAB_LABEL[tab]()}
        // The line keeps its height while the board loads, so the tabs and
        // everything under them do not drop when the counts land.
        meta={!board.resource.data ? <p className="app-summary" aria-hidden="true">{"\u00a0"}</p> : (
          <p className="app-summary">
            <Msg
              of={applicationsBoardSummary}
              args={{ moving: counts.moving, decided: counts.decided, closed: counts.closed }}
              elems={{
                needNext: counts.needNextStep > 0 && !needNext ? (
                  <Button variant="link" onClick={showNeedNext}>
                    {applicationsBoardNeedNext({ count: counts.needNextStep })}
                  </Button>
                ) : applicationsBoardNeedNext({ count: counts.needNextStep }),
              }}
            />
          </p>
        )}
      />
      <div
        // The List keeps Radar's ledger margin (patterns/jobs/margin.css) for
        // its compare beacon; the board's columns and Up next have none.
        className={tab === "list" ? "app-tabpanel job-margin-page" : "app-tabpanel"}
      >
        {tab === "list" && <ListView board={board} now={now} />}
        {tab === "board" && <BoardView board={board} now={now} />}
        {tab === "up-next" && <UpNext resource={board.resource} now={now} />}
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

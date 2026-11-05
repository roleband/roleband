import { useCallback, useRef } from "react";
import { useLocation, useNavigate, useParams, useSearchParams } from "react-router-dom";
import { STAGE_LABEL, type StageSlug } from "../../copy/vocabulary";
import { PageHeader } from "../../patterns/PageHeader";
import { useTabRoute } from "../../routing/useTabRoute";
import { Button, TabBar } from "../../ui";
import { Msg } from "../../ui/Msg";
import { shellNavPipeline, shellTabPipelineBoard, shellTabPipelineList, shellTabPipelineUpNext } from "../../copy/gen/shell";
import {
  applicationsBoardNeedNext,
  applicationsBoardSummary,
  applicationsMoved,
  applicationsMovedHidden,
  applicationsTabsLabel,
} from "../../copy/gen/applications";
import { ApplicationPage } from "./ApplicationPage";
import { BoardView } from "./BoardView";
import { ListView } from "./ListView";
import { boardCounts, columnOf } from "./board";
import { columnName, readHiddenColumns } from "./columnView";
import { readFilter, writeFilter } from "./filters";
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
/** Where a history entry keeps the other tabs' queries. */
const LEFT = "pipelineTabsLeft";
const leftOf = (state: unknown): Partial<Record<PipelineTab, string>> => {
  const held = (state as Record<string, unknown> | null)?.[LEFT];
  return held && typeof held === "object" ? (held as Partial<Record<PipelineTab, string>>) : {};
};
const isApplication = (slug: string | undefined): slug is string => slug != null && /^\d+$/.test(slug);

/** The application pipeline. `/pipeline/<job id>` is one application's page;
 *  every other slug is one of the place's tabs. */
export function ApplicationsScreen() {
  const { tab } = useParams();
  // Keyed by the role, so stepping to a neighbour starts its page afresh.
  if (isApplication(tab)) return <ApplicationPage key={tab} jobId={Number(tab)} />;
  return <PipelineTabs />;
}

/** The place: its summary, its tabs, and the applications every tab reads.
 *  Each tab is a view of its own, with its own filter in its own address;
 *  the page shares the data and nothing else. */
function PipelineTabs() {
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

  // Each tab's query as it was left rides in the history entry, so coming
  // back finds the tab's own filter and never the other tab's. The entry
  // holds it, not the component, because Back and a reload must find it too.
  const left = leftOf(useLocation().state);
  const open = (next: PipelineTab, search = left[next] ?? "") => {
    // A filter change within a tab is not a destination.
    navigate(
      { pathname: `/pipeline/${next}`, search },
      { replace: next === tab, state: { [LEFT]: { ...left, [tab]: params.toString() } } },
    );
  };
  // The summary's count is the board's: its link opens the board with that
  // filter added to whatever the board already had.
  const boardParams = new URLSearchParams(tab === "board" ? params : left.board);
  const boardFilter = readFilter(boardParams);
  const needNext = tab === "board" && boardFilter.quick.includes("needs_next");
  const showNeedNext = () =>
    open("board", writeFilter(boardParams, { ...boardFilter, quick: [...boardFilter.quick, "needs_next"] }).toString());

  return (
    <main className="main app-main" data-design-system="app">
      <PageHeader title={shellNavPipeline()}
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
      <TabBar
        className="app-tabbar"
        label={applicationsTabsLabel()}
        idPrefix="pipeline"
        controls="pipeline-tabpanel"
        value={tab}
        onChange={(next) => open(next)}
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
        {tab === "up-next" && <UpNext resource={board.resource} now={now} />}
      </div>
    </main>
  );
}

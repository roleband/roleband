import { useRef, useState } from "react";
import { useParams } from "react-router-dom";
import type { ApplicationCard, InterviewWrite } from "../../api";
import { STAGE_LABEL, type StageSlug } from "../../copy/vocabulary";
import { PageHeader } from "../../patterns/PageHeader";
import { useTabRoute } from "../../routing/useTabRoute";
import { AsyncBoundary, Button, CountBadge, TabBar } from "../../ui";
import { shellNavPipeline, shellTabPipelineBoard, shellTabPipelineUpNext } from "../../copy/gen/shell";
import {
  applicationsBoardLoadFailed,
  applicationsBoardSummary,
  applicationsClosedHide,
  applicationsClosedHideLabel,
  applicationsClosedShow,
  applicationsColumnClosed,
  applicationsColumnDecided,
  applicationsColumnEmpty,
  applicationsColumnEmptySaved,
  applicationsSectionEmpty,
  applicationsTabsLabel,
} from "../../copy/gen/applications";
import { ApplicationPage } from "./ApplicationPage";
import { ApplicationTile } from "./ApplicationTile";
import { COLUMNS, boardCounts, byStage, type ColumnDef } from "./board";
import { readClosedHidden, writeClosedHidden } from "./closedColumn";
import { InterviewDialog } from "./InterviewDialog";
import { UpNext } from "./UpNext";
import { useCardDrag } from "./useCardDrag";
import { useBoardController } from "./useBoardController";
import "./applications.css";

const PIPELINE_SLUGS = ["board", "up-next"] as const;
type PipelineTab = (typeof PIPELINE_SLUGS)[number];
const TAB_LABEL: Record<PipelineTab, () => string> = {
  board: shellTabPipelineBoard,
  "up-next": shellTabPipelineUpNext,
};
const isApplication = (slug: string | undefined): slug is string => slug != null && /^\d+$/.test(slug);

const COLUMN_NAME: Record<ColumnDef["id"], () => string> = {
  saved: () => STAGE_LABEL.saved,
  researching: () => STAGE_LABEL.researching,
  networking: () => STAGE_LABEL.networking,
  applied: () => STAGE_LABEL.applied,
  interviewing: () => STAGE_LABEL.interviewing,
  offer: () => STAGE_LABEL.offer,
  decided: () => applicationsColumnDecided(),
  closed: () => applicationsColumnClosed(),
};

/** The application pipeline. `/pipeline/<job id>` is one application's page;
 *  every other slug is one of the place's tabs. */
export function ApplicationsScreen() {
  const { tab } = useParams();
  // Keyed by the role, so stepping to a neighbour starts its page afresh.
  if (isApplication(tab)) return <ApplicationPage key={tab} jobId={Number(tab)} />;
  return <PipelineTabs />;
}

/** The Board, every starred or pursued role as a card in the column of its
 *  stage, and Up next, what is due by day. Both read the same applications. */
function PipelineTabs() {
  const { tab, setTab } = useTabRoute<PipelineTab>({ base: "/pipeline", slugs: PIPELINE_SLUGS, fallback: "board" });
  const { cards, resource, move, remove } = useBoardController();
  const [asking, setAsking] = useState<ApplicationCard | null>(null);
  const [closedHidden, setClosedHidden] = useState(readClosedHidden);
  // One clock per render, so every card on the board measures from the same instant.
  const now = new Date();
  const groups = byStage(cards, now);
  const counts = boardCounts(cards);

  const hideClosed = (hidden: boolean) => {
    writeClosedHidden(hidden);
    setClosedHidden(hidden);
  };

  // Interviewing asks for the interview's date first: it is the column's
  // entry condition. Every other move is immediate.
  const ask = (card: ApplicationCard, stage: StageSlug) => {
    if (stage === "interviewing" && card.stage !== "interviewing") setAsking(card);
    else void move(card, stage);
  };
  const confirmInterview = (interview: InterviewWrite) => {
    const card = asking;
    setAsking(null);
    if (card) void move(card, "interviewing", interview);
  };
  // A drop is a move like the menu's, and asks for the same.
  const scroller = useRef<HTMLDivElement>(null);
  const { drag, handlers } = useCardDrag(scroller, ask);
  /** The stage a drop now would move the dragged card to. */
  const landing = drag && drag.target !== drag.stage ? drag.target : null;

  const shown = COLUMNS.filter((column) => !(closedHidden && column.id === "closed"));
  const closedCount = (groups.get("rejected")?.length ?? 0) + (groups.get("role_closed")?.length ?? 0);

  return (
    <main className="main app-main" data-design-system="app">
      <PageHeader title={shellNavPipeline()}
        meta={resource.data ? (
          <p className="app-summary">
            {applicationsBoardSummary({
              moving: counts.moving,
              decided: counts.decided,
              closed: counts.closed,
              needNext: counts.needNextStep,
            })}
          </p>
        ) : undefined}
      />
      <TabBar
        className="app-tabbar"
        label={applicationsTabsLabel()}
        idPrefix="pipeline"
        controls="pipeline-tabpanel"
        value={tab}
        onChange={setTab}
        tabs={PIPELINE_SLUGS.map((slug) => ({ id: slug, label: TAB_LABEL[slug]() }))}
      />
      <div id="pipeline-tabpanel" className="app-tabpanel" role="tabpanel" aria-labelledby={`pipeline-tab-${tab}`}>
      {tab === "up-next" ? <UpNext resource={resource} /> : <AsyncBoundary
        resource={resource}
        failed={applicationsBoardLoadFailed()}
        skeleton={<div className="app-board" aria-hidden="true" />}
      >
        {() => (
          <div className="app-board-scroll" ref={scroller}>
            <div className="app-board" data-dragging={drag ? "" : undefined}>
              {shown.map((column) => {
                const name = COLUMN_NAME[column.id]();
                const total = column.stages.reduce((sum, stage) => sum + (groups.get(stage)?.length ?? 0), 0);
                const sectioned = column.stages.length > 1;
                return (
                  <section
                    key={column.id}
                    className="app-column"
                    aria-labelledby={`app-column-${column.id}`}
                    data-drop-column={column.id}
                    data-drop-target={!sectioned && landing != null && column.stages.includes(landing) ? "" : undefined}
                  >
                    <div className="app-column-head">
                      <h2 id={`app-column-${column.id}`} className="app-column-name">{name}</h2>
                      <span className="app-column-count">{total}</span>
                      {column.id === "closed" && (
                        <Button
                          variant="ghost"
                          size="sm"
                          className="app-column-hide"
                          aria-label={applicationsClosedHideLabel()}
                          onClick={() => hideClosed(true)}
                        >
                          {applicationsClosedHide()}
                        </Button>
                      )}
                    </div>
                    {column.stages.map((stage) => {
                      const list = groups.get(stage) ?? [];
                      return (
                        <div
                          key={stage}
                          className="app-section"
                          role={sectioned ? "group" : undefined}
                          aria-label={sectioned ? STAGE_LABEL[stage] : undefined}
                          data-drop-stage={stage}
                          data-drop-target={sectioned && landing === stage ? "" : undefined}
                        >
                          {sectioned && (
                            <h3 className="app-section-name" aria-hidden="true">
                              {STAGE_LABEL[stage]} <span className="app-column-count">{list.length}</span>
                            </h3>
                          )}
                          {list.length === 0 && (
                            <p className="app-column-empty">
                              {sectioned
                                ? applicationsSectionEmpty()
                                : stage === "saved" ? applicationsColumnEmptySaved() : applicationsColumnEmpty()}
                            </p>
                          )}
                          {list.map((card) => (
                            <ApplicationTile
                              key={card.job_id}
                              card={card}
                              now={now}
                              onMove={ask}
                              onRemove={remove}
                              drag={handlers(card)}
                              dragged={drag?.jobId === card.job_id ? drag : null}
                            />
                          ))}
                        </div>
                      );
                    })}
                  </section>
                );
              })}
              {closedHidden && (
                <Button
                  variant="ghost"
                  size="sm"
                  className="app-closed-show"
                  aria-label={applicationsClosedShow()}
                  onClick={() => hideClosed(false)}
                >
                  {applicationsColumnClosed()}
                  <CountBadge className="app-closed-count">{closedCount}</CountBadge>
                </Button>
              )}
            </div>
          </div>
        )}
      </AsyncBoundary>}
      </div>
      {asking && (
        <InterviewDialog card={asking} moving onCancel={() => setAsking(null)} onSubmit={confirmInterview} />
      )}
    </main>
  );
}

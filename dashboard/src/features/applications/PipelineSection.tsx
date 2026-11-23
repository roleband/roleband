import { useState } from "react";
import type { ApplicationCard, ApplicationDetail } from "../../api";
import { recordDay } from "./recordDays";
import { STAGE_LABEL, type StageSlug } from "../../copy/vocabulary";
import { Button, Content, Icon, Msg, Popover } from "../../ui";
import {
  applicationsFactDays,
  applicationsFactDaysValue,
  applicationsPostingDue,
  applicationsPostingEnded,
  applicationsPostingHistoryInterview,
  applicationsPostingHistoryNow,
  applicationsPostingHistoryTitle,
  applicationsPostingHistoryToday,
  applicationsPostingInterview,
  applicationsPostingNextStep,
  applicationsPostingRow,
  applicationsPostingSinceToday,
  applicationsPostingStage,
  applicationsCardPriority,
  applicationsFactPriority,
  applicationsPriorityMenu,
} from "../../copy/gen/applications";
import { dueText } from "./DueBadge";
import { interviewWhen } from "./interviewWords";
import { CLOSED_STAGES, daysInStage, daysToSay, dueState, isMoving, stepDue } from "./board";
import { PRIORITY_LABEL, PRIORITY_STORED, priorityOf } from "./priority";
import { PriorityMark, PriorityMenu } from "./PriorityMark";
import { stageName } from "./StageLabel";
import { offeredSections, workspaceStage } from "./workspaceSections";

type History = Pick<ApplicationDetail, "stages_reached" | "interviews">;

/** Stages an application ends in without the person taking the role. */
const LOST: ReadonlySet<StageSlug> = new Set([...CLOSED_STAGES, "withdrawn", "declined"]);

interface Line {
  at: string;
  when: string;
  text: React.ReactNode;
  tone?: string;
}

/** The history, oldest first: each stage on the day it was last entered, and
 *  every interview held so far. A moving application ends on today's line,
 *  how long it has stood in its stage; an ended one ends on its ending. */
function historyLines(card: ApplicationCard, history: History, now: Date): Line[] {
  const lines: Line[] = history.stages_reached.map(({ stage, at }) => ({
    at,
    when: recordDay(at, now),
    text: STAGE_LABEL[stage],
    tone: LOST.has(stage) ? "is-closed" : undefined,
  }));
  for (const interview of history.interviews) {
    if (interview.outcome === "cancelled" || new Date(interview.scheduled_at) > now) continue;
    lines.push({
      at: interview.scheduled_at,
      when: recordDay(interview.scheduled_at, now),
      text: <Msg of={applicationsPostingHistoryInterview} elems={{ label: <Content text={interview.label} /> }} />,
    });
  }
  lines.sort((a, b) => new Date(a.at).getTime() - new Date(b.at).getTime());
  const days = daysToSay(card, now);
  if (isMoving(card) && days != null) {
    lines.push({
      at: now.toISOString(),
      when: applicationsPostingHistoryToday(),
      text: applicationsPostingHistoryNow({ stage: STAGE_LABEL[card.stage], days }),
    });
  }
  return lines;
}

/** The timeline itself, a component so it is built only while the popover
 *  draws it. */
function HistoryTimeline({ card, history, now, title }: {
  card: ApplicationCard;
  history: History;
  now: Date;
  title: string;
}) {
  return (
    <ol className="timeline jd-history" aria-label={title}>
      {historyLines(card, history, now).map((line, i) => (
        <li className={`tl-item${line.tone ? ` ${line.tone}` : ""}`} key={i}>
          <span className="tl-dot" />
          <span className="tl-when">{line.when}</span>
          <span>{line.text}</span>
        </li>
      ))}
    </ol>
  );
}

function HistoryButton({ card, history, now, column }: {
  card: ApplicationCard;
  history: History;
  now: Date;
  column: HTMLElement | null;
}) {
  const [open, setOpen] = useState(false);
  const [anchor, setAnchor] = useState<HTMLButtonElement | null>(null);
  const title = applicationsPostingHistoryTitle();
  return (
    <>
      <Button
        ref={setAnchor}
        variant="icon"
        size="sm"
        aria-label={title}
        title={title}
        aria-haspopup="dialog"
        aria-expanded={open}
        onClick={() => setOpen((was) => !was)}
      >
        <Icon name="clock" size={14} />
      </Button>
      <Popover isOpen={open} onClose={() => setOpen(false)} anchor={anchor} within={column} label={title} className="app-overlay jd-history-popover">
        <div className="jd-history-title">{title}</div>
        <HistoryTimeline card={card} history={history} now={now} title={title} />
      </Popover>
    </>
  );
}

/** The priority, set in place from its menu. */
function PriorityPick({ card, onPick }: { card: ApplicationCard; onPick: (stored: number) => void }) {
  const [open, setOpen] = useState(false);
  const [anchor, setAnchor] = useState<HTMLButtonElement | null>(null);
  const level = priorityOf(card);
  return (
    <>
      <Button
        ref={setAnchor}
        variant="ghost"
        size="sm"
        className="jd-pipeline-pick"
        aria-label={applicationsCardPriority({ level: PRIORITY_LABEL[level]() })}
        aria-haspopup="dialog"
        aria-expanded={open}
        onClick={() => setOpen((was) => !was)}
      >
        <PriorityMark level={level} />
        {PRIORITY_LABEL[level]()}
      </Button>
      <PriorityMenu
        current={level}
        label={applicationsPriorityMenu({ title: card.title })}
        anchor={anchor}
        isOpen={open}
        onClose={() => setOpen(false)}
        onPick={(picked) => {
          setOpen(false);
          onPick(PRIORITY_STORED[picked]);
        }}
      />
    </>
  );
}

/**
 * Where the posting's role stands in the pipeline, always in view above its
 * Details: the stage and its priority; how long it has stood there, with the
 * application's history on demand; and what waits: when the next interview
 * is, the next step, and the day that step is due. The rows are read, apart
 * from the priority, which is set here: the bar's stage button is where the
 * stage is changed. A row shows only when it has something to say. On the
 * Workspace the next step and its day are the main column's, and so are the
 * interviews at a stage whose Workspace lists them, so they are not repeated
 * here. An ended application says how and when it ended, and
 * nothing waits.
 */
export function PipelineSection({ card, history, now, column, workspace = false, onPriority }: {
  card: ApplicationCard;
  history: History;
  now: Date;
  /** The side column the history opens across. */
  column: HTMLElement | null;
  /** The Workspace is on screen beside the section. */
  workspace?: boolean;
  /** Sets the priority, as stored. */
  onPriority: (priority: number) => void;
}) {
  const moving = isMoving(card);
  const stage = stageName(card);
  const days = daysInStage(card, now);
  const roundsBeside = workspace && offeredSections(workspaceStage(card)).includes("interviews");
  const interview = moving && !roundsBeside ? card.next_interview : null;
  const step = moving && !workspace && card.next_action ? card.next_action : null;
  const due = step ? stepDue(card) : null;
  const historyButton = <HistoryButton card={card} history={history} now={now} column={column} />;

  return (
    <>
      <div className="section-title">{applicationsPostingRow()}</div>
      <dl className="kv jd-pipeline-facts">
        <dt>{applicationsPostingStage()}</dt>
        <dd>{stage}</dd>
        {moving && (
          <>
            <dt>{applicationsFactPriority()}</dt>
            <dd className="jd-listed"><PriorityPick card={card} onPick={onPriority} /></dd>
          </>
        )}
        {moving && days != null && (
          <>
            <dt>{applicationsFactDays()}</dt>
            <dd className="jd-listed">
              <span>{days >= 1 ? applicationsFactDaysValue({ days }) : applicationsPostingSinceToday()}</span>
              {historyButton}
            </dd>
          </>
        )}
        {!moving && card.stage_since && (
          <>
            <dt>{applicationsPostingEnded()}</dt>
            <dd className="jd-listed">
              <span>{recordDay(card.stage_since, now)}</span>
              {historyButton}
            </dd>
          </>
        )}
        {interview && (
          <>
            <dt>{applicationsPostingInterview()}</dt>
            <dd>{interviewWhen(interview, now)}</dd>
          </>
        )}
        {step && (
          <>
            <dt>{applicationsPostingNextStep()}</dt>
            <dd><Content text={step} /></dd>
          </>
        )}
        {due && (
          <>
            <dt>{applicationsPostingDue()}</dt>
            <dd className={dueState(due, now) === "overdue" ? "jd-pipeline-late" : undefined}>{dueText(due, now, { bare: true })}</dd>
          </>
        )}
      </dl>
    </>
  );
}

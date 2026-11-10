import { useState } from "react";
import { Link } from "react-router-dom";
import type { ApplicationCard, ApplicationDetail } from "../../api";
import { date as formatDate } from "../../copy/format";
import { STAGE_LABEL, type StageSlug } from "../../copy/vocabulary";
import { Badge, Button, Content, Icon, Msg, Popover } from "../../ui";
import {
  applicationsFactDays,
  applicationsFactDaysValue,
  applicationsPostingEnded,
  applicationsPostingHistory,
  applicationsPostingHistoryInterview,
  applicationsPostingHistoryNow,
  applicationsPostingHistoryTitle,
  applicationsPostingHistoryToday,
  applicationsPostingInterview,
  applicationsPostingNextStep,
  applicationsPostingNoStep,
  applicationsPostingRow,
  applicationsPostingSinceToday,
  applicationsPostingStage,
} from "../../copy/gen/applications";
import { interviewWhen } from "./ApplicationPanels";
import { DueBadge } from "./DueBadge";
import { CLOSED_STAGES, applicationPath, daysInStage, daysToSay, isMoving, stepDue } from "./board";
import { stageName } from "./StageLabel";

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
    when: formatDate(at, "day"),
    text: STAGE_LABEL[stage],
    tone: LOST.has(stage) ? "is-closed" : undefined,
  }));
  for (const interview of history.interviews) {
    if (interview.outcome === "cancelled" || new Date(interview.scheduled_at) > now) continue;
    lines.push({
      at: interview.scheduled_at,
      when: formatDate(interview.scheduled_at, "day"),
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
        variant="ghost"
        size="sm"
        aria-haspopup="dialog"
        aria-expanded={open}
        onClick={() => setOpen((was) => !was)}
      >
        <Icon name="clock" size={13} /> {applicationsPostingHistory()}
      </Button>
      <Popover isOpen={open} onClose={() => setOpen(false)} anchor={anchor} within={column} label={title} className="app-overlay jd-history-popover">
        <div className="jd-history-title">{title}</div>
        <HistoryTimeline card={card} history={history} now={now} title={title} />
      </Popover>
    </>
  );
}

/**
 * Where the posting's role stands in the pipeline, always in view above its
 * Details: the stage, which links to the application; how long it has stood
 * there, with the application's history on demand; and what waits, the next
 * interview and the next step, each with the board's own date. An ended
 * application says how and when it ended, and nothing waits.
 */
export function PipelineSection({ card, history, now, column }: {
  card: ApplicationCard;
  history: History;
  now: Date;
  /** The side column the history opens across. */
  column: HTMLElement | null;
}) {
  const moving = isMoving(card);
  const stage = stageName(card);
  const days = daysInStage(card, now);
  const interview = moving ? card.next_interview : null;
  const step = moving && card.next_action ? card.next_action : null;
  const due = step ? stepDue(card) : null;
  const historyButton = <HistoryButton card={card} history={history} now={now} column={column} />;

  return (
    <>
      <div className="section-title">{applicationsPostingRow()}</div>
      <dl className="kv jd-pipeline-facts">
        <dt>{applicationsPostingStage()}</dt>
        <dd>
          <Link className="jd-pipeline-link" to={applicationPath(card.job_id)}>
            <span className="jd-pipeline-text">{stage}</span>
            <Icon name="arrowRight" size={13} />
          </Link>
        </dd>
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
              <span>{formatDate(card.stage_since, "day")}</span>
              {historyButton}
            </dd>
          </>
        )}
        {interview && (
          <>
            <dt>{applicationsPostingInterview()}</dt>
            <dd className="jd-pipeline">
              <Content text={interview.label} />
              <Badge className="app-due" tone="neutral" variant="tint" size="sm">{interviewWhen(interview)}</Badge>
            </dd>
          </>
        )}
        {moving && (
          <>
            <dt>{applicationsPostingNextStep()}</dt>
            <dd className="jd-pipeline">
              {step ? <Content text={step} /> : <span className="jd-pipeline-none">{applicationsPostingNoStep()}</span>}
              {due && <DueBadge due={due} now={now} />}
            </dd>
          </>
        )}
      </dl>
    </>
  );
}

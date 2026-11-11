import { useState } from "react";
import { Link } from "react-router-dom";
import type { ApplicationCard, ApplicationDetail } from "../../api";
import { date as formatDate } from "../../copy/format";
import { STAGE_LABEL, type StageSlug } from "../../copy/vocabulary";
import { Button, Content, Icon, Msg, Popover } from "../../ui";
import {
  applicationsCardOverdue,
  applicationsFactDays,
  applicationsFactDaysValue,
  applicationsPostingDue,
  applicationsPostingDueDay,
  applicationsPostingEnded,
  applicationsPostingHistoryInterview,
  applicationsPostingHistoryNow,
  applicationsPostingHistoryTitle,
  applicationsPostingHistoryToday,
  applicationsPostingInterview,
  applicationsPostingNextStep,
  applicationsPostingOpen,
  applicationsPostingRow,
  applicationsPostingSinceToday,
  applicationsPostingStage,
} from "../../copy/gen/applications";
import { interviewWhen } from "./ApplicationPanels";
import { CLOSED_STAGES, applicationPath, dayOffset, daysInStage, daysOverdue, daysToSay, dueState, isMoving, stepDue, type Due } from "./board";
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

/** The day a step is due, as the Due row says it: how late a missed step is,
 *  else the day itself. The one row that takes a colour is a step past its
 *  date, the state that asks the person to act. */
function dueDay(due: Due, now: Date): string {
  if (dueState(due, now) === "overdue") return applicationsCardOverdue({ days: daysOverdue(due, now) });
  return applicationsPostingDueDay({ offset: dayOffset(due.on, now), date: formatDate(due.on, "weekday") });
}

/**
 * Where the posting's role stands in the pipeline, always in view above its
 * Details: the stage; how long it has stood there, with the application's
 * history on demand; and what waits: when the next interview is, the next
 * step, and the day that step is due. Every row is a label and plain words:
 * the section is read, and the bar's stage button is where the stage is
 * changed. A row shows only when it has something to say. The section is a
 * summary of the application, so the way to the application itself stands on
 * its heading line, outside the rows. An ended application says how and when
 * it ended, and nothing waits.
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
      <div className="jd-section-head">
        <div className="section-title">{applicationsPostingRow()}</div>
        <Link className="ui-btn ui-btn-link ui-btn-quiet" to={applicationPath(card.job_id)}>{applicationsPostingOpen()}</Link>
      </div>
      <dl className="kv jd-pipeline-facts">
        <dt>{applicationsPostingStage()}</dt>
        <dd>{stage}</dd>
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
            <dd>{interviewWhen(interview)}</dd>
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
            <dd className={dueState(due, now) === "overdue" ? "jd-pipeline-late" : undefined}>{dueDay(due, now)}</dd>
          </>
        )}
      </dl>
    </>
  );
}

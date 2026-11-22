import { useState, type ReactNode } from "react";
import { Link } from "react-router-dom";
import type { ApplicationCard } from "../../api";
import { daysAgo, time as formatTime } from "../../copy/format";
import type { StageSlug } from "../../copy/vocabulary";
import { companyName } from "../../format";
import { Badge, Button, CompanyIcon, Content, Icon, MenuItem, dragSurface } from "../../ui";
import {
  applicationsCardActions,
  applicationsCardApplied,
  applicationsCardAskOutcome,
  applicationsCardDayTime,
  applicationsCardGoneQuiet,
  applicationsCardPostingClosed,
  applicationsCardPriority,
  applicationsCardRoundPast,
  applicationsMenuLabel,
  applicationsMenuRemove,
} from "../../copy/gen/applications";
import { cardDay } from "./dayWords";
import { dueText } from "./DueBadge";
import { useRoleLink } from "./roleLink";
import {
  boardStage,
  daysInStage,
  dueState,
  isMoving,
  isStale,
  stepDue,
} from "./board";
import { PRIORITY_LABEL, priorityOf } from "./priority";
import { PriorityMark } from "./PriorityMark";
import { StageMenu } from "./StageMenu";
import { endingName } from "./StageLabel";
import type { CardDragHandlers } from "./useCardDrag";

/** The card's lead line: the one fact its column asks about. Applied says
 *  when, then a step that is late or close, or that the role has gone
 *  quiet; Interviewing names the round awaiting its outcome, else the next
 *  one; every other moving stage names the next step. Nothing set is
 *  nothing said. */
function leadOf(card: ApplicationCard, now: Date): ReactNode[] {
  const due = stepDue(card);
  const state = due && dueState(due, now);
  const late = due && state === "overdue"
    ? <span key="late" className="app-tile-late">{dueText(due, now)}</span>
    : null;
  const stage = boardStage(card.stage);
  if (stage === "applied") {
    const days = daysInStage(card, now);
    const after = late
      ?? (due && state === "soon"
        ? <span key="due">{dueText(due, now)}</span>
        : isStale(card, now) ? <span key="quiet">{applicationsCardGoneQuiet()}</span> : null);
    return [
      days != null && <span key="main" className="app-tile-lead-main">{applicationsCardApplied({ ago: daysAgo(days) })}</span>,
      after,
    ];
  }
  if (stage === "interviewing") {
    const past = card.awaiting_outcome;
    if (past) {
      return [
        <span key="main" className="app-tile-lead-main">
          {applicationsCardRoundPast({ label: past.label, day: cardDay(new Date(past.scheduled_at), now) })}
        </span>,
        <span key="ask" className="app-tile-ask">{applicationsCardAskOutcome()}</span>,
      ];
    }
    const next = card.next_interview;
    if (next) {
      const at = new Date(next.scheduled_at);
      const day = cardDay(at, now);
      return [
        <span key="main" className="app-tile-lead-main"><Content text={next.label} /></span>,
        <span key="when">{next.all_day ? day : applicationsCardDayTime({ day, time: formatTime(at) })}</span>,
      ];
    }
  }
  if (!card.next_action) return [];
  return [
    <span key="main" className="app-tile-lead-main"><Content text={card.next_action} /></span>,
    late ?? (due && <span key="when">{cardDay(due.on, now)}</span>),
  ];
}

export interface ApplicationTileProps {
  card: ApplicationCard;
  now: Date;
  onMove: (card: ApplicationCard, stage: StageSlug) => void;
  onRemove: (card: ApplicationCard) => void;
  /** The board's handlers that drag this card to another column. */
  drag?: CardDragHandlers;
  /** How far the card is drawn from its place while it is dragged. */
  dragged?: { dx: number; dy: number } | null;
  /** Whether the card matches the filters while the board highlights
   *  matches; unset when nothing highlights. */
  match?: boolean;
}

/** One application on the board. The title opens the application, and its
 *  link covers the card; the one button beside the company holds every move.
 *  The card itself drags to another column, the pointer's fast path for the
 *  same moves. */
export function ApplicationTile({ card, now, onMove, onRemove, drag, dragged, match }: ApplicationTileProps) {
  const [menuButton, setMenuButton] = useState<HTMLButtonElement | null>(null);
  const [menuOpen, setMenuOpen] = useState(false);
  const role = useRoleLink();
  const company = companyName(card.company);
  const ending = endingName(card);
  const closed = card.posting_status === "closed";
  const level = priorityOf(card);

  /* A drag surface (src/ui/dragSurface.ts): a drag that starts on the card
     moves it and selects nothing. The company and the title stay copyable
     by select-all, as content inside a control. */
  return (
    <>
    <div
      className="app-tile"
      data-job-id={card.job_id}
      data-posting-closed={closed || undefined}
      data-dragging={dragged ? "" : undefined}
      data-match={match == null ? undefined : String(match)}
      style={dragged ? { transform: `translate(${dragged.dx}px, ${dragged.dy}px)` } : undefined}
      {...dragSurface}
      {...drag}
    >
      <div className="app-tile-head">
        <CompanyIcon slug={card.company} display={company} size={16} />
        <span className="app-tile-company" data-selection="content">{company}</span>
        <Button
          ref={setMenuButton}
          variant="icon"
          size="sm"
          className="app-tile-menu"
          aria-label={applicationsCardActions({ title: card.title })}
          aria-haspopup="dialog"
          aria-expanded={menuOpen}
          onClick={() => setMenuOpen((open) => !open)}
        >
          <Icon name="more" size={16} />
        </Button>
      </div>
      <Link {...role(card)} className="app-tile-open" draggable={false}>
        <span className="app-tile-title" data-selection="content"><Content text={card.title} /></span>
      </Link>
      {ending && (
        <span className="app-tile-ended">
          {ending}
        </span>
      )}
      {isMoving(card) && (
        <div className="app-tile-lead">
          <span className="app-tile-facts">
            {leadOf(card, now)}
            {closed && <Badge tone="warning" variant="tint" size="sm">{applicationsCardPostingClosed()}</Badge>}
          </span>
          {level !== "none" && (
            <span className="app-tile-priority">
              <PriorityMark level={level} label={applicationsCardPriority({ level: PRIORITY_LABEL[level]() })} />
            </span>
          )}
        </div>
      )}
      {!isMoving(card) && closed && (
        <Badge tone="warning" variant="tint" size="sm">{applicationsCardPostingClosed()}</Badge>
      )}
    </div>
    {/* Beside the card, not in it: the menu is portalled, and React would
        bubble a press inside it to the card's drag handlers. */}
      <StageMenu
        current={card.stage}
        endedAt={card.ended_at_stage}
        label={applicationsMenuLabel({ title: card.title })}
        anchor={menuButton}
        isOpen={menuOpen}
        onClose={() => setMenuOpen(false)}
        onMove={(stage) => {
          setMenuOpen(false);
          onMove(card, stage);
        }}
      >
        {/* Leaving the pipeline is offered only in Considering: past it an
            application keeps its history, and Withdrawn is how it ends. */}
        {card.stage === "saved" && card.starred && (
          <MenuItem
            onSelect={() => {
              setMenuOpen(false);
              onRemove(card);
            }}
          >
            {applicationsMenuRemove()}
          </MenuItem>
        )}
      </StageMenu>
    </>
  );
}

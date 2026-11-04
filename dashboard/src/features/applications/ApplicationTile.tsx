import { useState } from "react";
import { Link } from "react-router-dom";
import type { ApplicationCard } from "../../api";
import { date as formatDate } from "../../copy/format";
import { STAGE_LABEL, type StageSlug } from "../../copy/vocabulary";
import { companyName } from "../../format";
import { Badge, Button, CompanyIcon, Content, Icon, dragSurface } from "../../ui";
import { Abbr } from "../../ui/Abbr";
import {
  applicationsCardActions,
  applicationsCardComments,
  applicationsCardDaysInStage,
  applicationsCardDaysShort,
  applicationsCardDueInterview,
  applicationsCardDueStep,
  applicationsCardEnded,
  applicationsCardOverdue,
  applicationsCardPostingClosed,
  applicationsCardPriority,
  applicationsCardQuiet,
  applicationsMenuLabel,
  applicationsMenuRemove,
} from "../../copy/gen/applications";
import { applicationPath, boardStage, dayOffset, daysInStage, daysOverdue, daysQuiet, dueOf, dueState, isStale } from "./board";
import { StageMenu } from "./StageMenu";
import type { CardDragHandlers } from "./useCardDrag";

const PRIORITY_STEPS = [1, 2, 3, 4, 5] as const;

/** The day a date falls on, as days from today and as a date: the message
 *  says today and tomorrow in words. */
function when(on: Date, now: Date): { offset: number; date: string } {
  return { offset: dayOffset(on, now), date: formatDate(on, "weekday") };
}

/** The card's one due field: the sooner of the next interview and the next
 *  step, in one of three states. */
function DueField({ card, now }: { card: ApplicationCard; now: Date }) {
  const due = dueOf(card);
  if (!due) return null;
  const state = dueState(due, now);
  const text = state === "overdue"
    ? applicationsCardOverdue({ days: daysOverdue(due, now) })
    : due.kind === "interview"
      ? applicationsCardDueInterview(when(due.on, now))
      : applicationsCardDueStep(when(due.on, now));
  return (
    <Badge
      className="app-tile-due"
      tone={state === "set" ? "neutral" : "danger"}
      variant={state === "overdue" ? "solid" : "tint"}
      size="sm"
    >
      {text}
    </Badge>
  );
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
  const company = companyName(card.company);
  const days = daysInStage(card, now);
  const stale = isStale(card, now);
  const ending = card.ended_at_stage;

  /* A drag surface (src/ui/dragSurface.ts): a drag that starts on the card
     moves it and selects nothing. The company and the title stay copyable
     by select-all, as content inside a control. */
  return (
    <>
    <div
      className="app-tile"
      data-job-id={card.job_id}
      data-posting-closed={card.posting_status === "closed" || undefined}
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
      <Link to={applicationPath(card.job_id)} className="app-tile-open" draggable={false}>
        <span className="app-tile-title" data-selection="content"><Content text={card.title} /></span>
      </Link>
      {ending && (
        <span className="app-tile-ended">
          {applicationsCardEnded({ ending: STAGE_LABEL[card.stage], stage: STAGE_LABEL[boardStage(ending)] })}
        </span>
      )}
      <div className="app-tile-foot">
        <DueField card={card} now={now} />
        {card.posting_status === "closed" && (
          <Badge tone="warning" variant="tint" size="sm">{applicationsCardPostingClosed()}</Badge>
        )}
        {card.comment_count > 0 && (
          <span className="app-tile-fact" role="img" aria-label={applicationsCardComments({ count: card.comment_count })}>
            <Icon name="message" size={12} />
            <span aria-hidden="true">{card.comment_count}</span>
          </span>
        )}
        <span className="app-tile-end">
        <span className="app-tile-priority" role="img" aria-label={applicationsCardPriority({ priority: card.priority })}>
          {PRIORITY_STEPS.map((step) => (
            <span key={step} className="app-tile-dot" data-filled={step <= card.priority || undefined} aria-hidden="true" />
          ))}
        </span>
        {days != null && (
          <span className="app-tile-fact app-tile-days" data-stale={stale || undefined}>
            {stale && <Icon name="clock" size={12} />}
            <Abbr
              short={applicationsCardDaysShort({ days })}
              full={stale ? applicationsCardQuiet({ days, quiet: daysQuiet(card, now) ?? days }) : applicationsCardDaysInStage({ days })}
            />
          </span>
        )}
        </span>
      </div>
    </div>
    {/* Beside the card, not in it: the menu is portalled, and React would
        bubble a press inside it to the card's drag handlers. */}
      <StageMenu
        current={card.stage}
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
          <Button
            variant="ghost"
            size="sm"
            className="app-menu-option"
            onClick={() => {
              setMenuOpen(false);
              onRemove(card);
            }}
          >
            {applicationsMenuRemove()}
          </Button>
        )}
      </StageMenu>
    </>
  );
}

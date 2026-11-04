/* The board's rules, apart from how it looks: which column a stage sits in,
 * how a column orders its cards, when a card is due, and when it has gone
 * quiet. Pure functions of the cards and a clock, so the tests hold the
 * rules without a screen. */

import type { ApplicationCard } from "../../api";
import type { StageSlug } from "../../copy/vocabulary";

export type ColumnId =
  | "saved" | "researching" | "applied" | "interviewing" | "offer" | "decided" | "closed";

/** A column and the stages it holds, in board order. A column of one stage
 *  is that stage; Decided and Closed are split into a section per ending. */
export interface ColumnDef {
  id: ColumnId;
  stages: readonly StageSlug[];
}

/** The five stages an application moves through, in order. */
export const MOVING_STAGES = ["saved", "researching", "applied", "interviewing", "offer"] as const;
/** The endings the person chose. */
export const DECIDED_STAGES = ["accepted", "declined", "withdrawn"] as const;
/** The endings the company or the world decided. */
export const CLOSED_STAGES = ["rejected", "role_closed"] as const;

export const COLUMNS: readonly ColumnDef[] = [
  ...MOVING_STAGES.map((stage) => ({ id: stage, stages: [stage] })),
  { id: "decided", stages: DECIDED_STAGES },
  { id: "closed", stages: CLOSED_STAGES },
];

/** The stage a card shows as. Networking is part of Researching: the
 *  vocabulary keeps it, so an application recorded there still reads, and
 *  the board never offers it. */
export function boardStage(stage: StageSlug): StageSlug {
  return stage === "networking" ? "researching" : stage;
}

const DAY = 86_400_000;
/** A due date this close reads as urgent. */
const SOON = 2 * DAY;

/** Days without movement after which a card in this stage has gone quiet.
 *  Considering and the endings never go quiet: nothing is expected of them. */
const STALE_AFTER_DAYS: Partial<Record<StageSlug, number>> = {
  researching: 21,
  networking: 21,
  applied: 14,
  interviewing: 7,
  offer: 3,
};

/** What a card is waiting on: the sooner of its next interview and its next
 *  step's due date. */
export interface Due {
  kind: "interview" | "step";
  /** The instant it falls due. An all-day interview falls due when its day ends. */
  at: Date;
  /** The instant the date names, for saying which day. */
  on: Date;
}

export type DueState = "set" | "soon" | "overdue";

export function dueOf(card: ApplicationCard): Due | null {
  const interview = card.next_interview;
  const options: Due[] = [];
  if (interview) {
    const on = new Date(interview.scheduled_at);
    const at = interview.all_day ? new Date(on.getTime() + DAY) : on;
    options.push({ kind: "interview", at, on });
  }
  if (card.next_action_due) {
    const on = new Date(card.next_action_due);
    options.push({ kind: "step", at: on, on });
  }
  return options.sort((a, b) => a.at.getTime() - b.at.getTime())[0] ?? null;
}

/** An interview is never overdue: once it has started it is today's, and its
 *  outcome is the person's to record. A step past its date is overdue. */
export function dueState(due: Due, now: Date): DueState {
  const left = due.at.getTime() - now.getTime();
  if (left < 0 && due.kind === "step") return "overdue";
  return left <= SOON ? "soon" : "set";
}

/** Whole days a step is past its date, at least one. */
export function daysOverdue(due: Due, now: Date): number {
  return Math.max(1, Math.floor((now.getTime() - due.at.getTime()) / DAY));
}

/** The reader's calendar day a date falls on, relative to today: 0 today,
 *  1 tomorrow, -1 yesterday. */
export function dayOffset(date: Date, now: Date): number {
  const start = (d: Date) => new Date(d.getFullYear(), d.getMonth(), d.getDate()).getTime();
  return Math.round((start(date) - start(now)) / DAY);
}

/** Whole days since the card reached its stage; null when no date says. */
export function daysInStage(card: ApplicationCard, now: Date): number | null {
  if (!card.stage_since) return null;
  return Math.max(0, Math.floor((now.getTime() - new Date(card.stage_since).getTime()) / DAY));
}

/** Days since anything happened to the card: a move, a comment, an interview
 *  or an edit. */
export function daysQuiet(card: ApplicationCard, now: Date): number | null {
  const last = card.last_activity_at ?? card.stage_since;
  if (!last) return null;
  return Math.floor((now.getTime() - new Date(last).getTime()) / DAY);
}

export function isStale(card: ApplicationCard, now: Date): boolean {
  const after = STALE_AFTER_DAYS[card.stage];
  const quiet = daysQuiet(card, now);
  return after != null && quiet != null && quiet >= after;
}

const time = (value: string | null): number => (value ? new Date(value).getTime() : -Infinity);

/** A column's order: what is overdue or due within two days first, soonest
 *  first; then everything else, the latest activity first. */
export function sortColumn(cards: readonly ApplicationCard[], now: Date): ApplicationCard[] {
  const urgent = (card: ApplicationCard): number | null => {
    const due = dueOf(card);
    return due && dueState(due, now) !== "set" ? due.at.getTime() : null;
  };
  return [...cards].sort((a, b) => {
    const ua = urgent(a);
    const ub = urgent(b);
    if (ua != null || ub != null) {
      if (ua == null) return 1;
      if (ub == null) return -1;
      if (ua !== ub) return ua - ub;
    }
    return time(b.last_activity_at) - time(a.last_activity_at) || a.job_id - b.job_id;
  });
}

/** Every stage's cards in column order. A stage with no cards is an empty list. */
export function byStage(cards: readonly ApplicationCard[], now: Date): Map<StageSlug, ApplicationCard[]> {
  const groups = new Map<StageSlug, ApplicationCard[]>(
    COLUMNS.flatMap((column) => column.stages.map((stage) => [stage, []] as [StageSlug, ApplicationCard[]])),
  );
  for (const card of cards) groups.get(boardStage(card.stage))?.push(card);
  for (const [stage, list] of groups) groups.set(stage, sortColumn(list, now));
  return groups;
}

export interface BoardCounts {
  /** In one of the six moving stages. */
  moving: number;
  decided: number;
  closed: number;
  /** Past Considering and still moving, with neither a next step nor an
   *  interview booked: the cards that need the person to say what comes next. */
  needNextStep: number;
}

/** Still moving: in one of the moving stages, not ended. */
export function isMoving(card: ApplicationCard): boolean {
  return (MOVING_STAGES as readonly StageSlug[]).includes(boardStage(card.stage));
}

/** Past Considering and still moving, with neither a next step nor an
 *  interview booked. */
export function needsNextStep(card: ApplicationCard): boolean {
  return isMoving(card) && card.stage !== "saved" && !card.next_action && !card.next_interview;
}

export function boardCounts(cards: readonly ApplicationCard[]): BoardCounts {
  const of = (stages: readonly string[]) => cards.filter((card) => stages.includes(card.stage));
  return {
    moving: cards.filter(isMoving).length,
    decided: of(DECIDED_STAGES).length,
    closed: of(CLOSED_STAGES).length,
    needNextStep: cards.filter(needsNextStep).length,
  };
}

/** The application's own page. */
export const applicationPath = (jobId: number): string => `/pipeline/${jobId}`;

export function columnOf(stage: StageSlug): ColumnDef {
  return COLUMNS.find((column) => column.stages.includes(stage)) ?? COLUMNS[0];
}

/** Where an application stands among the cards of its column, in the order
 *  the board shows them (section by section), with its neighbours. Null when
 *  the board does not hold it. */
export function placeInColumn(
  cards: readonly ApplicationCard[],
  jobId: number,
  now: Date,
): { index: number; total: number; previous: ApplicationCard | null; next: ApplicationCard | null } | null {
  const card = cards.find((other) => other.job_id === jobId);
  if (!card) return null;
  const groups = byStage(cards, now);
  const order = columnOf(boardStage(card.stage)).stages.flatMap((stage) => groups.get(stage) ?? []);
  const index = order.findIndex((other) => other.job_id === jobId);
  return {
    index,
    total: order.length,
    previous: order[index - 1] ?? null,
    next: order[index + 1] ?? null,
  };
}

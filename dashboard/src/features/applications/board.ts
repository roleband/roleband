/* The board's rules, apart from how it looks: which column a stage sits in,
 * how a column orders its cards, when a card is due, and when it has gone
 * quiet. Pure functions of the cards and a clock, so the tests hold the
 * rules without a screen. */

import type { ApplicationCard, ApplicationStep } from "../../api";
import type { StageSlug } from "../../copy/vocabulary";
import { interviewEnds } from "./interviewWords";

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

export const DAY = 86_400_000;
/** A due date this many calendar days away or fewer reads as urgent. */
const SOON_DAYS = 2;

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

/** A step's day as a due date; none for a step with no day. */
export function dueOfStep(step: Pick<ApplicationStep, "due">): Due | null {
  if (!step.due) return null;
  const on = new Date(step.due);
  return { kind: "step", at: on, on };
}

type StepFields = Pick<ApplicationCard, "steps" | "next_action" | "next_action_due">;

/** The server's order of open steps: due ascending, a step with no day last,
 *  then id. */
function byDueThenId(a: ApplicationStep, b: ApplicationStep): number {
  if (a.due && b.due) {
    const apart = new Date(a.due).getTime() - new Date(b.due).getTime();
    if (apart !== 0) return apart;
  } else if (a.due || b.due) {
    return a.due ? -1 : 1;
  }
  return a.id - b.id;
}

/** The steps in the server's order, with the card's next step (the soonest)
 *  derived from them. */
function settled(steps: readonly ApplicationStep[]): StepFields {
  const ordered = [...steps].sort(byDueThenId);
  return { steps: ordered, next_action: ordered[0]?.text ?? null, next_action_due: ordered[0]?.due ?? null };
}

/** The card once one step has left its open steps (ticked or removed): the
 *  soonest of the rest is its next step. */
export function withoutStep(card: ApplicationCard, stepId: number): StepFields {
  return settled(card.steps.filter((step) => step.id !== stepId));
}

/** The card once a step is changed or added: the step takes its place in the
 *  server's order and the next step follows from it. */
export function withStep(card: ApplicationCard, step: ApplicationStep): StepFields {
  return settled([...card.steps.filter((one) => one.id !== step.id), step]);
}

export function stepDue(card: ApplicationCard): Due | null {
  return dueOfStep({ due: card.next_action_due });
}

export function dueOf(card: ApplicationCard): Due | null {
  const interview = card.next_interview;
  const options: Due[] = [];
  if (interview) {
    const on = new Date(interview.scheduled_at);
    options.push({ kind: "interview", at: interviewEnds(interview), on });
  }
  const step = stepDue(card);
  if (step) options.push(step);
  return options.sort((a, b) => a.at.getTime() - b.at.getTime())[0] ?? null;
}

/** The reader's calendar day a date falls on, relative to today: 0 today,
 *  1 tomorrow, -1 yesterday. */
export function dayOffset(date: Date, now: Date): number {
  const start = (d: Date) => new Date(d.getFullYear(), d.getMonth(), d.getDate()).getTime();
  return Math.round((start(date) - start(now)) / DAY);
}

/** An interview is never overdue: once it has started it is today's, and its
 *  outcome is the person's to record. A step on a day before today is
 *  overdue. Both read the calendar day, as the day headings do. */
export function dueState(due: Due, now: Date): DueState {
  const offset = dayOffset(due.on, now);
  if (offset < 0 && due.kind === "step") return "overdue";
  return offset <= SOON_DAYS ? "soon" : "set";
}

/** Calendar days a step is past its day, at least one. */
export function daysOverdue(due: Due, now: Date): number {
  return Math.max(1, -dayOffset(due.on, now));
}

/** Whole days since the card reached its stage; null when no date says. */
export function daysInStage(card: ApplicationCard, now: Date): number | null {
  if (!card.stage_since) return null;
  return Math.max(0, Math.floor((now.getTime() - new Date(card.stage_since).getTime()) / DAY));
}

/** Days in stage worth saying: none on the day of the move, which the person
 *  has just made, so a count starts at 1. Ordering and staleness read
 *  `daysInStage`, which counts the day of the move as 0. */
export function daysToSay(card: ApplicationCard, now: Date): number | null {
  const days = daysInStage(card, now);
  return days != null && days >= 1 ? days : null;
}

/** Days since anything happened to the card: a move, a comment, an interview
 *  or an edit. */
function daysQuiet(card: ApplicationCard, now: Date): number | null {
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

const movingStage = (stage: StageSlug): boolean =>
  (MOVING_STAGES as readonly StageSlug[]).includes(boardStage(stage));

/** Still moving: in one of the moving stages, not ended. */
export function isMoving(card: ApplicationCard): boolean {
  return movingStage(card.stage);
}

/** The endings a role can reach from where it is. The company can close a
 *  role at any point; a rejection or a withdrawal needs an application; an
 *  offer is accepted or declined only once there is one. An ended role is
 *  judged by the stage it ended from, so a wrong ending can be corrected to
 *  another that was possible then. The ending a role is in is always listed. */
export function reachableEndings(current: StageSlug, endedAt: StageSlug | null): Set<StageSlug> {
  const from = boardStage(movingStage(current) ? current : endedAt ?? current);
  const step = (MOVING_STAGES as readonly StageSlug[]).indexOf(from);
  const reachable = new Set<StageSlug>(["role_closed", current]);
  if (step >= MOVING_STAGES.indexOf("applied")) reachable.add("rejected").add("withdrawn");
  if (from === "offer") reachable.add("accepted").add("declined");
  return reachable;
}

/** The card a stage move paints before the server answers, by the server's
 *  rule for the stage an ending was reached from: the stage the card was
 *  moving in, kept across a change from one ending to another, and none once
 *  the card moves again. */
export function movedCard(card: ApplicationCard, stage: StageSlug, at: string): ApplicationCard {
  const endedAt = movingStage(stage) ? null : isMoving(card) ? card.stage : card.ended_at_stage;
  return { ...card, stage, stage_since: at, last_activity_at: at, ended_at_stage: endedAt };
}

/** The endings that owe nothing, as the follow-up reminders hold them
 *  (`TERMINAL_STAGES` in `tracker/notifications/pursuit_due.py`). An accepted
 *  offer is not one: signing and a start date still carry dates. */
const OWES_NOTHING: ReadonlySet<StageSlug> = new Set(["declined", "withdrawn", "rejected", "role_closed"]);

/** The application has ended in a way that expects nothing more of the
 *  person: Up next lists none of its dates, and no quick filter matches it. */
export function owesNothing(card: Pick<ApplicationCard, "stage">): boolean {
  return OWES_NOTHING.has(card.stage);
}

/** Past Considering and not ended, with neither a next step nor an
 *  interview booked. */
export function needsNextStep(card: ApplicationCard): boolean {
  return isMoving(card) && card.stage !== "saved" && !card.next_action && !card.next_interview;
}

export function columnOf(stage: StageSlug): ColumnDef {
  return COLUMNS.find((column) => column.stages.includes(stage)) ?? COLUMNS[0];
}


import type { ApplicationCard } from "../../api";
import {
  applicationsPriorityHigh,
  applicationsPriorityLow,
  applicationsPriorityMedium,
  applicationsPriorityNone,
  applicationsPriorityUrgent,
} from "../../copy/gen/applications";

/* A role's priority, the way the person names it: No priority, then Urgent,
 * High, Medium and Low. The stored 1 to 5 maps one to one, the larger the more
 * pressing, as the five dots it replaces read it. A role reads as having none
 * until one is chosen for it (`priority_set`), whatever the stored number: a
 * new pursuit is written at the column's default. */

export type PriorityLevel = "none" | "urgent" | "high" | "medium" | "low";

/** The levels in the menu's order, which is also their keys, 0 to 4. */
export const PRIORITY_LEVELS: readonly PriorityLevel[] = ["none", "urgent", "high", "medium", "low"];

/** What each level is stored as. */
export const PRIORITY_STORED: Record<PriorityLevel, number> = { none: 1, urgent: 5, high: 4, medium: 3, low: 2 };

const BY_STORED: Record<number, PriorityLevel> = { 1: "none", 2: "low", 3: "medium", 4: "high", 5: "urgent" };

export const PRIORITY_LABEL: Record<PriorityLevel, () => string> = {
  none: applicationsPriorityNone,
  urgent: applicationsPriorityUrgent,
  high: applicationsPriorityHigh,
  medium: applicationsPriorityMedium,
  low: applicationsPriorityLow,
};

export function priorityOf(card: Pick<ApplicationCard, "priority" | "priority_set">): PriorityLevel {
  return card.priority_set ? BY_STORED[card.priority] ?? "none" : "none";
}

const RANK: Record<PriorityLevel, number> = { urgent: 4, high: 3, medium: 2, low: 1, none: 0 };

/** A level's place in a sort, the most pressing highest and no priority last. */
export const priorityRank = (level: PriorityLevel): number => RANK[level];

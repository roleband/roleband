import type { ReactNode } from "react";
import type { ActivityCategory, ActivityEntry } from "../../../api/agentActivity";
import { STAGE_LABEL } from "../../../copy/vocabulary";
import { Content } from "../../../ui/Content";
import { Msg } from "../../../ui/Msg";
import { companyName } from "../../../format";
import { timestamp } from "../../../copy/format";
import {
  activityAskedMarketStatistics,
  activityAskedOffer,
  activityAskedPostings,
  activityAskedProfile,
  activityAskedProgress,
  activityAskedWhileOff,
  activityCategoryMarketStatistics,
  activityCategoryOffer,
  activityCategoryPostings,
  activityCategoryProfile,
  activityCategoryProgressAndNotes,
  activityDraftedRecipe,
  activityFieldDraft,
  activityFieldNextAction,
  activityFieldNextActionDue,
  activityFieldNotes,
  activityFieldPriority,
  activityFieldStage,
  activityGroupControllingCollection,
  activityGroupKeepingFindings,
  activityGroupTrackingProgress,
  activityGroupTuningTheRadar,
  activityMadeChange,
  activityMovedRole,
  activityReadConnection,
  activityReadMarketStatistics,
  activityReadOffer,
  activityReadPostings,
  activityReadPostingsCount,
  activityReadProfile,
  activityReadProgress,
  activitySavedRole,
  activityTriedWhileChangesOff,
  activityUpdatedRole,
  activityValueDraft,
} from "../../../copy/gen/activity";

/* The words of an Activity entry, from the facts the engine recorded
   (`subject`): its topic picks the sentence, and a role's title and company,
   a count or a stage slug fill it. A topic this screen has no words for
   falls back to the English the engine stored with it. */

export const CATEGORIES: readonly ActivityCategory[] = [
  "public_posting", "market_statistic", "private_pursuit", "offer", "candidate",
];

const CATEGORY_NAME: Record<ActivityCategory, () => string> = {
  public_posting: activityCategoryPostings,
  market_statistic: activityCategoryMarketStatistics,
  private_pursuit: activityCategoryProgressAndNotes,
  offer: activityCategoryOffer,
  candidate: activityCategoryProfile,
};

const GROUP_NAME: Record<string, () => string> = {
  tracking_progress: activityGroupTrackingProgress,
  keeping_findings: activityGroupKeepingFindings,
  tuning_radar: activityGroupTuningTheRadar,
  controlling_collection: activityGroupControllingCollection,
};

const READ: Record<string, () => string> = {
  "read.market_statistic": activityReadMarketStatistics,
  "read.private_pursuit": activityReadProgress,
  "read.offer": activityReadOffer,
  "read.candidate": activityReadProfile,
  "read.engine": activityReadConnection,
};

const ASKED: Record<ActivityCategory, () => string> = {
  public_posting: activityAskedPostings,
  market_statistic: activityAskedMarketStatistics,
  private_pursuit: activityAskedProgress,
  offer: activityAskedOffer,
  candidate: activityAskedProfile,
};

const FIELD_NAME: Record<string, () => string> = {
  stage: activityFieldStage,
  priority: activityFieldPriority,
  notes: activityFieldNotes,
  next_action: activityFieldNextAction,
  next_action_due: activityFieldNextActionDue,
  draft: activityFieldDraft,
};

const own = <T,>(record: Record<string, T>, key: unknown): T | undefined =>
  typeof key === "string" && Object.prototype.hasOwnProperty.call(record, key) ? record[key] : undefined;

export const isCategory = (value: unknown): value is ActivityCategory =>
  own(CATEGORY_NAME, value) !== undefined;

export function categoryName(category: string): string {
  return own(CATEGORY_NAME, category)?.() ?? category;
}

export function groupName(group: string): string {
  return own(GROUP_NAME, group)?.() ?? group;
}

export function fieldName(field: string): string {
  return own(FIELD_NAME, field)?.() ?? field;
}

export function stageName(stage: unknown): string {
  return own(STAGE_LABEL as Record<string, string>, stage) ?? String(stage);
}

const text = (value: unknown): string | null => (typeof value === "string" && value !== "" ? value : null);

/** What a field's stored value reads as. A date-time is the reader's own day
 *  and time; a stage is its name; anything else is shown as written. */
export function fieldValue(field: string, value: unknown): ReactNode {
  if (field === "stage") return stageName(value);
  if (field === "next_action_due" && typeof value === "string") {
    return timestamp(value, { month: "short", day: "numeric", hour: "numeric", minute: "2-digit" });
  }
  if (field === "draft" && typeof value === "number") return activityValueDraft({ version: value });
  if (typeof value === "number") return String(value);
  if (typeof value === "string") return <Content text={value} />;
  return JSON.stringify(value);
}

/** The entry's sentence, with a role's title in bold. `plain` drops the bold
 *  (the inspector's heading is bold as a whole). */
export function entryText(entry: ActivityEntry, { plain = false }: { plain?: boolean } = {}): ReactNode {
  const subject = entry.subject as Record<string, unknown>;
  const topic = subject.topic;
  const title = text(subject.title);
  const company = text(subject.company);
  const role = title && company ? {
    title: plain ? <Content text={title} /> : <b><Content text={title} /></b>,
    company: <Content text={companyName(company)} />,
  } : null;

  if (topic === "read.public_posting") {
    return typeof subject.count === "number" ? activityReadPostingsCount({ count: subject.count }) : activityReadPostings();
  }
  const read = own(READ, topic);
  if (read) return read();
  if (topic === "refused.category" && isCategory(subject.category)) return ASKED[subject.category]();
  if (topic === "refused.access") return activityAskedWhileOff();
  if (topic === "refused.writes") return activityTriedWhileChangesOff();
  if (role && topic === "pursuit.saved") return <Msg of={activitySavedRole} elems={role} />;
  if (role && topic === "pursuit.changed") return <Msg of={activityUpdatedRole} elems={role} />;
  if (role && topic === "pursuit.moved") {
    return <Msg of={activityMovedRole} elems={role} args={{ stage: stageName(subject.stage) }} />;
  }
  const recipe = text(subject.recipe);
  if (recipe && topic === "recipe.drafted") {
    return <Msg of={activityDraftedRecipe} elems={{ recipe: <Content text={recipe} /> }} />;
  }
  if (topic === "change") return activityMadeChange();
  return <Content text={entry.summary} />;
}

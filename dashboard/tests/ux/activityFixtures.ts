/* The Activity screen's list, as `/api/agent-activity` answers it: a full
   first page over three days, led by a change, a refusal and a read, and the
   cursor of an older page. Times are relative to the run, so the first day
   is always today. */

import type { ActivityEntry, ActivityPage } from "../../src/api/agentActivity";

const MINUTE = 60_000;
const minutesAgo = (minutes: number, now: number) => new Date(now - minutes * MINUTE).toISOString();

export function activityPage(now = Date.now()): ActivityPage {
  const lead: ActivityEntry[] = [
    {
      id: 500, occurred_at: minutesAgo(1, now), operation: "pursuits.patch", kind: "change",
      categories: ["private_pursuit", "public_posting"], action_group: "tracking_progress", refusal: null,
      summary: "Moved Design Lead at contoso to interviewing",
      subject: { topic: "pursuit.moved", title: "Design Lead", company: "contoso", stage: "interviewing" },
      changes: [
        { field: "stage", before: "applied", after: "interviewing" },
        { field: "next_action", before: null, after: "Portfolio review" },
      ],
    },
    {
      id: 499, occurred_at: minutesAgo(2, now), operation: "offer.get", kind: "refused",
      categories: ["offer"], action_group: null, refusal: "category_disabled",
      summary: "Asked for your offer", subject: { topic: "refused.category", category: "offer" }, changes: [],
    },
  ];
  // Reads spread back over today, yesterday and the day before.
  const reads: ActivityEntry[] = Array.from({ length: 48 }, (_, n) => ({
    id: 498 - n, occurred_at: minutesAgo(3 + n * 60, now), operation: "opportunities.search", kind: "read",
    categories: ["public_posting", "market_statistic"], action_group: null, refusal: null,
    summary: `Read ${n + 1} postings`, subject: { topic: "read.public_posting", count: n + 1 }, changes: [],
  }));
  return { items: [...lead, ...reads], next_cursor: "older-page" };
}

export const olderActivityPage: ActivityPage = {
  items: [{
    id: 1, occurred_at: "2026-10-01T09:00:00Z", operation: "recipes.draft.save", kind: "change",
    categories: ["public_posting"], action_group: null, refusal: null,
    summary: "Drafted a recipe for careers-fabrikam",
    subject: { topic: "recipe.drafted", recipe: "careers-fabrikam" },
    changes: [{ field: "draft", before: null, after: 3 }],
  }],
  next_cursor: null,
};

import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { Job } from "../../api";
import { applicationCardFixture as card, jobFixture } from "../../test/fixtures";
import {
  placedBand,
  readListHidden,
  readSort,
  sortRows,
  writeListHidden,
  writeSort,
  yearlyBase,
  type ListRow,
} from "./listRows";

/* The List's rules: rows by stage read as the board reads down; any other
 * sort keeps rows that lack the fact at the end, whichever way it runs; the
 * sort lives in the address and the default writes nothing; a level the
 * posting does not state is never shown; the hidden columns are this
 * browser's, with a default set. */

const NOW = new Date("2026-11-04T12:00:00Z");
const days = (n: number) => new Date(NOW.getTime() + n * 86_400_000).toISOString();
const name = (slug: string) => ({ a: "Anthropic", n: "Notion", s: "Stripe" })[slug] ?? slug;
const job = (overrides: Partial<Job>): Job => ({ ...jobFixture, ...overrides });
const row = (overrides: Parameters<typeof card>[0], posting?: Partial<Job>): ListRow => {
  const c = card(overrides);
  return { card: c, job: posting ? job({ id: c.job_id, ...posting }) : undefined };
};
const order = (rows: ListRow[]) => rows.map((r) => r.card.job_id);

describe("sorting the List", () => {
  it("by stage, in the board's column order, and within a stage as the column orders its cards", () => {
    const rows = [
      row({ job_id: 1, stage: "applied", last_activity_at: days(-1) }),
      row({ job_id: 2, stage: "saved", last_activity_at: days(-5) }),
      row({ job_id: 3, stage: "applied", last_activity_at: days(-9), next_action: "Call", next_action_due: days(-1) }),
      row({ job_id: 4, stage: "rejected" }),
      row({ job_id: 5, stage: "networking", last_activity_at: days(-2) }),
    ];
    // Overdue first in a column, then the latest activity; Networking is Researching.
    expect(order(sortRows(rows, "stage", "asc", NOW, name))).toEqual([2, 5, 3, 1, 4]);
    expect(order(sortRows(rows, "stage", "desc", NOW, name))).toEqual([4, 1, 3, 5, 2]);
  });

  it("keeps a row without the fact at the end, ascending and descending", () => {
    const rows = [
      row({ job_id: 1 }, { posted_base: { min: 200_000, max: 250_000, period: "year", currency: "USD" } }),
      row({ job_id: 2 }),
      row({ job_id: 3 }, { posted_base: null, comp_base_median: 300_000 }),
    ];
    expect(order(sortRows(rows, "pay", "desc", NOW, name))).toEqual([3, 1, 2]);
    expect(order(sortRows(rows, "pay", "asc", NOW, name))).toEqual([1, 3, 2]);
  });

  it("by role, by the company's name and then the title, not by the slug", () => {
    const rows = [
      row({ job_id: 1, company: "s", title: "B" }),
      row({ job_id: 2, company: "a", title: "Z" }),
      row({ job_id: 3, company: "s", title: "A" }),
      row({ job_id: 4, company: "n", title: "A" }),
    ];
    expect(order(sortRows(rows, "role", "asc", NOW, name))).toEqual([2, 4, 3, 1]);
  });

  it("by next step, the soonest due first, a row with nothing due last", () => {
    const rows = [
      row({ job_id: 1, next_action: "Later", next_action_due: days(5) }),
      row({ job_id: 2 }),
      row({ job_id: 3, next_action: "Overdue", next_action_due: days(-2) }),
    ];
    expect(order(sortRows(rows, "next", "asc", NOW, name))).toEqual([3, 1, 2]);
  });
});

describe("the sort in the address", () => {
  it("reads the default when the address names none, or names one it does not know", () => {
    expect(readSort(new URLSearchParams())).toEqual({ sort: "stage", order: "asc" });
    expect(readSort(new URLSearchParams("sort=salary&order=up"))).toEqual({ sort: "stage", order: "asc" });
    expect(readSort(new URLSearchParams("sort=pay"))).toEqual({ sort: "pay", order: "desc" });
  });

  it("writes nothing for the default, and keeps the filter beside it", () => {
    const filtered = new URLSearchParams("q=stripe");
    expect(writeSort(filtered, "pay", "asc").toString()).toBe("q=stripe&sort=pay&order=asc");
    expect(writeSort(new URLSearchParams("q=stripe&sort=pay&order=asc"), "stage", "asc").toString()).toBe("q=stripe");
  });
});

describe("a posting's facts", () => {
  it("shows no level for a posting that states none, or one no band maps", () => {
    expect(placedBand(job({ level_band: "senior", level_basis: "title" }))).toBe("senior");
    expect(placedBand(job({ level_band: "mid", level_basis: "none" }))).toBeNull();
    expect(placedBand(job({ level_band: "mid", level_basis: "unmapped" }))).toBeNull();
    expect(placedBand(undefined)).toBeNull();
  });

  it("orders pay by a yearly figure, never an hourly one taken as a salary", () => {
    expect(yearlyBase(job({ posted_base: { min: 90, max: 120, period: "hour", currency: "USD" }, comp_base_median: null }))).toBeNull();
    expect(yearlyBase(job({ posted_base: { min: 90, max: 120, period: "hour", currency: "USD" }, comp_base_median: 180_000 }))).toBe(180_000);
  });
});

describe("the columns a browser hides", () => {
  beforeEach(() => localStorage.clear());
  afterEach(() => vi.restoreAllMocks());

  it("hides priority, days in stage and last activity on a first visit, and remembers a choice", () => {
    expect(readListHidden()).toEqual(["priority", "in_stage", "activity"]);
    writeListHidden(["pay", "activity"]);
    expect(readListHidden()).toEqual(["pay", "activity"]);
    writeListHidden([]);
    expect(readListHidden()).toEqual([]);
  });

  it("falls back to the default set when storage throws or holds something else", () => {
    localStorage.setItem("roleband.pipeline-list-hidden-columns", "{}");
    expect(readListHidden()).toEqual(["priority", "in_stage", "activity"]);
    vi.spyOn(Storage.prototype, "getItem").mockImplementation(() => {
      throw new Error("blocked");
    });
    expect(readListHidden()).toEqual(["priority", "in_stage", "activity"]);
  });
});

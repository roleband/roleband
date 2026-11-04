import { describe, expect, it } from "vitest";
import { applicationCardFixture } from "../../test/fixtures";
import { matches, matchesQuick, matchesSearch, readFilter, writeFilter, type BoardFilter } from "./filters";

/* The quick filters are about work in motion; the search reads the company
 * and the title; the address holds the whole choice and nothing else. */

const NOW = new Date("2026-11-04T12:00:00Z");
const day = (offset: number) => new Date(NOW.getTime() + offset * 86_400_000).toISOString();

describe("a quick filter", () => {
  it("finds an overdue next step, and leaves one due today out", () => {
    expect(matchesQuick(applicationCardFixture({ stage: "applied", next_action: "Chase", next_action_due: day(-2) }), "overdue", NOW)).toBe(true);
    expect(matchesQuick(applicationCardFixture({ stage: "applied", next_action: "Chase", next_action_due: day(0) }), "overdue", NOW)).toBe(false);
  });

  it("counts what falls due within seven days, not what is already overdue or further out", () => {
    const due = (at: string) => applicationCardFixture({ stage: "applied", next_action: "Chase", next_action_due: at });
    expect(matchesQuick(due(day(3)), "due_week", NOW)).toBe(true);
    expect(matchesQuick(due(day(-2)), "due_week", NOW)).toBe(false);
    expect(matchesQuick(due(day(12)), "due_week", NOW)).toBe(false);
  });

  it("finds a card past Considering with nothing next, but not one in Considering", () => {
    expect(matchesQuick(applicationCardFixture({ stage: "applied" }), "needs_next", NOW)).toBe(true);
    expect(matchesQuick(applicationCardFixture({ stage: "saved" }), "needs_next", NOW)).toBe(false);
    expect(matchesQuick(applicationCardFixture({ stage: "applied", next_action: "Chase" }), "needs_next", NOW)).toBe(false);
  });

  it("finds a card quiet past its stage's patience", () => {
    expect(matchesQuick(applicationCardFixture({ stage: "applied", last_activity_at: day(-20) }), "quiet", NOW)).toBe(true);
    expect(matchesQuick(applicationCardFixture({ stage: "applied", last_activity_at: day(-2) }), "quiet", NOW)).toBe(false);
  });

  it("finds priority 4 and 5, and a closed posting", () => {
    expect(matchesQuick(applicationCardFixture({ priority: 4 }), "high_priority", NOW)).toBe(true);
    expect(matchesQuick(applicationCardFixture({ priority: 3 }), "high_priority", NOW)).toBe(false);
    expect(matchesQuick(applicationCardFixture({ posting_status: "closed" }), "posting_closed", NOW)).toBe(true);
    expect(matchesQuick(applicationCardFixture({ posting_status: "open" }), "posting_closed", NOW)).toBe(false);
  });

  it("never matches an application that has ended", () => {
    const ended = applicationCardFixture({ stage: "rejected", priority: 5, posting_status: "closed", last_activity_at: day(-90) });
    for (const quick of ["high_priority", "posting_closed", "quiet", "needs_next"] as const) {
      expect(matchesQuick(ended, quick, NOW)).toBe(false);
    }
  });

  it("treats a Networking card as Researching", () => {
    expect(matchesQuick(applicationCardFixture({ stage: "networking" }), "needs_next", NOW)).toBe(true);
  });
});

describe("the search", () => {
  it("reads the company's name and the title, whatever the case or accents", () => {
    const card = applicationCardFixture({ company: "stripe", title: "Café Platform Lead" });
    expect(matchesSearch(card, "STRIPE")).toBe(true);
    expect(matchesSearch(card, "cafe plat")).toBe(true);
    expect(matchesSearch(card, "openai")).toBe(false);
    expect(matchesSearch(card, "   ")).toBe(true);
  });

  it("must pass with every quick filter that is on", () => {
    const card = applicationCardFixture({ stage: "applied", priority: 5, company: "stripe" });
    const filter = (over: Partial<BoardFilter>): BoardFilter => ({ quick: [], query: "", mode: "only", ...over });
    expect(matches(card, filter({ quick: ["high_priority", "needs_next"], query: "stripe" }), NOW)).toBe(true);
    expect(matches(card, filter({ quick: ["high_priority", "posting_closed"] }), NOW)).toBe(false);
    expect(matches(card, filter({ quick: ["high_priority"], query: "openai" }), NOW)).toBe(false);
  });
});

describe("the address", () => {
  it("round-trips a filter and keeps every other parameter", () => {
    const filter: BoardFilter = { quick: ["quiet", "overdue"], query: "stripe", mode: "highlight" };
    const params = writeFilter(new URLSearchParams("tab=x"), filter);
    expect(params.get("tab")).toBe("x");
    expect(params.get("only")).toBe("overdue,quiet");
    expect(readFilter(params)).toEqual({ quick: ["overdue", "quiet"], query: "stripe", mode: "highlight" });
  });

  it("drops what it does not know, and an empty filter leaves no trace", () => {
    expect(readFilter(new URLSearchParams("only=overdue,bogus&show=sideways"))).toEqual({ quick: ["overdue"], query: "", mode: "only" });
    expect(writeFilter(new URLSearchParams("only=overdue&q=x&show=highlight"), { quick: [], query: "", mode: "only" }).toString()).toBe("");
  });
});

// What the Statistics screens name from slugs: an age band by its lower
// bound, and the Overview's one-line brief.
import { date } from "../../copy/format";
import { afterEach, describe, expect, it } from "vitest";
import { activate } from "../../copy/activate";
import { msg } from "../../test/msg";
import { agingBandName, overviewBrief } from "./names";

afterEach(() => activate("en"));

describe("agingBandName", () => {
  it("names each fixed band by its lower bound", () => {
    expect([0, 7, 14, 30, 60, 90].map(agingBandName)).toEqual([
      "< 1 week", "1–2 weeks", "2–4 weeks", "1–2 months", "2–3 months", "3 months+",
    ]);
  });
});

describe("overviewBrief", () => {
  const kpis = { open_total: 3192, companies: 41, new_count: 120, closed_count: 30, first_scan_count: 0, saved_total: 0 };

  it("says the facts the server's brief said, with the region's digits", async () => {
    await activate("en", { region: "en-US" });
    const data = {
      days: 30, since: "2026-10-12T06:00:00Z", kpis: { ...kpis, first_scan_count: 12 },
      top_skills: [{ term: "python", category: "language", job_count: 1435 }],
    };
    // The roles already listed at a company's first scan are when the
    // radar first looked, not the market: neither view says them.
    expect(overviewBrief(data)).toBe(
      "3,192 open roles across 41 companies. 120 opened in 30d, 30 closed. "
      + "Top skill: Python (1,435 roles).",
    );
  });

  it("leaves out a fact that is not there, and names where all the history starts", () => {
    expect(overviewBrief({ days: 0, since: "2026-11-03T06:02:00Z", kpis, top_skills: [] })).toBe(
      `${msg("insights-brief-open", { open: "3,192", companies: "41" })} `
      + msg("insights-brief-opened", { period: "since", opened: "120", closed: "30", days: 0, date: date("2026-11-03T06:02:00Z", "day") }),
    );
    expect(overviewBrief({ days: 0, since: "2026-11-03T06:02:00Z", kpis, top_skills: [] })).not.toMatch(/all time/);
    // Before any whole read there is no start to name.
    expect(overviewBrief({ days: 0, since: null, kpis, top_skills: [] })).toMatch(/closed, all time\.$/);
  });
});

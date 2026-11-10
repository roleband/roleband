// What the Statistics screens name from slugs: an age band by its lower
// bound, and the Overview's one-line brief.
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
      days: 30, kpis: { ...kpis, first_scan_count: 12 },
      top_skills: [{ term: "python", category: "language", job_count: 1435 }],
    };
    // The roles already listed at a company's first scan are when the
    // radar first looked, not the market: neither view says them.
    expect(overviewBrief(data)).toBe(
      "3,192 open roles across 41 companies. 120 opened in 30d, 30 closed. "
      + "Top skill: Python (1,435 roles).",
    );
  });

  it("leaves out a fact that is not there, and says all time for no window", () => {
    expect(overviewBrief({ days: 0, kpis, top_skills: [] })).toBe(
      `${msg("insights-brief-open", { open: "3,192", companies: "41" })} `
      + msg("insights-brief-opened", { allTime: "yes", opened: "120", closed: "30", days: 0 }),
    );
  });
});

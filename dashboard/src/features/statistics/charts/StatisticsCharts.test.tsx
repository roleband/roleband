import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import {
  HiringCompaniesChart,
  OverviewSignalChart,
  SkillsConstellationChart,
  TrajectoryShockChart,
} from "./StatisticsCharts";
import { msg } from "../../../test/msg";

describe("StatisticsCharts", () => {
  it("exposes a named visualization and exact text summary for every statistics tab", () => {
    render(
      <>
        <OverviewSignalChart skills={[{ term: "python", category: "language", job_count: 12 }]} />
        <HiringCompaniesChart bars={[
          { company: "google", label: "Google", open: 20, fresh: 3, closed: 2 },
          { company: "stripe", label: "Stripe", open: 12, fresh: 1, closed: 0 },
        ]} />
        <TrajectoryShockChart companies={[{
          company: "google", ticker: "GOOGL", equity_vehicle: "rsu", count: 8, median_tc: 620_000,
          base: 230_000, bonus: 40_000, equity: 350_000, equity_pct: 0.56,
          sources: { base: "posted" as const, bonus: "company_rule" as const, equity: "estimated" as const },
          vesting: "25/25/25/25",
        }]} priceChange={0.25} />
        <SkillsConstellationChart skills={[{
          term: "python", category: "language", job_count: 12,
          share: 0.4, market_share: 0.1, lift: 4, distinctiveness: 5.2,
        }]} />
      </>,
    );

    const names = [
      msg("insights-statistics-charts-market-demand-field"),
      "Open roles by company",
      msg("insights-statistics-charts-equity-shockwave-by-company"),
      "What sets these roles apart",
    ];
    for (const name of names) {
      expect(screen.getByRole("img", { name })).toBeInTheDocument();
    }

    expect(screen.getAllByText(/Python: 12/).length).toBeGreaterThan(0);
    expect(screen.getByText(/Python: 40% of these roles, ×4 the market/)).toBeInTheDocument();
    // The company chart draws the rows it is given, leaders first.
    expect(screen.getByText(/Google: 20 open, 3 new, 2 closed; Stripe: 12 open/)).toBeInTheDocument();
  });
});

import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import type { DisclosureRates } from "../../api";
import { msg } from "../../test/msg";
import { DisclosureRatePanel } from "./DisclosurePanel";

// The chart itself is an echarts canvas; these specs assert the copy and the
// wiring around it. The option builders are unit-tested in charts/disclosure.test.ts.
vi.mock("./charts/EChart", () => ({
  EChart: ({ ariaLabel, summary }: { ariaLabel: string; summary: string }) => (
    <figure>
      <div role="img" aria-label={ariaLabel} />
      <figcaption>{summary}</figcaption>
    </figure>
  ),
}));

const rates = (over: Partial<DisclosureRates> = {}): DisclosureRates => ({
  overall: { open: 732, checked: 600, disclosed: 150, rate: 0.25 },
  by_level: [
    { level_band: "senior", open: 406, checked: 400, disclosed: 100, rate: 0.25 },
    { level_band: "staff", open: 265, checked: 200, disclosed: 50, rate: 0.25 },
  ],
  ...over,
});

describe("DisclosureRatePanel", () => {
  it("headlines the rate against the checked roles, not every open role", async () => {
    render(<DisclosureRatePanel rates={rates()} />);

    expect(screen.getByText("25% of 600 checked roles post a range")).toBeInTheDocument();
  });

  it("names the roles not yet checked and leaves them out of the rate, never counting them as employer silence", async () => {
    // 732 open, 600 checked. Reporting 150/732 = 20% would blame employers for our
    // own extraction queue, so the panel must name the gap explicitly.
    render(<DisclosureRatePanel rates={rates()} />);

    expect(
      screen.getByText(msg("insights-disclosure-panel-of-open-roles-have-not", { pending: "132", open: "732" })),
    ).toBeInTheDocument();
    // The unchecked roles stay out of the rate: it is over the 600 checked, not the 732 open.
    expect(screen.getByText("25% of 600 checked roles post a range")).toBeInTheDocument();
  });

  it("omits the backlog note when every open role has been checked", () => {
    render(
      <DisclosureRatePanel
        rates={rates({ overall: { open: 600, checked: 600, disclosed: 150, rate: 0.25 } })}
      />,
    );
    expect(
      screen.queryByText(msg("insights-disclosure-panel-of-open-roles-have-not", { pending: "0", open: "600" })),
    ).not.toBeInTheDocument();
  });

  it("draws the rate by level, the grouping each company's own row cannot show", async () => {
    render(<DisclosureRatePanel rates={rates()} />);

    expect(screen.getByRole("img", { name: /post a range, by level/i })).toBeInTheDocument();
    expect(screen.getByText(/Senior: 25%, 100 of 400 roles/)).toBeInTheDocument();
    // No company grouping here: a company's share at one level is its table row.
    expect(screen.queryByRole("button", { name: "By company" })).not.toBeInTheDocument();
  });

  it("shows an empty state instead of a chart when nothing has been checked", () => {
    render(
      <DisclosureRatePanel
        rates={{
          overall: { open: 40, checked: 0, disclosed: 0, rate: null },
          by_level: [{ level_band: "senior", open: 40, checked: 0, disclosed: 0, rate: null }],
        }}
      />,
    );

    expect(screen.getByText(/no open roles have been checked/i)).toBeInTheDocument();
    expect(screen.queryByRole("img")).not.toBeInTheDocument();
  });
});

import { render, screen, within, fireEvent } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { CompPackage, CompTrajectory } from "../../api";
import { api } from "../../api";
import { msg } from "../../test/msg";
import { StockTrajectoryPanel } from "./StockTrajectoryPanel";

vi.mock("../../api", () => ({
  api: { compTrajectory: vi.fn() },
}));

const mock = (data: CompTrajectory) => vi.mocked(api.compTrajectory).mockResolvedValue(data);

type Sources = CompPackage["sources"];
const ESTIMATED: Sources = { base: "estimated", bonus: "estimated", equity: "estimated" };

// A package whose components sum to median_tc, as the backend guarantees.
const pkg = (median_tc: number, equity: number, bonus: number, sources: Sources = ESTIMATED) => ({
  count: 10,
  median_tc,
  equity,
  bonus,
  base: median_tc - equity - bonus,
  equity_pct: equity / median_tc,
  sources,
});

const base = (over: Partial<CompTrajectory> = {}): CompTrajectory => ({
  currency: "USD",
  overall: pkg(1_000_000, 450_000, 120_000), // base 430k
  public: [
    { company: "google", ticker: "GOOGL", equity_vehicle: "rsu", vesting: "38/32/20/10", ...pkg(1_000_000, 500_000, 120_000) },
    { company: "microsoft", ticker: "MSFT", equity_vehicle: "rsu", vesting: null, ...pkg(700_000, 140_000, 84_000) },
  ],
  private: [{ company: "openai", equity_vehicle: null, vesting: null, ...pkg(1_100_000, 550_000, 0) }],
  choice: [],
  set_apart: [],
  ...over,
});

const setSlider = (value: number) =>
  fireEvent.change(screen.getByLabelText("Stock price change percent"), {
    target: { value: String(value) },
  });

// KPI labels ("Today"/"Projected"/"Change") also appear as table column headers,
// so scope the lookup to the KPI label element.
const kpi = (label: string) =>
  screen.getByText(label, { selector: ".kpi-l" }).closest(".kpi")! as HTMLElement;

describe("StockTrajectoryPanel", () => {
  beforeEach(() => vi.clearAllMocks());

  it("leads with the equity share at today's price, and the projection once the price moves", async () => {
    mock(base());
    render(<StockTrajectoryPanel />);

    // At 0% the projection is today's median again: the figure would say
    // nothing a tile does not, so it says what a move acts on.
    const hero = await screen.findByRole("heading", { level: 2 });
    expect(hero).toHaveTextContent("45% of total compensation is equity");
    expect(hero).not.toHaveTextContent(/projected/);
    expect(within(kpi("Today")).getByText("$1M")).toBeInTheDocument();
    expect(within(kpi("Change")).getByText("$0")).toBeInTheDocument();

    setSlider(-20);
    expect(await screen.findByRole("heading", { level: 2, name: /\$910K projected/ })).toBeInTheDocument();
    setSlider(0);
    expect(await screen.findByRole("heading", { level: 2, name: "45% of total compensation is equity" })).toBeInTheDocument();
  });

  it("keeps TC short on the figure and tiles and spells it out on hover", async () => {
    mock(base());
    render(<StockTrajectoryPanel />);
    await screen.findByRole("heading", { level: 2 });
    setSlider(100);
    const hero = await screen.findByRole("heading", { level: 2, name: /projected/ });
    expect(hero.querySelector("abbr")).toHaveAttribute("title", "$1.45M projected total compensation");
    expect(within(kpi("Today")).getByText("median TC").closest("abbr"))
      .toHaveAttribute("title", "median total compensation");
    expect(within(kpi("Equity share")).getByText("of TC (at risk)").closest("abbr"))
      .toHaveAttribute("title", "of total compensation (at risk)");
  });

  it("charts what a 10% move is worth at today's price, never a chart of zeros", async () => {
    mock(base());
    render(<StockTrajectoryPanel />);
    await screen.findByRole("heading", { level: 2 });

    // 10% of Microsoft's $140K equity and of Google's $500K.
    expect(screen.getByText(/Microsoft: \+\$14K, Google: \+\$50K/)).toBeInTheDocument();
    expect(screen.getByText("Per 10% stock move · adjust above for a scenario")).toBeInTheDocument();
    // A scenario replaces the sensitivity view with itself.
    setSlider(-50);
    // A fall reads as one, never as "$-250000".
    expect(await screen.findByText(/Google: −\$250K/)).toBeInTheDocument();
    expect(screen.queryByText(/Google: \+\$50K/)).not.toBeInTheDocument();
  });

  it("re-prices only the equity slice when the stock moves up", async () => {
    mock(base());
    render(<StockTrajectoryPanel />);
    await screen.findByRole("heading", { level: 2 });

    setSlider(100); // stock doubles

    // overall: base 430k + bonus 120k + equity 450k*(1+1.0)=900k => 1.45M
    expect(within(kpi("Projected")).getByText("$1.45M")).toBeInTheDocument();
    // Change = equity * d = 450k * 1.0 = +450k
    expect(within(kpi("Change")).getByText("+$450K")).toBeInTheDocument();
  });

  it("drops total comp when the stock falls", async () => {
    mock(base());
    render(<StockTrajectoryPanel />);
    await screen.findByRole("heading", { level: 2 });

    setSlider(-50);
    // overall change = 450k * -0.5 = -225k (rendered with a U+2212 minus)
    const change = within(kpi("Change")).getByText(/225K/);
    expect(change).toHaveTextContent(/^−\$225K$/);
    expect(change).toHaveClass("bad");
  });

  it("projects each public company independently by its own equity slice", async () => {
    mock(base());
    render(<StockTrajectoryPanel />);
    await screen.findByRole("heading", { level: 2 });

    setSlider(50); // +50%

    // Google row: equity 500k * 0.5 = +250k; projected 1.25M.
    const goog = (await screen.findByText("Google")).closest("tr")!;
    expect(within(goog).getByText("GOOGL")).toBeInTheDocument();
    expect(within(goog).getByText("$1.25M")).toBeInTheDocument();
    expect(within(goog).getByText("+$250K")).toBeInTheDocument();

    // Microsoft has a thinner equity slice, so the same move adds less: 140k*0.5=+70k.
    const msft = screen.getByRole("row", { name: /Microsoft/ });
    expect(within(msft).getByText("+$70K")).toBeInTheDocument();
  });

  it("lists private companies as illiquid and does not move them with the slider", async () => {
    mock(base());
    render(<StockTrajectoryPanel />);
    await screen.findByRole("heading", { level: 2 });
    setSlider(200);

    const openai = (await screen.findByText("OpenAI")).closest("tr")!;
    // Median TC is shown, unchanged by the scenario (no projected column here).
    expect(within(openai).getByText("$1.10M")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Why private companies do not move" }))
      .toHaveAccessibleDescription(msg("insights-stock-trajectory-panel-pre-ipo-equity-is-illiquid"));
  });

  it("shows an empty state when no public roles have a comp estimate", async () => {
    mock(base({ overall: null, public: [], private: [] }));
    render(<StockTrajectoryPanel />);
    expect(
      await screen.findByText(/No open roles at public companies/i),
    ).toBeInTheDocument();
  });

  const SOURCES = ["posted", "company_rule", "measured", "estimated", "mixed"] as const;

  it.each(SOURCES)("labels a %s part with its source, explained once in the table's key", async (source) => {
    const sources: Sources = { base: source, bonus: source, equity: source };
    mock(base({
      public: [{ company: "google", ticker: "GOOGL", equity_vehicle: "rsu", vesting: null, ...pkg(1_000_000, 500_000, 120_000, sources) }],
      private: [],
    }));
    render(<StockTrajectoryPanel />);
    const goog = (await screen.findByText("Google")).closest("tr")!;
    const word = msg("insights-stock-trajectory-panel-part-source", { source });
    // Base, bonus and equity share each say where they come from.
    expect(within(goog).getAllByText(word)).toHaveLength(3);
    expect(within(goog).getAllByText(word)[0]).not.toHaveAttribute("title");
    const key = screen.getByRole("button", { name: msg("insights-stock-trajectory-panel-about-the-source-labels") });
    expect(key.closest("th")).toHaveTextContent(msg("insights-common-company"));
    expect(key).toHaveAccessibleDescription(
      new RegExp(msg("insights-stock-trajectory-panel-part-source-explained", { source }).replace(/[.*+?^${}()|[\]\\/]/g, "\\$&")),
    );
    for (const other of SOURCES.filter((s) => s !== source)) {
      expect(within(goog).queryByText(msg("insights-stock-trajectory-panel-part-source", { source: other }))).not.toBeInTheDocument();
    }
  });

  it.each(["measured", "mixed", "estimated"] as const)("says in the hero whether equity is %s", async (equity) => {
    mock(base({ overall: pkg(1_000_000, 450_000, 120_000, { ...ESTIMATED, equity }) }));
    render(<StockTrajectoryPanel />);
    await screen.findByRole("heading", { level: 2 });
    expect(document.body).toHaveTextContent(msg("insights-stock-trajectory-panel-typical-package", { equity }));
    for (const other of (["measured", "mixed", "estimated"] as const).filter((e) => e !== equity)) {
      expect(document.body).not.toHaveTextContent(msg("insights-stock-trajectory-panel-typical-package", { equity: other }));
    }
    expect(screen.getByRole("button", { name: "How stock trajectory is projected" }))
      .toHaveAccessibleDescription(msg("insights-stock-trajectory-panel-stock-moves-re-price-equity"));
  });

  it("says a company's own no-bonus rule as a fact, and an unknown zero as a figure", async () => {
    mock(base({
      public: [],
      private: [
        { company: "openai", equity_vehicle: null, vesting: "25/25/25/25",
          ...pkg(1_100_000, 550_000, 0, { base: "estimated", bonus: "company_rule", equity: "estimated" }) },
        { company: "stripe", equity_vehicle: "options", vesting: null,
          ...pkg(600_000, 200_000, 0, { base: "estimated", bonus: "measured", equity: "estimated" }) },
      ],
    }));
    render(<StockTrajectoryPanel />);
    const openai = (await screen.findByText("OpenAI")).closest("tr")!;
    expect(within(openai).getByText(msg("insights-stock-trajectory-panel-no-bonus"))).toBeInTheDocument();
    expect(within(openai).getByText(msg("insights-stock-trajectory-panel-vests", { schedule: "25/25/25/25" }))).toBeInTheDocument();
    const stripe = screen.getByRole("row", { name: /stripe/i });
    expect(within(stripe).queryByText(msg("insights-stock-trajectory-panel-no-bonus"))).not.toBeInTheDocument();
    expect(within(stripe).getByText("$0")).toBeInTheDocument();
  });

  it("shows a cash-or-equity company apart, with a total that no price move changes", async () => {
    mock(base({
      choice: [{ company: "netflix", ticker: "NFLX", count: 4, median_tc: 756_250, total_source: "posted" }],
    }));
    render(<StockTrajectoryPanel />);
    const choice = await screen.findByTestId("traj-choice");
    expect(within(choice).getByRole("heading", { name: msg("insights-stock-trajectory-panel-choice-companies") })).toBeInTheDocument();
    const nflx = within(choice).getByRole("row", { name: /Netflix/ });
    expect(within(nflx).getByText("NFLX")).toBeInTheDocument();
    expect(within(nflx).getByText("4")).toBeInTheDocument();
    expect(within(nflx).getByText(msg("insights-stock-trajectory-panel-part-source", { source: "posted" }))).toBeInTheDocument();
    // The label is explained in this table too, not only in the listed ones.
    const key = within(choice).getByRole("button", { name: msg("insights-stock-trajectory-panel-about-the-source-labels") });
    expect(key.closest("th")).toHaveTextContent(msg("insights-common-company"));
    expect(key).toHaveAccessibleDescription(new RegExp(msg("insights-stock-trajectory-panel-part-source-explained", { source: "posted" })));
    // Neither a split nor an equity share: the person picks the mix.
    expect(within(nflx).queryByText(/%/)).not.toBeInTheDocument();
    // It is not among the listed companies the slider re-prices.
    expect(screen.getAllByRole("row", { name: /Netflix/ })).toHaveLength(1);
    for (const move of [200, -75]) {
      setSlider(move);
      expect(within(screen.getByRole("row", { name: /Netflix/ })).getByText("$756K")).toBeInTheDocument();
    }
  });

  it("counts the roles left out and says why, by reason", async () => {
    mock(base({ set_apart: [{ reason: "not_us_pay", count: 5 }, { reason: "hourly", count: 2 }] }));
    render(<StockTrajectoryPanel />);
    const line = await screen.findByTestId("traj-left-out");
    expect(line).toHaveTextContent(msg("insights-stock-trajectory-panel-left-out", { count: 7 }));
    const why = within(line).getByRole("button", { name: msg("insights-stock-trajectory-panel-why-left-out") });
    expect(why).toHaveAccessibleDescription(new RegExp(msg("insights-stock-trajectory-panel-left-out-reason", { reason: "not_us_pay" })));
    expect(why).toHaveAccessibleDescription(new RegExp(msg("insights-stock-trajectory-panel-left-out-reason", { reason: "hourly" })));
    // A list a screen reader announces, built of phrasing content: a ul or
    // div inside the paragraph would end it early in the HTML parser.
    const items = within(within(line).getByRole("list", { hidden: true })).getAllByRole("listitem", { hidden: true });
    expect(items.map((i) => i.textContent)).toEqual([
      `${msg("insights-stock-trajectory-panel-left-out-reason", { reason: "not_us_pay" })}5`,
      `${msg("insights-stock-trajectory-panel-left-out-reason", { reason: "hourly" })}2`,
    ]);
    expect(line.tagName).toBe("P");
    expect(line.querySelector("div, ul, ol, li, table")).toBeNull();
  });

  it("still shows a cash-or-equity company and the roles left out when no listed company has a split", async () => {
    mock(base({
      overall: null, public: [], private: [],
      choice: [{ company: "netflix", ticker: "NFLX", count: 2, median_tc: 600_000, total_source: "estimated" }],
      set_apart: [{ reason: "not_us_pay", count: 3 }],
    }));
    render(<StockTrajectoryPanel />);
    expect(await screen.findByTestId("traj-choice")).toBeInTheDocument();
    expect(screen.getByTestId("traj-left-out")).toHaveTextContent(msg("insights-stock-trajectory-panel-left-out", { count: 3 }));
    expect(screen.queryByText(msg("insights-stock-trajectory-panel-no-open-roles-at-public"))).not.toBeInTheDocument();
    // No listed package, so no figure and no slider to move.
    expect(screen.queryByLabelText("Stock price change percent")).not.toBeInTheDocument();
  });

  describe("finding a company", () => {
    const find = () => screen.getByRole("searchbox", { name: msg("insights-demand-find-a-company") });
    const withChoice = () => base({
      choice: [{ company: "netflix", ticker: "NFLX", count: 4, median_tc: 756_250, total_source: "posted" }],
    });

    it("narrows every table to the companies it names, and hides a table with none", async () => {
      mock(withChoice());
      render(<StockTrajectoryPanel />);
      await screen.findByText("Google");
      fireEvent.change(find(), { target: { value: "micro" } });
      const pub = screen.getByTestId("traj-public");
      expect(within(pub).getByRole("row", { name: /Microsoft/ })).toBeInTheDocument();
      expect(within(pub).queryByRole("row", { name: /Google/ })).not.toBeInTheDocument();
      expect(screen.queryByTestId("traj-private")).not.toBeInTheDocument();
      expect(screen.queryByTestId("traj-choice")).not.toBeInTheDocument();
      expect(screen.queryByTestId("traj-no-match")).not.toBeInTheDocument();
    });

    it("reaches the private and cash-or-equity tables too, by name or slug, ignoring case", async () => {
      mock(withChoice());
      render(<StockTrajectoryPanel />);
      await screen.findByText("Google");
      fireEvent.change(find(), { target: { value: "OPENAI" } });
      expect(within(screen.getByTestId("traj-private")).getByRole("row", { name: /OpenAI/ })).toBeInTheDocument();
      expect(screen.queryByTestId("traj-public")).not.toBeInTheDocument();
      fireEvent.change(find(), { target: { value: "netf" } });
      expect(within(screen.getByTestId("traj-choice")).getByRole("row", { name: /Netflix/ })).toBeInTheDocument();
      expect(screen.queryByTestId("traj-private")).not.toBeInTheDocument();
    });

    it("says so when no company matches, and clearing it brings every table back", async () => {
      mock(withChoice());
      render(<StockTrajectoryPanel />);
      await screen.findByText("Google");
      fireEvent.change(find(), { target: { value: "  zzz " } });
      expect(screen.getByTestId("traj-no-match")).toHaveTextContent(msg("insights-stock-trajectory-panel-no-company-matches", { query: "zzz" }));
      for (const id of ["traj-public", "traj-private", "traj-choice"]) expect(screen.queryByTestId(id)).not.toBeInTheDocument();
      // The figure above is the whole market's, whatever the search.
      expect(screen.getByLabelText("Stock price change percent")).toBeInTheDocument();
      fireEvent.change(find(), { target: { value: "" } });
      for (const id of ["traj-public", "traj-private", "traj-choice"]) expect(screen.getByTestId(id)).toBeInTheDocument();
      expect(screen.queryByTestId("traj-no-match")).not.toBeInTheDocument();
    });

    it("offers no search when there is a single company to look at", async () => {
      mock(base({ public: base().public.slice(0, 1), private: [] }));
      render(<StockTrajectoryPanel />);
      await screen.findByText("Google");
      expect(screen.queryByRole("searchbox")).not.toBeInTheDocument();
    });
  });

  it("says nothing about left-out roles when none are", async () => {
    mock(base());
    render(<StockTrajectoryPanel />);
    await screen.findByRole("heading", { level: 2 });
    expect(screen.queryByTestId("traj-left-out")).not.toBeInTheDocument();
    expect(screen.queryByTestId("traj-choice")).not.toBeInTheDocument();
  });

  it("shows a listed company with no equity as having no stock exposure at all", async () => {
    mock(base({
      public: [{ company: "acme", ticker: "ACME", equity_vehicle: null, vesting: null, ...pkg(500_000, 0, 50_000) }],
      private: [],
    }));
    render(<StockTrajectoryPanel />);
    const row = (await screen.findByText("acme")).closest("tr")!;
    expect(within(row).getByText(msg("insights-stock-trajectory-panel-no-exposure"))).toBeInTheDocument();
    setSlider(200);
    expect(within(screen.getByRole("row", { name: /acme/i })).getAllByText("$500K")).toHaveLength(2);
  });
});

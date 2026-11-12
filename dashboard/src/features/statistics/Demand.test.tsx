import { msg } from "../../test/msg";
import { fireEvent, render, screen, within } from "@testing-library/react";
import { MemoryRouter, Route, Routes, useLocation } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { Demand, HiringCompany } from "../../api";
import { api } from "../../api";
import { activate } from "../../copy/activate";
import { DemandView } from "./Demand";

vi.mock("../../api", async () => {
  const actual = await vi.importActual<typeof import("../../api")>("../../api");
  return { ...actual, api: { ...actual.api, demand: vi.fn() } };
});

/* The chart is canvas; it renders the bars it is handed as text here, so a test
   can read exactly what the view chose to draw, and a bar is a button that
   clicks the way the chart reports a click (`HiringCompaniesChart.test.tsx`). */
vi.mock("./charts/StatisticsCharts", () => ({
  HiringCompaniesChart: ({ bars, onPick }: { bars: { company: string; label: string; open: number }[]; onPick?: (company: string) => void }) => (
    <ol aria-label="Company chart">
      {bars.map((b) => (
        <li key={b.label}><button type="button" onClick={() => onPick?.(b.company)}>{`${b.label}: ${b.open}`}</button></li>
      ))}
    </ol>
  ),
}));

const company = (slug: string, open: number, _other = false, extra: Partial<HiringCompany> = {}): HiringCompany => ({
  company: slug, open, new: 0, closed: 0, ...extra,
});

/* `/api/demand` as the route sends it: roles, each once, by company
   and by region. Twenty companies: five picked, fifteen from the Other
   companies set, the long tail the tab must not draw one bar each for. */
const demand = (over: Partial<Demand> = {}): Demand => ({
  open_total: 160,
  new: 3,
  closed: 2,
  companies: [
    company("anthropic", 40, false, { new: 2, closed: 1 }),
    company("google", 30),
    company("openai", 20, false, { new: 1 }),
    ...Array.from({ length: 15 }, (_, i) => company(`tail-${String(i).padStart(2, "0")}`, 4, true)),
    company("netflix", 6),
    company("stripe", 4, false, { closed: 1 }),
  ],
  regions: [
    {
      key: "north_america", open: 120, region_wide: 4,
      countries: [{ key: "united_states", open: 112 }, { key: "canada", open: 9 }],
    },
    {
      key: "europe", open: 41, region_wide: 7,
      countries: Array.from({ length: 10 }, (_, i) => ({ key: ["uk", "germany", "france", "spain", "italy", "poland", "sweden", "ireland", "netherlands", "portugal"][i], open: 10 - i })),
    },
  ],
  unplaced: 3,
  employer_dated_share: 466 / 640,
  ...over,
});

beforeEach(() => vi.clearAllMocks());

/** Where the Board route was asked for: its path and query, or nothing yet. */
function BoardProbe() {
  const { pathname, search } = useLocation();
  return <p data-testid="board">{`${pathname}${search}`}</p>;
}

function renderHiring(scope?: Parameters<typeof DemandView>[0]["scope"]) {
  return render(
    <MemoryRouter initialEntries={["/statistics/demand"]}>
      <Routes>
        <Route path="/statistics/demand" element={<DemandView scope={scope} />} />
        <Route path="/" element={<BoardProbe />} />
      </Routes>
    </MemoryRouter>,
  );
}

it("leads with the roles open now, each once, and the recent motion", async () => {
  vi.mocked(api.demand).mockResolvedValue(demand());
  renderHiring();
  expect(await screen.findByRole("heading", { name: "160 roles open" })).toBeInTheDocument();
  expect(screen.getByText(msg("insights-demand-hiring-now-new-closed", { company: msg("shared-count-company", { count: 20 }), new: "3", closed: "2" }))).toBeInTheDocument();
});

/* The load lines are whole catalog messages. Built from a noun ("Loading
   hiring…"), the Spanish line would read "Cargando hiring…": the frame
   translates, the English noun inside it does not. */
describe("while the numbers load, and when they fail", () => {
  afterEach(() => activate("en"));

  it("says each state as one message, in English", async () => {
    vi.mocked(api.demand).mockReturnValue(new Promise(() => {}));
    renderHiring();
    expect(await screen.findByRole("status")).toHaveTextContent(msg("insights-demand-loading"));
  });

  it("says each state as one message, in Spanish, with no English word inside", async () => {
    await activate("es");
    vi.mocked(api.demand).mockReturnValue(new Promise(() => {}));
    const pending = renderHiring();
    const loading = await screen.findByRole("status");
    expect(loading).toHaveTextContent(msg("insights-demand-loading"));
    expect(loading).not.toHaveTextContent(/hiring/i);
    pending.unmount();

    vi.mocked(api.demand).mockRejectedValue(new Error("offline"));
    renderHiring();
    const failed = await screen.findByRole("alert");
    expect(within(failed).getByRole("heading")).toHaveTextContent(msg("insights-demand-load-failed"));
    expect(failed).not.toHaveTextContent(/hiring/i);
  });

  it("counts new and closed over one period, named in the reader's words", async () => {
    // Side by side, "+3 −1" reads as one stretch of time: both tiles say the
    // same 2 days, and nothing on the tab counts only today.
    await activate("es");
    vi.mocked(api.demand).mockResolvedValue(demand());
    renderHiring();
    expect(await screen.findAllByText(msg("insights-demand-last-2-days"))).toHaveLength(2);
    expect(screen.queryByText(/\bhoy\b/)).toBeNull();
    expect(screen.queryByText("last 2 days")).toBeNull();
  });
});

it("draws the fifteen leaders and folds the long tail into one line that still counts it", async () => {
  vi.mocked(api.demand).mockResolvedValue(demand());
  renderHiring();
  const chart = await screen.findByRole("list", { name: "Company chart" });
  const bars = within(chart).getAllByRole("listitem").map((li) => li.textContent);
  expect(bars).toHaveLength(15);
  expect(bars[0]).toBe("Anthropic: 40");
  // 20 companies: 15 drawn, the 5 smallest folded into a sentence that keeps
  // their 4+4+4+6+4 roles; never a bar that would flatten the leaders.
  expect(
    screen.getByText(
      msg("insights-demand-more-hold", { share: "known", companies: "5 companies", roles: "22 roles", percent: 14 }),
    ),
  ).toBeInTheDocument();
});

it("asks the route for the scope it is given and names the side it shows", async () => {
  // The companies side is the scope bar's, sent to the route, which
  // ranks only that side; the view folds nothing when its companies fit.
  const scope = { side: "yours" as const, families: ["product_management"] };
  vi.mocked(api.demand).mockResolvedValue(demand({
    companies: [company("anthropic", 40), company("google", 30), company("stripe", 4)],
  }));
  renderHiring(scope);
  const bars = within(await screen.findByRole("list", { name: "Company chart" })).getAllByRole("listitem");
  expect(bars.map((li) => li.textContent)).toEqual(["Anthropic: 40", "Google: 30", "stripe: 4"]);
  expect(api.demand).toHaveBeenCalledWith(scope);
  expect(screen.getByText("Your companies")).toBeInTheDocument();
  // No tail to fold, and still the full list: a chart bar takes no keyboard
  // focus, so the list is how a keyboard reaches each company's roles.
  expect(screen.queryByText(/more hold/)).toBeNull();
  expect(screen.getByRole("button", { name: "Show all 3 companies" })).toBeInTheDocument();
});

it("opens the Board narrowed to a company when its bar is clicked", async () => {
  vi.mocked(api.demand).mockResolvedValue(demand());
  renderHiring();
  const chart = await screen.findByRole("list", { name: "Company chart" });
  fireEvent.click(within(chart).getByRole("button", { name: "Google: 30" }));
  expect(await screen.findByTestId("board")).toHaveTextContent(/^\/\?company=google$/);
});

it("opens every company in a searchable sheet", async () => {
  vi.mocked(api.demand).mockResolvedValue(demand());
  renderHiring();
  fireEvent.click(await screen.findByRole("button", { name: "Show all 20 companies" }));
  const sheet = await screen.findByRole("dialog", { name: "All companies hiring" });
  expect(within(sheet).getByText("20 of 20 companies")).toBeInTheDocument();
  fireEvent.change(within(sheet).getByRole("searchbox", { name: "Find a company" }), { target: { value: "strip" } });
  expect(within(sheet).getByText("1 of 20 companies")).toBeInTheDocument();
  expect(within(sheet).queryByText("Anthropic")).toBeNull();

  // Each company is a link to its roles on the Board, the folded tail too.
  const stripe = within(sheet).getByRole("link", { name: "stripe" });
  expect(stripe).toHaveAttribute("href", "/?company=stripe");
  fireEvent.change(within(sheet).getByRole("searchbox", { name: "Find a company" }), { target: { value: "" } });
  expect(within(sheet).getAllByRole("link")).toHaveLength(20);
  expect(within(sheet).getByRole("link", { name: "tail-14" })).toHaveAttribute("href", "/?company=tail-14");

  fireEvent.click(stripe);
  expect(await screen.findByTestId("board")).toHaveTextContent(/^\/\?company=stripe$/);
});

it("opens a region into its countries, with roles that name only the region apart", async () => {
  vi.mocked(api.demand).mockResolvedValue(demand());
  renderHiring();
  const europe = await screen.findByRole("button", { name: "Europe" });
  expect(europe).toHaveAttribute("aria-expanded", "false");
  expect(screen.queryByText("Germany")).toBeNull();

  fireEvent.click(europe);
  expect(europe).toHaveAttribute("aria-expanded", "true");
  expect(screen.getByText("Germany")).toBeInTheDocument();
  expect(screen.getByText("All of Europe")).toBeInTheDocument();
  // Eight countries shown, the other two named as a count, never dropped.
  expect(screen.queryByText("Portugal")).toBeNull();
  expect(screen.getByText("and 2 more countries")).toBeInTheDocument();
  expect(screen.getByText("3 roles name no specific place, such as Remote alone.")).toBeInTheDocument();
});

it("says so when nothing is open", async () => {
  vi.mocked(api.demand).mockResolvedValue(
    demand({ open_total: 0, new: 0, closed: 0, companies: [], regions: [], unplaced: 0 }),
  );
  renderHiring();
  expect(await screen.findByText("No open roles at these companies.")).toBeInTheDocument();
  expect(screen.getByText("No open roles yet.")).toBeInTheDocument();
  expect(screen.queryByRole("button", { name: /Show all/ })).toBeNull();
});

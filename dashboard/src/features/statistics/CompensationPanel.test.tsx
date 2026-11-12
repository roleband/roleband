import { msg } from "../../test/msg";
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { CompensationStats, DisclosedBand, PostedCountry, PostedLevel } from "../../api";
import { api } from "../../api";
import { CompensationPanel } from "./CompensationPanel";

vi.mock("../../context/SyncState", () => ({
  useSyncEpoch: () => ({ notificationVersion: 0, referenceVersion: 0 }),
  useSourceSwitch: () => {},
}));
vi.mock("../../api", () => ({
  api: { compensation: vi.fn() },
}));

const mock = (data: CompensationStats) => vi.mocked(api.compensation).mockResolvedValue(data);

const sum = (p25: number, p50: number, p75: number, p90: number, count: number) => ({
  count,
  min: 298_053,
  max: 1_500_000,
  p25,
  p50,
  p75,
  p90,
});

const figure = (
  level_band: string,
  low: number,
  high: number,
  ranges: number,
  employers: number,
  roles: number,
): PostedLevel => ({
  level_band, ranges, employers, roles, enough: true, low, high,
  mid_p25: low + 10_000, mid_p75: high - 10_000,
});
// A level with ranges, but fewer than the minimums: counts, no figure.
const thin = (level_band: string, ranges: number, employers: number, roles: number): PostedLevel => ({
  level_band, ranges, employers, roles, enough: false, low: null, high: null, mid_p25: null, mid_p75: null,
});
const band = (company: string, level_band: string, low: number, high: number, reqs = 1): DisclosedBand =>
  ({ company, level_band, low, high, reqs });

const us: PostedCountry = {
  country: "US",
  currency: "USD",
  ranges: 22,
  yours: true,
  levels: [
    figure("senior", 180_000, 240_000, 9, 6, 40),
    thin("staff", 3, 2, 5),
    figure("principal", 198_000, 270_000, 241, 141, 600),
    figure("director_plus", 220_000, 290_000, 666, 442, 1_500),
  ],
  not_placed: { roles: 37, ranges: 12 },
  other_currency: 2,
  excluded: { not_base: 80, not_yearly: 2, implausible: 1, placed_by_pay: 6 },
  bands: [
    band("google", "senior", 200_000, 280_000, 9),
    band("google", "principal", 262_000, 365_000, 18),
    band("google-deepmind", "principal", 207_000, 301_000),
    band("apple", "principal", 240_000, 340_000, 4),
    band("apple", "principal", 300_000, 420_000, 2),
  ],
};
const gb: PostedCountry = {
  country: "GB",
  currency: "GBP",
  ranges: 13,
  yours: false,
  levels: [figure("principal", 110_000, 150_000, 13, 9, 20)],
  not_placed: { roles: 0, ranges: 0 },
  other_currency: 0,
  excluded: { not_base: 10, not_yearly: 0, implausible: 0, placed_by_pay: 0 },
  bands: [band("deepmind", "principal", 110_000, 150_000)],
};
// One of the person's places, with no range posted there.
const se: PostedCountry = {
  country: "SE", currency: null, ranges: 0, yours: true, levels: [],
  not_placed: { roles: 0, ranges: 0 }, other_currency: 0, bands: [],
  excluded: { not_base: 0, not_yearly: 1, implausible: 0, placed_by_pay: 0 },
};

const posted = (over: Partial<CompensationStats["posted"]> = {}): CompensationStats["posted"] => ({
  min_employers: 5,
  min_ranges: 8,
  default_country: "US",
  countries: [us, gb, se],
  excluded: { not_base: 90, not_yearly: 3, implausible: 1, no_country: 4, placed_by_pay: 6 },
  your_levels: ["principal", "director_plus"],
  ...over,
});

// No role priced by its base alone: the block is sent, empty.
const noBase: CompensationStats["base_estimates"] = {
  min_roles: 5, coverage: { with_base: 0, total_open: 732 }, overall: null, by_level: [], by_company: [], by_family: [],
};
// 40 roles priced by their base alone.
const someBase: CompensationStats["base_estimates"] = {
  min_roles: 5,
  coverage: { with_base: 40, total_open: 772 },
  overall: sum(180_000, 210_000, 240_000, 260_000, 40),
  by_level: [
    { level_band: "senior", ...sum(180_000, 196_000, 210_000, 220_000, 25) },
    { level_band: "staff", ...sum(230_000, 247_000, 260_000, 270_000, 15) },
  ],
  by_company: [],
  by_family: [],
};

// A full valid payload; individual tests override the slices they assert on.
const base = (over: Partial<CompensationStats> = {}): CompensationStats => ({
  currency: "USD",
  min_roles: 5,
  coverage: { with_comp: 732, total_open: 732, pct: 1.0 },
  overall: sum(306_217, 600_000, 644_468, 900_000, 732),
  by_level: [
    { level_band: "senior", ...sum(250_000, 306_217, 340_000, 400_000, 406) },
    { level_band: "staff", ...sum(560_000, 644_468, 720_000, 820_000, 265) },
  ],
  by_company: [{ company: "openai", ...sum(700_000, 900_000, 1_000_000, 1_200_000, 58) }],
  by_family: [{ family: "ml_ai_research", ...sum(400_000, 479_251, 600_000, 820_000, 170) }],
  posted: posted(),
  disclosure: {
    overall: { open: 732, checked: 600, disclosed: 150, rate: 0.25 },
    by_company: [
      { company: "google", open: 200, checked: 200, disclosed: 160, rate: 0.8 },
      { company: "openai", open: 60, checked: 50, disclosed: 5, rate: 0.1 },
    ],
    by_level: [
      { level_band: "senior", open: 406, checked: 400, disclosed: 100, rate: 0.25 },
      { level_band: "staff", open: 265, checked: 200, disclosed: 50, rate: 0.25 },
    ],
  },
  base_estimates: noBase,
  ...over,
});

const show = (props: { advanced?: boolean } = {}, url = "/statistics/compensation") =>
  render(
    <MemoryRouter initialEntries={[url]}>
      <CompensationPanel {...props} />
    </MemoryRouter>,
  );

const headline = () => screen.findByRole("heading", { level: 2 });
const byLevel = (country: string) =>
  screen.getByRole("region", { name: msg("insights-posted-by-level", { country }) });

describe("CompensationPanel", () => {
  beforeEach(() => vi.clearAllMocks());

  it("opens on the typical posted base salary at the person's level in the US, never the estimate", async () => {
    mock(base());
    show();

    expect(await headline()).toHaveTextContent(msg("insights-posted-typically", { low: "$198K", high: "$270K" }));
    // The estimate's median is no headline anywhere on the tab.
    expect(screen.queryByText(/\$600K/)).toBeNull();
    expect(screen.getByText(
      msg("insights-posted-line", { level: "Principal", country: "United States", ranges: 241, employers: 141, roles: 600 }),
      { exact: false },
    )).toBeInTheDocument();
    expect(screen.getByRole("button", { name: msg("insights-posted-how-read") }))
      .toHaveAccessibleDescription(msg("insights-posted-how-read-body"));
    expect(screen.getByRole("combobox", { name: msg("insights-posted-country") })).toHaveValue("US");
    expect(screen.getByRole("combobox", { name: msg("insights-posted-level") })).toHaveValue("principal");
  });

  it("shows the middle half and the share posting a range, never an estimate coverage tile", async () => {
    mock(base());
    show();
    await headline();

    const tile = (label: string) => screen.getByText(label).closest(".kpi") as HTMLElement;
    expect(within(tile(msg("insights-posted-middle-half"))).getByText("$208K–$260K")).toBeInTheDocument();
    expect(within(tile(msg("insights-posted-share"))).getByText("25%")).toBeInTheDocument();
    expect(within(tile(msg("insights-posted-share"))).getByText(msg("insights-posted-checked", { checked: 600 })))
      .toBeInTheDocument();
    const labels = [...document.querySelectorAll(".kpi-l")].map((el) => el.textContent);
    expect(labels).toEqual([msg("insights-posted-middle-half"), msg("insights-posted-share")]);
  });

  it("withholds the figure for a level below the minimums and says why, with its counts", async () => {
    mock(base());
    show({}, "/statistics/compensation?level=staff");

    const h = await headline();
    expect(h).toHaveTextContent(msg("insights-posted-too-few"));
    expect(h).not.toHaveTextContent("$");
    expect(screen.getByText(
      msg("insights-posted-line", { level: "Staff", country: "United States", ranges: 3, employers: 2, roles: 5 }),
      { exact: false },
    )).toHaveTextContent(msg("insights-posted-needs", { min_employers: 5, min_ranges: 8 }));
    const middle = screen.getByText(msg("insights-posted-middle-half")).closest(".kpi") as HTMLElement;
    expect(middle.querySelector(".kpi-n")).toHaveTextContent(/^—$/);
  });

  it("switches country and level, and reads each country in its own currency", async () => {
    mock(base());
    const user = userEvent.setup();
    show();
    await headline();

    await user.selectOptions(screen.getByRole("combobox", { name: msg("insights-posted-level") }), "director_plus");
    expect(await headline()).toHaveTextContent(msg("insights-posted-typically", { low: "$220K", high: "$290K" }));

    // The level picked stays picked in another country, which says it has nothing there.
    await user.selectOptions(screen.getByRole("combobox", { name: msg("insights-posted-country") }), "GB");
    expect(await headline()).toHaveTextContent(msg("insights-posted-none"));
    expect(screen.getByText(msg("insights-posted-none-at-level", { country: "United Kingdom" }))).toBeInTheDocument();
    expect(screen.getByRole("combobox", { name: msg("insights-posted-level") })).toHaveValue("director_plus");

    await user.selectOptions(screen.getByRole("combobox", { name: msg("insights-posted-level") }), "principal");
    expect(await headline()).toHaveTextContent(msg("insights-posted-typically", { low: "£110K", high: "£150K" }));
    expect(byLevel("United Kingdom")).toBeInTheDocument();
  });

  it("keeps a level that is not the person's when the new country has no range there", async () => {
    mock(base());
    const user = userEvent.setup();
    show();
    await headline();

    await user.selectOptions(screen.getByRole("combobox", { name: msg("insights-posted-level") }), "senior");
    expect(await headline()).toHaveTextContent(msg("insights-posted-typically", { low: "$180K", high: "$240K" }));
    await user.selectOptions(screen.getByRole("combobox", { name: msg("insights-posted-country") }), "GB");
    expect(await headline()).toHaveTextContent(msg("insights-posted-none"));
    expect(screen.getByText(msg("insights-posted-none-at-level", { country: "United Kingdom" }))).toBeInTheDocument();
    expect(screen.getByRole("combobox", { name: msg("insights-posted-level") })).toHaveValue("senior");
  });

  it("names a country of the person's with nothing posted, rather than hiding it", async () => {
    mock(base());
    const user = userEvent.setup();
    show();
    await headline();

    const picker = screen.getByRole("combobox", { name: msg("insights-posted-country") });
    expect(within(picker).getByRole("option", { name: msg("insights-posted-your-place", { name: "Sweden" }) }))
      .toBeInTheDocument();
    expect(within(picker).getByRole("option", { name: "United Kingdom" })).toBeInTheDocument();
    await user.selectOptions(picker, "SE");
    expect(await headline()).toHaveTextContent(msg("insights-posted-none"));
    expect(screen.getByText(msg("insights-posted-none-in-country", { country: "Sweden" }))).toBeInTheDocument();
    // Both of the person's levels are still listed there, each saying it has nothing.
    const rows = within(byLevel("Sweden")).getAllByRole("listitem");
    expect(rows.map((r) => r.querySelector("strong")?.textContent)).toEqual(["Principal", "Director+"]);
    for (const row of rows) {
      expect(row).toHaveTextContent(msg("insights-posted-none"));
      expect(row).not.toHaveTextContent(msg("insights-pay-bands-bands-from-employers", { bands: 0, employers: 0 }));
    }
  });

  it("lists every level with its figure or why it has none, and counts unplaced roles apart", async () => {
    mock(base());
    show();
    await headline();

    const panel = byLevel("United States");
    const rows = within(panel).getAllByRole("listitem");
    expect(rows.map((r) => r.querySelector("strong")?.textContent)).toEqual(["Senior", "Staff", "Principal", "Director+"]);
    expect(rows[0]).toHaveTextContent("$180K–$240K");
    expect(rows[1]).toHaveTextContent(msg("insights-posted-too-few"));
    expect(rows[1]).toHaveTextContent(msg("insights-pay-bands-bands-from-employers", { bands: 3, employers: 2 }));
    expect(within(rows[2]).getByText(msg("insights-posted-your-level"))).toBeInTheDocument();
    expect(within(rows[0]).queryByText(msg("insights-posted-your-level"))).toBeNull();
    // Roles with no placed level are said once, below the levels, never inside one.
    expect(within(panel).getByText(msg("insights-posted-not-placed", { roles: 37, ranges: 12 }))).toBeInTheDocument();
    expect(rows.some((r) => /not placed/i.test(r.textContent ?? ""))).toBe(false);
    expect(within(panel).getByText(msg("insights-posted-other-currency", { count: 2 }))).toBeInTheDocument();
  });

  it("says when nothing is posted anywhere, and still shows the estimates", async () => {
    mock(base({ posted: posted({ countries: [], default_country: null }) }));
    show();

    expect(await headline()).toHaveTextContent(msg("insights-posted-none"));
    expect(screen.getByText(msg("insights-posted-none-anywhere"))).toBeInTheDocument();
    expect(screen.queryByRole("combobox")).toBeNull();
    expect(screen.getByText(msg("insights-compensation-panel-median-comp-by-level"))).toBeInTheDocument();
  });

  it("marks every estimate panel as a US-only estimate", async () => {
    mock(base());
    show();
    await headline();

    for (const heading of [
      msg("insights-compensation-panel-median-comp-by-level"),
      msg("insights-compensation-panel-top-paying-companies"),
      msg("insights-compensation-panel-median-pay-by-discipline"),
    ]) {
      const panel = screen.getByRole("heading", { level: 3, name: (name) => name.startsWith(heading) }).closest(".panel")!;
      expect(within(panel as HTMLElement).getByText(msg("insights-posted-estimate-us-only"))).toBeInTheDocument();
    }
    expect(screen.getByRole("button", { name: msg("insights-compensation-panel-how-compensation-is-estimated") }))
      .toHaveAccessibleDescription(msg("insights-compensation-panel-estimated-total-compensation-is-imputed"));
  });

  it("orders estimate levels by seniority and shows each median and the roles it rests on", async () => {
    mock(base());
    show();
    await headline();

    const panel = screen.getByText(msg("insights-compensation-panel-median-comp-by-level")).closest(".panel") as HTMLElement;
    const seniorRow = within(panel).getByText("Senior").closest(".comp-row") as HTMLElement;
    expect(within(seniorRow).getByText("$306K")).toBeInTheDocument();
    expect(within(seniorRow).getByText(msg("insights-compensation-panel-roles", { count: 406 }))).toBeInTheDocument();
    expect(seniorRow.getAttribute("title")).toContain(
      msg("insights-compensation-panel-spread", {
        low: "$250K",
        high: "$340K",
        roles: msg("insights-compensation-panel-roles", { count: 406 }),
      }),
    );
  });

  it("shows companies and disciplines as an equal pair, the same number of rows each", async () => {
    const co = (i: number) => ({ company: `co-${i}`, ...sum(1, 900_000 - i, 2, 3, 10) });
    const fam = (i: number) => ({ family: `f${i}`, family_display: `Family ${i}`, ...sum(1, 800_000 - i, 2, 3, 10) });
    mock(base({ by_company: Array.from({ length: 15 }, (_, i) => co(i)), by_family: Array.from({ length: 11 }, (_, i) => fam(i)) }));
    show();

    const companies = (await screen.findByRole("heading", { name: msg("insights-compensation-panel-top-paying-companies") })).closest(".panel")!;
    const families = screen.getByRole("heading", { name: msg("insights-compensation-panel-median-pay-by-discipline") }).closest(".panel")!;
    expect(companies.querySelectorAll(".comp-row")).toHaveLength(8);
    expect(families.querySelectorAll(".comp-row")).toHaveLength(8);
    expect(companies.parentElement).toBe(families.parentElement);
  });

  it("keeps the basic view to posted pay and the estimates; every range and who states pay are advanced", async () => {
    mock(base({ base_estimates: someBase }));
    show();
    await headline();

    expect(screen.queryByRole("list", { name: msg("insights-pay-bands-published-base-salary-bands-by") })).toBeNull();
    expect(screen.queryByText(msg("insights-disclosure-panel-who-states-pay"), { exact: false })).toBeNull();
    expect(screen.queryByRole("region", { name: msg("insights-compensation-panel-estimated-base-by-level") })).toBeNull();
  });

  it("still reports base-only estimates when no role has a total estimate, in the basic view too", async () => {
    mock(base({ coverage: { with_comp: 0, total_open: 40, pct: 0 }, overall: null, by_level: [],
      by_company: [], by_family: [], base_estimates: someBase }));
    show();

    // Posted pay still leads; no empty state stands in for the missing estimate.
    expect(await headline()).toHaveTextContent(msg("insights-posted-typically", { low: "$198K", high: "$270K" }));
    expect(screen.queryByText(/compensation estimate yet/i)).toBeNull();
    expect(screen.queryByText(msg("insights-compensation-panel-median-comp-by-level"))).toBeNull();
    const panel = screen.getByRole("region", { name: msg("insights-compensation-panel-estimated-base-by-level") });
    expect(panel).toHaveTextContent(msg("insights-compensation-panel-base-only-lead", { count: 40 }));
    expect(within(panel).getByText(msg("insights-posted-estimate-us-only"))).toBeInTheDocument();
  });

  it("draws every posted range of the country a row per level and colours only the employer picked", async () => {
    mock(base());
    const user = userEvent.setup();
    show({ advanced: true });
    await headline();

    expect(screen.getByRole("heading", {
      level: 3,
      name: (name) => name.startsWith(msg("insights-posted-every-range", { country: "United States" })),
    })).toBeInTheDocument();
    const rows = within(screen.getByRole("list", { name: msg("insights-pay-bands-published-base-salary-bands-by") }));
    // One row per level, never one per range: five ranges, two rows.
    expect(rows.getAllByRole("listitem")).toHaveLength(2);
    const principal = rows.getByRole("img", { name: /^Principal: 4 ranges from 3 employers/ });
    // The outline is the server's typical range, not a median the screen recomputes.
    expect(principal).toHaveAccessibleName(/typically \$198K to \$270K\.$/);
    expect(principal.querySelectorAll(".pay-band[data-chosen]")).toHaveLength(0);

    await user.click(screen.getByRole("button", { name: /^Filter by/ }));
    await user.click(await screen.findByRole("option", { name: /Google DeepMind/ }));
    expect(principal).toHaveAccessibleName(/Google DeepMind: \$207K to \$301K/);
    expect(principal.querySelectorAll(".pay-band[data-chosen]")).toHaveLength(1);
    expect(rows.getByRole("img", { name: /^Senior/ })).toHaveAccessibleName(/posts no range at this level/);

    // Every reason a role is left out is said, beside the chart.
    const about = screen.getByRole("button", { name: msg("insights-compensation-panel-about-published-salary-bands") });
    expect(about).toHaveAccessibleDescription(expect.stringContaining(msg("insights-comp-bands-placed-by-pay", { count: 6 })));
    expect(about).toHaveAccessibleDescription(expect.stringContaining(msg("insights-comp-bands-no-country", { count: 4 })));
  });

  it("draws every range, however many, in the chosen country's currency", async () => {
    const many = Array.from({ length: 251 }, (_, i) => band(`co-${i}`, "principal", 100_000 + i * 100, 140_000 + i * 100));
    mock(base({ posted: posted({ countries: [{ ...gb, bands: many }], default_country: "GB" }) }));
    show({ advanced: true });
    await headline();

    const principal = screen.getByRole("img", { name: /^Principal: 251 ranges from 251 employers/ });
    expect(principal.querySelectorAll(".pay-band")).toHaveLength(251);
    expect(principal).toHaveAccessibleName(/typically £110K to £150K/);
  });

  it("says why each of the country's own roles was left out when no range there qualifies", async () => {
    mock(base());
    show({ advanced: true }, "/statistics/compensation?country=SE");
    await headline();

    const every = msg("insights-posted-every-range", { country: "Sweden" });
    const panel = screen.getByRole("heading", { level: 3, name: (name) => name.startsWith(every) }).closest(".panel") as HTMLElement;
    expect(within(panel).queryByRole("list", { name: msg("insights-pay-bands-published-base-salary-bands-by") })).toBeNull();
    const note = panel.querySelector(".hiring-note");
    expect(note).toHaveTextContent(msg("insights-comp-bands-not-yearly", { count: 1 }));
    // Roles in no one country are no country's, so they are said here too.
    expect(note).toHaveTextContent(msg("insights-comp-bands-no-country", { count: 4 }));
    // The US's and the UK's roles are never counted under Sweden.
    expect(note).not.toHaveTextContent(/total compensation or does not say/);
    expect(note).not.toHaveTextContent(/level read from/);
  });

  it("counts only the chosen country's roles left out beside its chart", async () => {
    mock(base());
    show({ advanced: true }, "/statistics/compensation?country=GB");
    await headline();

    const about = screen.getByRole("button", { name: msg("insights-compensation-panel-about-published-salary-bands") });
    expect(about).toHaveAccessibleDescription(expect.stringContaining(msg("insights-comp-bands-not-base", { count: 10 })));
    expect(about).toHaveAccessibleDescription(expect.not.stringContaining(msg("insights-comp-bands-not-base", { count: 90 })));
    expect(about).toHaveAccessibleDescription(expect.not.stringContaining(msg("insights-comp-bands-placed-by-pay", { count: 6 })));
  });

  it("says why each role was left out when no country has a range at all", async () => {
    mock(base({ posted: posted({ countries: [], default_country: null }) }));
    show({ advanced: true });
    expect(await headline()).toHaveTextContent(msg("insights-posted-none"));
    expect(screen.getByText(msg("insights-comp-bands-not-base", { count: 90 }), { exact: false })).toBeInTheDocument();
  });

  it("opens who states pay by level, and draws no pay over time", async () => {
    mock(base());
    show({ advanced: true });
    await headline();

    const who = msg("insights-disclosure-panel-who-states-pay");
    expect(screen.getByRole("heading", { level: 3, name: (name) => name.startsWith(who) })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: msg("insights-common-by-level") })).toHaveAttribute("aria-pressed", "true");
    const titles = screen.getAllByRole("heading", { level: 3 }).map((h) => h.textContent ?? "");
    expect(titles.filter((t) => /over time|trend|skill/i.test(t))).toEqual([]);
    expect(api.compensation).toHaveBeenCalledTimes(1);
    expect(api.compensation).toHaveBeenCalledWith(undefined);
  });
});

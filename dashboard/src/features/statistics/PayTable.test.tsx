import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";
import type { PayDiscipline, PayTable as PayTableData, PayTableRow } from "../../api";
import { msg } from "../../test/msg";
import { PayTable } from "./PayTable";

/* The company table at one level. The posted range is the authority: an
   estimate stands only where a company posts none, equity names what the
   employer states, and nothing on a row is a figure we made up. */

const row = (company: string, over: Partial<PayTableRow> = {}): PayTableRow => ({
  company,
  followed_as_set: false,
  open_roles: 2,
  posting: 2,
  checked: 2,
  currency: "USD",
  low: 250_000,
  high: 320_000,
  ranges: [{ low: 250_000, high: 320_000, roles: 2 }],
  other_currency: false,
  reason: null,
  estimate_base: null,
  estimate_total: null,
  equity: null,
  ...over,
});

const silent = (company: string, over: Partial<PayTableRow> = {}): PayTableRow =>
  row(company, { low: null, high: null, ranges: [], currency: null, posting: 0, reason: "none", ...over });

const table = (over: Partial<PayTableData> = {}): PayTableData => ({
  country: "US",
  level_band: "principal",
  currency: "USD",
  skill: null,
  estimates: true,
  rows: [row("amazon")],
  not_placed: [],
  skills: [],
  min_skill_roles: 3,
  by_discipline: { min_employers: 5, min_ranges: 8, max_employer_share: 0.4, disciplines: [] },
  ...over,
});

const discipline = (family: string, over: Partial<PayDiscipline> = {}): PayDiscipline => ({
  family,
  picked: false,
  ranges: 10,
  employers: 5,
  roles: 40,
  enough: true,
  low: 245_000,
  high: 325_000,
  mid_p25: 262_500,
  mid_p75: 307_500,
  top_share: 0.2,
  withheld: null,
  ...over,
});

const show = (data: PayTableData, props: { advanced?: boolean; skill?: string | null } = {}) => {
  const onSkill = vi.fn();
  render(
    <MemoryRouter>
      <PayTable data={data} skill={props.skill ?? null} onSkill={onSkill} advanced={props.advanced} />
    </MemoryRouter>,
  );
  return { onSkill };
};

/** The row whose company cell is exactly this name, so "Google" never also
 *  matches "Google DeepMind". */
/** The skill filter's trigger, named as the catalogue names it: by the skill
 *  picked, or by "any skill" with none. */
const filterTrigger = (label = msg("insights-pay-table-any-skill")) =>
  msg("shared-filter-select-filter-by", { label: label.toLowerCase() });

const rowOf = (company: string) =>
  screen.getByRole("rowheader", { name: company }).closest("tr") as HTMLElement;

describe("PayTable", () => {
  it("names the level and country it answers, and links each company to the board", () => {
    show(table());

    expect(screen.getByRole("heading", { level: 3 })).toHaveTextContent(
      msg("insights-pay-table-heading", { level: "Principal", country: "United States" }),
    );
    expect(screen.getByRole("link", { name: "Amazon" })).toHaveAttribute("href", "/?company=amazon");
    // The open-roles figure is not a link: the board shows every level.
    expect(within(rowOf("Amazon")).getAllByRole("link")).toHaveLength(1);
  });

  it("shows a company's posted range with its count, and the ranges behind it as text", () => {
    show(table({
      rows: [row("amazon", {
        low: 220_000, high: 300_000, open_roles: 5, posting: 5, checked: 5,
        ranges: [
          { low: 260_000, high: 340_000, roles: 1 },
          { low: 220_000, high: 300_000, roles: 1 },
          { low: 200_000, high: 280_000, roles: 3 },
        ],
      })],
    }));

    const cells = within(rowOf("Amazon")).getAllByRole("cell");
    expect(cells[0]).toHaveTextContent("$220K–$300K");
    expect(cells[0]).toHaveTextContent(msg("insights-pay-table-ranges", { count: 3 }));
    // The strip is a picture; the same ranges are readable as text.
    expect(within(cells[0]).getByRole("img")).toHaveAccessibleName(
      msg("insights-pay-table-ranges-read", {
        company: "Amazon",
        ranges: "$260K–$340K, $220K–$300K, $200K–$280K",
      }),
    );
  });

  it("says why a cell holds no range, by its own reason", () => {
    show(table({
      rows: [
        silent("netflix", { reason: "total" }),
        silent("apple", { reason: "several_countries" }),
        silent("google", { reason: "unclear" }),
        silent("google-deepmind", { reason: "unread", checked: 0 }),
        silent("openai"),
      ],
    }));

    expect(within(rowOf("Netflix")).getAllByRole("cell")[0]).toHaveTextContent(msg("insights-pay-table-total"));
    expect(within(rowOf("Apple")).getAllByRole("cell")[0]).toHaveTextContent(msg("insights-pay-table-several-countries"));
    expect(within(rowOf("Google")).getAllByRole("cell")[0]).toHaveTextContent(msg("insights-pay-table-unclear"));
    expect(within(rowOf("Google DeepMind")).getAllByRole("cell")[0]).toHaveTextContent(msg("insights-pay-table-unread"));
    expect(within(rowOf("OpenAI")).getAllByRole("cell")[0]).toHaveTextContent(msg("insights-pay-table-no-range"));
  });

  it("says a company posts a range on some of its roles, not all", () => {
    show(table({ rows: [row("netflix", { open_roles: 5, checked: 5, posting: 3 })] }));

    expect(within(rowOf("Netflix")).getAllByRole("cell")[0])
      .toHaveTextContent(msg("insights-pay-table-some-roles", { posting: 3, roles: 5 }));
  });

  it("marks an estimated base by its level and discipline, and a total by its rung", () => {
    show(table({
      rows: [
        silent("apple", { estimate_base: { low: 232_000, high: 379_000, families: ["product_management", "engineering_management"] } }),
        silent("anthropic", { estimate_total: { low: 1_500_000, high: 1_500_000, rung: "Senior Staff Software Engineer" } }),
      ],
    }));

    const base = within(rowOf("Apple")).getAllByRole("cell")[1];
    expect(base).toHaveTextContent("$232K–$379K");
    expect(within(base).getByText(msg("insights-pay-table-est-base-full"))).toBeInTheDocument();
    expect(within(base).getByRole("button")).toHaveAccessibleDescription(
      msg("insights-pay-table-est-base-from", { level: "Principal", disciplines: "Product Management, Engineering Management" }),
    );

    const total = within(rowOf("Anthropic")).getAllByRole("cell")[1];
    expect(total).toHaveTextContent("$1.50M");
    expect(within(total).getByText(msg("insights-pay-table-est-tc-full"))).toBeInTheDocument();
    expect(within(total).getByRole("button")).toHaveAccessibleDescription(
      msg("insights-pay-table-est-tc-from", { rung: "Senior Staff Software Engineer" }),
    );
  });

  it("names a total estimate by its level when no single rung was read", () => {
    show(table({ rows: [silent("openai", { estimate_total: { low: 400_000, high: 400_000, rung: null } })] }));

    expect(within(within(rowOf("OpenAI")).getAllByRole("cell")[1]).getByRole("button"))
      .toHaveAccessibleDescription(msg("insights-pay-table-est-tc-from-level", { level: "Principal" }));
  });

  it("hides the estimate column outside the US and says why", () => {
    show(table({ country: "GB", currency: "GBP", estimates: false, rows: [row("google-deepmind", { currency: "GBP", low: 110_000, high: 150_000, ranges: [{ low: 110_000, high: 150_000, roles: 2 }] })] }));

    expect(screen.queryByRole("columnheader", { name: msg("insights-pay-table-estimate") })).toBeNull();
    expect(screen.getByText(msg("insights-pay-table-estimates-us"))).toBeInTheDocument();
    expect(within(rowOf("Google DeepMind")).getAllByRole("cell")[0]).toHaveTextContent("£110K–£150K");
  });

  it("shows equity as the employer states it, and a dash where it states nothing", () => {
    show(table({
      rows: [
        row("amazon", { equity: { vehicle: "rsu", vesting: "5/15/40/40", rule: null } }),
        row("apple", { equity: { vehicle: null, vesting: null, rule: "none" } }),
        row("netflix", { equity: { vehicle: "cash_election", vesting: null, rule: "employee_election" } }),
        row("openai", { equity: null }),
      ],
    }));

    expect(within(rowOf("Amazon")).getAllByRole("cell")[3]).toHaveTextContent("RSUs");
    expect(within(rowOf("Amazon")).getAllByRole("cell")[3])
      .toHaveTextContent(msg("insights-stock-trajectory-panel-vests", { schedule: "5/15/40/40" }));
    expect(within(rowOf("Apple")).getAllByRole("cell")[3])
      .toHaveTextContent(msg("insights-stock-trajectory-panel-no-equity"));
    expect(within(rowOf("Netflix")).getAllByRole("cell")[3])
      .toHaveTextContent(msg("insights-stock-trajectory-panel-cash-election"));
    // No percentage anywhere: the only equity share we could state is an estimate.
    expect(within(rowOf("OpenAI")).getAllByRole("cell")[3]).toHaveTextContent("—");
    expect(screen.queryByText(/%/)).toBeNull();
  });

  it("caps the rows, says how many more hire without posting a range, and opens them all", async () => {
    const rows = [
      ...Array.from({ length: 20 }, (_, i) => row(`co-${String(i).padStart(2, "0")}`)),
      silent("quiet-one"),
      silent("quiet-two"),
    ];
    show(table({ rows }));

    expect(screen.getAllByRole("row")).toHaveLength(21); // the header and 20 rows
    expect(screen.getByText(msg("insights-pay-table-more-silent", { count: 2 }))).toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: msg("insights-demand-show-all", { company: 22 }) }));
    expect(screen.getAllByRole("row")).toHaveLength(23);
    expect(screen.queryByText(msg("insights-pay-table-more-silent", { count: 2 }))).toBeNull();
  });

  it("finds a company among every row, not only the ones in view", async () => {
    const rows = [
      ...Array.from({ length: 20 }, (_, i) => row(`co-${String(i).padStart(2, "0")}`)),
      silent("netflix"),
    ];
    show(table({ rows }));

    expect(screen.queryByRole("link", { name: "Netflix" })).toBeNull();
    await userEvent.type(screen.getByRole("searchbox", { name: msg("insights-demand-find-a-company") }), "netflix");
    expect(screen.getByRole("link", { name: "Netflix" })).toBeInTheDocument();
  });

  it("offers the skills the table's roles name and reports the pick", async () => {
    const { onSkill } = show(table({ skills: [{ term: "python", roles: 8 }, { term: "sql", roles: 3 }] }));

    await userEvent.click(screen.getByRole("button", { name: filterTrigger() }));
    await userEvent.click(screen.getByRole("option", { name: "Python" }));
    expect(onSkill).toHaveBeenCalledWith("python");
  });

  it("names the skill in the heading while one is picked", () => {
    show(table({ skill: "python", skills: [{ term: "python", roles: 8 }] }), { skill: "python" });

    expect(screen.getByRole("heading", { level: 3 })).toHaveTextContent(
      msg("insights-pay-table-heading-skill", { level: "Principal", country: "United States", skill: "Python" }),
    );
  });

  it("counts the roles with no placed level under the table, never as a row", () => {
    show(table({ not_placed: [{ company: "apple", roles: 299 }, { company: "netflix", roles: 4 }] }));

    expect(screen.getByText(msg("insights-pay-table-not-placed", { roles: 303, companies: 2 }))).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "Apple" })).toBeNull();
  });

  it("says no company hires at the level rather than showing an empty table", () => {
    show(table({ rows: [] }));

    expect(screen.getByText(msg("insights-pay-table-empty", { country: "United States" }))).toBeInTheDocument();
    expect(screen.queryByRole("table")).toBeNull();
  });

  it("says a picked skill matches no role at this level, and keeps the way back", async () => {
    const { onSkill } = show(table({ rows: [], skill: "rust", skills: [] }), { skill: "rust" });

    expect(screen.getByText(msg("insights-pay-table-skill-empty", { country: "United States", skill: "Rust" })))
      .toBeInTheDocument();
    // The table offers no skill of its own now, so the picked one is the only
    // option: without it the person cannot return to every skill.
    await userEvent.click(screen.getByRole("button", { name: filterTrigger("Rust") }));
    await userEvent.click(screen.getByRole("option", { name: "Rust" }));
    expect(onSkill).toHaveBeenCalledWith(null);
  });

  it("keeps pay by discipline to the advanced view, every discipline at once", () => {
    const data = table({
      by_discipline: {
        min_employers: 5, min_ranges: 8, max_employer_share: 0.4,
        disciplines: [
          discipline("product_management"),
          discipline("software_engineering", { picked: true, low: 280_000, high: 360_000 }),
          discipline("data_science", { withheld: "too_few", enough: false, low: null, high: null, ranges: 4, employers: 3 }),
          discipline("engineering_management", { withheld: "one_employer", enough: false, low: null, high: null, top_share: 0.6 }),
        ],
      },
    });
    const heading = msg("insights-pay-discipline-heading", { level: "Principal", country: "United States" });

    show(data);
    expect(screen.queryByRole("region", { name: heading })).toBeNull();

    show(data, { advanced: true });
    const panel = screen.getByRole("region", { name: heading });
    const items = within(panel).getAllByRole("listitem");
    expect(items).toHaveLength(2);
    expect(items[1]).toHaveTextContent("$280K–$360K");
    expect(within(items[1]).getByText(msg("insights-pay-discipline-yours"))).toBeInTheDocument();
    // A discipline with no figure says which rule it misses, and never a range.
    expect(within(panel).getByText(msg("insights-pay-discipline-too-few", { families: "Data Science & Analytics" }))).toBeInTheDocument();
    expect(within(panel).getByText(msg("insights-pay-discipline-one-employer", { families: "Engineering Management" }))).toBeInTheDocument();
    expect(within(panel).getByText(msg("insights-pay-discipline-note"))).toBeInTheDocument();
  });
});

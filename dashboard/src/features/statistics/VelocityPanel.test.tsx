import { render, screen, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { VelocityStats } from "../../api";
import { api } from "../../api";
import { VelocityPanel } from "./VelocityPanel";

vi.mock("../../api", () => ({
  api: { velocity: vi.fn() },
}));

const mock = (data: VelocityStats) =>
  vi.mocked(api.velocity).mockResolvedValue(data);

const AGING = [
  { lo: 0, hi: 7, label: "< 1 week", count: 732 },
  { lo: 7, hi: 14, label: "1–2 weeks", count: 0 },
  { lo: 14, hi: 30, label: "2–4 weeks", count: 0 },
  { lo: 30, hi: 60, label: "1–2 months", count: 0 },
  { lo: 60, hi: 90, label: "2–3 months", count: 0 },
  { lo: 90, hi: null, label: "3 months+", count: 0 },
];

describe("VelocityPanel", () => {
  beforeEach(() => vi.clearAllMocks());

  it("shows activity KPIs, the company table, and aging distribution", async () => {
    mock({
      days: 30,
      since: null,
      kpis: {
        open_total: 732, already_listed: 0, age_unknown: 0, closed_unknown: 0,
        opened: 733,
        reposted: 12,
        closed: 1,
        median_days_open: 0,
        median_observed_listing_duration_days: null,
        closed_sample: 1,
        employer_dated_share: 0.7,
        closed_employer_dated_share: 1,
      },
      aging: AGING,
      posted: AGING,
      by_company: [
        { company: "apple", open: 392, opened: 392, reposted: 2, closed: 0, median_days_open: 0, median_observed_listing_duration_days: null },
        { company: "google", open: 183, opened: 183, reposted: 2, closed: 1, median_days_open: 0, median_observed_listing_duration_days: null },
      ],
    });

    render(<VelocityPanel days={30} />);

    const hero = await screen.findByRole("heading", { level: 2, name: /opened/ });
    expect(hero).toHaveTextContent("733 opened");

    // Openings and closings are the window's motion. An edit to a posting and
    // the difference of the two answer nothing a reader acts on: no Updated
    // tile or column, no net flow, no flow chart.
    expect(screen.getAllByText("Opened").length).toBeGreaterThan(0);
    expect(screen.queryByText("Updated")).toBeNull();
    expect(screen.queryByText("Net flow")).toBeNull();
    expect(screen.queryByRole("img")).toBeNull();

    // Activity table: one row per company with its lifecycle counts.
    const appleRow = screen.getByRole("table") &&
      within(screen.getByRole("table")).getByText("Apple").closest("tr")!;
    // Company · Open · Opened · Closed, one row per company; no company has
    // a time posted yet, so that column is not drawn.
    expect(within(appleRow as HTMLElement).getAllByRole("cell").map((c) => c.textContent)).toEqual([
      "Apple", "392", "392", "0",
    ]);
    expect(within(screen.getByRole("table")).queryByText("Time posted")).toBeNull();

    // Aging: the current single band holds all open roles.
    const ageRow = screen.getByText("< 1 week").closest(".bar-row")!;
    expect(within(ageRow as HTMLElement).getByText("732")).toBeInTheDocument();
  });

  it("flags the observed duration as accruing when few roles have closed", async () => {
    mock({
      days: 30,
      since: null,
      kpis: {
        open_total: 732, already_listed: 0, age_unknown: 0, closed_unknown: 3,
        opened: 733,
        reposted: 12,
        closed: 4,
        median_days_open: 0,
        median_observed_listing_duration_days: null,
        closed_sample: 1,
        employer_dated_share: 0.7,
        closed_employer_dated_share: 1,
      },
      aging: AGING,
      posted: AGING,
      by_company: [
        { company: "apple", open: 392, opened: 392, reposted: 2, closed: 0, median_days_open: 0, median_observed_listing_duration_days: null },
      ],
    });

    render(<VelocityPanel days={30} />);
    // One role in the singular; the closings with no known start are counted
    // beside it, so the two add up to the Closed tile.
    expect(await screen.findByText("Fills in once 5 closed roles have a known start. 1 has so far.")).toBeInTheDocument();
    const postedPanel = screen.getByRole("heading", { name: "How long postings stay up" }).closest(".panel") as HTMLElement;
    expect(within(postedPanel).getByText(/Time posted unknown: 3/)).toBeInTheDocument();
  });

  it("reads the measure, and never claims the role was filled", async () => {
    // A "time to fill" heading would assert a hire nobody observed.
    mock({
      days: 0,
      since: null,
      kpis: {
        open_total: 500, already_listed: 0, age_unknown: 0, closed_unknown: 0,
        opened: 900,
        reposted: 12,
        closed: 40,
        median_days_open: 12,
        median_observed_listing_duration_days: 14,
        closed_sample: 40,
        employer_dated_share: 0.7,
        closed_employer_dated_share: 0.75,
      },
      aging: AGING,
      posted: AGING,
      by_company: [
        { company: "google", open: 180, opened: 200, reposted: 2, closed: 22, median_days_open: 11, median_observed_listing_duration_days: 12 },
      ],
    });

    render(<VelocityPanel days={0} />);

    await screen.findByRole("heading", { level: 2, name: /opened/ });
    expect(document.querySelector(".cockpit-lead p")!.textContent).toContain(
      "14d median time posted",
    );
    expect(screen.queryByText(/have so far/i)).not.toBeInTheDocument();
    expect(document.body.textContent).not.toMatch(/to fill/i);
  });

  it("renders per-company time-posted bars once closures accrue", async () => {
    mock({
      days: 0,
      since: null,
      kpis: {
        open_total: 500, already_listed: 0, age_unknown: 0, closed_unknown: 0,
        opened: 900,
        reposted: 12,
        closed: 40,
        median_days_open: 12,
        median_observed_listing_duration_days: 14,
        closed_sample: 40,
        employer_dated_share: 0.7,
        closed_employer_dated_share: 0.75,
      },
      aging: AGING,
      posted: AGING,
      by_company: [
        { company: "google", open: 180, opened: 200, reposted: 2, closed: 22, median_days_open: 11, median_observed_listing_duration_days: 12 },
        { company: "openai", open: 60, opened: 90, reposted: 2, closed: 8, median_days_open: 9, median_observed_listing_duration_days: 20 },
      ],
    });

    render(<VelocityPanel days={0} />);

    // No accruing note this time.
    expect(await screen.findByRole("heading", { level: 2, name: /opened/ })).toHaveTextContent("900 opened");
    expect(screen.queryByText(/have so far/i)).not.toBeInTheDocument();

    // Each company's median time posted is a column of the one company table.
    const googleRow = within(screen.getByRole("table")).getByText("Google").closest("tr")!;
    expect(within(googleRow as HTMLElement).getByText("12d")).toBeInTheDocument();
    // The posted distribution draws the bands it was handed.
    const postedPanel = screen.getByRole("heading", { name: "How long postings stay up" }).closest(".panel")!;
    expect(within(postedPanel as HTMLElement).getByText("< 1 week")).toBeInTheDocument();
  });

  /* Under each chart, one plain line: the clock the bands count by. Never a
     warning box, and no employer-dated share beside a count of unknown ages. */
  it("says in one plain line what the age bands count from", async () => {
    mock({
      days: 0,
      since: null,
      kpis: {
        open_total: 658, already_listed: 0, age_unknown: 18, closed_unknown: 0, opened: 900, reposted: 12, closed: 40,
        median_days_open: 12, employer_dated_share: 466 / 640,
        median_observed_listing_duration_days: 14, closed_sample: 40, closed_employer_dated_share: 0.75,
      },
      aging: AGING,
      posted: AGING,
      by_company: [],
    });
    render(<VelocityPanel days={0} />);
    await screen.findByRole("heading", { level: 2, name: /opened/ });
    const agePanel = screen.getByRole("heading", { name: "Age of open roles" }).closest(".panel") as HTMLElement;
    expect(agePanel.querySelector(".vel-basis")).toHaveTextContent("Counted from when each role was first listed. Age unknown: 18");
    expect(agePanel.querySelectorAll("p")).toHaveLength(1);
    expect(screen.queryByText(/dated by the employer/)).toBeNull();
  });

  it("draws each company's open-roles bar from its open roles, the number printed beside it", async () => {
    // Amazon has fewer open roles but more opened ones than Google: a width
    // read off `opened` (797 vs 295) beside a label printing `open` would draw
    // the smaller number as the longer bar. A bar and its number are one fact.
    const company = (name: string, open: number, opened: number) => ({
      company: name, open, opened, reposted: 0, closed: 0,
      median_days_open: 0, median_observed_listing_duration_days: null,
    });
    mock({
      days: 30,
      since: null,
      kpis: {
        open_total: 155, already_listed: 0, age_unknown: 0, closed_unknown: 0, opened: 1092, reposted: 0, closed: 0, median_days_open: 0,
        median_observed_listing_duration_days: null, closed_sample: 0, employer_dated_share: null,
        closed_employer_dated_share: null,
      },
      aging: AGING,
      posted: AGING,
      by_company: [company("amazon", 50, 797), company("google", 105, 295)],
    });
    render(<VelocityPanel days={30} />);
    const table = await screen.findByRole("table");
    const width = (name: string) => {
      const row = within(table).getByText(name).closest("tr") as HTMLElement;
      return parseFloat((row.querySelector(".bar-fill") as HTMLElement).style.width);
    };
    expect(width("Google")).toBe(100);
    expect(width("Amazon")).toBeCloseTo((50 / 105) * 100, 5);
  });

  it("names the roles already listed when found apart from the openings it counts", async () => {
    // A first read of a company, or a posting its employer dated well before
    // we saw it, was already listed: said, never counted as opened.
    mock({
      days: 30,
      since: null,
      kpis: {
        open_total: 3192, already_listed: 1867, age_unknown: 0, closed_unknown: 0, opened: 494, reposted: 0, closed: 217,
        median_days_open: 40, median_observed_listing_duration_days: null, closed_sample: 0,
        employer_dated_share: 0.94, closed_employer_dated_share: null,
      },
      aging: AGING,
      posted: AGING,
      by_company: [],
    });
    render(<VelocityPanel days={30} />);
    expect(await screen.findByRole("heading", { level: 2, name: "494 opened" })).toBeInTheDocument();
    expect(screen.getByText(/1,867 found already listed/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "What “found already listed” means" })).toHaveAccessibleDescription(
      "Already listed when first seen: on a company's first scan, or dated earlier by the employer.",
    );
  });

  /* A role with no knowable start is beside the bands, never in "< 1 week":
     the bands and the unknown line add up to every role the panel counts. */
  it("says how many ages are unknown under each distribution, and nothing when none are", async () => {
    const kpis = {
      open_total: 750, already_listed: 0, opened: 10, reposted: 0, closed: 48,
      median_days_open: 3, median_observed_listing_duration_days: 9, closed_sample: 40,
      employer_dated_share: 0.5, closed_employer_dated_share: 0.5,
    };
    mock({ days: 30, since: null, kpis: { ...kpis, age_unknown: 18, closed_unknown: 8 }, aging: AGING, posted: AGING, by_company: [] });
    const { unmount } = render(<VelocityPanel days={30} />);
    await screen.findByRole("heading", { level: 2, name: /opened/ });
    const agePanel = screen.getByRole("heading", { name: "Age of open roles" }).closest(".panel") as HTMLElement;
    expect(within(agePanel).getByText(/Age unknown: 18/)).toBeInTheDocument();
    expect(within(agePanel).getByRole("button", { name: "What “unknown” means" })).toHaveAccessibleDescription(
      "Found on a company's first scan, with no date from the employer.",
    );
    const postedPanel = screen.getByRole("heading", { name: "How long postings stay up" }).closest(".panel") as HTMLElement;
    expect(within(postedPanel).getByText(/Time posted unknown: 8/)).toBeInTheDocument();
    unmount();

    mock({ days: 30, since: null, kpis: { ...kpis, age_unknown: 0, closed_unknown: 0 }, aging: AGING, posted: AGING, by_company: [] });
    render(<VelocityPanel days={30} />);
    await screen.findByRole("heading", { level: 2, name: /opened/ });
    expect(screen.queryByText(/unknown:/)).toBeNull();
  });

  it("leaves a company's time posted blank below five once another company has one, and says so where the column is explained", async () => {
    mock({
      days: 30,
      since: null,
      kpis: {
        open_total: 10, already_listed: 0, age_unknown: 0, closed_unknown: 0, opened: 4, reposted: 0, closed: 9,
        median_days_open: 3, median_observed_listing_duration_days: 9, closed_sample: 9,
        employer_dated_share: 0.5, closed_employer_dated_share: 0.5,
      },
      aging: AGING,
      posted: AGING,
      by_company: [
        { company: "google", open: 6, opened: 3, reposted: 0, closed: 4, median_days_open: 2, median_observed_listing_duration_days: null },
        { company: "openai", open: 4, opened: 1, reposted: 0, closed: 5, median_days_open: 2, median_observed_listing_duration_days: 9 },
      ],
    });
    render(<VelocityPanel days={30} />);
    const table = await screen.findByRole("table");
    const row = within(table).getByText("Google").closest("tr") as HTMLElement;
    expect(within(row).getAllByRole("cell").map((c) => c.textContent)).toEqual(["Google", "6", "3", "4", ""]);
    const tip = within(table).getByRole("button", { name: "What “Time posted” measures" });
    expect(tip).toHaveAccessibleDescription("Days from first listed to closed. Needs 5 closed roles with a known start.");
  });
});

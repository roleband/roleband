/**
 * The comp panel's job is to be honest about two different things at once: what kind of
 * money you get, and how sure we are of each part. These tests pin the honesty.
 *
 * The one that matters most: an `unclear` basis must NOT be split. Anthropic states a
 * figure and never says whether it is base or total; a panel that confidently breaks it
 * into cash/bonus/equity would be inventing a fact the posting does not state.
 */
import { calendarDay } from "../../copy/format";
import { render, screen, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it } from "vitest";

import type { Job, JobCompPackage } from "../../api";
import JobCompPanel from "./JobCompPanel";
import { compPackageFixture, jobFixture } from "../../test/fixtures";
import { msg } from "../../test/msg";
import { activate } from "../../copy/activate";

/** `null` is a row with no package at all — a list row, which never carries one.
 *  The detail route itself always sends an object. */
function withPackage(pkg: JobCompPackage | null): Job {
  return pkg === null ? { ...jobFixture } : { ...jobFixture, comp_package: pkg };
}

// Google job 879: base is stated, and so is the 25% bonus target. Built on the
// complete fixture, so keys this case is not about hold what the route sends.
const GOOGLE: JobCompPackage = compPackageFixture({
  state: "band",
  basis: "base",
  currency: "USD",
  pay_period: "year",
  stated: { low: 240000, high: 334000 },
  bonus_pct: 0.25,
  components: [
    { kind: "base", low: 240000, high: 334000, provenance: "stated" },
    { kind: "bonus", low: 60000, high: 83500, provenance: "stated" },
    { kind: "equity", low: 292289, high: 406769, provenance: "estimated" },
  ],
  total: { low: 592289, high: 824269, provenance: "estimated" },
  estimate: { low: 391162, median: 460191, high: 529219, provenance: "Google L6 estimated median" },
  split_source: "cross_family",
  no_split_reason: null,
  snippet: "US: $240000 - $334000 (USD) + 25% bonus target + equity",
  confidence: "high",
});

// Anthropic job 1: a stated figure whose meaning the employer withheld.
const ANTHROPIC: JobCompPackage = compPackageFixture({
  state: "band",
  basis: "unclear",
  currency: "USD",
  pay_period: "year",
  stated: { low: 210000, high: 260000 },
  bonus_pct: null,
  components: [],
  total: null,
  estimate: { low: 478826, median: 563325, high: 647823, provenance: "Anthropic Senior estimated median" },
  split_source: "measured",
  no_split_reason: "basis_unclear",
  snippet: "Annual Salary: $210,000—$260,000 USD",
  confidence: "high",
});

const NETFLIX: JobCompPackage = {
  ...ANTHROPIC,
  basis: "total",
  stated: { low: 440000, high: 725000 },
  total: { low: 440000, high: 725000, provenance: "stated" },
  estimate: { low: 400000, median: 500000, high: 600000, provenance: "Netflix Staff estimated median" },
  no_split_reason: "employee_election",
  snippet: "The range for this role is $440,000.00 - $725,000.00.",
};

describe("JobCompPanel", () => {
  // The panel is there to be read: nothing in it leads off the posting, for a
  // package it splits or one it does not.
  it.each([
    ["a split yearly package", GOOGLE],
    ["a figure it does not split", NETFLIX],
  ] as const)("holds no link out of the posting: %s", (_name, pkg) => {
    render(<JobCompPanel job={withPackage(pkg)} />, { wrapper: MemoryRouter });
    expect(screen.queryAllByRole("link")).toHaveLength(0);
    expect(screen.queryByText(/offer/i)).toBeNull();
  });

  /* The split is only ever drawn for a yearly band (comp_package.py refuses to
     split an hourly or monthly rate), so every figure in the legend is a year's
     money. A note under one that names a shorter period reads as the rate
     itself: "$240K–$334K / cash, every month". What sets base apart from the
     two beside it is that it is not conditional, so that is what it says. */
  it("says what base is, and names no pay period beside a year's figure", () => {
    render(<JobCompPanel job={withPackage(GOOGLE)} />, { wrapper: MemoryRouter });

    const legend = document.querySelector(".pkg-legend") as HTMLElement;
    const rows = [...legend.querySelectorAll<HTMLElement>(".pkg-leg")];
    const row = (name: string) => rows.find((one) => one.textContent?.startsWith(name))!;
    expect(row(msg("role-job-comp-panel-base")).querySelector(".pkg-leg-hint"))
      .toHaveTextContent(msg("role-job-comp-panel-guaranteed-cash"));
    // Equity's own note may say "per year"; none of them may name a shorter one.
    for (const one of rows) {
      const hint = one.querySelector(".pkg-leg-hint")!.textContent ?? "";
      expect(hint, `${one.textContent?.slice(0, 6)} names no pay cadence`).not.toMatch(/month|week|hour|day|fortnight/i);
    }
  });

  it("labels the employer-stated base as stated and the equity as estimated", () => {
    render(<JobCompPanel job={withPackage(GOOGLE)} />, { wrapper: MemoryRouter });

    // Which part of the total is certain, named with its own figure, under
    // the headline: the row holds the big figure apart from the bar.
    const statedLine = screen.getByTestId("pkg-stated-base");
    expect(statedLine).toHaveTextContent(msg("role-job-comp-panel-base"));
    expect(statedLine).toHaveTextContent("$240K–$334K");
    // It wears the card's ink for the employer's own numbers, not the muted one,
    // and carries what the headline counts for a reader who needs it.
    expect(statedLine.querySelector("svg"), "a mark, not words alone").toBeInTheDocument();
    expect(within(statedLine).getByRole("button", { name: msg("role-job-comp-panel-about-base-salary") })).toBeInTheDocument();
    expect(screen.queryByText(/of it is base salary/)).not.toBeInTheDocument();
    // Twice on purpose, and only here: the certain-pay row under the headline
    // and the breakdown's own base row. The headline itself is our estimate,
    // so neither repeats it.
    expect(screen.getAllByText("$240K–$334K")).toHaveLength(2);
    expect(within(statedLine).getByText("$240K–$334K")).toBeInTheDocument();
    expect(within(document.querySelector(".pkg-legend") as HTMLElement).getByText("$240K–$334K")).toBeInTheDocument();

    // Every component carries its own provenance, and they are not all the same.
    expect(screen.getAllByText("stated").length).toBeGreaterThanOrEqual(2); // base + bonus
    expect(screen.getAllByText("estimated").length).toBeGreaterThanOrEqual(1); // equity
  });

  it("says the bonus percentage came from the posting", () => {
    render(<JobCompPanel job={withPackage(GOOGLE)} />, { wrapper: MemoryRouter });
    expect(screen.getByText("25% of base, stated")).toBeInTheDocument();
  });

  it("refuses to split a band whose basis the employer never stated", () => {
    render(<JobCompPanel job={withPackage(ANTHROPIC)} />, { wrapper: MemoryRouter });

    // The sentence alone: no tag says it again in two words.
    const note = screen.getByTestId("pkg-no-split");
    expect(note).toHaveTextContent(msg("role-job-comp-panel-the-posting-states-this-figure"));
    expect(note.querySelector(".pkg-tag")).toBeNull();
    expect(note).not.toHaveTextContent(/basis not stated|isn't split/);
    // ...and it must not have invented a breakdown to fill the bar.
    expect(screen.queryByText("Base")).not.toBeInTheDocument();
    expect(screen.queryByText("Equity")).not.toBeInTheDocument();
    // The employer's figure is the headline, and our estimate is nowhere on
    // the card: not above it, and not repeated in a line under it.
    expect(document.querySelector(".pkg-head .big")).toHaveTextContent("$210K–$260K");
    expect(screen.queryByText(/estimate of total compensation/i)).not.toBeInTheDocument();
    expect(document.body).not.toHaveTextContent("$479K");
  });

  // A level we cannot place: the posted base stands, nothing is built on the guess.
  const UNPLACED: JobCompPackage = compPackageFixture({
    state: "band",
    basis: "base",
    currency: "USD",
    pay_period: "year",
    stated: { low: 151200, high: 223200 },
    // The employer's base, stated, with nothing built on the guessed level.
    components: [{ kind: "base", low: 151200, high: 223200, provenance: "stated" }],
    total: null,
    estimate: null,
    split_source: null,
    no_split_reason: "level_unplaced",
    snippet: "$151,200 - $223,200 base",
    confidence: "high",
  });

  it("draws the stated base as the bar's one segment, and models nothing on it", () => {
    const { container } = render(
      <JobCompPanel job={{ ...withPackage(UNPLACED), level_basis: "unmapped" }} />,
      { wrapper: MemoryRouter },
    );
    // The bar is there, with a single stated base segment at full width.
    const segments = container.querySelectorAll(".pkg-seg");
    expect(segments).toHaveLength(1);
    expect(segments[0]).toHaveClass("pkg-base");
    expect(segments[0]).not.toHaveClass("pkg-est");
    expect((segments[0] as HTMLElement).style.width).toBe("100%");
    // Nothing modelled: no bonus, no equity, no total.
    expect(screen.queryByText(msg("role-job-comp-panel-bonus"))).not.toBeInTheDocument();
    expect(screen.queryByText(msg("role-job-comp-panel-equity"))).not.toBeInTheDocument();
    // The employer's figure IS the headline here, so the certain-pay row and
    // the box below it both stay away: neither may print it a second time.
    expect(container.querySelector(".big")).toHaveTextContent("$151K–$223K");
    expect(container.querySelector(".pkg-leg-n")).toHaveTextContent("$151K–$223K");
    expect(screen.queryByTestId("pkg-stated-base")).toBeNull();
  });

  // A level RoleBand cannot place is about the app, not the job: the posted
  // figure stands, and nothing says what was not computed.
  it.each(["unmapped", "none"] as const)("says nothing about a level it cannot place (%s)", (basis) => {
    render(<JobCompPanel job={{ ...withPackage(UNPLACED), level_basis: basis }} />, { wrapper: MemoryRouter });
    expect(screen.getAllByText("$151K–$223K").length).toBeGreaterThan(0);
    expect(screen.queryByText("Equity")).not.toBeInTheDocument();
    expect(screen.queryByTestId("pkg-no-split")).toBeNull();
    expect(screen.queryByText(msg("taxonomy-level-not-mapped"))).toBeNull();
    expect(screen.queryByText(msg("taxonomy-level-not-stated"))).toBeNull();
    expect(document.body).not.toHaveTextContent(/level/i);
  });

  it("names the posting's own employer for an employee-selected mix, never a fixed one", () => {
    // The reason comes from the atlas (`equity_rule`), not from this panel: a
    // second employer with the rule is named as itself.
    render(<JobCompPanel job={{ ...withPackage(NETFLIX), company: "spotify" }} />, { wrapper: MemoryRouter });
    expect(
      screen.getByText(msg("role-job-comp-panel-states-this-as-total-annual", { company: "Spotify" })),
    ).toBeInTheDocument();
    expect(
      screen.queryByText(msg("role-job-comp-panel-states-this-as-total-annual", { company: "Netflix" })),
    ).not.toBeInTheDocument();
  });

  it("explains Netflix total compensation and employee-selected cash/options mix", () => {
    render(<JobCompPanel job={{ ...withPackage(NETFLIX), company: "netflix" }} />, { wrapper: MemoryRouter });
    expect(
      screen.getByText(msg("role-job-comp-panel-states-this-as-total-annual", { company: "Netflix" })),
    ).toBeInTheDocument();

    expect(screen.getByText("Posted total compensation")).toBeInTheDocument();
    // The sentence names the mix; no tag repeats it.
    expect(screen.getByTestId("pkg-no-split").querySelector(".pkg-tag")).toBeNull();
    expect(screen.queryByText(/never says whether it is base salary/)).not.toBeInTheDocument();
    expect(screen.queryByText("Base")).not.toBeInTheDocument();
  });

  it("leads with the employer's figure, never our estimate above it", () => {
    // The posting states $210K-$260K without saying what it covers, and we hold
    // an estimate of $479K-$648K: the employer's figure is the headline, under
    // the plain heading, and is written once.
    render(<JobCompPanel job={withPackage(ANTHROPIC)} />, { wrapper: MemoryRouter });

    expect(screen.getByText(msg("role-job-comp-panel-stated-by-the-employer"))).toBeInTheDocument();
    expect(screen.queryByText(msg("role-job-comp-panel-estimated-total-comp"))).not.toBeInTheDocument();
    expect(document.body.textContent?.match(/\$210K–\$260K/g)).toHaveLength(1);
  });

  it("flags a split borrowed from another job family instead of passing it off as measured", () => {
    render(<JobCompPanel job={withPackage(GOOGLE)} />, { wrapper: MemoryRouter });
    expect(screen.getByText("Split from another discipline")).toBeInTheDocument();
  });

  // With no figure found, the estimate stands alone whether the posting was
  // read or not: "estimated" already says the figure is ours, and a line
  // saying the posting has none would be false whenever the reader missed one.
  it("shows an estimate with no word about the posting's own pay, read or not", () => {
    const checked: JobCompPackage = {
      ...GOOGLE,
      state: "none_stated",
      basis: null,
      stated: null,
      bonus_pct: null,
      snippet: null,
      components: [
        { kind: "base", low: 160000, high: 200000, provenance: "estimated" },
        { kind: "equity", low: 200000, high: 260000, provenance: "estimated" },
      ],
    };
    for (const state of ["none_stated", "unchecked"] as const) {
      const { unmount } = render(<JobCompPanel job={withPackage({ ...checked, state })} />, { wrapper: MemoryRouter });
      expect(screen.getByText("Estimated total compensation")).toBeInTheDocument();
      expect(document.querySelector(".pkg-head .big")).toHaveTextContent("$592K–$824K");
      expect(document.querySelector(".pkg-note"), state).toBeNull();
      expect(document.body, state).not.toHaveTextContent(/no pay|no range|checked|posting/i);
      unmount();
    }
  });

  // $85-$110 an hour is $176,800-$228,800 over a full-time year. The package
  // carries that year as base: a rate says nothing about bonus or equity.
  const HOURLY: JobCompPackage = {
    ...ANTHROPIC,
    basis: "base",
    pay_period: "hour",
    stated: { low: 85, high: 110 },
    yearly_base: { low: 176800, high: 228800 },
    no_split_reason: "hourly",
  };

  it("shows an hourly rate as a full-time year of base salary, with the posted rate under it", () => {
    const { container } = render(<JobCompPanel job={withPackage(HOURLY)} />, { wrapper: MemoryRouter });
    expect(container.querySelector(".pkg-eyebrow")).toHaveTextContent(msg("role-job-comp-panel-base-from-posted-rate"));
    expect(container.querySelector(".pkg-head .big")).toHaveTextContent("$177K–$229K / yr");
    expect(screen.getByTestId("pkg-posted-rate")).toHaveTextContent(
      msg("role-job-comp-panel-posted-as", { choice: "hour", rate: "$85–$110 / hr" }),
    );
    // Base, never a total: no bonus, equity or total is drawn or named.
    expect(container).not.toHaveTextContent(/total compensation/i);
    expect(container.querySelector(".pkg-bar")).toBeNull();
    // The headline and the posted rate already say what the figure is.
    expect(screen.queryByTestId("pkg-no-split")).toBeNull();
  });

  it("never puts our estimate above an hourly rate, or anywhere on its card", () => {
    // The fixture holds an estimate of $479K-$648K a year.
    const { container } = render(<JobCompPanel job={withPackage(HOURLY)} />, { wrapper: MemoryRouter });
    expect(container).not.toHaveTextContent("$479K");
    expect(container).not.toHaveTextContent(/median/i);
  });

  // The server serves a period checked against the amount's size.
  it("shows a figure whose period it could not tell with no unit, and never as base", () => {
    const unclear: JobCompPackage = {
      ...ANTHROPIC,
      basis: "base",
      pay_period: "unclear",
      // A size both a month and a year can hold, with no word that settles it.
      stated: { low: 15000, high: 25000 },
      no_split_reason: "period_unclear",
      estimate: null,
      snippet: "Compensation: $15,000 - $25,000",
    };
    const { container } = render(<JobCompPanel job={withPackage(unclear)} />, { wrapper: MemoryRouter });
    const note = screen.getByTestId("pkg-no-split");
    expect(note).toHaveTextContent(msg("role-job-comp-panel-the-posting-s-wording-and"));
    expect(note.querySelector(".pkg-tag")).toBeNull();
    expect(container).not.toHaveTextContent("/ hr");
    expect(container).not.toHaveTextContent("/ yr");
    expect(screen.queryByText("Base")).not.toBeInTheDocument();
  });

  it("shows a monthly rate as twelve months of base, in the posting's own currency", () => {
    const monthly: JobCompPackage = {
      ...ANTHROPIC,
      basis: "base",
      currency: "EUR",
      pay_period: "month",
      stated: { low: 4500, high: 5500 },
      yearly_base: { low: 54000, high: 66000 },
      no_split_reason: "monthly",
    };
    const { container } = render(<JobCompPanel job={withPackage(monthly)} />, { wrapper: MemoryRouter });
    expect(container.querySelector(".pkg-head .big")).toHaveTextContent("€54K–€66K / yr");
    // The rate as posted, with no full-time hours: a month is a month.
    expect(screen.getByTestId("pkg-posted-rate")).toHaveTextContent(
      msg("role-job-comp-panel-posted-as", { choice: "other", rate: "€5K–€6K / mo" }),
    );
    expect(container).not.toHaveTextContent("$");
    expect(screen.queryByTestId("pkg-no-split")).toBeNull();
    expect(screen.queryByTestId("pkg-stated-base")).toBeNull();
  });

  it("writes a stated band in the posting's currency and one format", () => {
    const pounds: JobCompPackage = { ...GOOGLE, currency: "GBP" };
    render(<JobCompPanel job={withPackage(pounds)} />, { wrapper: MemoryRouter });
    const base = document.querySelector(".pkg-legend .pkg-leg-n");
    expect(base).toHaveTextContent(/^£\d+K–£\d+K/);
    expect(base).not.toHaveTextContent("$");
  });

  // The person knows their own minimum base, and the band beside it shows
  // where it falls: the card never restates the comparison, whatever it is.
  it.each(["clears", "straddles", "below"] as const)(
    "says nothing about the minimum base when the stated pay %s it",
    (verdict) => {
      const { container } = render(
        <JobCompPanel job={{ ...withPackage(GOOGLE), pay_floor_check: { verdict, amount: 250000, currency: "USD", basis: "base" } }} />,
        { wrapper: MemoryRouter },
      );
      expect(container).not.toHaveTextContent(/minimum base/i);
      expect(container).not.toHaveTextContent("$250K");
    },
  );

  it("says a band came from the posting's pay field", () => {
    const fromField = { ...withPackage({ ...GOOGLE, snippet: null }) };
    const job = { ...fromField, disclosed_comp: { ...fromField.disclosed_comp!, snippet: null, from_pay_field: true } };
    render(<JobCompPanel job={job} />, { wrapper: MemoryRouter });
    expect(screen.getByTestId("pkg-from-field")).toHaveTextContent("From the posting's compensation field, not its text.");
  });

  // The sentence the band was read from is the description's to show, in the
  // posting's own words; the panel carries the figures only.
  it("does not repeat the posting's pay sentence", () => {
    const { container } = render(<JobCompPanel job={withPackage(GOOGLE)} />, { wrapper: MemoryRouter });
    expect(GOOGLE.snippet).toBeTruthy();
    expect(container).not.toHaveTextContent(GOOGLE.snippet!);
    expect(container.querySelector("details, q")).toBeNull();
  });

  it("draws no panel rather than throwing when there is no package", () => {
    const { container } = render(<JobCompPanel job={withPackage(null)} />, { wrapper: MemoryRouter });
    expect(container).toBeEmptyDOMElement();
  });

  // No posted figure and no estimate: no panel, read for pay or not. A line
  // saying the posting has none would be the card's only content, and false
  // whenever the reader missed a figure the person can read below.
  it.each(["none_stated", "unchecked"] as const)(
    "draws no panel with no figure and no estimate (%s)",
    (state) => {
      const none: JobCompPackage = {
        ...GOOGLE, state, basis: null, stated: null, bonus_pct: null, snippet: null,
        components: [], total: null, estimate: null, split_source: null,
      };
      const { container } = render(<JobCompPanel job={withPackage(none)} />, { wrapper: MemoryRouter });
      expect(container).toBeEmptyDOMElement();
    },
  );

  it("a package with a figure is never the unknown panel", () => {
    render(<JobCompPanel job={withPackage(GOOGLE)} />, { wrapper: MemoryRouter });
    expect(screen.queryByTestId("pkg-unknown")).toBeNull();
  });

  // The company's offer rules say nothing about the figures above them: the
  // bonus and equity a panel shows come from the band's own shares whatever
  // the rules are, so a verified policy puts no sentence on the card.
  it("says nothing about how the company builds the offer, verified or not", () => {
    const verified: JobCompPackage = {
      ...GOOGLE,
      bonus_pct: null,
      policy: {
        verified: true,
        bonus_rule: "none",
        equity_rule: "tc_target_minus_base",
        vesting: "5/15/40/40",
        sign_on_bridges_vesting: true,
        base_cap_usd: 350000,
        annual_refresh: true,
        estimated: [],
        unknown: [],
      },
    };
    // The same package with no policy at all draws the same card, to the
    // character: a fact the panel does not read cannot reach the screen,
    // whatever sentence a future change might phrase it in.
    const { unmount } = render(<JobCompPanel job={withPackage(verified)} />, { wrapper: MemoryRouter });
    expect(document.querySelector(".pkg-head .big")).toHaveTextContent("$592K–$824K");
    const withPolicy = document.querySelector(".pkg-panel")!.textContent;
    unmount();

    render(<JobCompPanel job={withPackage({ ...verified, policy: null })} />, { wrapper: MemoryRouter });
    expect(document.querySelector(".pkg-panel")!.textContent).toBe(withPolicy);
  });

  // --- one headline, and no market median beside it (docs/pay.md) ----------------

  it("keeps the estimate without displaying source traceability", () => {
    render(<JobCompPanel job={withPackage({ ...GOOGLE, split_source: "heuristic",
      estimate: { ...GOOGLE.estimate!, provenance: "Google L6 reported median" },
    })} />, { wrapper: MemoryRouter });
    expect(screen.queryByText(/reported|Google L6/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/Splits from/)).not.toBeInTheDocument();
  });

  // The package total is a stated base plus a modelled bonus and grant; the
  // median is a reported total. They differ by a wide margin as ordinary
  // statistics, so no gap between them tells the person the offer is low.
  // GOOGLE's estimated total is $592K-$824K.
  it.each([
    ["sits wholly below it", 900000, "$900K", 0.79, "consistent"],
    ["tops out just under it", 830000, "$830K", 0.85, "consistent"],
    ["straddles it", 700000, "$700K", 1.01, "consistent"],
    ["sits above it", 460000, "$460K", 1.54, "consistent"],
    ["is far from it", 400000, "$400K", 1.71, "diverges"],
  ] as const)("names no market median when the total %s", (_name, median, shown, ratio, verdict) => {
    render(
      <JobCompPanel job={withPackage({
        ...GOOGLE,
        estimate: { ...GOOGLE.estimate!, median },
        market_gap: { ratio, verdict },
      })} />,
      { wrapper: MemoryRouter },
    );
    expect(screen.getByText("Estimated total compensation")).toBeInTheDocument();
    expect(document.body).not.toHaveTextContent(/market|median|×/i);
    expect(document.body).not.toHaveTextContent(shown);
  });

  // What the posting states is read first, then the cautions drawn from it,
  // then the bar.
  it("puts the stated base before the cautions, and the cautions before the bar", () => {
    render(
      <JobCompPanel
        job={withPackage({
          ...GOOGLE,
          split_source: "measured",
          reconciliation: { measured_base: 171000, ratio_high: 1.63, verdict: "stated_above_measured" },
        })}
      />,
      { wrapper: MemoryRouter },
    );
    const inOrder = [
      document.querySelector(".pkg-head .big"),
      screen.getByTestId("pkg-stated-base"),
      screen.getByTestId("pkg-reconciliation"),
      document.querySelector(".pkg-bar"),
    ];
    for (let i = 1; i < inOrder.length; i += 1) {
      expect(inOrder[i - 1]!.compareDocumentPosition(inOrder[i]!) & Node.DOCUMENT_POSITION_FOLLOWING, `step ${i} follows step ${i - 1}`).toBeTruthy();
    }
  });

  // --- posted band vs measured base (docs/pay.md) ---------------------------------

  it("cautions that the level may be wrong when the posted band sits above the measured base", () => {
    const job = withPackage({
      ...GOOGLE,
      split_source: "measured",
      reconciliation: { measured_base: 171000, ratio_high: 1.63, verdict: "stated_above_measured" },
    });
    render(<JobCompPanel job={job} />, { wrapper: MemoryRouter });

    const caution = screen.getByTestId("pkg-reconciliation");
    expect(caution).toHaveTextContent(/The posted range sits well above/);
    expect(caution).toHaveTextContent(/the level may be higher/);
    // The badge still says WHERE the ratios came from (a fact that must not be
    // rewritten), but it does not read as confident.
    const badge = screen.getByText("Measured split");
    expect(badge).toHaveClass("split-src-suspect");
    // Its help mark says why, in the doubting sentence rather than the plain one.
    const why = msg("role-job-comp-panel-this-company-s-real-base");
    expect(screen.getByRole("button", { name: msg("role-job-comp-panel-about-the-split") })).toHaveAccessibleDescription(
      msg("role-job-comp-panel-the-posted-band-does-not", { sPLIT_TITLE: why }),
    );
  });

  it("cautions in the other direction too", () => {
    const job = withPackage({
      ...GOOGLE,
      split_source: "measured",
      reconciliation: { measured_base: 400000, ratio_high: 0.6, verdict: "stated_below_measured" },
    });
    render(<JobCompPanel job={job} />, { wrapper: MemoryRouter });

    expect(screen.getByTestId("pkg-reconciliation")).toHaveTextContent(/the level may be lower/);
  });

  it("says nothing when the posted band and the measured base agree", () => {
    const job = withPackage({
      ...GOOGLE,
      split_source: "measured",
      reconciliation: { measured_base: 272333, ratio_high: 1.23, verdict: "consistent" },
    });
    render(<JobCompPanel job={job} />, { wrapper: MemoryRouter });

    expect(screen.queryByTestId("pkg-reconciliation")).not.toBeInTheDocument();
    expect(screen.getByText("Measured split")).not.toHaveClass("split-src-suspect");
    expect(screen.getByRole("button", { name: msg("role-job-comp-panel-about-the-split") })).toHaveAccessibleDescription(
      msg("role-job-comp-panel-this-company-s-real-base"),
    );
  });

  it("says nothing when there is no measurement to reconcile against", () => {
    const job = withPackage({
      ...GOOGLE,
      reconciliation: { measured_base: null, ratio_high: null, verdict: null },
    });
    render(<JobCompPanel job={job} />, { wrapper: MemoryRouter });

    expect(screen.queryByTestId("pkg-reconciliation")).not.toBeInTheDocument();
  });
});

describe("a base-only estimate", () => {
  const BASE_ONLY: JobCompPackage = compPackageFixture({
    state: "none_stated",
    components: [{ kind: "base", low: 170000, high: 230000, provenance: "estimated" }],
    total: null,
    estimate: null,
    split_source: null,
    base_estimate: { low: 170000, median: 200000, high: 230000, provider: "builtin", as_of: null },
  });

  // Read for pay or not, the one line says what the figure leaves out, and
  // nothing about the posting's own pay.
  it.each([
    ["none_stated", null],
    ["unchecked", "heuristic"],
  ] as const)("shows the base once, and says only that bonus and equity are unknown (%s)", (state, split_source) => {
    const { container } = render(
      <JobCompPanel job={withPackage({ ...BASE_ONLY, state, split_source })} />,
      { wrapper: MemoryRouter },
    );
    expect(screen.getByText(msg("role-job-comp-panel-estimated-base"))).toBeInTheDocument();
    expect(screen.getByTestId("comp-base-only")).toHaveTextContent(/^Bonus and equity unknown\.$/);
    // The one component is the headline: no bar, legend, split badge or second figure.
    expect(container.querySelector(".pkg-bar, .pkg-legend, .pkg-split")).toBeNull();
    expect(screen.getAllByText(/\$170K/)).toHaveLength(1);
    expect(container).not.toHaveTextContent(/no pay|no range|posting/i);
    expect(screen.queryByText(msg("role-job-comp-panel-estimated-total-comp"))).toBeNull();
  });
});

describe("a stated base outside US pay, with RoleBand answering", () => {
  it("is the headline, shown whole, and says nothing about where our split is measured", () => {
    const LONDON: JobCompPackage = compPackageFixture({
      state: "band", basis: "base", currency: "GBP", pay_period: "year",
      stated: { low: 90000, high: 130000 }, components: [], total: null, split_source: null,
      no_split_reason: "not_us_pay",
    });
    render(<JobCompPanel job={withPackage(LONDON)} />, { wrapper: MemoryRouter });
    // The employer's figure leads in its own currency, written once, whatever
    // we estimate in dollars.
    expect(document.querySelector(".pkg-head .big")).toHaveTextContent("£90K–£130K");
    expect(document.body.textContent?.match(/£90K/g)).toHaveLength(1);
    expect(screen.queryByText(msg("role-job-comp-panel-estimated-total-comp"))).toBeNull();
    // Our split is measured on US pay: that is about the app, so nothing says it.
    expect(screen.queryByTestId("pkg-no-split")).toBeNull();
    expect(document.body).not.toHaveTextContent(/US data|split/i);
    expect(document.querySelector(".pkg-bar")).toBeNull();
  });
});

describe("a stated yearly base that is all there is to show", () => {
  it("is the headline, named as base salary, and nothing under it repeats the figure", () => {
    const ONLY_BASE: JobCompPackage = compPackageFixture({
      state: "band", basis: "base", currency: "USD", pay_period: "year",
      stated: { low: 174000, high: 239000 }, components: [], total: null, estimate: null, base_estimate: null,
      split_source: null, no_split_reason: "level_unplaced",
    });
    render(<JobCompPanel job={withPackage(ONLY_BASE)} />, { wrapper: MemoryRouter });
    expect(screen.getByText(msg("role-job-comp-panel-base-stated-by-the-employer"))).toBeInTheDocument();
    expect(document.querySelector(".pkg-head .big")).toHaveTextContent("$174K–$239K");
    expect(document.body.textContent?.match(/\$174K/g)).toHaveLength(1);
    // The heading already says base: no line says it again, and no box holds the figure.
    expect(screen.queryByTestId("pkg-stated-base")).toBeNull();
    expect(screen.queryByTestId("pkg-no-split")).toBeNull();
  });

  it("writes a stated total once, though the package carries it twice", () => {
    // A stated total is the employer's own figure under the headline, and the
    // package also carries it as `stated`. The box below exists for a figure
    // the headline does NOT show, so here it must stay away.
    const { container } = render(
      <JobCompPanel job={{ ...withPackage(NETFLIX), company: "netflix" }} />,
      { wrapper: MemoryRouter },
    );
    expect(container.querySelector(".pkg-head .big")).toHaveTextContent("$440K–$725K");
    expect(container.textContent?.match(/\$440K–\$725K/g)).toHaveLength(1);
    // Why it is not split is still said.
    expect(screen.getByTestId("pkg-no-split")).toBeInTheDocument();
  });

  it("names a total the posting calls on-target earnings as base plus commission", () => {
    const OTE: JobCompPackage = compPackageFixture({
      state: "band", basis: "total", currency: "USD", pay_period: "year",
      stated: { low: 184000, high: 230000 }, components: [], total: { low: 184000, high: 230000, provenance: "stated" },
      estimate: null, split_source: null, no_split_reason: "total_compensation", on_target_earnings: true,
    });
    const { container } = render(<JobCompPanel job={withPackage(OTE)} />, { wrapper: MemoryRouter });
    expect(container.querySelector(".pkg-eyebrow")).toHaveTextContent(msg("role-job-comp-panel-on-target-earnings"));
    // Never total pay, and no equity drawn into it.
    expect(container).not.toHaveTextContent(/total compensation/i);
    expect(screen.queryByText(msg("role-job-comp-panel-equity"))).toBeNull();
    expect(screen.queryByTestId("pkg-no-split")).toBeNull();
  });

  it("a stated total the posting does not call on-target earnings stays total compensation", () => {
    render(<JobCompPanel job={withPackage({ ...NETFLIX, no_split_reason: "total_compensation", on_target_earnings: false })} />,
      { wrapper: MemoryRouter });
    expect(screen.getByText(msg("role-job-comp-panel-estimated-total-package", { choice: "yes" }))).toBeInTheDocument();
    expect(screen.queryByText(msg("role-job-comp-panel-on-target-earnings"))).toBeNull();
    // The headline says total compensation: no tag or sentence says it again.
    expect(screen.queryByTestId("pkg-no-split")).toBeNull();
    expect(document.body.textContent?.match(/total compensation/gi)).toHaveLength(1);
  });

  it("a figure whose kind the posting does not give keeps the plain heading", () => {
    const UNCLEAR: JobCompPackage = compPackageFixture({
      state: "band", basis: "unclear", currency: "USD", pay_period: "year",
      stated: { low: 210000, high: 260000 }, components: [], total: null, estimate: null, base_estimate: null,
      split_source: null, no_split_reason: "basis_unclear",
    });
    render(<JobCompPanel job={withPackage(UNCLEAR)} />, { wrapper: MemoryRouter });
    expect(screen.getByText(msg("role-job-comp-panel-stated-by-the-employer"))).toBeInTheDocument();
    expect(screen.queryByText(msg("role-job-comp-panel-base-stated-by-the-employer"))).toBeNull();
  });
});

describe("a plugin's figure with no split of its own", () => {
  const PLUGIN_TOTAL: JobCompPackage = compPackageFixture({
    state: "none_stated",
    components: [],
    total: null,
    estimate: { low: 793050, median: 933000, high: 1072950, provenance: "Google L7 estimated median" },
    split_source: null,
    no_split_reason: "plugin_without_split",
    policy: null,
  });

  it("shows the plugin's figure whole, with no bar, and no word about the split it lacks", () => {
    render(<JobCompPanel job={withPackage(PLUGIN_TOTAL)} />, { wrapper: MemoryRouter });
    expect(screen.getByText(msg("role-job-comp-panel-estimated-total-comp"))).toBeInTheDocument();
    expect(screen.queryByTestId("pkg-no-split")).toBeNull();
    // No segment of ours under it: no base, bonus or equity label anywhere.
    expect(screen.queryByText(msg("role-job-comp-panel-estimated-split"))).toBeNull();
    expect(document.querySelector(".pkg-bar")).toBeNull();
  });

  it("a company the plugin has not read says so, never 'no estimate' or a split not reported", () => {
    const unread = { plugin: "ladder", plugin_name: "Example ladder data", covered: false };
    const empty = { ...PLUGIN_TOTAL, estimate: null, no_split_reason: null };
    const { unmount } = render(<JobCompPanel job={{ ...withPackage(empty), pay_source: unread }} />, { wrapper: MemoryRouter });
    expect(screen.getByTestId("pkg-unknown")).toHaveTextContent(
      new RegExp(`^${msg("shared-pay-not-covered-hint", { plugin: "Example ladder data" }).replace(/[.*+?^${}()|[\]\\]/g, "\\$&")}$`),
    );
    unmount();

    render(<JobCompPanel job={{ ...withPackage({
      ...empty, state: "band", basis: "base", currency: "USD", pay_period: "year",
      stated: { low: 240000, high: 334000 }, no_split_reason: "plugin_not_covered",
    }), pay_source: unread }} />, { wrapper: MemoryRouter });
    // The sentence alone, with no tag that says it again.
    const note = screen.getByTestId("pkg-no-split");
    expect(note).toHaveTextContent(msg("shared-pay-not-covered-hint", { plugin: "Example ladder data" }));
    expect(note.querySelector(".pkg-tag")).toBeNull();
  });

  it("an employer's figure under a plugin leads, and no estimate is set beside it", () => {
    const plugin = { plugin: "ladder", plugin_name: "Example ladder data", covered: true };
    const stated = { ...PLUGIN_TOTAL, state: "band" as const, basis: "base" as const, currency: "USD",
                     pay_period: "year" as const, stated: { low: 240000, high: 334000 } };
    render(<JobCompPanel job={{ ...withPackage(stated), pay_source: plugin }} />, { wrapper: MemoryRouter });
    expect(document.querySelector(".pkg-head .big")).toHaveTextContent("$240K–$334K");
    expect(screen.queryByText(/estimate/i)).toBeNull();
    expect(document.body).not.toHaveTextContent("$793K");
  });

  // Negative control for the not-covered line: a plugin that has read the
  // company leaves nothing to explain, so a role with no figure has no panel.
  it("a company it has read with no figure for this role draws no panel", () => {
    const read = { plugin: "ladder", plugin_name: "Example ladder data", covered: true };
    const { container } = render(<JobCompPanel job={{ ...withPackage({ ...PLUGIN_TOTAL, estimate: null, no_split_reason: null }),
                                pay_source: read }} />, { wrapper: MemoryRouter });
    expect(container).toBeEmptyDOMElement();
  });

  it("a stated base under such a plugin is shown as the employer stated it, unsplit", () => {
    render(<JobCompPanel job={withPackage({
      ...PLUGIN_TOTAL, state: "band", basis: "base", currency: "USD", pay_period: "year",
      stated: { low: 240000, high: 334000 },
    })} />, { wrapper: MemoryRouter });
    expect(document.querySelector(".pkg-head .big")).toHaveTextContent("$240K–$334K");
    expect(screen.queryByTestId("pkg-no-split")).toBeNull();
  });
});

// --- where the split came from, named by its wire value ---------------------------------

describe("split source chip", () => {
  // Each value composes its own class, the one its rule paints
  // (design/dead-rules.test.ts holds every value to a rule).
  it.each(["measured", "cross_family", "heuristic"] as const)("a %s split wears split-src-%s", (source) => {
    render(<JobCompPanel job={withPackage({ ...GOOGLE, split_source: source })} />, { wrapper: MemoryRouter });
    const chip = document.querySelector(".split-src");
    expect(chip).not.toBeNull();
    expect(chip).toHaveClass(`split-src-${source}`);
  });
});

describe("who supplied the split", () => {
  const MEASURED = { ...GOOGLE, split_source: "measured" as const };

  it("names the plugin answering pay, and the date its rung is as of", () => {
    const job = { ...withPackage({ ...MEASURED, split_provider: "levels-plugin", split_as_of: "2026-10-01" }),
      pay_source: { ...jobFixture.pay_source!, plugin: "levels-plugin", plugin_name: "Levels", covered: true } };
    render(<JobCompPanel job={job} />, { wrapper: MemoryRouter });
    expect(screen.getByTestId("comp-split-from")).toHaveTextContent(`Split from Levels, as of ${calendarDay("2026-10-01")}.`);
  });

  it("names RoleBand's own data for a split of ours, without a date it does not have", () => {
    render(<JobCompPanel job={withPackage({ ...MEASURED, split_provider: "builtin", split_as_of: null })} />, { wrapper: MemoryRouter });
    expect(screen.getByTestId("comp-split-from")).toHaveTextContent("Split from built-in data.");
  });

  it("says nothing where no measured split was read", () => {
    render(<JobCompPanel job={withPackage({ ...MEASURED, split_provider: null, split_as_of: null })} />, { wrapper: MemoryRouter });
    expect(screen.queryByTestId("comp-split-from")).toBeNull();
  });
});

describe("the panel's own words, in the reader's language", () => {
  afterEach(() => activate("en"));

  it("tags each part stated or estimated in Spanish, in the legend and on the bar", async () => {
    await activate("es");
    render(<JobCompPanel job={withPackage(GOOGLE)} />, { wrapper: MemoryRouter });

    const legend = document.querySelector(".pkg-legend") as HTMLElement;
    expect(within(legend).getAllByText(msg("role-job-comp-panel-stated"))).toHaveLength(2); // base + bonus
    expect(within(legend).getAllByText(msg("role-job-comp-panel-estimated"))).toHaveLength(1); // equity
    expect(within(legend).queryByText("stated")).toBeNull();
    expect(within(legend).queryByText("estimated")).toBeNull();

    // The bar is read aloud and hovered: each part ends in the same word, never the API's code.
    const bar = screen.getByRole("img", { name: /;/ });
    const spoken = bar.getAttribute("aria-label") ?? "";
    expect(spoken.split("; ").map((part) => part.split(" ").pop())).toEqual([
      msg("role-job-comp-panel-stated"), msg("role-job-comp-panel-stated"), msg("role-job-comp-panel-estimated"),
    ]);
    const titles = [...bar.querySelectorAll(".pkg-seg")].map((seg) => seg.getAttribute("title") ?? "");
    expect(titles.map((title) => title.split(", ").pop())).toEqual([
      msg("role-job-comp-panel-stated"), msg("role-job-comp-panel-stated"), msg("role-job-comp-panel-estimated"),
    ]);
    expect(`${spoken} ${titles.join(" ")}`).not.toMatch(/\b(stated|estimated)\b/);
  });

  it("names an employee-selected mix in Spanish", async () => {
    await activate("es");
    render(<JobCompPanel job={{ ...withPackage(NETFLIX), company: "netflix" }} />, { wrapper: MemoryRouter });
    expect(screen.getByTestId("pkg-no-split")).toHaveTextContent(
      msg("role-job-comp-panel-states-this-as-total-annual", { company: "Netflix" }),
    );
    expect(screen.queryByText(/lets each person pick/)).toBeNull();
  });

  it("names the doubted level as the catalog writes it, never recased", () => {
    const job = withPackage({
      ...GOOGLE,
      split_source: "measured",
      reconciliation: { measured_base: 171000, ratio_high: 1.63, verdict: "stated_above_measured" },
    });
    render(<JobCompPanel job={{ ...job, level_band: "staff" }} />, { wrapper: MemoryRouter });
    expect(screen.getByTestId("pkg-reconciliation")).toHaveTextContent(
      msg("role-job-comp-panel-posted-band-sits-well-above", { band: msg("taxonomy-band-staff") }),
    );
  });
});

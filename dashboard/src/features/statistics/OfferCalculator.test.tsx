/* The offer on the Stock tab: one question at a time, then the offer year by
 * year with each answer as a chip to change. Every answer is kept through the
 * offer routes on this computer, never in the browser, and a rule the company
 * states is never asked. The routes are played by an in-memory store that
 * answers as the server does, so each test reads what would be kept. */
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { CompTrajectory, OfferAnswers, OfferDraft, OfferTerms, OfferTermsCompany, ValuationDraft } from "../../api";
import { api } from "../../api";
import { calendarDay, list, money } from "../../copy/format";
import { fmtComp } from "../../format";
import { msg } from "../../test/msg";
import { ToastProvider } from "../../ui/Toast";
import { StockTrajectoryPanel } from "./StockTrajectoryPanel";

vi.mock("../../api", () => ({
  api: {
    compTrajectory: vi.fn(),
    offerTerms: vi.fn(),
    offer: vi.fn(),
    saveOffer: vi.fn(),
    clearOffer: vi.fn(),
    saveValuation: vi.fn(),
    clearValuation: vi.fn(),
  },
}));

const terms = (over: Partial<OfferTermsCompany> & { company: string }): OfferTermsCompany => ({
  listed: true, ticker: null, equity_vehicle: "rsu", vesting: null, vesting_stated_by: null,
  bonus_rule: null, sign_on_bridges_vesting: false, quote: null, ...over,
});

const TERMS: OfferTerms = {
  feed_configured: false,
  companies: [
    terms({ company: "amazon", ticker: "AMZN", vesting: [5, 15, 40, 40], vesting_stated_by: "estimated", bonus_rule: "none", sign_on_bridges_vesting: true }),
    terms({ company: "microsoft", ticker: "MSFT", vesting: [25, 25, 25, 25], vesting_stated_by: "employer", bonus_rule: "pct_of_base" }),
    terms({ company: "netflix", ticker: "NFLX", equity_vehicle: "cash_election", bonus_rule: "none" }),
    terms({ company: "openai", listed: false, vesting: [25, 25, 25, 25], vesting_stated_by: "estimated", bonus_rule: "none" }),
    terms({ company: "anthropic", listed: false, bonus_rule: "none" }),
  ],
};

const pkg = (median_tc: number, equity: number, bonus: number) => ({
  count: 10, median_tc, equity, bonus, base: median_tc - equity - bonus, equity_pct: equity / median_tc,
  sources: { base: "posted", bonus: "company_rule", equity: "estimated" } as const,
});

const TRAJECTORY: CompTrajectory = {
  currency: "USD",
  overall: pkg(400_000, 160_000, 0),
  public: [{ company: "amazon", ticker: "AMZN", equity_vehicle: "rsu", vesting: "5/15/40/40", ...pkg(400_000, 160_000, 0) }],
  private: [{ company: "openai", equity_vehicle: null, vesting: "25/25/25/25", ...pkg(1_100_000, 550_000, 0) }],
  choice: [],
  set_apart: [],
};

const SAVED_AT = "2026-11-10T09:30:00+00:00";

/** What the offer routes keep, answered as the server answers. */
let kept: OfferAnswers;
const copy = (): OfferAnswers => structuredClone(kept);

const AMAZON_DONE: OfferDraft = {
  inputs: {
    company: "amazon", listed: true, base: 200_000, bonus_pct: 0, vehicle: "rsu", grant_unit: "dollars", grant: 400_000,
    strike: null, price: null, vesting: null, sign_on: [100_000, 80_000],
  },
  answered: ["company", "base", "stock", "vesting", "sign_on"],
  started_from: null,
};

const renderPanel = (entry: string | { pathname: string; state: unknown } = "/statistics/trajectory") =>
  render(<StockTrajectoryPanel />, {
    wrapper: ({ children }) => (
      <MemoryRouter initialEntries={[entry]}>
        <ToastProvider>{children}</ToastProvider>
      </MemoryRouter>
    ),
  });

const calculator = () => screen.getByTestId("traj-offer");
/** The first question, once the company list has loaded into it. */
const ready = async (company = "Amazon") => {
  await screen.findByTestId("traj-offer-question");
  await screen.findByRole("option", { name: company });
};
const question = () => screen.getByTestId("traj-offer-question");
const step = () => question().getAttribute("data-step");
const press = (name: string) => fireEvent.click(within(calculator()).getByRole("button", { name }));
const type = (label: string, value: string) =>
  fireEvent.change(within(calculator()).getByLabelText(label), { target: { value } });
const next = () => press(msg("insights-offer-next"));
const chip = (answer: string) => within(calculator()).getByRole("button", { name: msg("insights-offer-chip-edit", { answer }) });
const yearTotals = () => {
  fireEvent.click(within(calculator()).getByText(msg("insights-offer-show-table")));
  return within(screen.getByTestId("traj-offer-years")).getAllByRole("row").slice(1, 5)
    .map((row) => Array.from(row.querySelectorAll("td.traj-offer-total")).map((td) => td.textContent));
};
const comp = (n: number) => String(fmtComp(n));
const litDots = () => calculator().querySelectorAll(".traj-offer-dots [data-done]").length;
const offerKeysInBrowser = () =>
  [...Object.keys(window.localStorage), ...Object.keys(window.sessionStorage)].filter((k) => /offer|valuation/i.test(k));

describe("OfferCalculator", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    window.localStorage.clear();
    kept = { offer: null, valuations: {} };
    vi.mocked(api.compTrajectory).mockResolvedValue(TRAJECTORY);
    vi.mocked(api.offerTerms).mockResolvedValue(TERMS);
    vi.mocked(api.offer).mockImplementation(async () => copy());
    vi.mocked(api.saveOffer).mockImplementation(async (draft: OfferDraft) => {
      kept = { ...kept, offer: { ...structuredClone(draft), answered: [...new Set(draft.answered)], saved_at: SAVED_AT } };
      return copy();
    });
    vi.mocked(api.clearOffer).mockImplementation(async () => {
      kept = { ...kept, offer: null };
      return copy();
    });
    vi.mocked(api.saveValuation).mockImplementation(async (company: string, v: ValuationDraft) => {
      kept = { ...kept, valuations: { ...kept.valuations, [company]: { ...v, saved_at: SAVED_AT } } };
      return copy();
    });
    vi.mocked(api.clearValuation).mockImplementation(async (company: string) => {
      const { [company]: _gone, ...rest } = kept.valuations;
      kept = { ...kept, valuations: rest };
      return copy();
    });
  });
  afterEach(() => vi.restoreAllMocks());

  it("walks one question at a time, asks Amazon's schedule as yes or no, never its bonus, and shows each year after the move", async () => {
    renderPanel();
    await ready();
    expect(within(calculator()).getByRole("heading", { name: msg("insights-offer-start-title") })).toBeInTheDocument();
    expect(step()).toBe("company");

    // Next with nothing picked says what the question needs and stays.
    next();
    expect(within(calculator()).getByRole("alert")).toHaveTextContent(msg("insights-offer-need", { what: "company" }));
    expect(step()).toBe("company");

    press("Amazon");
    next();
    expect(step()).toBe("base");
    type(msg("insights-offer-q-base"), "200000");
    next();
    type(msg("insights-offer-q-stock", { vehicle: "rsu" }), "400000");
    next();

    // Amazon states its schedule: one press confirms it.
    expect(step()).toBe("vesting");
    expect(within(question()).getByRole("heading", {
      name: msg("insights-offer-q-vesting-stated", { schedule: list(["5", "15", "40", "40"]) }),
    })).toBeInTheDocument();
    press(msg("insights-offer-vesting-yes"));

    // No bonus question: Amazon pays none.
    expect(step()).toBe("sign_on");
    expect(within(question()).getByText(msg("insights-offer-sign-on-bridges"))).toBeInTheDocument();
    press(msg("insights-offer-sign-on-yes"));
    type(msg("insights-offer-sign-on", { year: 1 }), "100000");
    type(msg("insights-offer-sign-on", { year: 2 }), "80000");
    next();

    expect(screen.queryByTestId("traj-offer-question")).toBeNull();
    expect(within(calculator()).getByRole("heading", { name: msg("insights-offer-finished-title", { named: "yes", company: "Amazon" }) }))
      .toBeInTheDocument();
    // The no-bonus rule reads as a fact, not an answer to change.
    const rule = within(calculator()).getByText(msg("insights-offer-chip-bonus", { pct: 0 }));
    expect(rule).toHaveTextContent(msg("insights-offer-tag", { tag: "rule" }));
    expect(rule.closest("button")).toBeNull();
    expect(yearTotals()).toEqual([[comp(320_000)], [comp(340_000)], [comp(360_000)], [comp(360_000)]]);

    fireEvent.change(within(calculator()).getByLabelText(msg("insights-offer-move-aria", { listed: "yes" })), { target: { value: "20" } });
    // Only the equity moves: 20% of 20K, 60K, 160K, 160K.
    expect(yearTotals()).toEqual([
      [comp(320_000), comp(324_000)], [comp(340_000), comp(352_000)],
      [comp(360_000), comp(392_000)], [comp(360_000), comp(392_000)],
    ]);
    // One move for the whole tab: the hero's slider reads it too.
    expect(screen.getByLabelText(msg("insights-stock-trajectory-panel-stock-price-change-percent"))).toHaveValue("20");

    // Kept through the offer routes, as answered, and nowhere in the browser.
    await waitFor(() => expect(kept.offer?.answered).toEqual(["company", "base", "stock", "vesting", "sign_on"]));
    expect(kept.offer?.inputs).toMatchObject({ company: "amazon", base: 200_000, grant: 400_000, vesting: null, sign_on: [100_000, 80_000] });
    expect(offerKeysInBrowser()).toEqual([]);
    expect(within(calculator()).getByText(msg("insights-offer-entered", { date: calendarDay(SAVED_AT) }))).toBeInTheDocument();
  });

  it("assumes an even schedule where the company states none, and says so on its chip", async () => {
    renderPanel();
    await ready();
    fireEvent.change(within(calculator()).getByRole("combobox", { name: msg("insights-offer-all-companies") }), { target: { value: "anthropic" } });
    next();
    type(msg("insights-offer-q-base"), "150000");
    next();
    type(msg("insights-offer-q-stock", { vehicle: "rsu" }), "100000");
    next();
    // A private company asks its valuation, and not knowing it is an answer.
    expect(step()).toBe("valuation");
    press(msg("insights-offer-dont-know"));
    expect(step()).toBe("vesting");
    expect(within(question()).getByRole("heading", { name: msg("insights-offer-q-vesting") })).toBeInTheDocument();
    next();
    press(msg("insights-offer-sign-on-no"));

    const vesting = chip(msg("insights-offer-chip-vesting", { schedule: "25 / 25 / 25 / 25" }));
    expect(vesting).toHaveTextContent(msg("insights-offer-tag", { tag: "assumed" }));
    // Its equity can't be sold, and counts at the value it was granted at.
    expect(within(calculator()).getByText(`${msg("insights-offer-private")} ${msg("insights-offer-valuation-none")}`)).toBeInTheDocument();
    expect(within(calculator()).getByLabelText(msg("insights-offer-move-aria", { listed: "no" }))).toBeInTheDocument();
    await waitFor(() => expect(kept.offer?.inputs.vesting).toBeNull());
    expect(kept.valuations).toEqual({});
  });

  it("asks only base, stock and sign-on where each person picks their own cash and stock split", async () => {
    renderPanel();
    await ready();
    fireEvent.change(within(calculator()).getByRole("combobox", { name: msg("insights-offer-all-companies") }), { target: { value: "netflix" } });
    next();
    type(msg("insights-offer-q-base"), "300000");
    next();
    expect(within(question()).getByRole("heading", { name: msg("insights-offer-q-stock", { vehicle: "cash" }) })).toBeInTheDocument();
    // The split is in dollars: no choice of shares.
    expect(within(question()).queryByRole("button", { name: msg("insights-offer-grant-unit-option", { unit: "shares" }) })).toBeNull();
    type(msg("insights-offer-q-stock", { vehicle: "cash" }), "200000");
    next();
    expect(step()).toBe("sign_on");
  });

  it("changes one answer from its chip and goes back to the offer", async () => {
    kept = { offer: { ...AMAZON_DONE, saved_at: SAVED_AT }, valuations: {} };
    renderPanel();
    fireEvent.click(await screen.findByRole("button", { name: msg("insights-offer-chip-edit", { answer: msg("insights-offer-chip-base", { amount: comp(200_000) }) }) }));
    expect(step()).toBe("base");
    // A change is not a walk: no progress, and Cancel rather than Back.
    expect(within(question()).queryByRole("button", { name: msg("insights-offer-back") })).toBeNull();
    type(msg("insights-offer-q-base"), "250000");
    press(msg("insights-offer-done"));

    expect(screen.queryByTestId("traj-offer-question")).toBeNull();
    expect(chip(msg("insights-offer-chip-base", { amount: comp(250_000) }))).toBeInTheDocument();
    await waitFor(() => expect(kept.offer?.inputs.base).toBe(250_000));
    expect(kept.offer?.answered).toEqual(AMAZON_DONE.answered);
  });

  it("folds an unfinished offer to one line, and Continue opens the first open question", async () => {
    kept = { offer: { ...AMAZON_DONE, inputs: { ...AMAZON_DONE.inputs, grant: null }, answered: ["company", "base"], saved_at: SAVED_AT }, valuations: {} };
    renderPanel();
    expect(await screen.findByText(msg("insights-offer-unfinished", { answered: 2, total: 4 }))).toBeInTheDocument();
    expect(screen.queryByTestId("traj-offer-question")).toBeNull();
    // One lit dot for each answer, as many as the line says.
    expect(litDots()).toBe(2);
    press(msg("insights-offer-continue"));
    expect(step()).toBe("stock");
    // Walking, the question on screen is lit too.
    expect(litDots()).toBe(3);
    press(msg("insights-offer-later"));
    expect(screen.getByText(msg("insights-offer-unfinished", { answered: 2, total: 4 }))).toBeInTheDocument();
  });

  it("forgets the offer on Clear, starts again at the first question, and Undo in the toast puts it back", async () => {
    kept = { offer: { ...AMAZON_DONE, saved_at: SAVED_AT }, valuations: {} };
    renderPanel();
    const title = { name: msg("insights-offer-finished-title", { named: "yes", company: "Amazon" }) };
    await screen.findByRole("heading", title);
    press(msg("insights-offer-clear"));
    expect(step()).toBe("company");
    await waitFor(() => expect(kept.offer).toBeNull());
    expect(api.clearOffer).toHaveBeenCalledTimes(1);

    expect(screen.getByText(msg("insights-offer-cleared"))).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: msg("insights-offer-undo") }));
    expect(within(calculator()).getByRole("heading", title)).toBeInTheDocument();
    await waitFor(() => expect(kept.offer?.answered).toEqual(AMAZON_DONE.answered));
    expect(kept.offer?.inputs).toEqual(AMAZON_DONE.inputs);
  });

  it("reads a company not on the list as one answer, listed or private", async () => {
    kept = {
      offer: { ...AMAZON_DONE, inputs: { ...AMAZON_DONE.inputs, company: "", listed: false }, answered: ["company", "base", "stock", "vesting", "bonus", "sign_on"], saved_at: SAVED_AT },
      valuations: {},
    };
    renderPanel();
    expect(await screen.findByRole("button", { name: msg("insights-offer-chip-edit", { answer: msg("insights-offer-chip-another", { listed: "no" }) }) }))
      .toBeInTheDocument();
  });

  it("shows the price per share typed for a private company not on the list, and says when there is none", async () => {
    const typedIn = {
      ...AMAZON_DONE,
      inputs: { ...AMAZON_DONE.inputs, company: "", listed: false, grant_unit: "shares" as const, grant: 1_000, price: 50 },
      answered: ["company", "base", "stock", "price", "vesting", "bonus", "sign_on"] as OfferDraft["answered"],
    };
    kept = { offer: { ...typedIn, saved_at: SAVED_AT }, valuations: {} };
    const { unmount } = renderPanel();
    expect(await screen.findByRole("button", { name: msg("insights-offer-chip-edit", { answer: msg("insights-offer-chip-price", { kind: "some", amount: money(50) }) }) }))
      .toBeInTheDocument();
    unmount();

    kept = { offer: { ...typedIn, inputs: { ...typedIn.inputs, price: null }, saved_at: SAVED_AT }, valuations: {} };
    renderPanel();
    expect(await screen.findByRole("button", { name: msg("insights-offer-chip-edit", { answer: msg("insights-offer-chip-price", { kind: "none", amount: "" }) }) }))
      .toBeInTheDocument();
  });

  it("closes a question left open when an offer starts from a row, and keeps the started figures", async () => {
    kept = { offer: { ...AMAZON_DONE, inputs: { ...AMAZON_DONE.inputs, base: 123_000 }, saved_at: SAVED_AT }, valuations: {} };
    renderPanel();
    fireEvent.click(await screen.findByRole("button", { name: msg("insights-offer-chip-edit", { answer: msg("insights-offer-chip-base", { amount: comp(123_000) }) }) }));
    type(msg("insights-offer-q-base"), "999000");

    const row = within(screen.getByTestId("traj-public")).getByRole("row", { name: /Amazon/ });
    fireEvent.click(within(row).getByRole("button", { name: msg("insights-offer-start-aria", { company: "Amazon" }) }));

    // The open question was about the earlier offer: it closes, unsaved.
    expect(screen.queryByTestId("traj-offer-question")).toBeNull();
    expect(chip(msg("insights-offer-chip-base", { amount: comp(240_000) }))).toHaveTextContent(msg("insights-offer-tag", { tag: "typical" }));
    await waitFor(() => expect(kept.offer?.started_from).toEqual({ company: "amazon", title: null }));
    expect(kept.offer?.inputs.base).toBe(240_000);
    expect(within(calculator()).getByRole("button", { name: msg("insights-offer-undo") })).toBeInTheDocument();
  });

  it("starts from a company's row with typical figures, and Undo puts the earlier offer back", async () => {
    kept = { offer: { ...AMAZON_DONE, inputs: { ...AMAZON_DONE.inputs, base: 123_000 }, saved_at: SAVED_AT }, valuations: {} };
    renderPanel();
    const row = within(await screen.findByTestId("traj-public")).getByRole("row", { name: /Amazon/ });
    fireEvent.click(within(row).getByRole("button", { name: msg("insights-offer-start-aria", { company: "Amazon" }) }));

    // The started offer takes focus, so the move to it is announced.
    expect(within(calculator()).getByRole("heading", { name: msg("insights-offer-finished-title", { named: "yes", company: "Amazon" }) }))
      .toHaveFocus();
    // Amazon's median role: $240K base, $160K a year in equity over four years.
    expect(within(calculator()).getByText(msg("insights-offer-started-from", { kind: "company", title: "", company: "Amazon" })))
      .toBeInTheDocument();
    expect(chip(msg("insights-offer-chip-base", { amount: comp(240_000) }))).toHaveTextContent(msg("insights-offer-tag", { tag: "typical" }));
    expect(chip(msg("insights-offer-chip-stock", { kind: "dollars", amount: comp(640_000), count: "" }))).toBeInTheDocument();
    await waitFor(() => expect(kept.offer?.started_from).toEqual({ company: "amazon", title: null }));

    // Use my figures walks the typical answers, base first.
    press(msg("insights-offer-swap"));
    expect(step()).toBe("base");
    press(msg("insights-offer-later"));

    press(msg("insights-offer-undo"));
    expect(chip(msg("insights-offer-chip-base", { amount: comp(123_000) }))).toBeInTheDocument();
    await waitFor(() => expect(kept.offer?.inputs.base).toBe(123_000));
  });

  it("starts from a role's figures handed over by its detail page", async () => {
    renderPanel({
      pathname: "/statistics/trajectory",
      state: { offerFrom: { company: "microsoft", title: "Principal Engineer", base: 250_000, bonus: 37_500, equity: 120_000 } },
    });
    expect(await screen.findByText(msg("insights-offer-started-from", { kind: "role", title: "Principal Engineer", company: "Microsoft" })))
      .toBeInTheDocument();
    expect(chip(msg("insights-offer-chip-base", { amount: comp(250_000) }))).toBeInTheDocument();
    expect(chip(msg("insights-offer-chip-bonus", { pct: 15 }))).toBeInTheDocument();
    expect(chip(msg("insights-offer-chip-stock", { kind: "dollars", amount: comp(480_000), count: "" }))).toBeInTheDocument();
    await waitFor(() => expect(kept.offer?.started_from).toEqual({ company: "microsoft", title: "Principal Engineer" }));
  });

  it("ignores figures handed over in a shape it does not know", async () => {
    renderPanel({ pathname: "/statistics/trajectory", state: { offerFrom: { company: "microsoft", title: "x", base: "250000" } } });
    await ready();
    expect(step()).toBe("company");
    expect(api.saveOffer).not.toHaveBeenCalled();
  });

  it("keeps a private company's valuation once, for the offer and the company table", async () => {
    renderPanel();
    await ready();
    const privateTable = () => screen.getByTestId("traj-private");
    expect(within(privateTable()).queryByText(msg("insights-offer-at-your-valuation"))).toBeNull();

    press("OpenAI");
    next();
    type(msg("insights-offer-q-base"), "100000");
    next();
    type(msg("insights-offer-q-stock", { vehicle: "rsu" }), "2200000");
    next();
    expect(step()).toBe("valuation");
    type(msg("insights-offer-valuation-grant", { unit: "per_share" }), "50");
    type(msg("insights-offer-valuation-test", { unit: "per_share" }), "75");
    next();
    press(msg("insights-offer-vesting-yes"));
    press(msg("insights-offer-sign-on-no"));

    // $2.2M over four years at 1.5 times the grant's valuation, plus base.
    expect(yearTotals()[0]).toEqual([comp(925_000)]);
    // The table reads the same valuation: OpenAI's $550K a year in equity at 1.5x.
    expect(within(privateTable()).getByText(msg("insights-offer-at-your-valuation"))).toBeInTheDocument();
    const row = within(privateTable()).getByRole("row", { name: /OpenAI/ });
    expect(within(row).getByText(comp(1_375_000))).toBeInTheDocument();
    await waitFor(() => expect(kept.valuations.openai).toMatchObject({ unit: "per_share", grant_at: 50, test_at: 75 }));
    expect(kept.offer?.answered).toContain("valuation");
    expect(offerKeysInBrowser()).toEqual([]);
  });

  it("offers the last stored close as today's price, with its date", async () => {
    vi.mocked(api.offerTerms).mockResolvedValue({
      feed_configured: true,
      companies: [terms({ company: "microsoft", ticker: "MSFT", quote: { price: 412.5, as_of: "2026-11-07" } }), terms({ company: "meta", ticker: "META" })],
    });
    renderPanel();
    await ready("Microsoft");
    fireEvent.change(within(calculator()).getByRole("combobox", { name: msg("insights-offer-all-companies") }), { target: { value: "microsoft" } });
    next();
    type(msg("insights-offer-q-base"), "200000");
    next();
    press(msg("insights-offer-grant-unit-option", { unit: "shares" }));
    type(msg("insights-offer-q-stock", { vehicle: "rsu" }), "777");
    next();
    expect(step()).toBe("price");
    expect(within(question()).getByText(msg("insights-offer-q-price-quote", { price: money(412.5), date: calendarDay("2026-11-07") })))
      .toBeInTheDocument();
    press(msg("insights-offer-use-price", { price: money(412.5) }));
    expect(step()).toBe("vesting");
    await waitFor(() => expect(kept.offer?.answered).toContain("price"));
    // The stored close stays the price: none is typed in.
    expect(kept.offer?.inputs.price).toBeNull();
  });

  it("asks for today's price where no close is stored, pointing to Settings only without a key", async () => {
    vi.mocked(api.offerTerms).mockResolvedValue({ feed_configured: false, companies: [terms({ company: "meta", ticker: "META" })] });
    kept = {
      offer: {
        ...AMAZON_DONE,
        inputs: { ...AMAZON_DONE.inputs, company: "meta", grant_unit: "shares", grant: 100 },
        answered: ["company", "base", "stock"],
        saved_at: SAVED_AT,
      },
      valuations: {},
    };
    renderPanel();
    fireEvent.click(await screen.findByRole("button", { name: msg("insights-offer-continue") }));
    expect(step()).toBe("price");
    expect(within(question()).getByRole("link", { name: msg("insights-offer-price-settings") })).toHaveAttribute("href", "/settings/plugins");
    next();
    expect(within(question()).getByRole("alert")).toHaveTextContent(msg("insights-offer-need", { what: "price" }));
    type(msg("insights-offer-q-price", { quote: "no", company: "Meta" }), "600");
    next();
    expect(step()).toBe("vesting");
  });

  it("sends a write made after leaving and coming back only once the earlier one is kept", async () => {
    kept = { offer: { ...AMAZON_DONE, saved_at: SAVED_AT }, valuations: {} };
    let keep!: () => void;
    vi.mocked(api.saveOffer).mockImplementationOnce((draft: OfferDraft) => new Promise((resolve) => {
      keep = () => {
        kept = { ...kept, offer: { ...structuredClone(draft), saved_at: SAVED_AT } };
        resolve(copy());
      };
    }));
    const first = renderPanel();
    fireEvent.click(await screen.findByRole("button", { name: msg("insights-offer-chip-edit", { answer: msg("insights-offer-chip-base", { amount: comp(200_000) }) }) }));
    type(msg("insights-offer-q-base"), "250000");
    press(msg("insights-offer-done"));
    first.unmount();

    renderPanel();
    await screen.findByRole("heading", { name: msg("insights-offer-finished-title", { named: "yes", company: "Amazon" }) });
    press(msg("insights-offer-clear"));
    // The clear waits for the save still in the air, so the save cannot land after it.
    await new Promise((r) => setTimeout(r, 20));
    expect(api.clearOffer).not.toHaveBeenCalled();
    keep();
    await waitFor(() => expect(api.clearOffer).toHaveBeenCalledTimes(1));
    await waitFor(() => expect(kept.offer).toBeNull());
  });

  it("keeps a valuation that was not saved on screen, and says so, after the answer that follows it is saved", async () => {
    vi.mocked(api.saveValuation).mockRejectedValueOnce(new Error("offline"));
    renderPanel();
    await ready();
    press("OpenAI");
    next();
    type(msg("insights-offer-q-base"), "100000");
    next();
    type(msg("insights-offer-q-stock", { vehicle: "rsu" }), "2200000");
    next();
    type(msg("insights-offer-valuation-grant", { unit: "per_share" }), "50");
    type(msg("insights-offer-valuation-test", { unit: "per_share" }), "75");
    next();

    // The offer's own answer is kept; the valuation before it was not.
    await waitFor(() => expect(kept.offer?.answered).toContain("valuation"));
    expect(kept.valuations.openai).toBeUndefined();
    expect(await within(calculator()).findByText(msg("insights-offer-save-failed"))).toBeInTheDocument();
    const row = within(screen.getByTestId("traj-private")).getByRole("row", { name: /OpenAI/ });
    expect(within(row).getByText(comp(1_375_000))).toBeInTheDocument();
  });

  it("starts from a row only once the kept offer is read, so Undo has it to put back", async () => {
    kept = { offer: { ...AMAZON_DONE, saved_at: SAVED_AT }, valuations: {} };
    let read!: () => void;
    vi.mocked(api.offer).mockImplementationOnce(() => new Promise((resolve) => {
      read = () => resolve(copy());
    }));
    renderPanel();
    const start = () => within(screen.getByTestId("traj-public")).getByRole("button", { name: msg("insights-offer-start-aria", { company: "Amazon" }) });
    await screen.findByTestId("traj-public");
    expect(start()).toBeDisabled();
    fireEvent.click(start());
    expect(api.saveOffer).not.toHaveBeenCalled();

    read();
    await waitFor(() => expect(start()).toBeEnabled());
  });

  it("says when an answer was not kept, and leaves it on screen", async () => {
    vi.mocked(api.saveOffer).mockRejectedValue(new Error("offline"));
    renderPanel();
    await ready();
    press("Amazon");
    next();
    expect(await within(calculator()).findByText(msg("insights-offer-save-failed"))).toBeInTheDocument();
    expect(step()).toBe("base");
    expect(kept.offer).toBeNull();
  });
});

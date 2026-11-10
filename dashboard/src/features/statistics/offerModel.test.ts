/* The offer calculator's arithmetic: each year's total compensation at today's
 * price and after a move, from the person's figures and the company's stated
 * rules. The company terms below are the shapes `/api/statistics/offer-terms`
 * sends for these companies. */
import { describe, expect, it } from "vitest";
import type { OfferTerms, OfferTermsCompany } from "../../api";
import {
  ANOTHER_COMPANY,
  EMPTY_OFFER,
  computeOffer,
  offerFromPackage,
  pickCompany,
  type OfferInputs,
  type Valuation,
} from "./offerModel";

const company = (over: Partial<OfferTermsCompany> & { company: string }): OfferTermsCompany => ({
  listed: true,
  ticker: null,
  equity_vehicle: "rsu",
  vesting: null,
  vesting_stated_by: null,
  bonus_rule: null,
  sign_on_bridges_vesting: false,
  quote: null,
  ...over,
});

const AMAZON = company({
  company: "amazon", ticker: "AMZN", vesting: [5, 15, 40, 40], vesting_stated_by: "estimated",
  bonus_rule: "none", sign_on_bridges_vesting: true,
});
const GOOGLE = company({
  company: "google", ticker: "GOOGL", vesting: [38, 32, 20, 10], vesting_stated_by: "estimated", bonus_rule: "pct_of_base",
  quote: { price: 300, as_of: "2026-11-07" },
});
const ANTHROPIC = company({ company: "anthropic", listed: false, bonus_rule: "none" });
const NETFLIX = company({ company: "netflix", ticker: "NFLX", equity_vehicle: "cash_election", bonus_rule: "none" });
const STRIPE = company({ company: "stripe", listed: false, equity_vehicle: "options" });
const TERMS: OfferTerms = { feed_configured: true, companies: [AMAZON, GOOGLE, ANTHROPIC, NETFLIX, STRIPE] };

const offer = (over: Partial<OfferInputs>): OfferInputs => ({ ...EMPTY_OFFER, ...over });
const totals = (r: ReturnType<typeof computeOffer>) => r.years.map((y) => Math.round(y.total));
const moved = (r: ReturnType<typeof computeOffer>) => r.years.map((y) => Math.round(y.totalMoved));

describe("computeOffer", () => {
  it("vests a 5/15/40/40 grant year by year and moves only the equity under +20%", () => {
    const r = computeOffer(
      offer({ company: "amazon", base: 200_000, bonus_pct: 0, grant: 400_000, sign_on: [100_000, 80_000] }),
      AMAZON, null, 0.2,
    );
    expect(r.vesting).toEqual([5, 15, 40, 40]);
    expect(r.vestingFrom).toBe("estimated");
    expect(r.years.map((y) => y.equity)).toEqual([20_000, 60_000, 160_000, 160_000]);
    // Base, bonus and sign-on are cash: only the equity takes the 20%.
    expect(totals(r)).toEqual([320_000, 340_000, 360_000, 360_000]);
    expect(moved(r)).toEqual([324_000, 352_000, 392_000, 392_000]);
    expect(Math.round(r.total)).toBe(1_380_000);
    expect(Math.round(r.totalMoved)).toBe(1_460_000);
  });

  it("flags each year that pays less than the one before", () => {
    const r = computeOffer(offer({ company: "google", base: 200_000, grant: 400_000 }), GOOGLE, null, 0);
    expect(totals(r)).toEqual([352_000, 328_000, 280_000, 240_000]);
    expect(r.years.map((y) => y.drop)).toEqual([false, true, true, true]);
    const flat = computeOffer(offer({ base: 200_000, grant: 400_000 }), null, null, 0);
    expect(flat.years.map((y) => y.drop)).toEqual([false, false, false, false]);
  });

  it("assumes an even schedule, and says so, where the company states none", () => {
    const r = computeOffer(offer({ company: "anthropic", base: 300_000, grant: 800_000 }), ANTHROPIC, null, 0);
    expect(r.vesting).toEqual([25, 25, 25, 25]);
    expect(r.vestingFrom).toBe("assumed");
    expect(totals(r)).toEqual([500_000, 500_000, 500_000, 500_000]);
  });

  it("reads the person's own schedule over the company's, and a stated 33/33/33 as thirds", () => {
    const own = computeOffer(offer({ company: "amazon", grant: 400_000, vesting: [25, 25, 25, 25] }), AMAZON, null, 0);
    expect(own.years.map((y) => y.equity)).toEqual([100_000, 100_000, 100_000, 100_000]);
    expect(own.vestingFrom).toBe("you");
    const thirds = computeOffer(
      offer({ grant: 300_000 }),
      company({ company: "acme", vesting: [33, 33, 33], vesting_stated_by: "employer" }), null, 0,
    );
    expect(thirds.years.map((y) => Math.round(y.equity))).toEqual([100_000, 100_000, 100_000, 0]);
    expect(thirds.vestedPct).toBe(100);
    const short = computeOffer(offer({ grant: 400_000, vesting: [25, 25, 25, null] }), null, null, 0);
    expect(short.vestedPct).toBe(75);
  });

  it("keeps the person's own cash and equity split at a cash-election company under any move", () => {
    const allCash = computeOffer(offer({ company: "netflix", base: 600_000 }), NETFLIX, null, 0.5);
    expect(allCash.cashElection).toBe(true);
    expect(moved(allCash)).toEqual([600_000, 600_000, 600_000, 600_000]);
    const split = computeOffer(offer({ company: "netflix", base: 500_000, grant: 400_000 }), NETFLIX, null, -0.5);
    expect(split.years.map((y) => y.base)).toEqual([500_000, 500_000, 500_000, 500_000]);
    expect(moved(split)).toEqual([550_000, 550_000, 550_000, 550_000]);
  });

  it("values a grant in shares at the stored close, and the person's price over it", () => {
    const quoted = computeOffer(offer({ company: "google", grant_unit: "shares", grant: 1_000 }), GOOGLE, null, 0.1);
    expect(quoted.price).toEqual({ value: 300, from: "quote" });
    expect(Math.round(quoted.years[0].equity)).toBe(114_000);
    expect(Math.round(quoted.years[0].equityMoved)).toBe(125_400);
    const typed = computeOffer(offer({ company: "google", grant_unit: "shares", grant: 1_000, price: 250 }), GOOGLE, null, 0);
    expect(typed.price).toEqual({ value: 250, from: "you" });
    expect(Math.round(typed.years[0].equity)).toBe(95_000);
  });

  it("asks for today's price rather than value shares at zero without one", () => {
    const r = computeOffer(offer({ company: "amazon", base: 100_000, grant_unit: "shares", grant: 500 }), AMAZON, null, 0);
    expect(r.missing).toBe("price");
    expect(r.price).toBeNull();
    expect(totals(r)).toEqual([100_000, 100_000, 100_000, 100_000]);
    // A grant in dollars needs no price at all.
    expect(computeOffer(offer({ company: "amazon", grant: 400_000 }), AMAZON, null, 0).missing).toBeNull();
  });

  it("values options at the price above the strike, and never below zero", () => {
    const inputs = offer({ vehicle: "options", grant_unit: "shares", grant: 4_000, strike: 100, price: 150 });
    const r = computeOffer(inputs, null, null, -0.5);
    expect(r.years.map((y) => y.equity)).toEqual([50_000, 50_000, 50_000, 50_000]);
    expect(r.years.map((y) => y.equityMoved)).toEqual([0, 0, 0, 0]);
    expect(computeOffer({ ...inputs, strike: null }, null, null, 0).missing).toBe("strike");
  });

  it("follows a private company's entered valuation, with the move as a change in valuation", () => {
    const inputs = offer({ company: "anthropic", base: 300_000, grant: 800_000 });
    const priced = computeOffer(inputs, ANTHROPIC, null, 0);
    expect(priced.valued).toBe("priced");
    expect(priced.years[0].equity).toBe(200_000);

    const perShare: Valuation = { unit: "per_share", grant_at: 50, test_at: 75, share_count: null };
    const r = computeOffer(inputs, ANTHROPIC, perShare, 0.2);
    expect(r.valued).toBe("entered");
    expect(r.years[0].equity).toBe(300_000);
    expect(Math.round(r.years[0].equityMoved)).toBe(360_000);

    // A company valuation with the share count values a grant in shares.
    const whole: Valuation = { unit: "company", grant_at: 60e9, test_at: 90e9, share_count: 1e9 };
    const shares = computeOffer({ ...inputs, grant_unit: "shares", grant: 10_000 }, ANTHROPIC, whole, 0);
    expect(shares.years[0].equity).toBe(225_000);
    expect(computeOffer({ ...inputs, grant_unit: "shares", grant: 10_000 }, ANTHROPIC, { ...whole, share_count: null }, 0).missing)
      .toBe("share_count");
    expect(computeOffer({ ...inputs, grant_unit: "shares", grant: 10_000 }, ANTHROPIC, null, 0).missing).toBe("valuation");
  });

  it("values private options against the tested price per share", () => {
    const v: Valuation = { unit: "per_share", grant_at: 10, test_at: 30, share_count: null };
    const r = computeOffer(offer({ company: "stripe", vehicle: "options", grant_unit: "shares", grant: 40_000, strike: 10 }), STRIPE, v, 0);
    expect(r.years[0].equity).toBe(200_000);
  });

  it("values a typed-in private company's shares at the price per share entered, and asks for it until then", () => {
    const inputs = offer({ company: ANOTHER_COMPANY, listed: false, grant_unit: "shares", grant: 4_000 });
    expect(computeOffer(inputs, null, null, 0).missing).toBe("price");
    const r = computeOffer({ ...inputs, price: 25 }, null, null, 0.2);
    expect(r.missing).toBeNull();
    expect(r.years.map((y) => y.equity)).toEqual([25_000, 25_000, 25_000, 25_000]);
    expect(r.years[0].equityMoved).toBeCloseTo(30_000);
  });
});

describe("filling the form", () => {
  it("takes a picked company's stock type and no-bonus rule, and keeps the person's figures", () => {
    const filled = pickCompany(offer({ base: 250_000, bonus_pct: 15, grant: 300_000, price: 99, vesting: [1, 2, 3, 4] }), "amazon", TERMS);
    expect(filled).toMatchObject({ company: "amazon", base: 250_000, bonus_pct: 0, grant: 300_000, price: null, vesting: null });
    const options = pickCompany(offer({ grant_unit: "dollars" }), "stripe", TERMS);
    expect([options.vehicle, options.grant_unit]).toEqual(["options", "shares"]);
  });

  it("keeps a cash election in dollars, so no share price is needed that no question asks", () => {
    const netflix = pickCompany(offer({ company: "google", grant_unit: "shares", grant: 1_000 }), "netflix", TERMS);
    expect(netflix.grant_unit).toBe("dollars");
    expect(computeOffer(netflix, NETFLIX, null, 0).missing).toBeNull();
  });

  it("starts from a yearly package with the grant over the years it vests", () => {
    const amazon = offerFromPackage("amazon", { base: 210_000, bonus: 0, equity: 100_000 }, TERMS);
    expect(amazon).toMatchObject({ company: "amazon", base: 210_000, bonus_pct: 0, grant: 400_000, grant_unit: "dollars" });
    const thirds = offerFromPackage("acme", { base: 200_000, bonus: 30_000, equity: 90_000 },
      { feed_configured: false, companies: [company({ company: "acme", vesting: [33, 33, 33] })] });
    expect(thirds).toMatchObject({ bonus_pct: 15, grant: 270_000 });
    // An option grant is counted in options, which a dollar figure cannot say.
    const stripe = offerFromPackage("stripe", { base: 200_000, bonus: 0, equity: 150_000 }, TERMS, false);
    expect(stripe).toMatchObject({ vehicle: "options", grant_unit: "shares", grant: null });
    // A company with no stated terms is another company, listed as its table says.
    const unknown = offerFromPackage("acme-private", { base: 200_000, bonus: 0, equity: 50_000 }, TERMS, false);
    expect(unknown).toMatchObject({ company: ANOTHER_COMPANY, listed: false, grant: 200_000 });
  });
});

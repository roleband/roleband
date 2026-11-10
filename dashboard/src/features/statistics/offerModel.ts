/* The person's own offer, year by year, at today's price and under a move.
 * Pure, so the arithmetic is unit-tested. The shapes are the API's: the offer
 * is kept on this computer through `/api/profile/offer`, and nothing here is
 * sent anywhere else. */

import type { OfferAnswers, OfferDraft, OfferTerms, OfferTermsCompany, ValuationDraft } from "../../api";

export const OFFER_YEARS = 4;
/** The company picker's value for a company not on the list. */
export const ANOTHER_COMPANY = "";

/** What the person enters. A null figure is blank, never zero. The grant is a
 *  total in dollars, or a number of shares or options; a null price reads the
 *  stored close; a null schedule reads the company's, else an even one. */
export type OfferInputs = OfferDraft["inputs"];
export type Vehicle = OfferInputs["vehicle"];
export type GrantUnit = OfferInputs["grant_unit"];
/** The offer as kept: its inputs, the questions answered, the typical
 *  figures it started from, and when it was saved. */
export type StoredOffer = NonNullable<OfferAnswers["offer"]>;
/** A private company's valuation as the person enters it: the one the grant
 *  was priced at and the one to test, per share or for the whole company. */
export type Valuation = ValuationDraft;
export type ValuationUnit = Valuation["unit"];
export type StoredValuation = OfferAnswers["valuations"][string];

export const EMPTY_OFFER: OfferInputs = {
  company: ANOTHER_COMPANY,
  listed: true,
  base: null,
  bonus_pct: null,
  vehicle: "rsu",
  grant_unit: "dollars",
  grant: null,
  strike: null,
  price: null,
  vesting: null,
  sign_on: [null, null],
};

const EVEN_VESTING = [25, 25, 25, 25];

export type VestingFrom = "employer" | "estimated" | "assumed" | "you";
/** What the equity cannot be valued without. */
export type Missing = "price" | "strike" | "valuation" | "share_count";

export interface OfferYear {
  year: number;
  base: number;
  bonus: number;
  signOn: number;
  equity: number;
  total: number;
  /** The same year after the move. */
  equityMoved: number;
  totalMoved: number;
  /** Less than the year before, at today's price. */
  drop: boolean;
}

export interface OfferResult {
  years: OfferYear[];
  total: number;
  totalMoved: number;
  /** Percent vesting each year, as used. */
  vesting: number[];
  vestingFrom: VestingFrom;
  /** Percent of the grant the four years vest. */
  vestedPct: number;
  listed: boolean;
  cashElection: boolean;
  /** Today's share price and where it comes from; null when there is none. */
  price: { value: number; from: "you" | "quote" } | null;
  /** A private company's equity follows the valuation the person entered, or
   *  the one the grant was priced at. */
  valued: "entered" | "priced" | null;
  /** Set when the equity cannot be valued: it counts as zero until entered. */
  missing: Missing | null;
}

export function termsFor(terms: OfferTerms | null | undefined, company: string): OfferTermsCompany | null {
  if (!terms || company === ANOTHER_COMPANY) return null;
  return terms.companies.find((c) => c.company === company) ?? null;
}

function isListed(inputs: OfferInputs, company: OfferTermsCompany | null): boolean {
  return company ? company.listed : inputs.listed;
}

/** The schedule a grant vests on: the person's, else the company's, else even. */
function resolveVesting(
  inputs: OfferInputs,
  company: OfferTermsCompany | null,
): { vesting: number[]; from: VestingFrom } {
  if (inputs.vesting) {
    return { vesting: padYears(inputs.vesting.map((v) => v ?? 0)), from: "you" };
  }
  if (company?.vesting?.length) {
    return { vesting: padYears(company.vesting), from: company.vesting_stated_by ?? "estimated" };
  }
  return { vesting: [...EVEN_VESTING], from: "assumed" };
}

function padYears(values: readonly number[]): number[] {
  return Array.from({ length: OFFER_YEARS }, (_, i) => values[i] ?? 0);
}

/** A stated "33/33/33" means thirds: a sum a rounding short of 100 vests the
 *  whole grant. Any other sum is read as typed. */
function vestScale(vesting: readonly number[]): number {
  const sum = vesting.reduce((a, b) => a + b, 0);
  return sum >= 99 && sum < 100 ? 100 / sum : 1;
}

function perShare(price: number, vehicle: Vehicle, strike: number | null): number {
  return vehicle === "options" ? Math.max(0, price - (strike ?? 0)) : price;
}

/** A valuation figure as a price per share, or null without the share count. */
function pricePerShare(v: Valuation, figure: number): number | null {
  if (v.unit === "per_share") return figure;
  return v.share_count ? figure / v.share_count : null;
}

/** What the whole grant is worth after a move `d` (0.2 is +20%), and what is
 *  missing to value it. */
function grantValue(
  inputs: OfferInputs,
  listed: boolean,
  price: number | null,
  valuation: Valuation | null,
  d: number,
): { value: number; missing: Missing | null } {
  const grant = inputs.grant;
  if (!grant) return { value: 0, missing: null };
  const options = inputs.vehicle === "options";
  // An option is worth its price above the strike, so it is valued per share.
  const inShares = options || inputs.grant_unit === "shares";
  if (options && inputs.strike == null) return { value: 0, missing: "strike" };

  if (listed) {
    if (!inShares) return { value: grant * (1 + d), missing: null };
    if (price == null) return { value: 0, missing: "price" };
    return { value: grant * perShare(price * (1 + d), inputs.vehicle, inputs.strike), missing: null };
  }

  // Without a kept valuation, a price per share the person entered values the
  // grant as it stands today.
  const kept = valuation ?? (price != null ? { unit: "per_share" as const, grant_at: price, test_at: price, share_count: null } : null);
  const priced = kept?.grant_at ?? null;
  const tested = kept?.test_at ?? priced;
  if (!inShares) {
    // A grant stated in dollars was priced at the grant's valuation: it follows
    // the tested valuation by their ratio, so no share count is needed.
    const ratio = priced && tested ? tested / priced : 1;
    return { value: grant * ratio * (1 + d), missing: null };
  }
  if (!kept || tested == null) return { value: 0, missing: inputs.company === ANOTHER_COMPANY ? "price" : "valuation" };
  const pps = pricePerShare(kept, tested);
  if (pps == null) return { value: 0, missing: "share_count" };
  return { value: grant * perShare(pps * (1 + d), inputs.vehicle, inputs.strike), missing: null };
}

/** Each of the four years at today's price and after a move `d` (0.2 is +20%).
 *  Only the equity moves: base, bonus and sign-on are cash. A company where
 *  each person picks the cash and equity mix keeps the person's own split. */
export function computeOffer(
  inputs: OfferInputs,
  company: OfferTermsCompany | null,
  valuation: Valuation | null,
  d: number,
): OfferResult {
  const listed = isListed(inputs, company);
  const { vesting, from } = resolveVesting(inputs, company);
  const scale = vestScale(vesting);
  const quote = listed ? company?.quote ?? null : null;
  const price = inputs.price != null
    ? { value: inputs.price, from: "you" as const }
    : quote
      ? { value: quote.price, from: "quote" as const }
      : null;
  const today = grantValue(inputs, listed, price?.value ?? null, valuation, 0);
  const moved = grantValue(inputs, listed, price?.value ?? null, valuation, d);

  const base = inputs.base ?? 0;
  const bonus = base * (inputs.bonus_pct ?? 0) / 100;
  const years: OfferYear[] = [];
  for (let i = 0; i < OFFER_YEARS; i++) {
    const share = (vesting[i] / 100) * scale;
    const signOn = inputs.sign_on[i] ?? 0;
    const equity = today.value * share;
    const equityMoved = moved.value * share;
    const total = base + bonus + signOn + equity;
    years.push({
      year: i + 1,
      base,
      bonus,
      signOn,
      equity,
      total,
      equityMoved,
      totalMoved: base + bonus + signOn + equityMoved,
      drop: i > 0 && total < years[i - 1].total - 0.5,
    });
  }
  return {
    years,
    total: years.reduce((a, y) => a + y.total, 0),
    totalMoved: years.reduce((a, y) => a + y.totalMoved, 0),
    vesting,
    vestingFrom: from,
    vestedPct: Math.round(vesting.reduce((a, b) => a + b, 0) * scale * 10) / 10,
    listed,
    cashElection: company?.equity_vehicle === "cash_election",
    price: listed ? price : null,
    valued: listed ? null : valuation?.grant_at != null && valuation.test_at != null ? "entered" : "priced",
    missing: today.missing,
  };
}

/** The company's stated rules on the form: its stock type, and no bonus where
 *  it states none. The person's own figures stay; a typed price and schedule
 *  belonged to the company before, so they are cleared. */
export function pickCompany(inputs: OfferInputs, company: string, terms: OfferTerms | null): OfferInputs {
  const t = termsFor(terms, company);
  const options = t?.equity_vehicle === "options";
  return {
    ...inputs,
    company,
    price: null,
    vesting: null,
    vehicle: options ? "options" : t ? "rsu" : inputs.vehicle,
    // A cash election is a split of pay in dollars: no share count or price is asked.
    grant_unit: options ? "shares" : t?.equity_vehicle === "cash_election" ? "dollars" : inputs.grant_unit,
    bonus_pct: t?.bonus_rule === "none" ? 0 : inputs.bonus_pct,
  };
}

/** A yearly package (a company's median role, or one role's) as an offer to
 *  start from: its base and bonus, and its yearly equity times the years the
 *  grant vests over. An option grant is counted in options, which a yearly
 *  dollar figure cannot say, so it is left for the person to enter. Where the
 *  company states no yearly bonus, a measured one is not a yearly bonus, and
 *  the offer never asks about it, so the offer keeps none. */
export function offerFromPackage(
  company: string,
  parts: { base: number; bonus: number; equity: number },
  terms: OfferTerms | null,
  listed = true,
): OfferInputs {
  const t = termsFor(terms, company);
  const start = pickCompany({ ...EMPTY_OFFER, listed }, t ? company : ANOTHER_COMPANY, terms);
  const years = t?.vesting?.filter((v) => v > 0).length || OFFER_YEARS;
  return {
    ...start,
    base: Math.round(parts.base),
    bonus_pct: t?.bonus_rule === "none" ? 0 : parts.base > 0 ? Math.round((parts.bonus / parts.base) * 1000) / 10 : null,
    grant: start.vehicle === "options" ? null : Math.round(parts.equity * years),
    grant_unit: start.vehicle === "options" ? "shares" : "dollars",
  };
}

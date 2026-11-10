/* Which questions an offer asks and in what order. A rule the company states
 * is never asked; the answers given so far decide the rest. */

import { describe, expect, it } from "vitest";
import type { OfferTermsCompany } from "../../api";
import { ANOTHER_COMPANY, EMPTY_OFFER, type OfferInputs, type StoredOffer } from "./offerModel";
import { nextStep, stageOf, stepsFor } from "./offerSteps";

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

const AMAZON = company({ company: "amazon", vesting: [5, 15, 40, 40], bonus_rule: "none" });
const GOOGLE = company({ company: "google", bonus_rule: "pct_of_base", quote: { price: 300, as_of: "2026-11-07" } });
const NETFLIX = company({ company: "netflix", equity_vehicle: "cash_election", bonus_rule: "none" });
const STRIPE = company({ company: "stripe", listed: false, equity_vehicle: "options" });

const offer = (over: Partial<OfferInputs>): OfferInputs => ({ ...EMPTY_OFFER, ...over });
const stored = (answered: StoredOffer["answered"], over: Partial<StoredOffer> = {}): StoredOffer => ({
  inputs: offer({ company: "amazon" }),
  answered,
  started_from: null,
  saved_at: "2026-11-10T10:00:00Z",
  ...over,
});

describe("stepsFor", () => {
  it("asks base and stock first, and never the bonus of a company that pays none", () => {
    expect(stepsFor(offer({ company: "amazon", grant: 400_000 }), AMAZON))
      .toEqual(["company", "base", "stock", "vesting", "sign_on"]);
  });

  it("asks today's price only for a listed grant counted in shares", () => {
    expect(stepsFor(offer({ company: "google", grant: 400_000, grant_unit: "dollars" }), GOOGLE)).not.toContain("price");
    expect(stepsFor(offer({ company: "google", grant: 1_000, grant_unit: "shares" }), GOOGLE))
      .toEqual(["company", "base", "stock", "price", "vesting", "bonus", "sign_on"]);
  });

  it("asks a private company's options for the strike and the valuation, never today's price", () => {
    expect(stepsFor(offer({ company: "stripe", listed: false, vehicle: "options", grant_unit: "shares", grant: 40_000 }), STRIPE))
      .toEqual(["company", "base", "stock", "strike", "valuation", "vesting", "bonus", "sign_on"]);
  });

  it("asks a typed-in private company for a price per share, since its valuation has no company to be kept under", () => {
    const steps = stepsFor(offer({ company: ANOTHER_COMPANY, listed: false, grant_unit: "shares", grant: 4_000 }), null);
    expect(steps).toContain("price");
    expect(steps).not.toContain("valuation");
    expect(stepsFor(offer({ company: ANOTHER_COMPANY, listed: false, grant_unit: "dollars", grant: 100_000 }), null))
      .not.toContain("price");
  });

  it("skips vesting and price where the person picks their own cash and stock split", () => {
    expect(stepsFor(offer({ company: "netflix", grant: 100_000, grant_unit: "shares" }), NETFLIX))
      .toEqual(["company", "base", "stock", "sign_on"]);
  });

  it("asks nothing about a grant before there is one", () => {
    expect(stepsFor(offer({ company: "stripe", listed: false, vehicle: "options", grant: 0 }), STRIPE))
      .toEqual(["company", "base", "stock", "bonus", "sign_on"]);
  });

  it("leaves out the company question when the offer starts from one", () => {
    expect(stepsFor(offer({ company: "amazon" }), AMAZON, true)[0]).toBe("base");
  });
});

describe("stageOf and nextStep", () => {
  const steps = stepsFor(offer({ company: "amazon", grant: 400_000 }), AMAZON);

  it("reads nothing, some answers, and every answer as start, unfinished and finished", () => {
    expect(stageOf(null, steps)).toBe("start");
    expect(stageOf(stored(["company", "base"]), steps)).toBe("unfinished");
    expect(stageOf(stored([...steps]), steps)).toBe("finished");
  });

  it("reads an offer started from typical figures as finished at once", () => {
    expect(stageOf(stored(["company"], { started_from: { company: "amazon", title: null } }), steps)).toBe("finished");
  });

  it("goes to the first question still open, in order, whatever order the answers came in", () => {
    expect(nextStep(["company", "stock"], steps)).toBe("base");
    expect(nextStep([...steps], steps)).toBeNull();
  });
});

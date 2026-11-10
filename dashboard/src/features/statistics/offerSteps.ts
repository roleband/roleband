/* The guided offer's questions: which ones an offer asks, in what order, and
 * where the person is. Pure, so the order and the skips are unit-tested.
 *
 * A rule the company states is never asked: no yearly bonus, a cash election.
 * A schedule the company states is asked as yes or no. Base and stock come
 * first, so the chart means something after two answers. */

import type { OfferStep, OfferTermsCompany } from "../../api";
import { ANOTHER_COMPANY, type OfferInputs, type StoredOffer } from "./offerModel";

export type { OfferStep };

/** The questions this offer asks, in order. Answers change the list: a grant
 *  in shares at a listed company asks today's price, a private grant asks the
 *  valuation, options ask the strike. A company typed in by hand has no name
 *  to keep a valuation under, so its grant in shares asks a price instead. */
export function stepsFor(inputs: OfferInputs, company: OfferTermsCompany | null, startsFromCompany = false): OfferStep[] {
  const listed = company ? company.listed : inputs.listed;
  const cashElection = company?.equity_vehicle === "cash_election";
  const grant = (inputs.grant ?? 0) > 0;
  const inShares = inputs.vehicle === "options" || inputs.grant_unit === "shares";
  const named = inputs.company !== ANOTHER_COMPANY;
  const steps: OfferStep[] = [];
  if (!startsFromCompany) steps.push("company");
  steps.push("base", "stock");
  if (grant && inputs.vehicle === "options") steps.push("strike");
  if (grant && !cashElection && inShares && (listed || !named)) steps.push("price");
  if (grant && !listed && named) steps.push("valuation");
  if (grant && !cashElection) steps.push("vesting");
  // A bonus the offer holds is asked, so it can be changed, even where the
  // company states none (a posting that states one).
  if (company?.bonus_rule !== "none" || (inputs.bonus_pct ?? 0) > 0) steps.push("bonus");
  steps.push("sign_on");
  return steps;
}

/** Where the block is: nothing yet, some questions answered, or done. An offer
 *  started from typical figures is done at once: its figures read as typical
 *  until the person answers them. */
export type OfferStage = "start" | "unfinished" | "finished";

export function stageOf(offer: StoredOffer | null, steps: readonly OfferStep[]): OfferStage {
  if (!offer) return "start";
  if (offer.started_from) return "finished";
  return steps.every((s) => offer.answered.includes(s)) ? "finished" : "unfinished";
}

/** The first question still to answer, or null when none is left. */
export function nextStep(answered: readonly OfferStep[], steps: readonly OfferStep[]): OfferStep | null {
  return steps.find((s) => !answered.includes(s)) ?? null;
}

/** Preset schedules offered when the company states none: even first, which
 *  is also what an unanswered schedule assumes. */
export const VESTING_PRESETS: readonly (readonly number[])[] = [
  [25, 25, 25, 25],
  [5, 15, 40, 40],
  [40, 30, 20, 10],
];

/** Bonus targets offered as one press, as a percent of base. */
export const BONUS_PRESETS: readonly number[] = [0, 10, 15, 20];

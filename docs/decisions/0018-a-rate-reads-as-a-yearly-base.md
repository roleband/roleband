# 0018: An hourly or monthly rate reads as a yearly base salary

## Context

Most postings state a yearly range, and every figure a person compares pay
with is yearly: their own target, the market's levels, our estimates. Some
postings state an hourly or monthly rate instead. The pay panel used to show
such a rate only as posted, with our yearly estimate of total pay as the
headline above it, so "$85-$110 / hr" sat under "$480K-$650K / yr": the
employer's figure was the small one, and the headline was two to three times
what the employer offers.

A rate is pay for the time worked. It states the base and nothing about a
bonus or equity, which may or may not exist.

## Decision

- The package carries an hourly or monthly rate as `yearly_base`: 2,080 hours
  (40 a week for 52 weeks) or twelve months. A band the posting calls total
  pay gets none.
- Job detail's pay panel shows that year as its headline, as base salary
  ("Base salary from the posted rate"), with the rate as posted under it. No
  bonus, equity or total is drawn on it, and our estimate is not shown beside
  it.
- More generally, the employer's figure leads the panel whenever the posting
  states one; our estimate is the headline only when the posting states none.
- The stored band keeps the rate as stated. Sorting, pay filters, the pay
  floor and Insights read stated pay as before; this changes only how the
  package presents it.

## Consequences

- A person reads every posting in one unit and sees the employer's own number
  first.
- The year assumes full-time work. A part-time or seasonal posting's year is
  overstated; the rate as posted under it is the correction the person sees.
- `docs/pay.md` (When a band is not split, Rules) states the rule;
  `test_comp_package.py` and `JobCompPanel.test.tsx` enforce it, with a stated
  total and an unclear period as the controls that get no year.

## Alternatives considered

- **Show the rate only as posted.** Honest about the unit but leaves the
  person to convert it, and let our larger estimate take the headline.
- **Annualise into a total.** A rate says nothing about a bonus or equity;
  calling its year a total would invent them.
- **Annualise in the stored band.** It would rewrite what the posting states
  and every reader built on it; the package is the one place that presents
  pay.

# 0006: A stated base is shown whether or not the level is placed

## Context

The pay panel draws a bar of base, bonus and equity, each segment labelled
stated or estimated. The bar needs a package, and four things stop one being
built while the employer has still published a base salary:

- the posting's level is a guess we cannot place on the shared levels
  (`level_unplaced`), which no source prices;
- the posting's pay country is not the one our split is measured on
  (`not_us_pay`);
- a plugin answers pay and reports no split for the level
  (`plugin_without_split`, `plugin_not_covered`);
- the company lets each person pick their own cash and equity mix
  (`employee_election`).

`level_unplaced` reaches the most postings of the four. A title names no level
we can place whenever it is not one the shared levels spell, which is the
ordinary case outside software engineering, where the ladder holds nearly all
its rungs: a bare "Product Manager", "Program Manager" or "Engineering
Manager" states nothing the ladder can read.

Treating that as a reason to withhold the figure makes one rule cover two
different things. "Never price a level we cannot place" is about the parts
RoleBand models: the bonus, the equity, the total, each of which needs a level
to scale. The base is not modelled. The employer published it.

## Decision

A base the posting states is shown as the bar's one stated segment whenever the
package cannot be split, so the reader sees the employer's own figure in the
same design that carries every other stated component.

It requires exactly what a base segment claims: `pay_basis` is `base`, the
period is a year, and the bound is the posting's own. A band the posting never
called base (`basis_unclear`), a rate that is hourly, monthly or of an unknown
period, and a stated total keep no segment, because each would draw a figure as
something it is not.

Nothing else is built: no bonus, no equity, no `total`, no reconciliation
against the guessed level, no estimate. The `no_split_reason` stays and the
panel still says why there is no split.

Where the headline already prints the employer's figure, the panel prints it
once: the guaranteed-base line and the block that repeats the stated figure are
for a package whose headline is an estimate instead.

## Consequences

- A posting with an unplaced level and a stated yearly base now shows the bar
  with one full-width stated base segment, the headline "Stated by the
  employer", and the sentence saying no split or total is estimated.
- The bar no longer appears or disappears according to which of the four
  reasons applies, so a reader cannot conclude from its absence that the
  employer published nothing.
- `components` may now hold a single `base` segment with no `total` beside it.
  A reader of the package that assumes a total wherever components exist is
  wrong; `analytics/stock_trajectory` already requires `total` and a base
  together, so it counts none of these.
- The Insights posted-pay figures are unchanged: they read the stored band, not
  the package.

## Alternatives considered

- **Leave the figure in a note.** The note is the design for something we cannot
  show; the base is a stated fact, and the panel's own labelling of stated
  against estimated exists to carry exactly this difference.
- **Show the bar only for an unplaced level.** The other three reasons withhold
  the same fact for reasons equally unrelated to the base, and a bar that comes
  and goes by reason teaches the reader nothing.
- **Estimate bonus and equity from the guessed level too.** This is what
  [0005 of the level rule](../pay.md) refuses, and the case that produced it: a
  "Product Manager" posting stating $151,200 to $223,200 was shown a Senior
  Product Manager's $390,000.

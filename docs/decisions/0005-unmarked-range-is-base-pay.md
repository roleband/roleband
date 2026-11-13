# 0005: An unmarked range in the US or Canada is base pay

## Context

A posting's pay panel splits a range into base, bonus and equity only where the
stored basis (`disclosed_pay_basis`) says what the range covers. The basis is
settled by markers in the posting's own words: "base salary range", extras
stated as added on top, a range the posting calls total compensation, or a
definition per kind of role.

Most US and Canadian employers write none of them. Pay-transparency rules make
them carry a figure, and they print one range under a neutral label: "Pay
Range", "Zone 1", "California pay range", "Compensation:". A range with no marker is
`unclear`, and an `unclear` range is never split. That unmarked label is the
commonest shape in which a US or Canadian posting states its pay.

Reading such a range as base is not an assumption about one employer, but about
what postings in those countries conventionally state: the figure printed under
a bare label is the base salary, and a selling role's may be on-target earnings
instead. It is not a reading of any one statute. What the rules demand differs
by state and province, and some ask for expected compensation, which may include
a bonus, rather than for base. The convention is therefore a reading of the
market's wording, and the markers below are what overrides it wherever an
employer says something else.

## Decision

A range left `unclear` by every marker is base pay when both hold:

- its pay country is one of `BASE_BY_CONVENTION_COUNTRIES` (the US, Canada):
  a posting that names places in several countries, or none, has no country and
  keeps `unclear`;
- the role does not sell (`taxonomy/roles.sells` is false): a selling role's one
  range may be on-target earnings, and a role whose commission cannot be told
  (pre-sales, customer success, no family) keeps `unclear`.

It stays `unclear` when the posting describes an employee election, or the
range's own paragraph says it includes bonus, commission or equity, or calls
itself total, cash or on-target pay. The convention is read last, so every
marker a posting states wins over it.

Every writer of a band asks `settle_band` with the posting's pay country, and a
stored band a connector wrote is settled by the daily pass
(`settle_open_bands`), since the text pass never re-reads one.

## Consequences

- A US or Canadian posting with one unmarked yearly range now shows the
  breakdown wherever its level is placed, and feeds the posted-pay figures that
  read base pay only.
- The reading is a convention, not a quotation: a US employer who prints a
  total under a neutral label and says nothing is read as base. The paragraph
  tests in `tests/test_pay_basis_by_role.py` hold the wording that must still
  refuse it, and the panel never calls an unmarked range a quotation of the
  words "base salary".
- `basis_unclear` now means what no rule settles: a selling role, a range called
  total or cash pay, or a posting outside the two countries.
- Adding a country to the set is a claim about how that country's postings are
  conventionally worded, so the set is a named constant with the reasoning
  beside it. It is not a claim about a statute, and no code here reads one.
- A stored `base` does not record whether a marker or this convention settled
  it, and the convention reads the role's family and the posting's country.
  Nothing re-settles a band when a later pass changes either, so a role
  reclassified into a selling family keeps the basis its earlier family earned.
  Telling the two apart needs the band to carry where its basis came from; the
  stored value alone cannot, because an explicit marker stores `base` too.

## Alternatives considered

- **Read every unmarked range as base, anywhere.** Outside these countries a
  posted range is as often total compensation, and nothing in the text would
  catch the difference.
- **Read it as base only for a known employer.** A table of employers would
  cover the large ones and leave the thousands of small employers, which are
  most of the postings, unread.
- **Show the breakdown while keeping the basis `unclear`.** The basis is what
  the posted-pay figures and the pay floor read; splitting a range the stored
  basis calls unknown would make those readers disagree with the panel.

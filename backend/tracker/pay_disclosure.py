"""The pay-band vocabulary: reading a disclosed salary band out of posting text.

Deterministic, self-contained, and used by two callers that have nothing else in
common — the connector detail parsers and the disclosed-comp pass. That is why
it is vocabulary at this tier rather than model code: the connector layer
imports it without reaching up into `intelligence`.

Reading order: currency evidence, then band plausibility, then
`extract_grounded_band` (the entry point), then grounding the answer back in the
full posting (`find_pay_span`), then the basis and bonus derivations. The
number grammar and currency table are `pay_numbers`, the period rule
`pay_period`.

COMP FACTS. Nothing here estimates: it reports what a posting literally states.
`derive_pay_basis` is what makes a stated base a fact rather than a guess
(`docs/pay.md`, "the three components"). Read that file before changing a
bound, a window, or a threshold here.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Sequence
from enum import Enum
from itertools import product
from typing import Literal, NamedTuple

from pydantic import BaseModel, Field, PrivateAttr

from tracker.pay_numbers import AMOUNT, CURRENCY_CODE, NUM_RE, explicit_amount, number_readings
from tracker.pay_period import PayPeriod, attached_words, decide_period, size_classes
from tracker.taxonomy.roles import sells

# Collapse runs of whitespace when slicing a verbatim display snippet (case kept,
# unlike normalize_text which is for symmetric comparison).
_WS_RE = re.compile(r"\s+")


MAX_COMP = 100_000_000  # sanity ceiling (whole currency units / year)

#: The text pass's extractor version, stamped on every row it processes
#: (`jobs.structured_prompt_version`) and the stale gate's comparison. Bump it
#: when this module's reading of a band changes: the post pass then re-reads
#: every posting whose band the text pass wrote, or none was found, a capped
#: number per run. A band a connector read from a structured field
#: is never re-read (`jobs.disclosed_source`). Independent of the experimental
#: prompt's `intelligence.prompts.PROMPT_VERSION`, which does not extract.
PAY_PARSER_VERSION = "pay_parser/2026-11-13.2"


#: The periods a list row writes a posted base range with. An unclear period
#: has no unit to write, so the row shows the estimated base instead.
ROW_PAY_PERIODS = ("year", "hour", "month")


def band_stated(base_min: object, base_max: object) -> bool:
    """Does a stored row carry a stated band (either bound)?"""
    return base_min is not None or base_max is not None


def disclosure_known(structured_at: object, base_min: object, base_max: object) -> bool:
    """Do we know whether this posting states pay? The one reading every pay
    reader shares (detail, the `discloses_pay` filter, the transparency rate).

    A stored band is evidence on its own: a connector, the posting page or the
    text stated it, whichever wrote it (`jobs.disclosed_source`). Only the
    ABSENCE of a band needs the text pass's read (`jobs.structured_at`) to mean
    "states nothing"; before that read it means "not read yet". The stamp is
    the text pass's progress, never the band's availability: a band a page
    read stored before the text pass ran is already a stated band."""
    return structured_at is not None or band_stated(base_min, base_max)


class PayBasis(str, Enum):
    base = "base"
    total = "total"
    unclear = "unclear"


class DisclosedComp(BaseModel):
    disclosed: bool = False
    base_min: int | None = Field(default=None, ge=0, le=MAX_COMP)
    base_max: int | None = Field(default=None, ge=0, le=MAX_COMP)
    currency: str | None = Field(default=None, max_length=8)
    pay_basis: PayBasis = PayBasis.unclear
    pay_period: PayPeriod = PayPeriod.unclear
    source_snippet: str | None = Field(default=None, max_length=240)
    confidence: Literal["high", "low"] = "low"
    # Derived in code, never asked of the model: the guided-generation target in
    # `apple_fm._build_generable` is hand-written and has no such field. Read
    # against `pay_basis` as this reader found it; a writer stores the one
    # `settle_band` reads against the settled basis instead.
    bonus_pct: float | None = Field(default=None, ge=0.0, le=1.0)
    # Where the band sits in the full posting it was grounded in. Private: not
    # part of any answer, of the schema a model is shown, or of a dump.
    _span: tuple[int, int] | None = PrivateAttr(default=None)

    @property
    def span(self) -> tuple[int, int] | None:
        """Where the band sits in the posting (`locate_pay_span`), so the writer
        settling its basis and reading its bonus does not search for it again."""
        return self._span

    def located(self, span: tuple[int, int]) -> DisclosedComp:
        """This band, recorded as found at `span`."""
        self._span = span
        return self


# The currency marker is OPTIONAL IN POSITION, never optional in fact: a match
# must carry one somewhere, enforced by `_has_currency_evidence` rather than by
# the pattern, because it may sit before the low number, after it, or after the
# high number and a regex demanding one place cannot see the other two.
#
# A LEADING symbol cannot be required: large employers commonly write money
# with no symbol at all, the code trailing either number:
#
#     126,900.00 - 181,400.00 USD annually
#     168,000 USD - 258,750 USD
#
# A no-band control set must still yield no invented band. Three further
# shapes real postings use:
#
#     Zone A: CA$142,000 - CA$190,000        (a dollar with a country)
#     $175,100/year to $236,900/year         (a period between the number
#                                             and the dash)
#     base range ... is $184,050 $262,928    (no separator at all)
#
# The last one is why the separator branch that allows NONE demands that the
# high number carry its own currency marker: "a team of 5 10 engineers" must
# not read as a band, and without that lookahead it would.
# The country must be a token of its own: without the lookbehind, the "s" of
# "is $184,050" reads as Singapore and the band comes back SGD.
# Nor may a line break part it from its sign: "Zone A\n$190,000" is a zone.
_DOLLAR_PREFIX = r"(?:(?<![A-Za-z])(?:US|CA|C|A|NZ|HK|S)[ \xa0]?)?"
_MONEY_AHEAD = r"(?=" + _DOLLAR_PREFIX + r"[$£€])"
# An optional piece carries its own leading whitespace, `(?:\s*X)?`, never
# `\s*X?\s*`: two `\s*` beside an absent piece can split one run of spaces
# every possible way, and a run that leads nowhere then costs cubic time.
# A whole word, so "/yearly" is not read as "/year" with "ly" left over
# between the amount and the dash; an abbreviation may carry its full stop
# ("$174,900/yr. to $215,000/yr.").
_PERIOD_WORD = r"(?:(?:year|month|hour)(?:ly)?|annum|annually|(?:yr|mo|hr)\.?)(?![A-Za-z])"
# "$140,000/yr", "$140,000 per year", "$140,000 a year", "$140,000 annually".
_PER_PERIOD = (
    r"(?:\s*(?:(?:/\s*|per\s+|an?\s+)" + _PERIOD_WORD + r"|(?:annually|yearly|monthly|hourly)(?![A-Za-z])))?"
)
#: The two amounts may go without a separator only when the LOW one is money
#: too. Without that, the zone or level number in front of a band, "Zone 1
#: $284,800—$385,200" or "I4 $130,600—$192,000", is read as a low of 1 or 4.
#: That reading fails the ratio test, but the match has already consumed the
#: real band's low amount, so the scan never sees the band at all.
_NO_SEPARATOR = (
    r"(?(symbol)\s+" + _MONEY_AHEAD
    + r"|(?(lead_currency)\s+" + _MONEY_AHEAD
    + r"|(?(low_currency)\s+" + _MONEY_AHEAD + r"|(?!))))"
)
_EXPLICIT_BAND_RE = re.compile(
    # Never from inside a run of whitespace: a match from there is a match from
    # the run's first space, and every start in the run would read the rest of it.
    r"(?!(?<=\s)\s)"
    # A code before the low amount, Workday's and SAP's "USD 150,000 - 200,000".
    r"(?:(?P<lead_currency>" + CURRENCY_CODE + r")\s*+)?"
    r"(?:(?<![A-Za-z])(?P<prefix>US|CA|C|A|NZ|HK|S)[ \xa0]?)?(?P<symbol>[$£€])?\s*"
    r"(?P<low>" + AMOUNT + r")(?:\s*(?P<low_suffix>[kKmM](?![A-Za-z])))?"
    r"(?:\s*(?P<low_currency>" + CURRENCY_CODE + r"))?" + _PER_PERIOD +
    r"(?:\s*(?:[-–—]|to\b|and\b)\s*|" + _NO_SEPARATOR + r")"
    # The code repeated before the high amount: "USD $160,200 - USD $425,000",
    # "EUR 133,600 - EUR 160,320".
    r"(?:(?P<high_lead_currency>" + CURRENCY_CODE + r")\s*+)?"
    r"(?:(?:(?<![A-Za-z])(?P<high_prefix>US|CA|C|A|NZ|HK|S)[ \xa0]?)?(?P<high_symbol>[$£€])\s*)?"
    r"(?P<high>" + AMOUNT + r")\s*(?P<high_suffix>[kKmM](?![A-Za-z]))?" + _PER_PERIOD +
    r"(?:\s*(?P<currency>" + CURRENCY_CODE + r"))?",
    re.IGNORECASE,
)

#: A band whose bounds are split by words, not a separator:
#:
#:     base pay for this position ranges from $133,900/year in our
#:     lowest geographic market up to $231,400/year in our highest
#:
#: `_EXPLICIT_BAND_RE` joins two amounts only by a dash, "to" or "and", so
#: it reads this as no band at all. Narrow on purpose: "from", then a money
#: amount with its symbol, then words only (no digit, no currency sign, no
#: sentence end, at most 80 characters), then "to" or "up to" and a second
#: amount with its symbol (some employers write the sentence with a bare
#: "to"). Both bounds still pass `_read_candidate` and are grounded like any
#: other band.
#:
#: "between" opens the same shape, and closes it with "to" or "and":
#:
#:     the reasonably expected salary range is between $132,500 [minimum
#:     salary in our lowest geographic market] to $184,000 [maximum ...]
_FROM_UP_TO_RE = re.compile(
    r"\b(?:from|(?P<between>between))\s+"
    r"(?:(?<![A-Za-z])(?P<prefix>US|CA|C|A|NZ|HK|S)[ \xa0]?)?(?P<symbol>[$£€])\s*"
    r"(?P<low>" + AMOUNT + r")(?:\s*(?P<low_suffix>[kKmM](?![A-Za-z])))?"
    r"\s*(?:(?P<low_currency>" + CURRENCY_CODE + r")" + _PER_PERIOD + r"|/\s*" + _PERIOD_WORD + r")?"
    r"[^\d$£€.;!?\n]{0,80}?\b(?:(?:up\s+)?to|(?(between)and|(?!)))\s+"
    r"(?:(?<![A-Za-z])(?P<high_prefix>US|CA|C|A|NZ|HK|S)[ \xa0]?)?(?P<high_symbol>[$£€])\s*"
    r"(?P<high>" + AMOUNT + r")\s*(?P<high_suffix>[kKmM](?![A-Za-z]))?" + _PER_PERIOD +
    r"(?:\s*(?P<currency>" + CURRENCY_CODE + r"))?",
    re.IGNORECASE,
)

#: A band whose bounds are named minimum and maximum, each with its own amount:
#:
#:     Salary Min: $120,000  Salary Max: $160,000
#:     minimum base salary for this role ... is $150,000 per year; maximum
#:     base salary for this role is $200,000 per year
#:
#: The words between may hold no digit and no currency sign, so a
#: "minimum of 5 years" never reaches a figure. Grounding still demands both
#: amounts within one short span.
_MIN_MAX_RE = re.compile(
    r"\bmin(?:imum)?\b[^\d$£€\n]{0,80}?"
    r"(?:(?<![A-Za-z])(?P<prefix>US|CA|C|A|NZ|HK|S)[ \xa0]?)?(?P<symbol>[$£€])\s*"
    r"(?P<low>" + AMOUNT + r")(?:\s*(?P<low_suffix>[kKmM](?![A-Za-z])))?"
    r"(?:\s*(?P<low_currency>" + CURRENCY_CODE + r"))?" + _PER_PERIOD +
    r"[^\d$£€\n]{0,80}?\bmax(?:imum)?\b[^\d$£€\n]{0,80}?"
    r"(?:(?<![A-Za-z])(?P<high_prefix>US|CA|C|A|NZ|HK|S)[ \xa0]?)?(?P<high_symbol>[$£€])\s*"
    r"(?P<high>" + AMOUNT + r")\s*(?P<high_suffix>[kKmM](?![A-Za-z]))?" + _PER_PERIOD +
    r"(?:\s*(?P<currency>" + CURRENCY_CODE + r"))?",
    re.IGNORECASE,
)

#: A figure the posting states ONCE, as the pay itself rather than as the end
#: of a range:
#:
#:     The base salary for this role is $150,000 per year.
#:     Pay: $48,000 annually
#:     Base Salary: $200,000
#:     $75,000 Annual Salary
#:
#: One amount is far weaker evidence than two. Two amounts joined by a dash are
#: a range whatever surrounds them; a lone figure in a posting is more often a
#: sign-on bonus, a tuition cap or a travel allowance than it is pay. So this
#: pattern carries the words that make it pay INSIDE the match: a pay label,
#: then at most 60 characters holding no digit, no currency sign and no
#: sentence end. `_figure_states_pay` then reads what the label hands off to
#: and what the amount is called afterwards, and `rank` puts every one-amount
#: candidate behind every band, so a figure can only be read where no range is.
#:
#: The pattern states no `high` group, which is what makes it a one-amount
#: candidate: `_read_candidate` reads the band's two bounds off the one amount,
#: and `_one_bound` is that absence.
#: Horizontal space only, for a pattern that must stay on one line.
_H_SPACE = r"[^\S\n]"


def _pay_label(space: str) -> str:
    """The pay words a figure's label is made of, joined by `space`.

    The trailing-label pattern passes horizontal space, so no part of a label
    it reads can sit on the line below the amount."""
    return (
        r"(?:base" + space + r"++)?(?:salar(?:y|ies)|compensation|wages?|"
        r"pay(?:" + space + r"++(?:range|rate|scale))?)"
    )


_PAY_LABEL = _pay_label(r"\s")
_LABELLED_FIGURE_RE = re.compile(
    r"\b(?P<label>" + _PAY_LABEL + r")\b(?P<gap>[^\d$£€.;!?\n]{0,60}?)"
    r"(?:(?<![A-Za-z])(?P<prefix>US|CA|C|A|NZ|HK|S)[ \xa0]?)?(?P<symbol>[$£€])\s*+"
    r"(?P<low>" + AMOUNT + r")(?:\s*+(?P<low_suffix>[kKmM](?![A-Za-z])))?"
    r"(?:\s*+(?P<low_currency>" + CURRENCY_CODE + r"))?" + _PER_PERIOD +
    r"(?:\s*+(?P<currency>" + CURRENCY_CODE + r"))?",
    re.IGNORECASE,
)

#: The same figure with its label AFTER it: "$75,000 Annual Salary". Every gap
#: in it is horizontal space, so the whole match sits on the amount's own line:
#: the next line is a new statement, and a label read across the break turns
#: "Programme cost: $75,000\nyearly salary reviews apply" into pay. Excluding
#: the newline from `gap` alone leaves the period and currency fragments, and
#: the label's own words, to cross it.
_H_PERIOD = (
    r"(?:" + _H_SPACE + r"*+(?:(?:/" + _H_SPACE + r"*+|per" + _H_SPACE + r"++|an?" + _H_SPACE + r"++)"
    + _PERIOD_WORD + r"|(?:annually|yearly|monthly|hourly)(?![A-Za-z])))?"
)
_FIGURE_LABELLED_RE = re.compile(
    r"(?:(?<![A-Za-z])(?P<prefix>US|CA|C|A|NZ|HK|S)[ \xa0]?)?(?P<symbol>[$£€])" + _H_SPACE + r"*+"
    r"(?P<low>" + AMOUNT + r")(?:" + _H_SPACE + r"*+(?P<low_suffix>[kKmM](?![A-Za-z])))?"
    r"(?:" + _H_SPACE + r"*+(?P<low_currency>" + CURRENCY_CODE + r"))?" + _H_PERIOD +
    r"(?:" + _H_SPACE + r"*+(?P<currency>" + CURRENCY_CODE + r"))?"
    r"(?P<gap>[^\d$£€.;!?\n]{0,20}?)\b"
    r"(?P<label>(?:annual(?:ly)?" + _H_SPACE + r"++|yearly" + _H_SPACE + r"++)?"
    + _pay_label(_H_SPACE) + r")\b",
    re.IGNORECASE,
)

#: Every pattern a band is read with, in the order candidates are gathered.
_BAND_PATTERNS = (
    _EXPLICIT_BAND_RE, _FROM_UP_TO_RE, _MIN_MAX_RE, _LABELLED_FIGURE_RE, _FIGURE_LABELLED_RE,
)

#: A dollar sign with a country in front of it is not a US dollar. Read from
#: either number's prefix — a band writes it on both ("CA$142,000 - CA$190,000")
#: or only on the first.
_DOLLAR_CURRENCIES = {"US": "USD", "CA": "CAD", "C": "CAD", "A": "AUD", "NZ": "NZD", "HK": "HKD", "S": "SGD"}
_SIGN_CURRENCIES = {"£": "GBP", "€": "EUR"}


def _has_currency_evidence(match: re.Match) -> bool:
    """Is this candidate money at all, rather than any two numbers with a dash?

    The whole safety of an optional symbol rests here. Without it the pattern
    matches "a team of 5 to 10 engineers" and leans entirely on plausibility
    bounds to reject it — which they would, at every scale but the one where a
    headcount and a salary overlap.
    """
    groups = match.groupdict()
    return bool(
        groups["symbol"] or groups["low_currency"] or groups["currency"]
        or groups.get("lead_currency") or groups.get("high_lead_currency") or groups.get("high_symbol")
    )


# Local evidence that a currency range IS compensation. Used only to RANK
# equally-plausible candidates, never to reject one, so a terse band ("USA, KY,
# HEBRON - 151,200.00 - 204,600.00 USD annually", which carries no pay word at
# all) is still accepted. A bare "annual" is deliberately absent: "$3-4B annual
# logistics spend" has it.
_PAY_CONTEXT_RE = re.compile(
    r"(?:salar\w*|compensation|remuneration|\bwage\b|\bpay\b|\bpaid\b|total rewards|"
    r"/\s*hr\b|per\s+hour|hourly|per\s+year|pay\s+range|pay\s+scale|\bearnings\b)",
    re.IGNORECASE,
)


_CONTEXT_PAD = 160  # window either side of a candidate when ranking it


#: Money a sentence names as something other than pay. Magnitude alone would
#: let "Sign-on bonus of $50,000 - $100,000", an equity grant, a relocation sum
#: or a budget store a base band whenever no salary competed. Read only in the candidate's LEAD: what comes
#: after a band ("plus bonus and equity") is what it leaves out.
_OTHER_MONEY_RE = re.compile(
    r"\b(?:bonus(?:es)?|sign[- ]?on|equity|grants?|rsus?|stock|relocation|stipends?|"
    r"allowances?|budgets?|revenue|arr|spend|funding)\b",
    re.IGNORECASE,
)
#: A pay word in the same lead keeps the candidate: "The base salary range,
#: before bonus, is ..." is about pay.
_PAY_LEAD_RE = re.compile(
    r"\b(?:salar(?:y|ies)|base|wages?|hourly|pay|compensation|ote|earnings)\b", re.IGNORECASE
)
#: How far back each kind of word is read, never past the sentence's start.
#: The money a range is refused for sits just before it ("Sign-on bonus of ");
#: a pay word anywhere in the sentence's lead keeps it. "Base Salary + Equity
#: (if applicable) + Bonus (if applicable) $150,000-$180,000" names its pay
#: 60+ characters back, while a benefits list flattened into pay text can put
#: "stipend" 70 characters before a salary with no sentence end between.
_OTHER_MONEY_PAD = 50
_PAY_LEAD_PAD = 100
_SENTENCE_END_RE = re.compile(r"[.;!?](?:\s|$)|\n")


def _sentence_lead(pay_text: str, match: re.Match, pad: int) -> str:
    lead = pay_text[max(0, match.start() - pad) : match.start()]
    ends = list(_SENTENCE_END_RE.finditer(lead))
    return lead[ends[-1].end() :] if ends else lead


def _label_names_other_money(pay_text: str, match: re.Match) -> bool:
    """Does the words a pattern opens with, before its first amount, name money
    that is not pay?

    `_names_other_money` reads only what comes BEFORE a match. `_MIN_MAX_RE`
    opens on "Minimum", so in "Minimum annual bonus: $100,000; maximum annual
    bonus: $150,000" the word "bonus" sits INSIDE the match, where that check
    cannot see it. A label naming a pay word ("Minimum base salary") is kept,
    by the same exception.

    BOTH labels are read, because each bound carries its own: "Minimum base
    salary: $120,000; maximum annual bonus: $160,000" names two different
    components, and joining them states a band no employer wrote.
    """
    labels = [pay_text[match.start() : match.start("low")]]
    if not _one_bound(match):
        labels.append(pay_text[match.end("low") : match.start("high")])
    for label in labels:
        if _OTHER_MONEY_RE.search(label) and not _PAY_LEAD_RE.search(label):
            return True
    return False


def _names_other_money(pay_text: str, match: re.Match) -> bool:
    """Does the candidate's own sentence, just before it, say this money is
    not pay, with no pay word in its lead?"""
    return bool(_OTHER_MONEY_RE.search(_sentence_lead(pay_text, match, _OTHER_MONEY_PAD))) and not (
        _PAY_LEAD_RE.search(_sentence_lead(pay_text, match, _PAY_LEAD_PAD))
    )


def _one_bound(match: re.Match) -> bool:
    """Does this candidate state ONE amount rather than two?

    The pattern says so by having no `high` group at all, so there is no second
    bound to read, to label or to ground."""
    return "high" not in match.groupdict()


#: Words that hand a pay label off to other money: "Competitive salary plus a
#: $10,000 signing bonus" is a bonus the word "salary" introduced. A band needs
#: no such check — "$150,000 - $180,000 plus bonus" is a band and its extras —
#: but a lone figure after one of these words is the extra itself.
_HANDS_OFF_RE = re.compile(
    r"\+|\b(?:plus|and|with|along|addition|includes?|including|as\s+well)\b", re.IGNORECASE
)
#: How far past a lone figure its own noun can sit ("$10,000 signing bonus").
_FIGURE_TRAIL_PAD = 30
#: Words that make a figure ONE END of a range the posting never completes:
#: "a minimum of $120,000", "up to $70,000", "starting at $150,000", "is >
#: $250,000", and a "+" written on the amount itself ("$110,000+"). A "+" with
#: a space before it is not one: "Salary: $185,000 + Bonus" states a base and
#: what is added to it. A band stores two bounds and
#: nothing that says a bound is open, so reading such a figure as the pay would
#: invent the end the employer withheld: an open bound is a missed band.
_ONE_SIDED_RE = re.compile(
    r"\b(?:min(?:imum)?|max(?:imum)?|up\s+to|at\s+(?:least|most)|start(?:s|ing)?\s+(?:at|from)|"
    r"from|as\s+(?:much|little|low|high)\s+as|over|under|above|below|exceed(?:s|ing)?|"
    r"north\s+of|upwards?\s+of|no\s+less\s+than|begin(?:s|ning)?\s+at|"
    r"(?:greater|more|less|fewer)\s+than)\b|[><≥≤]",
    re.IGNORECASE,
)
#: How far before the figure a one-sided word reaches, when it sits outside the
#: match ("Minimum base salary: $120,000" labels the figure from in front).
_ONE_SIDED_PAD = 40
#: Another amount the lone figure may be a bound of. Money-sized only: a
#: currency sign with digits, a grouped number, four digits and more, or a
#: number written with its scale, so "(40 hours per week)" and "for level 3 and
#: 4 roles" are not amounts. A scale needs no currency of its own: "Base
#: salary: $120k for junior roles to 180k for senior roles" names its high
#: bound as plainly as any band does, at any number of digits ("$900k for this
#: role or 1m for the lead role"). "401k" is the retirement plan, not an
#: amount, and it sits beside a salary in every other posting.
_OTHER_AMOUNT_RE = re.compile(
    r"[$£€]\s*\d|\d{1,3},\d{3}|\d{4,}"
    r"|(?<!\d)(?!401\s*\(?[kK])\d{1,3}(?:\.\d+)?\s*+[kKmM](?![A-Za-z])"
)
#: Words that open a bound AFTER the amount: "$120,000 minimum", "$120,000 or
#: more", "$120,000 and above". "plus" is not one of them, because "$200,000,
#: plus a discretionary bonus" states a base and what is added to it.
_TRAILING_ONE_SIDED_RE = re.compile(
    r"\b(?:min(?:imum)?|max(?:imum)?|or\s+(?:more|above|higher|less|lower)|"
    r"and\s+(?:above|up|higher))\b",
    re.IGNORECASE,
)
#: How far either way a second amount makes the figure part of a range.
_FIGURE_ALONE_PAD = 80


def _figure_states_pay(pay_text: str, match: re.Match) -> bool:
    """Is the ONE amount this candidate states the pay its label names?

    Money a pay label introduces and then hands to something else is refused,
    on either side of the amount:

    - the label hands off before the amount ("Competitive salary plus a
      $10,000 signing bonus", "Pay for this role includes a $10,000 bonus");
    - the amount is called other money straight after it ("$5,000 relocation
      stipend"). A noun reached through one of the hand-off words is what the
      pay EXCLUDES, not what it is, so "$150,000 per year plus bonus and
      equity" keeps its band.

    An open bound is refused as well, whether the word that opens it comes
    before the amount ("up to $70,000", "a minimum of $120,000") or after it
    ("$120,000 minimum", "$120,000 or more"), and a "+" written on the amount
    opens one too: see `_ONE_SIDED_RE` and `_TRAILING_ONE_SIDED_RE`.

    A second amount in the same statement refuses it too, whichever side it
    sits: the figure is then one bound of a range this module failed to read,
    and the low end of a range is not the pay. That is the whole of
    "$181,000-$290,00 per year" (a typo breaks the high bound), "ranges from
    $120,000 in some markets up to 180,000 in others" (no currency on the
    high) and "from $90,000 for level 3 and 4 roles, up to $140,000" (a number
    between the bounds). Each must stay a missed band rather than become a
    figure the posting never stated alone.
    """
    gap = match.group("gap") or ""
    if _OTHER_MONEY_RE.search(gap) or _HANDS_OFF_RE.search(gap):
        return False
    if _ONE_SIDED_RE.search(gap) or _ONE_SIDED_RE.search(
        _sentence_lead(pay_text, match, _ONE_SIDED_PAD)
    ):
        return False
    # Past the amount's own scale, so a "+" on "$180K+" is read where a "+" on
    # "$180,000+" is.
    amount_ends = match.end("low_suffix") if match.group("low_suffix") else match.end("low")
    if pay_text[amount_ends : amount_ends + 1] == "+":
        return False
    trail = pay_text[match.end() : match.end() + _FIGURE_TRAIL_PAD]
    stop = _SENTENCE_END_RE.search(trail)
    trail = trail[: stop.start()] if stop else trail
    named = _OTHER_MONEY_RE.search(trail)
    if named and not _HANDS_OFF_RE.search(trail[: named.start()]):
        return False
    if _TRAILING_ONE_SIDED_RE.search(trail):
        return False
    statement = pay_text[match.end() : match.end() + _FIGURE_ALONE_PAD]
    stop = _SENTENCE_END_RE.search(statement)
    after = statement[: stop.start()] if stop else statement
    return not (
        _OTHER_AMOUNT_RE.search(after)
        or _OTHER_AMOUNT_RE.search(_sentence_lead(pay_text, match, _FIGURE_ALONE_PAD))
    )


_MAX_BAND_RATIO = 10  # real bands are usually under 3x; 10x is generous


class _Reading(NamedTuple):
    """What one regex candidate says before it is grounded."""

    low: int
    high: int
    currency: str | None
    period: PayPeriod
    #: Yearly by an agreeing word, or by a size that can only be yearly. Such
    #: a candidate outranks every other: "Phone stipend: $1,000 - $1,500 per
    #: month. Salary range: $150,000 - $200,000." states the salary second.
    #: A no-word amount where month and year overlap does not count: a
    #: "signing bonus of €10,000 - €15,000" must not displace a monthly salary.
    salary: bool


#: Comma groups a written amount can have: at most three digits first, then
#: groups of two or three (Indian "12,00,000"), and three last. Anything else
#: is a typo that dropped or doubled a digit: "$181,000-$290,00" read with the
#: comma removed is a band from $29,000, and "$215,0000 - $305,000" one up to
#: $2,150,000.
_GROUPED_RE = re.compile(r"\d{1,3}(?:,\d{2,3})*,\d{3}")


def _bound(raw: str, suffix: str | None) -> int | None:
    """One bound's amount, or None for an amount written with a broken comma
    group. A k or m that would lift a number already written in thousands
    past any pay ("$174,000K/year") repeats the thousands: the amount is the
    number as written. Only a reading no band could hold is reinterpreted, so
    a k that is the real scale ("$150k") keeps it."""
    # The amount pattern takes a comma that ends the clause ("$120,000, paid
    # monthly") with the digits; it is punctuation, not a group. A doubled
    # comma ("$200,,000") loses no digit and reads as one.
    whole = re.sub(r",+", ",", raw.split(".", 1)[0]).rstrip(",")
    if "," in whole and not _GROUPED_RE.fullmatch(whole):
        return None
    value = explicit_amount(raw, suffix)
    if suffix and value is not None and value > MAX_COMP:
        plain = explicit_amount(raw, None)
        if plain is not None and plain >= 1_000:
            return plain
    return value


def _read_candidate(match: re.Match, pay_text: str) -> _Reading | None:
    """The amounts, currency and period ONE regex candidate states, or None."""
    groups = match.groupdict()
    low_suffix, high_suffix = groups["low_suffix"], groups.get("high_suffix")
    # "$245-$280K" and "$120–$140k" write the scale once, on the high amount:
    # a bare low under a thousand shares it. A low written in full ("$90,000 -
    # $110,000k") keeps its own size.
    if high_suffix and not low_suffix and (bare := explicit_amount(match.group("low"), None)) is not None and bare < 1_000:
        low_suffix = high_suffix
    low = _bound(match.group("low"), low_suffix)
    # A one-amount candidate's band is that amount at both bounds: a figure
    # stated once bounds itself, and grounding then asks the posting for the
    # one number it does state.
    high = low if _one_bound(match) else _bound(match.group("high"), high_suffix)
    if low is None or high is None:
        return None
    low, high = sorted((low, high))
    if low <= 0 or high > low * _MAX_BAND_RATIO:
        return None
    if high > MAX_COMP:
        # What the band model may store. A won salary sits inside the yearly
        # size class and above this, where building the band raised and
        # stopped the pass: a missed band, never a crash.
        return None
    # A code after the LOW number is as authoritative as one after the high —
    # "168,000 USD - 258,750" states its currency exactly once, and reading only
    # the trailing position would store that band with no currency at all.
    codes = {
        code.upper()
        for code in (groups["currency"], groups["low_currency"], groups.get("lead_currency"), groups.get("high_lead_currency"))
        if code
    }
    # "£" and "€" name a currency as surely as a code. A "$" does not: postings
    # write it beside other codes ("$81 - $139 EUR"), a zone letter before it
    # reads as a dollar prefix ("Zone A\n$190,000"), and a dollar band can carry
    # a stray sign ("$150,000 - £180,000" for New York). So one dollar sign never
    # makes two currencies; the code, where there is one, decides. Only a country
    # prefix on BOTH dollar signs, naming two ("CA$150,000 - US$180,000"), does
    # when no code settles it. A prefix sits on its sign's line: a letter on the
    # line above ("Zone A\n$190,000") is a label.
    named = codes | {_SIGN_CURRENCIES[sign] for sign in (groups.get("symbol"), groups.get("high_symbol")) if sign in _SIGN_CURRENCIES}
    dollar_prefixes = {
        _DOLLAR_CURRENCIES[sign_prefix.upper()]
        for sign_prefix in (groups.get("prefix"), groups.get("high_prefix"))
        if sign_prefix
    }
    both_prefixed = bool(groups.get("prefix") and groups.get("high_prefix"))
    if len(named) > 1 or (not codes and both_prefixed and len(dollar_prefixes) > 1):
        # Two bounds in two currencies are two figures, not one band.
        return None
    explicit_currency = next(iter(codes), None)
    prefix = (groups.get("prefix") or groups.get("high_prefix") or "").upper()
    symbol = groups.get("symbol") or groups.get("high_symbol") or ""
    symbol_currency = {"$": "USD", "£": "GBP", "€": "EUR"}.get(symbol)
    if symbol_currency == "USD" and prefix:
        symbol_currency = _DOLLAR_CURRENCIES.get(prefix, "USD")
    currency = (explicit_currency or symbol_currency or "").upper() or None
    sizes = size_classes(low, high, currency)
    words = attached_words(pay_text, match.start(), match.end())
    period = decide_period(sizes, words)
    if period is None:
        return None
    salary = period is PayPeriod.year and (words is PayPeriod.year or sizes == (PayPeriod.year,))
    return _Reading(low, high, currency, period, salary)


def _locate_figure(description_text: str, amount: int) -> tuple[int, int] | None:
    """Where the posting states `amount` AS PAY, for a band of one amount.

    `locate_pay_span` grounds a band by its two bounds, and the tightest span
    holding both pins it to the right statement. One amount has no second bound
    to pin it: every occurrence of the number is an equally tight span, and the
    first one wins. So a posting that says "Customers: 150,000" before "The
    base salary for this role is $150,000 per year" would be quoted, and have
    its basis read, at the customer count.

    The figure patterns are therefore read again over the full posting, under
    every filter a candidate passes, and the first occurrence they state as pay
    is the band's place. The filters are what make it the band's place rather
    than any labelled occurrence: "Bonus pay: $150,000" is refused here as it
    is refused as a candidate, so a salary of the same figure further down is
    not quoted, or settled, at the bonus. Grounding holds by construction: the
    span is a match in `description_text`."""
    for pattern in (_LABELLED_FIGURE_RE, _FIGURE_LABELLED_RE):
        for match in pattern.finditer(description_text):
            if _bound(match.group("low"), match.group("low_suffix")) != amount:
                continue
            if (
                _names_other_money(description_text, match)
                or _label_names_other_money(description_text, match)
                or not _figure_states_pay(description_text, match)
            ):
                continue
            ends = match.end("low_suffix") if match.group("low_suffix") else match.end("low")
            return match.start("low"), ends
    return None


def _grounded(reading: _Reading, description_text: str, *, one_bound: bool = False) -> DisclosedComp:
    """The band `reading` states, grounded in the full posting, or `disclosed=False`.
    Located once: the quote, the basis and the bonus all read the same span."""
    span = (
        _locate_figure(description_text, reading.low)
        if one_bound
        else locate_pay_span(description_text, [reading.low, reading.high])
    )
    if span is None:
        return DisclosedComp(disclosed=False)
    basis = basis_at(description_text, span)
    return DisclosedComp(
        disclosed=True,
        base_min=reading.low,
        base_max=reading.high,
        currency=reading.currency,
        pay_basis=basis,
        pay_period=reading.period,
        source_snippet=quote_at(description_text, span),
        confidence="high",
        bonus_pct=derive_bonus_pct(description_text, span, basis),
    ).located(span)


def _has_pay_context(pay_text: str, match: re.Match) -> bool:
    window = pay_text[
        max(0, match.start() - _CONTEXT_PAD) : min(len(pay_text), match.end() + _CONTEXT_PAD)
    ]
    return bool(_PAY_CONTEXT_RE.search(window))


#: The cities and metro areas a short place string names. Injected by the
#: caller (`enrich.classify.specific_places`): place names live a layer up.
PlaceReader = Callable[[str], frozenset[str]]

#: Where a band's label stops reaching back: a sentence that starts a new
#: statement ("per year. There is a different range ..."), or a new line.
_LABEL_BREAK_RE = re.compile(r"[.!?](?=\s+[A-Z])|\n")
#: A band whose place FOLLOWS it: "$258,000 - $348,000 in San Francisco and
#: $235,000 - $317,000 in Chicago". A code or a period word may come between.
_PLACE_AFTER_RE = re.compile(
    r"\s*(?:(?:[A-Z]{3}|annually|per\s+(?:year|annum)|a\s+year|/\s*(?:year|yr))\b\.?\s*)*"
    r"(?:[,(]\s*)?(?:in|for|within|at)\b",
    re.IGNORECASE,
)
#: A place a band is NOT for: "California (excluding Bay Area)".
_NOT_THERE_RE = re.compile(
    r"\b(?:excluding|except(?:\s+for)?|other\s+than|outside(?:\s+of)?|not\s+including)\b[^;:)\n]*",
    re.IGNORECASE,
)
#: Splits a label into place-sized pieces the place reader can read.
_PLACE_PIECE_RE = re.compile(r"[,;:()\[\]•●–—/|\n]|\s-\s|\s(?:and|or)\s")
#: "For roles based in Pittsburgh" reads as "Pittsburgh".
_PLACE_LEAD_RE = re.compile(r"^.*\b(?:in|within|for|at|across)\s+(?:the\s+)?", re.IGNORECASE)
_LABEL_REACH = 400
_PLACE_TAIL_REACH = 160


def _band_labels(pay_text: str, matches: Sequence[re.Match]) -> dict[tuple[int, int], str]:
    """The words that say which place each band is for, by the band's span.

    Every accepted band bounds its neighbours, so a label never reaches past
    another band: before a band, back to the previous band (or a new
    statement); after it, an "in <place>" clause up to the next band or the
    sentence's end, which the next band's label then does not repeat."""
    spans = sorted({(m.start(), m.end()) for m in matches})
    labels: dict[tuple[int, int], str] = {}
    claimed = 0
    for index, (start, end) in enumerate(spans):
        following = spans[index + 1][0] if index + 1 < len(spans) else len(pay_text)
        before = pay_text[max(claimed, start - _LABEL_REACH):start]
        breaks = list(_LABEL_BREAK_RE.finditer(before))
        if breaks:
            before = before[breaks[-1].end():]
        tail, after = pay_text[end:following], ""
        if _PLACE_AFTER_RE.match(tail):
            stop = _LABEL_BREAK_RE.search(tail)
            after = tail[: stop.start() if stop else min(len(tail), _PLACE_TAIL_REACH)]
            # "For Austin based hires: ... $200,000" labels the NEXT band: a
            # clause that ends in a colon is that band's, never this one's.
            if ":" in after:
                after = ""
        claimed = end + len(after)
        labels[(start, end)] = before + " " + after
    return labels


def _named_places(label: str, places_in: PlaceReader) -> frozenset[str]:
    """Every city and metro area a band's label names, less the ones it
    excludes ("California (excluding Bay Area)")."""
    found: set[str] = set()
    for piece in _PLACE_PIECE_RE.split(_NOT_THERE_RE.sub(" ", label)):
        piece = piece.strip()
        if piece:
            found |= places_in(piece) | places_in(_PLACE_LEAD_RE.sub("", piece))
    return frozenset(found)


def extract_grounded_band(
    pay_text: str,
    description_text: str,
    *,
    place: frozenset[str] = frozenset(),
    places_in: PlaceReader | None = None,
) -> DisclosedComp:
    """THE salary-band parser. No model is involved in this path.

    It recovers only two literal, co-located currency amounts, and `find_pay_span`
    grounds them against the complete stored posting — so the failure mode is
    a missed band, not an invented one. Grounding proves the numbers are the
    posting's, not that they are pay: a range its own sentence names as other
    money (a bonus, a grant, a budget) is refused before it is ranked. That
    asymmetry is what lets it replace the model outright rather than merely
    back it up.

    `pay_text` is what we READ (a connector-isolated pay section when one exists,
    else the whole posting); `description_text` is what we ground AGAINST, and
    must always be the full stored text.

    EVERY candidate range is considered. Taking `search()`'s first match
    would lose real bands two ways: a section mentioning any earlier currency
    range would win outright ("$3-4B annual logistics spend" before the actual
    "$159000 - $231000 (USD)" further down the same section would store a $3-$4
    salary), and a first match that failed to ground would end the scan even
    when a later one would have grounded.

    Two filters, in order of trustworthiness. `size_classes` and `decide_period`
    REJECT a range that cannot be pay at any scale. The survivors
    are RANKED: a salary (yearly by its word or by a size that can only be
    yearly) first, so a stipend or a budget stated before it cannot displace
    it; then a band of two amounts before a figure stated once, which is the
    weaker statement and is read only where no range is; then pay wording
    nearby, because prose is the weaker signal (a budget figure can sit one
    sentence away from the word "pay") and a terse band carrying no pay word at
    all must still be accepted.

    A posting may state one band per place: a national range and its Bay Area
    and New York one, "select cities", zones, cities. The comp model shows the
    band for the job's location (`docs/pay.md`), so with the posting's first
    `place` (cities and metro areas) and a `places_in` reader, the band whose
    own label names that place is taken, if exactly one does. Without a place,
    or when no band or two name it, the order above decides.
    """
    readings = [
        (reading, match)
        for pattern in _BAND_PATTERNS
        for match in pattern.finditer(pay_text or "")
        if _has_currency_evidence(match)
        and not _names_other_money(pay_text, match)
        and not _label_names_other_money(pay_text, match)
        and (not _one_bound(match) or _figure_states_pay(pay_text, match))
        and (reading := _read_candidate(match, pay_text)) is not None
    ]
    # Stable sort: among equally-ranked candidates the earliest wins.
    # Grounding is the
    # expensive step, so it runs in rank order and stops at the first band.
    def rank(pair: tuple[_Reading, re.Match]) -> tuple[bool, bool, bool]:
        return (not pair[0].salary, _one_bound(pair[1]), not _has_pay_context(pay_text, pair[1]))

    # `rank` alone leaves the order each pattern was scanned in, so a band one
    # pattern reads later in the posting would beat an equally ranked one
    # another pattern read earlier. Position breaks the tie; `rank` itself stays
    # as it is, because the place selection below compares ranks for equality.
    readings.sort(key=lambda pair: (*rank(pair), pair[1].start()))
    # Several bands, one per place: the one for the posting's place.
    # Only among the best-ranked, and only when exactly one band names it: two
    # that do, or none, leave the order above to decide.
    # A posting states a RANGE per place, so only two-amount candidates are
    # considered: a lone figure overlaps the band it was read inside, and a
    # label bounded by that overlap names a place for neither.
    bands = [pair for pair in readings if not _one_bound(pair[1])]
    if place and places_in is not None and len({(r.low, r.high) for r, _ in bands}) > 1:
        labels = _band_labels(pay_text, [m for _, m in bands])
        best = rank(bands[0])
        named = [
            (r, m) for r, m in bands
            if rank((r, m)) == best and _named_places(labels[(m.start(), m.end())], places_in) & place
        ]
        if len({(r.low, r.high, r.currency) for r, _ in named}) == 1:
            band = _grounded(named[0][0], description_text)
            if band.disclosed:
                return band
    for reading, match in readings:
        band = _grounded(reading, description_text, one_bound=_one_bound(match))
        if band.disclosed:
            return band
    return DisclosedComp(disclosed=False)


_MAX_SPAN_CHARS = 200  # bounds must co-occur within one pay statement, not across the JD


_QUOTE_PAD = 50  # context kept either side of the numbers in the stored quote


# pay_basis markers routinely sit outside the stored quote (a "+ equity" tail,
# a lead-in sentence a paragraph above), so basis is derived from a wider window.
_BASIS_PAD = 300


# ...and the window is then grown to whole paragraphs, because a marker split in half
# by a fixed pad says nothing. A posting can print "The base salary range for this
# position is listed below.", then several hundred characters of benefits prose, then
# the band on its own line: the declaration and the number it declares are one block,
# and a +-300 window reaches neither end of it. Growing to the paragraph leaves a
# genuinely ambiguous band `unclear`.
_BASIS_BLOCK = "\n\n"


# The ceiling that keeps this a window and not the whole document: a posting written as
# one giant paragraph must not pull a bonus sentence from a screen away (the marker-leak
# regression test pins exactly that).
_BASIS_MAX = 1200


#: The high amount of a range that writes its "k" once, on that amount
#: ("$245-$280K"): the low before it is in thousands too (`_read_candidate`).
#: Every run of whitespace is taken possessively (`\s*+`, as the band patterns
#: above take theirs): nothing after a run is whitespace, so giving one back can
#: never help a match, and a run that leads nowhere is then read once instead of
#: at every split of itself.
_SHARED_K_AHEAD_RE = re.compile(r"\s*+(?:[-–—]|\bto\b)\s*+[$£€]?\s*+\d{1,3}(?:\.\d+)?\s*+[kK](?![A-Za-z])")


def _number_positions(text: str) -> list[tuple[int, int, int]]:
    """(value, start, end) for every number in `text`, including k/m scaling."""
    found: list[tuple[int, int, int]] = []
    text = text or ""
    for m in NUM_RE.finditer(text):
        raw, suffix = m.group(1), (m.group(2) or "").lower()
        if not suffix and _SHARED_K_AHEAD_RE.match(text, m.end()):
            suffix = "k"
        values: set[int] = set()
        for value in number_readings(raw, suffix):
            values.add(int(value))
            if suffix == "k":
                values.add(int(value * 1_000))
            elif suffix == "m":
                values.add(int(value * 1_000_000))
        for v in values:
            found.append((v, m.start(), m.end()))
    return found


def locate_pay_span(description_text: str, bounds: list[int]) -> tuple[int, int] | None:
    """Return `(start, end)` offsets of the tightest span of `description_text` that
    states every bound, else None. See `find_pay_span` for the grounding rationale."""
    if not description_text or not bounds:
        return None

    positions: dict[int, list[tuple[int, int]]] = {}
    for value, start, end in _number_positions(description_text):
        positions.setdefault(value, []).append((start, end))
    if any(b not in positions for b in bounds):
        return None

    best: tuple[int, int] | None = None
    for combo in product(*(positions[b] for b in bounds)):
        lo = min(s for s, _ in combo)
        hi = max(e for _, e in combo)
        if hi - lo <= _MAX_SPAN_CHARS and (best is None or (hi - lo) < (best[1] - best[0])):
            best = (lo, hi)
    return best


def find_pay_span(description_text: str, bounds: list[int]) -> str | None:
    """Return a VERBATIM span of the posting that states every bound, else None.

    This is the grounding gate. We do not trust the model's own snippet: it has been
    observed stitching two non-adjacent sentences into a quote that never appears
    contiguously in the posting, which a naive substring check wrongly rejects even
    though the numbers were right. Instead we locate the numbers ourselves and slice
    the quote out of the source, so the stored snippet is guaranteed verbatim.

    The anti-hallucination guarantee is preserved (and tightened): every bound must
    literally occur in the posting, and all bounds must sit within one short span —
    so a fabricated figure, a digit slip, or a value the model *derived* (e.g.
    annualizing an hourly rate) has nowhere to match.
    """
    span = locate_pay_span(description_text, bounds)
    return None if span is None else quote_at(description_text, span)


def quote_at(description_text: str, span: tuple[int, int]) -> str:
    """The stored quote for a band located at `span`: the numbers with some
    context either side, whitespace collapsed."""
    lo, hi = span
    quote = description_text[max(0, lo - _QUOTE_PAD) : min(len(description_text), hi + _QUOTE_PAD)]
    return _WS_RE.sub(" ", quote).strip()[:240]


_SENTENCE_RE = re.compile(r"(?<=[.!?;:\n])\s+")


# The band bundles bonus/commission/equity => "total".
# "range includes" and "inclusive of" are only about pay when they NAME a pay component.
# Bare, they fire on any range at all: "our product range includes Pixel phones", "may
# be inclusive of several career levels", "objectives inclusive of quality, yield, and
# cost". Each can sit in the same block as a real base band, so without the component
# requirement a wider window turns a correct `base` into `total`.
_INCLUSIVE_RE = re.compile(
    r"\brange\s+(?:also\s+)?includes\b[^.]{0,60}"
    r"\b(?:bonus|equity|stock|commission|incentive|variable|benefits|target)\b"
    r"|\bincludes\s+both\b"
    # Not after "not": Lyft's "base pay range ... not inclusive of potential equity
    # offering, bonus or benefits" says the opposite (`_ADDITIVE_RE` reads it).
    r"|(?<!\bnot\s)\binclusive\s+of\b[^.]{0,60}\b(?:bonus|equity|stock|commission|incentive|variable)\b"
    r"|\bon[-\s]target\s+earnings\b"
    r"|\bOTE\b"
    r"|\btotal\s+(?:target\s+)?(?:cash\s+)?compensation\s+range\b",
    re.I,
)


# Bonus/equity are stated as ADDED to the band => the band itself is "base".
_ADDITIVE_RE = re.compile(
    r"\+\s*\d+\s*(?:%\s*)?(annual\s+)?(bonus|target)"
    r"|\+\s*(equity|bonus|stock|benefits)"
    r"|\bplus\b[^.]{0,40}\b(bonus|equity|stock|commission)\b"
    r"|\b(in\s+addition(\s+to)?|additionally)\b[^.]{0,90}\b(bonus|equity|stock)\b"
    r"|\beligible\s+(to\s+participate\s+in|to\s+receive|for)\b[^.]{0,90}\b(bonus|equity|stock|incentive)\b"
    r"|\bdoes\s+not\s+include\b[^.]{0,60}\b(bonus|equity|stock)\b"
    r"|\bexclusive\s+of\b[^.]{0,40}\b(bonus|equity)\b"
    r"|\bnot\s+inclusive\s+of\b[^.]{0,60}\b(bonus|equity|stock)\b"
    # The package names what comes ON TOP of the band: Zipline's "The total
    # compensation package for this role may also include: equity compensation;
    # discretionary annual or performance bonuses", PayPal's "Additional compensation
    # for this role may include an annual performance bonus, equity", Brex's "equity
    # and other forms of compensation may be provided as part of a total compensation
    # package".
    r"|\bpackage\b[^.]{0,60}\bmay\s+(also\s+)?include\b[^.]{0,120}\b(bonus(es)?|equity|stock)\b"
    r"|\badditional\s+compensation\b[^.]{0,60}\bmay\s+include\b[^.]{0,80}\b(bonus|equity|stock|incentive)\b"
    r"|\b(equity|bonus|stock)\b[^.]{0,80}\bmay\s+be\s+provided\s+as\s+part\s+of\b",
    re.I,
)


# The posting names the band "base salary" outright.
# The last alternative is Amazon's geographic-market sentence, "The base pay for this
# position ranges from $196,900/year ... up to $340,300/year": an explicit base statement
# that the `base <noun> range` forms miss on the plural verb alone (`ranges` breaks the
# word boundary after `range`).
_BASEWORD_RE = re.compile(
    r"\bbase\s+(salary|pay|compensation)\s+(range|band)\b"
    r"|\bbase\s+(salary|pay|compensation)\s*:"
    r"|\brange\s+for\s+(the\s+)?base\s+salary\b"
    r"|\bbase\s+salary\s+range\b"
    r"|\bbase\s+(salary|pay|compensation)\b[^.]{0,60}\branges?\s+from\b"
    # Brex's "the starting base pay will depend on ...", PayPal's "The base pay for this
    # role will depend on where you work": the band's own sentence names it base.
    r"|\bstarting\s+base\s+(salary|pay)\b"
    r"|\bbase\s+(salary|pay)\s+for\s+this\s+(role|position)\b",
    re.I,
)


# Netflix defines the published amount as eligible compensation and lets the
# employee elect its cash/options mix. The range is therefore total compensation,
# even though the posting also says "annual salary" and has no bonus.
_EMPLOYEE_ELECTION_RE = re.compile(
    r"choose\s+(?:each\s+year\s+)?how\s+much\s+of\s+(?:your\s+)?compensation\s+"
    r"(?:you\s+want\s+)?in\s+(?:salary|hourly\s+pay)\s+versus\s+stock\s+options",
    re.I,
)


# A marker inside a CONDITIONAL clause says nothing about THIS posting's band.
# Anthropic pastes "For sales roles, the range provided is the role's On Target
# Earnings ("OTE") range, meaning that the range includes both the sales
# commissions/sales bonuses target and annual base salary for the role." onto every
# posting — Engineering Managers and Research Engineers included. Read literally it
# would mislabel every non-sales band as "total".
# `commissionable` is Databricks' spelling of the same conditional: "the expected salary
# range for non-commissionable roles or on-target earnings for commissionable roles".
_CONDITIONAL_RE = re.compile(
    r"\bfor\s+(sales|commissioned|commissionable|non-commissionable|certain|some|eligible|these)\s+roles\b"
    # ServiceNow's boilerplate under every band: "Sales positions generally offer a
    # competitive On Target Earnings (OTE) incentive compensation structure."
    r"|\bsales\s+(positions|roles)\s+(generally|typically|usually)\b"
    r"|\bif\s+(you|this|the\s+role|applicable)\b"
    r"|\bwhere\s+applicable\b"
    r"|\bfor\s+roles\s+that\b"
    r"|\bin\s+some\s+cases\b",
    re.I,
)


# The band means one thing for sales roles and another for the rest, stated as such:
# Databricks' "expected salary range for non-commissionable roles or on-target earnings
# for commissionable roles", Palo Alto's "starting base salary (for non-sales roles) or
# base salary + commission target (for sales/commissioned roles)". Which it is depends
# on the role, which this text-only reader cannot see, so it stays `unclear`; an
# additive marker beside it ("the package may also include ... equity") holds for both
# kinds of role and must not settle it.
_ROLE_SPLIT_RE = re.compile(
    r"\b(range|salary)\b[^.]{0,40}\bfor\s+non-?(sales|commissionable|commissioned)\s+roles\b"
    r"|\(for\s+non-?sales\s+roles\)\s+or\b",
    re.I,
)


def basis_context(description_text: str, span: tuple[int, int]) -> str:
    """The text that describes the band at `span`: its paragraph, plus a pad each side.

    Grown from `_BASIS_PAD` outward to the enclosing `\n\n` block so a marker is either
    wholly in or wholly out, then clipped at `_BASIS_MAX` so a posting with no paragraph
    breaks cannot pull in the whole document. Both edges move independently: a band on
    its own line (Amazon's "USA, WA, Seattle - 179,900.00 - 243,400.00 USD annually") is
    its own paragraph, so it is the LEFT edge that has to reach the sentence declaring
    what the number means.
    """
    lo, hi = span
    length = len(description_text)
    left, right = max(0, lo - _BASIS_PAD), min(length, hi + _BASIS_PAD)
    floor, ceiling = max(0, lo - _BASIS_MAX), min(length, hi + _BASIS_MAX)
    if left > 0:
        found = description_text.rfind(_BASIS_BLOCK, floor, left)
        left = found + len(_BASIS_BLOCK) if found != -1 else floor
    if right < length:
        found = description_text.find(_BASIS_BLOCK, right, ceiling)
        right = found if found != -1 else ceiling
    return description_text[left:right]


def _fires_unconditionally(pattern: re.Pattern[str], context: str) -> bool:
    """True iff `pattern` matches in some sentence of `context` that is not guarded by
    a conditional clause appearing before the match."""
    for sentence in _SENTENCE_RE.split(context):
        match = pattern.search(sentence)
        if match is None:
            continue
        guard = _CONDITIONAL_RE.search(sentence)
        if guard is not None and guard.start() < match.start():
            continue
        return True
    return False


def derive_pay_basis(description_text: str, bounds: list[int]) -> PayBasis:
    """Derive pay_basis from the posting text around the located band.

    Precedence: an unconditional inclusive marker wins (the posting says the range
    bundles bonus/commission), else an employee-elected salary/options mix means total,
    else an additive marker means extras sit on top of the band so the band is base,
    else explicit "base salary" is enough. Absent a marker: `unclear`.
    """
    span = locate_pay_span(description_text, bounds)
    return PayBasis.unclear if span is None else basis_at(description_text, span)


def basis_at(description_text: str, span: tuple[int, int]) -> PayBasis:
    """`derive_pay_basis` for a band already located at `span`."""
    lo, hi = span
    context = basis_context(description_text, span)
    election_context = description_text[max(0, lo - 700) : min(len(description_text), hi + 300)]
    return _basis_of(context, election_context)


def _basis_of(context: str, election_context: str) -> PayBasis:
    if _fires_unconditionally(_INCLUSIVE_RE, context):
        return PayBasis.total
    if _EMPLOYEE_ELECTION_RE.search(election_context):
        return PayBasis.total
    if _ROLE_SPLIT_RE.search(context):
        return PayBasis.unclear
    if _ADDITIVE_RE.search(context):
        return PayBasis.base
    if _BASEWORD_RE.search(context):
        return PayBasis.base
    return PayBasis.unclear


def basis_from_label(label: str) -> PayBasis:
    """The basis a pay LABEL states on its own, by the same markers and the
    same conditional guard as `derive_pay_basis`.

    For a structured pay tier on a posting page: its title is the only text
    beside the amount, so it is the whole context. One rule
    for both, or the same words read two ways: "Base salary range (total
    compensation also includes equity)" is base, and "Salary range, see Total
    Rewards below" says nothing, where a bare `total` word called both total.
    """
    return _basis_of(label or "", label or "")


# The posting says what its range means for each kind of role, anywhere in it:
# Adobe "for sales roles starting salaries are expressed as total target compensation
# (TTC = base + commission) ... Non-sales roles starting salaries are expressed as base
# salary", Anthropic "For sales roles, the range provided is the role's On Target
# Earnings ("OTE") range", Databricks "expected salary range for non-commissionable
# roles or on-target earnings for commissionable roles", Palo Alto "starting base
# salary (for non-sales roles) or base salary + commission target". One sentence that
# names a kind of role and what the range or salary is for it.
_ROLE_DEFINITION_RE = re.compile(
    r"\bnon-?\s?(?:sales|commissionable|commissioned)\s+roles\b"
    r"|\bfor\s+sales\s+roles\b[^.]{0,120}\b(?:on[-\s]target|OTE|total\s+target\s+compensation|commission)",
    re.I,
)
_RANGE_WORD_RE = re.compile(r"\b(?:salary|salaries|range|base\s+pay)\b", re.I)


def defines_band_by_role(description_text: str | None) -> bool:
    """Does the posting define its range per kind of role (sales vs the rest)?
    A bonus plan "for eligible non-sales roles" names no range or salary and is
    not such a definition."""
    for sentence in _SENTENCE_RE.split(description_text or ""):
        if _ROLE_DEFINITION_RE.search(sentence) and _RANGE_WORD_RE.search(sentence):
            return True
    return False


def basis_for_role(
    basis: str | None, description_text: str | None, family: str | None, title: str | None = None,
) -> str | None:
    """The basis of a band whose posting defines it per kind of role.

    Only an `unclear` band is settled: a marker the band's own text states (base,
    or Netflix's total) wins. Then a non-sales role's band is base and a sales
    role's is total, as the employer defines them; a role that cannot be placed
    (pre-sales, customer success, a customer-facing architect, no family) stays
    unclear.
    """
    if basis != PayBasis.unclear.value or not defines_band_by_role(description_text):
        return basis
    selling = sells(family, title)
    if selling is None:
        return basis
    return PayBasis.total.value if selling else PayBasis.base.value


# The posting calls the band a salary: Accenture's "Annual Salary Range",
# KPMG's "California Salary Range:", Applied Materials' "Salary:", Elastic's "typical
# starting salary range". A band its paragraph calls a salary is base; the exceptions
# are an employee election (`_EMPLOYEE_ELECTION_RE`) and "OTE" (`_INCLUSIVE_RE`), both
# read first.
_SALARY_RE = re.compile(
    r"\b(?:annual\s+)?salary(?:\s+range)?\s*:"
    r"|\b(?:annual|starting|expected|typical|estimated|anticipated)?\s*salary\s+range\b"
    r"|\bannual\s+salary\b",
    re.I,
)


_FORWARD_SALARY_RE = re.compile(
    r"(?:^|\n)(?:Salary and Other Compensation:\s*)?"
    r"The annual salary range for this (?:position|role) is (?:displayed|listed) below\.",
    re.I,
)
_RANGE_HEADING_RE = re.compile(r"(?:^|\n)(?:Pay|Salary)\s+Range(?:\s*:)?(?:\s*[$€£])?\s*$", re.I)


def _forward_salary(text: str, span: tuple[int, int]) -> bool:
    """Follow an explicit salary reference across benefits to one labelled band.

    Multiple bands or conflicting definitions cannot identify which amount the
    reference describes. The ordinary paragraph window stays bounded.
    """
    declarations = list(_FORWARD_SALARY_RE.finditer(text))
    if len(declarations) != 1:
        return False
    declaration = declarations[0]
    if not 0 <= span[0] - declaration.end() <= 2500:
        return False
    link = text[declaration.end():span[0]]
    definition = text[declaration.end():]
    if (not _RANGE_HEADING_RE.search(link)
            or _INCLUSIVE_RE.search(definition) or _CONDITIONAL_RE.search(definition)):
        return False
    ranges = [match for pattern in _BAND_PATTERNS
              for match in pattern.finditer(text, declaration.end())
              if _has_currency_evidence(match)]
    return (len(ranges) == 1
            and ranges[0].start() <= span[0] and ranges[0].end() >= span[1])


def names_salary(description_text: str | None, bounds: Sequence[int | None]) -> bool:
    """Does the posting call this band a salary, outside a conditional clause?
    Never for Netflix's employee election, where "salary" is the cash the person
    chooses out of a total."""
    text = description_text or ""
    return _names_salary_at(text, _locate(text, bounds))


def _locate(text: str, bounds: Sequence[int | None]) -> tuple[int, int] | None:
    stated = [b for b in bounds if b is not None]
    return locate_pay_span(text, stated) if stated else None


def _names_salary_at(text: str, span: tuple[int, int] | None) -> bool:
    if span is None or _EMPLOYEE_ELECTION_RE.search(text):
        return False
    return (_fires_unconditionally(_SALARY_RE, basis_context(text, span))
            or _forward_salary(text, span))


#: Pay countries whose postings state base pay when they state one range.
#: Their pay-transparency rules make a posting carry a pay figure at all, and
#: the figure employers there print under a bare label is conventionally the
#: base salary; a selling role's may be on-target earnings instead. What each
#: rule demands differs by state and province, and some ask for expected
#: compensation rather than base, so this is a reading of what postings say,
#: not of what any one law requires. Elsewhere an unmarked range stays
#: `unclear`.
BASE_BY_CONVENTION_COUNTRIES = frozenset({"US", "CA"})

#: Words that call a range more than base pay without saying what it adds:
#: "estimated total compensation for this role ranges from", "Our cash
#: compensation range", "total compensation around 90-115k". Not markers of
#: `total` on their own, but the convention never reads such a range as base.
_NOT_JUST_BASE_RE = re.compile(
    r"\btotal\s+(?:target\s+|annual\s+|starting\s+)*(?:cash\s+)?(?:compensation|comp|pay|earnings|rewards\s+range)\b"
    r"|\bcash\s+compensation\b|\btotal\s+cash\b|\bon[-\s]target\b|\bOTE\b",
    re.I,
)


def _settled_basis(
    basis: str | None, text: str, family: str | None, title: str | None, span: tuple[int, int] | None,
    country: str | None,
) -> str | None:
    if basis != PayBasis.unclear.value:
        return basis
    if defines_band_by_role(text):
        return basis_for_role(basis, text, family, title)
    if _names_salary_at(text, span):
        return PayBasis.base.value
    # Last, so every marker the posting states wins over the convention, and
    # never for a role that sells or one whose kind cannot be told: its one
    # range may be on-target earnings. A connector's band arrives unread by the
    # text's markers, so an election, an inclusive range or one its paragraph
    # calls total or cash pay is checked here.
    if (
        country in BASE_BY_CONVENTION_COUNTRIES
        and sells(family, title) is False
        # A band we cannot find in the text has no paragraph to read, so the
        # wording that would refuse the convention cannot be checked at all. A
        # source's figures need not appear in its prose, and reading such a
        # band as base on a rule we could not test is the invented fact this
        # module exists to refuse.
        and span is not None
        and not _EMPLOYEE_ELECTION_RE.search(text)
        and not _calls_more_than_base(basis_context(text, span))
    ):
        return PayBasis.base.value
    return basis


def _calls_more_than_base(context: str) -> bool:
    return (_fires_unconditionally(_INCLUSIVE_RE, context)
            or _fires_unconditionally(_NOT_JUST_BASE_RE, context))


class SettledBand(NamedTuple):
    """What every writer stores beside a band's bounds."""

    pay_basis: str | None
    bonus_pct: float | None


def settle_band(
    basis: str | None,
    description_text: str | None,
    family: str | None,
    title: str | None,
    bounds: Sequence[int | None],
    *,
    span: tuple[int, int] | None = None,
    stated_bonus: float | None = None,
    country: str | None = None,
) -> SettledBand:
    """The basis and the stated bonus every writer of a band stores (connector,
    text, page).

    Only an `unclear` band is settled; a basis its markers state wins. A band the
    posting defines per kind of role takes the role's reading (`basis_for_role`);
    otherwise a band its paragraph calls a salary is base, and so is one whose
    pay `country` (`taxonomy.locations.pay_country`) posts base pay by
    convention, for a role that does not sell. The bonus is read
    after that, against the settled basis: "Salary range: $150,000 - $200,000
    per year. Annual bonus target of 15%." is a base band with a 15% target,
    though no marker made it base before the word "salary" settled it. Only a
    base band carries a bonus share.

    `span` is where the band sits in `description_text` when the caller has
    located it already (`DisclosedComp.span`); otherwise it is located here.
    `stated_bonus` is a share the source read beside the band itself: a
    connector scans its own pay block before the posting's sections are stored,
    and carving that block into its own section can move the band away from
    the bonus sentence, so the source's reading stands over the stored text's."""
    text = description_text or ""
    if span is None:
        span = _locate(text, bounds)
    settled = _settled_basis(basis, text, family, title, span, country)
    if settled != PayBasis.base.value:
        return SettledBand(settled, None)
    if stated_bonus is not None:
        return SettledBand(settled, stated_bonus)
    return SettledBand(settled, derive_bonus_pct(text, span, settled))


# A target bonus stated as a share of base: Google's "+ 25% bonus target", or the
# longer "eligible for an annual bonus of 15% of base salary". Bounded to a sane
# range so a stray percentage elsewhere in the posting (equity refresh rates, 401k
# match, "top 10%") cannot be mistaken for a bonus target.
# The percentage is read whole: every decimal it is written with ("+ 42.86% bonus
# target" is 42.86), and never from inside a longer number ("142.86%" is not 42.86,
# and "42.86%" is not 86).
_BONUS_PCT = r"(?<![\d.])(\d{1,2}(?:\.\d+)?)"
_BONUS_PCT_RE = re.compile(
    r"\+\s*" + _BONUS_PCT + r"\s*%\s*(?:annual\s+)?(?:bonus|target)"
    r"|" + _BONUS_PCT + r"\s*%\s*(?:annual\s+|target\s+|discretionary\s+)*bonus(?:\s+target)?"
    r"|bonus[^.]{0,30}?\bof\s+" + _BONUS_PCT + r"\s*%",
    re.I,
)


_BONUS_PCT_MAX = 0.60  # above this it is not a bonus target; drop rather than guess


def derive_bonus_pct(
    description_text: str, span: tuple[int, int] | None, basis: str | None,
) -> float | None:
    """The target bonus the posting STATES as a share of base, e.g. 0.25, else None,
    read around the band located at `span` whose basis is `basis`.

    Only meaningful when the band itself is base salary: a "25% bonus target" says the
    bonus is 25% OF BASE, so pairing it with a band that bundles bonus already (total),
    or one whose meaning the employer never declared (unclear), would be nonsense. So
    this returns None unless `basis` is `base`, the same guard-rail logic that keeps
    us from inventing facts the posting did not state. A writer passes the settled
    basis (`settle_band`), so a band that only its salary wording makes base still
    carries the bonus its paragraph states.
    """
    if basis != PayBasis.base.value or span is None:
        return None
    context = basis_context(description_text, span)

    match = _BONUS_PCT_RE.search(context)
    if match is None:
        return None
    raw = next((g for g in match.groups() if g), None)
    if raw is None:
        return None
    pct = float(raw) / 100.0
    if not (0.0 < pct <= _BONUS_PCT_MAX):
        return None
    return round(pct, 4)

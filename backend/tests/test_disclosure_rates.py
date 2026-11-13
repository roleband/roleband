"""Pure-logic tests for the pay-disclosure RATE and its daily snapshot grain (no DB).

The rate answers a different question from `build_posted_pay` and gets its
denominator from a different place, so the two things this suite exists to stop
are: (1) counting roles the extraction pass has not read yet as employer silence,
which would make the rate track our own backlog; (2) letting the basis rules that
govern band *values* leak into the rate, which is basis-independent.
"""

from __future__ import annotations

from datetime import UTC, datetime

from tracker.analytics.comp_stats import (
    build_disclosure_rates,
    build_disclosure_snapshot_rows,
    build_posted_pay,
)

READ = datetime(2026, 7, 20, tzinfo=UTC)  # structured_at: the pass has read this role
UNREAD = None  # structured_at NULL: not yet examined


def _role(company, band, *, checked=READ, lo=None, hi=None, basis=None, currency="USD", period=None):
    """One (company, level_band, structured_at, base_min, base_max, pay_basis,
    currency, pay_period) row: the rate reads the first six columns."""
    return (company, band, checked, lo, hi, basis, currency, period)


def _posted_rows(rows):
    """The same roles as `build_posted_pay` rows, every one in a US place."""
    return [(c, b, "stated", lo, hi, basis, cur, per, ["silicon_valley"]) for c, b, _chk, lo, hi, basis, cur, per in rows]


def _level(rates, band):
    return next(lvl for lvl in rates["by_level"] if lvl["level_band"] == band)


# --- the denominator ---------------------------------------------------------


def test_unread_roles_are_excluded_from_the_rate_denominator():
    # 2 read roles, 1 of which discloses -> 50%. The 6 unread roles are backlog,
    # not silence: counting them would report 1/8 = 12.5% and make the rate track
    # extraction progress instead of employer behaviour.
    rows = [
        _role("google", "senior", lo=200_000, hi=300_000, basis="base"),
        _role("google", "senior"),
        *[_role("google", "senior", checked=UNREAD) for _ in range(6)],
    ]
    rates = build_disclosure_rates(rows)

    assert rates["overall"]["rate"] == 0.5
    assert rates["overall"]["checked"] == 2
    # `open` is still reported so the UI can state the backlog rather than hide it.
    assert rates["overall"]["open"] == 8
    assert rates["overall"]["disclosed"] == 1


def test_a_band_the_text_pass_has_not_read_still_discloses():
    """A stored band is evidence on its own: a posting page or a
    connector stated it, whether or not the text pass has read the posting.
    Only the ABSENCE of a band needs the text read to mean "stated nothing"."""
    rows = [
        _role("meta", "staff", checked=UNREAD, lo=300_000, hi=400_000, basis="base"),
        _role("meta", "staff", checked=UNREAD),  # the control: unread, no band
    ]
    rates = build_disclosure_rates(rows)

    assert rates["overall"]["disclosed"] == 1
    assert rates["overall"]["checked"] == 1
    assert rates["overall"]["rate"] == 1.0


def test_rate_is_none_not_zero_when_nothing_has_been_checked():
    rates = build_disclosure_rates([_role("openai", "senior", checked=UNREAD)])
    # 0.0 would assert "this employer publishes nothing", which we have not observed.
    assert rates["overall"]["rate"] is None
    assert _level(rates, "senior")["rate"] is None


# --- basis independence ------------------------------------------------------


def test_rate_counts_every_basis_while_bands_keep_only_base():
    # Netflix states a range but never says whether it bundles equity ("unclear"),
    # and one role quotes total comp. Both employers DID publish pay, so all three
    # count toward the rate — while the band chart, which needs a single axis,
    # keeps only the base row.
    rows = [
        _role("google", "senior", lo=200_000, hi=300_000, basis="base"),
        _role("netflix", "senior", lo=440_000, hi=725_000, basis="unclear"),
        _role("amazon", "senior", lo=350_000, hi=500_000, basis="total"),
    ]
    rates = build_disclosure_rates(rows)
    assert rates["overall"]["rate"] == 1.0
    assert rates["overall"]["disclosed"] == 3

    posted = build_posted_pay(_posted_rows(rows))
    [us] = posted["countries"]
    assert [b["company"] for b in us["bands"]] == ["google"]
    assert posted["excluded"]["not_base"] == 2


def test_a_stated_band_with_no_basis_still_counts_as_disclosed():
    rows = [_role("figma", "senior", lo=180_000, hi=240_000, basis=None)]
    rates = build_disclosure_rates(rows)
    assert rates["overall"]["disclosed"] == 1

    # ...and lands under "unclear" in the snapshot, so it can never be pooled with
    # base pay by a downstream aggregate that trusts the basis column.
    cells = build_disclosure_snapshot_rows(rows)
    assert [c["pay_basis"] for c in cells] == ["unclear"]


def test_a_placeholder_band_counts_in_the_rate_but_never_as_a_salary():
    # Anthropic posts a literal "Annual Salary: $1-$2 USD" on some reqs. The
    # employer did state a range, so the rate counts it; it is not a salary, so it
    # must not enter a band percentile.
    rows = [_role("anthropic", "senior", lo=1, hi=2, basis="base")]

    assert build_disclosure_rates(rows)["overall"]["rate"] == 1.0
    cells = build_disclosure_snapshot_rows(rows)
    assert cells[0]["pay_basis"] == "base"
    assert cells[0]["roles"] == 1
    assert cells[0]["bands"] == []


def test_a_band_in_another_currency_or_period_discloses_but_never_enters_the_dollar_bands():
    # The trend draws these bands as yearly US dollars. A pound band, a rupee
    # band and a monthly band all clear the floor by size, so only their
    # currency and period keep them out; a band stored with no currency is a
    # dollar band.
    rows = [
        _role("deepmind", "senior", lo=80_000, hi=120_000, basis="base", currency="GBP", period="year"),
        _role("flipkart", "senior", lo=3_500_000, hi=6_000_000, basis="base", currency="INR", period="year"),
        _role("acme", "senior", lo=55_000, hi=70_000, basis="base", currency="USD", period="month"),
        _role("google", "senior", lo=200_000, hi=300_000, basis="base", currency=None, period=None),
    ]
    cells = {c["company"]: c for c in build_disclosure_snapshot_rows(rows)}

    assert {c: (cell["roles"], cell["pay_basis"], cell["bands"]) for c, cell in cells.items()} == {
        "deepmind": (1, "base", []),
        "flipkart": (1, "base", []),
        "acme": (1, "base", []),
        "google": (1, "base", [{"low": 200_000, "high": 300_000, "reqs": 1}]),
    }
    assert build_disclosure_rates(rows)["overall"]["disclosed"] == 4

    # Posted pay reads the same roles in their own currency: the pound and
    # rupee ranges are counted apart from the US dollar figure, never converted.
    posted = build_posted_pay(_posted_rows(rows))
    [us] = posted["countries"]
    assert (us["currency"], [b["company"] for b in us["bands"]], us["other_currency"]) == ("USD", ["google"], 2)
    assert posted["excluded"]["not_yearly"] == 1


def test_a_one_sided_band_discloses_but_spans_nothing():
    rows = [_role("reddit", "senior", lo=190_000, hi=None, basis="base")]
    assert build_disclosure_rates(rows)["overall"]["disclosed"] == 1
    assert build_disclosure_snapshot_rows(rows)[0]["bands"] == []


# --- grouping and ordering ---------------------------------------------------


def test_groups_split_by_level_over_the_same_roles():
    rows = [
        _role("google", "senior", lo=200_000, hi=300_000, basis="base"),
        _role("google", "staff"),
        _role("meta", "staff", lo=300_000, hi=400_000, basis="base"),
    ]
    rates = build_disclosure_rates(rows)

    assert _level(rates, "senior") == {
        "level_band": "senior", "open": 1, "checked": 1, "disclosed": 1, "rate": 1.0
    }
    assert _level(rates, "staff")["rate"] == 0.5  # google staff silent, meta staff not
    assert rates["overall"]["rate"] == round(2 / 3, 4)


def test_levels_are_ordered_by_seniority():
    rows = [
        _role("google", "staff", lo=300_000, hi=400_000, basis="base"),
        _role("meta", "senior"),
        _role("openai", "director_plus", checked=UNREAD),
        _role("amazon", "mid", lo=150_000, hi=200_000, basis="base"),
        _role("amazon", "mid"),
    ]
    rates = build_disclosure_rates(rows)

    assert [lvl["level_band"] for lvl in rates["by_level"]] == [
        "mid", "senior", "staff", "director_plus"
    ]


def test_unclassified_level_uses_the_empty_sentinel_not_none():
    # Matches the CompSnapshot convention: the upsert conflict target stays NULL-free.
    rows = [_role("google", None, lo=200_000, hi=300_000, basis="base")]
    assert _level(build_disclosure_rates(rows), "")["disclosed"] == 1
    assert build_disclosure_snapshot_rows(rows)[0]["level_band"] == ""


# --- the snapshot grain ------------------------------------------------------


def test_snapshot_splits_silent_roles_into_the_empty_basis_cell():
    rows = [
        _role("google", "senior", lo=200_000, hi=300_000, basis="base"),
        _role("google", "senior"),
        _role("google", "senior", checked=UNREAD),
    ]
    cells = {c["pay_basis"]: c for c in build_disclosure_snapshot_rows(rows)}

    assert cells["base"]["roles"] == 1
    assert cells["base"]["checked"] == 1
    # The silent + unread roles share the "" cell; `checked` is what separates them.
    assert cells[""]["roles"] == 2
    assert cells[""]["checked"] == 1


def test_snapshot_collapses_repeated_bands_and_counts_the_reqs_on_each():
    # An employer publishes one band and hangs many reqs off it — the
    # stored unit is the distinct band, annotated with how many roles ride on it.
    rows = [
        *[_role("google", "senior", lo=200_000, hi=300_000, basis="base") for _ in range(3)],
        _role("google", "senior", lo=220_000, hi=320_000, basis="base"),
    ]
    cell = build_disclosure_snapshot_rows(rows)[0]

    assert cell["bands"] == [
        {"low": 200_000, "high": 300_000, "reqs": 3},
        {"low": 220_000, "high": 320_000, "reqs": 1},
    ]
    assert cell["roles"] == 4


def test_snapshot_never_mixes_two_bases_in_one_cell():
    rows = [
        _role("netflix", "staff", lo=440_000, hi=725_000, basis="unclear"),
        _role("netflix", "staff", lo=300_000, hi=400_000, basis="base"),
    ]
    cells = {c["pay_basis"]: c for c in build_disclosure_snapshot_rows(rows)}

    assert set(cells) == {"base", "unclear"}
    assert cells["base"]["bands"] == [{"low": 300_000, "high": 400_000, "reqs": 1}]
    assert cells["unclear"]["bands"] == [{"low": 440_000, "high": 725_000, "reqs": 1}]


def test_snapshot_cells_reconstruct_the_live_rate_exactly():
    """The stored history and the live endpoint must not be able to disagree.

    Two code paths compute disclosure from the same rows — the live rate from the
    jobs table, the trend from these cells. If summing the cells ever stopped
    matching, the Statistics panel and its own trend line would show different
    numbers for today.
    """
    rows = [
        _role("google", "senior", lo=200_000, hi=300_000, basis="base"),
        _role("google", "senior"),
        _role("google", "staff", checked=UNREAD),
        _role("netflix", "staff", lo=440_000, hi=725_000, basis="unclear"),
        _role("anthropic", "senior", lo=1, hi=2, basis="base"),
        _role("meta", "mid", checked=UNREAD, lo=150_000, hi=200_000, basis="base"),
    ]
    live = build_disclosure_rates(rows)["overall"]
    cells = build_disclosure_snapshot_rows(rows)

    assert sum(c["roles"] for c in cells) == live["open"]
    assert sum(c["checked"] for c in cells) == live["checked"]
    assert sum(c["roles"] for c in cells if c["pay_basis"]) == live["disclosed"]

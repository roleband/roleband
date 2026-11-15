"""Correcting stored pay periods the old rule got wrong.

Each text is verbatim from a real row, or the smallest edit of one. The rule
may relabel a band and repair a misread amount, never pick a different band and
never remove one.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from sqlalchemy import select

from tests.factories import make_job
from tracker.connectors.detail.ashby import AshbyDetailConnector
from tracker.db.models import Job
from tracker.intelligence_runtime import disclosed_comp
from tracker.intelligence_runtime.disclosed_comp import (
    correct_pay_periods,
    corrected_band,
    multi_year_share,
)
from tracker.pay_disclosure import extract_grounded_band
from tracker.pay_period import effective_period

NETFLIX = (
    "The range for this role is $600,000.00 - $1,066,000.00. This compensation range is "
    "determined by the market. Full-time hourly employees accrue 35 days annually for paid time off."
)
GOOGLE = "US: $163000 - $236000 (USD) + 15% bonus target + equity + benefits."
ELASTIC = "The typical starting salary range for this role is: €104.800—€165.700 EUR Additional Information"
VERCEL = (
    "San Francisco, CA pay range for this position is $382,000 - $485,000 OTE. "
    "New York pay range is $340,000 - $425,000 OTE."
)
COHERE = "Everyone receives a $500 home office stipend to set up your workspace."
# Words that contradict a size only a year can hold: a salary all the same.
CONTRADICTION = "Base pay: $150,000 - $200,000 per month, paid in arrears."
# Words that contradict a size month and year share: the rule cannot tell.
OVERLAP = "Base pay: $10,000 - $12,000 per hour."


def _ashby_quote(interval: str, low: int = 180_000, high: int = 220_000) -> str:
    """The quote the Ashby connector stores for a `low` - `high` band."""
    payload = {"compensation": {"summaryComponents": [{
        "compensationType": "Salary", "minValue": low, "maxValue": high,
        "currencyCode": "USD", "interval": interval,
    }]}}
    return AshbyDetailConnector().parse_payload(payload).source_disclosed_comp.source_snippet


def _read(text: str):
    band = extract_grounded_band(text, text)
    return band if band.disclosed else None


def test_the_same_amounts_read_again_take_the_new_period():
    assert corrected_band((600_000, 1_066_000, "USD", "hour"), _read(NETFLIX)) == {
        "disclosed_pay_period": "year"
    }


def test_a_stored_could_not_tell_is_a_candidate_only_when_its_size_settles_it():
    # A salary-sized amount stored `unclear` is served yearly, so the pass
    # relabels it from its own text, which now reads it yearly too.
    assert _read(CONTRADICTION).pay_period.value == "year"
    assert corrected_band((150_000, 200_000, "USD", "unclear"), _read(CONTRADICTION)) == {
        "disclosed_pay_period": "year"
    }
    # Where month and year share the size the rule still cannot tell: the
    # stored `unclear` is consistent, and re-reading it could only write it again.
    assert _read(OVERLAP).pay_period.value == "unclear"
    assert corrected_band((10_000, 12_000, "USD", "unclear"), _read(OVERLAP)) is None


def test_a_misread_european_amount_is_repaired_with_its_period():
    change = corrected_band((104, 165, "EUR", "year"), _read(ELASTIC))
    assert change is not None
    assert (change["disclosed_base_min"], change["disclosed_base_max"]) == (104_800, 165_700)
    assert change["disclosed_pay_period"] == "year"
    assert "€104.800" in change["disclosed_snippet"]


def test_another_band_in_the_same_posting_is_never_swapped_in():
    # Stored: the New York range. A re-read picks San Francisco's first. Both are
    # yearly, so the stored row is not even a candidate; and forced through, it
    # must still not be swapped.
    assert corrected_band((340_000, 425_000, "USD", "year"), _read(VERCEL)) is None
    assert corrected_band((340_000, 425_000, "USD", "unclear"), _read(VERCEL)) is None


def test_a_salary_whose_thousands_match_a_stored_small_band_is_not_a_repair():
    """The repair is for the "€104.800" misread only: the text must write the
    stored amounts with a dot before the thousands. Here the stored band is a
    real hourly range read as yearly and the posting also states a salary
    whose thousands happen to match; swapping it in is picking another band,
    not repairing a misread."""
    both = (
        "Contract rate: $150 - $200 per hour. Converts to full time at "
        "$150,000 - $200,000 per year."
    )
    reread = _read(both)
    assert (reread.base_min, reread.base_max) == (150_000, 200_000), "the salary ranks first"
    assert corrected_band((150, 200, "USD", "year"), reread) is None


def test_nothing_found_again_removes_nothing():
    # Cohere's stipend, stored as a $500 salary: the rule reads no pay at all.
    assert _read(COHERE) is None
    assert corrected_band((500, 500, "USD", "year"), None) is None


def test_a_band_already_consistent_is_not_touched():
    assert corrected_band((150_000, 200_000, "USD", "year"), _read(GOOGLE)) is None
    assert corrected_band((59, 89, "USD", "hour"), None) is None
    # A salary-sized amount called hourly is a salary: shown yearly, untouched.
    worded = "Hourly rate: $150,000 - $200,000"
    assert _read(worded).pay_period.value == "year"
    assert corrected_band((150_000, 200_000, "USD", "year"), _read(worded)) is None


def test_a_band_stored_whole_over_several_years_becomes_one_year_s_share():
    two_years = _ashby_quote("2 YEAR")
    assert "per 2 years" in two_years
    assert multi_year_share((180_000, 220_000, "USD", "unclear"), two_years) == {
        "disclosed_base_min": 90_000, "disclosed_base_max": 110_000, "disclosed_pay_period": "year",
    }
    # Read since the connector divides: already a year's share, never divided twice.
    assert multi_year_share((90_000, 110_000, "USD", "year"), two_years) is None
    # Where month and year share the share's size, the stated years still decide.
    assert multi_year_share((24_000, 28_000, "USD", "unclear"), _ashby_quote("2 YEAR", 24_000, 28_000)) == {
        "disclosed_base_min": 12_000, "disclosed_base_max": 14_000, "disclosed_pay_period": "year",
    }
    # A share no year can hold is left whole: dividing it again could never end.
    assert multi_year_share((600, 800, "USD", "unclear"), _ashby_quote("2 YEAR", 600, 800)) is None
    # Another band's quote never divides this one.
    assert multi_year_share((24_000, 28_000, "USD", "unclear"), two_years) is None
    # A count of years about something else never divides the band.
    beside = "Base pay: $180,000 - $220,000 per month; retention bonus paid per 2 years"
    assert multi_year_share((180_000, 220_000, "USD", "unclear"), beside) is None
    for joined in ("; bonus", " and bonus"):
        bonus = f"Base pay: $180,000 - $220,000 per month{joined} $20,000 per 2 years"
        assert multi_year_share((180_000, 220_000, "USD", "unclear"), bonus) is None, joined
    assert multi_year_share((180_000, 220_000, "USD", "unclear"), "$180K - $220K USD per 2 years") == {
        "disclosed_base_min": 90_000, "disclosed_base_max": 110_000, "disclosed_pay_period": "year",
    }
    # A quote that names no count of years is a year's pay as stated.
    assert multi_year_share((180_000, 220_000, "USD", "unclear"), _ashby_quote("1 YEAR")) is None
    assert multi_year_share((180_000, 220_000, "USD", "unclear"), CONTRADICTION) is None


def _row(key: str, text: str, low, high, currency, period) -> Job:
    return make_job(
        key, description_text=text, structured_at=datetime(2026, 9, 1, tzinfo=UTC),
        disclosed_base_min=low, disclosed_base_max=high,
        disclosed_currency=currency, disclosed_pay_period=period, disclosed_pay_basis="unclear",
    )


@pytest.mark.asyncio
async def test_the_pass_corrects_what_it_can_and_then_writes_nothing(db_session):
    db_session.add_all([
        _row("netflix", NETFLIX, 600_000, 1_066_000, "USD", "hour"),
        _row("contradiction", CONTRADICTION, 150_000, 200_000, "USD", "unclear"),
        _row("elastic", ELASTIC, 104, 165, "EUR", "year"),
        _row("cohere", COHERE, 500, 500, "USD", "year"),
        _row("right", GOOGLE, 163_000, 236_000, "USD", "year"),
    ])
    await db_session.commit()

    first = await correct_pay_periods(db_session)
    await db_session.commit()
    # The stored `unclear` salary is relabelled from its own text, once.
    assert first == {"candidates": 4, "relabelled": 2, "amounts_fixed": 1, "kept": 1}

    async def stored() -> dict:
        db_session.expire_all()
        return {
            job.req_id: (job.disclosed_base_min, job.disclosed_base_max,
                         job.disclosed_pay_period, job.disclosed_snippet)
            for job in (await db_session.scalars(select(Job))).all()
        }

    rows = await stored()
    assert {key: row[:3] for key, row in rows.items()} == {
        "netflix": (600_000, 1_066_000, "year"),
        "contradiction": (150_000, 200_000, "year"),
        "elastic": (104_800, 165_700, "year"),
        "cohere": (500, 500, "year"),  # kept: shown as "could not tell", never removed
        "right": (163_000, 236_000, "year"),
    }

    # Caught up: the one row still selected is the one no re-read can fix,
    # and the run writes nothing.
    again = await correct_pay_periods(db_session)
    await db_session.commit()
    assert again == {"candidates": 1, "relabelled": 0, "amounts_fixed": 0, "kept": 1}
    assert await stored() == rows


@pytest.mark.asyncio
async def test_a_run_killed_midway_keeps_the_batches_it_saved(db_session, monkeypatch):
    db_session.add_all([
        _row("netflix", NETFLIX, 600_000, 1_066_000, "USD", "hour"),
        _row("contradiction", CONTRADICTION, 150_000, 200_000, "USD", "unclear"),
    ])
    await db_session.commit()

    read = disclosed_comp.extract_grounded_band

    def dies_on_the_second_row(text, *args, **kwargs):
        if text == CONTRADICTION:
            raise RuntimeError("killed")
        return read(text, *args, **kwargs)

    monkeypatch.setattr(disclosed_comp, "_PERIOD_BATCH", 1)
    monkeypatch.setattr(disclosed_comp, "extract_grounded_band", dies_on_the_second_row)
    with pytest.raises(RuntimeError, match="killed"):
        await correct_pay_periods(db_session)
    await db_session.rollback()

    db_session.expire_all()
    periods = {job.req_id: job.disclosed_pay_period for job in (await db_session.scalars(select(Job))).all()}
    assert periods == {"netflix": "year", "contradiction": "unclear"}

    # The next run's candidates are only the row the killed one did not reach.
    monkeypatch.setattr(disclosed_comp, "extract_grounded_band", read)
    assert (await correct_pay_periods(db_session))["candidates"] == 1


@pytest.mark.asyncio
async def test_the_pass_divides_a_band_stored_whole_over_several_years(db_session):
    rows, quotes = [], {}
    for key, low, high in (("salary", 180_000, 220_000), ("overlap", 24_000, 28_000)):
        quote = quotes[key] = _ashby_quote("2 YEAR", low, high)
        legacy = _row(key, quote, low, high, "USD", "unclear")
        legacy.disclosed_snippet = quote
        legacy.disclosed_source = "connector"
        rows.append(legacy)
    db_session.add_all(rows)
    await db_session.commit()
    # Until the pass reads its quote, a whole multi-year band is never shown as a year.
    assert effective_period("unclear", 180_000, 220_000, "USD") == "unclear"

    assert (await correct_pay_periods(db_session))["amounts_fixed"] == 2
    db_session.expire_all()
    stored = {
        job.req_id: (job.disclosed_base_min, job.disclosed_base_max, job.disclosed_pay_period, job.disclosed_snippet)
        for job in (await db_session.scalars(select(Job))).all()
    }
    assert stored == {
        "salary": (90_000, 110_000, "year", quotes["salary"]),
        "overlap": (12_000, 14_000, "year", quotes["overlap"]),
    }

    # Divided once: neither row is a candidate again.
    assert (await correct_pay_periods(db_session))["candidates"] == 0

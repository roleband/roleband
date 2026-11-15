"""A pay-band refresh adds what it measures and forgets nothing.

The corpus holds only the postings it still sees. The postings that anchored a
range close, and the range goes on being what the company paid that year, so a
refresh that wrote its own measurement alone would drop ranges it could no
longer see and take their postings back to no level. These tests state what a
refresh may and may not do to the table it rewrites.
"""

from __future__ import annotations

import csv
from datetime import UTC, datetime
from types import SimpleNamespace

import pytest

from scripts.bench_level_bands import band_key, band_rows, held_rows, merge_rows

COLUMNS = ("company", "family", "base_min", "base_max", "year", "band", "anchor", "anchors")


@pytest.fixture
def stored():
    """A stored posting as the corpus hands it to `band_rows`: one US base
    range, posted in the measured year, at a company with no rung table."""

    def build(title: str, *, company: str = "acme",
              base_min: int = 200_000, base_max: int = 300_000) -> SimpleNamespace:
        return SimpleNamespace(
            id=abs(hash((company, title, base_min))) % 100_000, company=company, title=title,
            department=None, team=None, raw_level=None, description=None, status="open",
            disclosed_base_min=base_min, disclosed_base_max=base_max,
            disclosed_currency="USD", disclosed_pay_basis="base", disclosed_pay_period="year",
            posted_at=datetime(2026, 6, 1, tzinfo=UTC), first_posted_at=None,
            first_seen=datetime(2026, 6, 1, tzinfo=UTC),
        )

    return build


def row(company="acme", family="software_engineering", base_min=200_000, base_max=300_000,
        year=2026, band="staff", anchor="Staff Engineer", anchors=2) -> dict:
    return dict(zip(COLUMNS, (company, family, base_min, base_max, year, band, anchor, anchors),
                    strict=True))


def test_a_range_the_refresh_could_not_measure_is_kept():
    """The whole point: the postings that anchored it are gone, the range is
    not."""
    held = [row(base_min=180_000, base_max=260_000, band="senior")]

    merged = merge_rows(held, [row()], ())

    assert len(merged) == 2
    assert held[0] in merged


def test_fresh_evidence_wins_on_a_range_both_hold():
    """Not a duplicate, and not the stale reading: one row, the new band."""
    held = [row(band="senior", anchor="Senior Engineer", anchors=2)]

    merged = merge_rows(held, [row(band="staff", anchor="Staff Engineer", anchors=9)], ())

    assert len(merged) == 1
    assert (merged[0]["band"], merged[0]["anchors"]) == ("staff", 9)


def test_another_years_rows_survive_a_one_year_refresh():
    """One run measures one year. A 2026 refresh that dropped 2025 would delete
    a year of measurement nothing can re-measure."""
    held = [row(year=2025, band="principal"), row(year=2024, band="senior")]

    merged = merge_rows(held, [row(year=2026)], ())

    assert sorted(r["year"] for r in merged) == [2024, 2025, 2026]


def test_a_held_row_is_kept_when_the_refresh_measures_nothing():
    """A run against a corpus with no anchored range is not a reason to empty
    the table."""
    held = [row(), row(company="other", base_min=150_000, base_max=190_000)]

    assert merge_rows(held, [], ()) == sorted(held, key=band_key)


def test_the_table_is_written_in_one_order_however_the_rows_arrive():
    """Canonical order, so a refresh diffs as data rather than as a reshuffle."""
    held = [row(company="zeta"), row(company="alpha", base_max=310_000)]
    measured = [row(company="mid-co")]

    merged = merge_rows(held, measured, ())

    assert [r["company"] for r in merged] == ["alpha", "mid-co", "zeta"]
    assert merged == sorted(merged, key=band_key)


def test_a_range_is_matched_on_its_cell_and_both_bounds():
    """A refresh must not treat a revised range as the same row: the company
    moved a bound, and both figures are measured."""
    held = [row(base_max=301_000)]

    merged = merge_rows(held, [row(base_max=300_000)], ())

    assert len(merged) == 2


@pytest.mark.parametrize("field, value", [
    ("company", "other"), ("family", "product_management"),
    ("base_min", 199_000), ("base_max", 299_000), ("year", 2025),
])
def test_every_key_column_separates_two_rows(field, value):
    """Each part of the key identifies a row; none of them may be ignored when
    deciding whether a measurement replaces a held row."""
    merged = merge_rows([row()], [row(**{field: value})], ())

    assert len(merged) == 2


def test_the_held_rows_come_from_the_file_about_to_be_rewritten(tmp_path):
    """A refresh writing into a data checkout starts from that checkout's
    table, not from whatever copy the app happens to hold."""
    target = tmp_path / "pay_bands.csv"
    with target.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=COLUMNS, lineterminator="\n")
        writer.writeheader()
        writer.writerow(row(company="checkout-only"))

    assert [r["company"] for r in held_rows(target)] == ["checkout-only"]


def test_the_apps_own_table_answers_when_there_is_no_file_yet(tmp_path):
    """A first build has nothing to rewrite, and still must not start empty:
    the app's committed rows are the table."""
    rows = held_rows(tmp_path / "absent.csv")

    assert rows, "the app's pay bands are not loaded"
    assert all(set(COLUMNS) <= set(r) for r in rows)
    assert len({band_key(r) for r in rows}) == len(rows), "a key is repeated"


# --- a refusal is a result, not an absence ------------------------------------ #


def test_a_range_whose_anchors_now_disagree_is_not_carried():
    """The corpus is not silent about this range, it is contradicting it. The
    bar leaves a disagreeing range out, and a row kept from an earlier refresh
    would put it back."""
    held = [row(band="staff")]

    merged = merge_rows(held, [], [band_key(row())])

    assert merged == []


def test_silence_and_disagreement_are_told_apart():
    """One range has nothing said about it and keeps its row; the other is
    contradicted and loses it. A refresh that treated the two alike would
    either forget the first or assert the second."""
    unseen, contradicted = row(base_min=180_000, base_max=240_000), row(company="other")

    merged = merge_rows([unseen, contradicted], [], [band_key(contradicted)])

    assert merged == [unseen]


def test_a_rejection_does_not_reach_another_year():
    """The rejected key carries the year the run measured, so disagreement in
    one year cannot delete a range measured in another."""
    held = [row(year=2025, band="principal")]

    merged = merge_rows(held, [], [band_key(row(year=2026))])

    assert merged == held


def test_band_rows_names_the_range_its_anchors_disagree_on(stored):
    """End to end, on postings: two titles on one range state different bands,
    so the range is reported, no row is written, and the key that comes back is
    the one `merge_rows` matches a held row against, year included."""
    jobs = [stored("Senior Software Engineer"), stored("Staff Software Engineer")]

    rows, report, rejected = band_rows(jobs, 2026)

    assert rows == []
    assert len(report) == 1 and "disagree" in report[0]
    assert rejected == {("acme", "software_engineering", 200_000, 300_000, 2026)}


def test_band_rows_rejects_nothing_when_its_anchors_agree(stored):
    """The other side, so the test above is not passing for want of anchors."""
    jobs = [stored("Staff Software Engineer"), stored("Staff Software Engineer, Platform")]

    rows, _, rejected = band_rows(jobs, 2026)

    assert rejected == set()
    assert [r["band"] for r in rows] == ["staff"]

"""A posted range sharing ONE bound with a measured range is that same grade.

A company revises one end of a grade's range between postings, which is why
`pay_grades.csv` carries $207,000-$300,000 and $207,000-$301,000 as separate
measured rows of one rung. A range that shares a bound with a measured range,
and names no other grade, is read as that grade.

Everything weaker is refused, and the refusals are the point of this file:

1. **A shared bound that names two grades places nothing.** Amazon caps many
   ranges at one figure, so its top bound is shared by rows at different bands;
   a bound belonging to two grades names neither.
2. **Containment places nothing.** A wide range at one rung contains narrower
   ranges at others, which the committed tables show directly.
3. **Nearness places nothing**, before or between the company's other ranges.
4. The exact range still answers first, across the whole lineage, so no
   placement that works today is lost to a shared bound.
"""

from __future__ import annotations

import pytest

from tracker.levels.pay_grades import (
    PAY_BANDS,
    PAY_GRADES,
    PayGrade,
    _by_year,
    _shares_a_bound,
    grade_for_pay,
)
from tracker.schema import LevelBand

MEASURED = (*PAY_GRADES, *PAY_BANDS)


def _row(base_min: int, base_max: int, rung: str = "L5", *, company: str = "acme",
         family: str = "software_engineering", year: int = 2026) -> PayGrade:
    return PayGrade(company, family, base_min, base_max, year, rung, "anchor title", 2)


def _band_row(base_min: int, base_max: int, band: LevelBand, **kw) -> PayGrade:
    return PayGrade(kw.get("company", "acme"), kw.get("family", "software_engineering"),
                    base_min, base_max, kw.get("year", 2026), None, "anchor title", 2, band)


@pytest.fixture
def table(monkeypatch):
    """Install a measured table of our own, so the rule is read against rows
    the test states rather than against whatever the atlas holds today."""

    def install(rows: tuple[PayGrade, ...]) -> None:
        monkeypatch.setattr(
            "tracker.levels.pay_grades._INDEX",
            {(g.company, g.family, g.base_min, g.base_max, g.year): g for g in rows},
        )
        monkeypatch.setattr("tracker.levels.pay_grades._BY_YEAR", _by_year(rows))

    return install


# --- the rule ------------------------------------------------------------- #


@pytest.mark.parametrize("probe", [(207_000, 302_000), (207_000, 298_000),
                                   (204_000, 300_000), (210_000, 301_000)],
                         ids=["top-raised", "top-lowered", "bottom-lowered", "bottom-raised"])
def test_a_range_with_one_bound_revised_is_that_grade(table, probe):
    """Either bound may be the shared one, and the free one may move either way,
    as long as it only moved a little: that is one grade's range being revised
    rather than two grades that happen to meet at a number."""
    table((_row(207_000, 300_000), _row(207_000, 301_000)))

    grade = grade_for_pay("acme", "software_engineering", *probe, 2026)

    assert grade is not None and grade.rung == "L5"


def test_the_exact_range_answers_before_any_shared_bound(table):
    """Amazon's own tables share a top bound across bands, so a shared-bound
    read running first would lose the exact placements that work today."""
    table((_band_row(99_500, 160_000, LevelBand.MID),
           _band_row(118_200, 160_000, LevelBand.SENIOR)))

    assert grade_for_pay("acme", "software_engineering", 99_500, 160_000, 2026).band is LevelBand.MID
    assert grade_for_pay("acme", "software_engineering", 118_200, 160_000, 2026).band is LevelBand.SENIOR


def test_the_exact_range_of_a_parent_beats_a_childs_shared_bound(table):
    """The lineage runs twice, exact first: a measured range is never passed
    over for a bound shared with another, at any depth.

    The child's row is the query with its top revised, so an implementation that
    checked exact and revised-bound together for each company in turn would
    answer the child's L5 here instead of the parent's exact L7.
    """
    table((_row(400_000, 503_000, "L5", company="google-deepmind"),
           _row(400_000, 500_000, "L7", company="google")))

    grade = grade_for_pay("google-deepmind", "software_engineering", 400_000, 500_000, 2026)

    assert grade is not None and grade.rung == "L7"


# --- what it refuses ------------------------------------------------------ #


def test_a_bound_two_grades_share_names_neither(table):
    """A company that caps ranges at one figure shares that bound across
    bands. The range is refused rather than given the first of them."""
    table((_band_row(99_500, 160_000, LevelBand.MID),
           _band_row(118_200, 160_000, LevelBand.SENIOR)))

    assert grade_for_pay("acme", "software_engineering", 100_000, 160_000, 2026) is None


def test_a_childs_own_ambiguous_bound_is_not_settled_by_its_parent(table):
    """A company whose own ranges name a bound has spoken, and the refusal is
    part of what it said. Reading the parent's ladder past it would settle the
    child's own ambiguity from above, which is how an unplaced level becomes a
    wrong one."""
    table((_row(100_000, 200_000, "L5", company="google-deepmind"),
           _row(120_000, 200_000, "L6", company="google-deepmind"),
           _row(130_000, 200_000, "L7", company="google")))

    # The query revises the PARENT's range, within `REVISED_BOUND` of it, so a
    # fall-through would answer L7 rather than refuse. A query the parent could
    # not place either would pass whether the refusal is kept or not.
    assert grade_for_pay("google-deepmind", "software_engineering", 128_000, 200_000, 2026) is None
    # The control, the same query: with the child saying nothing about that
    # bound, the parent does answer.
    table((_row(130_000, 200_000, "L7", company="google"),))
    grade = grade_for_pay("google-deepmind", "software_engineering", 128_000, 200_000, 2026)
    assert grade is not None and grade.rung == "L7"


@pytest.mark.parametrize("probe, src, grade", [
    ((347_000, 385_000), (347_000, 490_000), "L7"),
    ((184_700, 277_600), (184_700, 324_800), "L6"),
    ((205_400, 374_300), (205_400, 308_500), "L6"),
], ids=["floor-shared-105k-apart", "floor-shared-47k-apart", "floor-shared-66k-apart"])
def test_a_figure_two_grades_open_at_names_neither(table, probe, src, grade):
    """A company that starts several grades at one figure is the case this rule
    has to refuse, and the one a bare shared bound gets wrong.

    These are real shapes: a posting topping out at $385,000 is not the grade of
    a range topping out at $490,000 because both open at $347,000. The clash
    guard cannot save it, since it needs a second measured row on that figure
    and here the tables hold one.
    """
    table((_row(*src, grade),))

    assert grade_for_pay("acme", "software_engineering", *probe, 2026) is None


def test_a_range_inside_another_is_not_that_grade(table):
    """Containment is not evidence: a wide range at one rung holds narrower
    ranges at others."""
    table((_row(240_000, 333_000, "L7"),))

    assert grade_for_pay("acme", "software_engineering", 256_000, 278_000, 2026) is None


def test_a_range_between_two_measured_ranges_is_not_placed(table):
    """Bracketing is not evidence either, even where both sides agree."""
    table((_row(150_000, 200_000, "L5"), _row(250_000, 300_000, "L5")))

    assert grade_for_pay("acme", "software_engineering", 205_000, 245_000, 2026) is None


def test_the_nearest_measured_range_is_not_read(table):
    """A range a thousand dollars from a measured one shares no bound with it."""
    table((_row(207_000, 300_000, "L5"),))

    assert grade_for_pay("acme", "software_engineering", 208_000, 301_000, 2026) is None


def test_a_bound_shared_in_another_year_places_nothing(table):
    """Ranges are revised yearly, so a bound is evidence only in its own year."""
    table((_row(207_000, 300_000, "L5", year=2025),))

    assert grade_for_pay("acme", "software_engineering", 207_000, 302_000, 2026) is None


def test_a_bound_shared_in_another_family_places_nothing(table):
    """One range may be two grades in two families."""
    table((_row(207_000, 300_000, "L5", family="product_management"),))

    assert grade_for_pay("acme", "software_engineering", 207_000, 302_000, 2026) is None


def test_another_companys_bound_places_nothing(table):
    table((_row(207_000, 300_000, "L5", company="other"),))

    assert grade_for_pay("acme", "software_engineering", 207_000, 302_000, 2026) is None


# --- against the tables as committed -------------------------------------- #


def test_the_committed_tables_still_hold_a_bound_two_grades_share():
    """The guard above is not hypothetical. If this stops holding after a
    yearly rebuild, the refusal has lost its reason and its test its teeth."""
    clashes = [
        (a, b)
        for a in MEASURED
        for b in MEASURED
        if (a.company, a.family, a.year) == (b.company, b.family, b.year)
        and (a.base_min, a.base_max) != (b.base_min, b.base_max)
        and (a.base_min == b.base_min or a.base_max == b.base_max)
        and (a.rung, a.band) != (b.rung, b.band)
    ]

    assert clashes, "no measured bound is shared by two grades"
    a, b = clashes[0]
    assert _shares_a_bound((a, b), a.base_min, b.base_max) is None


def test_the_committed_tables_still_hold_a_bound_one_grade_owns():
    """The other side: the rule has something to place, on the real tables."""
    pairs = [
        (a, b)
        for a in MEASURED
        for b in MEASURED
        if (a.company, a.family, a.year) == (b.company, b.family, b.year)
        and (a.base_min, a.base_max) != (b.base_min, b.base_max)
        and a.base_min == b.base_min
        and (a.rung, a.band) == (b.rung, b.band)
    ]

    assert pairs, "no measured bound is shared by one grade's own ranges"
    a, b = pairs[0]
    # A range on that bound, longer than either, is read as their grade.
    grade = grade_for_pay(a.company, a.family, a.base_min, max(a.base_max, b.base_max) + 1_000, a.year)
    assert grade is not None and (grade.rung, grade.band) == (a.rung, a.band)

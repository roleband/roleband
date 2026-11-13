"""Posted base ranges that a company pays at one rung.

Google posts a US base range on every posting, and the ranges are per grade:
a few distinct ranges repeat across many postings, and a range's titles agree
on the rung where they name one. A posting whose title names no rung ("Product Manager", "Engineering Manager") is read
by its range instead.

Each row is keyed by (company, taxonomy family, range, year): one range may be
two rungs in two families, and the company revises its ranges each year, so a
range seen in a later year is unknown until it is measured again. Each row
names the anchor: a title read by that family's own rules (`levels.titles`)
that states the rung, and how many of the range's postings anchored it. A row
exists only where at least two anchors agree on four of every five; the
dissenting postings are never guessed into agreement.

Every other company that posts repeating ranges has
band-level rows in `atlas/pay_bands.csv`, written by `scripts.bench_level_bands
pay-bands --write`: there is no ladder to name a rung on, so a row names the
band its anchoring titles state instead. The same rule holds: 2+
anchors, four of every five agreeing.

An exact (company, family, range) places a band. So does a range that shares
ONE bound with a measured range and names no other grade: a company revises one
end of a grade's range between postings, which is why $207,000-$300,000 and
$207,000-$301,000 are separate measured rows above. Nothing weaker places a
band. A range is never placed by its nearness to the company's other ranges,
nor by sitting between two of them, nor by sitting inside one: each of those
predicts the band far less often, and the last two pull director postings below
director.

Pure data, no DB. A pay change never re-annotates the inventory (it has no
pay), so this module and its CSVs are outside `CLASSIFIER_SOURCES`.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass

from tracker.levels.atlas import PAY_BANDS as PAY_BANDS_TABLE
from tracker.levels.atlas import PAY_GRADES as PAY_GRADES_TABLE
from tracker.levels.atlas import read_rows
from tracker.levels.ladder import lineage
from tracker.schema import LevelBand

PAY_BANDS_CSV = PAY_BANDS_TABLE.path


@dataclass(frozen=True)
class PayGrade:
    company: str
    family: str  # taxonomy family slug
    base_min: int
    base_max: int
    year: int
    rung: str | None  # a code on the family's ladder (or the company row)
    anchor: str  # a title that states the rung or band, as the company's rules read it
    anchors: int  # postings at this range whose title stated it
    #: The band, for a company with no ladder to name a rung on (`pay_bands.csv`).
    band: LevelBand | None = None


#: Google's per-grade ranges, from `tracker/levels/atlas/pay_grades.csv`.
#: Ranges a thousand dollars apart at the top ($207k-$300k and $207k-$301k)
#: are separate rows: both are posted, each is anchored.
PAY_GRADES: tuple[PayGrade, ...] = tuple(
    PayGrade(
        row["company"], row["family"], int(row["base_min"]), int(row["base_max"]),
        int(row["year"]), row["rung"], row["anchor"], int(row["anchors"]),
    )
    for row in read_rows(PAY_GRADES_TABLE)
)


def _load_bands() -> tuple[PayGrade, ...]:
    # Committed beside `pay_grades.csv`, and read the same way: a missing atlas
    # table fails at import rather than silently placing nothing.
    return tuple(
        PayGrade(
            row["company"], row["family"], int(row["base_min"]), int(row["base_max"]),
            int(row["year"]), None, row["anchor"], int(row["anchors"]), LevelBand(row["band"]),
        )
        for row in read_rows(PAY_BANDS_TABLE)
    )


#: Band-level rows for every other company that posts repeating ranges.
PAY_BANDS: tuple[PayGrade, ...] = _load_bands()

_INDEX = {(g.company, g.family, g.base_min, g.base_max, g.year): g for g in (*PAY_GRADES, *PAY_BANDS)}
_MEASURED = frozenset((g.company, g.family, g.year) for g in (*PAY_GRADES, *PAY_BANDS))


def _by_year(grades: Iterable[PayGrade]) -> dict[tuple[str, str, int], tuple[PayGrade, ...]]:
    """Every measured row of one company's family in one year, for the
    shared-bound read, which needs the company's other ranges and not just this
    one."""
    found: dict[tuple[str, str, int], list[PayGrade]] = defaultdict(list)
    for grade in grades:
        found[(grade.company, grade.family, grade.year)].append(grade)
    return {key: tuple(rows) for key, rows in found.items()}


_BY_YEAR = _by_year((*PAY_GRADES, *PAY_BANDS))


def has_measured_ranges(company: str, family: str | None, year: int) -> bool:
    """True when some posted range of this company's family in this year is
    measured: a stated range can then name the posting's band."""
    return family is not None and any((slug, family, year) in _MEASURED for slug in lineage(company))


def _sharing_rows(rows: tuple[PayGrade, ...], base_min: int, base_max: int) -> list[PayGrade]:
    """The measured rows of one cell that share a bound with this range."""
    return [row for row in rows if row.base_min == base_min or row.base_max == base_max]


def _shares_a_bound(rows: tuple[PayGrade, ...], base_min: int, base_max: int) -> PayGrade | None:
    """The grade of a range sharing one bound with a measured range, or None.

    Every sharing row must name the one grade: where a bound is shared by two
    grades it belongs to both and names neither, so the range is refused rather
    than given the first of them.
    """
    sharing = _sharing_rows(rows, base_min, base_max)
    if not sharing or len({(row.rung, row.band) for row in sharing}) > 1:
        return None
    return sharing[0]


def grade_for_pay(
    company: str, family: str | None, base_min: int, base_max: int, year: int,
) -> PayGrade | None:
    """The measured grade of this posted range, or None. A child company
    (google-deepmind) reads its parent's ranges when it has none of its own.

    The exact range answers first, across the whole lineage, so a measured range
    is never passed over for a bound shared with another.
    """
    if family is None:
        return None
    for slug in lineage(company):
        grade = _INDEX.get((slug, family, base_min, base_max, year))
        if grade is not None:
            return grade
    for slug in lineage(company):
        rows = _BY_YEAR.get((slug, family, year), ())
        if not _sharing_rows(rows, base_min, base_max):
            continue
        # This company's own ranges name the bound, so its parent's do not
        # answer: one grade owns the bound, or two do and it names neither.
        # Falling through on the refusal would settle a company's own
        # ambiguity from its parent's ladder.
        return _shares_a_bound(rows, base_min, base_max)
    return None

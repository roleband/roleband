"""Hiring-velocity analytics for the Statistics "Pace" sub-tab.

Pure, DB-free assembly of the motion over a window: the roles that opened and
came down, the ages of the roles still open, and how long the roles that came
down had been posted. The roles, each counted once, come from
`db.queries.motion`; this module shapes them, so all of it is unit-testable.

**This is not time-to-fill, and never was.** Time posted runs from a role's
listing start to the read that confirmed it gone (`closed_at`). RoleBand sees a public board, so
it can say a posting stopped being advertised and cannot say a person was
hired: employers legitimately unpublish, pause, re-post and schedule expiry,
and a posting can also vanish because our own scan of that board changed. A
name like "time to fill" would assert an employer outcome from an availability
observation, so the measure is `median_observed_listing_duration_days`.

A role whose start is unknown (`analytics.age_basis`) is counted beside the
bands and the medians, never inside them: the bands plus the unknown count are
every role the figure describes.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence

from tracker.analytics.age_basis import employer_dated_share

# (lo_days_inclusive, hi_days_exclusive|None): fixed so the axis is stable. The
# dashboard names each band by `lo` (`insights-aging-from-<lo>-days`);
# `tests/test_vocab_catalog.py` holds the two together.
AGING_BANDS: tuple[tuple[int, int | None], ...] = (
    (0, 7),
    (7, 14),
    (14, 30),
    (30, 60),
    (60, 90),
    (90, None),
)

# Below this many roles with a known time posted, a median is too thin to
# state, for the whole window and for one company.
MIN_DURATION_SAMPLE = 5

DURATION_KEY = "median_observed_listing_duration_days"

#: `(company, days or None when unknown, employer_dated)`.
AgeRow = tuple[str, float | None, bool]


def _median(vals: Sequence[float]) -> float | None:
    """Linear-interpolated median; None on empty input."""
    s = sorted(vals)
    n = len(s)
    if n == 0:
        return None
    mid = (n - 1) / 2
    lo = int(mid)
    if mid == lo:  # whole index (odd n) -> the middle element
        return float(s[lo])
    return (s[lo] + s[lo + 1]) / 2  # even n -> mean of the two middle elements


def _thin_median(vals: Sequence[float]) -> float | None:
    return _median(vals) if len(vals) >= MIN_DURATION_SAMPLE else None


def aging_histogram(days_open: Iterable[float]) -> list[dict]:
    """Bucket ages (in days) into the fixed AGING_BANDS, zero-filled. An age
    below zero (a start our clock places a moment ahead) is the first band, so
    the bands always add up to the ages given."""
    counts = [0] * len(AGING_BANDS)
    for d in days_open:
        d = max(0.0, d)
        for i, (lo, hi) in enumerate(AGING_BANDS):
            if d >= lo and (hi is None or d < hi):
                counts[i] += 1
                break
    return [
        {"lo": lo, "hi": hi, "count": counts[i]}
        for i, (lo, hi) in enumerate(AGING_BANDS)
    ]


def _known(rows: Iterable[AgeRow]) -> dict[str, list[float]]:
    out: dict[str, list[float]] = {}
    for company, d, _ in rows:
        if d is not None:
            out.setdefault(company, []).append(float(d))
    return out


def build_velocity(
    open_rows: Sequence[AgeRow],
    openings: Iterable[tuple[str, str]],
    came_down: Sequence[AgeRow],
    open_total: int,
    days: int,
    *,
    company_limit: int = 15,
) -> dict:
    """Assemble the Pace payload.

    `open_rows`: one per open role, with its age. `openings`: `(company,
    kind)` per role first seen in the window, `kind` one of `opened`,
    `already_listed` or `reposted` (`db.queries.motion.opening_kind`).
    `came_down`: one per role that came down in the window, with its time
    posted. Companies are ranked by opened count, then closed and open counts;
    every company with an opening or a closing is listed, others up to the limit.
    """
    counts: dict[str, dict[str, int]] = {"opened": {}, "already_listed": {}, "reposted": {}}
    for company, kind in openings:
        bucket = counts[kind]
        bucket[company] = bucket.get(company, 0) + 1
    opened, reposted = counts["opened"], counts["reposted"]

    open_by_co: dict[str, int] = {}
    for company, _, _ in open_rows:
        open_by_co[company] = open_by_co.get(company, 0) + 1
    closed: dict[str, int] = {}
    for company, _, _ in came_down:
        closed[company] = closed.get(company, 0) + 1
    ages_by_co = _known(open_rows)
    duration_by_co = _known(came_down)
    all_ages = [a for vs in ages_by_co.values() for a in vs]
    all_durations = [d for vs in duration_by_co.values() for d in vs]

    companies = set(open_by_co) | set(opened) | set(closed) | set(reposted)
    rows = sorted(
        (
            {
                "company": c,
                "open": open_by_co.get(c, 0),
                "opened": opened.get(c, 0),
                "closed": closed.get(c, 0),
                "reposted": reposted.get(c, 0),
                "median_days_open": _median(ages_by_co.get(c, [])),
                DURATION_KEY: _thin_median(duration_by_co.get(c, [])),
            }
            for c in companies
        ),
        key=lambda d: (d["opened"], d["closed"], d["open"]),
        reverse=True,
    )
    # Every company that opened or closed a role in the window keeps its row,
    # so the column totals match the tiles above them; quiet companies fill
    # the table up to the limit.
    moved = [d for d in rows if d["opened"] or d["closed"] or d["reposted"]]
    quiet = [d for d in rows if not (d["opened"] or d["closed"] or d["reposted"])]
    by_company = moved + quiet[: max(0, company_limit - len(moved))]

    return {
        "days": days,
        "kpis": {
            "open_total": open_total,
            "opened": sum(opened.values()),
            "closed": len(came_down),
            "reposted": sum(reposted.values()),
            "already_listed": sum(counts["already_listed"].values()),
            "median_days_open": _median(all_ages),
            "age_unknown": len(open_rows) - len(all_ages),
            "employer_dated_share": employer_dated_share(
                sum(1 for _, d, dated in open_rows if d is not None and dated), len(all_ages)
            ),
            DURATION_KEY: _thin_median(all_durations),
            "closed_sample": len(all_durations),
            "closed_unknown": len(came_down) - len(all_durations),
            "closed_employer_dated_share": employer_dated_share(
                sum(1 for _, d, dated in came_down if d is not None and dated), len(all_durations)
            ),
        },
        "aging": aging_histogram(all_ages),
        # How long the roles that came down stayed up, on the same bands, so
        # Pace's two distributions are one height.
        "posted": aging_histogram(all_durations),
        "by_company": by_company,
    }

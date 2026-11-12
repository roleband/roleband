"""Where a role's age starts in Pace, and what the age aggregates rest on.

Pace ages a role, open or come down, from the start of its listing
(`analytics.posting_reality.listing_start`: the earlier of the employer's date
and our first sighting), taken over every posting of its lineage, so a repost
keeps the age of the role it continues (`posting_reality.role_start`). A
sighting dates a posting only when the company was already read
(`schema.Arrival`): a first read's find without an earlier employer date has no
knowable start, and when it would be the role's earliest evidence the role's
age is unknown. Unknown ages stay out of the medians and the bands and are
counted beside them.

The Hiring rollup's median days and long-open counts (`analytics/demand.py`) keep our
own first-sighting clock.

Each age aggregate also states how many of the postings it summarises carry an
employer date. A posting is employer-dated when `jobs.posted_at` is set; a
stored earliest-date column does not change that meaning. The predicate lives
here once. Pure: no database import, so `velocity` stays DB-free.
"""

from __future__ import annotations

from datetime import datetime


def employer_dated_sql(alias: str = "") -> str:
    """The predicate for a `text()` query over `jobs` (`alias` = "j." etc.)."""
    return f"{alias}posted_at IS NOT NULL"


def aggregate_start(known_start: datetime | None, unknown_floor: datetime | None) -> datetime | None:
    """A role's start from its postings: `known_start` is the earliest listing
    start among the postings whose start is known, `unknown_floor` the earliest
    sighting among the rest (a first read's undated finds, which were listed
    for an unknown time before it). The start is known only when no unknown
    posting could be earlier; None otherwise."""
    if known_start is None:
        return None
    if unknown_floor is not None and unknown_floor < known_start:
        return None
    return known_start


def employer_dated_share(dated: int, total: int) -> float | None:
    """`dated / total` as a fraction; None when the aggregate summarises nothing,
    so an empty sample never reads as "none are dated"."""
    if total <= 0:
        return None
    return dated / total

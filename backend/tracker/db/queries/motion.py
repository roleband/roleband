"""How roles came and went: the openings and the roles that came down, each
role once, and how old the open roles are. Overview, Pace and Hiring read
these, so one question gets one answer on every tab.

Every count reads the postings Insights describes (in scope, not hidden) once
(`load`) and joins them into roles. Postings of one place set are one role.
The stored place sets hold open postings only (`lineage.place_sets`), so a
closed posting's set is what its `closed` event recorded while it was still
open (`place_sets.closing_role_notes`): `listed_with`, the postings of its
role that stayed open, and `closed_with`, those that closed in the same read.
Those ids join only postings the scope holds: a sibling at a place out of
scope keeps no in-scope role listed. A closing recorded without ids is its
posting alone.

**Openings** are the roles first seen in a window, each by its earliest
posting, picked before the window applies: a role whose first place was seen
before the window did not open in it, whichever of its places closed. One is
**opened** when it was new when found: by the New rule
(`posting_reality.is_new_listing`), its listing start was under
`NEW_LISTING_WINDOW` old at our first sighting. Any other original was
**already listed** when found: a company's first scan of a posting it did not
date as new, or a posting the employer dated earlier. A repost or duplicate is
**reposted**.

**Came down**: a role, its place set and its lineage joined, with every
in-scope posting closed, counted when the scan confirmed its last closing
(`closed_at`), as openings count at our first sighting. Its time posted runs
from the role's start to that closing, as the Closed board's "listed for"
does.

A role's start is `analytics.age_basis.aggregate_start` over every posting the
role joins: None when it is unknown.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Literal

from sqlalchemy import case, desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from tracker.analytics.age_basis import aggregate_start
from tracker.analytics.posting_reality import is_new_listing
from tracker.db.models import Job, JobLifecycleEvent, JobPlaceSetMember
from tracker.db.queries.insights import InsightsScope
from tracker.db.queries.jobs import exclude_hidden
from tracker.schema import Arrival

OpeningKind = Literal["opened", "already_listed", "reposted"]

_DAY_SECONDS = 86400.0


@dataclass(frozen=True)
class Opening:
    company: str
    kind: OpeningKind


@dataclass(frozen=True)
class CameDown:
    company: str
    went: datetime
    #: Whole days from the role's start to its closing; None when the start is unknown.
    days: int | None
    employer_dated: bool


@dataclass(frozen=True)
class OpenAge:
    company: str
    #: Whole days from the role's start to now; None when the start is unknown.
    days: int | None
    employer_dated: bool


def opening_kind(
    *, lineage_role: str | None, arrival: str | None, first_posted_at: datetime | None, first_seen: datetime
) -> OpeningKind:
    """What a posting first seen in a window was when we found it."""
    if lineage_role in ("repost", "duplicate"):
        return "reposted"
    # The New rule asked at our first sighting: the posting was open then.
    if is_new_listing(
        first_posted_at, first_seen, arrival=arrival, status="open", lineage_role=None, now=first_seen
    ):
        return "opened"
    return "already_listed"


@dataclass(frozen=True)
class Postings:
    """The postings one scope describes, by id, read once per request."""

    by_id: dict[int, Any]


def _last_close() -> Any:
    """The detail of a posting's latest `closed` event."""
    return (
        select(JobLifecycleEvent.detail)
        .where(JobLifecycleEvent.job_id == Job.id, JobLifecycleEvent.event_type == "closed")
        .order_by(desc(JobLifecycleEvent.created_at), desc(JobLifecycleEvent.id))
        .limit(1)
        .scalar_subquery()
    )


def _stored_set() -> Any:
    return (
        select(JobPlaceSetMember.set_id)
        .where(JobPlaceSetMember.job_id == Job.id, JobPlaceSetMember.status == "auto")
        .limit(1)
        .scalar_subquery()
    )


async def load(session: AsyncSession, scope: InsightsScope, hidden: list[str]) -> Postings:
    """Every posting Insights describes, open or closed, with what joins it
    into a role: its stored place set, its lineage and its closing note."""
    stmt = exclude_hidden(
        select(
            Job.id,
            Job.company,
            Job.status,
            Job.lineage_id,
            Job.lineage_role,
            Job.arrival,
            Job.first_posted_at,
            Job.first_seen,
            Job.closed_at,
            Job.posted_at.is_not(None).label("employer_dated"),
            _stored_set().label("set_id"),
            case((Job.status != "open", _last_close())).label("note"),
        ).where(Job.in_scope.is_(True), *scope.conds()),
        hidden,
    )
    return Postings({r.id: r for r in (await session.execute(stmt)).all()})


class _Groups:
    """Union-find over posting ids."""

    def __init__(self) -> None:
        self.parent: dict[int, int] = {}

    def find(self, key: int) -> int:
        self.parent.setdefault(key, key)
        while self.parent[key] != key:
            self.parent[key] = self.parent[self.parent[key]]
            key = self.parent[key]
        return key

    def join(self, a: int, b: int) -> None:
        self.parent[self.find(a)] = self.find(b)

    def members(self, ids: Iterable[int]) -> dict[int, list[int]]:
        out: dict[int, list[int]] = {}
        for job_id in ids:
            out.setdefault(self.find(job_id), []).append(job_id)
        return out


def _noted(note: Any) -> list[int]:
    """The ids a closing note joins its posting with; none for a closing
    recorded without them."""
    if not isinstance(note, dict):
        return []
    return [
        int(i)
        for key in ("listed_with", "closed_with")
        if isinstance(note.get(key), list)
        for i in note[key]
    ]


def _place_roles(postings: Postings) -> _Groups:
    """Postings of one place set: the stored set, and the ids each closing
    recorded, among the postings the scope holds."""
    groups = _Groups()
    first_of_set: dict[int, int] = {}
    for r in postings.by_id.values():
        groups.find(r.id)
        if r.set_id is not None:
            groups.join(r.id, first_of_set.setdefault(r.set_id, r.id))
        for other in _noted(r.note):
            if other in postings.by_id:
                groups.join(r.id, other)
    return groups


def _roles(postings: Postings) -> _Groups:
    """Postings of one role: a place set and a lineage, joined."""
    groups = _place_roles(postings)
    first_of_lineage: dict[int, int] = {}
    for r in postings.by_id.values():
        if r.lineage_id is not None:
            groups.join(r.id, first_of_lineage.setdefault(r.lineage_id, r.id))
    return groups


def _start(rows: Iterable[Any]) -> datetime | None:
    """A role's listing start over its postings. Our sighting dates a
    posting's appearance unless a company's first scan made it; an employer
    date before the sighting always does. NULL `arrival` takes the sighting
    at its word."""
    known: list[datetime] = []
    unknown: list[datetime] = []
    for r in rows:
        dated_earlier = r.first_posted_at is not None and r.first_posted_at < r.first_seen
        if r.arrival != Arrival.FIRST_READ.value or dated_earlier:
            known.append(min(r.first_posted_at, r.first_seen) if r.first_posted_at is not None else r.first_seen)
        else:
            unknown.append(r.first_seen)
    return aggregate_start(min(known, default=None), min(unknown, default=None))


def _whole_days(start: datetime | None, end: datetime) -> int | None:
    if start is None:
        return None
    return max(0, int((end - start).total_seconds() // _DAY_SECONDS))


def open_ages(postings: Postings, now: datetime) -> list[OpenAge]:
    """Every open role Insights describes, a place set once (through its
    earliest open posting, as every count shows it), aged from its role's
    start."""
    roles = _roles(postings)
    members = roles.members(postings.by_id)
    first_open_of_set: dict[int, Any] = {}
    for r in postings.by_id.values():
        if r.status == "open" and r.set_id is not None:
            held = first_open_of_set.get(r.set_id)
            if held is None or (r.first_seen, r.id) < (held.first_seen, held.id):
                first_open_of_set[r.set_id] = r
    out: list[OpenAge] = []
    for r in postings.by_id.values():
        if r.status != "open" or (r.set_id is not None and first_open_of_set[r.set_id] is not r):
            continue
        role = [postings.by_id[i] for i in members[roles.find(r.id)]]
        out.append(OpenAge(r.company, _whole_days(_start(role), now), any(m.employer_dated for m in role)))
    return out


def openings(postings: Postings, since: datetime | None) -> list[Opening]:
    """The roles first seen since `since` (all of them for None), each once,
    by its earliest posting."""
    out: list[Opening] = []
    for ids in _place_roles(postings).members(postings.by_id).values():
        first = min((postings.by_id[i] for i in ids), key=lambda r: (r.first_seen, r.id))
        if since is not None and first.first_seen < since:
            continue
        out.append(
            Opening(
                first.company,
                opening_kind(
                    lineage_role=first.lineage_role,
                    arrival=first.arrival,
                    first_posted_at=first.first_posted_at,
                    first_seen=first.first_seen,
                ),
            )
        )
    return out


def came_down(postings: Postings, since: datetime | None) -> list[CameDown]:
    """The roles whose last in-scope posting closed since `since` (all of them
    for None), each once."""
    out: list[CameDown] = []
    for ids in _roles(postings).members(postings.by_id).values():
        role = [postings.by_id[i] for i in ids]
        if any(r.status == "open" for r in role):
            continue
        closings = [r.closed_at for r in role if r.closed_at is not None]
        if not closings:
            continue
        went = max(closings)
        if since is not None and went < since:
            continue
        out.append(
            CameDown(role[0].company, went, _whole_days(_start(role), went), any(r.employer_dated for r in role))
        )
    return out


def per_company(items: Sequence[Opening | CameDown], kind: str | None = None) -> dict[str, int]:
    """Counts by company, of one opening kind when given."""
    out: dict[str, int] = {}
    for item in items:
        if kind is None or getattr(item, "kind", None) == kind:
            out[item.company] = out.get(item.company, 0) + 1
    return out

"""How roles came and went: the openings and the roles that came down, each
role once, and how old the open roles are. Overview, Pace and Hiring read
these, so one question gets one answer on every tab.

Every count reads the postings Insights describes (in scope, not hidden) once
(`load`): every role its window can reach, each whole, and none that opened
and came down before it. It joins them into roles. Postings of one place set are one role.
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

from sqlalchemy import (
    BigInteger,
    Integer,
    and_,
    case,
    cast,
    desc,
    false,
    func,
    literal_column,
    or_,
    select,
    true,
    union_all,
)
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased
from sqlalchemy.sql.elements import ColumnClause

from tracker.analytics.age_basis import aggregate_start
from tracker.analytics.posting_reality import is_new_listing
from tracker.db.models import Job, JobLifecycleEvent, JobPlaceSetMember
from tracker.db.queries.insights import InsightsScope
from tracker.lineage.counts import place_set_later
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
    """The postings one scope describes that a count can reach, by id, read
    once per request."""

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


#: The kind of a posting's node in `_reached`'s walk.
_POSTING: ColumnClause[str] = literal_column("'job'::text")

#: The keys of a closing note that name the postings it joins.
_NOTE_KEYS = ("listed_with", "closed_with")


def _scoped(job: Any, scope: InsightsScope, hidden: list[str]) -> list:
    """The postings Insights describes, on `job` (the table or an alias)."""
    conds = [job.in_scope.is_(True), *scope.conds(company=job.company, family=job.family)]
    return [*conds, job.company.notin_(hidden)] if hidden else conds


def _reached(scope: InsightsScope, hidden: list[str], seed: Any) -> Any:
    """The postings `seed` picks and every posting a role joins to them,
    through any number of postings between: a lineage, a stored place set,
    and a closing note in either direction.

    The walk visits postings and, as nodes of their own, the lineages and
    sets that hold them, so a group of any size is listed once, not once per
    member. A posting's own notes name the others; a posting named in
    another's `listed_with` is found from the note that names it.
    `closed_with` needs no such search: a read writes it on every posting it
    closes together, each naming the rest, so the postings it joins name each
    other. Edges come from every `closed` event, not only the latest, so the
    walk may reach a few postings no role joins; `load` applies the rule
    itself. What it reaches is a whole number of roles, so every role it
    touches is read entire however long ago its other postings closed, and
    nothing else is read.

    Rows are `(id, kind)`: a posting, a lineage or a set by its id."""
    start = select(cast(Job.id, BigInteger).label("id"), _POSTING.label("kind")).where(
        *_scoped(Job, scope, hidden), seed
    )
    reached = start.cte("reached", recursive=True)
    own, member, other = aliased(Job), aliased(Job), aliased(Job)
    in_set, peer = aliased(JobPlaceSetMember), aliased(JobPlaceSetMember)
    event = aliased(JobLifecycleEvent)
    # Literals, so a branch that does not apply to a row's kind is skipped
    # once per row, and the partial index on closing notes matches a
    # prepared plan.
    posting = _POSTING
    lineage: ColumnClause[str] = literal_column("'lineage'::text")
    place_set: ColumnClause[str] = literal_column("'set'::text")
    is_posting = reached.c.kind == posting
    closing = event.event_type == literal_column("'closed'")

    def edge(stmt: Any, kind: Any) -> Any:
        return stmt.add_columns(kind.label("kind")).correlate(reached)

    joined = union_all(
        edge(select(own.lineage_id.label("id")).where(is_posting, own.id == reached.c.id, own.lineage_id.is_not(None)), lineage),
        edge(select(in_set.set_id.label("id")).where(
            is_posting, in_set.job_id == reached.c.id, in_set.status == "auto", in_set.set_id.is_not(None)
        ), place_set),
        edge(select(member.id.label("id")).where(reached.c.kind == lineage, member.lineage_id == reached.c.id), posting),
        edge(select(peer.job_id.label("id")).where(
            reached.c.kind == place_set, peer.set_id == reached.c.id, peer.status == "auto"
        ), posting),
        *(
            edge(
                select(func.jsonb_array_elements_text(event.detail[key]).cast(Integer).label("id")).where(
                    is_posting, event.job_id == reached.c.id, closing,
                    func.jsonb_typeof(event.detail[key]) == "array",
                ),
                posting,
            )
            for key in _NOTE_KEYS
        ),
        edge(select(event.job_id.label("id")).where(
            is_posting, closing,
            event.detail.op("@>")(func.jsonb_build_object("listed_with", func.jsonb_build_array(reached.c.id))),
        ), posting),
    ).lateral("joined")
    # A scalar subquery, so each posting reached is checked by its id and a
    # step never reads the postings no role it holds joins.
    described = (
        select(literal_column("1"))
        .where(other.id == joined.c.id, *_scoped(other, scope, hidden))
        .correlate(joined)
        .scalar_subquery()
    )
    step = (
        select(cast(joined.c.id, BigInteger), joined.c.kind)
        .select_from(reached.join(joined, true()))
        .where(or_(joined.c.kind != posting, described.is_not(None)))
    )
    return reached.union(step)


async def load(
    session: AsyncSession,
    scope: InsightsScope,
    hidden: list[str],
    *,
    since: datetime | None,
    open_roles: bool = False,
) -> Postings:
    """The postings Insights describes that a count from `since` can reach,
    open or closed, with what joins them into a role: its stored place set,
    its lineage and its closing note.

    That is every role with a posting first seen or closed since `since`,
    and with `open_roles` every role still open, each with all its postings
    (`_reached`). A role that opened and came down before `since` is in no
    count from it, so the read grows with the window and the open roles, not
    with the history. None reads every posting: all time is the history."""
    if since is None:
        wanted: Any = and_(*_scoped(Job, scope, hidden))
    else:
        seed = or_(Job.first_seen >= since, Job.closed_at >= since)
        if open_roles:
            seed = or_(seed, Job.status == "open")
        reached = _reached(scope, hidden, seed)
        wanted = Job.id.in_(select(reached.c.id).where(reached.c.kind == _POSTING))
    stmt = select(
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
        # The set's member every count shows it through, for `open_ages`.
        (Job.id.in_(place_set_later()) if open_roles else false()).label("later"),
    ).where(wanted)
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
    """Every open role Insights describes, a place set once, through the
    member every count shows it by (`lineage.counts.place_set_later`), aged
    from its role's start. Needs a `load` with `open_roles`."""
    roles = _roles(postings)
    members = roles.members(postings.by_id)
    out: list[OpenAge] = []
    for r in postings.by_id.values():
        if r.status != "open" or r.later:
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

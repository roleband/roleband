"""`changes.list`: what changed on the radar after a position, in commit order.

A page answers events, each with a kind, a time and the ids to read next; it
never embeds the posting. `next_since` is the position after the page: the
caller passes it back as `since`, and reads each event once.

**Commit order.** A row's id, and the id of the transaction that wrote it,
are taken when the row is inserted, not when it commits, so a reader that
remembered "everything up to id N" would miss a row with a smaller id that
committed after it read. The feed's records carry the inserting transaction
(`change_xact`, `xid8`). A read first takes the oldest transaction still open
(the snapshot's `xmin`): every transaction below it has ended, so the rows
below it are final, and nothing can later commit there. A read answers the
rows between the previous position and that frontier; a row whose transaction
is still open waits for the next read rather than being passed over. A
long-open transaction delays the feed; it never costs it an event. A position
is a transaction id, so it means the same after an engine restart; it is bound
to the cluster that assigned it, and a database restored into another cluster
refuses the positions given out before (`expired`). Decision 0020.

**Paging.** A read fixes its frontier and pages through the rows below it
(`continue_with`, `page_shortened` when the tier's budget ends a page before
`limit`); `caught_up` says the page reached the frontier. Rows written before
the feed's columns existed, or restored from another cluster, are history
that comes first, ordered by id, and only to a read from the beginning or a
`start_time`.

**Kinds.** What each kind is built from:

- `new`, `closed`, `reopened`: recorded, the posting's lifecycle event
  (`job_lifecycle_events`: `opened` or `added`, `closed`, `reopened`).
- `stated_pay_changed`: recorded, a `changed` event whose detail carries the
  employer's band before and after (`disclosed_base`).
- `reposted`: derived. The opening is recorded; that it repeats an earlier
  posting of the same role is the lineage as of the read, which a later
  verdict can change. An opening reads as `new` or `reposted`, never both.
- `source_health`: derived. Each source run is recorded; that its health
  moved (healthy, degraded, failing) is a comparison with the source's
  previous run, made at the read.
- `pursuit_due`: derived. A next action's due time is state the person can
  move, not an event: a read reports the pursuits whose due time passed
  within its window of wall-clock time, so a due time moved after it passed
  can be reported twice or not at all.
- `plugin_source_health`: unavailable. A plugin run's outcome is written over
  its own row when the run ends, so there is no ordered record to read.

Visibility is the Board's: a posting or source of a company the person hides
or does not follow is left out, as of the read. A pursuit is the person's own
record and is never hidden. A data category the person does not share is
absent from every page.
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Annotated, Any, Literal, get_args

from pydantic import AwareDatetime, BaseModel, Field, ValidationError, model_validator
from pydantic.config import JsonDict
from sqlalchemy import (
    ColumnElement,
    and_,
    case,
    false,
    literal,
    not_,
    or_,
    select,
    text,
    true,
    tuple_,
)
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from tracker.agents.operations.descriptor import (
    DataClass,
    EngineEffects,
    OperationDescriptor,
    Shape,
    ToolTier,
)
from tracker.agents.operations.envelope import NextAction, OperationError
from tracker.agents.operations.policy import category_disabled
from tracker.agents.operations.search import PAGE_BUDGET_BYTES
from tracker.company_store import off_board_company_slugs
from tracker.db.models import Job, JobLifecycleEvent, Pursuit, ScrapeSourceRun
from tracker.notifications.pursuit_due import TERMINAL_STAGES

_CODE: JsonDict = {"x-text": "code"}
_IDENTIFIER: JsonDict = {"x-text": "identifier"}
_EVERY_TIER: tuple[ToolTier, ...] = ("small", "standard", "full")

DEFAULT_LIMIT = 20
MAX_LIMIT = 100

Kind = Literal[
    "new", "closed", "reopened", "reposted", "stated_pay_changed", "pursuit_due", "source_health",
    "plugin_source_health",
]
KINDS: tuple[Kind, ...] = get_args(Kind)
Basis = Literal["recorded", "derived"]
#: How each kind is known; a kind missing here has no ordered record and is
#: reported in `unavailable`, never inferred.
KIND_BASIS: dict[Kind, Basis] = {
    "new": "recorded",
    "closed": "recorded",
    "reopened": "recorded",
    "stated_pay_changed": "recorded",
    "reposted": "derived",
    "source_health": "derived",
    "pursuit_due": "derived",
}
UNAVAILABLE: dict[Kind, str] = {"plugin_source_health": "no_ordered_record"}
#: The data category each kind belongs to.
KIND_CATEGORY: dict[Kind, DataClass] = {
    kind: "private_pursuit" if kind == "pursuit_due" else "public_posting" for kind in KINDS
}
#: Every category: what an engine without per-category choices shares.
ALL_CATEGORIES: frozenset[DataClass] = frozenset(get_args(DataClass))

Health = Literal["healthy", "degraded", "failing"]
_FAILING = ("failed", "blocked")
_REPOST_ROLES = ("repost", "duplicate")
_OPENINGS = ("opened", "added")

#: The streams a window merges, in the order they sort within one transaction.
_EVENTS, _RUNS, _DUE = 0, 1, 2
#: A window's phases: history from before positions, positioned rows, derived due times.
_HISTORY, _POSITIONED, _DERIVED = 0, 1, 2

_FORMAT = 1


class ChangesListInput(Shape):
    since: str | None = Field(
        default=None, min_length=1, max_length=1024,
        description=(
            "The next_since of the previous page: the read continues after it, in commit order, "
            "with the same kinds. Without it the read starts at start_time, or at the oldest change kept."
        ),
    )
    start_time: AwareDatetime | None = Field(
        default=None,
        description=(
            "Without since: start with the changes recorded at or after this time, with its UTC offset. "
            "Pursuits whose next action fell due from this time on are included. Later reads with "
            "the since this read gives keep the bound."
        ),
    )
    kinds: list[Kind] | None = Field(
        default=None,
        description=(
            "Only these kinds; every kind the person shares when left out. A since read keeps the kinds "
            "of the read it continues."
        ),
    )
    limit: int = Field(default=DEFAULT_LIMIT, ge=1, le=MAX_LIMIT, description="Events on one page.")
    tier: ToolTier = Field(default="small", description="The caller's tool tier, which bounds the page.")

    @model_validator(mode="after")
    def _one_start(self) -> ChangesListInput:
        if self.since is not None and self.start_time is not None:
            raise ValueError("give since or start_time, not both")
        if self.kinds is not None and len(set(self.kinds)) != len(self.kinds):
            raise ValueError("a kind is named twice")
        return self


class StatedBand(Shape):
    """One side of a stated-pay change: the employer's base band as stated."""

    low: int | None
    high: int | None
    currency: str | None = Field(json_schema_extra=_CODE)
    period: str | None = Field(json_schema_extra=_CODE)


class StatedPayChange(Shape):
    before: StatedBand
    after: StatedBand


class SourceHealthChange(Shape):
    state: Health = Field(json_schema_extra=_CODE)
    #: Null on a source's first run.
    previous_state: Health | None = Field(json_schema_extra=_CODE)
    #: The run's own outcome, of which `state` is the class.
    outcome: str = Field(json_schema_extra=_CODE)
    provider: str = Field(json_schema_extra=_IDENTIFIER)


class ChangeEvent(Shape):
    #: Stable and unique per event: a caller that reads a page twice dedupes by it.
    sequence: str = Field(json_schema_extra=_IDENTIFIER)
    kind: Kind = Field(json_schema_extra=_CODE)
    #: `recorded` when the event is a row of its own; `derived` when the kind
    #: is a reading of recorded rows or state, made at this read.
    basis: Basis = Field(json_schema_extra=_CODE)
    #: When it happened; for `pursuit_due`, the time the next action fell due.
    at: datetime
    #: The posting to read next with `opportunities.get` (or `pursuits.get`).
    opportunity_id: int | None = None
    company: str | None = Field(default=None, json_schema_extra=_IDENTIFIER)
    pay: StatedPayChange | None = None
    source: SourceHealthChange | None = None


class UnavailableKind(Shape):
    kind: Kind = Field(json_schema_extra=_CODE)
    reason: str = Field(json_schema_extra=_CODE)


class ChangesPage(Shape):
    count: int = Field(ge=0)
    events: list[ChangeEvent]
    #: True when this page reached the read's frontier: nothing more until a
    #: change commits. False while `continue_with` reads more now.
    caught_up: bool
    #: The position after this page; pass it as `since` next time.
    next_since: str = Field(json_schema_extra=_IDENTIFIER)
    #: Requested kinds this engine has no ordered record of.
    unavailable: list[UnavailableKind]
    continue_with: list[NextAction] = Field(default_factory=list)


CHANGES_LIST = OperationDescriptor(
    id="changes.list",
    summary=(
        "List what changed after a position, in commit order: new, closed, reopened and reposted postings, "
        "stated-pay changes, pursuit actions falling due and source health. Pass next_since back as since."
    ),
    input=ChangesListInput,
    result=ChangesPage,
    access="read",
    idempotency="read",
    engine_effects=EngineEffects(),
    tool_tiers=_EVERY_TIER,
    data_classes=("public_posting", "private_pursuit"),
    examples=(
        {"start_time": "2026-11-14T00:00:00Z"},
        {"since": "<next_since of the previous page>", "limit": 20},
    ),
)

OPERATIONS: tuple[OperationDescriptor, ...] = (CHANGES_LIST,)


# --- positions ----------------------------------------------------------------- #


#: The range a position's times may take, in microseconds from the epoch: the
#: datetimes Python can hold, so a forged position is refused, not overflowed.
_EARLIEST = -62_135_596_800_000_000
_LATEST = 253_402_300_799_999_999
_Micros = Annotated[int, Field(ge=_EARLIEST, le=_LATEST)]
_Xact = Annotated[int, Field(ge=0, le=2**63 - 1)]
_Phase = Annotated[int, Field(ge=0, le=2)]


class _Position(BaseModel):
    """What a `since` token holds. `lo` None reads the history before positions."""

    f: int
    #: Digests of the workspace, the principal and the kinds the read asked for.
    w: str
    p: str
    k: str
    #: The cluster's system identifier, as text: JSON numbers lose its low bits.
    c: str
    lo: _Xact | None
    #: The window's frontier and wall-clock end, fixed when the window opens.
    hi: _Xact | None
    th: _Micros | None
    #: The due-time window's exclusive start, in microseconds; None is no bound.
    tl: _Micros | None
    #: The read's start_time, in microseconds: a row recorded before it is
    #: never answered, even one whose transaction commits after a later window.
    st: _Micros | None
    #: The last key read in this window: (phase, transaction or due time, stream, id).
    a: tuple[_Phase, Annotated[int, Field(ge=_EARLIEST, le=2**63 - 1)], _Phase, _Xact] | None

    @model_validator(mode="after")
    def _key_in_range(self) -> _Position:
        if self.a is not None and self.a[0] == _DERIVED and self.a[1] > _LATEST:
            raise ValueError("a due time past the datetimes a position can hold")
        if self.a is not None and self.a[0] != _DERIVED and self.a[1] < 0:
            raise ValueError("a transaction id below zero")
        return self


def _digest(*parts: object) -> str:
    return hashlib.sha256(json.dumps(parts, separators=(",", ":"), default=str).encode()).hexdigest()[:12]


def _micros(moment: datetime) -> int:
    return (moment - _EPOCH) // timedelta(microseconds=1)


def _moment(micros: int) -> datetime:
    return _EPOCH + timedelta(microseconds=micros)


_EPOCH = datetime(1970, 1, 1, tzinfo=UTC)


def encode_position(position: _Position) -> str:
    return base64.urlsafe_b64encode(position.model_dump_json().encode()).decode().rstrip("=")


def _refused(reason: str, message: str, *, resume_at: datetime | None = None) -> OperationError:
    arguments: dict[str, Any] = {} if resume_at is None else {"start_time": resume_at.isoformat()}
    return OperationError(
        "invalid_input",
        message,
        details={"field": "since", "reason": reason},
        next_actions=[NextAction(operation=CHANGES_LIST.id, arguments=arguments)],
    )


def decode_position(token: str, *, expected: _Position) -> _Position:
    """The position a `since` token resumes, or `invalid_input` naming why it
    cannot: never a silent restart."""
    try:
        raw = base64.urlsafe_b64decode(token + "=" * (-len(token) % 4))
        position = _Position.model_validate_json(raw)
    except (binascii.Error, ValueError, ValidationError):
        raise _refused(
            "malformed",
            "This is not a since value from changes.list. Start again with start_time, or without since.",
        ) from None
    # Where a fresh read picks up for a position that cannot continue: the end
    # of its window when one was open, else the start of its due window.
    last = position.th if position.th is not None else position.tl
    resume = None if last is None else _moment(last)
    if position.f != _FORMAT:
        raise _refused("expired", "This since value is from another version of the feed.", resume_at=resume)
    if position.w != expected.w:
        raise _refused("other_workspace", "This since value belongs to another workspace.")
    if position.p != expected.p:
        raise _refused("other_principal", "This since value belongs to another assistant.")
    if position.k != expected.k:
        raise _refused(
            "other_filters",
            "This since value continues a read of other kinds. Pass the same kinds, or start again.",
            resume_at=resume,
        )
    if position.c != expected.c:
        raise _refused(
            "expired",
            "The database was restored or moved since this position was given, so it no longer applies. "
            "Start again from the time of your last read.",
            resume_at=resume,
        )
    windowed = (position.hi, position.th)
    if (None in windowed) != (windowed == (None, None)) or (position.a is not None and position.hi is None):
        raise _refused("malformed", "This since value is not one changes.list gave.")
    return position


# --- reading -------------------------------------------------------------------- #


@dataclass(frozen=True)
class _Frontier:
    #: Every transaction of this database below this one has ended.
    xmin: int
    #: The next transaction id the cluster gives out.
    xmax: int
    now: datetime
    cluster: str


#: The read's frontier, in one statement so that its snapshot is taken before
#: the sessions are listed. Transaction ids are the cluster's, but only a
#: transaction of this database can write its rows, so the frontier is the
#: oldest one of those still running (a prepared one included), or the
#: snapshot's end when none is. A transaction that was running at the
#: snapshot and has ended by the listing is over, which is all the frontier
#: needs; one that starts after the snapshot has an id at or past its end.
#: Without the right to see every session's transaction the listing could miss
#: one, so the frontier falls back to the cluster's oldest running transaction.
_FRONTIER = text(
    "SELECT pg_snapshot_xmin(s.snap), pg_snapshot_xmax(s.snap),"
    " (SELECT min(x) FROM pg_snapshot_xip(s.snap) AS x WHERE xid(x) IN ("
    "   SELECT backend_xid FROM pg_stat_activity"
    "   WHERE datname = current_database() AND backend_xid IS NOT NULL"
    "   UNION ALL SELECT transaction FROM pg_prepared_xacts WHERE database = current_database())),"
    " current_setting('is_superuser') = 'on' OR pg_has_role(current_user, 'pg_read_all_stats', 'MEMBER'),"
    " clock_timestamp(), (pg_control_system()).system_identifier"
    " FROM (SELECT pg_current_snapshot() AS snap) AS s"
)


async def _frontier(session: AsyncSession) -> _Frontier:
    # The session listing is cached for the rest of a transaction once read;
    # cleared first, it is read afresh by the statement below.
    await session.execute(text("SELECT pg_stat_clear_snapshot()"))
    cluster_xmin, xmax, oldest_here, sees_all, now, cluster = (await session.execute(_FRONTIER)).one()
    frontier = (oldest_here if oldest_here is not None else xmax) if sees_all else cluster_xmin
    return _Frontier(int(frontier), int(xmax), now, str(cluster))


@dataclass(frozen=True)
class _Candidate:
    key: tuple[int, int, int, int]
    event: ChangeEvent


def _health(outcome: Any) -> ColumnElement[str]:
    return case((outcome.in_(_FAILING), "failing"), (outcome == "degraded", "degraded"), else_="healthy")


def _health_of(outcome: str) -> Health:
    return "failing" if outcome in _FAILING else "degraded" if outcome == "degraded" else "healthy"


def _after(
    stream: int, xact: Any, row_id: Any, after: tuple[int, int, int, int] | None, *, phase: int
) -> ColumnElement[bool]:
    """Rows of `stream` in `phase` that sort after the last key read."""
    if after is None or after[0] < phase:
        return true()
    if after[0] > phase:
        return false()
    _, last_xact, last_stream, last_id = after
    same: ColumnElement[bool] = (
        true() if stream > last_stream else row_id > last_id if stream == last_stream else false()
    )
    if phase == _HISTORY:
        return same
    return or_(xact > last_xact, and_(xact == last_xact, same))


def _segment(
    table: Any, stream: int, position: _Position, cluster: str, *, phase: int, start: datetime | None, at: Any
) -> ColumnElement[bool] | None:
    """The rows of one record that a phase of this window reads, or None."""
    after = _after(stream, table.change_xact, table.id, position.a, phase=phase)
    if phase == _HISTORY:
        if position.lo is not None:
            return None
        clause = and_(
            or_(table.change_xact.is_(None), table.change_cluster.is_distinct_from(int(cluster))), after
        )
    else:
        assert position.hi is not None
        clause = and_(
            table.change_cluster == int(cluster),
            table.change_xact >= (position.lo or 0),
            table.change_xact < position.hi,
            after,
        )
    return clause if start is None else and_(clause, at >= start)


def _order(table: Any, phase: int) -> tuple[Any, ...]:
    return (table.id,) if phase == _HISTORY else (table.change_xact, table.id)


async def _lifecycle(
    session: AsyncSession, position: _Position, cluster: str, served: frozenset[Kind], hidden: list[str],
    *, limit: int,
) -> list[_Candidate]:
    wanted: list[ColumnElement[bool]] = []
    openings = {"new", "reposted"} & served
    if openings:
        is_repost = Job.lineage_role.in_(_REPOST_ROLES)
        lineage = (
            true() if len(openings) == 2
            else and_(Job.lineage_role.is_not(None), is_repost) if "reposted" in openings
            else or_(Job.lineage_role.is_(None), not_(is_repost))
        )
        wanted.append(and_(JobLifecycleEvent.event_type.in_(_OPENINGS), lineage))
    for kind in ("closed", "reopened"):
        if kind in served:
            wanted.append(JobLifecycleEvent.event_type == kind)
    if "stated_pay_changed" in served:
        wanted.append(
            and_(JobLifecycleEvent.event_type == "changed", JobLifecycleEvent.detail.has_key("disclosed_base"))
        )
    if not wanted:
        return []
    start = None if position.st is None else _moment(position.st)
    found: list[_Candidate] = []
    for phase in (_HISTORY, _POSITIONED):
        segment = _segment(
            JobLifecycleEvent, _EVENTS, position, cluster, phase=phase, start=start, at=JobLifecycleEvent.created_at
        )
        if segment is None:
            continue
        statement = (
            select(JobLifecycleEvent, Job.company, Job.lineage_role)
            .join(Job, Job.id == JobLifecycleEvent.job_id)
            .where(segment, or_(*wanted))
            .order_by(*_order(JobLifecycleEvent, phase))
            .limit(limit)
        )
        if hidden:
            statement = statement.where(Job.company.not_in(hidden))
        for event, company, lineage_role in (await session.execute(statement)).all():
            found.append(_Candidate(
                (phase, int(event.change_xact or 0) if phase == _POSITIONED else 0, _EVENTS, event.id),
                _lifecycle_event(event, company, lineage_role),
            ))
    return found


def _lifecycle_event(event: JobLifecycleEvent, company: str, lineage_role: str | None) -> ChangeEvent:
    common: dict[str, Any] = {
        "sequence": f"job_event:{event.id}", "at": event.created_at, "opportunity_id": event.job_id,
        "company": company,
    }
    if event.event_type in _OPENINGS:
        kind: Kind = "reposted" if lineage_role in _REPOST_ROLES else "new"
        return ChangeEvent(kind=kind, basis=KIND_BASIS[kind], **common)
    if event.event_type == "closed":
        return ChangeEvent(kind="closed", basis="recorded", **common)
    if event.event_type == "reopened":
        return ChangeEvent(kind="reopened", basis="recorded", **common)
    band = (event.detail or {}).get("disclosed_base") or {}
    return ChangeEvent(
        kind="stated_pay_changed", basis="recorded",
        pay=StatedPayChange(before=_band(band.get("from")), after=_band(band.get("to"))), **common,
    )


def _band(side: Any) -> StatedBand:
    side = side if isinstance(side, dict) else {}

    def whole(value: Any) -> int | None:
        return round(value) if isinstance(value, int | float) and not isinstance(value, bool) else None

    return StatedBand(
        low=whole(side.get("min")), high=whole(side.get("max")),
        currency=side.get("currency") if isinstance(side.get("currency"), str) else None,
        period=side.get("period") if isinstance(side.get("period"), str) else None,
    )


async def _source_runs(
    session: AsyncSession, position: _Position, cluster: str, hidden: list[str], *, limit: int
) -> list[_Candidate]:
    run = ScrapeSourceRun
    earlier = aliased(ScrapeSourceRun)
    previous = (
        select(earlier.outcome)
        .where(
            earlier.binding_id == run.binding_id,
            earlier.id < run.id,
            earlier.scan_mode != "shadow",
            earlier.outcome != "unattempted",
        )
        .order_by(earlier.id.desc())
        .limit(1)
        .lateral("previous")
    )
    moved = or_(
        and_(previous.c.outcome.is_(None), _health(run.outcome) != "healthy"),
        and_(previous.c.outcome.is_not(None), _health(run.outcome) != _health(previous.c.outcome)),
    )
    start = None if position.st is None else _moment(position.st)
    found: list[_Candidate] = []
    for phase in (_HISTORY, _POSITIONED):
        segment = _segment(run, _RUNS, position, cluster, phase=phase, start=start, at=run.finished_at)
        if segment is None:
            continue
        statement = (
            select(run, previous.c.outcome)
            .outerjoin(previous, true())
            .where(segment, run.scan_mode != "shadow", run.outcome != "unattempted", moved)
            .order_by(*_order(run, phase))
            .limit(limit)
        )
        if hidden:
            statement = statement.where(run.company_slug.not_in(hidden))
        for row, before in (await session.execute(statement)).all():
            found.append(_Candidate(
                (phase, int(row.change_xact or 0) if phase == _POSITIONED else 0, _RUNS, row.id),
                ChangeEvent(
                    sequence=f"source_run:{row.id}", kind="source_health", basis="derived", at=row.finished_at,
                    company=row.company_slug,
                    source=SourceHealthChange(
                        state=_health_of(row.outcome),
                        previous_state=None if before is None else _health_of(before),
                        outcome=row.outcome, provider=row.provider_key,
                    ),
                ),
            ))
    return found


async def _due(session: AsyncSession, position: _Position, *, limit: int) -> list[_Candidate]:
    assert position.th is not None
    after = position.a
    if after is not None and after[0] > _DERIVED:
        return []
    statement = (
        select(Pursuit.id, Pursuit.job_id, Pursuit.next_action_due, Job.company)
        .join(Job, Job.id == Pursuit.job_id)
        .where(
            Pursuit.next_action_due.is_not(None),
            Pursuit.next_action_due <= _moment(position.th),
            Pursuit.stage.not_in(TERMINAL_STAGES),
        )
        .order_by(Pursuit.next_action_due, Pursuit.id)
        .limit(limit)
    )
    if position.tl is not None:
        statement = statement.where(Pursuit.next_action_due > _moment(position.tl))
    if after is not None and after[0] == _DERIVED:
        statement = statement.where(
            tuple_(Pursuit.next_action_due, Pursuit.id) > tuple_(literal(_moment(after[1])), literal(after[3]))
        )
    return [
        _Candidate(
            (_DERIVED, _micros(due), _DUE, pursuit_id),
            ChangeEvent(
                sequence=f"pursuit_due:{pursuit_id}:{_micros(due)}", kind="pursuit_due", basis="derived", at=due,
                opportunity_id=job_id, company=company,
            ),
        )
        for pursuit_id, job_id, due, company in (await session.execute(statement)).all()
    ]


@dataclass(frozen=True)
class ChangesAnswer:
    page: ChangesPage
    #: True when the tier's budget ended the page before `limit` events.
    shortened: bool


def _size(value: BaseModel) -> int:
    return len(value.model_dump_json().encode())


async def changes_page(
    session: AsyncSession,
    params: ChangesListInput,
    *,
    workspace_id: str,
    principal_id: str,
    shared: frozenset[DataClass] = ALL_CATEGORIES,
) -> ChangesAnswer:
    """One page of the feed after `params.since`, or from its start."""
    asked: tuple[Kind, ...] = tuple(sorted(params.kinds)) if params.kinds is not None else KINDS
    for kind in params.kinds or ():
        # A kind asked for by name is refused, as a search filter is; the whole
        # feed only leaves the withheld kinds out.
        if KIND_CATEGORY[kind] not in shared:
            raise category_disabled(KIND_CATEGORY[kind], field="kinds")
    in_view = frozenset(kind for kind in asked if KIND_CATEGORY[kind] in shared)
    served = frozenset(kind for kind in in_view if kind not in UNAVAILABLE)
    unavailable = [UnavailableKind(kind=kind, reason=UNAVAILABLE[kind]) for kind in KINDS
                   if kind in in_view and kind in UNAVAILABLE]

    frontier = await _frontier(session)
    expected = _Position(
        f=_FORMAT, w=_digest(workspace_id), p=_digest(workspace_id, principal_id), k=_digest(asked),
        c=frontier.cluster, lo=None, hi=None, th=None, tl=None, st=None, a=None,
    )
    if params.since is not None:
        position = decode_position(params.since, expected=expected)
        past_end = any(bound is not None and bound > frontier.xmax for bound in (position.lo, position.hi))
        backwards = position.lo is not None and position.hi is not None and position.lo > position.hi
        if past_end or backwards:
            raise _refused("malformed", "This since value is not one this database gave.")
    else:
        start = None if params.start_time is None else _micros(params.start_time)
        position = expected.model_copy(update={"st": start, "tl": None if start is None else start - 1})
    if position.hi is None:
        # A window opens: its frontier and its wall-clock end are fixed for every page of it.
        # Never below where the position starts: a frontier read with less
        # sight (the cluster's, when sessions cannot all be seen) may be lower,
        # and a window that moved back would answer its rows again.
        hi = frontier.xmin if position.lo is None else max(frontier.xmin, position.lo)
        position = position.model_copy(update={"hi": hi, "th": _micros(frontier.now)})

    room = params.limit + 1
    hidden = list(await off_board_company_slugs(session))
    candidates = [
        *await _lifecycle(session, position, frontier.cluster, served, hidden, limit=room),
        *(await _source_runs(session, position, frontier.cluster, hidden, limit=room)
          if "source_health" in served else []),
        *(await _due(session, position, limit=room) if "pursuit_due" in served else []),
    ]
    candidates.sort(key=lambda candidate: candidate.key)
    candidates = candidates[:room]

    budget = PAGE_BUDGET_BYTES[params.tier]
    kept = candidates[: params.limit]
    while True:
        page = _page(kept, position, more=len(candidates) > len(kept), tier=params.tier,
                     limit=params.limit, kinds=params.kinds, unavailable=unavailable)
        if _size(page) <= budget or len(kept) <= 1:
            break
        kept = kept[:-1]
    if _size(page) > budget:
        raise OperationError(
            "invalid_input",
            "One change does not fit the tier's budget; read with a larger tier.",
            details={"field": "tier", "reason": "over_budget", "budget_bytes": budget},
        )
    return ChangesAnswer(page, shortened=len(kept) < min(params.limit, len(candidates)))


def _later(bound: int | None, end: int | None) -> int | None:
    """The next due-time window's start: where this one ended, or a start_time
    still ahead of it, which keeps every due time before start_time out."""
    return end if bound is None or end is None else max(bound, end)


def _page(
    kept: list[_Candidate], position: _Position, *, more: bool, tier: ToolTier, limit: int,
    kinds: list[Kind] | None, unavailable: list[UnavailableKind],
) -> ChangesPage:
    if more:
        following = position.model_copy(update={"a": kept[-1].key if kept else position.a})
    else:
        # The window is read to its frontier: the next read opens a new one from there.
        following = position.model_copy(
            update={"lo": position.hi, "hi": None, "tl": _later(position.tl, position.th), "th": None, "a": None}
        )
    token = encode_position(following)
    arguments: dict[str, Any] = {"since": token, "limit": limit, "tier": tier}
    if kinds is not None:
        arguments["kinds"] = list(kinds)
    continuing = [NextAction(operation=CHANGES_LIST.id, arguments=arguments)]
    return ChangesPage(
        count=len(kept),
        events=[candidate.event for candidate in kept],
        caught_up=not more,
        next_since=token,
        unavailable=unavailable,
        continue_with=continuing if more else [],
    )

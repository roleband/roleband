"""Pursuit state writes. Current row + append-only event in one transaction."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Literal
from urllib.parse import urlsplit

from pydantic import BaseModel, Field, field_validator
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from tracker.db.models import (
    Favorite,
    Job,
    Pursuit,
    PursuitComment,
    PursuitEvent,
    PursuitInterview,
)
from tracker.platform.locks import advisory_xact_lock_pair

PursuitStage = Literal[
    "saved",
    "researching",
    "networking",
    "applied",
    "interviewing",
    "offer",
    "accepted",
    "declined",
    "withdrawn",
    "rejected",
    "role_closed",
]

#: The user's own endings: each can be reversed, and Withdrawn can re-engage
#: while the posting is open.
DECIDED_STAGES = frozenset({"accepted", "declined", "withdrawn"})
#: Endings the company or the world decided. Only these never move again.
CLOSED_STAGES = frozenset({"rejected", "role_closed"})
#: A role at one of these has left the moving stages.
ENDED_STAGES = DECIDED_STAGES | CLOSED_STAGES


# A partial write: an ABSENT field is left alone, and `None` is how the model
# spells absent, which is why every field below is optional.
#
# `stage` and `priority` are NOT NULL in the table, so an explicit `null` for
# either asks for a value the row cannot hold, and would reach the flush as a
# 500. The guard is on the MODEL rather than in the route because both writers
# construct one: the HTTP route passes the body straight through, and MCP drops
# `None` before constructing, so only the route could ever send one. The other
# three columns ARE nullable, and a `null` there is a legitimate "clear this"
# (the only way the route offers to take a follow-up back off), so the guard
# names two fields and not all five.
#
# Deliberately NOT a docstring: a Pydantic docstring is published as the
# schema's `description`, so this prose would land in `openapi.json` and
# `api.gen.ts` and make a behaviour guard into a wire change.
class PursuitUpdate(BaseModel):
    stage: PursuitStage | None = None
    priority: int | None = Field(default=None, ge=1, le=5)
    notes: str | None = Field(json_schema_extra={"x-text": "content"}, default=None, max_length=20_000)
    next_action: str | None = Field(default=None, max_length=2_000)
    next_action_due: datetime | None = None

    # `mode="before"` on a field with a default runs ONLY when the key is
    # present, which is exactly the distinction needed: absent is "leave it",
    # null is a request the table must refuse.
    @field_validator("stage", "priority", mode="before")
    @classmethod
    def _reject_explicit_null(cls, value: object) -> object:
        if value is None:
            raise ValueError("cannot be null; omit the field to leave it unchanged")
        return value


#: The two-int lock namespace for writes to one role's saved state and pursuit
#: (`favorites`, `pursuits`, `pursuit_events`), keyed by job id.
ROLE_WRITE_LOCK_NAMESPACE = 91244


async def lock_role_writes(session: AsyncSession, job_id: int) -> None:
    """Serialize every writer of one role's saved state and pursuit until the
    transaction ends: the star, unsave, a pursuit write from the dashboard or
    the agent. Without it each read-then-insert below races between two
    clients (a second tab, the MCP agent beside a click): both see no row, both
    insert, the second commit fails; two stage changes both record the same old
    stage. Never a row lock on `jobs`: the scan writers hold those until each
    company commits."""
    await advisory_xact_lock_pair(session, ROLE_WRITE_LOCK_NAMESPACE, job_id)


async def ensure_favorite(session: AsyncSession, job_id: int) -> bool:
    """Save the job unless it already is. Returns whether a row was added.

    `favorites.job_id` is UNIQUE, so "insert unless one exists" is not tidiness:
    a second insert is an IntegrityError and a 500. Two independent writers
    reach this table, the star on a job row and a pursuit write (which saves
    the job on the way past), and both go through here. ON CONFLICT is avoided
    so fake/test sessions and real sessions use the same straightforward ORM
    path.

    The caller owns the transaction: this flushes nothing and commits nothing,
    which is why it reports whether it added anything. The star route commits
    only when it did.
    """
    await lock_role_writes(session, job_id)
    existing = await session.scalar(select(Favorite.id).where(Favorite.job_id == job_id))
    if existing is not None:
        return False
    session.add(Favorite(job_id=job_id))
    return True


def public_pursuit(pursuit: Pursuit, job: Job | None = None) -> dict:
    data = {
        "id": pursuit.id,
        "job_id": pursuit.job_id,
        "stage": pursuit.stage,
        "priority": pursuit.priority,
        "notes": pursuit.notes,
        "next_action": pursuit.next_action,
        "next_action_due": pursuit.next_action_due,
        "created_at": pursuit.created_at,
        "updated_at": pursuit.updated_at,
    }
    if job is not None:
        data["opportunity"] = {
            "title": job.title,
            "company": job.company,
            "status": job.status,
            "url": job.url,
        }
    return data


def _stored(values: dict[str, object]) -> dict[str, object]:
    """Field values as the event's JSON column keeps them."""
    return {field: value.isoformat() if isinstance(value, datetime) else value for field, value in values.items()}


async def upsert_pursuit(
    session: AsyncSession,
    job_id: int,
    payload: PursuitUpdate,
    *,
    actor: Literal["user", "agent"],
) -> Pursuit:
    job = await session.get(Job, job_id)
    if job is None:
        raise LookupError("opportunity not found")

    # Before the read the event's `from_stage` is taken from.
    await lock_role_writes(session, job_id)
    pursuit = await session.scalar(
        select(Pursuit).where(Pursuit.job_id == job_id).execution_options(populate_existing=True)
    )
    created = pursuit is None
    if pursuit is None:
        pursuit = Pursuit(job_id=job_id)
        session.add(pursuit)
        await session.flush()

    before = pursuit.stage
    changed: dict[str, object] = {}
    replaced: dict[str, object] = {}
    values = payload.model_dump(exclude_unset=True)
    for field, value in values.items():
        if getattr(pursuit, field) != value:
            replaced[field] = getattr(pursuit, field)
            setattr(pursuit, field, value)
            changed[field] = value

    # Pursuing a job implies it is saved.
    await ensure_favorite(session, job_id)

    if created or changed:
        session.add(
            PursuitEvent(
                pursuit_id=pursuit.id,
                actor=actor,
                event_type="created" if created else "updated",
                from_stage=None if created else before,
                to_stage=pursuit.stage,
                # Both versions of every field, so a write never loses what
                # it replaced (an agent's note over the user's own).
                detail={"changed": sorted(changed), "before": _stored(replaced), "after": _stored(changed)},
            )
        )
    await session.flush()
    return pursuit


async def ensure_pursuit(
    session: AsyncSession, job_id: int, *, actor: Literal["user", "agent"]
) -> Pursuit:
    """The pursuit for one role, created at Considering if it has none yet.

    A star alone is a Considering card with no row behind it; the first
    comment or interview on it needs one to hang from. Raises `LookupError`
    for an unknown job."""
    return await upsert_pursuit(session, job_id, PursuitUpdate(), actor=actor)


# --- comments ------------------------------------------------------------------


class CommentWrite(BaseModel):
    body: str = Field(json_schema_extra={"x-text": "content"}, min_length=1, max_length=20_000)

    @field_validator("body")
    @classmethod
    def _not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("a comment needs some text")
        return value


class CommentNotEditable(Exception):
    """An agent's comment: the user may read it, not rewrite it."""


async def _comment_on(session: AsyncSession, job_id: int, comment_id: int) -> PursuitComment:
    """The comment, if it belongs to this role's pursuit. `LookupError` otherwise,
    so an id from another role is never reached through this one's route."""
    comment = await session.scalar(
        select(PursuitComment)
        .join(Pursuit, Pursuit.id == PursuitComment.pursuit_id)
        .where(PursuitComment.id == comment_id, Pursuit.job_id == job_id)
    )
    if comment is None:
        raise LookupError("comment not found")
    return comment


async def add_comment(
    session: AsyncSession, job_id: int, payload: CommentWrite, *, actor: Literal["user", "agent"]
) -> PursuitComment:
    pursuit = await ensure_pursuit(session, job_id, actor=actor)
    comment = PursuitComment(pursuit_id=pursuit.id, actor=actor, body=payload.body)
    session.add(comment)
    await session.flush()
    return comment


async def edit_comment(
    session: AsyncSession, job_id: int, comment_id: int, payload: CommentWrite
) -> PursuitComment:
    await lock_role_writes(session, job_id)
    comment = await _comment_on(session, job_id, comment_id)
    if comment.actor != "user":
        raise CommentNotEditable("only the user's own comments can be edited")
    if comment.body != payload.body:
        comment.body = payload.body
        comment.edited_at = datetime.now(UTC)
        await session.flush()
    return comment


async def delete_comment(session: AsyncSession, job_id: int, comment_id: int) -> None:
    await lock_role_writes(session, job_id)
    comment = await _comment_on(session, job_id, comment_id)
    if comment.actor != "user":
        raise CommentNotEditable("only the user's own comments can be deleted")
    await session.delete(comment)
    await session.flush()


def public_comment(comment: PursuitComment) -> dict:
    return {
        "id": comment.id,
        "actor": comment.actor,
        "body": comment.body,
        "source": comment.source,
        "created_at": comment.created_at,
        "edited_at": comment.edited_at,
    }


# --- interviews ----------------------------------------------------------------

InterviewFormat = Literal["video", "phone", "onsite"]
InterviewOutcome = Literal["passed", "not_passed", "cancelled"]


def _web_link(value: str | None) -> str | None:
    """An interview's link is opened from the page as a join button, so only a
    web address is stored: any other scheme would hand the click to whatever
    the system registers for it, and a bare host would open as a path inside
    the dashboard. `None` clears it."""
    if value is None:
        return None
    link = value.strip()
    parts = urlsplit(link)
    if parts.scheme.lower() not in {"http", "https"} or not parts.netloc:
        raise ValueError("a link is a web address that starts with http:// or https://")
    return link


class InterviewWrite(BaseModel):
    label: str = Field(json_schema_extra={"x-text": "content"}, min_length=1, max_length=120)
    scheduled_at: datetime
    all_day: bool = False
    format: InterviewFormat | None = None
    link: str | None = Field(default=None, max_length=2_000)
    outcome: InterviewOutcome | None = None
    notes: str | None = Field(json_schema_extra={"x-text": "content"}, default=None, max_length=20_000)

    _link_is_web = field_validator("link")(_web_link)


# A partial write, as `PursuitUpdate`: absent is "leave it". `label`,
# `scheduled_at` and `all_day` are NOT NULL, so an explicit null for them is
# refused; a null on the others clears them.
class InterviewUpdate(BaseModel):
    label: str | None = Field(json_schema_extra={"x-text": "content"}, default=None, min_length=1, max_length=120)
    scheduled_at: datetime | None = None
    all_day: bool | None = None
    format: InterviewFormat | None = None
    link: str | None = Field(default=None, max_length=2_000)
    outcome: InterviewOutcome | None = None
    notes: str | None = Field(json_schema_extra={"x-text": "content"}, default=None, max_length=20_000)

    @field_validator("label", "scheduled_at", "all_day", mode="before")
    @classmethod
    def _reject_explicit_null(cls, value: object) -> object:
        if value is None:
            raise ValueError("cannot be null; omit the field to leave it unchanged")
        return value

    _link_is_web = field_validator("link")(_web_link)


async def _interview_on(session: AsyncSession, job_id: int, interview_id: int) -> PursuitInterview:
    interview = await session.scalar(
        select(PursuitInterview)
        .join(Pursuit, Pursuit.id == PursuitInterview.pursuit_id)
        .where(PursuitInterview.id == interview_id, Pursuit.job_id == job_id)
        .execution_options(populate_existing=True)
    )
    if interview is None:
        raise LookupError("interview not found")
    return interview


async def add_interview(
    session: AsyncSession, job_id: int, payload: InterviewWrite, *, actor: Literal["user", "agent"]
) -> PursuitInterview:
    pursuit = await ensure_pursuit(session, job_id, actor=actor)
    interview = PursuitInterview(pursuit_id=pursuit.id, **payload.model_dump())
    session.add(interview)
    await session.flush()
    return interview


async def update_interview(
    session: AsyncSession, job_id: int, interview_id: int, payload: InterviewUpdate
) -> PursuitInterview:
    await lock_role_writes(session, job_id)
    interview = await _interview_on(session, job_id, interview_id)
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(interview, field, value)
    await session.flush()
    return interview


async def delete_interview(session: AsyncSession, job_id: int, interview_id: int) -> None:
    await lock_role_writes(session, job_id)
    interview = await _interview_on(session, job_id, interview_id)
    await session.delete(interview)
    await session.flush()


def public_interview(interview: PursuitInterview) -> dict:
    return {
        "id": interview.id,
        "label": interview.label,
        "scheduled_at": interview.scheduled_at,
        "all_day": interview.all_day,
        "format": interview.format,
        "link": interview.link,
        "outcome": interview.outcome,
        "notes": interview.notes,
        "created_at": interview.created_at,
        "updated_at": interview.updated_at,
    }


async def list_pursuits(
    session: AsyncSession,
    *,
    stage: PursuitStage | None = None,
    limit: int = 50,
) -> list[dict]:
    stmt = select(Pursuit, Job).join(Job, Job.id == Pursuit.job_id)
    if stage is not None:
        stmt = stmt.where(Pursuit.stage == stage)
    rows = (
        await session.execute(
            stmt.order_by(Pursuit.priority.asc(), Pursuit.updated_at.desc()).limit(limit)
        )
    ).all()
    return [public_pursuit(pursuit, job) for pursuit, job in rows]

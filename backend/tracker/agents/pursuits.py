"""Pursuit state writes. Current row + append-only event in one transaction."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from dataclasses import field as dataclass_field
from datetime import UTC, datetime, timedelta
from typing import Annotated, Any, Literal
from urllib.parse import urlsplit

from pydantic import AfterValidator, BaseModel, Field, field_validator, model_validator
from sqlalchemy import and_, case, exists, func, literal, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from tracker.agents.receipts import RevisionConflict
from tracker.db.models import (
    Favorite,
    Job,
    Pursuit,
    PursuitComment,
    PursuitEvent,
    PursuitInterview,
    PursuitStep,
)
from tracker.notifications.pursuit_due import generate_pursuit_due_notifications
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

def _as_utc(value: datetime) -> datetime:
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)


#: A moment of the person's, always carrying an offset: a bare datetime is
#: read as UTC where it enters, so every stored and compared instant agrees.
Instant = Annotated[datetime, AfterValidator(_as_utc)]


def refuse_null(value: object) -> object:
    """The `mode="before"` guard of a field whose column cannot hold null:
    absent leaves it, an explicit null is refused."""
    if value is None:
        raise ValueError("cannot be null; omit the field to leave it unchanged")
    return value


# A partial write: an ABSENT field is left alone, and `None` is how the model
# spells absent, which is why every field below is optional.
#
# `stage` and `priority` are NOT NULL in the table, so an explicit `null` for
# either asks for a value the row cannot hold, and would reach the flush as a
# 500. The guard is on the MODEL rather than in a route because every writer
# constructs one, so no writer can pass a `null` through. The other
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
    next_action_due: Instant | None = None

    # `mode="before"` on a field with a default runs ONLY when the key is
    # present, which is exactly the distinction needed: absent is "leave it",
    # null is a request the table must refuse.
    _no_null = field_validator("stage", "priority", mode="before")(refuse_null)


#: The two-int lock namespace for writes to one role's saved state and pursuit
#: (`favorites`, `pursuits`, `pursuit_events`), keyed by job id.
ROLE_WRITE_LOCK_NAMESPACE = 91244


async def lock_role_writes(session: AsyncSession, job_id: int) -> None:
    """Serialize every writer of one role's saved state and pursuit until the
    transaction ends: the star, unsave, a pursuit write from the dashboard or
    the agent. Without it each read-then-insert below races between two
    clients (a second tab, an agent beside a click): both see no row, both
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


#: How long the person may pause writing the notes before the next save
#: starts a new writing session, and with it a new entry in the role's history.
NOTES_SESSION_GAP = timedelta(minutes=10)


def continues_notes(event: type[PursuitEvent] = PursuitEvent) -> Any:
    """An event that only carried on a notes writing session: History shows
    the session once, as its first event, and keeps no copy of the notes in
    the events after it."""
    return and_(event.detail.has_key("session"), event.detail["changed"].astext == '["notes"]')


async def _notes_session(session: AsyncSession, pursuit_id: int) -> int | None:
    """The writing session a notes save by the person carries on: its first
    event's id, when the role's latest event is the person's own notes save
    from the page, made within the gap. Their assistant's writes are each an
    entry of their own, and so is anything written between two saves."""
    last = (
        await session.execute(
            select(PursuitEvent.id, PursuitEvent.actor, PursuitEvent.detail, PursuitEvent.created_at >= func.now() - NOTES_SESSION_GAP)
            .where(PursuitEvent.pursuit_id == pursuit_id)
            .order_by(PursuitEvent.created_at.desc(), PursuitEvent.id.desc())
            .limit(1)
        )
    ).first()
    if last is None:
        return None
    event_id, actor, detail, recent = last
    detail = detail or {}
    if actor != "user" or "via" in detail or detail.get("changed") != ["notes"] or not recent:
        return None
    return int(detail.get("session", event_id))


def _stored(values: dict[str, object]) -> dict[str, object]:
    """Field values as the event's JSON column keeps them."""
    return {field: value.isoformat() if isinstance(value, datetime) else value for field, value in values.items()}


async def upsert_pursuit(
    session: AsyncSession,
    job_id: int,
    payload: PursuitUpdate,
    *,
    actor: Literal["user", "agent"],
    expected_revision: int | None = None,
    via: str | None = None,
    notes_was: str | None = None,
    new_notes_session: bool = False,
) -> Pursuit:
    """Create or change the pursuit of one role. Every write that changes the
    row advances its `revision` (the mapper does it on flush); a write that
    changes nothing leaves it.

    `via` names the way an agent's write came in (the agent operations say
    `agent_api`); the event keeps it beside the actor.

    `expected_revision` is the revision the caller read, 0 for a role with no
    pursuit yet. Given, the write is refused with `RevisionConflict` when the
    row has moved since; the check runs under the role's lock, so no write can
    land between it and this one. Omitted, the write is last-writer-wins, as
    the dashboard's is.

    `notes_was` is the notes text the writer started from, "" for none. Given
    with new notes, the write is refused with `NotesMoved` when the stored
    notes differ from it, under the same lock: notes written meanwhile (by an
    agent, or in another window) are never written over unseen.

    `new_notes_session` starts a notes writing session with this write even
    within the gap: an earlier version put back is not more of the typing
    before it, and the notes it replaces must stay a version.
    """
    pursuit, _ = await _write_pursuit(
        session, job_id, payload.model_dump(exclude_unset=True),
        actor=actor, expected_revision=expected_revision, via=via, notes_was=notes_was,
        new_notes_session=new_notes_session,
    )
    return pursuit


class NotesMoved(Exception):
    """The role's notes changed after the text a notes write started from.
    Carries the notes as they are now, for the writer to merge."""

    def __init__(self, current: str | None) -> None:
        super().__init__("the notes changed since they were read")
        self.current = current


#: The pursuit's columns that hold its soonest open step, written from the steps.
STEP_MIRROR = ("next_action", "next_action_due")


async def _write_pursuit(
    session: AsyncSession,
    job_id: int,
    values: dict[str, object],
    *,
    actor: Literal["user", "agent"],
    expected_revision: int | None,
    via: str | None,
    step_write: StepChange | None = None,
    notes_was: str | None = None,
    new_notes_session: bool = False,
) -> tuple[Pursuit, PursuitStep | None]:
    """`upsert_pursuit`, and the one way a step is written: the step change
    runs under the role's lock and revision check, the pursuit's soonest-step
    columns follow it, and the write's one event records both. Answers the
    pursuit and the step the write touched. The overdue reminders are
    reconciled in the write's transaction, so every writer's reminders follow
    its write."""
    job = await session.get(Job, job_id)
    if job is None:
        raise LookupError("opportunity not found")

    # Before the read the event's `from_stage` and the revision check are taken from.
    await lock_role_writes(session, job_id)
    pursuit = await session.scalar(
        select(Pursuit).where(Pursuit.job_id == job_id).execution_options(populate_existing=True)
    )
    if expected_revision is not None:
        current = 0 if pursuit is None else pursuit.revision
        if current != expected_revision:
            raise RevisionConflict(expected=expected_revision, current=current)
    if notes_was is not None and "notes" in values:
        stored = None if pursuit is None else pursuit.notes
        if (stored or "") != notes_was:
            raise NotesMoved(stored)
    created = pursuit is None
    if pursuit is None:
        # The table's defaults, stated, so the fields below compare against
        # them and the row is inserted once with its values, at revision 1.
        pursuit = Pursuit(job_id=job_id, stage="saved", priority=3)
        session.add(pursuit)

    touched: PursuitStep | None = None
    before = pursuit.stage
    changed: dict[str, object] = {}
    replaced: dict[str, object] = {}
    values = dict(values)
    legacy_step = {field: values.pop(field) for field in STEP_MIRROR if field in values}
    # Everything this write changes is decided before anything is flushed, so
    # the pursuit's row is written once and its revision advances once.
    with session.no_autoflush:
        plan = _StepPlan([] if created else await open_steps(session, pursuit.id))
        for field, value in values.items():
            if getattr(pursuit, field) != value:
                replaced[field] = getattr(pursuit, field)
                setattr(pursuit, field, value)
                changed[field] = value
        # A priority is chosen once the log records one. The first choice is
        # recorded even when it equals the default the row was written with, so a
        # chosen Medium reads apart from one never set.
        if "priority" in values and "priority" not in changed and (
            created or not await session.scalar(select(priority_chosen(pursuit.id)))
        ):
            replaced["priority"] = pursuit.priority
            changed["priority"] = pursuit.priority

        if legacy_step:
            _write_first_step(plan, legacy_step)
        if step_write is not None:
            touched = await step_write(session, plan)
        if plan.told is not None:
            first = plan.first()
            soonest = {
                "next_action": first.text if first is not None else None,
                "next_action_due": first.due if first is not None else None,
            }
            for field, value in soonest.items():
                if getattr(pursuit, field) != value:
                    replaced[field] = getattr(pursuit, field)
                    setattr(pursuit, field, value)
                    changed[field] = value
            # A step write is a write to the pursuit, whichever step it touched:
            # its revision advances, so an agent's stale read of the steps is refused.
            pursuit.updated_at = func.now()

        # Pursuing a job implies it is saved.
        await ensure_favorite(session, job_id)
    # The insert, or the one update that advances the revision; new steps need its id.
    await session.flush()
    plan.store(session, pursuit)
    for gone in plan.removed:
        await session.delete(gone)
    if plan.added or plan.removed:
        await session.flush()
    said = plan.said()

    # A save of the notes alone, by the person from the page, that carries on
    # a writing session keeps no copy of the notes: the session's first event
    # keeps what it replaced, and what the session ended with is what the next
    # one replaced, or the notes as they are.
    carries_on = None
    if not created and actor == "user" and via is None and set(changed) == {"notes"} and said is None and not new_notes_session:
        carries_on = await _notes_session(session, pursuit.id)
    before_values, after_values = _stored(replaced), _stored(changed)
    if carries_on is not None:
        before_values.pop("notes")
        after_values.pop("notes")

    if created or changed or said is not None:
        session.add(
            PursuitEvent(
                pursuit_id=pursuit.id,
                actor=actor,
                event_type="created" if created else "updated",
                from_stage=None if created else before,
                to_stage=pursuit.stage,
                # Both versions of every field, so a write never loses what
                # it replaced (an agent's note over the user's own); a save
                # carrying on a notes session keeps neither (above).
                detail={
                    "changed": sorted({*changed, *(["steps"] if said is not None else [])}),
                    "before": before_values,
                    "after": after_values,
                    **({"step": said} if said is not None else {}),
                    **({"via": via} if via is not None else {}),
                    **({"session": carries_on} if carries_on is not None else {}),
                },
            )
        )
    await session.flush()
    await generate_pursuit_due_notifications(session)
    return pursuit, touched


def priority_chosen(pursuit_id: Any) -> Any:
    """True when the person, or an agent for them, has ever chosen the
    pursuit's priority. A new pursuit is written at the column's default, so
    the stored value alone cannot tell a chosen Medium from one never set: the
    change log can, since it records every priority a write chose."""
    return exists().where(
        PursuitEvent.pursuit_id == pursuit_id,
        PursuitEvent.detail["changed"].contains(["priority"]),
    )


#: The priority a pursuit reads as until one is chosen: No priority.
UNCHOSEN_PRIORITY = 1


def priority_rank() -> Any:
    """A pursuit's priority as its place in a list reads it: the stored number
    once one is chosen, No priority until then."""
    return case((priority_chosen(Pursuit.id), Pursuit.priority), else_=literal(UNCHOSEN_PRIORITY))


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

    _no_null = field_validator("label", "scheduled_at", "all_day", mode="before")(refuse_null)

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


# --- next steps ----------------------------------------------------------------

#: What a step write did, as the write's event and the Activity schema name it.
StepAction = Literal["added", "edited", "done", "reopened", "removed"]

#: A step write run inside `_write_pursuit`: it makes its change on the plan and
#: returns the step it touched.
StepChange = Callable[[AsyncSession, "_StepPlan"], Awaitable[PursuitStep]]


class StepNeedsWords(ValueError):
    """A day was given for a next step that has no words."""


def step_words(value: str | None) -> str | None:
    """A next step's words, trimmed; blank is refused. Null passes, for a
    partial write whose own guard decides what an absent or null field means."""
    if value is None:
        return None
    words = value.strip()
    if not words:
        raise ValueError("a next step needs some words")
    return words


class StepWrite(BaseModel):
    text: str = Field(json_schema_extra={"x-text": "content"}, min_length=1, max_length=2_000)
    due: Instant | None = None

    _has_words = field_validator("text")(step_words)


# A partial write, as `PursuitUpdate`: absent is "leave it". `text` and `done`
# always have a value, so an explicit null for them is refused; a null `due`
# takes the step's day off. A write that names none of the three changes nothing.
class StepUpdate(BaseModel):
    text: str | None = Field(json_schema_extra={"x-text": "content"}, default=None, min_length=1, max_length=2_000)
    due: Instant | None = None
    done: bool | None = None

    _no_null = field_validator("text", "done", mode="before")(refuse_null)
    _has_words = field_validator("text")(step_words)

    @model_validator(mode="after")
    def _changes_something(self) -> StepUpdate:
        if not self.model_fields_set & {"text", "due", "done"}:
            raise ValueError("name at least one field to change: text, due, done")
        return self


def soonest_first() -> tuple[Any, ...]:
    """The steps' one order: by day, a step with no day after every dated one,
    then in the order they were added."""
    return (PursuitStep.due.asc().nulls_last(), PursuitStep.id.asc())


async def open_steps(session: AsyncSession, pursuit_id: int) -> list[PursuitStep]:
    return list(
        (
            await session.scalars(
                select(PursuitStep)
                .where(PursuitStep.pursuit_id == pursuit_id, PursuitStep.done_at.is_(None))
                .order_by(*soonest_first())
                .execution_options(populate_existing=True)
            )
        ).all()
    )


def _said(step: PursuitStep, action: StepAction, was: dict[str, object] | None = None) -> dict[str, object]:
    """A step as the write's event keeps it."""
    return {
        "id": step.id,
        "action": action,
        **_stored({"text": step.text, "due": step.due}),
        **({"was": _stored(was)} if was else {}),
    }


@dataclass
class _StepPlan:
    """One write's change to a pursuit's steps, made on the steps in memory:
    the pursuit's soonest step is read from it before anything is stored, and
    a new step is stored once the pursuit has its id."""

    #: The open steps as read, then every step the write touched.
    steps: list[PursuitStep]
    added: list[PursuitStep] = dataclass_field(default_factory=list)
    removed: list[PursuitStep] = dataclass_field(default_factory=list)
    #: The step the write changed, what it did, and what it replaced.
    told: tuple[PursuitStep, StepAction, dict[str, object]] | None = None

    def _touch(self, step: PursuitStep) -> None:
        if not any(one is step for one in self.steps):
            self.steps.append(step)

    def add(self, text: str, due: datetime | None) -> PursuitStep:
        step = PursuitStep(text=text, due=due)
        self.steps.append(step)
        self.added.append(step)
        self.told = (step, "added", {})
        return step

    def remove(self, step: PursuitStep) -> PursuitStep:
        self._touch(step)
        self.removed.append(step)
        self.told = (step, "removed", {})
        return step

    def change(self, step: PursuitStep, values: dict[str, object]) -> PursuitStep:
        """A step's new words, day or done state; nothing is told when nothing changed."""
        self._touch(step)
        was: dict[str, object] = {}
        for name in ("text", "due"):
            if name in values and getattr(step, name) != values[name]:
                was[name] = getattr(step, name)
                setattr(step, name, values[name])
        if "done" in values and values["done"] != (step.done_at is not None):
            step.done_at = datetime.now(UTC) if values["done"] else None
            self.told = (step, "done" if values["done"] else "reopened", was)
        elif was:
            self.told = (step, "edited", was)
        return step

    def first(self) -> PursuitStep | None:
        """The soonest open step, in `soonest_first`'s order; a step not stored
        yet sorts after the stored ones of its day, as its id will."""
        open_ = [
            (index, step) for index, step in enumerate(self.steps)
            if step.done_at is None and not any(step is gone for gone in self.removed)
        ]
        if not open_:
            return None
        return min(
            open_,
            key=lambda pair: (
                pair[1].due is None,
                pair[1].due if pair[1].due is not None else datetime.min.replace(tzinfo=UTC),
                pair[1].id is None,
                pair[1].id or 0,
                pair[0],
            ),
        )[1]

    def store(self, session: AsyncSession, pursuit: Pursuit) -> None:
        """Adds the new steps under the pursuit's id."""
        for step in self.added:
            step.pursuit_id = pursuit.id
            session.add(step)

    def said(self) -> dict[str, object] | None:
        """What the event says of the step the write changed, once it is flushed."""
        if self.told is None:
            return None
        step, action, was = self.told
        return _said(step, action, was)


def _write_first_step(plan: _StepPlan, values: dict[str, object]) -> None:
    """A write of `next_action` or `next_action_due`, the pursuit's one step as
    a client that knows one step names it: it changes the soonest open step,
    adds one when there is none, and clearing the words ticks it done."""
    first = plan.first()
    text = values.get("next_action", first.text if first is not None else None)
    due = values.get("next_action_due", first.due if first is not None else None)
    words = text.strip() if isinstance(text, str) else ""
    if first is None:
        if not words:
            if due is not None:
                raise StepNeedsWords("a next step needs some words before it can have a day")
            return
        plan.add(words, due)  # type: ignore[arg-type]
        return
    plan.change(first, {"done": True} if not words else {"text": words, "due": due})


async def _step_on(session: AsyncSession, job_id: int, step_id: int) -> PursuitStep:
    """The step, if it belongs to this role's pursuit. `LookupError` otherwise,
    so an id from another role is never reached through this one's route."""
    step = await session.scalar(
        select(PursuitStep)
        .join(Pursuit, Pursuit.id == PursuitStep.pursuit_id)
        .where(PursuitStep.id == step_id, Pursuit.job_id == job_id)
        .execution_options(populate_existing=True)
    )
    if step is None:
        raise LookupError("next step not found")
    return step


async def add_step(
    session: AsyncSession,
    job_id: int,
    payload: StepWrite,
    *,
    actor: Literal["user", "agent"],
    expected_revision: int | None = None,
    via: str | None = None,
) -> tuple[Pursuit, PursuitStep]:
    async def add(session: AsyncSession, plan: _StepPlan) -> PursuitStep:
        return plan.add(payload.text, payload.due)

    pursuit, step = await _write_pursuit(
        session, job_id, {}, actor=actor, expected_revision=expected_revision, via=via, step_write=add
    )
    assert step is not None
    return pursuit, step


async def update_step(
    session: AsyncSession,
    job_id: int,
    step_id: int,
    payload: StepUpdate,
    *,
    actor: Literal["user", "agent"],
    expected_revision: int | None = None,
    via: str | None = None,
) -> tuple[Pursuit, PursuitStep]:
    """Change a step's words or day, tick it done or open it again. A step of
    another role, or none, is a `LookupError`."""
    # Before the write starts: a wrong id must not leave a pursuit row pending in the session.
    await _step_on(session, job_id, step_id)

    async def change(session: AsyncSession, plan: _StepPlan) -> PursuitStep:
        return plan.change(await _step_on(session, job_id, step_id), payload.model_dump(exclude_unset=True))

    pursuit, step = await _write_pursuit(
        session, job_id, {}, actor=actor, expected_revision=expected_revision, via=via, step_write=change
    )
    assert step is not None
    return pursuit, step


async def delete_step(
    session: AsyncSession,
    job_id: int,
    step_id: int,
    *,
    actor: Literal["user", "agent"],
    expected_revision: int | None = None,
    via: str | None = None,
) -> Pursuit:
    """Remove a step added by mistake. Ticking one done keeps it; this does not."""
    # Before the write starts: a wrong id must not leave a pursuit row pending in the session.
    await _step_on(session, job_id, step_id)

    async def remove(session: AsyncSession, plan: _StepPlan) -> PursuitStep:
        return plan.remove(await _step_on(session, job_id, step_id))

    pursuit, _ = await _write_pursuit(
        session, job_id, {}, actor=actor, expected_revision=expected_revision, via=via, step_write=remove
    )
    return pursuit


def public_step(step: PursuitStep) -> dict:
    return {
        "id": step.id,
        "text": step.text,
        "due": step.due,
        "created_at": step.created_at,
        "done_at": step.done_at,
    }


async def steps_of(session: AsyncSession, pursuit_ids: list[int]) -> dict[int, list[dict]]:
    """Each pursuit's open steps, soonest first."""
    found: dict[int, list[dict]] = {pid: [] for pid in pursuit_ids}
    if not pursuit_ids:
        return found
    rows = await session.scalars(
        select(PursuitStep)
        .where(PursuitStep.pursuit_id.in_(pursuit_ids), PursuitStep.done_at.is_(None))
        .order_by(*soonest_first())
    )
    for step in rows.all():
        found[step.pursuit_id].append(public_step(step))
    return found


async def done_steps(session: AsyncSession, pursuit_id: int) -> list[dict]:
    """The pursuit's ticked steps, the latest done first."""
    rows = await session.scalars(
        select(PursuitStep)
        .where(PursuitStep.pursuit_id == pursuit_id, PursuitStep.done_at.is_not(None))
        .order_by(PursuitStep.done_at.desc(), PursuitStep.id.desc())
    )
    return [public_step(step) for step in rows.all()]


@dataclass(frozen=True)
class PursuitListKey:
    """A pursuit's place in `list_pursuits`' order, for reading on after it."""

    priority: int
    updated_at: datetime
    id: int


async def list_pursuits(
    session: AsyncSession,
    *,
    stage: PursuitStage | None = None,
    limit: int = 50,
    after: PursuitListKey | None = None,
    with_revision: bool = False,
) -> list[dict]:
    """Pursuits by priority, the most urgent first and the most recently
    changed first within one, then by id, so two rows changed in one
    transaction still have one order and a
    page that ends between them resumes at the second (`after`). A pursuit
    with no priority chosen ranks as No priority, whatever its stored number,
    and `after.priority` is that rank.

    `with_revision` adds each pursuit's `revision`, read with its fields, for a
    caller that passes it back to a write."""
    stmt = select(Pursuit, Job).join(Job, Job.id == Pursuit.job_id)
    if stage is not None:
        stmt = stmt.where(Pursuit.stage == stage)
    rank = priority_rank()
    if after is not None:
        stmt = stmt.where(
            or_(
                rank < after.priority,
                and_(rank == after.priority, Pursuit.updated_at < after.updated_at),
                and_(
                    rank == after.priority,
                    Pursuit.updated_at == after.updated_at,
                    Pursuit.id > after.id,
                ),
            )
        )
    rows = (
        await session.execute(
            stmt.order_by(rank.desc(), Pursuit.updated_at.desc(), Pursuit.id.asc()).limit(limit)
        )
    ).all()
    return [
        {**public_pursuit(pursuit, job), **({"revision": pursuit.revision} if with_revision else {})}
        for pursuit, job in rows
    ]

"""The application pipeline's reads: the board, one application, its activity.

An application is a role the user starred or gave a pursuit, keyed by its job
id. A star with no pursuit row is a card at Considering. A pursuit still at
Considering whose star was taken away is off the board; its notes and comments
stay and come back with the star.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import Select, and_, exists, func, literal, or_, select, union
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from tracker.agents.pursuits import priority_chosen, public_interview, steps_of
from tracker.db.models import (
    ENDED_STAGES,
    OWES_NOTHING,
    Favorite,
    Job,
    Pursuit,
    PursuitComment,
    PursuitEvent,
    PursuitInterview,
    PursuitStep,
)

#: An interview with no outcome stays the next one until this long after it
#: began, so a round that ran this morning still asks how it went.
NEXT_INTERVIEW_GRACE = timedelta(hours=12)

#: An all-day interview is stored at its day's local midnight, so it stays the
#: next one for the whole of that day. A clock change inside the day moves the
#: end by its hour.
ALL_DAY_SPAN = timedelta(days=1)

#: The longest span one calendar read covers: a month grid, six whole weeks
#: from local midnight to local midnight. When a clock goes back inside the
#: grid, those six weeks are an hour longer than 42 days of 24 hours.
CALENDAR_SPAN_MAX = timedelta(days=42, hours=1)

def _next_interview(now: datetime) -> Select[tuple[PursuitInterview]]:
    """Each pursuit's soonest round with no outcome, kept until twelve hours
    after it began (an all-day round: until its day is over)."""
    return (
        select(PursuitInterview)
        .where(
            PursuitInterview.outcome.is_(None),
            or_(
                and_(PursuitInterview.all_day.is_(False), PursuitInterview.scheduled_at >= now - NEXT_INTERVIEW_GRACE),
                and_(PursuitInterview.all_day.is_(True), PursuitInterview.scheduled_at >= now - ALL_DAY_SPAN),
            ),
        )
        .distinct(PursuitInterview.pursuit_id)
        .order_by(PursuitInterview.pursuit_id, PursuitInterview.scheduled_at, PursuitInterview.id)
    )


def _awaiting_outcome(now: datetime) -> Select[tuple[PursuitInterview]]:
    """Each pursuit's latest round that has taken place with no outcome given:
    a timed round once it has begun, an all-day round once its day is over. A
    timed round is also the next one for its first twelve hours, so the two
    can be the same round."""
    return (
        select(PursuitInterview)
        .where(
            PursuitInterview.outcome.is_(None),
            or_(
                and_(PursuitInterview.all_day.is_(False), PursuitInterview.scheduled_at <= now),
                and_(PursuitInterview.all_day.is_(True), PursuitInterview.scheduled_at <= now - ALL_DAY_SPAN),
            ),
        )
        .distinct(PursuitInterview.pursuit_id)
        .order_by(PursuitInterview.pursuit_id, PursuitInterview.scheduled_at.desc(), PursuitInterview.id.desc())
    )


def card_interview(interview: PursuitInterview) -> dict[str, Any]:
    """A round as a card or a pursuit read names it."""
    return {
        "id": interview.id,
        "label": interview.label,
        "scheduled_at": interview.scheduled_at,
        "all_day": interview.all_day,
        "format": interview.format,
        "link": interview.link,
    }


async def pursuit_marks(
    session: AsyncSession, pursuit_ids: list[int], *, now: datetime
) -> dict[int, dict[str, Any]]:
    """What the board reads about each pursuit beyond its row (its open next
    steps, its next round, the round awaiting its outcome, whether its
    priority was ever chosen), for
    a read that is not the board's."""
    marks: dict[int, dict[str, Any]] = {
        pid: {"next_interview": None, "awaiting_outcome": None, "priority_set": False, "steps": []}
        for pid in pursuit_ids
    }
    if not pursuit_ids:
        return marks
    for pid, steps in (await steps_of(session, pursuit_ids)).items():
        marks[pid]["steps"] = steps
    for key, query in (("next_interview", _next_interview(now)), ("awaiting_outcome", _awaiting_outcome(now))):
        for interview in (await session.scalars(query.where(PursuitInterview.pursuit_id.in_(pursuit_ids)))).all():
            marks[interview.pursuit_id][key] = card_interview(interview)
    chosen = await session.scalars(
        select(Pursuit.id).where(Pursuit.id.in_(pursuit_ids), priority_chosen(Pursuit.id))
    )
    for pid in chosen.all():
        marks[pid]["priority_set"] = True
    return marks


def _stage_changes():
    """Events that put a pursuit into a stage: its creation, and every write
    whose stage differs from the one before it."""
    return or_(
        PursuitEvent.event_type == "created",
        PursuitEvent.from_stage.is_distinct_from(PursuitEvent.to_stage),
    )


async def board(session: AsyncSession, *, now: datetime, job_id: int | None = None) -> list[dict]:
    """Every application on the board, or the one for `job_id`."""
    on_board = union(select(Favorite.job_id), select(Pursuit.job_id)).subquery()

    last_change = (
        select(PursuitEvent.pursuit_id, PursuitEvent.created_at)
        .where(_stage_changes())
        .distinct(PursuitEvent.pursuit_id)
        .order_by(PursuitEvent.pursuit_id, PursuitEvent.created_at.desc(), PursuitEvent.id.desc())
        .subquery()
    )
    # The stage an ending was reached from is the last one still moving: a
    # change from one ending to another (Declined, then Accepted) keeps it.
    ended_from = (
        select(PursuitEvent.pursuit_id, PursuitEvent.from_stage)
        .where(
            PursuitEvent.from_stage.not_in(sorted(ENDED_STAGES)),
            PursuitEvent.to_stage.in_(sorted(ENDED_STAGES)),
        )
        .distinct(PursuitEvent.pursuit_id)
        .order_by(PursuitEvent.pursuit_id, PursuitEvent.created_at.desc(), PursuitEvent.id.desc())
        .subquery()
    )
    comments = (
        select(
            PursuitComment.pursuit_id,
            func.count().label("n"),
            func.max(PursuitComment.created_at).label("last_at"),
        )
        .group_by(PursuitComment.pursuit_id)
        .subquery()
    )
    next_interview = aliased(PursuitInterview, _next_interview(now).subquery(), name="next_interview")
    awaiting = aliased(PursuitInterview, _awaiting_outcome(now).subquery(), name="awaiting")
    interview_touched = (
        select(PursuitInterview.pursuit_id, func.max(PursuitInterview.updated_at).label("last_at"))
        .group_by(PursuitInterview.pursuit_id)
        .subquery()
    )

    stmt = (
        select(
            Job,
            Pursuit,
            Favorite.created_at.label("starred_at"),
            ended_from.c.from_stage.label("ended_from"),
            last_change.c.created_at.label("stage_since"),
            func.coalesce(comments.c.n, 0).label("comment_count"),
            comments.c.last_at.label("last_comment_at"),
            interview_touched.c.last_at.label("last_interview_at"),
            next_interview,
            awaiting,
            priority_chosen(Pursuit.id).label("priority_set"),
        )
        .select_from(on_board)
        .join(Job, Job.id == on_board.c.job_id)
        .outerjoin(Pursuit, Pursuit.job_id == Job.id)
        .outerjoin(Favorite, Favorite.job_id == Job.id)
        .outerjoin(last_change, last_change.c.pursuit_id == Pursuit.id)
        .outerjoin(ended_from, ended_from.c.pursuit_id == Pursuit.id)
        .outerjoin(comments, comments.c.pursuit_id == Pursuit.id)
        .outerjoin(next_interview, next_interview.pursuit_id == Pursuit.id)
        .outerjoin(awaiting, awaiting.pursuit_id == Pursuit.id)
        .outerjoin(interview_touched, interview_touched.c.pursuit_id == Pursuit.id)
        .where(or_(Favorite.id.is_not(None), Pursuit.stage != "saved"))
    )
    if job_id is not None:
        stmt = stmt.where(Job.id == job_id)

    rows = (await session.execute(stmt)).all()
    steps = await steps_of(session, [row.Pursuit.id for row in rows if row.Pursuit is not None])
    cards = []
    for row in rows:
        job: Job = row.Job
        pursuit: Pursuit | None = row.Pursuit
        stage = pursuit.stage if pursuit is not None else "saved"
        touched = [
            t for t in (
                row.starred_at,
                pursuit.updated_at if pursuit is not None else None,
                row.last_comment_at,
                row.last_interview_at,
            ) if t is not None
        ]
        cards.append({
            "job_id": job.id,
            "pursuit_id": pursuit.id if pursuit is not None else None,
            "stage": stage,
            "priority": pursuit.priority if pursuit is not None else 3,
            "priority_set": bool(row.priority_set),
            "starred": row.starred_at is not None,
            "company": job.company,
            "title": job.title,
            "level_band": job.level_band,
            "posting_status": job.status,
            "next_action": pursuit.next_action if pursuit is not None else None,
            "next_action_due": pursuit.next_action_due if pursuit is not None else None,
            "steps": steps[pursuit.id] if pursuit is not None else [],
            "next_interview": card_interview(row.next_interview) if row.next_interview is not None else None,
            "awaiting_outcome": card_interview(row.awaiting) if row.awaiting is not None else None,
            "comment_count": row.comment_count,
            "stage_since": row.stage_since or row.starred_at,
            "last_activity_at": max(touched) if touched else None,
            "ended_at_stage": row.ended_from if stage in ENDED_STAGES else None,
        })
    return cards


async def application(session: AsyncSession, job_id: int, *, now: datetime) -> dict | None:
    """One application: its card, every interview, and when it reached each stage.

    `None` when the role is not on the board."""
    cards = await board(session, now=now, job_id=job_id)
    if not cards:
        return None
    card = cards[0]
    interviews: list[dict[str, Any]] = []
    reached: list[dict[str, Any]] = []
    if card["pursuit_id"] is not None:
        rows = await session.scalars(
            select(PursuitInterview)
            .where(PursuitInterview.pursuit_id == card["pursuit_id"])
            .order_by(PursuitInterview.scheduled_at.desc(), PursuitInterview.id.desc())
        )
        interviews = [public_interview(i) for i in rows.all()]
        # The latest time the application entered each stage: a stage it left
        # and came back to shows its return.
        entered = await session.execute(
            select(PursuitEvent.to_stage, func.max(PursuitEvent.created_at))
            .where(PursuitEvent.pursuit_id == card["pursuit_id"], _stage_changes())
            .group_by(PursuitEvent.to_stage)
        )
        reached = [{"stage": stage, "at": at} for stage, at in entered.all()]
    starred_at = await session.scalar(select(Favorite.created_at).where(Favorite.job_id == job_id))
    if starred_at is not None and not any(r["stage"] == "saved" for r in reached):
        reached.append({"stage": "saved", "at": starred_at})
    reached.sort(key=lambda r: r["at"])
    return {"application": card, "interviews": interviews, "stages_reached": reached}


# Ids per hydrating read: asyncpg binds at most 32,767 parameters in one
# statement, and a whole history can hold more entries of one kind.
_HYDRATE_CHUNK = 10_000


async def _rows_by_id[Row: (PursuitEvent, PursuitComment)](
    session: AsyncSession, model: type[Row], ids: list[int]
) -> dict[int, Row]:
    rows: dict[int, Row] = {}
    for start in range(0, len(ids), _HYDRATE_CHUNK):
        chunk = ids[start : start + _HYDRATE_CHUNK]
        rows.update((row.id, row) for row in (await session.scalars(select(model).where(model.id.in_(chunk)))).all())
    return rows


async def activity(
    session: AsyncSession, job_id: int, *, offset: int = 0, limit: int | None = None
) -> list[dict] | None:
    """Comments and events on one application, newest first: the whole
    history unless `limit` asks for a slice. The page shows every entry, so
    any comment can be read, edited and deleted however long the history.

    `None` when the role is not on the board (no star, and no pursuit past
    Considering); an empty list when it has a star and nothing has happened
    yet. A slice pages by position, not by time: rows
    written in one transaction share its `now()`, so a time cursor would skip
    the rest of a tie a page ended inside. The order breaks every tie."""
    on_board = await session.scalar(
        select(
            or_(
                exists().where(Favorite.job_id == job_id),
                exists().where(Pursuit.job_id == job_id, Pursuit.stage != "saved"),
            )
        )
    )
    if not on_board:
        return None
    pursuit_id = await session.scalar(select(Pursuit.id).where(Pursuit.job_id == job_id))
    if pursuit_id is None:
        return []

    events = select(
        literal("event").label("kind"),
        PursuitEvent.id,
        PursuitEvent.created_at,
    ).where(PursuitEvent.pursuit_id == pursuit_id)
    notes = select(
        literal("comment").label("kind"),
        PursuitComment.id,
        PursuitComment.created_at,
    ).where(PursuitComment.pursuit_id == pursuit_id)
    feed = union(events, notes).subquery()
    ordered = (
        select(feed.c.kind, feed.c.id)
        .order_by(feed.c.created_at.desc(), feed.c.kind, feed.c.id.desc())
        .offset(max(0, offset))
    )
    if limit is not None:
        ordered = ordered.limit(max(1, limit))
    page = (await session.execute(ordered)).all()

    event_rows = await _rows_by_id(session, PursuitEvent, [i for kind, i in page if kind == "event"])
    comment_rows = await _rows_by_id(session, PursuitComment, [i for kind, i in page if kind == "comment"])

    items: list[dict] = []
    for kind, i in page:
        if kind == "event":
            e = event_rows[i]
            detail = e.detail or {}
            items.append({
                "kind": "event",
                "id": e.id,
                "created_at": e.created_at,
                "actor": e.actor,
                "source": e.source,
                "event_type": e.event_type,
                "from_stage": e.from_stage,
                "to_stage": e.to_stage,
                "changed": list(detail.get("changed", [])),
                "step": _event_step(detail.get("step")),
            })
        else:
            c = comment_rows[i]
            items.append({
                "kind": "comment",
                "id": c.id,
                "created_at": c.created_at,
                "actor": c.actor,
                "source": c.source,
                "body": c.body,
                "edited_at": c.edited_at,
            })
    return items


def _event_step(step: Any) -> dict | None:
    """The step an event wrote, as History reads it."""
    if not isinstance(step, dict):
        return None
    return {"id": step["id"], "action": step["action"], "text": step["text"], "due": step.get("due")}


def _on_board():
    """A pursuit the board shows: past Considering, or still starred."""
    return or_(
        Pursuit.stage != "saved",
        exists().where(Favorite.job_id == Pursuit.job_id),
    )


async def calendar(session: AsyncSession, *, start: datetime, end: datetime) -> list[dict]:
    """Every interview and dated next step from `start` up to `end`, on an
    application the board shows, soonest first.

    An interview stays on its day whatever its outcome, so a past week reads
    as it ran; a cancelled one is left out. A step is on its day while it is
    open; a ticked one leaves the calendar."""
    interviews = await session.execute(
        select(PursuitInterview, Pursuit.job_id)
        .join(Pursuit, Pursuit.id == PursuitInterview.pursuit_id)
        .where(
            PursuitInterview.scheduled_at >= start,
            PursuitInterview.scheduled_at < end,
            PursuitInterview.outcome.is_distinct_from("cancelled"),
            _on_board(),
        )
    )
    steps = await session.execute(
        select(PursuitStep, Pursuit.job_id)
        .join(Pursuit, Pursuit.id == PursuitStep.pursuit_id)
        .where(
            PursuitStep.done_at.is_(None),
            PursuitStep.due >= start,
            PursuitStep.due < end,
            Pursuit.stage.not_in(sorted(OWES_NOTHING)),
            _on_board(),
        )
    )
    items: list[dict] = [
        {
            "kind": "interview",
            "job_id": job_id,
            "at": interview.scheduled_at,
            "interview_id": interview.id,
            "label": interview.label,
            "all_day": interview.all_day,
            "format": interview.format,
            "link": interview.link,
            "outcome": interview.outcome,
        }
        for interview, job_id in interviews.all()
    ]
    items += [
        {"kind": "step", "job_id": job_id, "step_id": step.id, "at": step.due, "step": step.text}
        for step, job_id in steps.all()
    ]
    items.sort(key=lambda item: (item["at"], item["job_id"], item["kind"], item.get("step_id", 0)))
    return items

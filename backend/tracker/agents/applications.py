"""The application pipeline's reads: the board, one application, its activity.

An application is a role the user starred or gave a pursuit, keyed by its job
id. A star with no pursuit row is a card at Considering. A pursuit still at
Considering whose star was taken away is off the board; its notes and comments
stay and come back with the star.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import exists, func, literal, or_, select, union
from sqlalchemy.ext.asyncio import AsyncSession

from tracker.agents.pursuits import ENDED_STAGES, public_interview
from tracker.db.models import (
    Favorite,
    Job,
    Pursuit,
    PursuitComment,
    PursuitEvent,
    PursuitInterview,
)

#: An interview with no outcome stays the next one until this long after it
#: began, so a round that ran this morning still asks how it went.
NEXT_INTERVIEW_GRACE = timedelta(hours=12)

#: The most activity entries one read returns.
ACTIVITY_LIMIT_MAX = 200


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
        select(PursuitEvent.pursuit_id, PursuitEvent.from_stage, PursuitEvent.created_at)
        .where(_stage_changes())
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
    next_interview = (
        select(PursuitInterview)
        .where(
            PursuitInterview.outcome.is_(None),
            PursuitInterview.scheduled_at >= now - NEXT_INTERVIEW_GRACE,
        )
        .distinct(PursuitInterview.pursuit_id)
        .order_by(PursuitInterview.pursuit_id, PursuitInterview.scheduled_at, PursuitInterview.id)
        .subquery()
    )
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
            last_change.c.from_stage.label("left_stage"),
            last_change.c.created_at.label("stage_since"),
            func.coalesce(comments.c.n, 0).label("comment_count"),
            comments.c.last_at.label("last_comment_at"),
            interview_touched.c.last_at.label("last_interview_at"),
            next_interview.c.id.label("ni_id"),
            next_interview.c.label.label("ni_label"),
            next_interview.c.scheduled_at.label("ni_at"),
            next_interview.c.all_day.label("ni_all_day"),
            next_interview.c.format.label("ni_format"),
        )
        .select_from(on_board)
        .join(Job, Job.id == on_board.c.job_id)
        .outerjoin(Pursuit, Pursuit.job_id == Job.id)
        .outerjoin(Favorite, Favorite.job_id == Job.id)
        .outerjoin(last_change, last_change.c.pursuit_id == Pursuit.id)
        .outerjoin(comments, comments.c.pursuit_id == Pursuit.id)
        .outerjoin(next_interview, next_interview.c.pursuit_id == Pursuit.id)
        .outerjoin(interview_touched, interview_touched.c.pursuit_id == Pursuit.id)
        .where(or_(Favorite.id.is_not(None), Pursuit.stage != "saved"))
    )
    if job_id is not None:
        stmt = stmt.where(Job.id == job_id)

    cards = []
    for row in (await session.execute(stmt)).all():
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
            "starred": row.starred_at is not None,
            "company": job.company,
            "title": job.title,
            "level_band": job.level_band,
            "posting_status": job.status,
            "next_action": pursuit.next_action if pursuit is not None else None,
            "next_action_due": pursuit.next_action_due if pursuit is not None else None,
            "next_interview": (
                {
                    "id": row.ni_id,
                    "label": row.ni_label,
                    "scheduled_at": row.ni_at,
                    "all_day": row.ni_all_day,
                    "format": row.ni_format,
                }
                if row.ni_id is not None
                else None
            ),
            "comment_count": row.comment_count,
            "stage_since": row.stage_since or row.starred_at,
            "last_activity_at": max(touched) if touched else None,
            "ended_at_stage": row.left_stage if stage in ENDED_STAGES else None,
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


async def activity(
    session: AsyncSession, job_id: int, *, offset: int = 0, limit: int = 100
) -> list[dict] | None:
    """Comments and events on one application, newest first.

    `None` when the role has no pursuit and no star; an empty list when it has
    a star and nothing has happened yet. Pages by position, not by time: rows
    written in one transaction share its `now()`, so a time cursor would skip
    the rest of a tie a page ended inside. The order breaks every tie."""
    on_board = await session.scalar(
        select(
            or_(
                exists().where(Favorite.job_id == job_id),
                exists().where(Pursuit.job_id == job_id),
            )
        )
    )
    if not on_board:
        return None
    pursuit_id = await session.scalar(select(Pursuit.id).where(Pursuit.job_id == job_id))
    if pursuit_id is None:
        return []

    limit = max(1, min(limit, ACTIVITY_LIMIT_MAX))
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
    page = (
        await session.execute(
            select(feed.c.kind, feed.c.id)
            .order_by(feed.c.created_at.desc(), feed.c.kind, feed.c.id.desc())
            .offset(max(0, offset))
            .limit(limit)
        )
    ).all()

    event_ids = [i for kind, i in page if kind == "event"]
    comment_ids = [i for kind, i in page if kind == "comment"]
    event_rows = {
        e.id: e
        for e in (await session.scalars(select(PursuitEvent).where(PursuitEvent.id.in_(event_ids)))).all()
    } if event_ids else {}
    comment_rows = {
        c.id: c
        for c in (await session.scalars(select(PursuitComment).where(PursuitComment.id.in_(comment_ids)))).all()
    } if comment_ids else {}

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

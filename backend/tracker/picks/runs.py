"""Runs of the judge: what each was handed, and how it ended.

A run is opened with the postings it may judge, each with the content hash it
had then, and closed by the assistant (`finished`, or `stopped` with a note)
or by the engine (`abandoned`: expired, replaced by another run from the
same assistant, or closed when the routine is paused or removed).

A day's runs of the routine together are handed at most the daily cap; a
trial is counted apart, against its own cap.

Nothing here commits: the caller owns the transaction.
"""

from __future__ import annotations

import secrets
from datetime import UTC, date, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from tracker.db.models import PickDelivery, PickRun
from tracker.picks.health import ABANDONED_AFTER, RunFact
from tracker.picks.lock import lock_picks
from tracker.platform.util import local_day_start_utc
from tracker.settings_store import get_top_picks_settings


class RunError(Exception):
    """A run the engine cannot act on. `code` is `unknown_run` or `run_closed`."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


def new_run_id() -> str:
    return f"run_{secrets.token_hex(6)}"


async def handed_today(session: AsyncSession, now: datetime, *, zone: ZoneInfo) -> int:
    """Routine handoffs on the local day, including conservatively counted queues."""
    local_now = now.astimezone(zone)
    start = local_day_start_utc(local_now, zone)
    end = local_day_start_utc(local_now + timedelta(days=1), zone)
    recorded = await session.scalar(
        select(func.count()).select_from(PickDelivery).join(PickRun).where(
            PickRun.trial.is_(False), PickDelivery.local_day == local_now.date(),
        )
    )
    legacy = await session.scalar(
        select(func.coalesce(func.sum(func.jsonb_array_length(PickRun.queue)), 0)).where(
            PickRun.trial.is_(False), PickRun.tracks_delivery.is_(False),
            PickRun.started_at >= start, PickRun.started_at < end,
        )
    )
    return int(recorded or 0) + int(legacy or 0)


async def _delivered_ids(session: AsyncSession, run: PickRun, job_ids: list[int]) -> set[int]:
    return set((await session.scalars(
        select(PickDelivery.job_id).where(PickDelivery.run_id == run.id, PickDelivery.job_id.in_(job_ids))
    )).all())


async def hand_off(
    session: AsyncSession, run: PickRun, job_ids: list[int], *, room: int, day: date,
) -> set[int]:
    """Admit eligible entries in rank order. The caller holds the picks lock
    from before it reads the available room until it commits the batch."""
    if not run.tracks_delivery or not job_ids:
        return set(job_ids)
    delivered = await _delivered_ids(session, run, job_ids)
    fresh = [job_id for job_id in job_ids if job_id not in delivered]
    if not run.trial:
        fresh = fresh[:room]
    session.add_all([PickDelivery(run_id=run.id, job_id=job_id, local_day=day) for job_id in fresh])
    return delivered.union(fresh)


async def close_abandoned(session: AsyncSession, now: datetime, *, host: str | None = None) -> int:
    """Close as `abandoned` every run left open past the bound, and every
    open run of `host`, which is about to begin another. Returns how many."""
    await lock_picks(session)
    open_runs = (await session.scalars(select(PickRun).where(PickRun.outcome.is_(None)).with_for_update())).all()
    closed = 0
    for run in open_runs:
        if (host is not None and run.host == host) or now - run.started_at > ABANDONED_AFTER:
            run.outcome, run.finished_at = "abandoned", now
            run.note = run.note or "The run was never closed."
            closed += 1
    await session.flush()
    return closed


async def close_open(session: AsyncSession, now: datetime, *, note: str, routine_only: bool = False) -> int:
    """Close open runs as `abandoned`, with `note` saying why."""
    await lock_picks(session)
    query = select(PickRun).where(PickRun.outcome.is_(None))
    if routine_only:
        query = query.where(PickRun.trial.is_(False))
    open_runs = (await session.scalars(query.with_for_update())).all()
    for run in open_runs:
        run.outcome, run.finished_at, run.note = "abandoned", now, run.note or note
    await session.flush()
    return len(open_runs)


async def forget_notes(session: AsyncSession) -> None:
    """Clear what every run's closing note says: a note is the assistant's own
    words and can repeat what it read of the person."""
    await session.execute(update(PickRun).where(PickRun.note.isnot(None)).values(note=None))


async def begin(
    session: AsyncSession,
    *,
    host: str | None,
    model: str | None,
    trial: bool,
    brief_version: int,
    queue: list[tuple[int, str]],
    counts: dict[str, Any],
    now: datetime,
) -> PickRun:
    """Open a run that may judge `queue`: each posting's id and content hash."""
    await lock_picks(session)
    run = PickRun(
        id=new_run_id(), host=host, model=model, trial=trial, brief_version=brief_version, started_at=now,
        queue=[[job_id, content_hash] for job_id, content_hash in queue], counts=counts, tracks_delivery=True,
    )
    session.add(run)
    await session.flush()
    return run


async def open_run(
    session: AsyncSession, run_id: str, now: datetime | None = None, *, for_write: bool = True,
) -> PickRun:
    """A run that can still serve work, locked through the caller's transaction."""
    # A shared row lock lets batch reads run together and orders them against
    # a pause, which closes the run under an exclusive lock.
    run = await session.scalar(
        select(PickRun)
        .where(PickRun.id == run_id)
        .execution_options(populate_existing=True)
        .with_for_update(read=not for_write)
    )
    if run is None:
        raise RunError("unknown_run", "There is no run by that id. Begin a run to get one.")
    outcome = as_fact(run, now or datetime.now(UTC)).outcome
    if outcome is None and not run.trial and (await get_top_picks_settings(session)).state != "on":
        outcome = "abandoned"
    if outcome is not None:
        raise RunError("run_closed", f"This run is closed ({outcome}). Begin a new run.")
    return run


async def finish(
    session: AsyncSession, run_id: str, *, outcome: str, note: str | None, tokens: int | None, now: datetime,
) -> PickRun:
    await lock_picks(session)
    run = await open_run(session, run_id, now)
    run.outcome, run.finished_at, run.note, run.tokens = outcome, now, note, tokens
    await session.flush()
    return run


def queue_of(run: PickRun) -> dict[int, str]:
    """The content hash each posting of the run's queue had when ranked."""
    return {int(job_id): str(content_hash) for job_id, content_hash in run.queue}


async def delivered_queue(session: AsyncSession, run: PickRun, job_ids: list[int]) -> dict[int, str]:
    queued = queue_of(run)
    if not run.tracks_delivery:
        return {job_id: queued[job_id] for job_id in job_ids if job_id in queued}
    return {job_id: queued[job_id] for job_id in await _delivered_ids(session, run, job_ids)}


def as_fact(run: PickRun, now: datetime) -> RunFact:
    """`run` as health reads it: one still open past the bound reads as abandoned
    before any write has closed it."""
    outcome = run.outcome
    if outcome is None and now - run.started_at > ABANDONED_AFTER:
        outcome = "abandoned"
    return RunFact(outcome=outcome, started_at=run.started_at, finished_at=run.finished_at, note=run.note)


async def newest_routine_run(session: AsyncSession) -> PickRun | None:
    return await session.scalar(
        select(PickRun).where(PickRun.trial.is_(False)).order_by(PickRun.started_at.desc(), PickRun.id.desc()).limit(1)
    )


async def newest_closed_routine_run(session: AsyncSession) -> PickRun | None:
    return await session.scalar(
        select(PickRun)
        .where(PickRun.trial.is_(False), PickRun.outcome.isnot(None))
        .order_by(PickRun.finished_at.desc(), PickRun.id.desc())
        .limit(1)
    )


async def last_finished(session: AsyncSession, *, trial: bool = False) -> PickRun | None:
    return await session.scalar(
        select(PickRun)
        .where(PickRun.trial.is_(trial), PickRun.outcome == "finished")
        .order_by(PickRun.finished_at.desc(), PickRun.id.desc())
        .limit(1)
    )

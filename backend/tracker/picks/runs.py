"""Runs of the judge: what each was handed, and how it ended.

A run is opened with the postings it may judge, each with the content hash it
had then, and closed by the assistant (`finished`, or `stopped` with a note)
or by the engine (`abandoned`: left open past `health.ABANDONED_AFTER`, or
still open when the same assistant begins another).

A day's runs of the routine together are handed at most the daily cap; a
trial is counted apart, against its own cap.

Nothing here commits: the caller owns the transaction.
"""

from __future__ import annotations

import secrets
from datetime import datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from tracker.db.models import PickRun
from tracker.picks.health import ABANDONED_AFTER, RunFact
from tracker.picks.lock import lock_picks
from tracker.platform.util import local_day_start_utc


class RunError(Exception):
    """A run the engine cannot act on. `code` is `unknown_run` or `run_closed`."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


def new_run_id() -> str:
    return f"run_{secrets.token_hex(6)}"


async def handed_today(session: AsyncSession, now: datetime) -> int:
    """How many postings today's runs of the routine were handed, by the local day."""
    return int(await session.scalar(
        select(func.coalesce(func.sum(func.jsonb_array_length(PickRun.queue)), 0)).where(
            PickRun.trial.is_(False), PickRun.started_at >= local_day_start_utc(now)
        )
    ) or 0)


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


async def close_open(session: AsyncSession, now: datetime, *, note: str) -> int:
    """Close every open run as `abandoned`, with `note` saying why."""
    await lock_picks(session)
    open_runs = (await session.scalars(select(PickRun).where(PickRun.outcome.is_(None)).with_for_update())).all()
    for run in open_runs:
        run.outcome, run.finished_at, run.note = "abandoned", now, run.note or note
    await session.flush()
    return len(open_runs)


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
        queue=[[job_id, content_hash] for job_id, content_hash in queue], counts=counts,
    )
    session.add(run)
    await session.flush()
    return run


async def open_run(session: AsyncSession, run_id: str) -> PickRun:
    """The run, locked, for a write that needs it open."""
    run = await session.scalar(select(PickRun).where(PickRun.id == run_id).with_for_update())
    if run is None:
        raise RunError("unknown_run", "There is no run by that id. Begin a run to get one.")
    if run.outcome is not None:
        raise RunError("run_closed", f"This run is closed ({run.outcome}). Begin a new run.")
    return run


async def get(session: AsyncSession, run_id: str) -> PickRun | None:
    return await session.get(PickRun, run_id)


async def finish(
    session: AsyncSession, run_id: str, *, outcome: str, note: str | None, tokens: int | None, now: datetime,
) -> PickRun:
    await lock_picks(session)
    run = await open_run(session, run_id)
    run.outcome, run.finished_at, run.note, run.tokens = outcome, now, note, tokens
    await session.flush()
    return run


def queue_of(run: PickRun) -> dict[int, str]:
    """The content hash each posting of the run's queue had when it was handed."""
    return {int(job_id): str(content_hash) for job_id, content_hash in run.queue}


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

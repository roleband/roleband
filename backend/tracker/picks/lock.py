"""The lock every write of the picks tables holds, in a module of its own so
each writer takes it without importing another."""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from tracker.platform.locks import advisory_xact_lock

#: Serializes the brief, the background, runs and verdicts: a write holds it
#: from before its first read until its commit, so a version number, the one
#: active brief and a run's queue are each decided by one writer at a time.
PICKS_LOCK_KEY = 91254


async def lock_picks(session: AsyncSession) -> None:
    await advisory_xact_lock(session, PICKS_LOCK_KEY)

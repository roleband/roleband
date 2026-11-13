"""Async engine + session factory.

The engine is built on first use, not at import. With the embedded server the
URL property *starts Postgres*, so an import-time engine would boot a database
from anything that merely imports this module — `scripts.export_openapi` (whose
whole point is producing the schema without a server, and which `npm run
gen:api` calls), pytest collection, and `--help` on every CLI entrypoint.

`engine` and `async_session_factory` are importable as module attributes via
`__getattr__` (PEP 562), resolved lazily on first access.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Awaitable, Callable, Sequence
from contextlib import asynccontextmanager
from typing import Any

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from tracker.config import get_settings

_engine: AsyncEngine | None = None
_session_factory: async_sessionmaker[AsyncSession] | None = None


def get_engine() -> AsyncEngine:
    """The process-wide engine, created (and DB started) on first call."""
    global _engine
    if _engine is None:
        # The pgvector.sqlalchemy `Vector` column type handles list<->vector
        # binding itself (serializing to the pgvector text form), so no asyncpg
        # codec registration is needed.
        _engine = create_async_engine(
            get_settings().database_url, pool_pre_ping=True, future=True
        )
    return _engine


def get_session_factory() -> async_sessionmaker[AsyncSession]:
    global _session_factory
    if _session_factory is None:
        _session_factory = async_sessionmaker(
            get_engine(), expire_on_commit=False, class_=AsyncSession
        )
    return _session_factory


def __getattr__(name: str) -> Any:
    """Keep `from tracker.db.session import engine` working, but lazily."""
    if name == "engine":
        return get_engine()
    if name == "async_session_factory":
        return get_session_factory()
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


@asynccontextmanager
async def session_scope() -> AsyncIterator[AsyncSession]:
    """Transactional scope: commit on success, rollback on error."""
    async with get_session_factory()() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


def _say(line: str) -> None:
    print(line, flush=True)


@asynccontextmanager
async def _chunk_scope(session: AsyncSession | None) -> AsyncIterator[AsyncSession]:
    """One chunk's transaction: a session of its own, or `session` committed in
    place. A caller that already holds a session must get that one, because its
    session can be on a different database from the process-wide factory's (a
    scratch database, a test's) and its writes belong where its reads came
    from."""
    if session is None:
        async with session_scope() as own:
            yield own
        return
    try:
        yield session
        await session.commit()
    except Exception:
        await session.rollback()
        raise


async def commit_in_batches(
    ids: Sequence[int],
    work: Callable[[AsyncSession, list[int]], Awaitable[int]],
    *,
    size: int,
    label: str,
    report: Callable[[str], None] | None = _say,
    session: AsyncSession | None = None,
) -> int:
    """Run `work` over `ids` in chunks of `size`, each chunk its own transaction.

    The shape every backfill takes: a run that dies keeps every chunk
    before the one it died in, where a single transaction would roll back every
    row. Each report names the last id saved, so a caller whose rerun cannot
    skip finished work by itself resumes after it. Returns the sum of `work`.

    `session`: run and commit each chunk on this session instead of opening one
    per chunk, for a caller inside a pipeline that owns its own session.
    """
    done = 0
    for start in range(0, len(ids), size):
        chunk = list(ids[start:start + size])
        async with _chunk_scope(session) as chunk_session:
            done += await work(chunk_session, chunk)
        if report is not None:
            report(f"saved {start + len(chunk)}/{len(ids)} {label} (through id {chunk[-1]})")
    return done

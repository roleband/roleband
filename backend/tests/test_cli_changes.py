"""`roleband changes list` across an engine restart, against a real engine.

A position is the database's, not the engine process's: a `since` taken
before the engine stops continues after it starts again, with no event read
twice and none skipped, including the ones written while it was down.
"""

from __future__ import annotations

import asyncio

from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from tests import test_cli
from tests.factories import make_job
from tests.test_cli import cli
from tracker.agents.config import AgentAccessConfig, set_agent_access
from tracker.db.models import JobLifecycleEvent

#: The scratch home, the throwaway database and the engine of the client's own tests.
home = test_cli.home
engine_database = test_cli.engine_database
engine = test_cli.engine


def _db(running, work):
    async def go():
        database = create_async_engine(running.database_url)
        try:
            async with AsyncSession(database, expire_on_commit=False) as session:
                result = await work(session)
                await session.commit()
                return result
        finally:
            await database.dispose()

    return asyncio.run(go())


def _posting(running) -> int:
    async def write(session: AsyncSession) -> int:
        await set_agent_access(session, AgentAccessConfig(enabled=True, allow_writes=False))
        job = make_job("restart", company="acme")
        session.add(job)
        await session.flush()
        return job.id

    return _db(running, write)


def _events(running, job_id: int, count: int) -> list[int]:
    """`count` closings, each committed on its own, as the pipeline writes them."""
    written = []
    for _ in range(count):
        async def write(session: AsyncSession) -> int:
            event = JobLifecycleEvent(job_id=job_id, event_type="closed", detail={})
            session.add(event)
            await session.flush()
            return event.id

        written.append(_db(running, write))
    return written


def _read(home, *args: str) -> dict:
    result = cli(home, "changes", "list", *args, "--json")
    assert result.status == 0, result
    return result.envelope["data"]


def _follow(home, since: str) -> tuple[list[str], str]:
    """Every event to the read's frontier, two at a time, as continue_with says."""
    seen: list[str] = []
    while True:
        data = _read(home, "--since", since, "--limit", "2")
        seen += [event["sequence"] for event in data["events"]]
        since = data["next_since"]
        if data["caught_up"]:
            return seen, since


def test_a_since_continues_across_an_engine_restart_with_nothing_lost_or_repeated(home, engine):
    job_id = _posting(engine)
    home.contexts(current="dev", dev={"url": engine.url})
    start = _read(home)
    assert start["events"] == [] and start["caught_up"] is True

    first = _events(engine, job_id, 5)
    page = _read(home, "--since", start["next_since"], "--limit", "2")
    assert [e["sequence"] for e in page["events"]] == [f"job_event:{i}" for i in first[:2]]
    assert page["caught_up"] is False

    engine.stop()
    while_down = _events(engine, job_id, 2)
    engine.start()
    home.contexts(current="dev", dev={"url": engine.url})

    rest, since = _follow(home, page["next_since"])
    later, since = _follow(home, since)
    assert rest + later == [f"job_event:{i}" for i in first[2:] + while_down]
    assert _follow(home, since)[0] == []
    # The same since read again answers the same page: a caller that lost a
    # reply reads it again and dedupes by sequence.
    again = _read(home, "--since", start["next_since"], "--limit", "2")
    assert [e["sequence"] for e in again["events"]] == [e["sequence"] for e in page["events"]]


def test_a_since_the_engine_cannot_continue_exits_two_with_the_lookup(home, engine):
    _posting(engine)
    home.contexts(current="dev", dev={"url": engine.url})
    result = cli(home, "changes", "list", "--since", "not-a-position", "--json")
    assert result.status == 2
    error = result.envelope["error"]
    assert error["code"] == "invalid_input"
    assert error["details"] == {"field": "since", "reason": "malformed"}
    assert error["next_actions"] == [{"operation": "changes.list", "arguments": {}}]

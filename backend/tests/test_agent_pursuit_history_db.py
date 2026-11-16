"""What an agent's pursuit writes leave behind: the favorite, the pursuit and its event log.

The write operations' contracts (keys, receipts, revisions) are held in
`test_agent_writes_db.py`; this file reads the rows back and checks what
each write put in them.
"""

from __future__ import annotations

from typing import Any

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from tracker.agents.config import AgentAccessConfig, set_agent_access
from tracker.agents.operations.workspace import ensure_workspace_id
from tracker.api.agent_operations import IDEMPOTENCY_KEY_HEADER, PREFIX
from tracker.db.models import Favorite, Job, Pursuit, PursuitEvent

pytestmark = [pytest.mark.asyncio, pytest.mark.usefixtures("no_escape")]


@pytest_asyncio.fixture
async def job_id(db_session, scratch_scope) -> int:
    await set_agent_access(db_session, AgentAccessConfig(enabled=True, allow_writes=True))
    await ensure_workspace_id(db_session)
    job = Job(company="acme", req_id="r1", dedupe_key="acme:r1", title="Staff PM",
              url="https://careers.example.test/r1", status="open", level_band="staff")
    db_session.add(job)
    await db_session.commit()
    return job.id


def _key(n: int) -> dict[str, str]:
    return {IDEMPOTENCY_KEY_HEADER: f"idk_{n:032d}"}


async def _save(api_client, job_id: int, body: dict[str, Any] | None = None, *, n: int = 1) -> dict:
    response = await api_client.put(f"{PREFIX}/pursuits/{job_id}", json=body or {}, headers=_key(n))
    return response.json()


async def _patch(api_client, job_id: int, body: dict[str, Any], *, n: int) -> dict:
    response = await api_client.patch(f"{PREFIX}/pursuits/{job_id}", json=body, headers=_key(n))
    return response.json()


async def _rows(db_session, statement) -> list:
    async with async_sessionmaker(db_session.bind, expire_on_commit=False)() as session:
        return list((await session.scalars(statement)).all())


def _events(db_session) -> Any:
    return _rows(db_session, select(PursuitEvent).order_by(PursuitEvent.id))


async def test_saving_under_two_keys_leaves_one_favorite_and_one_pursuit(api_client, db_session, job_id):
    """Each key is its own request, so the second one runs; it finds the role
    already saved and adds nothing."""
    first = await _save(api_client, job_id, n=1)
    second = await _save(api_client, job_id, n=2)

    assert first["ok"] and second["ok"] and second["meta"]["replayed"] is False
    assert first["data"]["opportunity_id"] == second["data"]["opportunity_id"] == job_id
    assert len(await _rows(db_session, select(Favorite.id))) == 1
    assert len(await _rows(db_session, select(Pursuit.id))) == 1
    assert [e.event_type for e in await _events(db_session)] == ["created"]


async def test_a_stage_change_appends_an_event_naming_both_stages(api_client, db_session, job_id):
    await _save(api_client, job_id, n=1)

    patched = await _patch(api_client, job_id, {"if_revision": 1, "stage": "interviewing"}, n=2)

    assert patched["ok"], patched["error"]
    events = await _events(db_session)
    assert [(e.event_type, e.from_stage, e.to_stage, e.actor) for e in events] == [
        ("created", None, "saved", "agent"),
        ("updated", "saved", "interviewing", "agent"),
    ]


async def test_a_change_keeps_the_value_it_replaced_in_the_event_log(api_client, db_session, job_id):
    """The event carries what each changed field was and what it became, so
    both versions of an agent's write survive."""
    await _save(api_client, job_id, n=1)
    first = await _patch(api_client, job_id, {"if_revision": 1, "notes": "Recruiter: Ada, call on Monday."}, n=2)
    await _patch(
        api_client, job_id,
        {"if_revision": first["data"]["revision"], "notes": "Emailed the recruiter.", "priority": 2}, n=3,
    )

    last = (await _events(db_session))[-1]

    assert last.detail["changed"] == ["notes", "priority"]
    assert last.detail["before"] == {"notes": "Recruiter: Ada, call on Monday.", "priority": 3}
    assert last.detail["after"] == {"notes": "Emailed the recruiter.", "priority": 2}


async def test_writing_against_an_unknown_opportunity_changes_nothing(api_client, db_session, job_id):
    refused = await _save(api_client, 999_999)

    assert refused["ok"] is False and refused["error"]["code"] == "not_found"
    assert await _rows(db_session, select(Pursuit.id)) == []
    assert await _rows(db_session, select(Favorite.id)) == []
    assert await _rows(db_session, select(PursuitEvent.id)) == []
    # The role that does exist still saves under the same key.
    assert (await _save(api_client, job_id))["ok"] is True


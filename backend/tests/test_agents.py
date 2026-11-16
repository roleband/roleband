"""Agent access settings and the pursuit writer.

The two access switches round-trip through the settings store, and the connect
commands Settings shows are the ones `roleband connect` accepts, with no
credential in them. The pursuit writer
serializes per role and appends an auditable event for an agent write.
"""

from __future__ import annotations

import asyncio
import shlex
from datetime import UTC, datetime

import pytest

from tracker.agents.config import (
    AGENT_ACCESS_KEY,
    AgentAccessConfig,
    get_agent_access,
    set_agent_access,
)
from tracker.agents.pursuits import ROLE_WRITE_LOCK_NAMESPACE, PursuitUpdate, upsert_pursuit
from tracker.api.routers.intelligence import _agent_connection_state
from tracker.cli import connect
from tracker.db.models import AppSetting, Favorite, Job, Pursuit, PursuitEvent

# Every test here reaches code that starts or signals a process on this
# machine, so none of them may.
pytestmark = pytest.mark.usefixtures("no_escape")


class ConfigSession:
    def __init__(self, row=None):
        self.row = row
        self.executed = []

    async def get(self, model, key):
        assert model is AppSetting and key == AGENT_ACCESS_KEY
        return self.row

    async def execute(self, stmt):
        self.executed.append(stmt)

    async def scalar(self, stmt):
        self.executed.append(stmt)
        return self.row.value if self.row is not None else None


def test_agent_access_defaults_off_and_round_trips_both_gates():
    assert asyncio.run(get_agent_access(ConfigSession())) == AgentAccessConfig(
        enabled=False, allow_writes=False
    )
    damaged = ConfigSession(AppSetting(key=AGENT_ACCESS_KEY, value={"enabled": "yes"}))
    assert asyncio.run(get_agent_access(damaged)) == AgentAccessConfig()

    session = ConfigSession()
    saved = asyncio.run(set_agent_access(session, AgentAccessConfig(enabled=True, allow_writes=True)))
    assert saved.allow_writes is True
    # A save of the switches alone keeps the stored category choices, none here.
    assert session.executed[-1].compile().params["value"] == {
        "enabled": True,
        "allow_writes": True,
        "categories": {},
    }


def test_settings_offers_the_connect_command_for_exactly_the_hosts_connect_sets_up():
    """The card's commands are what `roleband connect` accepts: a host the
    command does not set up would hand the person a command that refuses, and a
    host it sets up without a tile would be unreachable from Settings."""
    state = _agent_connection_state(AgentAccessConfig(enabled=True, allow_writes=False))

    assert (state["enabled"], state["allow_writes"]) == (True, False)
    assert [item["host"] for item in state["connect"]] == list(connect.HOSTS)
    for item in state["connect"]:
        assert shlex.split(item["command"]) == ["roleband", "connect", item["host"], "--apply"]
    # The control: a host `connect` refuses as unmeasured is never offered.
    assert connect.UNTESTED and not set(connect.UNTESTED) & {item["host"] for item in state["connect"]}
    assert set(state) == {"enabled", "allow_writes", "connect"}
    assert "api_key" not in str(state).lower() and "token" not in str(state).lower()


class PursuitSession:
    def __init__(self, job: Job):
        self.job = job
        self.pursuit = None
        self.favorite = None
        self.added = []
        self.locks = []

    async def execute(self, stmt, params=None):
        # The only statement the writer runs through `execute`: its lock.
        assert "pg_advisory_xact_lock" in str(stmt)
        self.locks.append(params)

    async def get(self, model, key):
        assert model is Job and key == self.job.id
        return self.job

    async def scalar(self, stmt):
        entity = stmt.column_descriptions[0].get("entity")
        if entity is Pursuit:
            return self.pursuit
        if entity is Favorite:
            return self.favorite
        raise AssertionError(f"unexpected scalar entity {entity}")

    def add(self, value):
        self.added.append(value)
        if isinstance(value, Pursuit):
            value.id = 7
            value.created_at = value.updated_at = datetime.now(UTC)
            self.pursuit = value
        elif isinstance(value, Favorite):
            self.favorite = value

    async def flush(self):
        pass


def test_agent_pursuit_write_saves_job_and_appends_auditable_event():
    job = Job(
        id=101, company="openai", req_id="r1", dedupe_key="openai:r1", title="Staff PM",
        url="https://example.test/job", locations=["SF"], location_groups=["silicon_valley"],
        level_band="staff", track="product_program", status="open", in_scope=True,
        first_seen=datetime.now(UTC), last_seen=datetime.now(UTC),
    )
    session = PursuitSession(job)

    pursuit = asyncio.run(
        upsert_pursuit(
            session,
            101,
            PursuitUpdate(stage="applied", priority=1, next_action="Email recruiter"),
            actor="agent",
        )
    )

    assert pursuit.stage == "applied" and pursuit.priority == 1
    assert session.favorite.job_id == 101
    # Serialized per job across clients.
    assert {"ns": ROLE_WRITE_LOCK_NAMESPACE, "k": 101} in session.locks
    event = next(value for value in session.added if isinstance(value, PursuitEvent))
    assert event.actor == "agent" and event.event_type == "created"
    assert event.to_stage == "applied"
    assert event.detail["changed"] == ["next_action", "priority", "stage"]

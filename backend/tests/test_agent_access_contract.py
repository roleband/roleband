"""The agent access settings answer, store and enforce one state.

Settings reads the action groups from `GET /api/intelligence/agents`; the
engine admits a write by `policy.admit` over the stored row. For every
combination of the two switches and an empty or partial `groups` map, the
answer to the save, a fresh read and the engine's admission of a real write
request must agree: a group reads "on" exactly when a write of that group gets
past the switches.

While writes are off a connected row reads every group "off" without storing
it; switching writes back on shows the groups the save stored.
"""

from __future__ import annotations

import itertools
from typing import get_args

import pytest
import pytest_asyncio
from sqlalchemy import select

from scripts.seed_synthetic import seed, task_req_id
from tracker.agents.config import AgentAccessConfig, get_agent_access, set_agent_access
from tracker.agents.operations import policy
from tracker.agents.operations.catalog import REGISTERED
from tracker.agents.operations.descriptor import ActionGroup
from tracker.agents.operations.workspace import ensure_workspace_id
from tracker.api.agent_operations import IDEMPOTENCY_KEY_HEADER, AgentRoute
from tracker.db.models import Job

pytestmark = [pytest.mark.asyncio, pytest.mark.usefixtures("no_escape")]

URL = "/api/intelligence/agents"
KEY = "idk_" + "d" * 32
GROUPS: tuple[ActionGroup, ...] = get_args(ActionGroup)
SWITCHES = list(itertools.product([True, False], repeat=2))
#: An empty map, and one that names a single group.
MAPS = [{}, {"tuning_radar": "off"}]
#: Stored before each save, so an answer cannot pass by echoing an empty row.
STORED = {"controlling_collection": "off", "tracking_progress": "off"}
UNKNOWN = {"probe_unknown_field": 1}
WRITES = [d for d in REGISTERED if d.access == "write" and d.action_group is not None]


@pytest_asyncio.fixture
async def workspace(db_session, scratch_scope):
    await seed(db_session, 8, seed_value=1, derived=False, agent_tasks=True)
    await set_agent_access(db_session, AgentAccessConfig(enabled=True, allow_writes=True, groups=STORED))
    await ensure_workspace_id(db_session)
    await db_session.commit()
    return db_session


def _shown(body: dict) -> tuple:
    return body["enabled"], body["allow_writes"], body["groups"]


async def _write_paths(session) -> dict[str, tuple[str, str]]:
    from tracker.api.app import app

    job = await session.scalar(select(Job.id).where(Job.req_id == task_req_id("INTERVIEW")))
    routes = {r.openapi_extra["x-operation"]: r for r in app.routes if isinstance(r, AgentRoute)}
    paths = {}
    for descriptor in WRITES:
        route = routes[descriptor.id]
        (method,) = route.methods
        paths[descriptor.id] = (method, route.path.replace("{opportunity_id}", str(job)).replace("{company}", "acme"))
    return paths


async def _admitted(api_client, method: str, path: str) -> bool:
    """Whether the engine lets this write past the switches. The switches are
    read before the input, and the body names a field no write accepts, so an
    admitted write stops at its input and changes nothing."""
    response = await api_client.request(method, path, json=UNKNOWN, headers={IDEMPOTENCY_KEY_HEADER: KEY})
    code = response.json()["error"]["code"]
    if code in {"access_disabled", "writes_disabled"}:
        assert response.status_code == 403, response.text
        return False
    assert (response.status_code, code) == (422, "invalid_input"), response.text
    return True


async def _agree(api_client, session, answer: dict) -> None:
    """The answer, a fresh read and the engine's admission agree."""
    assert _shown((await api_client.get(URL)).json()) == _shown(answer)
    session.expire_all()
    stored = await get_agent_access(session)
    for group in GROUPS:
        shows_on = answer["enabled"] and answer["groups"][group] == "on"
        assert policy.acts(stored, group) == shows_on, group
    paths = await _write_paths(session)
    for descriptor in WRITES:
        method, path = paths[descriptor.id]
        shows_on = answer["enabled"] and answer["groups"][descriptor.action_group] == "on"
        assert await _admitted(api_client, method, path) == shows_on, descriptor.id


@pytest.mark.parametrize("groups", MAPS, ids=["empty", "partial"])
@pytest.mark.parametrize(("enabled", "allow_writes"), SWITCHES, ids=lambda v: "on" if v else "off")
async def test_a_put_answers_reads_and_enforces_the_same_groups(api_client, workspace, enabled, allow_writes, groups):
    response = await api_client.put(URL, json={"enabled": enabled, "allow_writes": allow_writes, "groups": groups})

    assert response.status_code == 200, response.text
    answer = response.json()
    assert (answer["enabled"], answer["allow_writes"]) == (enabled, allow_writes)
    read_only = enabled and not allow_writes
    assert answer["groups"] == {g: "off" if read_only else groups.get(g, "on") for g in GROUPS}
    await _agree(api_client, workspace, answer)

    # The map replaces the stored one, also while it reads all off: allowing
    # writes shows what this save stored, not the groups stored before it.
    response = await api_client.put(URL, json={"enabled": True, "allow_writes": True})
    assert response.json()["groups"] == {g: groups.get(g, "on") for g in GROUPS}
    await _agree(api_client, workspace, response.json())


@pytest.mark.parametrize(
    "groups", [{}, {"tuning_radar": "off"}, {"tuning_radar": "on"}], ids=["empty", "partial-off", "partial-on"],
)
@pytest.mark.parametrize(("enabled", "allow_writes"), SWITCHES, ids=lambda v: "on" if v else "off")
async def test_a_patch_answers_reads_and_enforces_the_same_groups(
    api_client, workspace, enabled, allow_writes, groups
):
    await api_client.put(URL, json={"enabled": enabled, "allow_writes": allow_writes})
    before = (await api_client.get(URL)).json()

    response = await api_client.patch(URL, json={"groups": groups})

    assert response.status_code == 200, response.text
    answer = response.json()
    if not groups:
        assert _shown(answer) == _shown(before)
    # Turning a group on from a read-only connection grants that group alone;
    # any other PATCH keeps both switches and every group it does not name.
    grant = enabled and not allow_writes and "on" in groups.values()
    base = dict.fromkeys(GROUPS, "off") if grant else {g: STORED.get(g, "on") for g in GROUPS}
    stored = {**base, **groups}
    writes = allow_writes or grant
    assert (answer["enabled"], answer["allow_writes"]) == (enabled, writes)
    read_only = enabled and not writes
    assert answer["groups"] == (dict.fromkeys(GROUPS, "off") if read_only else stored)
    # Stored as the map says, also while the answer cannot show it.
    workspace.expire_all()
    assert {g: (await get_agent_access(workspace)).groups.get(g, "on") for g in GROUPS} == stored
    await _agree(api_client, workspace, answer)

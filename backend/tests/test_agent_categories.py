"""The person's choice per data category, as every agent operation applies it.

A category switched off is absent, not masked: an operation whose primary
category is off is refused with `category_disabled`, and one that only
carries part of a category answers without that part's keys. Each case here also
reads the same call with the category shared, so a test cannot pass because
the part was never there.

The workspace is `scripts.seed_synthetic`'s, with its agent-task pursuits.
"""

from __future__ import annotations

import asyncio
import dataclasses
import io
import json

import pytest
import pytest_asyncio
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import async_sessionmaker

import tracker.agents.config as config_module
from scripts.seed_synthetic import seed, task_req_id
from tests.barriers import until_waiting
from tracker.agents.config import (
    AGENT_ACCESS_KEY,
    AgentAccessConfig,
    get_agent_access,
    set_agent_access,
)
from tracker.agents.operations import meta
from tracker.agents.operations.catalog import REGISTERED
from tracker.agents.operations.descriptor import OperationDescriptor
from tracker.agents.operations.opportunities import OpportunitySummary
from tracker.agents.operations.outcomes import outcome
from tracker.agents.operations.pursuits import PursuitItem
from tracker.agents.operations.radar import RadarSummary
from tracker.agents.operations.workspace import ensure_workspace_id
from tracker.api.agent_operations import IDEMPOTENCY_KEY_HEADER, PREFIX
from tracker.cli.render import write_human
from tracker.config import get_settings
from tracker.db.models import AppSetting, Favorite, Job, Pursuit, TrackedCompany
from tracker.db.queries.jobs import unplaced_level_expr
from tracker.settings_store import set_intent_embedding

pytestmark = [pytest.mark.asyncio, pytest.mark.usefixtures("no_escape")]

#: The interview pursuit's notes in the seeded workspace.
NOTES = "Onsite loop booked"
KEY = "idk_" + "c" * 32


@pytest_asyncio.fixture
async def workspace(db_session, scratch_scope):
    await seed(db_session, 8, seed_value=1, derived=False, agent_tasks=True)
    await set_agent_access(db_session, AgentAccessConfig(enabled=True, allow_writes=True))
    await ensure_workspace_id(db_session)
    await db_session.commit()
    return db_session


async def _choose(session, **categories: str) -> None:
    """Store these category choices beside both switches on."""
    await set_agent_access(session, AgentAccessConfig(enabled=True, allow_writes=True, categories=categories))
    await session.commit()


async def _job(session, key: str) -> int:
    return await session.scalar(select(Job.id).where(Job.req_id == task_req_id(key)))


async def _get(api_client, path: str, **params):
    response = await api_client.get(f"{PREFIX}{path}", params=params)
    return response, response.json()


def _data(response, body: dict) -> dict:
    assert response.status_code == 200 and body["ok"] is True, body
    return body["data"]


def _disabled(response, body: dict, category: str) -> dict:
    assert body["ok"] is False and body["data"] is None, body
    assert body["error"]["code"] == "category_disabled"
    assert response.status_code == 403 and outcome("category_disabled").exit_status == 4
    assert body["error"]["details"]["category"] == category
    assert body["error"]["details"]["setting"] == f"agent_access.categories.{category}"
    return body["error"]


# --------------------------------------------------------------------------- #
# The stored choices
# --------------------------------------------------------------------------- #


async def test_a_row_without_choices_shares_every_category(db_session, scratch_scope):
    db_session.add(AppSetting(key=AGENT_ACCESS_KEY, value={"enabled": True, "allow_writes": False}))
    await db_session.commit()
    assert (await get_agent_access(db_session)).categories == {}


@pytest.mark.parametrize("categories", [{"offer": "everyone"}, {"diary": "any_model"}, ["offer"]])
async def test_a_choice_the_engine_cannot_read_turns_everything_off(api_client, workspace, categories):
    await workspace.execute(
        update(AppSetting).where(AppSetting.key == AGENT_ACCESS_KEY).values(
            value={"enabled": True, "allow_writes": True, "categories": categories}
        )
    )
    await workspace.commit()

    assert (await get_agent_access(workspace)).enabled is False
    response, body = await _get(api_client, "/opportunities")
    assert body["error"]["code"] == "access_disabled" and response.status_code == 403


async def test_the_settings_switches_keep_the_stored_choices(api_client, workspace):
    await _choose(workspace, private_pursuit="not_shared")

    response = await api_client.put("/api/intelligence/agents", json={"enabled": True, "allow_writes": False})

    assert response.status_code == 200
    assert "categories" not in response.json()
    stored = await get_agent_access(workspace)
    assert (stored.enabled, stored.allow_writes, stored.categories) == (True, False, {"private_pursuit": "not_shared"})


async def test_a_switch_save_cannot_put_back_choices_saved_while_it_ran(db_session, scratch_scope, monkeypatch):
    """The race a read-then-write invites: a categories save runs between the
    switch save's read of the stored choices and its write."""
    await set_agent_access(db_session, AgentAccessConfig(enabled=True))
    await db_session.commit()
    sessions = async_sessionmaker(db_session.bind, expire_on_commit=False)
    read = config_module._locked_categories
    other: list[asyncio.Task] = []

    async def withhold() -> None:
        async with sessions() as session:
            await set_agent_access(session, AgentAccessConfig(enabled=True, categories={"offer": "not_shared"}))
            await session.commit()

    async def read_then_let_the_other_run(session):
        categories = await read(session)
        other.append(asyncio.create_task(withhold()))
        await until_waiting(db_session.bind, other[0])
        return categories

    monkeypatch.setattr(config_module, "_locked_categories", read_then_let_the_other_run)
    async with sessions() as switches:
        await set_agent_access(switches, AgentAccessConfig(enabled=True, allow_writes=True))
        # The other save waits on this one's lock instead of committing under it.
        assert not other[0].done()
        await switches.commit()
    await other[0]

    async with sessions() as session:
        # The categories save ran last, after the switch save let go.
        assert (await get_agent_access(session)).categories == {"offer": "not_shared"}


async def test_enabled_off_refuses_everything_whatever_the_categories_say(api_client, workspace):
    await set_agent_access(workspace, AgentAccessConfig(enabled=False, categories={"public_posting": "any_model"}))
    await workspace.commit()

    response, body = await _get(api_client, "/opportunities")

    assert body["error"]["code"] == "access_disabled"


# --------------------------------------------------------------------------- #
# The primary category refuses the operation
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("choice", ["not_shared", "local_only"])
async def test_pursuits_off_refuses_the_pursuit_reads_with_nothing_of_them(api_client, workspace, choice):
    job_id = await _job(workspace, "INTERVIEW")
    assert NOTES in json.dumps(_data(*await _get(api_client, f"/pursuits/{job_id}")))
    await _choose(workspace, private_pursuit=choice)

    for path in ("/pursuits", f"/pursuits/{job_id}"):
        response, body = await _get(api_client, path)
        _disabled(response, body, "private_pursuit")
        assert NOTES not in response.text


async def test_capabilities_names_the_category_that_closes_an_operation(api_client, workspace):
    await _choose(workspace, private_pursuit="not_shared")

    operations = {
        entry["operation"]: entry["availability"]
        for entry in _data(*await _get(api_client, "/capabilities"))["operations"]
    }

    for closed in ("pursuits.list", "pursuits.get", "pursuits.save", "pursuits.patch"):
        assert operations[closed] == {"state": "unavailable", "reason": "category_disabled"}
    # Pursuits are a secondary category of these: they stay open.
    for open_ in ("opportunities.get", "opportunities.search", "radar.summary", "receipts.get"):
        assert operations[open_] == {"state": "available", "reason": None}


async def test_postings_off_refuses_the_posting_reads(api_client, workspace):
    job_id = await _job(workspace, "INTERVIEW")
    await _choose(workspace, public_posting="not_shared")

    for path in (f"/opportunities/{job_id}", f"/opportunities/{job_id}/history", "/opportunities", "/vocabulary"):
        response, body = await _get(api_client, path)
        _disabled(response, body, "public_posting")


# --------------------------------------------------------------------------- #
# A secondary category is left out
# --------------------------------------------------------------------------- #


async def test_opportunities_get_keeps_the_posting_without_the_pursuit(api_client, workspace):
    job_id = await _job(workspace, "INTERVIEW")
    shared = _data(*await _get(api_client, f"/opportunities/{job_id}", view="detail", tier="full"))
    assert shared["pursuit"]["stage"] == "interviewing" and shared["saved"] is not None
    await _choose(workspace, private_pursuit="not_shared")

    response, body = await _get(api_client, f"/opportunities/{job_id}", view="detail", tier="full")

    data = _data(response, body)
    assert "pursuit" not in data and "saved" not in data
    assert NOTES not in response.text
    assert body["meta"]["data_classes"] == ["public_posting", "market_statistic"]
    assert data == {k: v for k, v in shared.items() if k not in {"pursuit", "saved"}}


async def test_a_pursued_posting_at_a_hidden_company_is_not_found_without_pursuits(api_client, workspace):
    job_id = await _job(workspace, "INTERVIEW")
    company = (await workspace.get(Job, job_id)).company
    await workspace.execute(update(TrackedCompany).where(TrackedCompany.slug == company).values(visible=False))
    await workspace.commit()
    # Shared, the person's pursuit keeps it reachable.
    assert _data(*await _get(api_client, f"/opportunities/{job_id}"))["id"] == job_id
    await _choose(workspace, private_pursuit="not_shared")

    for path in (f"/opportunities/{job_id}", f"/opportunities/{job_id}/history"):
        response, body = await _get(api_client, path)
        assert body["error"]["code"] == "not_found"
        assert body["error"]["details"] == {"opportunity_id": job_id}


async def test_market_statistics_off_leaves_the_estimates_out(api_client, workspace):
    job_id = await _job(workspace, "INTERVIEW")
    shared = _data(*await _get(api_client, f"/opportunities/{job_id}", view="evidence"))
    assert shared["estimated_total_comp"] is not None and shared["evidence"]["estimate_sources"]
    await _choose(workspace, market_statistic="not_shared")

    data = _data(*await _get(api_client, f"/opportunities/{job_id}", view="evidence"))

    assert not {"estimate_component", "estimated_total_comp", "estimated_base"} & data.keys()
    assert data["evidence"] == {"dates": shared["evidence"]["dates"]}
    # The posting's own pay is a posting fact, not a statistic.
    assert data["employer_stated_pay"] == shared["employer_stated_pay"]


async def _rows(api_client, **params) -> tuple[list[str], list[list]]:
    page = _data(*await _get(api_client, "/opportunities", tier="full", limit=100, **params))
    return page["columns"], page["rows"]


async def test_search_answers_without_the_pursuit_or_estimate_columns(api_client, workspace):
    columns, rows = await _rows(api_client)
    pursuit, estimate = columns.index("pursuit"), columns.index("estimated_pay")
    assert any(row[pursuit] for row in rows) and any(row[estimate] for row in rows)
    await _choose(workspace, private_pursuit="not_shared", market_statistic="not_shared")

    left, closed = await _rows(api_client)

    assert left == [c for c in columns if c not in {"pursuit", "estimated_pay"}]
    kept = [columns.index(c) for c in left]
    assert closed == [[row[i] for i in kept] for row in rows]


async def test_queryless_best_match_leaves_the_profile_statement_out_without_the_candidate_category(
    api_client, workspace
):
    """The statement in the candidate profile steers the queryless order only
    while that category is shared; the saved and pursued roles keep steering it."""
    dim = get_settings().embedding_dim
    taste, aim = [0.0] * dim, [0.0] * dim
    taste[1], aim[0] = 1.0, 1.0
    pulled = set((await workspace.scalars(select(Favorite.job_id).union(select(Pursuit.job_id)))).all())
    columns, rows = await _rows(api_client, sort="best_match")
    placed = set((await workspace.scalars(select(Job.id).where(~unplaced_level_expr(Job)))).all())
    # A placed role, since those lead whatever the intent, that the default order puts last of them.
    target = next(row[columns.index("id")] for row in reversed(rows) if row[columns.index("id")] in placed - pulled)
    await workspace.execute(update(Job).values(embedding=taste))
    # Mostly the statement's direction, a little of the taste's.
    await workspace.execute(update(Job).where(Job.id == target).values(embedding=[*[1.0, 0.1], *[0.0] * (dim - 2)]))
    await workspace.commit()

    async def order() -> list:
        columns, rows = await _rows(api_client, sort="best_match")
        return [row[columns.index("id")] for row in rows]

    without_statement = await order()
    await set_intent_embedding(workspace, "Lead product for developer tools", aim)
    await workspace.commit()
    with_statement = await order()
    await _choose(workspace, candidate="not_shared")
    withheld = await order()

    assert with_statement[0] == target and without_statement[0] != target
    assert withheld == without_statement


@pytest.mark.parametrize(
    ("category", "params", "field"),
    [
        ("private_pursuit", {"saved_only": "true"}, "saved_only"),
        ("market_statistic", {"minimum_estimated_pay": "100000"}, "minimum_estimated_pay"),
        ("market_statistic", {"sort": "estimated_pay"}, "sort"),
    ],
)
async def test_search_refuses_to_select_by_a_category_that_is_off(api_client, workspace, category, params, field):
    _data(*await _get(api_client, "/opportunities", **params))
    await _choose(workspace, **{category: "not_shared"})

    response, body = await _get(api_client, "/opportunities", **params)

    assert _disabled(response, body, category)["details"]["field"] == field


async def test_radar_summary_counts_only_the_open_roles_without_pursuits(api_client, workspace):
    shared = _data(*await _get(api_client, "/radar/summary"))
    assert shared["active_pursuits"] == 4
    await _choose(workspace, private_pursuit="not_shared")

    response, body = await _get(api_client, "/radar/summary")

    assert _data(response, body) == {"open_opportunities": shared["open_opportunities"]}
    assert body["meta"]["data_classes"] == ["market_statistic"]


async def test_pursuits_answer_without_their_posting_when_postings_are_off(api_client, workspace):
    job_id = await _job(workspace, "INTERVIEW")
    assert _data(*await _get(api_client, f"/pursuits/{job_id}"))["opportunity"]["title"]
    await _choose(workspace, public_posting="not_shared")

    one = _data(*await _get(api_client, f"/pursuits/{job_id}"))
    listed = _data(*await _get(api_client, "/pursuits"))["items"]

    assert "opportunity" not in one and one["stage"] == "interviewing"
    assert listed and all("opportunity" not in item for item in listed)


async def test_a_pursuit_write_and_its_replay_answer_without_the_posting(api_client, workspace):
    job_id = await _job(workspace, "INTERVIEW")
    revision = _data(*await _get(api_client, f"/pursuits/{job_id}"))["revision"]
    await _choose(workspace, public_posting="not_shared")

    async def patch():
        response = await api_client.patch(
            f"{PREFIX}/pursuits/{job_id}", json={"if_revision": revision, "priority": 2},
            headers={IDEMPOTENCY_KEY_HEADER: KEY},
        )
        return response, response.json()

    fresh, replayed = _data(*await patch()), await patch()
    assert replayed[1]["meta"]["replayed"] is True
    assert "opportunity" not in fresh and "opportunity" not in _data(*replayed)
    await _choose(workspace)
    # The receipt keeps the whole answer for when postings are shared again.
    receipt = _data(*await _get(api_client, "/receipts", operation="pursuits.patch", key=KEY))
    assert receipt["result"]["opportunity"]["title"]


async def test_a_receipt_of_a_pursuit_write_is_refused_while_pursuits_are_off(api_client, workspace):
    job_id = await _job(workspace, "RESEARCH")
    revision = _data(*await _get(api_client, f"/pursuits/{job_id}"))["revision"]
    response = await api_client.patch(
        f"{PREFIX}/pursuits/{job_id}", json={"if_revision": revision, "notes": "Private aside"},
        headers={IDEMPOTENCY_KEY_HEADER: KEY},
    )
    assert response.status_code == 200, response.text
    await _choose(workspace, private_pursuit="not_shared")

    response, body = await _get(api_client, "/receipts", operation="pursuits.patch", key=KEY)

    _disabled(response, body, "private_pursuit")
    assert "Private aside" not in response.text


# --------------------------------------------------------------------------- #
# Every operation declares what it reads
# --------------------------------------------------------------------------- #

HANDSHAKE = frozenset(descriptor.id for descriptor in meta.OPERATIONS)


def undeclared(descriptors: tuple[OperationDescriptor, ...]) -> list[str]:
    """Operations, other than the handshake, that declare no data category."""
    return [d.id for d in descriptors if not d.data_classes and d.id not in HANDSHAKE]


async def test_every_registered_operation_declares_the_categories_it_reads():
    assert undeclared(REGISTERED) == []


async def test_an_operation_that_declares_no_category_fails_the_check():
    bare = dataclasses.replace(REGISTERED[-1], id="widgets.list", data_classes=())
    assert undeclared((*REGISTERED, bare)) == ["widgets.list"]


async def test_a_part_a_category_can_leave_out_is_optional_in_the_schema():
    for model, keys in (
        (OpportunitySummary, {"saved", "pursuit", "estimate_component", "estimated_total_comp", "estimated_base"}),
        (RadarSummary, {"saved_opportunities", "active_pursuits", "overdue_next_actions", "pursuits_by_stage"}),
        (PursuitItem, {"opportunity"}),
    ):
        schema = model.model_json_schema()
        assert keys <= schema["properties"].keys()
        assert not keys & set(schema["required"]), model.__name__


async def test_the_client_lays_out_a_page_without_the_columns_left_out():
    columns = ["id", "title", "company", "location", "more_locations", "workplace", "level", "listed_days",
               "stated_pay"]
    data = {"total": 1, "count": 1, "sort": "newest", "order": "desc", "filters": {}, "columns": columns,
            "rows": [[42, "Staff PM", "acme", "Berlin", 0, "hybrid", "staff", 3, None]]}
    out = io.StringIO()

    write_human({"ok": True, "operation": "opportunities.search", "data": data, "meta": {}}, out, io.StringIO())

    assert out.getvalue().splitlines()[1] == "     42  Staff PM · acme · Berlin · hybrid · staff · 3d"

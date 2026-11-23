"""A pursuit's several next steps, through the real routes and agent
operations, on real Postgres.

A card lists its open steps soonest first, undated ones last; the pursuit's
`next_action` columns name the first of them. Ticking, reopening, editing a
day and deleting each move that first step, and each write leaves one History
event saying what it did to which step. The older one-step write still works:
clearing its words ticks the soonest step done, and a day with no words and no
step to put it on is refused. A reminder rings once per overdue step.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta, timezone
from typing import Any

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from tracker.agents.config import AgentAccessConfig, set_agent_access
from tracker.agents.operations.catalog import CATALOG
from tracker.agents.operations.outcomes import outcome
from tracker.agents.operations.workspace import ensure_workspace_id
from tracker.api.agent_operations import IDEMPOTENCY_KEY_HEADER, PREFIX
from tracker.db.models import AgentActivity, Job, Notification, PursuitStep

pytestmark = [pytest.mark.asyncio, pytest.mark.usefixtures("no_escape")]

NOW = datetime.now(UTC).replace(microsecond=0)


@pytest_asyncio.fixture
async def roles(db_session) -> tuple[int, int]:
    """Two open roles, agent reads and writes on."""
    await set_agent_access(db_session, AgentAccessConfig(enabled=True, allow_writes=True))
    await ensure_workspace_id(db_session)
    jobs = [
        Job(company="acme", req_id=f"r{n}", dedupe_key=f"acme:r{n}", title=f"Staff PM {n}",
            url=f"https://careers.example.test/r{n}", status="open", level_band="staff",
            first_seen=NOW - timedelta(days=5), last_seen=NOW, in_scope=True)
        for n in (1, 2)
    ]
    db_session.add_all(jobs)
    await db_session.commit()
    return jobs[0].id, jobs[1].id


def _fresh(db_session) -> AsyncSession:
    return async_sessionmaker(db_session.bind, expire_on_commit=False)()


def _at(value: str | None) -> datetime | None:
    return None if value is None else datetime.fromisoformat(value)


async def _apply(api_client, job_id: int) -> None:
    response = await api_client.put(f"/api/jobs/{job_id}/pursuit", json={"stage": "applied"})
    assert response.status_code == 200, response.text


async def _add(api_client, job_id: int, text: str, due: datetime | None = None) -> int:
    body: dict[str, Any] = {"text": text}
    if due is not None:
        body["due"] = due.isoformat()
    response = await api_client.post(f"/api/jobs/{job_id}/pursuit/steps", json=body)
    assert response.status_code == 200, response.text
    return response.json()["step"]["id"]


async def _edit(api_client, job_id: int, step_id: int, body: dict[str, Any]) -> dict:
    response = await api_client.patch(f"/api/jobs/{job_id}/pursuit/steps/{step_id}", json=body)
    assert response.status_code == 200, response.text
    return response.json()["step"]


async def _card(api_client, job_id: int) -> dict:
    response = await api_client.get("/api/applications")
    assert response.status_code == 200, response.text
    return next(card for card in response.json()["applications"] if card["job_id"] == job_id)


async def _steps(api_client, job_id: int) -> list[str]:
    return [step["text"] for step in (await _card(api_client, job_id))["steps"]]


async def _last_event(api_client, job_id: int) -> dict:
    response = await api_client.get(f"/api/applications/{job_id}/activity")
    assert response.status_code == 200, response.text
    return next(item for item in response.json()["items"] if item["kind"] == "event")


async def _three(api_client, job_id: int) -> dict[str, int]:
    """Steps added in an order that is not the soonest-first order."""
    await _apply(api_client, job_id)
    return {
        "Ask Sam": await _add(api_client, job_id, "Ask Sam"),
        "Send portfolio": await _add(api_client, job_id, "Send portfolio", NOW + timedelta(days=5)),
        "Thank-you note": await _add(api_client, job_id, "Thank-you note", NOW + timedelta(days=2)),
    }


# --- the list and its first step ---------------------------------------------------


async def test_a_card_lists_its_steps_soonest_first_and_undated_last_and_names_the_first(
    api_client, db_session, roles
):
    job, _ = roles
    await _three(api_client, job)

    card = await _card(api_client, job)

    assert [step["text"] for step in card["steps"]] == ["Thank-you note", "Send portfolio", "Ask Sam"]
    assert card["steps"][-1]["due"] is None
    assert card["next_action"] == "Thank-you note"
    assert _at(card["next_action_due"]) == NOW + timedelta(days=2)


async def test_ticking_a_step_done_moves_the_first_step_and_says_so_in_history(api_client, db_session, roles):
    job, _ = roles
    ids = await _three(api_client, job)

    ticked = await _edit(api_client, job, ids["Thank-you note"], {"done": True})

    assert ticked["done_at"] is not None
    card = await _card(api_client, job)
    assert [step["text"] for step in card["steps"]] == ["Send portfolio", "Ask Sam"]
    assert card["next_action"] == "Send portfolio"
    assert _at(card["next_action_due"]) == NOW + timedelta(days=5)
    event = await _last_event(api_client, job)
    assert "steps" in event["changed"]
    assert event["step"]["id"] == ids["Thank-you note"] and event["step"]["action"] == "done"
    assert event["step"]["text"] == "Thank-you note"


async def test_reopening_a_ticked_step_puts_it_back_in_its_place(api_client, db_session, roles):
    job, _ = roles
    ids = await _three(api_client, job)
    await _edit(api_client, job, ids["Thank-you note"], {"done": True})

    reopened = await _edit(api_client, job, ids["Thank-you note"], {"done": False})

    assert reopened["done_at"] is None
    assert await _steps(api_client, job) == ["Thank-you note", "Send portfolio", "Ask Sam"]
    assert (await _card(api_client, job))["next_action"] == "Thank-you note"
    assert (await _last_event(api_client, job))["step"]["action"] == "reopened"


async def _detail(api_client, job_id: int) -> dict:
    response = await api_client.get(f"/api/applications/{job_id}")
    assert response.status_code == 200, response.text
    return response.json()


async def test_the_role_page_lists_the_done_steps_latest_done_first_apart_from_the_open_ones(
    api_client, db_session, roles
):
    job, other = roles
    ids = await _three(api_client, job)
    await _add(api_client, job, "Call Mo")
    # Ticked in an order that is neither the order added nor the order of the days.
    for name in ("Send portfolio", "Ask Sam", "Thank-you note"):
        await _edit(api_client, job, ids[name], {"done": True})
    await _apply(api_client, other)
    elsewhere = await _add(api_client, other, "Another role's step")
    await _edit(api_client, other, elsewhere, {"done": True})

    detail = await _detail(api_client, job)

    assert [step["text"] for step in detail["done_steps"]] == ["Thank-you note", "Ask Sam", "Send portfolio"]
    assert all(step["done_at"] is not None for step in detail["done_steps"])
    assert [step["text"] for step in detail["application"]["steps"]] == ["Call Mo"]


async def test_a_done_step_leaves_the_done_steps_when_it_is_reopened_or_deleted(api_client, db_session, roles):
    job, _ = roles
    ids = await _three(api_client, job)
    for step_id in ids.values():
        await _edit(api_client, job, step_id, {"done": True})

    await _edit(api_client, job, ids["Ask Sam"], {"done": False})
    deleted = await api_client.delete(f"/api/jobs/{job}/pursuit/steps/{ids['Send portfolio']}")
    assert deleted.status_code == 200, deleted.text

    detail = await _detail(api_client, job)
    assert [step["text"] for step in detail["done_steps"]] == ["Thank-you note"]
    assert [step["text"] for step in detail["application"]["steps"]] == ["Ask Sam"]
    assert (await _last_event(api_client, job))["step"]["action"] == "removed"


async def test_a_role_with_no_step_done_has_no_done_steps(api_client, db_session, roles):
    job, _ = roles
    await _three(api_client, job)

    assert (await _detail(api_client, job))["done_steps"] == []


async def test_giving_an_undated_step_the_soonest_day_makes_it_first_and_taking_it_off_sends_it_last(
    api_client, db_session, roles
):
    job, _ = roles
    ids = await _three(api_client, job)

    await _edit(api_client, job, ids["Ask Sam"], {"due": (NOW + timedelta(days=1)).isoformat()})

    card = await _card(api_client, job)
    assert [step["text"] for step in card["steps"]] == ["Ask Sam", "Thank-you note", "Send portfolio"]
    assert card["next_action"] == "Ask Sam" and _at(card["next_action_due"]) == NOW + timedelta(days=1)
    assert (await _last_event(api_client, job))["step"]["action"] == "edited"

    await _edit(api_client, job, ids["Ask Sam"], {"due": None})

    assert await _steps(api_client, job) == ["Thank-you note", "Send portfolio", "Ask Sam"]


async def test_deleting_a_step_takes_it_off_and_moves_the_first_step(api_client, db_session, roles):
    job, _ = roles
    ids = await _three(api_client, job)

    response = await api_client.delete(f"/api/jobs/{job}/pursuit/steps/{ids['Thank-you note']}")

    assert response.status_code == 200 and response.json() == {"id": ids["Thank-you note"], "deleted": True}
    card = await _card(api_client, job)
    assert [step["text"] for step in card["steps"]] == ["Send portfolio", "Ask Sam"]
    assert card["next_action"] == "Send portfolio"
    event = await _last_event(api_client, job)
    assert event["step"]["action"] == "removed" and event["step"]["text"] == "Thank-you note"
    async with _fresh(db_session) as session:
        assert await session.get(PursuitStep, ids["Thank-you note"]) is None
    again = await api_client.delete(f"/api/jobs/{job}/pursuit/steps/{ids['Thank-you note']}")
    assert again.status_code == 404


async def test_the_last_step_ticked_leaves_the_card_with_no_next_action(api_client, db_session, roles):
    job, _ = roles
    await _apply(api_client, job)
    only = await _add(api_client, job, "Thank-you note", NOW + timedelta(days=2))

    await _edit(api_client, job, only, {"done": True})

    card = await _card(api_client, job)
    assert card["steps"] == [] and card["next_action"] is None and card["next_action_due"] is None


async def test_a_step_is_reached_only_through_its_own_role(api_client, db_session, roles):
    job, other = roles
    ids = await _three(api_client, job)
    await _apply(api_client, other)
    step = ids["Thank-you note"]

    patched = await api_client.patch(f"/api/jobs/{other}/pursuit/steps/{step}", json={"done": True})
    deleted = await api_client.delete(f"/api/jobs/{other}/pursuit/steps/{step}")

    assert patched.status_code == 404 and deleted.status_code == 404
    # Nothing changed on the role that owns it.
    assert await _steps(api_client, job) == ["Thank-you note", "Send portfolio", "Ask Sam"]


async def test_a_step_with_no_words_or_on_an_unknown_role_is_refused(api_client, db_session, roles):
    job, _ = roles
    await _apply(api_client, job)

    blank = await api_client.post(f"/api/jobs/{job}/pursuit/steps", json={"text": "   "})
    unknown = await api_client.post("/api/jobs/987654321/pursuit/steps", json={"text": "Chase"})
    null_words = await _add(api_client, job, "Chase")
    nulled = await api_client.patch(f"/api/jobs/{job}/pursuit/steps/{null_words}", json={"text": None})

    assert blank.status_code == 422 and unknown.status_code == 404 and nulled.status_code == 422
    assert await _steps(api_client, job) == ["Chase"]


# --- the one-step write ------------------------------------------------------------


async def test_clearing_the_next_action_ticks_the_soonest_step_done_and_keeps_the_rest(
    api_client, db_session, roles
):
    job, _ = roles
    ids = await _three(api_client, job)

    response = await api_client.put(f"/api/jobs/{job}/pursuit", json={"stage": "applied", "next_action": None})

    assert response.status_code == 200, response.text
    card = await _card(api_client, job)
    assert [step["text"] for step in card["steps"]] == ["Send portfolio", "Ask Sam"]
    assert card["next_action"] == "Send portfolio"
    async with _fresh(db_session) as session:
        ticked = await session.get(PursuitStep, ids["Thank-you note"])
        assert ticked is not None and ticked.done_at is not None
    assert (await _last_event(api_client, job))["step"]["action"] == "done"


async def test_a_day_with_no_words_moves_the_soonest_step_and_is_refused_with_no_step(
    api_client, db_session, roles
):
    with_step, without = roles
    ids = await _three(api_client, with_step)
    await _apply(api_client, without)
    day = (NOW + timedelta(days=9)).isoformat()

    moved = await api_client.put(f"/api/jobs/{with_step}/pursuit", json={"stage": "applied", "next_action_due": day})
    refused = await api_client.put(f"/api/jobs/{without}/pursuit", json={"stage": "applied", "next_action_due": day})

    assert moved.status_code == 200, moved.text
    # The day goes on the soonest step, which is now the latest one.
    assert await _steps(api_client, with_step) == ["Send portfolio", "Thank-you note", "Ask Sam"]
    async with _fresh(db_session) as session:
        assert (await session.get(PursuitStep, ids["Thank-you note"])).due == NOW + timedelta(days=9)
    assert refused.status_code == 422, refused.text
    assert (await _card(api_client, without))["steps"] == []


# --- reminders -----------------------------------------------------------------------


async def _reminders(db_session) -> list[Notification]:
    async with _fresh(db_session) as session:
        return list((await session.scalars(
            select(Notification).where(Notification.category == "pursuit_due").order_by(Notification.source_id)
        )).all())


async def test_each_overdue_step_rings_once_and_ticking_one_retracts_only_its_own(api_client, db_session, roles):
    job, _ = roles
    await _apply(api_client, job)
    owed = await _add(api_client, job, "Thank-you note", NOW - timedelta(days=2))
    also_owed = await _add(api_client, job, "Send portfolio", NOW - timedelta(days=1))
    await _add(api_client, job, "Ask Sam", NOW + timedelta(days=3))

    rung = await _reminders(db_session)

    assert [(row.source_type, row.source_id) for row in rung] == [("step", owed), ("step", also_owed)]
    kept = next(row for row in rung if row.source_id == also_owed)

    await _edit(api_client, job, owed, {"done": True})

    left = await _reminders(db_session)
    assert [(row.source_type, row.source_id) for row in left] == [("step", also_owed)]
    # The other step's reminder is the same row, not a new one ringing again.
    assert left[0].id == kept.id and left[0].created_at == kept.created_at


# --- agent operations ----------------------------------------------------------------


def _key(n: int) -> dict[str, str]:
    return {IDEMPOTENCY_KEY_HEADER: f"idk_{n:032d}"}


async def _agent(api_client, method: str, path: str, body: dict[str, Any], n: int) -> tuple[int, dict]:
    response = await api_client.request(method, f"{PREFIX}/pursuits{path}", json=body, headers=_key(n))
    return response.status_code, response.json()


async def test_an_agent_step_added_against_a_stale_revision_changes_nothing(api_client, db_session, roles):
    job, _ = roles
    await _apply(api_client, job)
    await _add(api_client, job, "Thank-you note")
    revision = (await api_client.get(f"{PREFIX}/pursuits/{job}")).json()["data"]["revision"]

    status, stale = await _agent(api_client, "POST", f"/{job}/steps", {"if_revision": revision - 1, "text": "Chase"}, 1)

    assert stale["ok"] is False and stale["error"]["code"] == "revision_conflict"
    assert status == outcome("revision_conflict").http_status
    assert await _steps(api_client, job) == ["Thank-you note"]

    status, added = await _agent(api_client, "POST", f"/{job}/steps", {"if_revision": revision, "text": "Chase"}, 2)

    assert status == 200 and added["data"]["revision"] == revision + 1
    assert [step["text"] for step in added["data"]["steps"]] == ["Thank-you note", "Chase"]


async def test_an_agent_ticks_a_step_done_and_opens_it_again(api_client, db_session, roles):
    job, _ = roles
    ids = await _three(api_client, job)
    step = ids["Thank-you note"]
    revision = (await api_client.get(f"{PREFIX}/pursuits/{job}")).json()["data"]["revision"]

    status, done = await _agent(api_client, "POST", f"/{job}/steps/{step}/done", {"if_revision": revision}, 1)

    assert status == 200, done
    assert [s["text"] for s in done["data"]["steps"]] == ["Send portfolio", "Ask Sam"]
    assert done["data"]["next_action"] == "Send portfolio"

    status, undone = await _agent(
        api_client, "POST", f"/{job}/steps/{step}/undo", {"if_revision": done["data"]["revision"]}, 2
    )

    assert status == 200, undone
    assert [s["text"] for s in undone["data"]["steps"]] == ["Thank-you note", "Send portfolio", "Ask Sam"]
    assert undone["data"]["next_action"] == "Thank-you note"
    async with _fresh(db_session) as session:
        rows = (await session.scalars(
            select(AgentActivity).where(AgentActivity.kind == "change").order_by(AgentActivity.id)
        )).all()
    assert [(row.operation, row.subject["topic"], row.subject["action"]) for row in rows] == [
        ("steps.done", "pursuit.step", "done"), ("steps.undo", "pursuit.step", "undo"),
    ]
    assert rows[0].subject["step"] == "Thank-you note"


async def test_an_agent_step_of_another_role_is_not_found(api_client, db_session, roles):
    job, other = roles
    ids = await _three(api_client, job)
    await _apply(api_client, other)
    revision = (await api_client.get(f"{PREFIX}/pursuits/{other}")).json()["data"]["revision"]

    status, body = await _agent(
        api_client, "POST", f"/{other}/steps/{ids['Thank-you note']}/done", {"if_revision": revision}, 1
    )

    assert body["ok"] is False and body["error"]["code"] == "not_found"
    assert status == outcome("not_found").http_status
    assert await _steps(api_client, job) == ["Thank-you note", "Send portfolio", "Ask Sam"]


async def test_an_agent_due_only_patch_with_no_step_names_the_missing_words(api_client, db_session, roles):
    job, _ = roles
    await _apply(api_client, job)
    revision = (await api_client.get(f"{PREFIX}/pursuits/{job}")).json()["data"]["revision"]

    status, body = await _agent(
        api_client, "PATCH", f"/{job}", {"if_revision": revision, "next_action_due": NOW.isoformat()}, 1
    )

    assert body["ok"] is False and body["error"]["code"] == "invalid_input"
    assert body["error"]["details"]["field"] == "next_action"
    assert status == outcome("invalid_input").http_status
    assert (await _card(api_client, job))["steps"] == []


async def test_agents_have_no_operation_that_deletes_a_step(api_client, db_session, roles):
    assert sorted(d.id for d in CATALOG if d.id.startswith("steps.")) == [
        "steps.add", "steps.done", "steps.edit", "steps.undo",
    ]
    job, _ = roles
    ids = await _three(api_client, job)

    response = await api_client.delete(f"{PREFIX}/pursuits/{job}/steps/{ids['Ask Sam']}", headers=_key(1))

    assert response.status_code in (404, 405)
    assert "Ask Sam" in await _steps(api_client, job)


# --- review fixes ------------------------------------------------------------------


async def test_ticking_a_step_done_through_the_agent_does_not_list_its_words_as_cleared(
    api_client, db_session, roles
):
    job, _ = roles
    ids = await _three(api_client, job)
    revision = (await api_client.get(f"{PREFIX}/pursuits/{job}")).json()["data"]["revision"]

    status, done = await _agent(
        api_client, "POST", f"/{job}/steps/{ids['Thank-you note']}/done", {"if_revision": revision}, 1
    )

    assert status == 200, done
    async with _fresh(db_session) as session:
        row = await session.scalar(select(AgentActivity).where(AgentActivity.operation == "steps.done"))
    assert row is not None
    assert not row.changes
    assert row.subject["step"] == "Thank-you note"


async def test_an_agent_edit_lists_the_words_and_day_before_and_after(api_client, db_session, roles):
    job, _ = roles
    ids = await _three(api_client, job)
    revision = (await api_client.get(f"{PREFIX}/pursuits/{job}")).json()["data"]["revision"]

    status, edited = await _agent(
        api_client, "PATCH", f"/{job}/steps/{ids['Ask Sam']}", {"if_revision": revision, "text": "Ask Sam about pay"}, 1
    )

    assert status == 200, edited
    async with _fresh(db_session) as session:
        row = await session.scalar(select(AgentActivity).where(AgentActivity.operation == "steps.edit"))
    assert row is not None
    assert [(c["field"], c["before"], c["after"]) for c in row.changes] == [
        ("step_text", "Ask Sam", "Ask Sam about pay")
    ]


async def test_an_agent_edit_of_a_ticked_step_lists_its_new_words_and_day(api_client, db_session, roles):
    job, _ = roles
    ids = await _three(api_client, job)
    step = ids["Ask Sam"]
    revision = (await api_client.get(f"{PREFIX}/pursuits/{job}")).json()["data"]["revision"]
    status, done = await _agent(api_client, "POST", f"/{job}/steps/{step}/done", {"if_revision": revision}, 1)
    assert status == 200, done
    due = datetime(2030, 3, 4, 9, tzinfo=timezone(timedelta(hours=2)))

    status, edited = await _agent(
        api_client, "PATCH", f"/{job}/steps/{step}",
        {"if_revision": done["data"]["revision"], "text": "Asked Sam about pay", "due": due.isoformat()}, 2,
    )

    assert status == 200, edited
    assert step not in [s["id"] for s in edited["data"]["steps"]]
    async with _fresh(db_session) as session:
        row = await session.scalar(select(AgentActivity).where(AgentActivity.operation == "steps.edit"))
    assert row is not None
    changes = {c["field"]: (c["before"], c["after"]) for c in row.changes}
    assert changes["step_text"] == ("Ask Sam", "Asked Sam about pay")
    assert _at(changes["step_due"][1]) == datetime(2030, 3, 4, 7, tzinfo=UTC)
    assert row.subject["step"] == "Asked Sam about pay"


async def test_a_step_patch_that_names_nothing_is_refused_as_invalid_input(api_client, db_session, roles):
    job, _ = roles
    ids = await _three(api_client, job)

    response = await api_client.patch(f"/api/jobs/{job}/pursuit/steps/{ids['Ask Sam']}", json={})

    assert response.status_code == 422, response.text
    assert await _steps(api_client, job) == ["Thank-you note", "Send portfolio", "Ask Sam"]


async def test_a_day_sent_with_no_offset_is_read_as_utc_everywhere_it_enters(api_client, db_session, roles):
    job, _ = roles
    await _apply(api_client, job)
    # One base for every date, so the step sent with an offset is always the soonest.
    base = (NOW + timedelta(days=30)).replace(hour=9, minute=0, second=0)

    def day(offset: int) -> datetime:
        return base + timedelta(days=offset)

    def bare(offset: int) -> str:
        return day(offset).replace(tzinfo=None).isoformat()

    await _add(api_client, job, "Dated with an offset", day(0))

    step = await api_client.post(f"/api/jobs/{job}/pursuit/steps", json={"text": "Bare day", "due": bare(1)})
    pursuit = await api_client.put(f"/api/jobs/{job}/pursuit", json={"next_action_due": bare(2)})

    assert step.status_code == 200, step.text
    assert _at(step.json()["step"]["due"]) == day(1)
    assert pursuit.status_code == 200, pursuit.text
    # The one-step write moved the soonest step then, the one sent with an offset.
    moved = {step["text"]: _at(step["due"]) for step in (await _card(api_client, job))["steps"]}
    assert moved["Dated with an offset"] == day(2)
    assert moved["Bare day"] == day(1)


async def test_a_step_written_in_the_store_rings_its_reminder_without_the_route(api_client, db_session, roles):
    from tracker.agents.pursuits import StepUpdate, StepWrite, add_step, update_step

    job, _ = roles
    await _apply(api_client, job)

    pursuit, step = await add_step(
        db_session, job, StepWrite(text="Chase the recruiter", due=NOW - timedelta(days=1)), actor="user"
    )
    await db_session.commit()
    rung = (await db_session.scalars(select(Notification).where(Notification.source_type == "step"))).all()
    assert [row.source_id for row in rung] == [step.id]

    await update_step(db_session, job, step.id, StepUpdate(done=True), actor="user")
    await db_session.commit()
    assert (await db_session.scalars(select(Notification).where(Notification.source_type == "step"))).all() == []

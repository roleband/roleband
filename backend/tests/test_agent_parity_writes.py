"""The writes an MCP tool makes today, as keyed operations under `allow_writes`.

`pursuits.save`, `pursuits.patch`, `recipes.draft.save` and the read that
recovers a lost reply, `receipts.get`, driven over the real agent router on a
scratch database. The MCP tool bodies run beside them through `session_scope`,
so "what the tool does" is the tool's own code, and each deliberate difference
the parity checklist names is asserted as one: explicit null clears, the
revision a patch states, the receipt a retry replays.

Every refusal is checked for what it leaves behind as well as for its code: a
stale revision, a write with writes off, an input error and an unknown role
change no row and keep no receipt.
"""

from __future__ import annotations

import asyncio
import copy
import re
from datetime import UTC, datetime, timedelta, timezone
from typing import Any

import pytest
import pytest_asyncio
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

import tracker.mcp.server as server
from tests.test_agent_writes_db import _until_waiting
from tests.test_recipe_adapter import RECIPE
from tracker.agents.config import AgentAccessConfig, set_agent_access
from tracker.agents.operations.catalog import CATALOG
from tracker.agents.operations.outcomes import EXIT_NOT_FOUND, outcome
from tracker.agents.operations.pursuits import VIA, PursuitItem
from tracker.agents.operations.recipes import SavedDraft
from tracker.agents.operations.workspace import ensure_workspace_id
from tracker.agents.receipts import LEGACY_AGENT_PRINCIPAL, ReceiptKey, lock_key
from tracker.api.agent_operations import IDEMPOTENCY_KEY_HEADER, PREFIX
from tracker.db.models import (
    CommandReceipt,
    ConnectorRecipe,
    ConnectorRecipeRevision,
    Favorite,
    Job,
    Notification,
    Pursuit,
    PursuitEvent,
)
from tracker.notifications.pursuit_due import generate_pursuit_due_notifications

pytestmark = [pytest.mark.asyncio, pytest.mark.usefixtures("no_escape")]

KEY = "idk_" + "a" * 32
OTHER_KEY = "idk_" + "b" * 32
DUE = datetime(2026, 12, 1, 9, 0, tzinfo=UTC)


@pytest_asyncio.fixture
async def roles(db_session, scratch_scope) -> tuple[int, int]:
    """Two open roles, agent reads and writes on."""
    await set_agent_access(db_session, AgentAccessConfig(enabled=True, allow_writes=True))
    await ensure_workspace_id(db_session)
    jobs = [
        Job(company="acme", req_id=f"r{n}", dedupe_key=f"acme:r{n}", title=f"Staff PM {n}",
            url=f"https://careers.example.test/r{n}", status="open", level_band="staff")
        for n in (1, 2)
    ]
    db_session.add_all(jobs)
    await db_session.commit()
    return jobs[0].id, jobs[1].id


def _fresh(db_session) -> AsyncSession:
    return async_sessionmaker(db_session.bind, expire_on_commit=False)()


def _headers(key: str | None) -> dict[str, str]:
    return {} if key is None else {IDEMPOTENCY_KEY_HEADER: key}


async def _save(api_client, job_id: int, body: dict[str, Any] | None = None, *, key: str | None = KEY):
    response = await api_client.put(f"{PREFIX}/pursuits/{job_id}", json=body or {}, headers=_headers(key))
    return response, response.json()


async def _patch(api_client, job_id: int, body: dict[str, Any], *, key: str | None = KEY):
    response = await api_client.patch(f"{PREFIX}/pursuits/{job_id}", json=body, headers=_headers(key))
    return response, response.json()


async def _draft(api_client, document: dict[str, Any], *, key: str | None = KEY):
    response = await api_client.post(f"{PREFIX}/recipes/drafts", json={"document": document}, headers=_headers(key))
    return response, response.json()


async def _receipt(api_client, operation: str, key: str):
    response = await api_client.get(f"{PREFIX}/receipts", params={"operation": operation, "key": key})
    return response, response.json()


async def _dashboard_edit(api_client, job_id: int, body: dict[str, Any]) -> None:
    response = await api_client.put(f"/api/jobs/{job_id}/pursuit", json=body)
    assert response.status_code == 200, response.text


def _data(response, body: dict) -> dict:
    assert response.status_code == 200 and body["ok"] is True, body
    return body["data"]


def _refused(response, body: dict, code: str) -> dict:
    assert body["ok"] is False and body["data"] is None, body
    assert body["error"]["code"] == code, body["error"]
    assert response.status_code == outcome(code).http_status
    return body["error"]


async def _pursuit(db_session, job_id: int) -> Pursuit | None:
    async with _fresh(db_session) as session:
        return await session.scalar(select(Pursuit).where(Pursuit.job_id == job_id))


async def _events(db_session, job_id: int) -> list[tuple[str, str, dict]]:
    async with _fresh(db_session) as session:
        rows = await session.execute(
            select(PursuitEvent.actor, PursuitEvent.event_type, PursuitEvent.detail)
            .join(Pursuit, Pursuit.id == PursuitEvent.pursuit_id)
            .where(Pursuit.job_id == job_id)
            .order_by(PursuitEvent.id)
        )
        return [tuple(row) for row in rows.all()]


async def _count(db_session, model) -> int:
    async with _fresh(db_session) as session:
        return await session.scalar(select(func.count()).select_from(model))


# --------------------------------------------------------------------------- #
# pursuits.save  <-  save_opportunity
# --------------------------------------------------------------------------- #


async def test_save_starts_a_pursuit_at_saved_and_records_the_agent_and_its_way_in(api_client, db_session, roles):
    job_id, _ = roles

    response, body = await _save(api_client, job_id)

    data = _data(response, body)
    assert (data["opportunity_id"], data["stage"], data["priority"], data["revision"]) == (job_id, "saved", 3, 1)
    assert data["opportunity"]["title"] == "Staff PM 1"
    assert body["meta"]["idempotency_key"] == KEY and body["meta"]["replayed"] is False
    assert [(actor, kind, detail.get("via")) for actor, kind, detail in await _events(db_session, job_id)] == [
        ("agent", "created", VIA)
    ]
    async with _fresh(db_session) as session:
        assert await session.scalar(select(func.count()).select_from(Favorite).where(Favorite.job_id == job_id)) == 1


async def test_save_answers_what_the_tool_answers_for_the_same_pursuit(api_client, db_session, roles):
    job_id, _ = roles
    data = _data(*await _save(api_client, job_id, {"priority": 2}))

    # The tool saving it again with the same priority changes nothing, and
    # answers the pursuit as it stands: the fields the operation answered,
    # with the opportunity's id as `opportunity_id` in place of the row's.
    tool = await server.save_opportunity(job_id, priority=2)
    fields = {key: value for key, value in tool.items() if key not in ("id", "job_id")}

    assert PursuitItem.model_validate(
        {**fields, "opportunity_id": tool["job_id"], "revision": 1, "opportunity": data["opportunity"]}
    ).model_dump(mode="json") == data
    assert (await _pursuit(db_session, job_id)).revision == 1


async def test_save_keeps_an_existing_pursuits_stage_and_notes_and_changes_only_a_given_priority(
    api_client, db_session, roles
):
    job_id, _ = roles
    await _dashboard_edit(api_client, job_id, {"stage": "applied", "notes": "the person's", "priority": 4})

    unchanged = _data(*await _save(api_client, job_id, key=KEY))
    reprioritised = _data(*await _save(api_client, job_id, {"priority": 1}, key=OTHER_KEY))

    assert (unchanged["stage"], unchanged["notes"], unchanged["priority"], unchanged["revision"]) == (
        "applied", "the person's", 4, 1
    )
    assert (reprioritised["stage"], reprioritised["notes"], reprioritised["priority"], reprioritised["revision"]) == (
        "applied", "the person's", 1, 2
    )


async def test_save_with_a_stale_revision_changes_nothing_and_names_the_current_one(api_client, db_session, roles):
    job_id, _ = roles
    await _dashboard_edit(api_client, job_id, {"priority": 4})
    await _dashboard_edit(api_client, job_id, {"notes": "moved on"})  # revision 2

    error = _refused(*await _save(api_client, job_id, {"priority": 1, "if_revision": 1}), "revision_conflict")

    assert error["details"] == {"expected_revision": 1, "current_revision": 2}
    assert error["next_actions"] == [{"operation": "pursuits.get", "arguments": {"opportunity_id": job_id}}]
    pursuit = await _pursuit(db_session, job_id)
    assert (pursuit.priority, pursuit.revision) == (4, 2)
    assert await _count(db_session, CommandReceipt) == 0


async def test_save_with_revision_zero_creates_and_with_zero_after_creation_conflicts(api_client, db_session, roles):
    job_id, _ = roles

    created = _data(*await _save(api_client, job_id, {"if_revision": 0}))
    error = _refused(*await _save(api_client, job_id, {"priority": 2, "if_revision": 0}, key=OTHER_KEY),
                     "revision_conflict")

    assert created["revision"] == 1
    assert error["details"] == {"expected_revision": 0, "current_revision": 1}


@pytest.mark.parametrize("body", [{"priority": None}, {"priority": 0}, {"if_revision": None}, {"stage": "applied"}])
async def test_save_refuses_a_null_an_out_of_range_priority_and_a_field_it_does_not_take(
    api_client, db_session, roles, body
):
    job_id, _ = roles

    _refused(*await _save(api_client, job_id, body), "invalid_input")

    assert await _pursuit(db_session, job_id) is None
    assert await _count(db_session, CommandReceipt) == 0


async def test_save_of_an_unknown_role_is_not_found_and_keeps_no_receipt(api_client, db_session, roles):
    _refused(*await _save(api_client, 999_999), "not_found")

    assert await _count(db_session, Pursuit) == 0
    assert await _count(db_session, CommandReceipt) == 0


async def test_save_without_a_key_is_refused_before_anything_is_written(api_client, db_session, roles):
    job_id, _ = roles

    error = _refused(*await _save(api_client, job_id, key=None), "invalid_input")

    assert error["details"] == {"header": IDEMPOTENCY_KEY_HEADER}
    assert await _pursuit(db_session, job_id) is None


# --------------------------------------------------------------------------- #
# Replay: one key, one write
# --------------------------------------------------------------------------- #


async def test_a_retried_save_replays_and_writes_once(api_client, db_session, roles):
    job_id, _ = roles
    first = _data(*await _save(api_client, job_id, {"priority": 2}))

    response, body = await _save(api_client, job_id, {"priority": 2})

    assert _data(response, body) == first and body["meta"]["replayed"] is True
    assert len(await _events(db_session, job_id)) == 1
    assert await _count(db_session, CommandReceipt) == 1


@pytest.mark.parametrize("write", ["save", "patch"])
async def test_a_receipt_stored_with_the_row_keys_replays_in_the_record_shape(api_client, db_session, roles, write):
    """A receipt keeps the result in the keys it was stored with. One that
    names the pursuit row's `id` and `job_id` still replays, as the
    `opportunity_id` record, and writes nothing again."""
    job_id, _ = roles
    body = {"priority": 2} if write == "save" else {"if_revision": 0, "notes": "first"}
    send = _save if write == "save" else _patch
    first = _data(*await send(api_client, job_id, body))
    async with _fresh(db_session) as session:
        receipt = await session.scalar(select(CommandReceipt))
        row_id = (await session.scalar(select(Pursuit.id).where(Pursuit.job_id == job_id)))
        stored = {key: value for key, value in receipt.result.items() if key != "opportunity_id"}
        receipt.result = {"id": row_id, "job_id": job_id, **stored}
        await session.commit()

    response, replayed = await send(api_client, job_id, body)

    assert _data(response, replayed) == first and replayed["meta"]["replayed"] is True
    assert "id" not in replayed["data"] and "job_id" not in replayed["data"]
    assert len(await _events(db_session, job_id)) == 1


async def test_two_identical_saves_at_once_write_once(api_client, db_session, roles):
    """Both saves queue on the key's lock, held here until both wait, so they
    truly overlap: one writes, the other replays its receipt."""
    job_id, _ = roles
    async with _fresh(db_session) as session:
        workspace = await ensure_workspace_id(session)
    async with _fresh(db_session) as holder:
        await lock_key(holder, ReceiptKey(workspace, LEGACY_AGENT_PRINCIPAL, "pursuits.save", KEY))
        tasks = [asyncio.create_task(_save(api_client, job_id, {"priority": 2})) for _ in range(2)]
        await _until_waiting(db_session.bind, 2)
        assert not any(task.done() for task in tasks)
        await holder.rollback()
    answers = await asyncio.gather(*tasks)

    assert sorted(body["meta"]["replayed"] for _, body in answers) == [False, True]
    assert answers[0][1]["data"] == answers[1][1]["data"]
    assert len(await _events(db_session, job_id)) == 1
    assert (await _pursuit(db_session, job_id)).revision == 1


async def test_a_retried_patch_replays_its_result_after_the_person_moved_the_pursuit_on(
    api_client, db_session, roles
):
    """Replay comes before the revision check: the lost reply of a revision-1
    patch is recovered with its revision-1 input, and the person's later edit
    is neither refused as a conflict nor overwritten."""
    job_id, _ = roles
    await _dashboard_edit(api_client, job_id, {"notes": "first"})  # revision 1
    body = {"if_revision": 1, "next_action": "Email the recruiter"}
    first = _data(*await _patch(api_client, job_id, body))
    await _dashboard_edit(api_client, job_id, {"next_action": "the person's own"})  # revision 3

    response, replay = await _patch(api_client, job_id, body)

    assert _data(response, replay) == first and replay["meta"]["replayed"] is True
    pursuit = await _pursuit(db_session, job_id)
    assert (pursuit.next_action, pursuit.revision) == ("the person's own", 3)


async def test_one_key_for_another_patch_is_a_conflict_not_a_second_write(api_client, db_session, roles):
    job_id, _ = roles
    _data(*await _patch(api_client, job_id, {"if_revision": 0, "notes": "one"}))

    error = _refused(*await _patch(api_client, job_id, {"if_revision": 1, "notes": "two"}), "idempotency_conflict")

    assert error["details"] == {"idempotency_key": KEY}
    assert (await _pursuit(db_session, job_id)).notes == "one"


async def test_a_null_and_an_absent_field_are_different_requests_under_one_key(api_client, db_session, roles):
    job_id, _ = roles
    await _dashboard_edit(api_client, job_id, {"notes": "keep", "next_action": "call"})  # revision 1
    _data(*await _patch(api_client, job_id, {"if_revision": 1, "next_action": "call back"}))

    _refused(
        *await _patch(api_client, job_id, {"if_revision": 1, "next_action": "call back", "notes": None}),
        "idempotency_conflict",
    )

    assert (await _pursuit(db_session, job_id)).notes == "keep"


# --------------------------------------------------------------------------- #
# pursuits.patch  <-  update_pursuit: explicit null
# --------------------------------------------------------------------------- #


async def _followed_up(api_client, job_id: int) -> int:
    """A pursuit with notes, a next action and its due date; its revision."""
    await _dashboard_edit(api_client, job_id, {
        "stage": "applied", "notes": "Referred by Sam", "next_action": "Follow up",
        "next_action_due": DUE.isoformat(),
    })
    return 1


async def test_null_clears_the_due_date_and_leaves_every_absent_field(api_client, db_session, roles):
    job_id, _ = roles
    revision = await _followed_up(api_client, job_id)

    data = _data(*await _patch(api_client, job_id, {"if_revision": revision, "next_action_due": None}))

    assert data["next_action_due"] is None
    assert (data["stage"], data["notes"], data["next_action"], data["revision"]) == (
        "applied", "Referred by Sam", "Follow up", revision + 1
    )
    pursuit = await _pursuit(db_session, job_id)
    assert (pursuit.next_action_due, pursuit.notes, pursuit.next_action) == (None, "Referred by Sam", "Follow up")


async def test_null_clears_the_notes_and_the_next_action(api_client, db_session, roles):
    job_id, _ = roles
    revision = await _followed_up(api_client, job_id)

    data = _data(*await _patch(api_client, job_id, {"if_revision": revision, "notes": None, "next_action": None}))

    assert (data["notes"], data["next_action"]) == (None, None)
    pursuit = await _pursuit(db_session, job_id)
    assert (pursuit.notes, pursuit.next_action, pursuit.next_action_due) == (None, None, DUE)
    *_, (actor, _, detail) = await _events(db_session, job_id)
    assert actor == "agent" and detail["changed"] == ["next_action", "notes"] and detail["via"] == VIA
    assert detail["before"] == {"next_action": "Follow up", "notes": "Referred by Sam"}


async def test_a_patch_of_one_field_leaves_the_others_as_they_were(api_client, db_session, roles):
    job_id, _ = roles
    revision = await _followed_up(api_client, job_id)

    data = _data(*await _patch(api_client, job_id, {"if_revision": revision, "priority": 1}))

    assert (data["priority"], data["stage"], data["notes"], data["next_action"]) == (
        1, "applied", "Referred by Sam", "Follow up"
    )
    assert data["next_action_due"] == DUE.isoformat().replace("+00:00", "Z")


async def test_the_tool_cannot_clear_a_due_date_and_the_operation_can(api_client, db_session, roles):
    """The difference the checklist names: the MCP tool reads null as not
    given, which is how the baseline's one wrong write happened."""
    job_id, _ = roles
    revision = await _followed_up(api_client, job_id)

    tool = await server.update_pursuit(job_id, next_action="Follow up", next_action_due=None)
    assert tool["next_action_due"] == DUE
    data = _data(*await _patch(api_client, job_id, {"if_revision": revision, "next_action_due": None}))

    assert data["next_action_due"] is None


async def test_a_stale_patch_is_refused_and_the_persons_edit_stands(api_client, db_session, roles):
    job_id, _ = roles
    revision = await _followed_up(api_client, job_id)
    await _dashboard_edit(api_client, job_id, {"notes": "the person's newer note"})

    error = _refused(*await _patch(api_client, job_id, {"if_revision": revision, "notes": "agent"}),
                     "revision_conflict")

    assert error["details"] == {"expected_revision": revision, "current_revision": revision + 1}
    assert (await _pursuit(db_session, job_id)).notes == "the person's newer note"
    assert await _count(db_session, CommandReceipt) == 0


async def test_a_patch_with_revision_zero_starts_the_pursuit_as_the_tool_does(api_client, db_session, roles):
    job_id, _ = roles

    data = _data(*await _patch(api_client, job_id, {"if_revision": 0, "stage": "researching"}))

    assert (data["stage"], data["priority"], data["revision"]) == ("researching", 3, 1)


async def test_a_pursuit_record_names_only_the_id_a_patch_takes(api_client, db_session, roles):
    _, pursued = roles
    await _dashboard_edit(api_client, pursued, {"stage": "applied"})

    listed = (await api_client.get(f"{PREFIX}/pursuits")).json()["data"]["items"]
    got = (await api_client.get(f"{PREFIX}/pursuits/{pursued}")).json()["data"]
    patched = _data(*await _patch(api_client, pursued, {"if_revision": got["revision"], "priority": 2}))

    for record in (*listed, got, patched):
        assert [key for key in record if key == "id" or key.endswith("_id")] == ["opportunity_id"], record
        assert record["opportunity_id"] == pursued


async def test_a_patch_at_a_revision_of_an_opportunity_with_no_pursuit_says_there_is_none(
    api_client, db_session, roles
):
    """The misread a record with the pursuit row's own id invited: that id
    sent as the opportunity, at the pursuit's revision. The opportunity it
    names has no pursuit, so the answer says so, rather than a conflict that
    re-reading can never resolve."""
    unpursued, pursued = roles
    await _dashboard_edit(api_client, pursued, {"next_action": "Follow up", "next_action_due": DUE.isoformat()})
    row = await _pursuit(db_session, pursued)
    assert (row.id, row.revision) == (unpursued, 1), "the row id names the other role, as in the misread"

    error = _refused(*await _patch(api_client, row.id, {"if_revision": 1, "next_action": None}), "not_found")

    assert outcome("not_found").exit_status == EXIT_NOT_FOUND
    assert error["details"] == {"opportunity_id": unpursued, "expected_revision": 1, "current_revision": 0}
    assert "no pursuit for this opportunity" in error["message"] and "pursuits.list" in error["message"]
    assert error["next_actions"] == [{"operation": "pursuits.list", "arguments": {}}]
    assert await _pursuit(db_session, unpursued) is None
    kept = await _pursuit(db_session, pursued)
    assert (kept.next_action, kept.revision) == ("Follow up", 1)
    assert await _count(db_session, CommandReceipt) == 0

    # The same change at revision 0 starts that pursuit; a save at a stale
    # revision of a pursuit that exists is still a conflict.
    created = _data(*await _patch(api_client, unpursued, {"if_revision": 0, "next_action": None}, key=OTHER_KEY))
    assert (created["opportunity_id"], created["revision"]) == (unpursued, 1)
    stale = _refused(*await _save(api_client, pursued, {"priority": 1, "if_revision": 7}), "revision_conflict")
    assert stale["details"] == {"expected_revision": 7, "current_revision": 1}


#: Words a refusal would use to steer the caller towards a write.
_WRITE_WORDS = re.compile(r"\b(creat|start|begin|send|save|patch|write|retry|if_revision|revision 0 to)", re.I)


@pytest.mark.parametrize("write", ["patch", "save"])
@pytest.mark.parametrize("revision", [1, 7])
async def test_the_no_pursuit_refusal_never_suggests_a_create(api_client, db_session, roles, write, revision):
    """The caller most likely holds a wrong id; a create suggested there is a
    pursuit on an opportunity the person never chose. So neither the message
    nor a suggested call leads to a write."""
    unpursued, _ = roles
    body = {"if_revision": revision, **({"next_action": None} if write == "patch" else {"priority": 2})}
    send = _patch if write == "patch" else _save

    error = _refused(*await send(api_client, unpursued, body), "not_found")

    assert not _WRITE_WORDS.search(error["message"]), error["message"]
    assert error["next_actions"], "the refusal points somewhere to look"
    for action in error["next_actions"]:
        assert CATALOG.get(action["operation"]).access == "read", action
        assert "if_revision" not in action["arguments"], action
    assert await _pursuit(db_session, unpursued) is None


async def test_the_write_word_check_catches_a_create_hint():
    # Negative control: the message this refusal must not carry is caught.
    assert _WRITE_WORDS.search("To start pursuing this opportunity, send the change with if_revision 0.")
    assert _WRITE_WORDS.search("Create it with revision 0.")
    assert not _WRITE_WORDS.search(
        "There is no pursuit for this opportunity, so its revision is 0. "
        "Check the id: pursuits.list names each pursuit's opportunity_id."
    )


@pytest.mark.parametrize("body", [
    {"stage": None},
    {"priority": None},
    {},
    {"stage": "hired"},
    {"opportunity": 1, "notes": "x"},
    {"next_action_due": "2026-01-01T00:00:00"},
])
async def test_an_input_error_writes_nothing_and_leaves_the_key_unused(api_client, db_session, roles, body):
    job_id, _ = roles
    revision = await _followed_up(api_client, job_id)

    _refused(*await _patch(api_client, job_id, {"if_revision": revision, **body}), "invalid_input")

    assert (await _pursuit(db_session, job_id)).revision == revision
    assert await _count(db_session, CommandReceipt) == 0
    # The refused request did not consume the key: a valid one under it writes.
    assert _data(*await _patch(api_client, job_id, {"if_revision": revision, "priority": 2}))["priority"] == 2


async def test_a_patch_without_its_revision_is_an_input_error(api_client, db_session, roles):
    job_id, _ = roles
    await _followed_up(api_client, job_id)

    error = _refused(*await _patch(api_client, job_id, {"notes": "x"}), "invalid_input")

    assert {"location": ["if_revision"], "type": "missing"} in error["details"]["errors"]


async def test_a_due_date_set_in_the_past_rings_and_clearing_it_retracts_the_reminder(api_client, db_session, roles):
    job_id, _ = roles
    past = datetime.now(UTC) - timedelta(days=2)

    _data(*await _patch(api_client, job_id, {"if_revision": 0, "next_action": "Chase", "next_action_due": past.isoformat()}))
    rung = await _reminders(db_session, job_id)
    _data(*await _patch(api_client, job_id, {"if_revision": 1, "next_action_due": None}, key=OTHER_KEY))

    assert rung == 1
    assert await _reminders(db_session, job_id) == 0


async def test_a_reminder_the_person_read_stays_read_whatever_offset_the_due_time_came_in(
    api_client, db_session, roles
):
    """The write's own reminder pass and a later one read the same instant;
    a due time sent with another offset than UTC must not look like a new
    follow-up to the later pass, which would ring it again unread."""
    job_id, _ = roles
    due = (datetime.now(UTC) - timedelta(days=2)).astimezone(timezone(timedelta(hours=2)))
    _data(*await _patch(api_client, job_id, {"if_revision": 0, "next_action": "Chase", "next_action_due": due.isoformat()}))
    async with _fresh(db_session) as session:
        await session.execute(
            update(Notification).where(Notification.job_id == job_id).values(read_at=datetime.now(UTC))
        )
        await session.commit()

    async with _fresh(db_session) as session:
        await generate_pursuit_due_notifications(session)
        await session.commit()

    async with _fresh(db_session) as session:
        rows = (await session.execute(
            select(Notification.read_at).where(Notification.job_id == job_id, Notification.category == "pursuit_due")
        )).all()
    assert len(rows) == 1 and rows[0].read_at is not None


async def test_a_read_reminder_whose_due_time_was_stored_with_another_offset_stays_read(
    api_client, db_session, roles
):
    """A reminder already stored with its writer's offset names the same
    instant as the pass's UTC value: it is the same follow-up, so it keeps the
    person's read state instead of ringing again."""
    job_id, _ = roles
    due = datetime.now(UTC) - timedelta(days=2)
    _data(*await _patch(api_client, job_id, {"if_revision": 0, "next_action": "Chase", "next_action_due": due.isoformat()}))
    async with _fresh(db_session) as session:
        reminder = await session.scalar(select(Notification).where(Notification.job_id == job_id))
        reminder.meta = {**reminder.meta, "due_at": due.astimezone(timezone(timedelta(hours=-5))).isoformat()}
        reminder.read_at = datetime.now(UTC)
        await session.commit()

    async with _fresh(db_session) as session:
        await generate_pursuit_due_notifications(session)
        await session.commit()

    async with _fresh(db_session) as session:
        rows = (await session.execute(
            select(Notification.read_at).where(Notification.job_id == job_id, Notification.category == "pursuit_due")
        )).all()
    assert len(rows) == 1 and rows[0].read_at is not None


async def test_a_new_due_time_rings_again_unread_though_the_last_was_read(api_client, db_session, roles):
    job_id, _ = roles
    due = datetime.now(UTC) - timedelta(days=3)
    _data(*await _patch(api_client, job_id, {"if_revision": 0, "next_action": "Chase", "next_action_due": due.isoformat()}))
    async with _fresh(db_session) as session:
        await session.execute(
            update(Notification).where(Notification.job_id == job_id).values(read_at=datetime.now(UTC))
        )
        await session.commit()

    later = due + timedelta(days=1)
    _data(*await _patch(api_client, job_id, {"if_revision": 1, "next_action_due": later.isoformat()}, key=OTHER_KEY))

    async with _fresh(db_session) as session:
        rows = (await session.execute(
            select(Notification.read_at).where(Notification.job_id == job_id, Notification.category == "pursuit_due")
        )).all()
    assert len(rows) == 1 and rows[0].read_at is None


async def _reminders(db_session, job_id: int) -> int:
    async with _fresh(db_session) as session:
        return await session.scalar(
            select(func.count()).select_from(Notification).where(
                Notification.job_id == job_id, Notification.category == "pursuit_due"
            )
        )


# --------------------------------------------------------------------------- #
# recipes.draft.save  <-  save_recipe_draft
# --------------------------------------------------------------------------- #


async def _revisions(db_session) -> list[tuple[str, int, str, str]]:
    async with _fresh(db_session) as session:
        rows = await session.execute(
            select(ConnectorRecipe.slug, ConnectorRecipeRevision.version, ConnectorRecipeRevision.created_by,
                   ConnectorRecipe.status)
            .join(ConnectorRecipe, ConnectorRecipe.id == ConnectorRecipeRevision.recipe_id)
            .order_by(ConnectorRecipeRevision.id)
        )
        return [tuple(row) for row in rows.all()]


async def test_a_draft_is_appended_never_activated_and_answers_as_the_tool_does(api_client, db_session, roles):
    data = _data(*await _draft(api_client, RECIPE))
    tool = await server.save_recipe_draft(copy.deepcopy(RECIPE), confirmed=True)

    assert data["slug"] == "demo-careers" and data["version"] == 1
    assert SavedDraft.model_validate(tool).model_dump() == {**data, "revision_id": tool["revision_id"], "version": 2}
    assert await _revisions(db_session) == [
        ("demo-careers", 1, "agent", "draft"), ("demo-careers", 2, "agent", "draft")
    ]


async def test_a_retried_draft_stores_one_revision_and_a_new_key_appends_the_next(api_client, db_session, roles):
    first = _data(*await _draft(api_client, RECIPE))

    response, replay = await _draft(api_client, RECIPE)
    second = _data(*await _draft(api_client, RECIPE, key=OTHER_KEY))

    assert _data(response, replay) == first and replay["meta"]["replayed"] is True
    assert second["version"] == 2
    assert [version for _, version, _, _ in await _revisions(db_session)] == [1, 2]


@pytest.mark.parametrize("document", [
    {k: v for k, v in RECIPE.items() if k != "id"},
    {**RECIPE, "listing": {**RECIPE["listing"], "item": None}},
])
async def test_a_draft_without_an_id_or_that_does_not_compile_stores_nothing(api_client, db_session, roles, document):
    error = _refused(*await _draft(api_client, document), "invalid_input")

    assert error["details"]["field"].startswith("document")
    assert await _revisions(db_session) == []
    assert await _count(db_session, CommandReceipt) == 0


async def test_a_draft_that_does_not_compile_names_the_compilers_problems(api_client, db_session, roles):
    elsewhere = {**RECIPE, "listing": {**RECIPE["listing"], "start_url": "https://elsewhere.example/jobs"}}

    error = _refused(*await _draft(api_client, elsewhere), "invalid_input")

    assert any("elsewhere.example" in problem for problem in error["details"]["problems"]), error
    assert await _revisions(db_session) == []


# --------------------------------------------------------------------------- #
# receipts.get
# --------------------------------------------------------------------------- #


async def test_a_receipt_reads_back_what_the_write_answered(api_client, db_session, roles):
    job_id, _ = roles
    written = _data(*await _patch(api_client, job_id, {"if_revision": 0, "notes": "first"}))
    _data(*await _patch(api_client, job_id, {"if_revision": 1, "notes": "moved on"}, key=OTHER_KEY))

    data = _data(*await _receipt(api_client, "pursuits.patch", KEY))

    assert (data["operation"], data["key"], data["contract_version"]) == ("pursuits.patch", KEY, "1.0")
    assert data["result"] == written and data["result"]["notes"] == "first"


async def test_a_receipt_answers_with_writes_off(api_client, db_session, roles):
    job_id, _ = roles
    written = _data(*await _save(api_client, job_id))
    await set_agent_access(db_session, AgentAccessConfig(enabled=True, allow_writes=False))
    await db_session.commit()

    assert _data(*await _receipt(api_client, "pursuits.save", KEY))["result"] == written


async def test_a_receipt_of_another_workspace_principal_or_operation_is_not_found(api_client, db_session, roles):
    job_id, _ = roles
    _data(*await _save(api_client, job_id))
    async with _fresh(db_session) as session:
        for workspace, principal, operation in (("other-workspace", LEGACY_AGENT_PRINCIPAL, "pursuits.patch"),
                                                 (None, "another-assistant", "pursuits.patch")):
            mine = await session.scalar(select(CommandReceipt))
            session.add(CommandReceipt(
                workspace_id=workspace or mine.workspace_id, principal_id=principal, operation=operation,
                idempotency_key=OTHER_KEY, input_hash="0" * 64, contract_version="1.0", result={"leak": True},
            ))
        await session.commit()

    for operation, key in (("pursuits.patch", OTHER_KEY), ("pursuits.patch", KEY), ("recipes.draft.save", KEY)):
        error = _refused(*await _receipt(api_client, operation, key), "not_found")
        assert error["details"] == {"operation": operation, "key": key}


@pytest.mark.parametrize("operation,key,code", [
    ("pursuits.list", KEY, "invalid_input"),
    ("widgets.delete", KEY, "unknown_operation"),
    ("pursuits.patch", "short", "invalid_input"),
    ("Pursuits.Patch", KEY, "invalid_input"),
])
async def test_a_receipt_is_asked_of_a_keyed_write_by_a_well_formed_key(api_client, roles, operation, key, code):
    _refused(*await _receipt(api_client, operation, key), code)


# --------------------------------------------------------------------------- #
# The switches
# --------------------------------------------------------------------------- #


async def test_with_writes_off_every_write_is_refused_and_writes_nothing_while_reads_answer(
    api_client, db_session, roles
):
    job_id, other = roles
    _data(*await _save(api_client, other))  # a pursuit and a receipt to read back
    await set_agent_access(db_session, AgentAccessConfig(enabled=True, allow_writes=False))
    await db_session.commit()
    before = (await _count(db_session, Pursuit), await _count(db_session, CommandReceipt))

    for response, body in (
        await _save(api_client, job_id, key=OTHER_KEY),
        await _patch(api_client, other, {"if_revision": 1, "notes": "x"}, key=OTHER_KEY),
        await _draft(api_client, RECIPE, key=OTHER_KEY),
    ):
        error = _refused(response, body, "writes_disabled")
        assert error["details"] == {"setting": "agent_access.allow_writes"}
        assert outcome("writes_disabled").exit_status == 4

    assert (await _count(db_session, Pursuit), await _count(db_session, CommandReceipt)) == before
    assert (await _pursuit(db_session, other)).notes is None
    assert await _revisions(db_session) == []
    assert _data(*(await _get(api_client, f"/pursuits/{other}")))["revision"] == 1
    assert _data(*await _receipt(api_client, "pursuits.save", KEY))["result"]["opportunity_id"] == other


async def test_with_access_off_the_receipt_read_is_refused_too(api_client, db_session, roles):
    job_id, _ = roles
    _data(*await _save(api_client, job_id))
    await set_agent_access(db_session, AgentAccessConfig(enabled=False, allow_writes=True))
    await db_session.commit()

    _refused(*await _receipt(api_client, "pursuits.save", KEY), "access_disabled")
    _refused(*await _save(api_client, job_id, key=OTHER_KEY), "access_disabled")


async def test_capabilities_lists_the_writes_unavailable_with_writes_off(api_client, db_session, roles):
    await set_agent_access(db_session, AgentAccessConfig(enabled=True, allow_writes=False))
    await db_session.commit()

    listed = {row["operation"]: row for row in _data(*await _get(api_client, "/capabilities"))["operations"]}

    for operation in ("pursuits.save", "pursuits.patch", "recipes.draft.save"):
        assert listed[operation]["availability"] == {"state": "unavailable", "reason": "writes_disabled"}
        assert listed[operation]["idempotency"] == "required_key"
    assert listed["receipts.get"]["availability"] == {"state": "available", "reason": None}


async def _get(api_client, path: str):
    response = await api_client.get(f"{PREFIX}{path}")
    return response, response.json()


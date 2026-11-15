"""An agent write runs once per key, against the revision it read, and keeps a receipt.

The subject is the write path of the agent operation core
(`OperationContext.write`), the receipt store (`tracker/agents/receipts.py`)
and the pursuit revision (`upsert_pursuit`), driven over real ASGI on the
scratch database. The write operation below is defined by this test: the
catalog has no pursuit write yet, and the core is what is under test, so the
route is the smallest one that reaches the real domain writer. The dashboard's
own pursuit route is mounted beside it, so "the person edits in the dashboard"
is the dashboard's real code.
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator
from typing import Annotated, Any

import pytest
import pytest_asyncio
from fastapi import APIRouter, Depends, FastAPI
from httpx import ASGITransport, AsyncClient
from pydantic import Field
from sqlalchemy import func, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.orm.exc import StaleDataError

from tracker.agents.config import AgentAccessConfig, set_agent_access
from tracker.agents.operations import catalog as catalog_module
from tracker.agents.operations.catalog import REGISTERED, Catalog
from tracker.agents.operations.descriptor import EngineEffects, OperationDescriptor, Shape
from tracker.agents.operations.envelope import Envelope, OperationError
from tracker.agents.operations.outcomes import EXIT_CONFLICT, outcome
from tracker.agents.operations.workspace import ensure_workspace_id
from tracker.agents.pursuits import PursuitStage, PursuitUpdate, upsert_pursuit
from tracker.agents.receipts import LEGACY_AGENT_PRINCIPAL, ReceiptKey, lock_key
from tracker.api import agent_operations
from tracker.api.agent_operations import (
    IDEMPOTENCY_KEY_HEADER,
    PREFIX,
    AgentRoute,
    OperationContext,
    admitted,
    operation_route,
)
from tracker.db.models import CommandReceipt, Job, Pursuit, PursuitEvent

OPERATION = "testing.pursuit_patch"
KEY = "idk_" + "a" * 32
#: The route answers this note by failing after its domain write, before commit.
FAIL_AFTER_WRITE = "fail after the write"


class PatchInput(Shape):
    opportunity_id: int = Field(ge=1)
    if_revision: int = Field(ge=0)
    stage: PursuitStage | None = None
    notes: str | None = Field(default=None, max_length=2_000)


class PatchResult(Shape):
    opportunity_id: int
    revision: int
    stage: str
    notes: str | None


PATCH = OperationDescriptor(
    id=OPERATION,
    summary="Change a pursuit's stage or notes against the revision read.",
    input=PatchInput,
    result=PatchResult,
    access="write",
    idempotency="required_key",
    engine_effects=EngineEffects(state_write=True),
    tool_tiers=("full",),
    data_classes=("private_pursuit",),
    expects_revision=True,
)


def _router() -> APIRouter:
    router = APIRouter(route_class=AgentRoute)

    @router.patch(
        f"{PREFIX}/testing/pursuits/{{opportunity_id}}",
        response_model=Envelope[PatchResult],
        openapi_extra=operation_route(PATCH),
    )
    async def patch(op: Annotated[OperationContext, Depends(admitted(PATCH))]) -> Envelope[Any]:
        payload = op.input_as(PatchInput)
        fields = payload.model_dump(exclude_unset=True, exclude={"opportunity_id", "if_revision"})

        async def apply() -> PatchResult:
            try:
                pursuit = await upsert_pursuit(
                    op.session,
                    payload.opportunity_id,
                    PursuitUpdate(**fields),
                    actor=op.actor,
                    expected_revision=payload.if_revision,
                )
            except LookupError:
                raise OperationError("not_found", "No opportunity has this id.") from None
            if payload.notes == FAIL_AFTER_WRITE:
                raise RuntimeError("the operation failed after its write")
            return PatchResult(
                opportunity_id=pursuit.job_id, revision=pursuit.revision, stage=pursuit.stage, notes=pursuit.notes
            )

        return await op.write(apply)

    return router


@pytest_asyncio.fixture
async def client(db_session, monkeypatch) -> AsyncIterator[AsyncClient]:
    """The test operation's route and the dashboard's pursuit route, each
    request on its own session, as the engine serves them."""
    from tracker.api.deps import get_session
    from tracker.api.routers import profile

    monkeypatch.setattr(agent_operations, "CATALOG", Catalog((*REGISTERED, PATCH)))
    monkeypatch.setattr(catalog_module, "CATALOG", agent_operations.CATALOG)
    app = FastAPI()
    app.include_router(_router())
    app.include_router(profile.router)
    factory = async_sessionmaker(db_session.bind, expire_on_commit=False)

    async def request_session() -> AsyncIterator[AsyncSession]:
        async with factory() as session:
            yield session

    app.dependency_overrides[get_session] = request_session
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://127.0.0.1:8010") as http:
        yield http


@pytest_asyncio.fixture
async def job_id(db_session) -> int:
    await set_agent_access(db_session, AgentAccessConfig(enabled=True, allow_writes=True))
    await ensure_workspace_id(db_session)
    job = Job(
        company="openai", req_id="r1", dedupe_key="openai:r1", title="Staff PM",
        url="https://careers.example.test/r1", status="open", level_band="staff",
    )
    db_session.add(job)
    await db_session.commit()
    return job.id


def _fresh(db_session) -> AsyncSession:
    return async_sessionmaker(db_session.bind, expire_on_commit=False)()


async def _agent_patch(client: AsyncClient, job_id: int, body: dict[str, Any], *, key: str | None = KEY):
    headers = {} if key is None else {IDEMPOTENCY_KEY_HEADER: key}
    return await client.patch(f"{PREFIX}/testing/pursuits/{job_id}", json=body, headers=headers)


async def _dashboard_edit(client: AsyncClient, job_id: int, body: dict[str, Any]) -> None:
    response = await client.put(f"/api/jobs/{job_id}/pursuit", json=body)
    assert response.status_code == 200, response.text


async def _state(db_session, job_id: int) -> dict[str, Any]:
    async with _fresh(db_session) as session:
        pursuit = await session.scalar(select(Pursuit).where(Pursuit.job_id == job_id))
        events = (
            await session.execute(
                select(PursuitEvent.actor, PursuitEvent.event_type)
                .join(Pursuit, Pursuit.id == PursuitEvent.pursuit_id)
                .where(Pursuit.job_id == job_id)
                .order_by(PursuitEvent.id)
            )
        ).all()
        receipts = (await session.scalars(select(CommandReceipt).order_by(CommandReceipt.id))).all()
    return {
        "revision": None if pursuit is None else pursuit.revision,
        "notes": None if pursuit is None else pursuit.notes,
        "stage": None if pursuit is None else pursuit.stage,
        "events": [tuple(event) for event in events],
        "receipts": receipts,
    }


# --------------------------------------------------------------------------- #
# The revision: every writer advances it
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_every_write_that_changes_a_pursuit_advances_its_revision(client, db_session, job_id):
    await _dashboard_edit(client, job_id, {"notes": "first"})
    assert (await _state(db_session, job_id))["revision"] == 1
    await _dashboard_edit(client, job_id, {"stage": "applied"})
    assert (await _state(db_session, job_id))["revision"] == 2
    # A write that changes nothing writes nothing, and the revision stays.
    await _dashboard_edit(client, job_id, {"stage": "applied"})
    assert (await _state(db_session, job_id))["revision"] == 2


@pytest.mark.asyncio
async def test_a_write_from_a_stale_copy_of_the_row_fails_instead_of_landing(db_session, job_id):
    """The mapper's UPDATE names the revision it read. A writer that skipped
    the role's lock and wrote from an old copy is refused, not silently
    applied over the newer row."""
    async with _fresh(db_session) as setup:
        await upsert_pursuit(setup, job_id, PursuitUpdate(notes="first"), actor="user")
        await setup.commit()
    async with _fresh(db_session) as stale, _fresh(db_session) as other:
        old = await stale.scalar(select(Pursuit).where(Pursuit.job_id == job_id))
        await stale.commit()
        await upsert_pursuit(other, job_id, PursuitUpdate(notes="the person's"), actor="user")
        await other.commit()
        old.notes = "an old copy's"
        with pytest.raises(StaleDataError):
            await stale.flush()
    state = await _state(db_session, job_id)
    assert (state["notes"], state["revision"]) == ("the person's", 2)


# --------------------------------------------------------------------------- #
# Receipts: replay, conflict, one write
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_an_identical_retry_after_a_lost_reply_returns_the_committed_receipt(client, db_session, job_id):
    await _dashboard_edit(client, job_id, {"notes": "the person's"})  # revision 1
    body = {"if_revision": 1, "stage": "applied"}
    first = await _agent_patch(client, job_id, body)
    assert first.status_code == 200, first.text
    assert first.json()["data"]["revision"] == 2
    # The reply is lost. Meanwhile the person edits, so revision 1 is stale.
    await _dashboard_edit(client, job_id, {"notes": "edited since"})

    retry = await _agent_patch(client, job_id, body)

    assert retry.status_code == 200, retry.text
    envelope = retry.json()
    assert envelope["ok"] is True
    # The historical outcome, revision 1 -> 2, not the row as it is now.
    assert envelope["data"] == first.json()["data"]
    assert envelope["meta"]["replayed"] is True
    assert envelope["meta"]["idempotency_key"] == KEY
    assert first.json()["meta"] == {**first.json()["meta"], "replayed": False, "idempotency_key": KEY}
    state = await _state(db_session, job_id)
    assert state["revision"] == 3
    assert state["notes"] == "edited since" and state["stage"] == "applied"
    assert state["events"] == [("user", "created"), ("agent", "updated"), ("user", "updated")]
    (receipt,) = state["receipts"]
    assert (receipt.principal_id, receipt.operation, receipt.idempotency_key) == (
        LEGACY_AGENT_PRINCIPAL, OPERATION, KEY,
    )


@pytest.mark.asyncio
async def test_a_different_request_under_a_used_key_conflicts_and_writes_nothing(client, db_session, job_id):
    first = await _agent_patch(client, job_id, {"if_revision": 0, "notes": "a"})
    assert first.status_code == 200, first.text

    for changed in (
        {"if_revision": 0, "notes": "b"},  # another value
        {"if_revision": 0, "notes": "a", "stage": "saved"},  # one more field, even a no-op one
        {"if_revision": 0},  # a field fewer
    ):
        response = await _agent_patch(client, job_id, changed)
        assert response.status_code == 409, response.text
        error = response.json()["error"]
        assert error["code"] == "idempotency_conflict"
        assert outcome(error["code"]).exit_status == EXIT_CONFLICT
        assert response.json()["meta"]["idempotency_key"] == KEY

    state = await _state(db_session, job_id)
    assert (state["notes"], state["revision"], len(state["receipts"])) == ("a", 1, 1)
    # The same request in another key order and spacing is the same request.
    again = await client.patch(
        f"{PREFIX}/testing/pursuits/{job_id}",
        content=b'{ "notes" : "a",  "if_revision" : 0 }',
        headers={IDEMPOTENCY_KEY_HEADER: KEY, "Content-Type": "application/json"},
    )
    assert again.status_code == 200 and again.json()["meta"]["replayed"] is True


@pytest.mark.asyncio
async def test_concurrent_identical_requests_make_one_write(client, db_session, job_id):
    """Five identical requests queue on the key's lock, held here until all
    five wait, so they truly overlap: one writes, four replay its receipt."""
    from sqlalchemy.ext.asyncio import AsyncEngine

    workspace = await ensure_workspace_id(db_session)
    await db_session.commit()
    body = {"if_revision": 0, "stage": "researching"}
    engine: AsyncEngine = db_session.bind
    async with _fresh(db_session) as holder:
        await lock_key(holder, ReceiptKey(workspace, LEGACY_AGENT_PRINCIPAL, OPERATION, KEY))
        tasks = [asyncio.create_task(_agent_patch(client, job_id, body)) for _ in range(5)]
        await _until_waiting(engine, 5)
        assert not any(task.done() for task in tasks)
        await holder.rollback()
    responses = await asyncio.gather(*tasks)

    assert all(response.status_code == 200 for response in responses), [r.text for r in responses]
    replayed = sorted(response.json()["meta"]["replayed"] for response in responses)
    assert replayed == [False, True, True, True, True]
    assert len({str(response.json()["data"]) for response in responses}) == 1
    state = await _state(db_session, job_id)
    assert state["revision"] == 1
    assert state["events"] == [("agent", "created")]
    assert len(state["receipts"]) == 1


async def _until_waiting(engine, count: int, timeout: float = 10.0) -> None:
    query = text(
        "SELECT count(*) FROM pg_locks l JOIN pg_stat_activity a ON a.pid = l.pid"
        " WHERE NOT l.granted AND l.locktype = 'advisory' AND a.datname = current_database()"
    )
    async with asyncio.timeout(timeout), engine.connect() as conn:
        while True:
            waiting = await conn.scalar(query)
            await conn.rollback()
            if waiting >= count:
                return
            await asyncio.sleep(0.01)


@pytest.mark.asyncio
async def test_a_dashboard_edit_between_the_agents_read_and_write_is_a_revision_conflict(
    client, db_session, job_id
):
    await _dashboard_edit(client, job_id, {"notes": "draft"})
    read_revision = (await _state(db_session, job_id))["revision"]
    await _dashboard_edit(client, job_id, {"notes": "the person's newer notes"})

    response = await _agent_patch(client, job_id, {"if_revision": read_revision, "notes": "the agent's notes"})

    assert response.status_code == 409, response.text
    envelope = response.json()
    assert envelope["error"]["code"] == "revision_conflict"
    assert outcome("revision_conflict").exit_status == EXIT_CONFLICT == 6
    assert envelope["error"]["details"] == {"expected_revision": read_revision, "current_revision": read_revision + 1}
    assert envelope["meta"]["idempotency_key"] == KEY
    state = await _state(db_session, job_id)
    assert state["notes"] == "the person's newer notes"
    assert state["receipts"] == []
    # The refusal did not use the key up: a new decision under it can run.
    retry = await _agent_patch(client, job_id, {"if_revision": read_revision + 1, "notes": "the agent's notes"})
    assert retry.status_code == 200 and retry.json()["meta"]["replayed"] is False


@pytest.mark.asyncio
async def test_a_new_pursuit_is_revision_zero_to_its_first_writer(client, db_session, job_id):
    created = await _agent_patch(client, job_id, {"if_revision": 0, "stage": "saved"})
    assert created.status_code == 200 and created.json()["data"]["revision"] == 1
    late = await _agent_patch(client, job_id, {"if_revision": 0, "notes": "x"}, key="idk_" + "b" * 32)
    assert late.status_code == 409
    assert late.json()["error"]["details"] == {"expected_revision": 0, "current_revision": 1}


@pytest.mark.asyncio
async def test_a_rolled_back_write_leaves_no_receipt_and_no_write(client, db_session, job_id):
    await _dashboard_edit(client, job_id, {"notes": "kept"})

    response = await _agent_patch(client, job_id, {"if_revision": 1, "notes": FAIL_AFTER_WRITE})

    assert response.status_code == 500
    assert response.json()["error"]["code"] == "internal_error"
    assert response.json()["meta"]["idempotency_key"] == KEY
    state = await _state(db_session, job_id)
    assert (state["notes"], state["revision"]) == ("kept", 1)
    assert state["events"] == [("user", "created")]
    assert state["receipts"] == []
    # Nothing was recorded under the key, so a different request under it runs.
    retry = await _agent_patch(client, job_id, {"if_revision": 1, "notes": "landed"})
    assert retry.status_code == 200 and retry.json()["meta"]["replayed"] is False


@pytest.mark.asyncio
async def test_the_receipt_key_is_unique_in_the_table_itself(db_session, job_id):
    """The final guard behind the lock: two receipts for one key cannot both commit."""
    workspace = await ensure_workspace_id(db_session)
    row = {
        "workspace_id": workspace, "principal_id": "agent", "operation": OPERATION, "idempotency_key": KEY,
        "input_hash": "0" * 64, "contract_version": "1.0", "result": {},
    }
    db_session.add(CommandReceipt(**row))
    await db_session.commit()
    db_session.add(CommandReceipt(**{**row, "input_hash": "1" * 64}))
    with pytest.raises(IntegrityError):
        await db_session.commit()
    await db_session.rollback()


# --------------------------------------------------------------------------- #
# What a caller cannot do
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    "extra",
    [{"actor": "user"}, {"principal_id": "user"}, {"source": "dashboard"}, {"provenance": "user"}],
    ids=["actor", "principal", "source", "provenance"],
)
@pytest.mark.asyncio
async def test_a_caller_cannot_supply_its_actor_or_provenance(client, db_session, job_id, extra):
    response = await _agent_patch(client, job_id, {"if_revision": 0, "notes": "x", **extra})
    assert response.status_code == 422, response.text
    assert response.json()["error"]["code"] == "invalid_input"
    state = await _state(db_session, job_id)
    assert state["revision"] is None and state["receipts"] == []

    # A header naming another principal is not read: the write is the agent's.
    written = await client.patch(
        f"{PREFIX}/testing/pursuits/{job_id}",
        json={"if_revision": 0, "notes": "x"},
        headers={IDEMPOTENCY_KEY_HEADER: KEY, "X-RoleBand-Principal": "user", "X-RoleBand-Actor": "user"},
    )
    assert written.status_code == 200, written.text
    state = await _state(db_session, job_id)
    assert state["events"] == [("agent", "created")]
    assert state["receipts"][0].principal_id == LEGACY_AGENT_PRINCIPAL


@pytest.mark.asyncio
@pytest.mark.parametrize("key", [None, "short", "has space in it", "x" * 129, "-leading-dash"])
async def test_a_write_without_a_well_formed_key_is_refused_before_anything(client, db_session, job_id, key):
    response = await _agent_patch(client, job_id, {"if_revision": 0, "notes": "x"}, key=key)
    assert response.status_code == 422
    envelope = response.json()
    assert envelope["error"]["code"] == "invalid_input"
    assert envelope["error"]["details"] == {"header": IDEMPOTENCY_KEY_HEADER}
    assert envelope["meta"]["idempotency_key"] is None
    assert (await _state(db_session, job_id))["revision"] is None


@pytest.mark.parametrize(
    ("content", "reason"),
    [
        (b"[1, 2]", "not an object"),
        (b'{"notes": "a", "notes": "b", "if_revision": 0}', "a repeated key"),
        (b"{not json", "malformed"),
        (b'{"opportunity_id": 999, "if_revision": 0}', "a path field given twice"),
    ],
)
@pytest.mark.asyncio
async def test_a_body_that_is_not_one_unambiguous_object_is_invalid_input(client, db_session, job_id, content, reason):
    response = await client.patch(
        f"{PREFIX}/testing/pursuits/{job_id}",
        content=content,
        headers={IDEMPOTENCY_KEY_HEADER: KEY, "Content-Type": "application/json"},
    )
    assert response.status_code == 422, reason
    assert response.json()["error"]["code"] == "invalid_input"
    assert (await _state(db_session, job_id))["receipts"] == []


@pytest.mark.asyncio
async def test_a_refused_request_does_not_use_up_its_key(client, db_session, job_id):
    invalid = await _agent_patch(client, job_id, {"if_revision": -1, "notes": "x"})
    assert invalid.status_code == 422
    valid = await _agent_patch(client, job_id, {"if_revision": 0, "notes": "y"})
    assert valid.status_code == 200 and valid.json()["meta"]["replayed"] is False


@pytest.mark.asyncio
async def test_switching_writes_off_stops_a_replay_too(client, db_session, job_id):
    first = await _agent_patch(client, job_id, {"if_revision": 0, "notes": "x"})
    assert first.status_code == 200
    await set_agent_access(db_session, AgentAccessConfig(enabled=True, allow_writes=False))
    await db_session.commit()
    replay = await _agent_patch(client, job_id, {"if_revision": 0, "notes": "x"})
    assert replay.status_code == 403
    assert replay.json()["error"]["code"] == "writes_disabled"
    assert replay.json()["data"] is None


@pytest.mark.asyncio
async def test_receipts_are_kept_per_workspace(client, db_session, job_id):
    """A copy of the database under another workspace id replays nothing the
    original recorded: the same key there is a new request."""
    first = await _agent_patch(client, job_id, {"if_revision": 0, "notes": "x"})
    assert first.status_code == 200
    await db_session.execute(text("UPDATE workspace_identity SET workspace_id = 'ws_' || repeat('c', 32)"))
    await db_session.commit()
    elsewhere = await _agent_patch(client, job_id, {"if_revision": 1, "notes": "y"})
    assert elsewhere.status_code == 200 and elsewhere.json()["meta"]["replayed"] is False
    async with _fresh(db_session) as session:
        assert await session.scalar(select(func.count()).select_from(CommandReceipt)) == 2


# --------------------------------------------------------------------------- #
# What a write descriptor declares
# --------------------------------------------------------------------------- #


class _NoRevision(Shape):
    opportunity_id: int


class _OptionalRevision(Shape):
    opportunity_id: int
    if_revision: int | None = None


@pytest.mark.parametrize(
    ("overrides", "reason"),
    [
        ({"input": _NoRevision}, "takes a required int 'if_revision'"),
        ({"input": _OptionalRevision}, "takes a required int 'if_revision'"),
        (
            {"access": "read", "idempotency": "read", "engine_effects": EngineEffects()},
            "only a write states the revision",
        ),
    ],
)
def test_a_write_that_expects_a_revision_must_take_one(overrides, reason):
    fields = {
        "id": "testing.other", "summary": "s", "input": PatchInput, "result": PatchResult, "access": "write",
        "idempotency": "required_key", "engine_effects": EngineEffects(state_write=True),
        "tool_tiers": ("full",), "expects_revision": True,
    }
    with pytest.raises(ValueError, match=reason):
        OperationDescriptor(**{**fields, **overrides})


def test_a_write_route_documents_its_body_and_its_key_header(monkeypatch):
    monkeypatch.setattr(agent_operations, "CATALOG", Catalog((*REGISTERED, PATCH)))
    app = FastAPI()
    app.include_router(_router())
    operation = app.openapi()["paths"][f"{PREFIX}/testing/pursuits/{{opportunity_id}}"]["patch"]
    parameters = {(item["name"], item["in"], item["required"]) for item in operation["parameters"]}
    assert parameters == {("opportunity_id", "path", True), (IDEMPOTENCY_KEY_HEADER, "header", True)}
    body = operation["requestBody"]["content"]["application/json"]["schema"]
    assert set(body["properties"]) == {"if_revision", "stage", "notes"}
    assert body["required"] == ["if_revision"]


class _Window(Shape):
    days: int = Field(ge=1)


class _NestedInput(Shape):
    opportunity_id: int
    if_revision: int
    window: _Window
    note: str | None = None


NESTED = OperationDescriptor(
    id="testing.nested", summary="s", input=_NestedInput, result=PatchResult, access="write",
    idempotency="required_key", engine_effects=EngineEffects(state_write=True), tool_tiers=("full",),
    expects_revision=True,
)


def test_a_nested_input_keeps_every_field_in_the_documented_body(monkeypatch):
    monkeypatch.setattr(agent_operations, "CATALOG", Catalog((*REGISTERED, NESTED)))
    router = APIRouter(route_class=AgentRoute)

    @router.post(f"{PREFIX}/testing/nested/{{opportunity_id}}", openapi_extra=operation_route(NESTED))
    async def handler(op: Annotated[OperationContext, Depends(admitted(NESTED))]) -> None:
        raise AssertionError("not called")

    app = FastAPI()
    app.include_router(router)
    schema = app.openapi()["paths"][f"{PREFIX}/testing/nested/{{opportunity_id}}"]["post"]["requestBody"]
    body = schema["content"]["application/json"]["schema"]
    assert set(body["properties"]) == {"if_revision", "window", "note"}
    assert sorted(body["required"]) == ["if_revision", "window"]
    assert body["properties"]["window"]["properties"]["days"]["minimum"] == 1
    assert "$ref" not in json.dumps(body) and "$defs" not in json.dumps(body)


@pytest.mark.asyncio
async def test_a_body_past_the_bound_is_refused_unread(client, db_session, job_id):
    response = await client.patch(
        f"{PREFIX}/testing/pursuits/{job_id}",
        content=b'{"if_revision": 0, "notes": "' + b"x" * (agent_operations.MAX_BODY_BYTES + 1) + b'"}',
        headers={IDEMPOTENCY_KEY_HEADER: KEY, "Content-Type": "application/json"},
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "invalid_input"
    assert (await _state(db_session, job_id))["revision"] is None

"""The agent operation core and its routes under `/api/agent/v1/`.

Descriptors refuse metadata that contradicts itself, the catalog and the
routes stay one-to-one, the person's two switches admit or refuse every
operation, every answer is one envelope whose code carries the contract's
exit status, and the workspace id is the engine's durable row, not the engine
session. The routes run over real ASGI on the scratch database.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass

import pytest
from fastapi.routing import APIRoute
from pydantic import BaseModel
from sqlalchemy import select

from scripts.export_agent_operations import COMMITTED, render
from tracker.agents.config import AgentAccessConfig, set_agent_access
from tracker.agents.operations import meta
from tracker.agents.operations.catalog import CATALOG, REGISTERED, Catalog, bundled_index
from tracker.agents.operations.descriptor import (
    OPERATION_ID,
    Availability,
    EngineEffects,
    NoInput,
    OperationDescriptor,
    Shape,
)
from tracker.agents.operations.envelope import OperationError
from tracker.agents.operations.outcomes import CONTRACT_VERSION, OUTCOMES, compatible, outcome
from tracker.agents.operations.policy import admit, availability
from tracker.agents.operations.workspace import ensure_workspace_id, get_workspace_id
from tracker.api.agent_operations import PREFIX, REQUEST_ID_HEADER, AgentRoute
from tracker.db.models import WorkspaceIdentity

ENVELOPE_KEYS = {"contract_version", "request_id", "workspace_id", "operation", "ok", "data", "meta", "warnings", "error"}
WORKSPACE = re.compile(r"^ws_[0-9a-f]{32}$")

#: The process outcome table of the command contract, by category. Written out
#: here, not read from `outcomes.py`, so a change to the table must change this.
CONTRACT_EXITS = {
    "internal_error": 1,
    "invalid_arguments": 2,
    "invalid_input": 2,
    "unknown_operation": 2,
    "unsupported_operation": 2,
    "context_required": 2,
    "context_not_found": 2,
    "context_invalid": 2,
    "engine_unavailable": 3,
    "engine_not_ready": 3,
    "transport_error": 3,
    "transport_unverified": 3,
    "workspace_mismatch": 3,
    "access_disabled": 4,
    "writes_disabled": 4,
    "not_found": 5,
    "revision_conflict": 6,
    "idempotency_conflict": 6,
    "approval_required": 7,
    "deadline_exceeded": 8,
    "rate_limited": 8,
    "partial_result": 9,
    "operation_cancelled": 9,
    "contract_incompatible": 10,
    "interrupted": 130,
}


# --------------------------------------------------------------------------- #
# The outcome table
# --------------------------------------------------------------------------- #


def test_every_code_has_the_contracts_exit_status():
    assert {code: entry.exit_status for code, entry in OUTCOMES.items()} == CONTRACT_EXITS


def test_an_unknown_code_is_an_internal_failure_not_a_success():
    assert outcome("no_such_code").exit_status == 1
    assert outcome("no_such_code").retryable is False


def test_an_error_with_a_code_outside_the_table_cannot_be_raised():
    with pytest.raises(ValueError, match="not an error code"):
        OperationError("made_up", "x")


def test_refusals_are_never_retryable_and_unavailability_is():
    assert not outcome("access_disabled").retryable
    assert not outcome("writes_disabled").retryable
    assert outcome("engine_unavailable").retryable
    # Unverified transport stops automatic retry.
    assert not outcome("transport_unverified").retryable


@pytest.mark.parametrize(
    ("version", "ok"),
    [("1.0", True), ("1.7", True), ("2.0", False), ("1", False), ("1.x", False), (None, False), (1.0, False)],
)
def test_only_the_same_major_contract_is_compatible(version, ok):
    assert compatible(version) is ok


# --------------------------------------------------------------------------- #
# Descriptors and the catalog
# --------------------------------------------------------------------------- #


class _Result(Shape):
    value: int


class _Loose(BaseModel):
    value: int = 0


def _descriptor(**overrides) -> OperationDescriptor:
    fields = dict(
        id="widgets.list", summary="List widgets.", input=NoInput, result=_Result, access="read",
        idempotency="read", engine_effects=EngineEffects(), tool_tiers=("full",),
    )
    fields.update(overrides)
    return OperationDescriptor(**fields)


def test_a_well_formed_descriptor_is_accepted():
    assert _descriptor().required_scopes == ("agent_access.enabled",)
    write = _descriptor(access="write", idempotency="required_key", engine_effects=EngineEffects(state_write=True))
    assert write.required_scopes == ("agent_access.enabled", "agent_access.allow_writes")


@pytest.mark.parametrize(
    ("overrides", "reason"),
    [
        ({"id": "Widgets.List"}, "lowercase"),
        ({"id": "widgets..list"}, "lowercase"),
        ({"id": "widgets/list"}, "lowercase"),
        ({"engine_effects": EngineEffects(state_write=True)}, "needs write access"),
        ({"engine_effects": EngineEffects(external_action=True)}, "needs write access"),
        ({"access": "write", "idempotency": "read"}, "declares its idempotency key"),
        ({"idempotency": "required_key"}, "idempotent as a read"),
        ({"tool_tiers": ()}, "at least one tool tier"),
        ({"tool_tiers": ("small", "small")}, "repeats"),
        ({"version": "2.0"}, "1.x contract version"),
        ({"input": _Loose}, "refuse unknown keys"),
    ],
)
def test_a_descriptor_that_contradicts_itself_is_refused(overrides, reason):
    with pytest.raises(ValueError, match=reason):
        _descriptor(**overrides)


def test_an_operation_cannot_be_registered_twice():
    with pytest.raises(ValueError, match="registered twice"):
        Catalog([_descriptor(), _descriptor()])


def test_the_catalog_lists_the_handshake_operations_in_every_tier():
    assert [descriptor.id for descriptor in CATALOG] == ["capabilities", "describe", "status"]
    for tier in ("small", "standard", "full"):
        assert {descriptor.id for descriptor in CATALOG.in_tier(tier)} == {"capabilities", "describe", "status"}
    assert len(REGISTERED) == 3


def test_a_tier_filter_leaves_out_operations_of_other_tiers():
    catalog = Catalog([_descriptor(), _descriptor(id="widgets.get", tool_tiers=("small", "full"))])
    assert [d.id for d in catalog.in_tier("small")] == ["widgets.get"]
    assert [d.id for d in catalog.in_tier(None)] == ["widgets.get", "widgets.list"]


def _text_fields(schema: dict) -> list[tuple[str, dict]]:
    """Every string or list-of-strings property in a schema and its $defs."""
    out = []
    for model_name, model in [("", schema), *schema.get("$defs", {}).items()]:
        for field_name, prop in (model.get("properties") or {}).items():
            options = [prop, *prop.get("anyOf", [])]
            items = [option.get("items") or {} for option in options if option.get("type") == "array"]
            if any(option.get("type") == "string" or "enum" in option for option in options) or any(
                item.get("type") == "string" or "enum" in item for item in items
            ):
                out.append((f"{model_name or schema.get('title')}.{field_name}", prop))
    return out


@pytest.mark.parametrize("descriptor", REGISTERED, ids=lambda descriptor: descriptor.id)
def test_every_text_field_an_operation_answers_declares_its_text_class(descriptor):
    fields = _text_fields(descriptor.result.model_json_schema())
    assert fields, "the walk found no text fields: it no longer reads this schema"
    assert [name for name, prop in fields if "x-text" not in prop] == []


def test_availability_is_only_unknown_offline_and_reasoned_when_not_available():
    with pytest.raises(ValueError):
        Availability("available", "why")
    with pytest.raises(ValueError):
        Availability("unavailable")


def test_the_clients_bundled_index_is_the_catalog():
    assert COMMITTED.read_text(encoding="utf-8") == render(), (
        "tracker/cli/operations.json is stale: run `.venv/bin/python -m scripts.export_agent_operations`"
    )
    index = bundled_index()
    assert index["contract_version"] == CONTRACT_VERSION
    for entry in index["operations"]:
        # Bundled metadata cannot know the person's switches.
        assert entry["metadata_source"] == "bundled"
        assert entry["availability"] == {"state": "unknown", "reason": "offline"}


def test_the_describe_input_takes_only_an_operation_id():
    pattern = meta.DescribeInput.model_json_schema()["properties"]["operation"]["pattern"]
    assert pattern == OPERATION_ID
    with pytest.raises(ValueError):
        meta.DescribeInput(operation="a/../b")
    with pytest.raises(ValueError):
        meta.DescribeInput(operation="status", extra="x")


# --------------------------------------------------------------------------- #
# Policy on the two switches
# --------------------------------------------------------------------------- #


@dataclass
class Switches:
    enabled: bool
    allow_writes: bool


READ = _descriptor()
WRITE = _descriptor(id="widgets.save", access="write", idempotency="required_key",
                    engine_effects=EngineEffects(state_write=True))


@pytest.mark.parametrize(
    ("switches", "read", "write"),
    [
        (Switches(False, False), "access_disabled", "access_disabled"),
        # A stored allow_writes without enabled admits nothing.
        (Switches(False, True), "access_disabled", "access_disabled"),
        (Switches(True, False), None, "writes_disabled"),
        (Switches(True, True), None, None),
    ],
)
def test_reads_need_enabled_and_writes_need_allow_writes(switches, read, write):
    for descriptor, refusal in ((READ, read), (WRITE, write)):
        if refusal is None:
            admit(descriptor, switches)
            assert availability(descriptor, switches).state == "available"
        else:
            with pytest.raises(OperationError) as caught:
                admit(descriptor, switches)
            assert caught.value.code == refusal
            assert outcome(refusal).exit_status == 4
            assert availability(descriptor, switches) == Availability("unavailable", refusal)


# --------------------------------------------------------------------------- #
# Routes
# --------------------------------------------------------------------------- #


def _agent_routes() -> list[APIRoute]:
    from tracker.api.app import app

    return [route for route in app.routes if isinstance(route, APIRoute) and route.path.startswith(PREFIX)]


def test_every_operation_has_exactly_one_explicit_route_and_no_route_dispatches():
    routes = _agent_routes()
    assert all(isinstance(route, AgentRoute) for route in routes)
    operations = [route.openapi_extra["x-operation"] for route in routes]
    assert sorted(operations) == sorted(descriptor.id for descriptor in CATALOG)
    for route in routes:
        # A path converter that swallows slashes would let one route serve any name.
        assert ":path}" not in route.path, route.path
        assert route.methods == {"GET"}, f"{route.path}: the handshake operations are reads"


def test_an_agent_route_that_names_no_operation_cannot_be_built():
    from fastapi import APIRouter

    router = APIRouter(route_class=AgentRoute)
    with pytest.raises(ValueError, match="names no catalogued operation"):
        router.add_api_route(f"{PREFIX}/nothing", lambda: None)
    with pytest.raises(ValueError, match="names no catalogued operation"):
        router.add_api_route(f"{PREFIX}/unknown", lambda: None, openapi_extra={"x-operation": "no.such"})


def _example_path(route: APIRoute) -> str:
    return route.path.replace("{operation}", "status")


async def _enable(db_session, *, enabled: bool = True, allow_writes: bool = False) -> None:
    await set_agent_access(db_session, AgentAccessConfig(enabled=enabled, allow_writes=allow_writes))
    await ensure_workspace_id(db_session)
    await db_session.commit()


def _assert_envelope(body: dict, *, operation: str, ok: bool) -> None:
    assert set(body) == ENVELOPE_KEYS
    assert body["contract_version"] == CONTRACT_VERSION
    assert body["operation"] == operation
    assert body["ok"] is ok
    if ok:
        assert body["error"] is None and body["data"] is not None
    else:
        assert body["data"] is None
        assert set(body["error"]) == {"code", "message", "retryable", "details", "next_actions"}


@pytest.mark.asyncio
@pytest.mark.parametrize("enabled", [False, None], ids=["switched-off", "never-set"])
async def test_a_switched_off_connection_is_refused_every_operation(api_client, db_session, enabled):
    if enabled is not None:
        await _enable(db_session, enabled=False, allow_writes=True)
    else:
        await ensure_workspace_id(db_session)
        await db_session.commit()
    routes = _agent_routes()
    assert routes
    for route in routes:
        response = await api_client.get(_example_path(route))
        body = response.json()
        assert response.status_code == 403, route.path
        _assert_envelope(body, operation=route.openapi_extra["x-operation"], ok=False)
        assert body["error"]["code"] == "access_disabled"
        # Nothing about the workspace before the switch admits the caller.
        assert body["workspace_id"] is None


@pytest.mark.asyncio
async def test_status_names_the_durable_workspace_and_a_separate_engine_session(api_client, db_session):
    await _enable(db_session)
    stored = (await db_session.execute(select(WorkspaceIdentity.workspace_id))).scalar_one()

    response = await api_client.get(f"{PREFIX}/status")
    body = response.json()

    assert response.status_code == 200
    _assert_envelope(body, operation="status", ok=True)
    data = body["data"]
    assert body["workspace_id"] == data["workspace_id"] == stored
    assert WORKSPACE.fullmatch(stored)
    assert data["engine_session_id"] and data["engine_session_id"] != stored
    assert data["trust"] == {"mode": "local_loopback", "verified": False}
    assert data["access"] == {"enabled": True, "allow_writes": False}
    assert data["contract_version"] == CONTRACT_VERSION
    assert body["meta"]["data_classes"] == []


@pytest.mark.asyncio
async def test_a_request_id_is_echoed_only_when_it_is_a_plain_token(api_client, db_session):
    await _enable(db_session)
    echoed = await api_client.get(f"{PREFIX}/status", headers={REQUEST_ID_HEADER: "req_agent_42"})
    assert echoed.json()["request_id"] == "req_agent_42"
    replaced = await api_client.get(f"{PREFIX}/status", headers={REQUEST_ID_HEADER: "x\u001b[2J; rm"})
    assert replaced.json()["request_id"].startswith("req_")
    assert "\u001b" not in replaced.json()["request_id"]


@pytest.mark.asyncio
async def test_capabilities_lists_each_operation_with_live_availability(api_client, db_session):
    await _enable(db_session)
    body = (await api_client.get(f"{PREFIX}/capabilities")).json()
    _assert_envelope(body, operation="capabilities", ok=True)
    data = body["data"]
    assert data["metadata_source"] == "engine"
    assert data["engine_version"]
    assert data["supported_contract_versions"] == [CONTRACT_VERSION]
    assert [entry["operation"] for entry in data["operations"]] == ["capabilities", "describe", "status"]
    for entry in data["operations"]:
        assert entry["availability"] == {"state": "available", "reason": None}
        assert set(entry["engine_effects"]) == {"state_write", "outbound_network", "model_egress", "external_action"}


@pytest.mark.asyncio
async def test_capabilities_filters_by_tier_and_refuses_unknown_input(api_client, db_session):
    await _enable(db_session)
    small = (await api_client.get(f"{PREFIX}/capabilities", params={"tier": "small"})).json()
    assert {entry["operation"] for entry in small["data"]["operations"]} == {"capabilities", "describe", "status"}

    for params, field in (({"tier": "huge"}, "tier"), ({"verbose": "1"}, "verbose")):
        response = await api_client.get(f"{PREFIX}/capabilities", params=params)
        body = response.json()
        assert response.status_code == 422
        _assert_envelope(body, operation="capabilities", ok=False)
        assert body["error"]["code"] == "invalid_input"
        assert [error["location"] for error in body["error"]["details"]["errors"]] == [[field]]
        # The value sent is not repeated back.
        assert "huge" not in json.dumps(body)


@pytest.mark.asyncio
async def test_describe_returns_one_operation_in_full_from_the_engine(api_client, db_session):
    await _enable(db_session)
    body = (await api_client.get(f"{PREFIX}/operations/capabilities")).json()
    _assert_envelope(body, operation="describe", ok=True)
    data = body["data"]
    assert data["operation"] == "capabilities"
    assert data["metadata_source"] == "engine"
    assert data["availability"] == {"state": "available", "reason": None}
    assert data["input_schema"]["additionalProperties"] is False
    assert "tier" in data["input_schema"]["properties"]
    assert data["output_schema"]["title"] == "CapabilitiesResult"
    # The reference is a JSON pointer into the described operation itself.
    pointer = data["output_schema_ref"]
    assert pointer.startswith("#/")
    target = data
    for token in pointer[2:].split("/"):
        target = target[token]
    assert target == data["output_schema"]
    assert data["required_scopes"] == ["agent_access.enabled"]


@pytest.mark.asyncio
async def test_describe_of_an_unknown_operation_points_at_capabilities(api_client, db_session):
    await _enable(db_session)
    response = await api_client.get(f"{PREFIX}/operations/opportunities.search")
    body = response.json()
    assert response.status_code == 404
    _assert_envelope(body, operation="describe", ok=False)
    assert body["error"]["code"] == "unknown_operation"
    assert body["error"]["next_actions"] == [{"operation": "capabilities", "arguments": {}}]
    # Admitted, so the workspace is named even on a failure.
    assert WORKSPACE.fullmatch(body["workspace_id"])


@pytest.mark.asyncio
async def test_an_operation_id_outside_the_rule_is_invalid_input(api_client, db_session):
    await _enable(db_session)
    body = (await api_client.get(f"{PREFIX}/operations/Status")).json()
    assert body["error"]["code"] == "invalid_input"


@pytest.mark.asyncio
async def test_an_unexpected_failure_is_an_internal_error_envelope(api_client, db_session, monkeypatch):
    await _enable(db_session)

    def broken(_tier):
        raise RuntimeError("boom")

    monkeypatch.setattr(CATALOG, "in_tier", broken)
    response = await api_client.get(f"{PREFIX}/capabilities")
    body = response.json()
    assert response.status_code == 500
    _assert_envelope(body, operation="capabilities", ok=False)
    assert body["error"]["code"] == "internal_error"
    assert "boom" not in json.dumps(body)


@pytest.mark.asyncio
async def test_a_database_without_its_workspace_row_answers_not_ready(api_client, db_session):
    await set_agent_access(db_session, AgentAccessConfig(enabled=True, allow_writes=False))
    await db_session.commit()
    response = await api_client.get(f"{PREFIX}/status")
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "engine_not_ready"


# --------------------------------------------------------------------------- #
# The workspace identity
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_the_workspace_id_is_made_once_and_never_replaced(db_session):
    assert await get_workspace_id(db_session) is None
    first = await ensure_workspace_id(db_session)
    await db_session.commit()
    second = await ensure_workspace_id(db_session)
    await db_session.commit()
    assert first == second
    assert WORKSPACE.fullmatch(first)
    rows = (await db_session.execute(select(WorkspaceIdentity))).scalars().all()
    assert len(rows) == 1


@pytest.mark.asyncio
async def test_the_table_refuses_a_second_or_malformed_identity(db_session):
    from sqlalchemy import text
    from sqlalchemy.exc import IntegrityError

    await ensure_workspace_id(db_session)
    await db_session.commit()
    for statement in (
        "INSERT INTO workspace_identity (workspace_id) VALUES ('ws_" + "0" * 32 + "')",
        "INSERT INTO workspace_identity (singleton, workspace_id) VALUES (false, 'ws_" + "1" * 32 + "')",
    ):
        with pytest.raises(IntegrityError):
            await db_session.execute(text(statement))
        await db_session.rollback()
    await db_session.execute(text("DELETE FROM workspace_identity"))
    with pytest.raises(IntegrityError):
        await db_session.execute(text("INSERT INTO workspace_identity (workspace_id) VALUES ('rb_example')"))
    await db_session.rollback()

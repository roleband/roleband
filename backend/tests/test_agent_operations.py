"""The agent operation core and its routes under `/api/agent/v1/`.

Descriptors refuse metadata that contradicts itself, the catalog and the
routes stay one-to-one, the person's two switches admit or refuse every
operation, every answer is one envelope whose code carries the contract's
exit status, and the workspace id is the engine's durable row, not the engine
session. The routes run over real ASGI on the scratch database.
"""

from __future__ import annotations

import dataclasses
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
from tracker.agents.operations.index import first_sentence
from tracker.agents.operations.outcomes import CONTRACT_VERSION, OUTCOMES, compatible, outcome
from tracker.agents.operations.policy import admit, availability, shared, withheld
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
    "unsupported_host": 2,
    "engine_unavailable": 3,
    "engine_not_ready": 3,
    "transport_error": 3,
    "transport_unverified": 3,
    "workspace_mismatch": 3,
    "access_disabled": 4,
    "writes_disabled": 4,
    "category_disabled": 4,
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
    assert not outcome("category_disabled").retryable
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
    listed = [descriptor.id for descriptor in CATALOG]
    assert listed == sorted(listed)
    assert len(listed) == len(REGISTERED)
    for tier in ("small", "standard", "full"):
        assert {"capabilities", "describe", "status"} <= {descriptor.id for descriptor in CATALOG.in_tier(tier)}


def test_a_tier_filter_leaves_out_operations_of_other_tiers():
    catalog = Catalog([_descriptor(), _descriptor(id="widgets.get", tool_tiers=("small", "full"))])
    assert [d.id for d in catalog.in_tier("small")] == ["widgets.get"]
    assert [d.id for d in catalog.in_tier(None)] == ["widgets.get", "widgets.list"]


#: String formats that carry a date or a time, never text a person reads.
_TIME_FORMATS = {"date", "date-time", "time", "duration"}


def _is_text(option: dict) -> bool:
    if "enum" in option:
        return True
    return option.get("type") == "string" and option.get("format") not in _TIME_FORMATS


def _text_fields(schema: dict) -> list[tuple[str, dict]]:
    """Every string or list-of-strings property in a schema and its $defs."""
    out = []
    for model_name, model in [("", schema), *schema.get("$defs", {}).items()]:
        for field_name, prop in (model.get("properties") or {}).items():
            options = [prop, *prop.get("anyOf", [])]
            items = [option.get("items") or {} for option in options if option.get("type") == "array"]
            if any(_is_text(option) for option in options) or any(_is_text(item) for item in items):
                out.append((f"{model_name or schema.get('title')}.{field_name}", prop))
    return out


def test_the_text_class_walk_reads_every_result_schema():
    found = {descriptor.id: _text_fields(descriptor.result.model_json_schema()) for descriptor in REGISTERED}
    # Only a result made of counts may have no text field.
    assert [operation for operation, fields in found.items() if not fields] == ["radar.summary"]


def test_a_formatted_string_other_than_a_date_or_time_is_still_text():
    schema = {"title": "R", "properties": {
        "link": {"type": "string", "format": "uri"},
        "seen": {"type": "string", "format": "date-time"},
        "day": {"anyOf": [{"type": "string", "format": "date"}, {"type": "null"}]},
    }}
    assert [name for name, _ in _text_fields(schema)] == ["R.link"]


@pytest.mark.parametrize("descriptor", REGISTERED, ids=lambda descriptor: descriptor.id)
def test_every_text_field_an_operation_answers_declares_its_text_class(descriptor):
    fields = _text_fields(descriptor.result.model_json_schema())
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
    categories: dict[str, str] = dataclasses.field(default_factory=dict)


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


POSTINGS_AND_PURSUITS = _descriptor(id="widgets.list", data_classes=("public_posting", "private_pursuit"))


@pytest.mark.parametrize("choice", ["not_shared", "local_only"])
def test_a_read_whose_primary_category_is_not_shared_is_refused_with_its_own_code(choice):
    switches = Switches(True, True, {"public_posting": choice})
    with pytest.raises(OperationError) as caught:
        admit(POSTINGS_AND_PURSUITS, switches)
    assert caught.value.code == "category_disabled"
    assert caught.value.details == {
        "category": "public_posting", "setting": "agent_access.categories.public_posting",
    }
    assert outcome("category_disabled").exit_status == 4
    assert outcome("category_disabled").http_status == 403
    assert availability(POSTINGS_AND_PURSUITS, switches) == Availability("unavailable", "category_disabled")


def test_a_secondary_category_switched_off_admits_the_operation_and_is_withheld():
    switches = Switches(True, False, {"private_pursuit": "not_shared"})
    admit(POSTINGS_AND_PURSUITS, switches)
    assert withheld(POSTINGS_AND_PURSUITS, switches) == {"private_pursuit"}
    assert shared(switches, "public_posting") and not shared(switches, "private_pursuit")


def test_a_category_with_no_choice_is_shared_and_enabled_off_shares_nothing():
    assert shared(Switches(True, False), "offer")
    assert shared(Switches(True, False, {"offer": "any_model"}), "offer")
    everything_open = Switches(False, False, {"public_posting": "any_model"})
    assert not shared(everything_open, "public_posting")
    with pytest.raises(OperationError) as caught:
        admit(POSTINGS_AND_PURSUITS, everything_open)
    assert caught.value.code == "access_disabled"


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
        descriptor = CATALOG.get(route.openapi_extra["x-operation"])
        assert descriptor is not None
        if descriptor.access == "read":
            # A read is a GET unless it takes a document, which travels as a POST body.
            expected = {"POST"} if _takes_document(descriptor) else {"GET"}
            assert route.methods == expected, route.path
        else:
            # A write takes a body and never a GET, which commits nothing.
            assert len(route.methods) == 1 and route.methods <= {"POST", "PUT", "PATCH"}, route.path


def _takes_document(descriptor: OperationDescriptor) -> bool:
    return any(
        prop.get("type") == "object" for prop in descriptor.input.model_json_schema().get("properties", {}).values()
    )


def test_an_agent_route_that_names_no_operation_cannot_be_built():
    from fastapi import APIRouter

    router = APIRouter(route_class=AgentRoute)
    with pytest.raises(ValueError, match="names no catalogued operation"):
        router.add_api_route(f"{PREFIX}/nothing", lambda: None)
    with pytest.raises(ValueError, match="names no catalogued operation"):
        router.add_api_route(f"{PREFIX}/unknown", lambda: None, openapi_extra={"x-operation": "no.such"})


def _example_path(route: APIRoute) -> str:
    return route.path.replace("{operation}", "status").replace("{opportunity_id}", "1")


async def _call(api_client, route: APIRoute):
    (method,) = route.methods
    if method == "GET":
        return await api_client.get(_example_path(route))
    return await api_client.request(method, _example_path(route), json={})


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
        response = await _call(api_client, route)
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
    body = (await api_client.get(f"{PREFIX}/capabilities", params={"view": "full"})).json()
    _assert_envelope(body, operation="capabilities", ok=True)
    data = body["data"]
    assert data["view"] == "full"
    assert data["metadata_source"] == "engine"
    assert data["engine_version"]
    assert data["supported_contract_versions"] == [CONTRACT_VERSION]
    assert [entry["operation"] for entry in data["operations"]] == [descriptor.id for descriptor in CATALOG]
    for entry in data["operations"]:
        # Writes stay off until the person allows them; every read is available.
        expected = (
            {"state": "unavailable", "reason": "writes_disabled"}
            if entry["access"] == "write"
            else {"state": "available", "reason": None}
        )
        assert entry["availability"] == expected, entry["operation"]
        assert set(entry["engine_effects"]) == {"state_write", "outbound_network", "model_egress", "external_action"}


#: The most one discovery answer may take: the capability index budget of the
#: standard tool tier, 1,500 tokens at four bytes each.
DISCOVERY_BUDGET = 1_500 * 4


@pytest.mark.asyncio
@pytest.mark.parametrize("allow_writes", [False, True])
async def test_the_capability_index_is_each_summary_by_id_within_its_budget(api_client, db_session, allow_writes):
    """What every trial reads first: what each operation is for, what more
    than reading it does, and what the person's switches turn off."""
    await _enable(db_session, allow_writes=allow_writes)
    response = await api_client.get(f"{PREFIX}/capabilities")
    assert len(response.content) <= DISCOVERY_BUDGET
    body = response.json()
    _assert_envelope(body, operation="capabilities", ok=True)
    data = body["data"]
    assert data["view"] == "summary"
    assert data["operations"] == {descriptor.id: first_sentence(descriptor.summary) for descriptor in CATALOG}
    # Only what a call does beyond reading the engine is listed.
    assert data["effects"]["pursuits.patch"] == ["state_write"]
    assert data["effects"]["sources.inspect"] == ["outbound_network"]
    assert data["effects"]["capabilities"] == ["file_write"]
    assert "opportunities.search" not in data["effects"]
    writes = sorted(descriptor.id for descriptor in CATALOG if descriptor.access == "write")
    assert data["unavailable"] == ({} if allow_writes else dict.fromkeys(writes, "writes_disabled"))
    assert data["continue_with"] == [{"operation": "capabilities", "arguments": {"view": "full"}}]


@pytest.mark.asyncio
async def test_a_category_kept_back_shows_in_the_index_with_its_reason(api_client, db_session):
    await set_agent_access(db_session, AgentAccessConfig(
        enabled=True, allow_writes=True, categories={"offer": "not_shared"}))
    await ensure_workspace_id(db_session)
    await db_session.commit()
    data = (await api_client.get(f"{PREFIX}/capabilities")).json()["data"]
    assert data["unavailable"] == {"offer.get": "category_disabled"}


def test_the_index_keeps_a_summary_up_to_its_first_full_stop():
    assert first_sentence("Save an opportunity. A new pursuit starts at saved.") == "Save an opportunity."
    assert first_sentence("Read one opportunity in a declared view: summary, detail or evidence.") == (
        "Read one opportunity in a declared view: summary, detail or evidence."
    )
    for descriptor in CATALOG:
        kept = first_sentence(descriptor.summary)
        assert descriptor.summary.startswith(kept) and kept.endswith("."), descriptor.id


@pytest.mark.asyncio
async def test_capabilities_filters_by_tier_and_refuses_unknown_input(api_client, db_session):
    await _enable(db_session)
    small = (await api_client.get(f"{PREFIX}/capabilities", params={"tier": "small", "view": "full"})).json()
    assert {entry["operation"] for entry in small["data"]["operations"]} == {
        descriptor.id for descriptor in CATALOG if "small" in descriptor.tool_tiers
    }
    assert "recipes.contract.get" not in {entry["operation"] for entry in small["data"]["operations"]}
    index = (await api_client.get(f"{PREFIX}/capabilities", params={"tier": "small"})).json()["data"]
    assert set(index["operations"]) == {descriptor.id for descriptor in CATALOG if "small" in descriptor.tool_tiers}
    # The full view of the same list keeps the tier.
    assert index["continue_with"] == [{"operation": "capabilities", "arguments": {"view": "full", "tier": "small"}}]

    for params, field in (({"tier": "huge"}, "tier"), ({"verbose": "1"}, "verbose"), ({"view": "all"}, "view")):
        response = await api_client.get(f"{PREFIX}/capabilities", params=params)
        body = response.json()
        assert response.status_code == 422
        _assert_envelope(body, operation="capabilities", ok=False)
        assert body["error"]["code"] == "invalid_input"
        assert [error["location"] for error in body["error"]["details"]["errors"]] == [[field]]
        # The value sent is not repeated back.
        assert "huge" not in json.dumps(body)


def _titled(schema: object) -> bool:
    """Whether a schema node anywhere in `schema` has a `title` keyword. The
    keys of `properties` and `$defs` are names, so a field named title is not one."""
    if isinstance(schema, list):
        return any(_titled(item) for item in schema)
    if not isinstance(schema, dict):
        return False
    return "title" in schema or any(
        any(_titled(item) for item in value.values()) if key in ("properties", "$defs") else _titled(value)
        for key, value in schema.items()
    )


def test_a_brief_input_schema_drops_title_keywords_and_keeps_fields_named_title():
    from tracker.agents.operations.index import describe_view

    schema = {
        "title": "Input", "type": "object",
        "properties": {"title": {"title": "Title", "type": "string"},
                       "sort": {"enum": ["title", "pay"], "title": "Sort"}},
        "$defs": {"title": {"title": "Title", "type": "string"}},
    }
    entry = {"operation": "widgets.list", "input_schema": schema, "output_schema": {}, "output_schema_ref": "#/x"}
    brief = describe_view(entry, "summary")["input_schema"]
    assert brief == {
        "type": "object",
        "properties": {"title": {"type": "string"}, "sort": {"enum": ["title", "pay"]}},
        "$defs": {"title": {"type": "string"}},
    }
    assert _titled(schema) and not _titled(brief)
    assert describe_view(entry, "full")["input_schema"] == schema


@pytest.mark.asyncio
async def test_describe_says_how_to_call_an_operation_within_the_budget(api_client, db_session):
    await _enable(db_session)
    for descriptor in CATALOG:
        response = await api_client.get(f"{PREFIX}/operations/{descriptor.id}")
        assert len(response.content) <= DISCOVERY_BUDGET, descriptor.id
        data = response.json()["data"]
        assert data["view"] == "summary" and data["summary"] == descriptor.summary
        assert "output_schema" not in data and "output_schema_ref" not in data
        assert data["continue_with"] == [
            {"operation": "describe", "arguments": {"operation": descriptor.id, "view": "full"}}
        ]
        # The input schema is whole but for the titles derived from field names.
        schema = descriptor.input.model_json_schema()
        assert set(data["input_schema"].get("properties", {})) == set(schema.get("properties", {}))
        assert data["input_schema"].get("required") == schema.get("required")
        assert not _titled(data["input_schema"]), descriptor.id
    described = (await api_client.get(f"{PREFIX}/operations/opportunities.get")).json()["data"]
    assert described["input_schema"]["properties"]["view"]["enum"] == ["summary", "detail", "evidence"]
    assert described["input_schema"]["additionalProperties"] is False


@pytest.mark.asyncio
async def test_describe_returns_one_operation_in_full_from_the_engine(api_client, db_session):
    await _enable(db_session)
    body = (await api_client.get(f"{PREFIX}/operations/capabilities", params={"view": "full"})).json()
    _assert_envelope(body, operation="describe", ok=True)
    data = body["data"]
    assert data["view"] == "full"
    assert data["operation"] == "capabilities"
    assert data["metadata_source"] == "engine"
    assert data["availability"] == {"state": "available", "reason": None}
    assert data["input_schema"]["additionalProperties"] is False
    assert "tier" in data["input_schema"]["properties"]
    assert data["output_schema"] == meta.CapabilitiesResult.model_json_schema()
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
    response = await api_client.get(f"{PREFIX}/operations/widgets.list")
    body = response.json()
    assert response.status_code == 404
    _assert_envelope(body, operation="describe", ok=False)
    assert body["error"]["code"] == "unknown_operation"
    assert body["error"]["next_actions"] == [{"operation": "capabilities", "arguments": {}}]
    # Admitted, so the workspace is named even on a failure.
    assert WORKSPACE.fullmatch(body["workspace_id"])


@pytest.mark.asyncio
async def test_describe_of_a_resource_name_lists_the_operations_under_it(api_client, db_session):
    await _enable(db_session)
    body = (await api_client.get(f"{PREFIX}/operations/opportunities")).json()
    assert body["error"]["code"] == "unknown_operation"
    under = sorted(descriptor.id for descriptor in CATALOG if descriptor.id.startswith("opportunities."))
    assert len(under) >= 3, "the catalog must have opportunities operations, or this proves nothing"
    assert body["error"]["details"]["candidates"] == under
    assert body["error"]["next_actions"] == [
        *({"operation": "describe", "arguments": {"operation": name}} for name in under),
        {"operation": "capabilities", "arguments": {}},
    ]
    # A partial id names what it starts; a name that starts nothing names nothing.
    partial = (await api_client.get(f"{PREFIX}/operations/opportunities.ge")).json()
    assert partial["error"]["details"]["candidates"] == ["opportunities.get", "opportunities.get_many"]
    none = (await api_client.get(f"{PREFIX}/operations/widgets")).json()
    assert none["error"]["details"]["candidates"] == []


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

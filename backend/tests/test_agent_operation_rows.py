"""Every operation the engine offers is accounted for where coverage is decided.

The coverage ledger names the operation that covers each dashboard route, and
the MCP parity checklist names the operation that replaces each MCP tool and
the switch that gates it. An operation in neither was added without anyone
deciding what it covers, so the catalog may hold no such operation. One the
checklist names must sit under the switch the checklist gives it: the parity
rule is "the same switch", and a read moved under the write switch, or a write
left under the read switch, would break it silently.

`capabilities` and `describe` are the discovery surface itself, as the routes
under `/api/agent/v1/` are for the ledger: they describe operations and cover
nothing.
"""

from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

from tracker.agents.operations.catalog import CATALOG
from tracker.agents.operations.descriptor import EngineEffects, OperationDescriptor
from tracker.agents.operations.recipes import (
    RECIPES_CONTRACT_GET,
    RECIPES_VALIDATE,
    SOURCES_INSPECT,
)

_FIXTURES = Path(__file__).parent / "fixtures"

#: Operations that describe the surface and cover no route or tool.
DISCOVERY = {"capabilities", "describe"}

#: The scopes an operation under each checklist switch requires. An ungated
#: tool's replacement still needs `enabled`, as every operation does
#: (`tracker/agents/operations/policy.py`); its checklist row says so.
SCOPES_FOR_SWITCH = {
    "none": ("agent_access.enabled",),
    "enabled": ("agent_access.enabled",),
    "allow_writes": ("agent_access.enabled", "agent_access.allow_writes"),
}


def _ledger_operations() -> set[str]:
    rows = json.loads((_FIXTURES / "agent_coverage_ledger.json").read_text())["rows"]
    return {row["operation"] for row in rows if row.get("operation")}


def _checklist_switches() -> dict[str, str]:
    rows = json.loads((_FIXTURES / "mcp_parity_checklist.json").read_text())["tools"]
    return {row["operation"]: row["switch"] for row in rows}


def row_problems(
    descriptors: list[OperationDescriptor], ledger: set[str], checklist: dict[str, str]
) -> list[str]:
    problems: list[str] = []
    for descriptor in descriptors:
        if descriptor.id in DISCOVERY:
            continue
        if descriptor.id not in ledger and descriptor.id not in checklist:
            problems.append(f"{descriptor.id}: no ledger or checklist row")
            continue
        switch = checklist.get(descriptor.id)
        if switch is not None and descriptor.required_scopes != SCOPES_FOR_SWITCH.get(switch):
            problems.append(f"{descriptor.id}: requires {list(descriptor.required_scopes)}, checklist says {switch!r}")
    return problems


def test_every_catalog_operation_has_its_row_under_its_switch():
    assert row_problems(list(CATALOG), _ledger_operations(), _checklist_switches()) == []


def test_the_parity_reads_are_named_by_the_checklist_itself():
    """The reads that replace MCP tools are found through the checklist, not
    only through a dashboard route the ledger happens to map to them."""
    checklist = _checklist_switches()
    for operation in ("radar.summary", "opportunities.get", "opportunities.history", "pursuits.list",
                      "recipes.contract.get", "sources.inspect", "recipes.validate"):
        assert operation in CATALOG
        assert checklist[operation] == "enabled"
    assert "pursuits.get" in _ledger_operations()


def test_the_recipe_reads_that_fetch_pages_declare_it_and_the_contract_does_not():
    assert SOURCES_INSPECT.engine_effects.outbound_network
    assert RECIPES_VALIDATE.engine_effects.outbound_network
    assert not RECIPES_CONTRACT_GET.engine_effects.outbound_network
    for descriptor in (SOURCES_INSPECT, RECIPES_VALIDATE, RECIPES_CONTRACT_GET):
        assert descriptor.access == "read" and not descriptor.engine_effects.state_write


# --- negative controls


def _read(operation_id: str) -> OperationDescriptor:
    descriptor = CATALOG.get("radar.summary")
    assert descriptor is not None
    return replace(descriptor, id=operation_id)


def test_an_operation_in_neither_file_fails():
    problems = row_problems([_read("widgets.list")], _ledger_operations(), _checklist_switches())

    assert problems == ["widgets.list: no ledger or checklist row"]


def test_a_write_under_the_read_switch_fails():
    write = replace(
        _read("pursuits.list"), access="write", idempotency="required_key",
        engine_effects=EngineEffects(state_write=True),
    )

    problems = row_problems([write], _ledger_operations(), _checklist_switches())

    assert problems == [
        "pursuits.list: requires ['agent_access.enabled', 'agent_access.allow_writes'], checklist says 'enabled'"
    ]


def test_a_read_under_the_write_switch_fails():
    problems = row_problems([_read("pursuits.save")], _ledger_operations(), _checklist_switches())

    assert problems == ["pursuits.save: requires ['agent_access.enabled'], checklist says 'allow_writes'"]


def test_the_discovery_operations_are_the_only_ones_without_a_row():
    unrowed = {
        descriptor.id for descriptor in CATALOG
        if descriptor.id not in _ledger_operations() and descriptor.id not in _checklist_switches()
    }
    assert unrowed == DISCOVERY

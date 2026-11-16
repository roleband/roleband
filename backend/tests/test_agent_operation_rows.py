"""Every operation the engine offers is accounted for where coverage is decided.

The coverage ledger names the operation that covers each dashboard route and
lists those that cover none (`unrouted`). An operation the ledger does not
name must be one of `OUTSIDE_THE_LEDGER`: it answers something no dashboard
route does (the connection's state, a lost reply's receipt, a recipe's
contract). An operation in neither was added without anyone deciding what it
covers, so the catalog may hold no such operation. Every operation also sits
under the switch its access class means: a read under `enabled`, a write under
`enabled` and `allow_writes`, so a read moved under the write switch, or a
write left under the read switch, fails.

`capabilities` and `describe` are the discovery surface itself, as the routes
under `/api/agent/v1/` are for the ledger: they describe operations and cover
nothing.
"""

from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

from tracker.agents.operations.catalog import CATALOG
from tracker.agents.operations.descriptor import OperationDescriptor
from tracker.agents.operations.recipes import (
    RECIPES_CONTRACT_GET,
    RECIPES_VALIDATE,
    SOURCES_INSPECT,
)

_FIXTURES = Path(__file__).parent / "fixtures"

#: Operations that describe the surface and cover no route.
DISCOVERY = {"capabilities", "describe"}

#: Operations that answer what no dashboard route answers.
OUTSIDE_THE_LEDGER = {
    "status", "receipts.get", "opportunities.get_many", "opportunities.reality",
    "recipes.contract.get", "sources.inspect",
}

#: The scopes an operation of each access class requires.
SCOPES_FOR_ACCESS = {
    "read": ("agent_access.enabled",),
    "write": ("agent_access.enabled", "agent_access.allow_writes"),
}


def _ledger_operations() -> set[str]:
    """The operations the ledger names: on a route's row, or as covering none."""
    ledger = json.loads((_FIXTURES / "agent_coverage_ledger.json").read_text())
    return {row["operation"] for row in ledger["rows"] if row.get("operation")} | {
        entry["operation"] for entry in ledger.get("unrouted", [])
    }


def row_problems(
    descriptors: list[OperationDescriptor], ledger: set[str], outside: set[str]
) -> list[str]:
    problems: list[str] = []
    for descriptor in descriptors:
        if descriptor.id in DISCOVERY:
            continue
        if descriptor.id not in ledger and descriptor.id not in outside:
            problems.append(f"{descriptor.id}: no ledger row and not outside the ledger")
            continue
        if descriptor.required_scopes != SCOPES_FOR_ACCESS[descriptor.access]:
            problems.append(
                f"{descriptor.id}: a {descriptor.access} requires {list(descriptor.required_scopes)}"
            )
    return problems


def test_every_catalog_operation_has_its_row_under_its_switch():
    assert row_problems(list(CATALOG), _ledger_operations(), OUTSIDE_THE_LEDGER) == []


def test_the_operations_outside_the_ledger_exist_and_the_ledger_does_not_name_them():
    assert OUTSIDE_THE_LEDGER <= {d.id for d in CATALOG}
    assert not OUTSIDE_THE_LEDGER & _ledger_operations()
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


def test_an_operation_in_neither_place_fails():
    problems = row_problems([_read("widgets.list")], _ledger_operations(), OUTSIDE_THE_LEDGER)

    assert problems == ["widgets.list: no ledger row and not outside the ledger"]


def _stub(operation_id: str, access: str, scopes: tuple[str, ...]):
    return SimpleNamespace(id=operation_id, access=access, required_scopes=scopes)


def test_a_write_under_the_read_switch_fails():
    write = _stub("pursuits.list", "write", ("agent_access.enabled",))

    problems = row_problems([write], _ledger_operations(), OUTSIDE_THE_LEDGER)

    assert problems == ["pursuits.list: a write requires ['agent_access.enabled']"]


def test_a_read_under_the_write_switch_fails():
    read = _stub("pursuits.get", "read", ("agent_access.enabled", "agent_access.allow_writes"))

    problems = row_problems([read], _ledger_operations(), OUTSIDE_THE_LEDGER)

    assert problems == [
        "pursuits.get: a read requires ['agent_access.enabled', 'agent_access.allow_writes']"
    ]


def test_the_discovery_operations_are_the_only_ones_without_a_row():
    unrowed = {
        descriptor.id for descriptor in CATALOG
        if descriptor.id not in _ledger_operations() and descriptor.id not in OUTSIDE_THE_LEDGER
    }
    assert unrowed == DISCOVERY

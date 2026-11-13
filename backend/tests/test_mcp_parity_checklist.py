"""Each MCP tool has a CLI operation that replaces it, under the same switch.

`fixtures/mcp_parity_checklist.json` maps every tool the MCP server registers
to the operation that replaces it, with the deliberate differences between the
two and what is still undecided. The MCP server is removed only once the CLI
does everything it does, so a tool added to the server without a row here would
be lost silently at the removal.

The switch is checked against the access class Settings publishes for each
tool, which `test_agents.py` holds to the server's own gate: the replacement
answers under exactly the switch the tool answers under.
"""

from __future__ import annotations

import asyncio
import json
import re
from pathlib import Path

import pytest

from tracker.agents.config import AgentAccessConfig
from tracker.api.routers.intelligence import _agent_connection_state
from tracker.mcp.server import mcp

pytestmark = pytest.mark.usefixtures("no_escape")

_CHECKLIST = Path(__file__).parent / "fixtures" / "mcp_parity_checklist.json"

#: The operation catalog's form, as in `test_agent_coverage_ledger.py`.
OPERATION_ID = re.compile(r"^[a-z][a-z0-9_]*(\.[a-z][a-z0-9_]*)*$")

#: The access class Settings publishes, and the switch that class means.
SWITCH_FOR_ACCESS = {"status": "none", "read": "enabled", "write": "allow_writes"}


def _checklist() -> dict:
    return json.loads(_CHECKLIST.read_text())


def _registered() -> set[str]:
    return {tool.name for tool in asyncio.run(mcp.list_tools())}


def _published_switches() -> dict[str, str]:
    state = _agent_connection_state(AgentAccessConfig(enabled=True, allow_writes=True))
    return {tool["name"]: SWITCH_FOR_ACCESS[tool["access"]] for tool in state["tools"]}


def parity_problems(registered: set[str], switches: dict[str, str], rows: list[dict]) -> list[str]:
    """Every way the checklist fails to describe the registered tools."""

    problems: list[str] = []
    names = [row.get("tool") for row in rows]
    for name in sorted({n for n in names if names.count(n) > 1}):
        problems.append(f"{name}: {names.count(name)} rows")
    for name in sorted(registered - set(names)):
        problems.append(f"{name}: no row")
    for name in sorted(set(names) - registered):
        problems.append(f"{name}: not a registered tool")
    operations = [row.get("operation") for row in rows]
    for row in rows:
        name, operation = row.get("tool"), row.get("operation")
        if not isinstance(operation, str) or not OPERATION_ID.match(operation):
            problems.append(f"{name}: {operation!r} is not an operation ID")
        elif operations.count(operation) > 1:
            problems.append(f"{name}: {operation} replaces more than one tool")
        if name in switches and row.get("switch") != switches[name]:
            problems.append(f"{name}: gated by {switches[name]}, row says {row.get('switch')!r}")
        for key in ("differences", "open"):
            items = row.get(key)
            if not isinstance(items, list) or not all(isinstance(i, str) and i.strip() for i in items):
                problems.append(f"{name}: {key} must be a list of sentences")
    return problems


def test_every_registered_tool_has_its_replacement():
    rows = _checklist()["tools"]

    assert parity_problems(_registered(), _published_switches(), rows) == []
    assert len(rows) == 12


def test_the_differences_every_operation_shares_are_stated():
    shared = _checklist()["every_operation"]

    assert shared and all(isinstance(line, str) and line.strip() for line in shared)


# --- negative controls


def test_a_tool_without_a_row_fails():
    rows = _checklist()["tools"]
    dropped = rows[2]["tool"]

    problems = parity_problems(
        _registered(), _published_switches(), [row for row in rows if row["tool"] != dropped]
    )

    assert problems == [f"{dropped}: no row"]


def test_a_new_tool_without_a_row_fails():
    problems = parity_problems(_registered() | {"delete_everything"}, {}, _checklist()["tools"])

    assert problems == ["delete_everything: no row"]


def test_a_row_for_a_tool_the_server_dropped_fails():
    rows = [*_checklist()["tools"], {
        "tool": "gone", "operation": "gone.get", "switch": "enabled", "differences": [], "open": [],
    }]

    assert parity_problems(_registered(), _published_switches(), rows) == ["gone: not a registered tool"]


def test_a_write_mapped_under_the_read_switch_fails():
    rows = _checklist()["tools"]
    patched = [
        {**row, "switch": "enabled"} if row["tool"] == "update_pursuit" else row for row in rows
    ]

    assert parity_problems(_registered(), _published_switches(), patched) == [
        "update_pursuit: gated by allow_writes, row says 'enabled'"
    ]


def test_two_tools_cannot_share_one_replacement():
    rows = _checklist()["tools"]
    patched = [
        {**row, "operation": "pursuits.list"} if row["tool"] == "save_opportunity" else row
        for row in rows
    ]

    problems = parity_problems(_registered(), _published_switches(), patched)

    assert problems == [
        "get_pursuits: pursuits.list replaces more than one tool",
        "save_opportunity: pursuits.list replaces more than one tool",
    ]

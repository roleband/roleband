"""Every API route has a decision about what an agent reaches it through.

`fixtures/agent_coverage_ledger.json` holds one row per (method, path) the app
serves: either the ID of the operation that covers the route, or an
exclusion kind with the reason no operation does. A new route cannot ship
without that decision, and a removed route cannot leave a row behind that still
claims coverage.

Routes under `/api/agent/v1/` are the operation surface itself, so they need no
row and may not have one.

This file checks the form of each operation ID, not that the operation exists:
a covered route names the operation that is to serve it.
"""

from __future__ import annotations

import json
import re
from collections import Counter
from pathlib import Path

from fastapi import FastAPI

from scripts.freeze_route_table import route_rows
from tracker.api.app import app

_LEDGER = Path(__file__).parent / "fixtures" / "agent_coverage_ledger.json"

#: The operation surface: served to agents, so it is the coverage, not a route to cover.
AGENT_PREFIX = "/api/agent/v1/"

#: The operation catalog's form: lowercase segments joined by dots, underscores
#: inside a segment (`status`, `opportunities.search`, `companies.facts.list`).
OPERATION_ID = re.compile(r"^[a-z][a-z0-9_]*(\.[a-z][a-z0-9_]*)*$")

#: Why a route has no operation. A new kind is a decision about the agent
#: surface, so it is added here deliberately, never by a row inventing one.
EXCLUSION_KINDS = {
    "app_setting": "a setting or secret that stays in the app, so no agent can widen its own access",
    "person_only": "an act only the person performs: attesting a fact, or consenting for themself",
    "destructive": "removes the person's data with nothing to restore it from",
    "internal": "serves the dashboard or the launcher and has no meaning to an agent",
    "maintainer": "a diagnostic or maintainer control",
}


def _ledger() -> dict:
    return json.loads(_LEDGER.read_text())


def _served(application: FastAPI) -> set[tuple[str, str]]:
    return {
        (row["method"], row["path"])
        for row in route_rows(application)
        if not row["path"].startswith(AGENT_PREFIX)
    }


def coverage_problems(served: set[tuple[str, str]], rows: list[dict]) -> list[str]:
    """Every way the ledger fails to describe the served routes, one line each."""

    problems: list[str] = []
    keys = [(row.get("method"), row.get("path")) for row in rows]
    for key, count in Counter(keys).items():
        if count > 1:
            problems.append(f"{key[0]} {key[1]}: {count} rows")
    for method, path in sorted(served - set(keys)):
        problems.append(f"{method} {path}: no row")
    for method, path in keys:
        if path is not None and path.startswith(AGENT_PREFIX):
            problems.append(f"{method} {path}: the operation surface needs no row")
        elif (method, path) not in served:
            problems.append(f"{method} {path}: no such route")
    for row in rows:
        where = f"{row.get('method')} {row.get('path')}"
        operation, excluded, reason = row.get("operation"), row.get("excluded"), row.get("reason")
        if (operation is None) == (excluded is None):
            problems.append(f"{where}: needs exactly one of operation or excluded")
            continue
        if operation is not None:
            if not isinstance(operation, str) or not OPERATION_ID.match(operation):
                problems.append(f"{where}: {operation!r} is not an operation ID")
            if reason is not None:
                problems.append(f"{where}: a covered route carries no exclusion reason")
            continue
        if excluded not in EXCLUSION_KINDS:
            problems.append(f"{where}: {excluded!r} is not an exclusion kind")
        if not isinstance(reason, str) or not reason.strip():
            problems.append(f"{where}: excluded without a reason")
    return problems


def test_every_route_has_exactly_one_decision():
    assert coverage_problems(_served(app), _ledger()["rows"]) == []


def test_the_ledger_covers_the_frozen_route_table():
    """The ledger and the frozen table describe one set of routes, so a route
    added with a regenerated table and no ledger row fails here as well."""

    frozen = json.loads((Path(__file__).parent / "fixtures" / "route_table.json").read_text())
    frozen_keys = {
        (row["method"], row["path"]) for row in frozen["routes"]
        if not row["path"].startswith(AGENT_PREFIX)
    }
    assert {(row["method"], row["path"]) for row in _ledger()["rows"]} == frozen_keys


# --- negative controls: each breaks the real ledger one way and must be caught.


def test_a_missing_row_is_reported_by_route():
    rows = _ledger()["rows"]
    dropped = rows[len(rows) // 2]

    problems = coverage_problems(_served(app), [row for row in rows if row is not dropped])

    assert problems == [f"{dropped['method']} {dropped['path']}: no row"]


def test_a_new_route_without_a_row_fails():
    probe = FastAPI(openapi_url=None, docs_url=None, redoc_url=None)

    @probe.get("/api/probe-only")
    async def probe_only() -> dict:  # pragma: no cover - never called
        return {}

    problems = coverage_problems(_served(probe), [])

    assert problems == ["GET /api/probe-only: no row"]


def test_a_row_for_a_removed_route_fails():
    rows = [*_ledger()["rows"], {"method": "GET", "path": "/api/gone", "operation": "gone.get"}]

    assert coverage_problems(_served(app), rows) == ["GET /api/gone: no such route"]


def test_an_exclusion_needs_a_reason_and_a_known_kind():
    rows = _ledger()["rows"]
    excluded = next(row for row in rows if "excluded" in row)
    others = [row for row in rows if row is not excluded]
    where = f"{excluded['method']} {excluded['path']}"

    blank = coverage_problems(_served(app), [*others, {**excluded, "reason": "  "}])
    missing = coverage_problems(
        _served(app), [*others, {k: v for k, v in excluded.items() if k != "reason"}]
    )
    unknown = coverage_problems(_served(app), [*others, {**excluded, "excluded": "later"}])

    assert blank == [f"{where}: excluded without a reason"]
    assert missing == [f"{where}: excluded without a reason"]
    assert unknown == [f"{where}: 'later' is not an exclusion kind"]


def test_a_row_names_one_disposition_in_the_contract_form():
    rows = _ledger()["rows"]
    covered = next(row for row in rows if "operation" in row)
    others = [row for row in rows if row is not covered]
    where = f"{covered['method']} {covered['path']}"

    both = coverage_problems(_served(app), [*others, {**covered, "excluded": "internal", "reason": "x"}])
    neither = coverage_problems(
        _served(app), [*others, {"method": covered["method"], "path": covered["path"]}]
    )
    malformed = coverage_problems(
        _served(app), [*others, {**covered, "operation": "opportunities search"}]
    )

    assert both == [f"{where}: needs exactly one of operation or excluded"]
    assert neither == [f"{where}: needs exactly one of operation or excluded"]
    assert malformed == [f"{where}: 'opportunities search' is not an operation ID"]


def test_a_duplicate_row_fails():
    rows = _ledger()["rows"]

    problems = coverage_problems(_served(app), [*rows, rows[0]])

    assert problems == [f"{rows[0]['method']} {rows[0]['path']}: 2 rows"]


def test_the_operation_surface_is_exempt_and_takes_no_row():
    probe = FastAPI(openapi_url=None, docs_url=None, redoc_url=None)

    @probe.get(AGENT_PREFIX + "status")
    async def agent_status() -> dict:  # pragma: no cover - never called
        return {}

    assert _served(probe) == set()
    row = {"method": "GET", "path": AGENT_PREFIX + "status", "operation": "status"}
    assert coverage_problems(_served(probe), [row]) == [
        f"GET {AGENT_PREFIX}status: the operation surface needs no row"
    ]

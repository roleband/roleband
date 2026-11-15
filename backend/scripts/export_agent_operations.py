"""Write the `roleband` client's bundled operation index.

The client answers `--help`, `capabilities --offline` and `describe --offline`
from `tracker/cli/operations.json` without an engine, and without importing
the engine's catalog, and builds one command per operation from it. This
writes that file from the catalog (`tracker/agents/operations/catalog.py`)
and the agent router, which gives each operation its method and path;
`tests/test_agent_operations.py` fails while the committed copy differs.

    .venv/bin/python -m scripts.export_agent_operations [out_path]
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

from tracker.agents.operations.catalog import CATALOG, bundled_index

COMMITTED = Path(__file__).resolve().parents[1] / "tracker" / "cli" / "operations.json"


def routes() -> dict[str, dict[str, str]]:
    """Each operation's one route, as the client calls it."""
    from fastapi.routing import APIRoute

    from tracker.api.routers.agent import router

    found: dict[str, dict[str, str]] = {}
    for route in router.routes:
        if not isinstance(route, APIRoute):
            continue
        operation = (route.openapi_extra or {}).get("x-operation")
        if not isinstance(operation, str) or len(route.methods) != 1:
            raise ValueError(f"{route.path}: an agent route names one operation and answers one method")
        if operation in found:
            raise ValueError(f"{operation} has more than one route")
        found[operation] = {"method": next(iter(route.methods)), "path": route.path}
    if missing := sorted(descriptor.id for descriptor in CATALOG if descriptor.id not in found):
        raise ValueError(f"operations without a route: {missing}")
    return dict(sorted(found.items()))


def index() -> dict[str, Any]:
    return {**bundled_index(), "routes": routes()}


def render() -> str:
    """The exact bytes the committed index must contain."""
    return json.dumps(index(), indent=1, sort_keys=True) + "\n"


def main() -> None:
    out = Path(sys.argv[1]) if len(sys.argv) > 1 else COMMITTED
    out.write_text(render(), encoding="utf-8")
    print(f"{len(bundled_index()['operations'])} operations -> {out}")


if __name__ == "__main__":
    main()

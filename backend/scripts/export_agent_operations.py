"""Write the `roleband` client's bundled operation index.

The client answers `--help`, `capabilities --offline` and `describe --offline`
from `tracker/cli/operations.json` without an engine, and without importing
the engine's catalog. This writes that file from the catalog
(`tracker/agents/operations/catalog.py`); `tests/test_agent_operations.py`
fails while the committed copy differs.

    .venv/bin/python -m scripts.export_agent_operations [out_path]
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from tracker.agents.operations.catalog import bundled_index

COMMITTED = Path(__file__).resolve().parents[1] / "tracker" / "cli" / "operations.json"


def render() -> str:
    """The exact bytes the committed index must contain."""
    return json.dumps(bundled_index(), indent=1, sort_keys=True) + "\n"


def main() -> None:
    out = Path(sys.argv[1]) if len(sys.argv) > 1 else COMMITTED
    out.write_text(render(), encoding="utf-8")
    print(f"{len(bundled_index()['operations'])} operations -> {out}")


if __name__ == "__main__":
    main()

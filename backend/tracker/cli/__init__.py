"""`roleband`: the command-line client agents use to reach a local engine.

A thin client. It reads its named contexts, calls one operation over loopback
HTTP, prints one envelope and exits with the code's status
(`tracker/agents/operations/outcomes.py`). It never opens a database, never
reads a project `.env`, never infers an engine from `ROLEBAND_PGDATA` and never
falls back to an address it was not given. The import contracts in
`backend/pyproject.toml` hold it to that.

`--help`, `--version`, `capabilities --offline` and `describe --offline` read
only the bundled index, `operations.json`, which `scripts.export_agent_operations`
generates from the engine's catalog.
"""

"""Agent operations: the typed, versioned actions an agent may call.

Each operation is one `OperationDescriptor` (`descriptor.py`) with typed input
and result models, listed once in `catalog.py`. The engine serves each one on
its own route under `/api/agent/v1/` (`tracker/api/routers/agent.py`); the
`roleband` client (`tracker/cli/`) reads the same descriptors from a generated
bundle and never imports this package's database modules.

`outcomes.py` imports only the standard library, because the client imports it
for the error-code to exit-code table. Keep it that way: the import contracts
in `backend/pyproject.toml` fail a client import that reaches the database.
"""

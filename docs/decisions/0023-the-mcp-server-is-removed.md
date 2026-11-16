# 0023: The MCP server is removed

## Context

[Decision 0015](0015-agents-use-the-cli.md) made the `roleband` command the
interface for agents and kept the MCP server in `tracker/mcp/` until the command
did everything it did. The server opened the database in its own process, so it
repeated rules the engine owns, and it read only the two agent switches: a data
category the person kept from assistants
([decision 0017](0017-agent-access-open-by-default.md)) was still shared through
it.

Every MCP tool now has an operation that replaces it under the same switch, and
the agent task bench passes through the command on Claude Code, Codex and a
local model, with no wrong write.

## Decision

- The MCP server, its tools and the `mcp` package are removed. The `roleband`
  command is the only agent interface.
- `tracker.mcp.server` stays as an entry point that serves nothing, because
  hosts set up for the server still launch it (`python -m tracker.mcp.server`,
  or `packaged.py mcp.server` in the Mac app). It imports nothing beyond `sys`,
  writes to standard error which `roleband connect` command replaces it, writes
  nothing to standard output and exits with status 2.
- The Settings card shows the `roleband connect` command for each host that
  command sets up, in place of an MCP configuration.
- Each behaviour an MCP tool test asserted that an operation still owns is
  asserted against the operation. Tests of the MCP transport itself are
  removed with it.

## Consequences

- Every agent call goes through the engine's operations, so the switches and
  every data category apply to all of them, and an agent needs a running engine.
- A host that can only speak MCP, such as the Claude desktop chat app, cannot
  connect. A host that can run a command connects through `roleband`.
- A host left on the old setup reports that the server did not start, and its
  log says what to run instead.
  `backend/tests/test_retired_agent_server.py` holds that answer and refuses
  any import in the entry point.
- `docs/cli.md` replaces the MCP page.

## Alternatives considered

- **Keep the server beside the command.** Two contracts that drift, and the
  server would need its own copy of the category rules to stop sharing what the
  person kept back.
- **Rebuild the server as a client of the engine's operations.** It would close
  the category gap but keep a second protocol surface, its dependency and its
  tests for hosts that can already run a command.
- **Delete the entry point too.** An existing host would fail with a Python
  import error that does not say what changed or what to run instead.

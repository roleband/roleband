# 0015: Agents reach RoleBand through the CLI

## Context

An agent the person runs (an assistant app, a coding agent, a script around a
local model) needs to read the radar and record progress. The engine already
owns every rule an agent must obey: which postings the Board shows, how stated
pay stays apart from estimates, which writes an assistant may make, and the
locks and supervisor that keep collection orderly. The MCP server in
`tracker/mcp/` reaches the same data by opening the database in its own
process, so it repeats some of those rules and works with the engine stopped.

Most agent hosts can run a command. Fewer speak a given tool protocol, and a
protocol tied to one host family does not serve a local model driven by a
script.

## Decision

- The `roleband` command is the interface for agents. It is a client of the
  running engine: it calls the engine's operations under `/api/agent/v1/` over
  loopback HTTP and renders their results.
- The command opens no database and imports no database code. It talks to the
  engine of the context it was given and never falls back to another one.
- An operation is typed and lives below HTTP, in `tracker/agents/`. The agent
  router and the CLI are its edges; neither calls a dashboard router function.
  A dashboard route may call the same operation and keep its own wire shape.
- Every dashboard route has a row in
  `backend/tests/fixtures/agent_coverage_ledger.json`: the operation that
  covers it, or an exclusion kind and its reason. Settings that widen an
  agent's own access, secrets, consents and verdicts only the person gives stay
  in the app.
- The consumer surface has no SQL, no migration, no mass delete, no secret
  export, no general HTTP passthrough and no general process execution.
- Each tool of the MCP server has a row in
  `backend/tests/fixtures/mcp_parity_checklist.json` naming the operation that
  replaces it under the same switch, with every deliberate difference.

## Consequences

- One implementation per operation: an agent and the dashboard see the same
  visibility, pay separation and policy, and a rule changes in one place.
- The engine must be running. A disconnected command fails as a connection
  error, never with a silently stale answer.
- A host whose shell sandbox blocks loopback addresses must be configured to
  allow the engine's port; a chat app that cannot run a command cannot connect.
- `tests/test_agent_coverage_ledger.py` fails when a route has no row, when a
  row names a route that is gone, and when an exclusion has no reason, so a new
  route cannot ship without a decision about agents.
  `tests/test_mcp_parity_checklist.py` fails when an MCP tool has no row or its
  replacement is gated by another switch.
- An import contract on `tracker.cli` refuses database modules.

## Alternatives considered

- **The command opens the database itself, as the MCP server does.** No engine
  needed, but a second writer beside the engine, a second copy of every
  visibility and policy rule, and no supervisor in front of collection.
- **MCP as the interface, with the command beside it.** Two contracts that
  drift, each with its own filter semantics, for hosts that can already run a
  command.
- **A compiled client in another language.** Faster start, but a second build,
  signing and schema-client surface; the bundled Python is measured first.
- **A generic HTTP passthrough to the dashboard API.** Exposes every route,
  including the ones that widen access, and defeats the boundary this record
  draws.

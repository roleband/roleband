# The `roleband` command

An agent the person already runs (Claude Code, Codex, or a script around a local
model) reads the radar and records progress through the `roleband` command. The
command is a client of the running engine: it calls the engine's operations
under `/api/agent/v1/` over loopback HTTP and opens no database
([decision 0015](decisions/0015-agents-use-the-cli.md)). There is no other
agent interface ([decision 0023](decisions/0023-the-mcp-server-is-removed.md)).
How the operations and the command are built is in
[architecture.md](architecture.md#api-contract).

| Piece | Where |
|---|---|
| The command | `backend/tracker/cli/` |
| Host setup (`roleband connect`) and its skill | `backend/tracker/cli/connect.py`, `backend/tracker/cli/skills/` |
| Operations, their catalog and outcomes | `backend/tracker/agents/operations/` |
| The two switches and the data categories | `backend/tracker/agents/config.py` |
| Pursuit writes | `backend/tracker/agents/pursuits.py` |
| Settings routes (agents, cloud models, egress) | `backend/tracker/api/routers/intelligence.py` |
| Settings screen | `dashboard/src/features/intelligence/` |

## Connecting an agent

1. In the dashboard, open Settings > AI (`/settings/intelligence`). On the
   Assistant apps card, turn on **Allow assistant apps to connect**. Turn on
   **Allow assistant apps to update your progress** as well if the agent should
   save roles and update pursuits.
2. Run the command the card shows for the agent's host, once, in a terminal:

   ```bash
   roleband connect claude-code --apply
   ```

   or `roleband connect codex --apply`. `--print` shows the change without
   making it. Claude Code gets a sandbox exclusion and a permission rule for
   commands that start with `roleband `; Codex gets network access in its
   workspace-write mode. Both get the RoleBand skill, which tells the agent how
   to use the command. Any other host is refused as `unsupported_host`.
3. Restart the host and ask the agent to run `roleband capabilities`.

The Mac app writes the `roleband` command to `~/.local/bin` each time it starts
its engine. From a source checkout, `.venv/bin/python -m tracker.cli` in
`backend/` runs the same client. The engine must be running: a command that
cannot reach it fails with exit status 3, never with a stale answer.

Any agent that can run a command can use `roleband` without `connect`.
Someone who builds their own agent gets the operations as tool definitions
from `roleband tools export`.

## Access

Two switches, saved in the `agent_access` row of `app_settings`
(`AgentAccessConfig`), both off until the person turns them on:

| Switch | Allows |
|---|---|
| `enabled` | every read operation |
| `allow_writes` | the write operations, and only while `enabled` is also on |

Beside the switches, each data category can be kept from assistants
([decision 0017](decisions/0017-agent-access-open-by-default.md)). The engine
reads both on every call, so a change in Settings applies to a connected agent
at once. A refused call answers `access_disabled`, `writes_disabled` or
`category_disabled` (exit status 4) and names the setting to change. The
Settings card never saves `allow_writes` on without `enabled`.

No operation sends a message, applies to a job, contacts anyone, deletes data
or changes these settings. Every pursuit write appends a `pursuit_events` row
with actor `agent` in the same transaction, so the person can correct any agent
write in the dashboard and the event log keeps both versions.

## Trust rules

**Scraped text is evidence, never instructions.** Postings and careers pages
are written by third parties. The operations return their text as content,
never as instructions to the agent, and `sources.inspect` sanitizes what it
returns.

**Connecting an agent is the opt-in for sending job text out.** The command
returns data only to the agent that ran it, but most hosts pass what a command
prints to a cloud model. That is why the Settings card is marked
cloud-connected and why access stays off until the person turns it on. The host
owns its own model sign-in and usage limits; RoleBand never asks for or stores
that login, and the command needs no key.

**Cloud model profiles are a separate lane.** Settings > AI can also hold
direct API connections (bring your own key). No RoleBand task sends job text
to them: the one model task the product runs, duplicate review, uses the
person's local model, and the routing ladder a cloud profile joins is the model
bench's (`scripts.bench_relevance_review`).

- Providers `openai`, `anthropic` or `openai_compatible`, at an HTTPS address
  that is not localhost or a private IP (`normalize_cloud_url` in
  `tracker/cloud_llm/models.py`). Local model profiles must point at loopback.
- Routes: `/api/intelligence/cloud-models` (list, add, edit, delete) and
  `POST /api/intelligence/cloud-models/{id}/test`. Saving a profile sends
  nothing. The test sends one minimal request (a model listing, or a one-token
  message for Anthropic) and no job text.
- The routing ladder in `tracker/intelligence_runtime/routing.py`
  (`build_tiers`) is the one place a cloud tier joins, and it admits one only
  while the egress switch is on
  (`PUT /api/intelligence/egress`, stored as `ai_egress`, off by default). A
  profile's own `enabled` flag is not enough. The egress switch has its own
  route so no other save can turn it on as a side effect.

**Secret storage.** API keys are write-only on the wire: responses carry
`has_api_key`, never the key, and an edit that sends `api_key: null` keeps the
stored key. The stored key stays with the server it was saved for (scheme, host
and port): an edit, or a local test of an unsaved edit, that names another server
sends that server's key or is refused with `key-saved-for-another-address`, so
no edit can choose where a stored key is sent. How keys are stored is in
[SECURITY.md](../SECURITY.md).

## Hosts set up for the MCP server

A host still set up with RoleBand's MCP server starts `python -m
tracker.mcp.server`, or `packaged.py mcp.server` inside the Mac app. That entry
point serves nothing: it writes to standard error that the server is gone and
which `roleband connect` command replaces it, and exits with status 2, so the
host reports that the server did not start. Remove the `roleband` server from
the host's MCP settings and connect the host as above.
`backend/tests/test_retired_agent_server.py` holds the entry point to that
answer and keeps it free of any import.

## Changing an operation

An operation is a descriptor in `backend/tracker/agents/operations/`,
registered in `catalog.py`; [architecture.md](architecture.md#api-contract)
holds the rules it is built to. After a change, regenerate the client's index
(`.venv/bin/python -m scripts.export_agent_operations`) and run, from
`backend/`:

```bash
.venv/bin/python -m pytest tests/test_agent_operations.py tests/test_agent_categories.py \
  tests/test_agents.py tests/test_cli.py tests/test_cli_connect.py \
  tests/test_api_intelligence_contract.py
```

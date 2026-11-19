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
| The two switches, the data categories and the action groups | `backend/tracker/agents/config.py` |
| Pursuit writes | `backend/tracker/agents/pursuits.py` |
| Settings routes (agents, cloud models, egress) | `backend/tracker/api/routers/intelligence.py` |
| Settings screen | `dashboard/src/features/intelligence/` |

## Connecting an agent

1. In the dashboard, open Settings > AI (`/settings/intelligence`). On the
   Assistant apps card, turn on **Allow assistant apps to connect**. That one
   switch shares every data category and allows every kind of change;
   **Customize** on the same card holds any of them back.
2. Run the command the card shows for the agent's host, once, in a terminal.
   Each widens what the host allows, beyond reaching the engine:

   - Claude Code: a command that starts with `roleband ` runs outside Claude
     Code's sandbox, with no limit on the files or network it reaches, and a
     permission rule lets Claude Code run it without asking.
   - Codex: `network_access = true` opens all network access, not only the
     engine's, to every command Codex runs in its workspace-write mode. Codex
     has no setting for loopback alone.

   ```bash
   roleband connect claude-code --apply
   ```

   or `roleband connect codex --apply`. `--print` shows the change, and these
   costs, without making it. Both hosts get the RoleBand skill, which tells the
   agent how to use the command. Any other host is refused as
   `unsupported_host`.
3. Restart the host and ask the agent to run `roleband capabilities`. It asks
   the engine, so it needs a context: the Mac app writes one, and anywhere else
   create the context file below first.

The command reaches an engine only through a named context, read from
`ROLEBAND_CLI_CONFIG`, else `roleband/cli.json` under `XDG_CONFIG_HOME`
(`~/.config` when unset); there is no default engine, and a command with no
context answers `context_required`. Each time the Mac app starts its engine it
writes the `app` context there with the engine's address, and makes it current
when the file names none. Other contexts, the person's choice of current one and
a `workspace_id` pinned to `app` are kept; a file the command could not read, or
a link, is left alone. Anywhere else, such as a source checkout or Windows,
create the file by hand:

```json
{"format": 1, "current": "app", "contexts": {"app": {"url": "http://127.0.0.1:8010"}}}
```

The Mac app writes the `roleband` command to `~/.local/bin` each time it starts
its engine. That folder must be on `PATH`, since the host runs the command by
name and Claude Code's permission rule matches only `roleband `; `connect` says
so when it is not, with the line to add to the shell profile
(`export PATH="$HOME/.local/bin:$PATH"`). From a source checkout, `.venv/bin/python -m tracker.cli` in
`backend/` runs the same client. The engine must be running: a command that
cannot reach it fails with exit status 3, never with a stale answer.

Any agent that can run a command can use `roleband` without `connect`.
Someone who builds their own agent gets the operations as tool definitions
from `roleband tools export`.

**What the card shows for each app.** The engine reads each host's own files
(`backend/tracker/platform/agent_hosts.py`, shared with `connect` so the two
agree): connected when the skill and what `connect` writes are both there, an
update when the installed skill is an unedited copy of an older version,
"asks before each command" when the skill is there but the rule is gone or a
deny or ask rule covers `roleband`, and blocked when Codex's `sandbox_mode` is
`read-only`, which `connect` leaves to the person. An
engine that cannot see the person's home folder shows every host as not
connected. Each call also names its host in the `X-RoleBand-Host` header, from
the variable the host sets in every command it runs (`CLAUDECODE=1`;
`CODEX_THREAD_ID` or `CODEX_SANDBOX` for Codex), and the engine records it on
the call's activity row (`agent_activity.host`). Any other caller, or a value
the engine does not know, is recorded as `other`. The card shows each app's
latest call, and its Activity button opens the list filtered to that app
(`?app=`).

## Access

Two switches, saved in the `agent_access` row of `app_settings`
(`AgentAccessConfig`), both off until the person turns them on:

| Switch | Allows |
|---|---|
| `enabled` | every read operation |
| `allow_writes` | the write operations, and only while `enabled` is also on |

Beside the switches, each data category can be kept from assistants and each
action group switched off
([decision 0017](decisions/0017-agent-access-open-by-default.md)). The engine
reads them on every call, so a change in Settings applies to a connected agent
at once. A refused call answers `access_disabled`, `writes_disabled` or
`category_disabled` (exit status 4) and names the setting to change: a write
whose group is off is `writes_disabled` naming `agent_access.groups.<group>`.
The Settings card saves `allow_writes` with `enabled`, one switch for both, so
it never saves `allow_writes` on without `enabled`.

No operation sends a message, applies to a job, contacts anyone, deletes data
or changes these settings. Every pursuit write appends a `pursuit_events` row
with actor `agent` in the same transaction, so the person can correct any agent
write in the dashboard and the event log keeps both versions.

A duplicate verdict (`duplicates.decide`, action group `tuning_radar`) records
`decided_by` `agent` and the assistant's one-line reason on the pair; a row
with no `decided_by` was decided by the person. An assistant never replaces the
person's verdict: such a pair answers `decided_by_person` and the rest of the
batch goes ahead. A pair it is unsure about stays pending for the person with
its note. The Review screen marks the assistant's verdicts with their reasons,
and the person changes any of them there
([decision 0024](decisions/0024-an-assistant-decides-duplicates.md)).

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

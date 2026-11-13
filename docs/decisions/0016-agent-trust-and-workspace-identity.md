# 0016: Same-account trust on macOS, and a durable workspace identity

## Context

On macOS the engine's HTTP is not authenticated: `local_http.required()` is
false there, so any process of the signed-in user can call loopback routes.
The packaged Windows engine requires a signed request on every `/api/` route,
reads included, with the control or a browser key. The MCP server already
reads and writes under the person's two switches with no credential of its own.

An agent needs to know which engine answered. The engine's discovery record
names an `instance` that changes with every engine session, so it cannot key
anything that must outlive a restart: receipts of writes, named positions in
the changes feed, grants.

## Decision

**Trust mode.** On macOS the first agent connection uses same-account loopback
trust, and says so: the `status` operation reports the mode as `same_account_loopback`.
The engine enforces the person's switches on every call. The command connects
only to `127.0.0.1`, ignores proxy settings and follows no redirect. There is no
silent fallback between trust modes, and no fallback from a development context
to the installed app's port. On packaged Windows an agent request is signed like
any other, so the agent path there needs a credential for reads as well as
writes.

**Workspace identity.** The engine keeps a durable `workspace_id` for the
person's data store, in that store, and creates it before it first returns it;
the command never creates one. It survives an engine restart, an app update
and a moved app. The rotating discovery `instance` is reported apart from it as
`engine_session_id`. Receipts, cursors and grants are keyed by `workspace_id`;
nothing is keyed by an engine session, a checkout path or a bundle path. A copy
of a database made for scratch work gets a new workspace identity before an
agent uses it; restoring a backup over the original keeps the original's.

## Consequences

- Reads and the person's own writes ship on macOS without a new credential,
  under exactly the switches the MCP server uses today.
- This mode does not separate one same-account process from another. A hostile
  program running as the person can call the engine directly; nothing in the
  agent path claims otherwise.
- Telling assistants apart, or restricting one of them, needs a distinct agent
  credential bound to a principal and the workspace. Reusing the control key
  with a caller-supplied client name would let any holder act as any client.
- A context bound to one `workspace_id` refuses an engine that reports another,
  so a scratch engine is never mistaken for the person's.

## Alternatives considered

- **Verified engine discovery on macOS first.** The command would read an
  account-private discovery record and verify signed responses, as on Windows.
  It proves which engine answered, not who is calling, and the middleware's
  origin and discovery assumptions would need rework for the dashboard's own
  browser path; it adds work before the first read without adding protection
  against a same-account process.
- **Key everything by the engine session.** Every restart would orphan receipts
  and cursors and make a lost reply unrecoverable.
- **Let the command create the identity.** Two clients could mint two
  identities for one store.

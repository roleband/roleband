# 0010: A Windows update is journaled and settled by the version that runs next

## Context

Windows replaces an MSIX outside any transaction RoleBand controls: once the package
manager switches packages, the old program may never run again, and the new one starts
with whatever schema the retained database has. The update therefore cannot be one
process's transaction. Every entry point (the app, a second app process, login, a toast,
an external MCP client) must still refuse to open the database while an update is half
done, and the next version to run must know whether the switch happened.

## Decision

Before the package manager is asked to replace the package, the engine writes
`recovery/update.json` (format 1, `package-update`): an ID, the state, the from and to
versions, the retained verified package and its digest, and phase `applying`. It is
written only from a retained package that verifies against the installed identity
([decision 0009](0009-windows-release-authorization.md)) and only while no engine runs.

The version that runs next settles it: the to-version moves it to `preparing`, runs its
preparation, which checkpoints before migrating
([decision 0008](0008-windows-pre-migration-checkpoints.md)), and records `complete` or
`failed`; the from-version finding `applying` records `aborted`, because the switch never
happened. A failed update is recovered to `recovered`. While the journal says `applying`,
`failed` or `recovering`, the native host and the Python database chokepoint both refuse
to start; `preparing` is allowed, since the engine lease keeps a second engine out. A
damaged journal is refused and preserved. `desktop.py update begin|resume|settle` writes it;
nothing else does.

## Consequences

A crash or power loss at any point leaves a journal the next start can read, and the
database is never opened by a version that does not match it. Both readers share the
`update` cases of `launcher/windows/contracts/retained-records.json`;
`tests/test_windows_update_journal.py` covers the transitions.

## Alternatives considered

Letting the old version wait for the switch and then verify the new one cannot work: the
package manager stops it. Detecting an update only from a schema change misses an update
that changes no schema and cannot tell a failed switch from no switch.

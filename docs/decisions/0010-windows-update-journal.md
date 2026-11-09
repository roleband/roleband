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
([decision 0009](0009-windows-release-authorization.md)), only while no engine runs, and
only when the running version's own package is kept too, so the update can be undone.

The version that runs next settles it: the to-version moves it to `preparing`, runs its
preparation, which checkpoints before migrating
([decision 0008](0008-windows-pre-migration-checkpoints.md)), and records `complete` or
`failed`; the from-version finding `applying` records `aborted`, because the switch never
happened. A failed update is recovered to `recovered`. While the journal says `applying`,
`failed` or `recovering`, the native host and the Python database chokepoint both refuse
to start; `preparing` is allowed, since the engine lease keeps a second engine out. A
damaged journal is refused and preserved. `desktop.py update begin|resume|settle` writes it;
nothing else does.

The native host's `UpdateCoordinator` drives it. To apply, it stops the engine, has the
journal begun, registers the app for restart and asks Windows' package manager to replace
the package with app shutdown forced; if Windows refuses, it resumes the journal, which
records `aborted`. Every Start resumes the journal before the engine starts; when that run
is the new version, Ready settles the update `complete`, and a failed database preparation
settles it `failed`. The engine reports that failure and waits to be stopped rather than
exiting, so the host does not take it for a crash and restart it into the same failure. An
engine that exits before it is ever Ready until the restart limit also settles it `failed`.
Other trouble, such as a start refused before an engine runs, leaves it `preparing` for the
next start.

A failed update stays closed and offers Undo. The new version marks it `recovering` and
registers the retained previous package again, as a downgrade. The previous version's next
Start puts the database back before the engine starts: it restores the pre-migration
checkpoint recorded for this update's ID, through the ordinary promotion that keeps the
replaced database, and records `recovered`. Without a checkpoint for this update the schema
never changed, so the database stays; a checkpoint from an earlier update is never
restored, because history written since would be lost. The new version never reached Ready,
so nothing was written after the checkpoint. If the previous package is somehow missing, Undo
says so and nothing is registered.

## Consequences

A crash or power loss at any point leaves a journal the next start can read, and the
database is never opened by a version that does not match it. Both readers share the
`update` cases of `launcher/windows/contracts/retained-records.json`;
`tests/test_windows_update_journal.py` covers the transitions.

## Alternatives considered

Letting the old version wait for the switch and then verify the new one cannot work: the
package manager stops it. Detecting an update only from a schema change misses an update
that changes no schema and cannot tell a failed switch from no switch.

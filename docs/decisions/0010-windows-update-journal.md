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
records `aborted`. Windows installs while the old version stays open, closing it only at the end, and
the app shows Windows' own percentage meanwhile. The old version can also be opened again while
Windows still installs; before its start settles `applying` as never having happened, it reads
Windows' deployment log (AppXDeploymentServer/Operational) for an install of the new package
since the journal began: one still running is waited for, a failed one is said with Windows'
reason and then settled as not having happened, and none found is settled as before. Every
Start resumes the journal before the engine starts; when that run
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
so nothing was written after the checkpoint. If the previous package is missing, Undo
downloads that version's release and verifies it like any update; if it cannot, it says so and
nothing is registered. It tells a lost connection, a full disk and a release the feed no longer
has apart: for the last, Undo is not offered again, and the update stays `failed` for a newer
release to take over.

No broken update leaves a person stuck. Besides Undo, a newer release takes over a failed or
unfinished update: from the app, a failed version may begin an update to a newer one, and a newer
version installed by hand, the way out when a version cannot even open, settles whatever it finds
unfinished. The update keeps its ID and its previous version, so Undo still returns to the
version from before it and to the checkpoint taken before its first migration, which later
preparations of the same update reuse whatever the failed version left. A takeover Windows did
not switch to leaves the failed version failed, with Undo. The previous version installed again
by hand over an update that never became ready finishes it as Undo would: it marks the update
`recovering` and puts back the database from before it.

## Consequences

A crash or power loss at any point leaves a journal the next start can read, and the
database is never opened by a version that does not match it. Both readers share the
`update` cases of `launcher/windows/contracts/retained-records.json`;
`tests/test_windows_update_journal.py` covers the transitions.

Each step runs in one version's code. The running version checks, downloads, keeps the way
back, begins and asks Windows to install; the new version prepares and records a failure; a
failed version downloads the previous release and asks Windows to put it back; the previous
version restores the database. So a change to recovery helps only updates from a release that
already carries it, and the journal keeps the keys, format and phases every earlier version
reads: any version refuses another shape as damaged.

## Alternatives considered

Letting the old version wait for the switch and then verify the new one cannot work: the
package manager stops it. Detecting an update only from a schema change misses an update
that changes no schema and cannot tell a failed switch from no switch.

# 0007. Windows checkpoint promotion and reader contracts

## Context

A scratch restore proves that a checkpoint can be read. Recovery also needs an
offline operation that puts verified history back at the retained database path,
preserves the failed database, and survives termination between directory moves.
Installing an older application cannot establish whether its engine understands
the retained storage.

## Decision

Use an explicit checkpoint promotion command with desktop and engine leases. It
requires a stopped app-owned PG16 database, a checkpoint bound to that database's
path and retained owner/password/key hashes, and the repair runtime's exact
Alembic heads. Unbound checkpoints remain usable for scratch verification only.
Checkpoint digests are pinned before preparation; changing either file prevents
resumption. This local binding is an integrity check, not release authentication.

Restore into fresh private storage and verify all checkpoint fingerprints and a
rollback-only write before switching. Transfer the retained database password
through an authenticated SQL parameter and protected passfile. Leave the original
owner record, passfile and Fernet key in place. Recovery cannot invent a missing
key or adopt another account's encrypted settings.

Retain a bounded private journal with `preparing`, `prepared`, `retaining`,
`installing`, `checking`, `complete` and `aborted` phases. Publish journal changes
through a flushed temporary file and handle-based atomic replacement. Readers
share deletion; Windows [replacement semantics](https://learn.microsoft.com/en-us/windows-hardware/drivers/ddi/ntifs/ns-ntifs-_file_rename_information)
let them retain the opened snapshot without blocking publication. Record NTFS
directory identities before moving the old database into the transaction's
retained storage and the restored database into its place. Resume recognizes a
completed rename even when the following journal publication was interrupted.
The coordinator and its descendants use a kill-on-close Windows Job Object.

Before any switch, fence storage with format 2 compatibility metadata and a
positive `minimum_reader` contract. Engines that only understand the exact legacy
format 1 record refuse format 2 before starting PostgreSQL. Compatible engines
adopt legacy metadata while retaining its original record. The native host and
engine entry points reject unsupported reader floors and pending or malformed
restore journals. Explicit recovery may preserve an incompatible failed cluster
without opening it and replace it with a checkpoint the repair engine understands.

`minimum_reader` is the only signal an older engine trusts. A writer that adds a
field or changes the format raises it; an engine reads a format 2 or later record's
floor before checking its shape and, if the floor is above its own contract, asks
for a newer engine rather than reporting damage. A record whose floor the engine
meets must have exactly the shape that engine knows, so a new field without a
raised floor reads as damage.

`restore resume` reuses the journal and rebuilds interrupted preparation in fresh
storage. `restore abort` is allowed only while the original database remains at
its original path; once switching begins, resolution requires resumption. Final
verification opens the promoted database using the original credentials, then
stops it before recording completion. All attempts and the displaced database
remain private and retained; the command deletes no history.

## Consequences

This is an offline operator recovery primitive. Restoring a checkpoint makes its
snapshot the active history; later history remains in the displaced database for
inspection rather than being merged automatically. A retained compatible signed
repair package is required when the installed application cannot run recovery.
Windows can register a lower package version with an explicit
[`Add-AppxPackage -ForceUpdateFromAnyVersion`](https://learn.microsoft.com/en-us/windows/msix/desktop/managing-your-msix-deployment-update)
operation, but package registration and database promotion remain separate steps.

Real database tests cover retained encrypted settings, newer-reader refusal,
process termination and Windows sharing failures around directory promotion.
They do not establish signed package rollback, interrupted Windows deployment,
release-metadata authentication or a complete automatic update transaction.

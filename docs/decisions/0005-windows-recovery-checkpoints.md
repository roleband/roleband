# 0005. Windows recovery checkpoints

## Context

MSIX replaces application files independently of PostgreSQL state retained outside
the package. A readable dump header does not establish that observation history
can be restored. Recovery needs a verified copy before it can replace a database.

## Decision

Use logical PG16 checkpoints with account-private storage and a fresh-cluster
restore drill. The database fingerprint and `pg_dump` share a repeatable-read
[exported snapshot](https://www.postgresql.org/docs/16/functions-admin.html#FUNCTIONS-SNAPSHOT-SYNCHRONIZATION).
The fingerprint covers ordinary and partitioned tables, materialized views,
columns, indexes, constraints, extension versions, schema heads and sequence state.
CHECK and partial-index predicates use PostgreSQL's planned expression output:
dump/restore can move array casts onto constants while preserving their meaning.
Other definition details remain part of the comparison.
Rows are streamed in deterministic JSON order, with UTC timestamps and UTF-8.
Sequence changes during export prevent publication because sequence values are
not transactional snapshots. Foreign tables are refused.

Restore uses the matching PG16 tools, a fresh private cluster and
[`pg_restore --single-transaction --exit-on-error`](https://www.postgresql.org/docs/16/app-pgrestore.html).
The restored fingerprint must match before a rollback-only temporary-table write
checks that the result is writable. The source is never a restore target. Existing
verification state, overlapping storage and reparse-point paths are refused.
Archive hashes are checked before creating a verification cluster.

The builder writes a completion manifest only after this drill succeeds, then
publishes the checkpoint directory with a non-replacing rename. Failed partial
checkpoints and stopped scratch clusters remain available for diagnosis. Previous
checkpoints are retained. The dump excludes account credentials and the retained
Fernet key, whose recovery requires their own ownership and transfer contract.

The explicit-path desktop checkpoint command acquires the desktop and engine
leases, requires an existing app-owned stopped cluster and an existing database,
and stops only the source server it starts. It cannot promote a restored database,
change the source schema or replace an installed package.

## Consequences

A checkpoint consumes space for the archive and a full restored cluster. Export
and deterministic row sorting can be expensive; the fingerprint streams rather
than loading table contents into Python memory. A checkpoint proves a restore
against its matching runtime, not compatibility with an arbitrary future engine.

Checkpoint creation is a recovery primitive. Package authorization, durable
transaction state, all-entry-point recovery guards, retained executable recovery,
failed-database preservation and atomic promotion remain necessary before a
production update can claim recoverable replacement.

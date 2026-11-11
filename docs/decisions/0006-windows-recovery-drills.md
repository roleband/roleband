# 0006. Windows recovery drill journals

## Context

A verified logical checkpoint establishes a recoverable copy. Process termination
can still leave a restore attempt running or partially initialized. Ordinary
startup must not silently bypass an unfinished recovery operation, and the
operator needs an executable way to retry or resolve it.

## Decision

Retain an account-private, bounded journal for scratch-only checkpoint drills.
Acquire the desktop and engine leases and require the current database to be
stopped before beginning, retrying or abandoning a drill. Pin both the checkpoint
manifest and archive digest before publishing the first journal. Each attempt
restores into a new UUID-named directory. Earlier attempts and completed journals
remain available for diagnosis.

Write journal changes to a fresh file, flush its contents, then replace the journal
through the temporary file's handle with
[POSIX replacement semantics](https://learn.microsoft.com/en-us/windows-hardware/drivers/ddi/ntifs/ns-ntifs-_file_rename_information)
and flush the result, as decision 0007 describes: a reader that shares deletion keeps
the snapshot it opened. Record `verifying` before starting the
scratch cluster and `verified` only after the checkpoint verifier confirms matching
history, a rollback-only write and cluster shutdown. An exception records `failed`;
process termination leaves the previous durable record.

The drill command contains itself and all scratch descendants in a Windows
kill-on-close Job Object before creating the journal. This includes initialization
and database start, so termination cannot leave a child that starts a server after
the retry has inspected the old attempt. The current database is never started in
this job. Dead PID files remain diagnostic evidence in storage that is never reused.

The native host, desktop run/prepare/seed entry points and Windows embedded-server
entry point refuse unfinished or malformed journals. The native host reports the
condition before spawning instead of spending its automatic restart budget.
`desktop.py recovery status` inspects the record. `retry` stops verified owned
scratch servers and restores the pinned checkpoint into another fresh directory.
Dead initialization PID files remain in the abandoned attempt; a foreign process
or uncertain identity blocks resolution. `abandon` stops scratch servers, preserves
all attempts and allows the unchanged current database to start. Abandonment is
valid only for this scratch-only operation kind. A future operation that changes
live state must define its own recovery contract.

## Consequences

Retry and abandonment are tested against real process termination during journal
publication, PostgreSQL initialization and scratch restore. Neither operation
promotes a database or modifies the current database, its credentials or retained
Fernet key. A successful drill verifies the checkpoint rather than the application's
current database. This journal does not authorize package replacement or migration.
Compatibility records, retained trusted recovery executables and failed-database
preservation during promotion remain separate requirements for production updates.

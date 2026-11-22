# 0020: The changes feed reads in commit order, below the oldest open transaction

## Context

`changes.list` gives an agent what changed after a position it holds, and the
position must neither lose nor repeat an event. The records it reads
(`job_lifecycle_events`, `scrape_source_runs`, `plugin_run_ends`) are ordered by a bigint id from
a sequence, but the id is taken when the row is inserted, not when it commits.
Two writers run at once (a scrape run and a page read, say): the first takes id
10 and stays open, the second takes id 11 and commits. A reader that answers
row 11 and remembers "after 11" never sees row 10 when it commits. A wall-clock
time has the same flaw, and a sequence drawn at commit is no better, since two
commits can draw it in either order.

The ids of Postgres transactions have a property the row ids lack: every
transaction below the oldest one still running has ended, so no row can later
commit there. `xid8` gives that id in 64 bits, so it never wraps.

## Decision

- Each record the feed reads carries the inserting transaction's id
  (`change_xact xid8`, default `pg_current_xact_id()`) and the system identifier
  of the cluster that assigned it (`change_cluster`). Writers set neither.
- A read fixes a frontier: the oldest transaction of this database still
  running when it starts, prepared transactions included, or the snapshot's end
  when none is. It answers rows of the cluster whose `change_xact` is at or past
  the previous position and below the frontier, ordered by transaction, record
  and id; a row of a transaction still open waits for a later read. Only this
  database's transactions can write its rows, so another database's long
  transaction does not hold the feed. A role that cannot see every session falls
  back to the cluster's oldest running transaction. A window never opens below
  the position it continues, even when that fallback finds a lower frontier: a
  window that moved back would answer its rows again.
- The position (`next_since`) is opaque: the frontier reached, the last row
  read within a window, the wall-clock window for derived due times, and digests
  binding it to the workspace, the principal and the kinds asked for, with the
  cluster's identifier. A read that starts from a `start_time` keeps that bound
  in every position after it, so a row of an older transaction that commits
  later is still left out. It lives with the caller; nothing about it is held in the
  engine process, so an engine restart changes nothing.
- A position that cannot continue is refused as `invalid_input` with a reason
  (`malformed`, `other_workspace`, `other_principal`, `other_filters`,
  `expired`) and the `changes.list` call to start again, never reset to the
  start or to now.
- Rows written before the columns existed (NULL), and rows restored from
  another cluster, carry no position this cluster can order. They are history
  that a read from the beginning or from a `start_time` answers first, by id.
- A record is inserted, never updated: a row its writer rewrites has no place
  in commit order. A plugin run's row is rewritten while it runs and when it
  ends, so the transaction that closes a run also inserts its end into
  `plugin_run_ends`, once per run; that table is the plugin record.
- A kind with no ordered record of its own is derived at the read and labelled
  so (a repost label, a source's or a plugin job's health move, a pursuit's due
  time) or reported unavailable.
- A due reminder must still be active when the feed reads it. Its latest
  scheduling or reactivation event in `pursuit_events` carries the same
  transaction position as the other records. The feed returns the reminder
  once its deadline has passed and its schedule is below the transaction
  frontier. Either crossing can happen first: a scheduled reminder becomes
  due in a later wall-clock window, or an already overdue schedule becomes
  visible in a later transaction window. A schedule with no position in this
  cluster uses only the wall-clock window.

## Consequences

- A long-open write transaction in the database delays the feed until it ends;
  it cannot cost it an event. The writers commit per batch already (AGENTS.md).
- A restore into a new cluster, or a major Postgres upgrade that changes the
  system identifier, expires every position given out before; the refusal names
  the time to start again from. Rows written while the schema is downgraded read
  as history after the upgrade, as rows from before the columns do. A plugin
  run closed before `plugin_run_ends` existed, or by code that does not know
  it, has no end there and is never reported; the next recorded end of its job
  is still compared with it, unless it was stopped, since a stopped run is left
  out of every comparison.
- Delivery is at least once: the same `since` answers the same page again, and
  each event's `sequence` is stable for deduplication.
- `tests/test_agent_changes_db.py` holds the order with two writers, one held
  open across a read, beside a naive id cursor that loses the late commit;
  `tests/test_cli_changes.py` continues a position across a real engine restart.

## Alternatives considered

- **The row id as the position.** Loses a row that commits after a reader
  passed its id; the negative control in the tests shows it.
- **A sequence or timestamp taken at commit** (a deferred trigger). Two commits
  can take it in either order, so the same loss returns, and every writer pays a
  trigger.
- **A change table filled after commit by one assigner.** Ordered by
  construction, but a read would have to write (no GET commits), or a background
  job would own a second copy of every event.
- **The cluster's oldest running transaction** (`pg_snapshot_xmin`) alone.
  Correct, but a transaction in any other database of the cluster, a restore
  copy beside the live one for instance, would hold the feed back; it remains
  the fallback.

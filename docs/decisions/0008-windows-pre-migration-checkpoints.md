# 0008: Windows migrations start from a verified checkpoint

## Context

Every engine start runs preparation, which upgrades the schema when the engine's
migrations are newer than the retained database. On Windows the only executable
way back from a database is promoting a bound checkpoint
([decision 0007](0007-windows-checkpoint-promotion.md)); a plain `pg_dump` in
`backups/` is not one. A failed or harmful migration therefore needs a checkpoint
of the database as it was, made before the upgrade and bound to its heads and
retained credentials, so that the previous package can promote it.

## Decision

On Windows, preparation creates a pre-migration checkpoint before any upgrade of
a schema that already has a revision, and does not upgrade if it cannot. The
checkpoint is a normal [recovery checkpoint](0005-windows-recovery-checkpoints.md):
exported from one snapshot, restored into fresh scratch storage, compared by
fingerprint and published only after that matches. It lives in
`recovery/pre-migration/<id>` with its scratch cluster in
`recovery/pre-migration-checks/<id>`, and `recovery/pre-migration.json` names the
latest one with the heads it migrates from and to.

A retry reuses the named checkpoint when its archive is intact and the live
database still matches its fingerprints and retained credentials, which is the
case after a migration that failed and rolled back. Anything else gets a new one.
Checkpoints are never removed by preparation.

A pre-migration checkpoint may hold an empty `jobs` table; its manifest says
`"purpose": "pre-migration"`. The engine takes it of the database it claims, so the
rule that keeps an operator from establishing recovery from an empty database
does not apply, and an install that updates before its first scan can still start.
Operator checkpoints keep that rule.

## Consequences

An update with a migration costs one export, one scratch restore and their disk
space, about twice the database, kept until someone removes them. Promotion still
requires the runtime whose heads match the checkpoint, so recovering from a
migration needs the previous signed package, as decision 0007 states.
`tests/test_windows_migration.py` holds the contract: a failed migration leaves a
verified checkpoint at the previous heads; a migration runs only after its
checkpoint; no checkpoint means no migration; a current schema takes none.

## Alternatives considered

Refusing to migrate unless an operator made a fresh checkpoint makes every update
a manual step. Keeping the plain dump leaves no Windows command that can use it.
Cleaning up older checkpoints automatically would delete recovery copies without
the owner's say; retention stays a separate, explicit decision.

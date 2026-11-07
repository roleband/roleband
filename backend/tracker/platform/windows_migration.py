"""Protect retained Windows data with a verified checkpoint before its schema changes."""

from __future__ import annotations

import sys
import uuid
from collections.abc import Iterable
from datetime import UTC, datetime
from pathlib import Path

from tracker.platform.embedded_db import EmbeddedServer

if sys.platform != "win32":
    raise ImportError("Windows migration checkpoints require Windows")

#: Names the latest pre-migration checkpoint, for `restore begin` with the previous package.
RECORD = Path("recovery") / "pre-migration.json"


def checkpoint_before_migration(server: EmbeddedServer, state: Path, current: Iterable[str],
                                target: Iterable[str]) -> Path:
    """Return a verified bound checkpoint of the database as it is before migrating.

    Raises instead of returning when none can be made, so the caller never migrates
    unprotected data. A retry after a failed migration reuses the recorded checkpoint
    when the database still matches it, since a failed upgrade rolls back.
    """
    from tracker.platform.windows_checkpoint import PRE_MIGRATION, create_checkpoint, still_matches
    from tracker.platform.windows_private import private_directory
    from tracker.platform.windows_storage import StorageCompatibilityError, read_json, write_json

    record = state / RECORD
    if record.exists():
        try:
            previous = Path(str(read_json(record).get("checkpoint", "")))
        except StorageCompatibilityError:
            previous = None
        if previous is not None and previous.is_absolute() and still_matches(server, previous):
            return previous
    name = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid.uuid4().hex[:8]
    checkpoints, checks = state / "recovery" / "pre-migration", state / "recovery" / "pre-migration-checks"
    private_directory(state / "recovery")
    private_directory(checkpoints)
    private_directory(checks)
    checkpoint = create_checkpoint(server, checkpoints / name, checks / name, purpose=PRE_MIGRATION)
    write_json(record, {"format": 1, "checkpoint": str(checkpoint), "from_heads": sorted(current),
                        "to_heads": sorted(target), "created_at": datetime.now(UTC).isoformat()})
    return checkpoint

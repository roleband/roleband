"""The journal of one package update, which every entry point reads before opening the database.

Windows replaces the package outside any transaction RoleBand controls, and the old program
may not run again. So the journal is written before the replacement and settled by whichever
version starts next: the new version moves it to `preparing` and, once its database is
prepared and healthy, to `complete`; the old version finding it still `applying` knows the
switch never happened, and puts back the database when a failed version of the update had
migrated it. While it says `applying`, `failed` or `recovering`, nothing opens the database.
`preparing` is allowed: the engine lease already keeps a second engine out.
"""

from __future__ import annotations

import json
import re
import sys
import uuid
from contextvars import ContextVar
from pathlib import Path
from typing import Any

if sys.platform != "win32":
    raise ImportError("Windows update journals require Windows")

from tracker.platform.windows_fs import checked_path, publish, read_private
from tracker.platform.windows_recovery import RecoveryError
from tracker.platform.windows_release import ReleaseError, stable_version

PHASES = ("applying", "preparing", "complete", "failed", "aborted", "recovering", "recovered")
RESOLVED = frozenset({"complete", "aborted", "recovered"})
BLOCKING = frozenset({"applying", "failed", "recovering"})
LIMIT = 64 * 1024
#: Set while recovery itself restores the database, the one opening `recovering` allows.
_recovering: ContextVar[Path | None] = ContextVar("recovering_update", default=None)
_KEYS = {"format", "kind", "id", "state", "from_version", "to_version", "package", "package_sha256", "phase"}


def journal(state: Path) -> Path:
    return state / "recovery" / "update.json"


def _valid(record: Any, state: Path) -> dict[str, Any]:
    try:
        if (not isinstance(record, dict) or set(record) != _KEYS or type(record["format"]) is not int or record["format"] != 1
                or record["kind"] != "package-update" or record["state"] != str(state)
                or not isinstance(record["id"], str) or not re.fullmatch(r"[0-9a-f]{32}", record["id"])
                or record["phase"] not in PHASES or not isinstance(record["package"], str)
                or not Path(record["package"]).is_absolute() or not isinstance(record["package_sha256"], str)
                or not re.fullmatch(r"[0-9a-f]{64}", record["package_sha256"])
                or stable_version(record["from_version"]) >= stable_version(record["to_version"])):
            raise ValueError("shape")
    except (ValueError, ReleaseError) as error:
        raise RecoveryError("The update journal is damaged or unsupported; preserve it for repair") from error
    return record


def read(state: Path) -> dict[str, Any] | None:
    path = journal(state)
    if not path.exists():
        return None
    try:
        record = json.loads(read_private(path, LIMIT))
    except (ValueError, UnicodeError) as error:
        raise RecoveryError("The update journal is damaged or unsupported; preserve it for repair") from error
    return _valid(record, state)


def require_launchable(state: Path) -> None:
    record = read(state)
    if record is not None and record["phase"] in BLOCKING:
        if record["phase"] == "recovering" and _recovering.get() == state:
            return
        raise RecoveryError(f"A Windows update from {record['from_version']} to {record['to_version']} is unfinished. "
                            "Open RoleBand to finish or recover it before anything else uses the database.")


def _write(state: Path, record: dict[str, Any]) -> dict[str, Any]:
    from tracker.platform.windows_private import private_directory

    private_directory(state / "recovery")
    publish(journal(state), (json.dumps(_valid(record, state), indent=2) + "\n").encode("utf-8"))
    return record


def failed_in(record: dict[str, Any] | None, running: str) -> bool:
    """Whether `running` is the new version of the unsettled update `record`, and that update failed, an Undo Windows
    did not carry out included. From there Undo returns to the previous version, and a newer release takes over."""
    return record is not None and record["phase"] in {"failed", "recovering"} and running == record["to_version"]


def way_back(record: dict[str, Any] | None, running: str) -> str:
    """The version an update begun by `running` returns to on Undo: the running one, or, when it takes over a failed
    update, the version from before that update, whose checkpoint Undo restores."""
    return record["from_version"] if record is not None and failed_in(record, running) else running


def _checkpoint_record(state: Path) -> Path:
    return state / "recovery" / "pre-migration.json"


def _migrated(state: Path, record: dict[str, Any]) -> bool:
    """Whether a version of this update may have migrated the database: the pre-migration checkpoint was made for
    it, or its record cannot be read to say otherwise."""
    from tracker.platform.windows_storage import StorageCompatibilityError, read_json

    marker = _checkpoint_record(state)
    if not marker.exists():
        return False
    try:
        return read_json(marker).get("update_id") == record["id"]
    except StorageCompatibilityError:
        return True


def begin(state: Path, *, from_version: str, to_version: str, package: Path, package_sha256: str) -> dict[str, Any]:
    """Record the replacement about to happen; refused while another update is unsettled."""
    state = checked_path(state)
    current = read(state)
    if current is not None and current["phase"] not in RESOLVED:
        # A newer release takes over a failed update from the failed version. The update keeps its id and its
        # previous version, so Undo still returns to the version and the checkpoint from before it began.
        if failed_in(current, from_version) and stable_version(to_version) > stable_version(from_version):
            return _write(state, {**current, "to_version": to_version, "package": str(package),
                                  "package_sha256": package_sha256, "phase": "applying"})
        raise RecoveryError("Another Windows update is unsettled; settle it first")
    return _write(state, {"format": 1, "kind": "package-update", "id": uuid.uuid4().hex, "state": str(state),
                          "from_version": from_version, "to_version": to_version, "package": str(package),
                          "package_sha256": package_sha256, "phase": "applying"})


def resume(state: Path, running: str) -> dict[str, Any] | None:
    """Settle what the running version can know: whether the replacement happened."""
    record = read(state)
    if record is None or record["phase"] in RESOLVED:
        return record
    try:
        version = stable_version(running)
    except ReleaseError:
        return record
    # A newer release installed over an unfinished update, from the app or by hand, takes it over: the way out
    # of a version that cannot even open. It prepares as the update's new version.
    if version > stable_version(record["to_version"]):
        return _write(state, {**record, "to_version": running, "phase": "preparing"})
    if record["phase"] == "applying" and running == record["to_version"]:
        return _write(state, {**record, "phase": "preparing"})
    # The switch never happened. A takeover may still have left the failed version's migration in the database: then
    # this version finishes the update as Undo would, putting back the database from before it.
    if record["phase"] == "applying" and running == record["from_version"]:
        return _write(state, {**record, "phase": "recovering" if _migrated(state, record) else "aborted"})
    # The previous version installed again by hand over an update that never became ready: the same as Undo, so this
    # version finishes it, putting back the database from before the update.
    if record["phase"] in {"preparing", "failed"} and running == record["from_version"]:
        return _write(state, {**record, "phase": "recovering"})
    # A takeover Windows did not switch to: the failed version it started from runs again, still failed.
    if record["phase"] == "applying" and stable_version(record["from_version"]) < version:
        return _write(state, {**record, "to_version": running, "phase": "failed"})
    return record


def undoable(record: dict[str, Any] | None, running: str) -> dict[str, Any]:
    """`record`, when `running` may return it to its previous version; RecoveryError otherwise."""
    if record is None or not failed_in(record, running):
        raise RecoveryError("Only a failed update can be returned to its previous version")
    return record


def recover_begin(state: Path, running: str) -> dict[str, Any]:
    """The new version hands back: the previous package is about to be registered again."""
    return _write(state, {**undoable(read(state), running), "phase": "recovering"})


def recovered(state: Path, running: str) -> dict[str, Any]:
    record = read(state)
    if record is None or record["phase"] != "recovering" or running != record["from_version"]:
        raise RecoveryError("Recovery finishes only in the previous version")
    return _write(state, {**record, "phase": "recovered"})


def recover_database(state: Path, running: str) -> dict[str, Any]:
    """In the previous version: put back the database this update's migration replaced.

    Only a pre-migration checkpoint made for this update is restored. The new version never
    reached Ready, so nothing has been written since it; without one, the schema never
    changed and the database stays as it is. A restore that was interrupted is resumed, and
    the replaced database is kept, as every restore keeps it.
    """
    from tracker.platform.windows_restore import RESOLVED as RESTORE_RESOLVED
    from tracker.platform.windows_restore import read_restore, restore
    from tracker.platform.windows_storage import StorageCompatibilityError, read_json

    state = checked_path(state)
    record = read(state)
    if record is None or record["phase"] != "recovering" or running != record["from_version"]:
        raise RecoveryError("Recovery finishes only in the previous version")
    marker = _checkpoint_record(state)
    try:
        checkpoint = read_json(marker) if marker.exists() else {}
    except StorageCompatibilityError as error:
        raise RecoveryError("The pre-migration record is damaged; preserve it for repair") from error
    if checkpoint.get("update_id") == record["id"]:
        token = _recovering.set(state)
        try:
            current = read_restore(state)
            if current is not None and current["phase"] not in RESTORE_RESOLVED:
                restore(state, "resume")
            elif not (current is not None and current["phase"] == "complete"
                      and current["checkpoint"] == checkpoint["checkpoint"]):
                restore(state, "begin", Path(checkpoint["checkpoint"]))
        finally:
            _recovering.reset(token)
    return recovered(state, running)


def settle(state: Path, running: str, *, prepared: bool) -> dict[str, Any]:
    """The new version's verdict on its own preparation."""
    record = read(state)
    if record is None or record["phase"] != "preparing" or running != record["to_version"]:
        raise RecoveryError("No update is being prepared by this version")
    return _write(state, {**record, "phase": "complete" if prepared else "failed"})

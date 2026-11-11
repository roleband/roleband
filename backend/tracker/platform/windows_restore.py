"""Resume verified checkpoint promotion while retaining the previous database."""

from __future__ import annotations

import os
import re
import sys
import uuid
from contextlib import AbstractContextManager, closing
from contextvars import ContextVar
from pathlib import Path
from typing import Any

import psycopg2
from psycopg2 import sql

if sys.platform != "win32":
    raise ImportError("Windows restore requires Windows")

from tracker.platform.windows_fs import checked_path, move
from tracker.platform.windows_leases import lease
from tracker.platform.windows_recovery import RecoveryError, _pin, _quiesce, recovery_leases
from tracker.platform.windows_storage import (
    READER_CONTRACT,
    metadata,
    read_json,
    retained_profile,
    validate,
    write_json,
)

PHASES = {"preparing", "prepared", "retaining", "installing", "checking", "complete", "aborted",
          "reinstating", "reinstated"}
#: Phases that leave the retained database launchable.
RESOLVED = {"complete", "aborted", "reinstated"}
#: Phases in which the original database may have left its path.
SWITCHED = {"retaining", "installing", "checking", "reinstating"}
_checking: ContextVar[Path | None] = ContextVar("windows_restore_checking", default=None)


def _journal(state: Path) -> Path:
    return checked_path(state / "recovery" / "restore.json")


def read_restore(state: Path) -> dict[str, Any] | None:
    state = checked_path(state)
    path = _journal(state)
    if not path.exists():
        return None
    record = read_json(path)
    try:
        if (type(record.get("format")) is not int or record.get("format") != 1
                or record.get("kind") != "checkpoint-restore" or record.get("state") != str(state)
                or record.get("phase") not in PHASES or not re.fullmatch("[0-9a-f]{32}", record["id"])
                or not isinstance(record["checkpoint"], str) or not Path(record["checkpoint"]).is_absolute()
                or not all(re.fullmatch("[0-9a-f]{64}", record[key]) for key in ("manifest_sha256", "archive_sha256"))
                or not isinstance(record["profile"], dict) or set(record["profile"]) != {"owner", "password", "key"}
                or not all(value is None and key == "key" or isinstance(value, str) and re.fullmatch("[0-9a-f]{64}", value)
                           for key, value in record["profile"].items())
                or not isinstance(record["attempts"], list) or len(record["attempts"]) > 256
                or record["phase"] not in {"preparing", "aborted"} and not record["attempts"]
                or not all(isinstance(item, str) and re.fullmatch("[0-9a-f]{32}", item) for item in record["attempts"])
                or len(set(record["attempts"])) != len(record["attempts"])):
            raise ValueError("unsupported restore journal")
        validate(record["original_metadata"], state / "db", require_reader=False)
        _identity_record(record["original_directory"])
        if record["phase"] not in {"preparing", "aborted"}:
            _identity_record(record["restored_directory"])
    except (ValueError, TypeError, KeyError) as error:
        raise RecoveryError("Restore journal is damaged or unsupported; preserve it for repair") from error
    return record


def _identity_record(value: Any) -> None:
    if (not isinstance(value, list) or len(value) != 2 or any(type(item) is not int for item in value)
            or value[0] < 0 or value[1] <= 0):
        raise ValueError("unsupported directory identity")


def require_launchable(state: Path) -> None:
    state = checked_path(state)
    record = read_restore(state)
    if record is not None and record["phase"] not in RESOLVED:
        if record["phase"] == "checking" and _checking.get() == state:
            return
        raise RecoveryError("Database restore is unfinished. With a compatible signed repair package, use restore "
                            "resume to finish it or restore reinstate to return the original database.")
    marker = state / "db.auth" / "cluster.json"
    if marker.exists():
        validate(read_json(marker), state / "db")


def _identity(path: Path) -> list[int]:
    from tracker.platform.windows_private import require_private

    checked_path(path)
    require_private(path)
    if not path.is_dir():
        raise RecoveryError("Restore storage is not an ordinary directory")
    info = path.stat()
    identity = [info.st_dev, info.st_ino]
    _identity_record(identity)
    return identity


def _matches(path: Path, identity: list[int]) -> bool:
    return path.exists() and _identity(path) == identity


def _save(state: Path, record: dict[str, Any], phase: str) -> None:
    record["phase"] = phase
    write_json(_journal(state), record)


def _paths(state: Path, record: dict[str, Any]) -> tuple[Path, Path, Path]:
    directory = checked_path(state / "recovery" / ("restore-" + record["id"]))
    failed = directory / "retained-db"
    staged = directory / record["attempts"][-1] if record["attempts"] else directory / "unused"
    return directory, failed, staged


def _startup_lease(state: Path) -> AbstractContextManager[None]:
    return lease(state / "db.auth" / "startup.lock")


def _check_profile(state: Path, record: dict[str, Any]) -> None:
    if retained_profile(state / "db") != record["profile"]:
        raise RecoveryError("Retained credentials, owner or encryption key changed; restore cannot continue")
    current = validate(read_json(state / "db.auth/cluster.json"), state / "db", require_reader=False)
    original = record["original_metadata"]
    allowed = [original, metadata(state / "db", minimum_reader=original.get("minimum_reader", 1))]
    if record["phase"] in {"installing", "checking", "complete", "reinstating"}:
        allowed.append(metadata(state / "db"))
    if current not in allowed:
        raise RecoveryError("Storage compatibility metadata changed during restore")


def _manifest(state: Path, record: dict[str, Any]) -> dict[str, Any]:
    from alembic.script import ScriptDirectory

    checkpoint = checked_path(Path(record["checkpoint"]))
    # A pre-migration checkpoint is the one kind kept inside the state; its folder is never
    # moved, staged into or restored over.
    inside = checkpoint.is_relative_to(state) and checkpoint.parent != state / "recovery" / "pre-migration"
    if inside or state.is_relative_to(checkpoint):
        raise RecoveryError("Restore checkpoint must be separate from retained state")
    if _pin(checkpoint) != (record["manifest_sha256"], record["archive_sha256"]):
        raise RecoveryError("Restore checkpoint changed after the operation began")
    from tracker.platform.windows_checkpoint import MANIFEST_LIMIT

    manifest = read_json(checkpoint / "checkpoint.json", maximum=MANIFEST_LIMIT)
    heads = sorted(ScriptDirectory(str(Path(__file__).resolve().parents[2] / "alembic")).get_heads())
    if (manifest.get("format") != 1 or manifest.get("postgres_major") != 16 or manifest.get("verified") is not True
            or manifest.get("source_pgdata") != str((state / "db").resolve())
            or manifest.get("reader_contract") != READER_CONTRACT or manifest.get("retained_profile") != record["profile"]
            or not isinstance(manifest.get("facts"), dict) or manifest["facts"].get("schema_heads") != heads
            or not isinstance(manifest.get("source_database"), str)
            or not re.fullmatch("[A-Za-z_][A-Za-z0-9_]{0,62}", manifest["source_database"])):
        raise RecoveryError("Checkpoint does not bind this account's credentials/key and the repair runtime's schema")
    return manifest


def _prepare(state: Path, record: dict[str, Any], manifest: dict[str, Any]) -> None:
    from tracker.platform.embedded_db import ensure_server
    from tracker.platform.windows_checkpoint import _restore, verify_restored
    from tracker.platform.windows_private import private_directory, require_private

    directory, _failed, _staged = _paths(state, record)
    private_directory(directory)
    for attempt in record["attempts"]:
        old = checked_path(directory / attempt)
        if old.exists():
            require_private(old)
            _quiesce(old / "db")
    if len(record["attempts"]) >= 256:
        raise RecoveryError("Restore attempt limit reached; preserve the operation for repair")
    record["attempts"].append(uuid.uuid4().hex)
    _save(state, record, "preparing")
    _directory, _failed, staged = _paths(state, record)
    _restore(Path(record["checkpoint"]), manifest, staged, database=manifest["source_database"])
    # The retained password is transferred only through a protected file and an
    # authenticated SQL parameter; it never appears in process arguments or logs.
    passfile = state / "db.auth/pgpass.conf"
    secret = passfile.read_text(encoding="utf-8")
    match = re.fullmatch(r"127\.0\.0\.1:\*:\*:postgres:([A-Za-z0-9_-]{64})\n", secret)
    if match is None:
        raise RecoveryError("Retained database credentials use an unsupported format")
    server = ensure_server(staged / "db", database=manifest["source_database"])
    try:
        with closing(psycopg2.connect(server.dsn(), connect_timeout=5)) as connection:
            connection.autocommit = True
            with connection.cursor() as cursor:
                cursor.execute(sql.SQL("ALTER ROLE {} PASSWORD %s").format(sql.Identifier("postgres")), (match[1],))
        destination = staged / "db.auth/pgpass.conf"
        require_private(destination)
        with destination.open("wb") as stream:
            stream.write(passfile.read_bytes())
            stream.flush()
            os.fsync(stream.fileno())
        verify_restored(server, manifest)
    finally:
        _quiesce(staged / "db")
    record["restored_directory"] = _identity(staged / "db")
    write_json(directory / "original-metadata.json", record["original_metadata"])
    _save(state, record, "prepared")


def _reinstate(state: Path, record: dict[str, Any]) -> dict[str, Any]:
    """Return the retained original database to its path after the switch began.

    The restored database is kept beside it as `rejected-db`. Every step checks
    directory identities, so an interrupted reinstatement resumes."""
    directory, failed, _staged = _paths(state, record)
    rejected = directory / "rejected-db"
    current = state / "db"
    if record["phase"] not in SWITCHED or (record["phase"] == "retaining" and not failed.exists()):
        raise RecoveryError("The original database has not moved; abort the restore instead")
    if current.exists():
        _quiesce(current)
    _save(state, record, "reinstating")
    with _startup_lease(state):
        if _matches(current, record["restored_directory"]):
            move(current, rejected)
        elif current.exists() and not _matches(current, record["original_directory"]):
            raise RecoveryError("Cannot identify the database at the retained path; preserve it for repair")
        if not current.exists():
            if not _matches(failed, record["original_directory"]):
                raise RecoveryError("The retained original database was moved or replaced")
            move(failed, current)
        # The original keeps the reader floor it had, so a database that needed a
        # newer engine stays closed to this one.
        floor = record["original_metadata"].get("minimum_reader", 1)
        write_json(state / "db.auth/cluster.json", metadata(current, minimum_reader=floor))
        _check_profile(state, record)
        _save(state, record, "reinstated")
    record["rejected_database"] = str(rejected) if rejected.exists() else None
    return record


def restore(state: Path, action: str, checkpoint: Path | None = None) -> dict[str, Any]:
    from tracker.platform.embedded_db import ensure_server
    from tracker.platform.windows_checkpoint import verify_restored
    from tracker.platform.windows_private import require_private
    from tracker.platform.windows_recovery import read_recovery

    state = checked_path(state)
    if action not in {"begin", "resume", "abort", "reinstate"}:
        raise ValueError("Unsupported restore action")
    with recovery_leases(state, require_stopped=False):
        drill = read_recovery(state)
        if drill is not None and drill["phase"] not in {"verified", "abandoned"}:
            raise RecoveryError("Resolve the unfinished scratch recovery check before restoring")
        record = read_restore(state)
        if action == "begin":
            if record is not None and record["phase"] not in RESOLVED:
                raise RecoveryError("Resume or reinstate the unfinished restore before beginning another")
            if checkpoint is None:
                raise ValueError("A checkpoint is required")
            pgdata = state / "db"
            require_private(pgdata)
            if not (pgdata / "PG_VERSION").is_file() or (pgdata / "PG_VERSION").read_text().strip() != "16":
                raise RecoveryError("Restore requires the existing app-owned PG16 database")
            with _startup_lease(state):
                if (pgdata / "postmaster.pid").exists():
                    from tracker.platform.windows_db import _retire_dead_pid

                    if not _retire_dead_pid(pgdata):
                        raise RecoveryError("Stop the current database before restoring a checkpoint")
                profile = retained_profile(pgdata)
                original = validate(read_json(state / "db.auth/cluster.json"), pgdata, require_reader=False)
                manifest_hash, archive_hash = _pin(checkpoint)
                previous = record
                record = {"format": 1, "kind": "checkpoint-restore", "id": uuid.uuid4().hex, "state": str(state),
                          "phase": "preparing", "checkpoint": str(checked_path(checkpoint)), "manifest_sha256": manifest_hash,
                          "archive_sha256": archive_hash, "profile": profile, "original_metadata": original,
                          "original_directory": _identity(pgdata), "attempts": []}
                _manifest(state, record)
                if previous is not None:
                    move(_journal(state), _journal(state).with_name("restore-completed-" + uuid.uuid4().hex + ".json"))
                _save(state, record, "preparing")
                write_json(state / "db.auth/cluster.json", metadata(pgdata, minimum_reader=original.get("minimum_reader", 1)))
        elif record is None or record["phase"] in RESOLVED:
            raise RecoveryError("There is no unfinished restore")
        _check_profile(state, record)
        directory, failed, staged = _paths(state, record)
        if action == "reinstate":
            return _reinstate(state, record)
        if record["phase"] == "reinstating":
            raise RecoveryError("Reinstatement of the original database is unfinished; run restore reinstate again")
        if action == "abort":
            if record["phase"] not in {"preparing", "prepared", "retaining"} or failed.exists() or not _matches(state / "db", record["original_directory"]):
                raise RecoveryError("The database switch has begun; resume the restore or reinstate the original")
            for attempt in record["attempts"]:
                _quiesce(checked_path(directory / attempt / "db"))
            _save(state, record, "aborted")
            return record
        manifest = _manifest(state, record)
        if record["phase"] == "preparing":
            if not _matches(state / "db", record["original_directory"]) or failed.exists():
                raise RecoveryError("Original database identity changed before restore preparation")
            # Publication of the first journal can precede a failed fence write.
            # Every preparation attempt fences legacy readers before any switch.
            with _startup_lease(state):
                write_json(state / "db.auth/cluster.json", metadata(state / "db", minimum_reader=record["original_metadata"].get("minimum_reader", 1)))
            _prepare(state, record, manifest)
            directory, failed, staged = _paths(state, record)
        if record["phase"] == "prepared":
            _quiesce(staged / "db")
            _save(state, record, "retaining")
        if record["phase"] == "retaining":
            with _startup_lease(state):
                if (state / "db/postmaster.pid").exists():
                    raise RecoveryError("A database process appeared during restore")
                if _matches(state / "db", record["original_directory"]) and not failed.exists():
                    move(state / "db", failed)
                elif (state / "db").exists() or not _matches(failed, record["original_directory"]):
                    raise RecoveryError("Cannot identify the retained database after interruption")
                _save(state, record, "installing")
        if record["phase"] == "installing":
            with _startup_lease(state):
                if not _matches(failed, record["original_directory"]):
                    raise RecoveryError("The retained database was moved or replaced")
                if not (state / "db").exists() and _matches(staged / "db", record["restored_directory"]):
                    move(staged / "db", state / "db")
                elif not _matches(state / "db", record["restored_directory"]) or (staged / "db").exists():
                    raise RecoveryError("Cannot identify the restored database after interruption")
                write_json(state / "db.auth/cluster.json", metadata(state / "db"))
                _save(state, record, "checking")
        if record["phase"] == "checking":
            if not _matches(state / "db", record["restored_directory"]) or not _matches(failed, record["original_directory"]):
                raise RecoveryError("Database identities changed before final restore verification")
            token = _checking.set(state)
            try:
                server = ensure_server(state / "db", database=manifest["source_database"])
                verify_restored(server, manifest)
            finally:
                try:
                    _quiesce(state / "db")
                finally:
                    _checking.reset(token)
            _check_profile(state, record)
            _save(state, record, "complete")
        record["retained_database"] = str(failed)
        return record

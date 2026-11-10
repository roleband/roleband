"""Durable, retryable restore drills that never replace the current database."""

from __future__ import annotations

import hashlib
import json
import re
import sys
import time
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

import psutil

if sys.platform != "win32":
    raise ImportError("Windows recovery requires Windows")

from tracker.platform.windows_fs import RecordTooLarge, checked_path, move, publish, read_private

LIMIT = 128 * 1024
TERMINAL = {"verified", "abandoned"}


class RecoveryError(RuntimeError):
    """Retained recovery state cannot authorize ordinary database access."""


def _journal(state: Path) -> Path:
    return checked_path(checked_path(state) / "recovery" / "check.json")


def read_recovery(state: Path) -> dict[str, Any] | None:
    from tracker.platform.windows_private import require_private

    path = _journal(state)
    if not path.parent.exists():
        return None
    require_private(path.parent)
    if not path.exists():
        return None
    if not path.is_file():
        raise RecoveryError("Recovery journal is not an ordinary bounded file")
    try:
        payload = read_private(path, LIMIT)
    except RecordTooLarge as error:
        raise RecoveryError("Recovery journal is not an ordinary bounded file") from error
    try:
        record = json.loads(payload)
        if (not isinstance(record, dict) or type(record.get("format")) is not int or record.get("format") != 1
                or record.get("kind") != "checkpoint-drill" or record.get("state") != str(checked_path(state))
                or record.get("phase") not in {"verifying", "failed", *TERMINAL}
                or not isinstance(record.get("checkpoint"), str) or not Path(record["checkpoint"]).is_absolute()
                or not all(isinstance(record.get(key), str) and re.fullmatch(r"[0-9a-f]{64}", record[key])
                           for key in ("manifest_sha256", "archive_sha256"))
                or not isinstance(record.get("attempts"), list) or not 1 <= len(record["attempts"]) <= 256
                or not all(isinstance(item, str) and re.fullmatch(r"[0-9a-f]{32}", item) for item in record["attempts"])
                or len(set(record["attempts"])) != len(record["attempts"])):
            raise ValueError("unsupported recovery record")
    except (ValueError, TypeError, UnicodeError) as error:
        raise RecoveryError("Recovery journal is damaged or unsupported; preserve it for repair") from error
    return record


def require_launchable(state: Path) -> None:
    from tracker.platform.windows_restore import require_launchable as require_restore_complete
    from tracker.platform.windows_update_journal import require_launchable as require_update_settled

    require_update_settled(state)
    require_restore_complete(state)
    record = read_recovery(state)
    if record is not None and record["phase"] not in TERMINAL:
        raise RecoveryError("A recovery check is unfinished. Use recovery status, retry or abandon before starting the engine.")


def _write(state: Path, record: dict[str, Any]) -> None:
    encoded = (json.dumps(record, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    if len(encoded) > LIMIT:
        raise RecoveryError("Recovery journal exceeds its size limit")
    publish(_journal(state), encoded)


@contextmanager
def recovery_leases(state: Path, *, require_stopped: bool = True) -> Iterator[None]:
    from tracker.platform.paths import reaches_installed_data
    from tracker.platform.windows_leases import lifecycle_leases

    state = checked_path(state)
    # An installed release restores its own database after Undo; nothing else reaches installed data.
    if reaches_installed_data(state):
        raise RecoveryError("Trial recovery cannot reach an installed app's data")
    with lifecycle_leases(state):
        if require_stopped and (state / "db" / "postmaster.pid").exists():
            raise RecoveryError("Stop the current database before starting or resolving a recovery check")
        yield


def _pin(checkpoint: Path) -> tuple[str, str]:
    from tracker.platform.windows_checkpoint import MANIFEST_LIMIT, _archive, _ordinary

    checkpoint = checked_path(checkpoint)
    _ordinary(checkpoint, directory=True)
    path = checkpoint / "checkpoint.json"
    _ordinary(path)
    if path.stat().st_size > MANIFEST_LIMIT:
        raise RecoveryError("Recovery manifest exceeds its size limit")
    payload = path.read_bytes()
    manifest = json.loads(payload)
    if not isinstance(manifest, dict) or manifest.get("verified") is not True:
        raise RecoveryError("Recovery requires a completed checkpoint")
    _archive(checkpoint, manifest)
    return hashlib.sha256(payload).hexdigest(), manifest["sha256"]


def _stop_attempts(state: Path, record: dict[str, Any]) -> None:
    from tracker.platform.windows_private import require_private

    for attempt in record["attempts"]:
        scratch = checked_path(state / "recovery" / "attempts" / attempt)
        if scratch.exists():
            require_private(scratch)
            pgdata = checked_path(scratch / "db")
            if pgdata.exists():
                require_private(pgdata)
            _quiesce(pgdata)


def _quiesce(pgdata: Path) -> None:
    from tracker.platform.embedded_db import bundled_bin_dir, stop_server
    from tracker.platform.windows_private import require_private

    deadline = time.monotonic() + 30
    path = pgdata / "postmaster.pid"
    while path.exists():
        require_private(path)
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
            pid, recorded_path, started = lines[:3]
            if Path(recorded_path).resolve() != pgdata.resolve() or int(pid) == 0:
                raise ValueError("foreign recovery database")
            try:
                process = psutil.Process(abs(int(pid)))
                began = process.create_time()
            except psutil.NoSuchProcess:
                # An interrupted initdb can leave a dead single-user pidfile.
                # The attempt is retained and never reused, including this file.
                return
            if abs(began - int(started)) >= 3:
                # Windows reuses process IDs: a process that started at another
                # time is not the recorded postmaster, which has exited.
                return
            if (Path(process.exe()).resolve() != (bundled_bin_dir(16) / "postgres.exe").resolve()
                    or process.username() != psutil.Process().username()):
                raise ValueError("foreign recovery process")
            if int(pid) > 0 and len(lines) >= 8 and lines[7].strip() == "ready":
                if not stop_server(pgdata) or path.exists():
                    raise RecoveryError("An interrupted recovery database did not confirm shutdown")
                return
        except (ValueError, IndexError, psutil.Error) as error:
            raise RecoveryError("Cannot verify the interrupted recovery database; preserve it for repair") from error
        if time.monotonic() >= deadline:
            raise RecoveryError("Recovery initialization is still finishing; retry after it exits")
        time.sleep(0.1)


def recover(state: Path, action: str, checkpoint: Path | None = None) -> dict[str, Any]:
    """Serialize a scratch-only drill, retaining every attempt and its journal."""
    from tracker.platform.windows_checkpoint import verify_checkpoint
    from tracker.platform.windows_private import private_directory

    state = checked_path(state)
    if action not in {"begin", "retry", "abandon"}:
        raise ValueError("Unsupported recovery action")
    with recovery_leases(state):
        record = read_recovery(state)
        if action == "begin":
            if record is not None and record["phase"] not in TERMINAL:
                raise RecoveryError("Resolve the unfinished recovery check before starting another")
            if checkpoint is None:
                raise ValueError("A checkpoint is required")
            checkpoint = checked_path(checkpoint)
            if checkpoint.is_relative_to(state) or state.is_relative_to(checkpoint):
                raise RecoveryError("Recovery checkpoint must be separate from current state")
            manifest_hash, archive_hash = _pin(checkpoint)
            if record is not None:
                path = _journal(state)
                move(path, path.with_name("completed-" + uuid.uuid4().hex + ".json"))
            record = {"format": 1, "kind": "checkpoint-drill", "state": str(state),
                      "checkpoint": str(checkpoint), "manifest_sha256": manifest_hash,
                      "archive_sha256": archive_hash, "phase": "verifying", "attempts": [uuid.uuid4().hex]}
            _write(state, record)
        else:
            if record is None or record["phase"] in TERMINAL:
                raise RecoveryError("There is no unfinished recovery check")
            _stop_attempts(state, record)
            if action == "abandon":
                record["phase"] = "abandoned"
                _write(state, record)
                return record
            if len(record["attempts"]) >= 256:
                raise RecoveryError("Recovery attempt limit reached; abandon this drill before beginning another")
            record["attempts"].append(uuid.uuid4().hex)
            record["phase"] = "verifying"
            _write(state, record)
        try:
            checkpoint = Path(record["checkpoint"])
            if _pin(checkpoint) != (record["manifest_sha256"], record["archive_sha256"]):
                raise RecoveryError("Recovery checkpoint changed after this operation began")
            attempts = state / "recovery" / "attempts"
            private_directory(attempts)
            scratch = attempts / record["attempts"][-1]
            verify_checkpoint(checkpoint, scratch)
            record["phase"] = "verified"
            _write(state, record)
            return record
        except BaseException:
            record["phase"] = "failed"
            _write(state, record)
            raise

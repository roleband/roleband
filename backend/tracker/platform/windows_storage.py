"""Retained Windows storage contracts that older engine builds cannot bypass."""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path
from typing import Any

if sys.platform != "win32":
    raise ImportError("Windows storage contracts require Windows")

from tracker.platform.windows_fs import RecordTooLarge, checked_path, publish, read_private

READER_CONTRACT = 1
LIMIT = 128 * 1024


class StorageCompatibilityError(RuntimeError):
    """The retained cluster requires a different supported engine."""


def metadata(pgdata: Path, version: int = 16, minimum_reader: int = READER_CONTRACT) -> dict[str, Any]:
    return {"format": 2, "pgdata": str(pgdata), "version": version, "minimum_reader": minimum_reader}


def validate(record: Any, pgdata: Path, version: int = 16, *, require_reader: bool = True) -> dict[str, Any]:
    legacy = {"format": 1, "pgdata": str(pgdata), "version": version}
    if record == legacy and type(record.get("format")) is int and type(record.get("version")) is int:
        return legacy
    if not isinstance(record, dict):
        raise StorageCompatibilityError("Windows storage metadata is damaged or names another cluster")
    # A writer that changes the record declares the reader it needs. Its other
    # fields may be unknown here, so that floor is read before the shape: an
    # older engine then asks for a newer one instead of reporting damage.
    floor = record.get("minimum_reader")
    if (require_reader and type(record.get("format")) is int and record["format"] >= 2
            and type(floor) is int and READER_CONTRACT < floor <= 65535):
        raise StorageCompatibilityError(
            f"This database requires Windows reader contract {floor}; this engine supports {READER_CONTRACT}. "
            "Install a compatible signed package or use a compatible recovery checkpoint."
        )
    if (set(record) != {"format", "pgdata", "version", "minimum_reader"}
            or type(record["format"]) is not int or record["format"] != 2
            or record["pgdata"] != str(pgdata) or type(record["version"]) is not int or record["version"] != version
            or type(record["minimum_reader"]) is not int or not 1 <= record["minimum_reader"] <= 65535):
        raise StorageCompatibilityError("Windows storage metadata is damaged or names another cluster")
    return record


def retained_profile(pgdata: Path) -> dict[str, str | None]:
    from tracker.platform.windows_private import require_private

    checked_path(pgdata)
    state = pgdata.parent
    require_private(state)
    owner = state / f"{pgdata.name}.owner.json"
    if read_json(owner) != {"owner": "app"}:
        raise StorageCompatibilityError("Recovery requires an app-owned database")
    paths = {"owner": owner, "password": state / f"{pgdata.name}.auth" / "pgpass.conf",
             "key": state / "secret.key"}
    result: dict[str, str | None] = {}
    for name, path in paths.items():
        checked_path(path)
        if name == "key" and not path.exists():
            result[name] = None
            continue
        require_private(path)
        with path.open("rb") as stream:
            result[name] = hashlib.file_digest(stream, "sha256").hexdigest()
    return result


def read_json(path: Path, *, maximum: int = LIMIT) -> dict[str, Any]:
    try:
        payload = read_private(path, maximum)
    except RecordTooLarge as error:
        raise StorageCompatibilityError("Retained Windows metadata exceeds its size limit") from error
    try:
        result = json.loads(payload)
        if not isinstance(result, dict):
            raise ValueError("metadata must be an object")
        return result
    except (ValueError, UnicodeError) as error:
        raise StorageCompatibilityError("Retained Windows metadata is damaged; preserve it for repair") from error


def write_json(path: Path, record: dict[str, Any]) -> None:
    payload = (json.dumps(record, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    if len(payload) > LIMIT:
        raise StorageCompatibilityError("Retained Windows metadata exceeds its size limit")
    publish(path, payload)

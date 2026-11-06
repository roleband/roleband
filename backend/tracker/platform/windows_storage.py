"""Retained Windows storage contracts that older engine builds cannot bypass."""

from __future__ import annotations

import ctypes
import hashlib
import json
import msvcrt
import os
import sys
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from ctypes import wintypes
from pathlib import Path
from typing import Any, BinaryIO

if sys.platform != "win32":
    raise ImportError("Windows storage contracts require Windows")

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
    if (not isinstance(record, dict) or set(record) != {"format", "pgdata", "version", "minimum_reader"}
            or type(record["format"]) is not int or record["format"] != 2
            or record["pgdata"] != str(pgdata) or type(record["version"]) is not int or record["version"] != version
            or type(record["minimum_reader"]) is not int or not 1 <= record["minimum_reader"] <= 65535):
        raise StorageCompatibilityError("Windows storage metadata is damaged or names another cluster")
    if require_reader and record["minimum_reader"] > READER_CONTRACT:
        raise StorageCompatibilityError(
            f"This database requires Windows reader contract {record['minimum_reader']}; this engine supports {READER_CONTRACT}. "
            "Install a compatible signed package or use a compatible recovery checkpoint."
        )
    return record


def retained_profile(pgdata: Path) -> dict[str, str | None]:
    from tracker.platform.windows_private import require_private
    from tracker.platform.windows_recovery import _path

    _path(pgdata)
    state = pgdata.parent
    require_private(state)
    owner = state / f"{pgdata.name}.owner.json"
    if read_json(owner) != {"owner": "app"}:
        raise StorageCompatibilityError("Recovery requires an app-owned database")
    paths = {"owner": owner, "password": state / f"{pgdata.name}.auth" / "pgpass.conf",
             "key": state / "secret.key"}
    result: dict[str, str | None] = {}
    for name, path in paths.items():
        _path(path)
        if name == "key" and not path.exists():
            result[name] = None
            continue
        require_private(path)
        with path.open("rb") as stream:
            result[name] = hashlib.file_digest(stream, "sha256").hexdigest()
    return result


@contextmanager
def _reader(path: Path) -> Iterator[BinaryIO]:
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.CreateFileW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, ctypes.c_void_p,
                                   wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE]
    kernel.CreateFileW.restype = wintypes.HANDLE
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    # Readers retain the opened snapshot while atomic publication replaces its
    # directory entry, matching the native host's FileShare.Delete contract.
    handle = kernel.CreateFileW(str(path), 0x80000000, 5, None, 3, 0x80, None)
    if handle == wintypes.HANDLE(-1).value:
        raise ctypes.WinError(ctypes.get_last_error())
    try:
        descriptor = msvcrt.open_osfhandle(handle, os.O_RDONLY | os.O_BINARY)
    except BaseException:
        kernel.CloseHandle(handle)
        raise
    with os.fdopen(descriptor, "rb") as stream:
        yield stream


def _replace(source: Path, destination: Path) -> None:
    class RenameInfo(ctypes.Structure):
        _fields_ = [("flags", wintypes.DWORD), ("root", wintypes.HANDLE),
                    ("length", wintypes.DWORD), ("name", wintypes.WCHAR * 1)]

    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.CreateFileW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, ctypes.c_void_p,
                                   wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE]
    kernel.CreateFileW.restype = wintypes.HANDLE
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel.SetFileInformationByHandle.argtypes = [wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD]
    kernel.FlushFileBuffers.argtypes = [wintypes.HANDLE]
    handle = kernel.CreateFileW(str(source), 0x40010000, 7, None, 3, 0x80000080, None)
    if handle == wintypes.HANDLE(-1).value:
        raise ctypes.WinError(ctypes.get_last_error())
    try:
        encoded = str(destination).encode("utf-16-le")
        buffer = ctypes.create_string_buffer(RenameInfo.name.offset + len(encoded) + 2)
        info = RenameInfo.from_buffer(buffer)
        info.flags, info.length = 3, len(encoded)
        ctypes.memmove(ctypes.addressof(buffer) + RenameInfo.name.offset, encoded, len(encoded))
        # FileRenameInfoEx replaces the name while deletion-sharing readers keep
        # their old snapshot. MoveFileEx rejects an open replacement target.
        if not kernel.SetFileInformationByHandle(handle, 22, buffer, len(buffer)):
            raise ctypes.WinError(ctypes.get_last_error())
        if not kernel.FlushFileBuffers(handle):
            raise ctypes.WinError(ctypes.get_last_error())
    finally:
        kernel.CloseHandle(handle)


def read_json(path: Path, *, maximum: int = LIMIT) -> dict[str, Any]:
    from tracker.platform.windows_private import require_private
    from tracker.platform.windows_recovery import _path

    _path(path)
    require_private(path.parent)
    require_private(path)
    with _reader(path) as stream:
        payload = stream.read(maximum + 1)
    if len(payload) > maximum:
        raise StorageCompatibilityError("Retained Windows metadata exceeds its size limit")
    try:
        result = json.loads(payload)
        if not isinstance(result, dict):
            raise ValueError("metadata must be an object")
        return result
    except (ValueError, UnicodeError) as error:
        raise StorageCompatibilityError("Retained Windows metadata is damaged; preserve it for repair") from error


def write_json(path: Path, record: dict[str, Any]) -> None:
    from tracker.platform.windows_private import private_directory, require_private
    from tracker.platform.windows_recovery import _path

    _path(path)
    private_directory(path.parent)
    if path.exists():
        require_private(path)
    payload = (json.dumps(record, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    if len(payload) > LIMIT:
        raise StorageCompatibilityError("Retained Windows metadata exceeds its size limit")
    temporary = path.with_name(".metadata-" + uuid.uuid4().hex)
    with temporary.open("xb") as stream:
        stream.write(payload)
        stream.flush()
        os.fsync(stream.fileno())
    require_private(temporary)
    _replace(temporary, path)

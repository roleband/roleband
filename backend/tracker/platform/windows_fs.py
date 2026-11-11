"""File primitives for retained Windows state that the engine and the native host share.

A record is read through a handle that shares deletion and published by
replacing the name through a handle, so a reader keeps its snapshot without
blocking a writer. `MoveFileEx` cannot replace a target that any process holds
open, and the native host reads these records with `FileShare.Delete`.
"""

from __future__ import annotations

import ctypes
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
    raise ImportError("Windows file primitives require Windows")

_REPARSE_POINT = 0x400


class ReparsePointError(PermissionError):
    """Retained state would traverse a junction, symbolic link or other reparse point."""


class RecordTooLarge(ValueError):
    """A retained record exceeds the size its reader accepts."""


def checked_path(path: Path) -> Path:
    """The absolute path, refusing a reparse point at it or at any existing ancestor."""
    selected = Path(os.path.abspath(path))
    for parent in (selected, *selected.parents):
        try:
            attributes = parent.lstat().st_file_attributes
        except FileNotFoundError:
            continue
        if attributes & _REPARSE_POINT:
            raise ReparsePointError(f"retained storage cannot traverse a reparse point: {parent}")
    return selected


def _kernel() -> Any:
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.CreateFileW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, ctypes.c_void_p,
                                   wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE]
    kernel.CreateFileW.restype = wintypes.HANDLE
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel.SetFileInformationByHandle.argtypes = [wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD]
    kernel.FlushFileBuffers.argtypes = [wintypes.HANDLE]
    kernel.MoveFileExW.argtypes = [wintypes.LPCWSTR, wintypes.LPCWSTR, wintypes.DWORD]
    kernel.MoveFileExW.restype = wintypes.BOOL
    return kernel


@contextmanager
def reader(path: Path) -> Iterator[BinaryIO]:
    """A read handle that shares reading and deletion, so publication can replace the name."""
    kernel = _kernel()
    generic_read, share_read_delete, open_existing, normal = 0x80000000, 0x5, 3, 0x80
    handle = kernel.CreateFileW(str(path), generic_read, share_read_delete, None, open_existing, normal, None)
    if handle == wintypes.HANDLE(-1).value:
        raise ctypes.WinError(ctypes.get_last_error())
    try:
        descriptor = msvcrt.open_osfhandle(handle, os.O_RDONLY | os.O_BINARY)
    except BaseException:
        kernel.CloseHandle(handle)
        raise
    with os.fdopen(descriptor, "rb") as stream:
        yield stream


def read_private(path: Path, maximum: int) -> bytes:
    """A private record's bytes, after checking its path, directory and file ACLs."""
    from tracker.platform.windows_private import require_private

    path = checked_path(path)
    require_private(path.parent)
    require_private(path)
    with reader(path) as stream:
        payload = stream.read(maximum + 1)
    if len(payload) > maximum:
        raise RecordTooLarge(f"retained record exceeds {maximum} bytes: {path}")
    return payload


def _replace(source: Path, destination: Path) -> None:
    class RenameInfo(ctypes.Structure):
        _fields_ = [("flags", wintypes.DWORD), ("root", wintypes.HANDLE),
                    ("length", wintypes.DWORD), ("name", wintypes.WCHAR * 1)]

    kernel = _kernel()
    write_delete, share_all, open_existing, write_through_normal = 0x40010000, 0x7, 3, 0x80000080
    handle = kernel.CreateFileW(str(source), write_delete, share_all, None, open_existing, write_through_normal, None)
    if handle == wintypes.HANDLE(-1).value:
        raise ctypes.WinError(ctypes.get_last_error())
    try:
        encoded = str(destination).encode("utf-16-le")
        buffer = ctypes.create_string_buffer(RenameInfo.name.offset + len(encoded) + 2)
        info = RenameInfo.from_buffer(buffer)
        replace_if_exists, posix_semantics = 0x1, 0x2
        info.flags, info.length = replace_if_exists | posix_semantics, len(encoded)
        ctypes.memmove(ctypes.addressof(buffer) + RenameInfo.name.offset, encoded, len(encoded))
        file_rename_info_ex = 22
        if not kernel.SetFileInformationByHandle(handle, file_rename_info_ex, buffer, len(buffer)):
            raise ctypes.WinError(ctypes.get_last_error())
        if not kernel.FlushFileBuffers(handle):
            raise ctypes.WinError(ctypes.get_last_error())
    finally:
        kernel.CloseHandle(handle)


def publish(path: Path, payload: bytes) -> None:
    """Replace `path` with `payload` in one step, through a flushed private temporary file.

    A failure leaves the previous record in place and no temporary file behind."""
    from tracker.platform.windows_private import private_directory, require_private

    path = checked_path(path)
    private_directory(path.parent)
    if path.exists():
        require_private(path)
    temporary = path.with_name("." + path.stem + "-" + uuid.uuid4().hex)
    try:
        with temporary.open("xb") as stream:
            # The new file takes its ACL from the directory's inheritable entries; it is checked before the
            # payload, often a secret, is in it.
            require_private(temporary)
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        _replace(temporary, path)
    except BaseException:
        temporary.unlink(missing_ok=True)
        raise


def move(source: Path, destination: Path, *, replace: bool = False) -> None:
    """Rename a file or directory, returning only after the rename is written through."""
    write_through, replace_existing = 0x8, 0x1
    if not _kernel().MoveFileExW(str(source), str(destination), write_through | (replace_existing if replace else 0)):
        raise ctypes.WinError(ctypes.get_last_error())

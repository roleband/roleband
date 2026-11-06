"""Account-private leases that the native host, the engine and operator commands share.

The native host holds `launcher/desktop.lock` open without sharing while it owns
an engine. The engine holds a byte lock on `launcher/engine.lock` for its life.
A command that changes retained state holds both. The two mechanisms exclude
each other: an open without sharing fails while any handle is open, and a byte
lock fails while another handle holds it. `db.auth/startup.lock` serializes
starting and switching a cluster.
"""

from __future__ import annotations

import ctypes
import msvcrt
import os
import sys
from collections.abc import Iterator
from contextlib import ExitStack, contextmanager
from ctypes import wintypes
from pathlib import Path

from tracker.platform import filelock

if sys.platform != "win32":
    raise ImportError("Windows leases require Windows")

DESKTOP = "desktop.lock"
ENGINE = "engine.lock"
_SHARING_VIOLATION = 32


def _open(path: Path) -> int:
    """A read-write descriptor sharing reading and writing, as `open` gives.

    Opened through `CreateFileW` because the C runtime reports a sharing
    violation as a plain access denial, indistinguishable from an ACL refusal."""
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.CreateFileW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, ctypes.c_void_p,
                                   wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE]
    kernel.CreateFileW.restype = wintypes.HANDLE
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    read_write, share_read_write, open_always, normal = 0xC0000000, 0x3, 4, 0x80
    handle = kernel.CreateFileW(str(path), read_write, share_read_write, None, open_always, normal, None)
    if handle == wintypes.HANDLE(-1).value:
        error = ctypes.get_last_error()
        if error == _SHARING_VIOLATION:
            raise filelock.LockHeld(f"{path.name} is held by the RoleBand app; quit it first")
        raise ctypes.WinError(error)
    try:
        return msvcrt.open_osfhandle(handle, os.O_RDWR | os.O_BINARY)
    except BaseException:
        kernel.CloseHandle(handle)
        raise


@contextmanager
def lease(path: Path, *, blocking: bool = False) -> Iterator[None]:
    """Hold `path`'s lease, or raise `filelock.LockHeld` naming the file and its holder."""
    from tracker.platform.windows_private import require_private

    if path.exists():
        require_private(path)
    descriptor = _open(path)
    try:
        require_private(path)
        try:
            filelock.lock(descriptor, blocking=blocking)
        except filelock.LockHeld as error:
            raise filelock.LockHeld(f"{path.name} is held by a running RoleBand engine or command") from error
        yield
    finally:
        os.close(descriptor)


@contextmanager
def lifecycle_leases(state: Path) -> Iterator[None]:
    """Both lifecycle leases of `state`, so neither the app nor an engine can run beside the holder."""
    from tracker.platform.windows_private import private_directory

    private_directory(state)
    private_directory(state / "launcher")
    with ExitStack() as held:
        for name in (DESKTOP, ENGINE):
            held.enter_context(lease(state / "launcher" / name))
        yield

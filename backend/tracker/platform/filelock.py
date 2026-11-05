"""Exclusive whole-file advisory locks with one interface on every platform.

POSIX takes `flock`. Windows locks the file's first byte with `msvcrt.locking`.
Both locks belong to the open handle: closing it, or the death of the process
holding it, releases the lock, so a crashed holder never leaves a stale lock.

A Windows byte lock is mandatory for that byte, so a process that does not hold
it cannot read the byte either. Every caller here reads its file only while it
holds the lock, which keeps the two platforms equivalent for these files.

Callers look these functions up on the module at call time
(`filelock.lock(...)`), so a test can patch one name to see every lock taken.
"""

from __future__ import annotations

import os
import sys
import time
from typing import IO, Any

if sys.platform == "win32":
    import msvcrt
else:
    import fcntl

#: How long a blocking Windows lock sleeps between attempts. `msvcrt` offers no
#: wait without a deadline (`LK_LOCK` gives up after about ten seconds).
_POLL_SECONDS = 0.05


class LockHeld(OSError):
    """A non-blocking lock found the file locked by another handle."""


def _descriptor(file: int | IO[Any]) -> int:
    return file if isinstance(file, int) else file.fileno()


def lock(file: int | IO[Any], *, blocking: bool = True) -> None:
    """Take the exclusive lock, waiting for it unless `blocking` is false."""
    fd = _descriptor(file)
    if sys.platform != "win32":
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | (0 if blocking else fcntl.LOCK_NB))
        except BlockingIOError as exc:
            raise LockHeld(str(exc)) from exc
        return
    # `locking` acts at the descriptor's position; the lock byte is always 0.
    position = os.lseek(fd, 0, os.SEEK_CUR)
    try:
        while True:
            os.lseek(fd, 0, os.SEEK_SET)
            try:
                msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
                return
            except OSError as exc:
                if not blocking:
                    raise LockHeld(str(exc)) from exc
            time.sleep(_POLL_SECONDS)
    finally:
        os.lseek(fd, position, os.SEEK_SET)


def unlock(file: int | IO[Any]) -> None:
    """Release a lock this handle holds."""
    fd = _descriptor(file)
    if sys.platform != "win32":
        fcntl.flock(fd, fcntl.LOCK_UN)
        return
    position = os.lseek(fd, 0, os.SEEK_CUR)
    try:
        os.lseek(fd, 0, os.SEEK_SET)
        msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)
    finally:
        os.lseek(fd, position, os.SEEK_SET)

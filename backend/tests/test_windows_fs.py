"""A published record reads while its publisher still holds the handle that renamed it into place."""

from __future__ import annotations

import ctypes
import sys
from collections.abc import Iterator
from contextlib import contextmanager
from ctypes import wintypes
from pathlib import Path

import pytest

pytestmark = pytest.mark.skipif(sys.platform != "win32", reason="Windows private storage requires Windows")


@contextmanager
def publishers_handle(path: Path) -> Iterator[None]:
    """The handle `publish` keeps on a record from the rename that names it until its flush ends: write and
    delete access, sharing everything. Another process sees the name for that whole time."""
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.CreateFileW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, ctypes.c_void_p,
                                   wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE]
    kernel.CreateFileW.restype = wintypes.HANDLE
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    write_delete, share_all, open_existing, normal = 0x40010000, 0x7, 3, 0x80
    handle = kernel.CreateFileW(str(path), write_delete, share_all, None, open_existing, normal, None)
    if handle == wintypes.HANDLE(-1).value:
        raise ctypes.WinError(ctypes.get_last_error())
    try:
        yield
    finally:
        kernel.CloseHandle(handle)


def test_a_record_reads_while_its_publisher_still_holds_it(tmp_path):
    from tracker.platform.windows_fs import publish, read_private

    record = tmp_path / "launcher" / "api-listener-1.bin"
    publish(record, b"socket")

    with publishers_handle(record):
        assert read_private(record, 64) == b"socket"

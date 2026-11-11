"""How much memory this computer has: the one reader every sizing choice uses."""

from __future__ import annotations

import os
import sys

#: Below this much installed memory a computer is small: the embedding model
#: takes its small artifact and the database its Small preset, so the two
#: choices never disagree about the same computer.
SMALL_BELOW = 16 * 2**30


def total_memory_bytes() -> int | None:
    """Total physical RAM: `GlobalMemoryStatusEx` on Windows, POSIX sysconf on
    macOS and Linux. None on failure."""
    if sys.platform == "win32":
        import ctypes
        from ctypes import wintypes

        class MemoryStatus(ctypes.Structure):
            _fields_ = [
                ("length", wintypes.DWORD), ("load", wintypes.DWORD),
                ("total_physical", ctypes.c_ulonglong), ("available_physical", ctypes.c_ulonglong),
                ("total_page_file", ctypes.c_ulonglong), ("available_page_file", ctypes.c_ulonglong),
                ("total_virtual", ctypes.c_ulonglong), ("available_virtual", ctypes.c_ulonglong),
                ("available_extended_virtual", ctypes.c_ulonglong),
            ]

        status = MemoryStatus()
        status.length = ctypes.sizeof(MemoryStatus)
        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel.GlobalMemoryStatusEx.argtypes = [ctypes.POINTER(MemoryStatus)]
        kernel.GlobalMemoryStatusEx.restype = wintypes.BOOL
        if not kernel.GlobalMemoryStatusEx(ctypes.byref(status)) or status.total_physical <= 0:
            return None
        return int(status.total_physical)
    try:
        page = os.sysconf("SC_PAGE_SIZE")
        pages = os.sysconf("SC_PHYS_PAGES")
        if page > 0 and pages > 0:
            return page * pages
    except (ValueError, OSError, AttributeError):
        pass
    return None

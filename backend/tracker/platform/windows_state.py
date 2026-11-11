"""Windows retained state resolved through the account's LocalAppData known folder."""

from __future__ import annotations

import ctypes
import sys
from ctypes import wintypes
from pathlib import Path
from uuid import UUID

if sys.platform != "win32":
    raise ImportError("Windows state discovery requires Windows")

KF_FLAG_NO_PACKAGE_REDIRECTION = 0x00010000


def local_app_data() -> Path:
    shell = ctypes.WinDLL("shell32", use_last_error=True)
    shell.SHGetKnownFolderPath.argtypes = [wintypes.LPVOID, wintypes.DWORD, wintypes.HANDLE,
                                         ctypes.POINTER(wintypes.LPWSTR)]
    shell.SHGetKnownFolderPath.restype = ctypes.c_long
    allocator = ctypes.WinDLL("ole32")
    allocator.CoTaskMemFree.argtypes = [wintypes.LPVOID]
    folder = ctypes.create_string_buffer(UUID("F1B32785-6FBA-4FCF-9D55-7B8E7F157091").bytes_le)
    value = wintypes.LPWSTR()
    result = shell.SHGetKnownFolderPath(folder, KF_FLAG_NO_PACKAGE_REDIRECTION, None, ctypes.byref(value))
    try:
        if result < 0 or not value.value:
            raise OSError(f"LocalAppData lookup failed ({result:#x})")
        path = Path(value.value)
        if not path.is_absolute():
            raise OSError("LocalAppData must be an absolute path")
        return path
    finally:
        if value:
            allocator.CoTaskMemFree(value)

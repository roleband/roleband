"""Windows directories whose ACL grants access only to this account and SYSTEM."""

from __future__ import annotations

import ctypes
import re
import sys
from collections.abc import Iterator
from contextlib import contextmanager
from ctypes import wintypes
from pathlib import Path

if sys.platform != "win32":
    raise ImportError("Windows private storage requires Windows")


class PrivatePathError(PermissionError):
    """A path cannot safely hold account credentials."""


class _SecurityAttributes(ctypes.Structure):
    _fields_ = [
        ("length", wintypes.DWORD),
        ("descriptor", wintypes.LPVOID),
        ("inherit", wintypes.BOOL),
    ]


def _apis():
    advapi = ctypes.WinDLL("advapi32", use_last_error=True)
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    advapi.ConvertStringSecurityDescriptorToSecurityDescriptorW.argtypes = [
        wintypes.LPCWSTR, wintypes.DWORD, ctypes.POINTER(wintypes.LPVOID), wintypes.LPVOID,
    ]
    advapi.ConvertSecurityDescriptorToStringSecurityDescriptorW.argtypes = [
        wintypes.LPVOID, wintypes.DWORD, wintypes.DWORD,
        ctypes.POINTER(wintypes.LPWSTR), wintypes.LPVOID,
    ]
    advapi.GetNamedSecurityInfoW.argtypes = [
        wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD,
        wintypes.LPVOID, wintypes.LPVOID, wintypes.LPVOID, wintypes.LPVOID,
        ctypes.POINTER(wintypes.LPVOID),
    ]
    advapi.GetNamedSecurityInfoW.restype = wintypes.DWORD
    advapi.OpenProcessToken.argtypes = [wintypes.HANDLE, wintypes.DWORD, ctypes.POINTER(wintypes.HANDLE)]
    advapi.GetTokenInformation.argtypes = [
        wintypes.HANDLE, ctypes.c_int, wintypes.LPVOID, wintypes.DWORD, ctypes.POINTER(wintypes.DWORD),
    ]
    advapi.ConvertSidToStringSidW.argtypes = [wintypes.LPVOID, ctypes.POINTER(wintypes.LPWSTR)]
    kernel.GetCurrentProcess.restype = wintypes.HANDLE
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel.LocalFree.argtypes = [wintypes.LPVOID]
    kernel.CreateDirectoryW.argtypes = [wintypes.LPCWSTR, ctypes.POINTER(_SecurityAttributes)]
    return advapi, kernel


def account_sid() -> str:
    """The process token's user SID, independent of localized account names."""
    return _token_sid(1)


def default_owner_sid() -> str:
    """The owner this process's token gives what it creates without naming an owner: the account itself, or the
    Administrators group for a token running elevated."""
    return _token_sid(4)


def _token_sid(information: int) -> str:
    """The SID a token information class leads with (TokenUser and TokenOwner both start with one)."""
    advapi, kernel = _apis()
    token = wintypes.HANDLE()
    if not advapi.OpenProcessToken(kernel.GetCurrentProcess(), 0x0008, ctypes.byref(token)):
        raise ctypes.WinError(ctypes.get_last_error())
    try:
        size = wintypes.DWORD()
        advapi.GetTokenInformation(token, information, None, 0, ctypes.byref(size))
        info = ctypes.create_string_buffer(size.value)
        if not advapi.GetTokenInformation(token, information, info, size, ctypes.byref(size)):
            raise ctypes.WinError(ctypes.get_last_error())
        sid = ctypes.cast(info, ctypes.POINTER(wintypes.LPVOID))[0]
        text = wintypes.LPWSTR()
        if not advapi.ConvertSidToStringSidW(sid, ctypes.byref(text)):
            raise ctypes.WinError(ctypes.get_last_error())
        try:
            return text.value or ""
        finally:
            kernel.LocalFree(text)
    finally:
        kernel.CloseHandle(token)


def require_private(path: Path) -> None:
    """Refuse reparse points, foreign ownership and ACLs granting other accounts."""
    if path.lstat().st_file_attributes & 0x400:
        raise PrivatePathError(f"private storage is a reparse point: {path}")
    advapi, kernel = _apis()
    descriptor = wintypes.LPVOID()
    error = advapi.GetNamedSecurityInfoW(str(path), 1, 5, None, None, None, None, ctypes.byref(descriptor))
    if error:
        raise ctypes.WinError(error)
    text = wintypes.LPWSTR()
    try:
        if not advapi.ConvertSecurityDescriptorToStringSecurityDescriptorW(
            descriptor, 1, 5, ctypes.byref(text), None,
        ):
            raise ctypes.WinError(ctypes.get_last_error())
        sddl = text.value or ""
    finally:
        if text:
            kernel.LocalFree(text)
        kernel.LocalFree(descriptor)
    if problem := descriptor_problem(sddl, sddl_name(account_sid()), sddl_name(default_owner_sid())):
        raise PrivatePathError(f"private storage {problem}: {path}")


def sddl_name(sid: str) -> str:
    """How descriptor strings write an account: its full SID, or the short alias Windows uses for a well-known
    account, such as LA for the built-in Administrator. Descriptors read back from disk use the alias, so a
    comparison with the full SID alone would refuse that account's own storage."""
    advapi, kernel = _apis()
    descriptor = wintypes.LPVOID()
    if not advapi.ConvertStringSecurityDescriptorToSecurityDescriptorW(
        f"O:{sid}", 1, ctypes.byref(descriptor), None,
    ):
        raise ctypes.WinError(ctypes.get_last_error())
    text = wintypes.LPWSTR()
    try:
        if not advapi.ConvertSecurityDescriptorToStringSecurityDescriptorW(
            descriptor, 1, 1, ctypes.byref(text), None,
        ):
            raise ctypes.WinError(ctypes.get_last_error())
        return (text.value or "").removeprefix("O:")
    finally:
        if text:
            kernel.LocalFree(text)
        kernel.LocalFree(descriptor)


def descriptor_problem(sddl: str, account: str, default_owner: str | None = None) -> str | None:
    """What makes a descriptor unsafe for private storage, if anything: an owner other than the account or the
    owner this process gives what it creates, no list of allowed entries (or a null one), or an entry for anyone
    but the account and SYSTEM. Inherited entries count like any other, so a file that inherits from a private
    directory passes; private_directory itself protects a directory's list from what its parents grant. The
    descriptor and the names are in descriptor-string form (see sddl_name).

    An elevated administrator's files are owned by the Administrators group, which only administrators can act
    as; the entries still admit no one but the account and SYSTEM."""
    owner, _, dacl = sddl.partition("D:")
    entries = re.findall(r"\(([^()]*)\)", dacl)
    if owner not in {f"O:{account}", f"O:{default_owner or account}"} or not entries or "NO_ACCESS_CONTROL" in dacl:
        return f"has an unsafe owner or ACL ({owner or 'no owner'})"
    for entry in entries:
        fields = entry.split(";")
        if len(fields) != 6 or fields[0] != "A" or fields[5] not in {account, "SY"}:
            return "grants another account access"
    return None


@contextmanager
def private_attributes() -> Iterator[_SecurityAttributes]:
    """Security attributes granting this account and SYSTEM full access."""
    advapi, kernel = _apis()
    sid = account_sid()
    sddl = f"O:{sid}D:P(A;OICI;FA;;;{sid})(A;OICI;FA;;;SY)"
    descriptor = wintypes.LPVOID()
    if not advapi.ConvertStringSecurityDescriptorToSecurityDescriptorW(
        sddl, 1, ctypes.byref(descriptor), None,
    ):
        raise ctypes.WinError(ctypes.get_last_error())
    try:
        yield _SecurityAttributes(ctypes.sizeof(_SecurityAttributes), descriptor, False)
    finally:
        kernel.LocalFree(descriptor)


def private_directory(path: Path, *, exist_ok: bool = True) -> None:
    """Create with a protected inheritable ACL before any sensitive file exists."""
    path.parent.mkdir(parents=True, exist_ok=True)
    _, kernel = _apis()
    with private_attributes() as attributes:
        if not kernel.CreateDirectoryW(str(path), ctypes.byref(attributes)):
            error = ctypes.get_last_error()
            if error == 183 and not exist_ok:
                raise FileExistsError(error, "Private directory already exists", str(path))
            if error != 183:
                raise ctypes.WinError(error)
    require_private(path)


def native_path(path: Path) -> str:
    """An existing path the bundled clients can represent in their narrow argv."""
    value = str(path)
    if value.isascii():
        return value
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.GetShortPathNameW.argtypes = [wintypes.LPCWSTR, wintypes.LPWSTR, wintypes.DWORD]
    size = kernel.GetShortPathNameW(value, None, 0)
    if not size:
        raise ctypes.WinError(ctypes.get_last_error())
    buffer = ctypes.create_unicode_buffer(size)
    if not kernel.GetShortPathNameW(value, buffer, size):
        raise ctypes.WinError(ctypes.get_last_error())
    if not buffer.value.isascii():
        raise PrivatePathError(f"bundled PostgreSQL requires an ASCII path or a Windows short-path alias: {path}")
    return buffer.value

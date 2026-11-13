"""Windows: a stop whose process has already gone is a stop, not an error.

`terminate` answers a caller that wants the process gone, so "it had already
stopped" is its False and not an exception. Windows refuses TerminateProcess
with ERROR_ACCESS_DENIED for a process that is already on its way out, and at
that instant its kernel object is not signalled yet, so the exit status is the
only answer available. What must still raise is the other failure: a process
that is alive and does not die.

The module is Windows-only, and every native call it makes goes through
`_kernel()`. Both are what lets these cases run on any machine: the module is
loaded here under a Windows platform, and a stand-in answers for kernel32. The
native paths themselves run in tests/test_windows_supervisor.py, on Windows.
"""

from __future__ import annotations

import ctypes
import importlib.util
import sys
from ctypes import wintypes
from pathlib import Path

import pytest

MODULE = Path(__file__).resolve().parents[1] / "tracker" / "platform" / "windows_process.py"

#: Win32 values, restated so these tests measure the module against the
#: platform's numbers rather than against its own constants.
ACCESS_DENIED = 5
INVALID_HANDLE = 6
WAIT_OBJECT_0 = 0
WAIT_TIMEOUT = 0x102
STILL_ACTIVE = 259
FILETIME_EPOCH = 11_644_473_600

HANDLE = 0x2A
STARTED = 1_762_900_000.5


@pytest.fixture(scope="module")
def windows_process():
    """The Windows module, loaded under a Windows platform on any host.

    It is loaded under a name of its own, so no other suite can reach this
    copy, and whatever it imports leaves `sys.modules` again afterwards. The
    standard library modules that pick a platform branch at import time are
    imported first, while the platform is still this machine's."""
    for name in ("psutil", "shutil", "subprocess"):
        importlib.import_module(name)
    spec = importlib.util.spec_from_file_location("windows_process_stop_subject", MODULE)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    imported = set(sys.modules)
    host = sys.platform
    sys.platform = "win32"
    try:
        spec.loader.exec_module(module)
    finally:
        sys.platform = host
    try:
        yield module
    finally:
        for name in set(sys.modules) - imported:
            del sys.modules[name]


@pytest.fixture
def win32_errors(monkeypatch):
    """The Win32 error slot and `WinError`, answered here on every platform.

    `ctypes.get_last_error`, `set_last_error` and `WinError` exist only on
    Windows, and which error a failing call leaves behind is part of what is
    under test."""
    slot = [0]
    monkeypatch.setattr(ctypes, "get_last_error", lambda: slot[0], raising=False)
    monkeypatch.setattr(ctypes, "set_last_error", lambda value: slot.__setitem__(0, value), raising=False)
    monkeypatch.setattr(
        ctypes,
        "WinError",
        lambda code=None, descr=None: PermissionError(slot[0] if code is None else code, descr or "stand-in"),
        raising=False,
    )
    return slot


class _Kernel:
    """kernel32 as `terminate` reaches it, over one process we describe.

    Every call leaves its own error behind, the way GetLastError does, so a
    reading taken after the wrong call reports the wrong number."""

    def __init__(
        self, *, created: float = STARTED, refuses: int | None = None,
        signalled: bool = False, exit_code: int = STILL_ACTIVE, probes_leave: int = INVALID_HANDLE,
    ) -> None:
        self.created = created
        self.refuses = refuses
        self.signalled = signalled
        self.exit_code = exit_code
        self.probes_leave = probes_leave
        self.calls: list[str] = []

    def OpenProcess(self, _access, _inherit, _pid):
        self.calls.append("OpenProcess")
        return HANDLE

    def GetProcessTimes(self, _handle, created, *_rest):
        self.calls.append("GetProcessTimes")
        ticks = round((self.created + FILETIME_EPOCH) * 10_000_000)
        filetime = ctypes.cast(created, ctypes.POINTER(wintypes.FILETIME)).contents
        filetime.dwHighDateTime, filetime.dwLowDateTime = ticks >> 32, ticks & 0xFFFFFFFF
        return 1

    def TerminateProcess(self, _handle, _code):
        self.calls.append("TerminateProcess")
        if self.refuses is None:
            return 1
        ctypes.set_last_error(self.refuses)
        return 0

    def WaitForSingleObject(self, _handle, _timeout):
        self.calls.append("WaitForSingleObject")
        ctypes.set_last_error(self.probes_leave)
        return WAIT_OBJECT_0 if self.signalled else WAIT_TIMEOUT

    def GetExitCodeProcess(self, _handle, code):
        self.calls.append("GetExitCodeProcess")
        ctypes.set_last_error(self.probes_leave)
        ctypes.cast(code, ctypes.POINTER(wintypes.DWORD)).contents.value = self.exit_code
        return 1

    def CloseHandle(self, _handle):
        self.calls.append("CloseHandle")
        return 1


class _Target:
    """A process as `psutil` describes it to `terminate`: a PID and a start time."""

    pid = 4242

    def __init__(self, created: float) -> None:
        self.created = created

    def create_time(self) -> float:
        return self.created

    def is_running(self) -> bool:
        return True


@pytest.fixture
def stop(windows_process, win32_errors, monkeypatch):
    """`terminate` against a described kernel, for a process psutil says began
    at `started` (by default the one the kernel object itself reports)."""

    def run(kernel: _Kernel, *, started: float | None = None):
        monkeypatch.setattr(windows_process, "_kernel", lambda: kernel)
        return windows_process.terminate(_Target(kernel.created if started is None else started))

    return run


def test_a_process_already_on_its_way_out_is_gone_rather_than_an_error(stop):
    """The refusal a stop meets under load: the call is denied, the object is
    not signalled yet, and the exit status is the only witness."""
    kernel = _Kernel(refuses=ACCESS_DENIED, signalled=False, exit_code=137)
    assert stop(kernel) is False, "an exit status that is no longer STILL_ACTIVE means the process is gone"
    assert "GetExitCodeProcess" in kernel.calls, "the wait cannot answer for a process that is still exiting"
    assert "CloseHandle" in kernel.calls


def test_a_signalled_kernel_object_still_answers_without_the_exit_status(stop):
    kernel = _Kernel(refuses=ACCESS_DENIED, signalled=True)
    assert stop(kernel) is False
    assert "GetExitCodeProcess" not in kernel.calls, "a signalled object settles it; nothing else is asked"


def test_a_live_process_that_refuses_to_die_still_raises(stop):
    kernel = _Kernel(refuses=ACCESS_DENIED, signalled=False, exit_code=STILL_ACTIVE)
    with pytest.raises(PermissionError):
        stop(kernel)


def test_the_error_raised_is_the_one_the_refused_call_left(stop):
    """The probes that follow leave their own error behind, and reporting that
    one would name a failure that never happened."""
    kernel = _Kernel(refuses=ACCESS_DENIED, signalled=False, exit_code=STILL_ACTIVE, probes_leave=INVALID_HANDLE)
    with pytest.raises(PermissionError) as refusal:
        stop(kernel)
    assert refusal.value.args[0] == ACCESS_DENIED, "the error belongs to TerminateProcess, not to the probes"


def test_a_recycled_pid_is_gone_and_nothing_is_terminated(stop):
    kernel = _Kernel(created=STARTED)
    assert stop(kernel, started=STARTED + 5) is False
    assert "TerminateProcess" not in kernel.calls, "a different kernel object carries this PID now"


def test_a_process_this_call_terminates_is_reported_terminated(stop):
    kernel = _Kernel()
    assert stop(kernel) is True
    assert "WaitForSingleObject" not in kernel.calls, "a call that succeeded asks nothing further"

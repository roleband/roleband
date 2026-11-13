"""Owned Windows process trees, console cancellation and parent lifetime monitoring."""

from __future__ import annotations

import argparse
import ctypes
import os
import shutil
import subprocess
import sys
import threading
from ctypes import wintypes
from datetime import UTC, datetime
from pathlib import Path

import psutil

from tracker.platform.windows_private import private_attributes

if sys.platform != "win32":
    raise ImportError("Windows process control requires Windows")

CANCELLABLE_ENV = "ROLEBAND_CANCELLABLE_PROCESS"
_MARKER = "tracker.supervisor.child"
#: The exit code a live process reports. A process that really exits with it is
#: indistinguishable by exit code alone, which is why the wait below is asked first.
_STILL_ACTIVE = 259
_job_handle: int | None = None


class _Limits(ctypes.Structure):
    _fields_ = [
        ("process_time", ctypes.c_int64), ("job_time", ctypes.c_int64),
        ("flags", wintypes.DWORD), ("min_working_set", ctypes.c_size_t),
        ("max_working_set", ctypes.c_size_t), ("active_processes", wintypes.DWORD),
        ("affinity", ctypes.c_size_t), ("priority", wintypes.DWORD), ("scheduling", wintypes.DWORD),
    ]


class _ExtendedLimits(ctypes.Structure):
    _fields_ = [
        ("basic", _Limits), ("io", ctypes.c_uint64 * 6),
        ("process_memory", ctypes.c_size_t), ("job_memory", ctypes.c_size_t),
        ("peak_process_memory", ctypes.c_size_t), ("peak_job_memory", ctypes.c_size_t),
    ]


def _kernel():
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.CreateJobObjectW.argtypes = [wintypes.LPVOID, wintypes.LPCWSTR]
    kernel.CreateJobObjectW.restype = wintypes.HANDLE
    kernel.SetInformationJobObject.argtypes = [wintypes.HANDLE, ctypes.c_int, wintypes.LPVOID, wintypes.DWORD]
    kernel.AssignProcessToJobObject.argtypes = [wintypes.HANDLE, wintypes.HANDLE]
    kernel.GetCurrentProcess.restype = wintypes.HANDLE
    kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    kernel.OpenProcess.restype = wintypes.HANDLE
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel.GetProcessTimes.argtypes = [wintypes.HANDLE, *([ctypes.POINTER(wintypes.FILETIME)] * 4)]
    kernel.TerminateProcess.argtypes = [wintypes.HANDLE, wintypes.UINT]
    kernel.GetExitCodeProcess.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]
    kernel.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
    kernel.WaitForSingleObject.restype = wintypes.DWORD
    kernel.AttachConsole.argtypes = [wintypes.DWORD]
    kernel.GenerateConsoleCtrlEvent.argtypes = [wintypes.DWORD, wintypes.DWORD]
    kernel.SetConsoleCtrlHandler.argtypes = [wintypes.LPVOID, wintypes.BOOL]
    return kernel


def enter_job() -> None:
    """Contain the trampoline before it can create any command or descendant."""
    global _job_handle
    kernel = _kernel()
    with private_attributes() as attributes:
        job = kernel.CreateJobObjectW(ctypes.byref(attributes), None)
    if not job:
        raise ctypes.WinError(ctypes.get_last_error())
    limits = _ExtendedLimits()
    limits.basic.flags = 0x2000  # JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
    try:
        if not kernel.SetInformationJobObject(job, 9, ctypes.byref(limits), ctypes.sizeof(limits)):
            raise ctypes.WinError(ctypes.get_last_error())
        if not kernel.AssignProcessToJobObject(job, kernel.GetCurrentProcess()):
            raise ctypes.WinError(ctypes.get_last_error())
    except BaseException:
        kernel.CloseHandle(job)
        raise
    # The trampoline keeps the sole, non-inheritable handle until OS exit.
    # Closing it earlier would kill this process before it publishes its result.
    _job_handle = job
    os.environ[CANCELLABLE_ENV] = "1"


def hold_awake() -> None:
    """Hold a system execution request until the trampoline's main thread exits."""
    kernel = _kernel()
    kernel.SetThreadExecutionState.argtypes = [wintypes.DWORD]
    kernel.SetThreadExecutionState.restype = wintypes.DWORD
    if not kernel.SetThreadExecutionState(0x80000001):
        raise ctypes.WinError(ctypes.get_last_error())


def creation_time(handle: int) -> float:
    values = [wintypes.FILETIME() for _ in range(4)]
    if not _kernel().GetProcessTimes(handle, *(ctypes.byref(value) for value in values)):
        raise ctypes.WinError(ctypes.get_last_error())
    ticks = (values[0].dwHighDateTime << 32) | values[0].dwLowDateTime
    return ticks / 10_000_000 - 11_644_473_600


def run_wrapper() -> int | None:
    """The supervisor's run wrapper this process runs under, or None outside one.

    Windows has no process groups: a stop signals the run's wrapper (`owned_process`), so its PID is what names the
    run a stop ended. A virtualenv redirector may stand between the two, so the nearest wrapper above counts."""
    try:
        ancestors = psutil.Process().parents()
    except psutil.Error:
        return None
    return next((ancestor.pid for ancestor in ancestors if owned_process(ancestor.pid) is not None), None)


def owned_process(
    pid: int, *, run_id: int | None = None, started: datetime | None = None, data_dir: Path | None = None,
) -> psutil.Process | None:
    """Prove account, parsed run marker, optional state namespace and kernel age."""
    try:
        process = psutil.Process(pid)
        began = process.create_time()
        if process.username() != psutil.Process().username():
            return None
        args = process.cmdline()
        index = args.index(_MARKER)
        if index == 0 or args[index - 1] != "-m" or args[index + 1] != "--run":
            return None
        actual_run = int(args[index + 2])
        if run_id is not None and run_id != actual_run:
            return None
        if started is not None and abs(began - started.timestamp()) > 0.001:
            return None
        if data_dir is not None:
            result = Path(args[args.index("--result") + 1]).resolve()
            if result != (data_dir / "run" / f"{actual_run}.json").resolve():
                return None
        return process
    except (psutil.Error, ValueError, IndexError, OSError):
        return None


def _gone(kernel, handle: int) -> bool:
    """Whether this kernel object's process has stopped running.

    The wait answers only once the object is signalled, which happens after the
    last thread is gone. A process that is still running its own exit path has
    an exit status already and is not signalled yet, so both questions are
    asked: TerminateProcess refuses a process in that state."""
    if kernel.WaitForSingleObject(handle, 0) == 0:
        return True
    code = wintypes.DWORD()
    if not kernel.GetExitCodeProcess(handle, ctypes.byref(code)):
        return False
    return code.value != _STILL_ACTIVE


def terminate(process: psutil.Process) -> bool:
    """Terminate the verified kernel object even if its PID is recycled later.

    False means the process this handle names is gone, by the caller's measure:
    a recycled PID, or a process that had already stopped. A process that is
    alive and refuses to die raises, and so does any other failure."""
    kernel = _kernel()
    handle = kernel.OpenProcess(0x101001, False, process.pid)
    if not handle:
        if not process.is_running():
            return False
        raise ctypes.WinError(ctypes.get_last_error())
    try:
        if abs(creation_time(handle) - process.create_time()) > 0.001:
            return False
        if not kernel.TerminateProcess(handle, 137):
            # Captured before the calls below leave their own error behind.
            error = ctypes.get_last_error()
            if _gone(kernel, handle):
                return False
            raise ctypes.WinError(error)
        return True
    finally:
        kernel.CloseHandle(handle)


def monitor_parent(pid: int, started: float) -> None:
    """A service's job closes when its particular supervisor kernel object dies."""
    kernel = _kernel()
    parent = kernel.OpenProcess(0x101000, False, pid)
    if not parent:
        raise ctypes.WinError(ctypes.get_last_error())
    if abs(creation_time(parent) - started) > 0.001:
        kernel.CloseHandle(parent)
        raise OSError("service supervisor identity changed before startup")

    def wait() -> None:
        try:
            kernel.WaitForSingleObject(parent, 0xFFFFFFFF)
            kernel.TerminateProcess(kernel.GetCurrentProcess(), 137)
        finally:
            kernel.CloseHandle(parent)

    threading.Thread(target=wait, name="supervisor-lifetime", daemon=True).start()


def popen_options(python: str, env: dict[str, str]) -> dict:
    """A hidden console and an interpreter PID that matches the process we own."""
    executable = python
    if Path(python).resolve() == Path(sys.executable).resolve():
        # The Windows venv redirector creates another process. Its base binary
        # honors this launcher variable while keeping the venv's import paths.
        executable = psutil.Process().exe()
        env["__PYVENV_LAUNCHER__"] = python
    else:
        resolved = Path(shutil.which(python) or python).resolve()
        config = resolved.parent.parent / "pyvenv.cfg"
        if config.is_file():
            values = dict(line.split("=", 1) for line in config.read_text(encoding="utf-8").splitlines() if "=" in line)
            values = {name.strip(): value.strip() for name, value in values.items()}
            selected = values.get("executable")
            if not selected and values.get("home"):
                selected = str(Path(values["home"]) / "python.exe")
            if not selected or not Path(selected).is_file():
                raise OSError("the selected virtual environment has no base interpreter")
            executable = selected
            env["__PYVENV_LAUNCHER__"] = str(resolved)
    startup = subprocess.STARTUPINFO()
    startup.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    startup.wShowWindow = subprocess.SW_HIDE
    return {"executable": executable, "creationflags": subprocess.CREATE_NEW_CONSOLE, "startupinfo": startup}


def request_interrupt(process: psutil.Process) -> bool:
    """Send CTRL_BREAK from a disposable helper attached only to the run's console."""
    env = dict(os.environ)
    env["__PYVENV_LAUNCHER__"] = sys.executable
    backend = str(Path(__file__).resolve().parents[2])
    env["PYTHONPATH"] = backend + os.pathsep + env.get("PYTHONPATH", "")
    try:
        done = subprocess.run(
            [psutil.Process().exe(), "-X", "utf8", "-m", __name__,
             "--interrupt", str(process.pid), "--created", str(process.create_time())],
            env=env, stdin=subprocess.DEVNULL, capture_output=True, timeout=10,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
    except (OSError, subprocess.SubprocessError, psutil.Error):
        return False
    return done.returncode == 0


def _interrupt(pid: int, started: float) -> bool:
    kernel = _kernel()
    expected = datetime.fromtimestamp(started, UTC)
    if owned_process(pid, started=expected) is None:
        return True
    kernel.FreeConsole()
    if not kernel.AttachConsole(pid):
        return False
    handler_type = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.DWORD)
    handler = handler_type(lambda _event: True)
    try:
        if not kernel.SetConsoleCtrlHandler(handler, True):
            return False
        if owned_process(pid, started=expected) is None:
            return True
        return bool(kernel.GenerateConsoleCtrlEvent(1, 0))
    finally:
        kernel.FreeConsole()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--interrupt", type=int, required=True)
    parser.add_argument("--created", type=float, required=True)
    arguments = parser.parse_args()
    sys.exit(0 if _interrupt(arguments.interrupt, arguments.created) else 1)

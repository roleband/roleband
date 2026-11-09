"""Serve an authenticated engine on an exclusively owned loopback socket.

On Windows the supervisor owns the socket for the engine's whole life and hands each API process a
duplicate of it. Loopback ports are shared by every account on the PC: a port that went free while
the API restarted could be taken by another account's process, which the browser would then treat
as the engine's own address.
"""

from __future__ import annotations

import argparse
import os
import socket
import sys
import time
from pathlib import Path

import uvicorn

from tracker.platform.local_http import origin

#: Set by the supervisor: wait for its socket instead of binding the port.
SHARED_ENV = "ROLEBAND_HTTP_SHARED_LISTENER"
#: How long an API process waits for the supervisor's socket.
HANDOFF_SECONDS = 30.0
#: WSAPROTOCOL_INFOW, which `socket.share` produces, is well under this.
_HANDOFF_LIMIT = 4096


def exclusive_socket(host: str, port: int) -> socket.socket:
    origin(host, port)
    listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        if sys.platform == "win32":
            listener.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        listener.bind((host, port))
        return listener
    except BaseException:
        listener.close()
        raise


def handoff_path(data: Path, pid: int) -> Path:
    """Where the supervisor leaves the socket for one API process. Only that process can use it."""
    return data / "launcher" / f"api-listener-{pid}.bin"


def request_path(data: Path, pid: int) -> Path:
    """Where the API process `pid` asks for the socket. A virtualenv's python.exe and the interpreter it
    starts share one command line; only the process that will serve asks."""
    return data / "launcher" / f"api-listener-{pid}.request"


def hand_over(listener: socket.socket, data: Path, pid: int) -> None:
    """Share the supervisor's socket with the API process `pid`, which asked for it (Windows)."""
    if sys.platform != "win32":
        raise OSError("socket handover requires Windows")
    from tracker.platform.windows_fs import publish

    publish(handoff_path(data, pid), listener.share(pid))
    request_path(data, pid).unlink(missing_ok=True)


def _received(data: Path, host: str, port: int) -> socket.socket:
    """The supervisor's socket, once it has been handed to this process."""
    if sys.platform != "win32":
        raise OSError("socket handover requires Windows")
    from tracker.platform.windows_fs import publish, read_private

    path = handoff_path(data, os.getpid())
    publish(request_path(data, os.getpid()), b"")
    deadline = time.monotonic() + HANDOFF_SECONDS
    while not path.exists():
        if time.monotonic() > deadline:
            raise TimeoutError("the supervisor did not hand over the engine's socket")
        time.sleep(0.05)
    payload = read_private(path, _HANDOFF_LIMIT)
    path.unlink()
    listener = socket.fromshare(payload)
    try:
        if listener.getsockname() != (host, port):
            raise ValueError("the handed-over socket is not the engine's address")
        _release_completion_port(listener)
    except BaseException:
        listener.close()
        raise
    return listener


def _release_completion_port(listener: socket.socket) -> None:
    """Detach the socket from the I/O completion port an earlier API process tied it to.

    A socket is tied to at most one completion port for its life, and every handle shares that tie: the
    proactor event loop of the next API process would otherwise fail to accept on it (WinError 87).
    FileReplaceCompletionInformation with no port removes the tie (Windows 8.1 and later).
    """
    if sys.platform != "win32":
        raise OSError("completion ports are a Windows mechanism")
    import ctypes
    from ctypes import wintypes

    class IoStatusBlock(ctypes.Structure):
        _fields_ = [("status", ctypes.c_void_p), ("information", ctypes.c_void_p)]

    class CompletionInformation(ctypes.Structure):
        _fields_ = [("port", wintypes.HANDLE), ("key", ctypes.c_void_p)]

    ntdll = ctypes.WinDLL("ntdll")
    ntdll.NtSetInformationFile.argtypes = [
        wintypes.HANDLE, ctypes.POINTER(IoStatusBlock), ctypes.c_void_p, wintypes.ULONG, ctypes.c_int,
    ]
    ntdll.NtSetInformationFile.restype = ctypes.c_long
    replace_completion, status_success, status_invalid_parameter = 61, 0, 0xC000000D
    released = CompletionInformation(None, None)
    status = ntdll.NtSetInformationFile(
        listener.fileno(), ctypes.byref(IoStatusBlock()), ctypes.byref(released), ctypes.sizeof(released),
        replace_completion,
    ) & 0xFFFFFFFF
    # The first API process finds no tie to remove, which Windows reports as an invalid parameter.
    if status not in (status_success, status_invalid_parameter):
        raise OSError(f"could not detach the engine's socket from its earlier completion port (0x{status:08X})")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", required=True, type=int)
    args = parser.parse_args()
    os.environ["ROLEBAND_LOCAL_AUTH"] = "1"
    from tracker.config import get_settings
    from tracker.platform.paths import DATA_DIR

    settings = get_settings()
    if args.host != settings.api_host or args.port != settings.api_port:
        parser.error("HTTP endpoint must match the engine configuration")
    shared = sys.platform == "win32" and os.environ.get(SHARED_ENV) == "1"
    listener = _received(DATA_DIR, args.host, args.port) if shared else exclusive_socket(args.host, args.port)
    with listener:
        os.environ["ROLEBAND_HTTP_EXCLUSIVE"] = "1"
        config = uvicorn.Config("tracker.api.app:app", host=args.host, port=args.port, access_log=False)
        uvicorn.Server(config).run(sockets=[listener])


if __name__ == "__main__":
    main()

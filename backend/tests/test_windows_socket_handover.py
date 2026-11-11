"""The supervisor hands the engine's socket to the API process that asks for it, and to no other."""

from __future__ import annotations

import asyncio
import os
import socket
import subprocess
import sys

import pytest

from tests.conftest import allow_windows_process_control
from tracker.platform.paths import REPO_ROOT

pytestmark = [
    pytest.mark.skipif(sys.platform != "win32", reason="Windows private storage requires Windows"),
    pytest.mark.usefixtures("no_escape"),
]

REAL_POPEN = subprocess.Popen

MARKER = "tracker.supervisor.http_server"
#: The API server, as `python -c` with the module's name among its arguments, the way the supervisor sees it.
RECEIVER = (
    "import sys; from pathlib import Path; from tracker.supervisor.http_server import _received; "
    "print(_received(Path(sys.argv[2]), '127.0.0.1', int(sys.argv[3])).getsockname()[1])"
)
#: A virtualenv's python.exe: the same command line, starting the real interpreter as its child a moment later.
LAUNCHER = (
    "import subprocess, sys, time; time.sleep(1.0); "
    f"sys.exit(subprocess.run([sys.executable, '-c', {RECEIVER!r}, *sys.argv[1:]]).returncode)"
)
#: The Windows trampoline the supervisor starts, which runs the launcher.
TRAMPOLINE = (
    "import subprocess, sys; "
    f"sys.exit(subprocess.run([sys.executable, '-c', {LAUNCHER!r}, *sys.argv[1:]]).returncode)"
)


@pytest.fixture(autouse=True)
def real_processes(no_escape, monkeypatch):
    monkeypatch.setattr(subprocess, "Popen", REAL_POPEN)
    allow_windows_process_control(monkeypatch)


def test_the_socket_reaches_the_api_process_behind_a_launcher_with_its_command_line(tmp_path):
    from tracker.platform.windows_private import private_directory
    from tracker.supervisor.api import ApiService
    from tracker.supervisor.http_server import exclusive_socket

    data = tmp_path / "state"
    private_directory(data)
    with socket.socket() as reservation:
        reservation.bind(("127.0.0.1", 0))
        port = reservation.getsockname()[1]
    service = ApiService(repo_root=REPO_ROOT, data_dir=data, host="127.0.0.1", port=port,
                         env={"ROLEBAND_LOCAL_AUTH": "1"})
    assert service.shares_listener
    private_directory(data / "launcher")
    service._listener = exclusive_socket("127.0.0.1", port)
    env = {**os.environ, "PYTHONPATH": str(REPO_ROOT / "backend")}
    trampoline = subprocess.Popen(
        [sys.executable, "-c", TRAMPOLINE, MARKER, str(data), str(port)], env=env,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
    )
    try:
        asyncio.run(service._hand_over(trampoline))
        output, errors = trampoline.communicate(timeout=60)
    finally:
        if trampoline.poll() is None:
            trampoline.kill()
        service.close()
    assert trampoline.returncode == 0, errors
    assert output.strip() == str(port), "the API process serves on the supervisor's socket"
    assert not list((data / "launcher").glob("api-listener-*")), "nothing is left for a process that never asked"

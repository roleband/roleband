"""A crash's leftover lock file never keeps the database from starting, and a live server keeps its own.

After a crash, `postmaster.pid` (and the socket's lock file) can name a process number that now belongs to
another program, or be empty or half-written. Postgres refuses to start over either, so the start clears them
first. The same clearing must never touch a running server's lock file: Postgres shuts a live server down within
a minute of losing it. The negative controls attach a second process to a live server whose data path has a
space in it, reached through a link and directly.
"""

from __future__ import annotations

import os
import signal
import subprocess
import sys
from pathlib import Path

import pytest

pytest.importorskip("pixeltable_pgserver", reason="embedded Postgres wheel not installed")

import psutil  # noqa: E402 - a pgserver dependency, present whenever the wheel is

from tests.embedded_utils import cluster_locale, destroy, psql  # noqa: E402
from tracker.platform.embedded_db import EmbeddedServer, ensure_server, stop_server  # noqa: E402

pytestmark = pytest.mark.skipif(sys.platform == "win32", reason="the POSIX database start clears a crash's lock files")

BACKEND = Path(__file__).resolve().parents[1]


def _start(pgdata: Path) -> EmbeddedServer:
    return ensure_server(pgdata, database="probe", locale=cluster_locale())


def _postmaster(pgdata: Path) -> int:
    return int((pgdata / "postmaster.pid").read_text().splitlines()[0])


def _socket_lock(lines: list[str]) -> Path:
    """The socket's lock file a postmaster.pid names: its socket directory and port."""
    return Path(lines[4]) / f".s.PGSQL.{lines[3]}.lock"


def _crash_leftovers(server: EmbeddedServer, pid: int) -> None:
    """Stop the server, then put back both its lock files as a crash leaves them, naming `pid`."""
    lines = (server.pgdata / "postmaster.pid").read_text().splitlines()
    socket_lock = _socket_lock(lines)
    socket_lines = socket_lock.read_text().splitlines()
    assert stop_server(server.pgdata)
    assert not socket_lock.exists()
    (server.pgdata / "postmaster.pid").write_text("\n".join([str(pid), *lines[1:]]) + "\n")
    socket_lock.write_text("\n".join([str(pid), *socket_lines[1:]]) + "\n")


def _dead_pid() -> int:
    finished = subprocess.run([sys.executable, "-c", "import os; print(os.getpid())"], capture_output=True, text=True,
                              check=True)
    pid = int(finished.stdout)
    assert not psutil.pid_exists(pid)
    return pid


@pytest.fixture
def server(tmp_path):
    server = _start(tmp_path / "db")
    psql(server, "CREATE TABLE kept(value text); INSERT INTO kept VALUES ('before the crash')")
    try:
        yield server
    finally:
        destroy(server.pgdata)


@pytest.fixture
def sleeper():
    process = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(120)"])
    try:
        yield process
    finally:
        process.kill()
        process.wait()


def test_a_lock_naming_a_live_program_of_this_account_is_cleared(server, sleeper):
    _crash_leftovers(server, sleeper.pid)
    restarted = _start(server.pgdata)
    assert psql(restarted, "SELECT value FROM kept") == "before the crash"
    assert _postmaster(server.pgdata) != sleeper.pid
    assert sleeper.poll() is None


def test_a_lock_naming_another_clusters_server_is_cleared_and_that_server_runs_on(server, tmp_path):
    other = _start(tmp_path / "other" / "db")
    try:
        other_pid = _postmaster(other.pgdata)
        other_lock = (other.pgdata / "postmaster.pid").read_text()
        _crash_leftovers(server, other_pid)
        restarted = _start(server.pgdata)
        assert psql(restarted, "SELECT value FROM kept") == "before the crash"
        assert _postmaster(server.pgdata) != other_pid
        assert psql(other, "SELECT 1") == "1"
        assert (other.pgdata / "postmaster.pid").read_text() == other_lock
        assert _socket_lock(other_lock.splitlines()).exists()
    finally:
        destroy(other.pgdata)


@pytest.mark.parametrize("content", ["", "\n", "garbled\n"], ids=["empty", "blank line", "garbled"])
def test_an_unreadable_lock_is_cleared(server, content):
    assert stop_server(server.pgdata)
    (server.pgdata / "postmaster.pid").write_text(content)
    restarted = _start(server.pgdata)
    assert psql(restarted, "SELECT value FROM kept") == "before the crash"


def test_a_lock_half_written_by_a_server_that_died_starting_is_replaced(server):
    lines = (server.pgdata / "postmaster.pid").read_text().splitlines()
    assert stop_server(server.pgdata)
    (server.pgdata / "postmaster.pid").write_text("\n".join([str(_dead_pid()), *lines[1:3]]) + "\n")
    restarted = _start(server.pgdata)
    assert psql(restarted, "SELECT value FROM kept") == "before the crash"


def test_a_killed_server_restarts_with_its_data(server):
    postmaster = psutil.Process(_postmaster(server.pgdata))
    children = postmaster.children(recursive=True)
    os.kill(postmaster.pid, signal.SIGKILL)
    _gone, alive = psutil.wait_procs([postmaster, *children], timeout=30)
    assert not alive
    assert (server.pgdata / "postmaster.pid").exists()
    # The next process to open the database starts it, as after a power loss.
    assert _attach(server.pgdata) == "before the crash"
    assert _postmaster(server.pgdata) != postmaster.pid


def _attach(pgdata: Path) -> str:
    """Attach a separate process, as the app's API and its jobs each do, and return what it reads."""
    script = (
        "import sys; from pathlib import Path\n"
        "from tracker.platform.embedded_db import ensure_server, run_psql\n"
        "server = ensure_server(Path(sys.argv[1]), database='probe')\n"
        "print(run_psql(server.dsn(), server.bin_dir, 'SELECT value FROM kept'))\n"
    )
    env = {**os.environ, "PYTHONPATH": os.pathsep.join(filter(None, [str(BACKEND), os.environ.get("PYTHONPATH")]))}
    attached = subprocess.run([sys.executable, "-c", script, str(pgdata)], capture_output=True, text=True, env=env,
                              cwd=BACKEND, timeout=120)
    assert attached.returncode == 0, attached.stderr
    return attached.stdout.strip()


def test_a_live_server_keeps_its_lock_when_another_process_attaches(tmp_path):
    real = tmp_path / "Application Support"
    real.mkdir()
    link = tmp_path / "linked"
    link.symlink_to(real, target_is_directory=True)
    server = _start(link / "db")
    try:
        psql(server, "CREATE TABLE kept(value text); INSERT INTO kept VALUES ('live')")
        lock = real / "db" / "postmaster.pid"
        before = (lock.stat().st_ino, lock.read_text())
        socket_lock = _socket_lock(before[1].splitlines())
        socket_before = (socket_lock.stat().st_ino, socket_lock.read_text())
        pid = _postmaster(real / "db")
        for path in (link / "db", real / "db"):
            assert _attach(path) == "live"
            assert (lock.stat().st_ino, lock.read_text()) == before
            assert (socket_lock.stat().st_ino, socket_lock.read_text()) == socket_before
            assert psutil.Process(pid).is_running()
        assert psql(server, "SELECT value FROM kept") == "live"
    finally:
        destroy(real / "db")

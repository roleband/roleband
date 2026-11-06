"""Windows restart preserves history while retiring only dead process metadata."""

from __future__ import annotations

import os
import sys

import psutil
import pytest

from tests.embedded_utils import psql
from tests.test_windows_checkpoint import server as server
from tracker.platform.embedded_db import EmbeddedDbError, ensure_server, stop_server

pytestmark = pytest.mark.skipif(sys.platform != "win32", reason="Windows restart requires Windows")


def _originals(server):
    state = server.pgdata.parent
    (state / "secret.key").write_bytes(b"retained synthetic key")
    return {path: path.read_bytes() for path in (state / "secret.key", state / "db.owner.json",
            state / "db.auth/cluster.json", state / "db.auth/pgpass.conf")}


def _retained(server, originals):
    assert psql(server, "SELECT count(*) FROM job_observations") == "3"
    assert psql(server, "SELECT title FROM jobs WHERE id=1") == "Éclair 中文"
    assert psql(server, "SELECT stage FROM pursuits") == "saved"
    for path, payload in originals.items():
        assert path.read_bytes() == payload


def test_crashed_postmaster_restarts_with_history_and_logs_outside_pgdata(server):
    from tracker.platform.windows_private import require_private

    originals = _originals(server)
    path = server.pgdata / "postmaster.pid"
    original = path.read_bytes()
    process = psutil.Process(int(original.splitlines()[0]))
    children = process.children()
    process.kill()
    process.wait(timeout=10)
    _gone, alive = psutil.wait_procs(children, timeout=10)
    assert not alive
    assert path.read_bytes() == original
    resumed = ensure_server(server.pgdata, database="probe")
    retained = list(server.pgdata.glob("postmaster.pid.stale-*"))
    assert len(retained) == 1 and retained[0].read_bytes() == original
    assert (server.pgdata.parent / "db.auth/postgres.log").is_file()
    assert not (server.pgdata / "log").exists()
    require_private(server.pgdata.parent / "db.auth/postgres.log")
    _retained(resumed, originals)


def test_recycled_pid_does_not_terminate_its_new_process_or_replace_credentials(server):
    originals = _originals(server)
    path = server.pgdata / "postmaster.pid"
    lines = path.read_text().splitlines()
    stop_server(server.pgdata)
    lines[0] = str(os.getpid())
    lines[2] = str(int(psutil.boot_time()) - 60)
    original = "\n".join(lines) + "\n"
    path.write_text(original)
    resumed = ensure_server(server.pgdata, database="probe")
    retained = list(server.pgdata.glob("postmaster.pid.stale-*"))
    assert len(retained) == 1 and retained[0].read_text() == original
    assert psutil.Process(os.getpid()).is_running()
    _retained(resumed, originals)


@pytest.mark.parametrize("case", ["foreign_path", "live_pid", "malformed", "cancellable"])
def test_uncertain_or_cancellable_restart_preserves_its_record(server, tmp_path, monkeypatch, case):
    from tracker.platform.windows_process import CANCELLABLE_ENV

    path = server.pgdata / "postmaster.pid"
    original = path.read_bytes()
    lines = original.decode().splitlines()
    stop_server(server.pgdata)
    if case == "foreign_path":
        lines[1] = str(tmp_path / "foreign")
    elif case == "live_pid":
        lines[0], lines[2] = str(os.getpid()), str(int(psutil.Process().create_time()))
    elif case == "malformed":
        lines = ["unreadable identity"]
    damaged = ("\n".join(lines) + "\n").encode()
    path.write_bytes(damaged)
    try:
        with monkeypatch.context() as context:
            if case == "cancellable":
                context.setenv(CANCELLABLE_ENV, "1")
            with pytest.raises(EmbeddedDbError):
                ensure_server(server.pgdata, database="probe")
        assert path.read_bytes() == damaged
        assert not list(server.pgdata.glob("postmaster.pid.stale-*"))
    finally:
        path.write_bytes(original)
        ensure_server(server.pgdata, database="probe")


def test_an_unrecorded_live_postmaster_prevents_retiring_a_spoofed_dead_record(server):
    path = server.pgdata / "postmaster.pid"
    original = path.read_bytes()
    lines = original.decode().splitlines()
    lines[0], lines[2] = str(os.getpid()), str(int(psutil.boot_time()) - 60)
    spoofed = ("\n".join(lines) + "\n").encode()
    path.write_bytes(spoofed)
    try:
        with pytest.raises(EmbeddedDbError, match="live database process owns"):
            ensure_server(server.pgdata, database="probe")
        assert path.read_bytes() == spoofed
        assert not list(server.pgdata.glob("postmaster.pid.stale-*"))
    finally:
        path.write_bytes(original)
    assert psql(server, "SELECT count(*) FROM jobs") == "2"

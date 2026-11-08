"""Windows restart preserves history while retiring only dead process metadata."""

from __future__ import annotations

import itertools
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


class _Named:
    """A real process presented under PostgreSQL's image name."""

    def __init__(self, process):
        self._process, self.pid, self.info = process, process.pid, {"name": "postgres.exe"}

    def cmdline(self):
        return self._process.cmdline()


def _unreadable_process():
    """A process of another account, whose command line this account cannot read."""
    for process in psutil.process_iter():
        try:
            process.cmdline()
        except psutil.AccessDenied:
            return process
        except psutil.Error:
            continue
    pytest.skip("this account can read every process's command line")


def _dead_record(server):
    path = server.pgdata / "postmaster.pid"
    lines = path.read_text().splitlines()
    stop_server(server.pgdata)
    lines[0], lines[2] = str(os.getpid()), str(int(psutil.boot_time()) - 60)
    record = "\n".join(lines) + "\n"
    path.write_text(record)
    return path, record


def test_another_accounts_postgres_does_not_block_retiring_a_dead_record(server, monkeypatch):
    """A PostgreSQL service or a second account's app runs postgres.exe whose
    command line this account cannot read; it cannot be serving this cluster."""
    from tracker.platform import windows_db

    originals = _originals(server)
    foreign = _unreadable_process()
    path, record = _dead_record(server)
    real = psutil.process_iter
    monkeypatch.setattr(windows_db.psutil, "process_iter",
                        lambda *args, **kwargs: itertools.chain(real(*args, **kwargs), [_Named(foreign)]))
    resumed = ensure_server(server.pgdata, database="probe")
    retained = list(server.pgdata.glob("postmaster.pid.stale-*"))
    assert len(retained) == 1 and retained[0].read_text() == record
    assert not path.read_text().startswith(f"{os.getpid()}\n")
    _retained(resumed, originals)


def test_a_record_rewritten_during_the_ownership_scan_is_not_retired(server, monkeypatch):
    from tracker.platform import windows_db

    path, record = _dead_record(server)
    real = psutil.process_iter

    def rewriting(*args, **kwargs):
        yield from real(*args, **kwargs)
        path.write_text(record + "rewritten\n")

    monkeypatch.setattr(windows_db.psutil, "process_iter", rewriting)
    try:
        with pytest.raises(EmbeddedDbError):
            ensure_server(server.pgdata, database="probe")
        assert path.read_text().endswith("rewritten\n")
        assert not list(server.pgdata.glob("postmaster.pid.stale-*"))
    finally:
        monkeypatch.undo()
        path.write_text(record)
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


class _Reused:
    """A live process as process_iter presents it once its PID has been reused: under the name of the
    process that had the PID before, which psutil keeps on Windows."""

    def __init__(self, process):
        self._process, self.info = process, {"name": "cmd.exe"}

    def __getattr__(self, attribute):
        return getattr(self._process, attribute)

    def name(self):
        return "cmd.exe"


def _postmaster_under_a_stale_name(server, monkeypatch):
    postmaster = int((server.pgdata / "postmaster.pid").read_text().splitlines()[0])
    real = psutil.process_iter
    monkeypatch.setattr(psutil, "process_iter", lambda *args, **kwargs: (
        _Reused(process) if process.pid == postmaster else process for process in real(*args, **kwargs)))


def test_a_live_postmaster_under_a_reused_pid_still_prevents_retiring_a_spoofed_record(server, monkeypatch):
    path = server.pgdata / "postmaster.pid"
    original = path.read_bytes()
    lines = original.decode().splitlines()
    lines[0], lines[2] = str(os.getpid()), str(int(psutil.boot_time()) - 60)
    spoofed = ("\n".join(lines) + "\n").encode()
    _postmaster_under_a_stale_name(server, monkeypatch)
    path.write_bytes(spoofed)
    try:
        with pytest.raises(EmbeddedDbError, match="live database process owns"):
            ensure_server(server.pgdata, database="probe")
        assert path.read_bytes() == spoofed
        assert not list(server.pgdata.glob("postmaster.pid.stale-*"))
    finally:
        monkeypatch.undo()
        path.write_bytes(original)
    assert psql(server, "SELECT count(*) FROM jobs") == "2"


def test_cleanup_finds_a_postmaster_under_a_reused_pid(server, monkeypatch):
    from tracker.supervisor.residue import clusters_under

    _postmaster_under_a_stale_name(server, monkeypatch)
    assert clusters_under(server.pgdata.parent) == [server.pgdata.resolve()]

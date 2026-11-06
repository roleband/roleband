"""Interrupted scratch restores block ordinary launch until explicitly resolved."""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import time
from contextlib import contextmanager
from pathlib import Path

import psutil
import pytest

from tests.embedded_utils import psql
from tests.test_windows_checkpoint import server as server
from tracker.platform.embedded_db import ensure_server

pytestmark = pytest.mark.skipif(sys.platform != "win32", reason="Windows recovery requires Windows")


@pytest.fixture(autouse=True)
def stop_scratch_clusters(tmp_path):
    yield
    from tracker.platform.windows_recovery import _quiesce

    for pid in tmp_path.rglob("postmaster.pid"):
        _quiesce(pid.parent)


@pytest.fixture
def checkpoint(server, tmp_path):
    from tracker.platform.windows_checkpoint import create_checkpoint

    return create_checkpoint(server, tmp_path / "checkpoint", tmp_path / "initial-drill")


def _command(action, state, *args):
    return [psutil.Process().exe(), "-I", "-B", str(Path(__file__).resolve().parents[1] / "desktop.py"),
            "--source", "recovery", action, "--state", str(state), *map(str, args)]


def _cli(action, state, *args):
    return subprocess.run(_command(action, state, *args), env={**os.environ, "__PYVENV_LAUNCHER__": sys.executable},
                          capture_output=True, text=True, timeout=120)


def _interrupted(checkpoint, state, boundary="ready"):
    log_path = state.parent / "recovery-coordinator.log"
    log = log_path.open("wb")
    try:
        process = subprocess.Popen(_command("begin", state, "--checkpoint", checkpoint),
                                   env={**os.environ, "__PYVENV_LAUNCHER__": sys.executable},
                                   stdout=log, stderr=subprocess.STDOUT)
    except BaseException:
        log.close()
        raise
    journal = state / "recovery" / "check.json"
    deadline = time.monotonic() + 120
    try:
        while time.monotonic() < deadline:
            if journal.exists():
                try:
                    record = json.loads(journal.read_text())
                except (FileNotFoundError, PermissionError):
                    time.sleep(0.005)
                    continue
                scratch = state / "recovery" / "attempts" / record["attempts"][-1]
                pid = scratch / "db" / "postmaster.pid"
                try:
                    lines = pid.read_text().splitlines() if pid.exists() else []
                    leader = int(lines[0]) if lines else 0
                except (FileNotFoundError, PermissionError, ValueError):
                    # PostgreSQL creates, rewrites and removes this file while it starts.
                    time.sleep(0.005)
                    continue
                reached = (boundary == "journal" or (boundary == "initializing" and leader < 0)
                           or (boundary == "ready" and len(lines) >= 8 and leader > 0 and lines[7].strip() == "ready"))
                if reached:
                    process.kill()
                    process.wait(timeout=10)
                    if lines:
                        try:
                            psutil.Process(abs(int(lines[0]))).wait(timeout=10)
                        except psutil.NoSuchProcess:
                            pass
                    assert record["phase"] == "verifying"
                    return record, scratch
            assert process.poll() is None, log_path.read_text(errors="replace")[-6000:]
            time.sleep(0.005)
        pytest.fail(f"Recovery did not start a real scratch database; see {log_path}")
    finally:
        if process.poll() is None:
            process.kill()
            process.wait(timeout=10)
        log.close()


def test_an_open_journal_reader_keeps_its_snapshot_without_blocking_publication(tmp_path):
    """The native host reads the journal with deletion sharing while a
    coordinator may be publishing the next phase."""
    from tracker.platform.windows_fs import reader
    from tracker.platform.windows_private import private_directory
    from tracker.platform.windows_recovery import _write, read_recovery

    state = tmp_path / "retained"
    private_directory(state)
    record = {"format": 1, "kind": "checkpoint-drill", "state": str(state), "checkpoint": str(tmp_path / "checkpoint"),
              "manifest_sha256": "a" * 64, "archive_sha256": "b" * 64, "phase": "verifying", "attempts": ["c" * 32]}
    _write(state, record)
    with reader(state / "recovery" / "check.json") as snapshot:
        _write(state, {**record, "phase": "verified"})
        assert json.load(snapshot)["phase"] == "verifying"
        assert read_recovery(state)["phase"] == "verified"
    assert [entry.name for entry in (state / "recovery").iterdir()] == ["check.json"]


def test_completed_drill_retains_history_and_allows_ordinary_database_access(checkpoint, server, tmp_path):
    from tracker.platform.windows_recovery import read_recovery, require_launchable

    state = tmp_path / "retained 中文"
    result = _cli("begin", state, "--checkpoint", checkpoint)
    assert result.returncode == 0, result.stderr
    record = read_recovery(state)
    assert record["phase"] == "verified"
    scratch = state / "recovery" / "attempts" / record["attempts"][0]
    assert (scratch / "db" / "PG_VERSION").exists()
    assert not (scratch / "db" / "postmaster.pid").exists()
    require_launchable(state)
    assert psql(server, "SELECT count(*) FROM job_observations") == "3"
    assert psql(server, "SELECT stage FROM pursuits") == "saved"
    assert json.loads(_cli("status", state).stdout)["phase"] == "verified"
    again = _cli("begin", state, "--checkpoint", checkpoint)
    assert again.returncode == 0, again.stderr
    assert len(list((state / "recovery").glob("completed-*.json"))) == 1
    assert scratch.exists()


def test_killed_coordinator_blocks_start_and_retries_into_fresh_storage(checkpoint, tmp_path):
    from tracker.platform.windows_recovery import RecoveryError, read_recovery, require_launchable

    state = tmp_path / "retained"
    record, scratch = _interrupted(checkpoint, state)
    with pytest.raises(RecoveryError, match="unfinished"):
        require_launchable(state)
    with pytest.raises(RecoveryError, match="unfinished"):
        ensure_server(state / "db", database="must_not_be_created")
    assert not (state / "db").exists()
    for action in ("run", "prepare", "seed"):
        command = _command("status", state)[:5] + [action]
        result = subprocess.run(command, env={**os.environ, "ROLEBAND_STATE_DIR": str(state),
                                              "ROLEBAND_PGDATA": str(state / "db"),
                                              "ROLEBAND_CACHE_DIR": str(state / "cache"),
                                              "ROLEBAND_PLUGINS_DIR": str(state / "plugins"),
                                              "ROLEBAND_SECRET_KEY_FILE": str(state / "secret.key"),
                                              "ROLEBAND_DATABASE_URL": "",
                                              "__PYVENV_LAUNCHER__": sys.executable},
                                capture_output=True, text=True, timeout=20)
        assert result.returncode != 0
        assert "unfinished" in result.stderr
        assert not (state / "db").exists()
    retry = _cli("retry", state)
    assert retry.returncode == 0, retry.stderr
    resolved = read_recovery(state)
    assert resolved["phase"] == "verified"
    assert resolved["attempts"][:1] == record["attempts"]
    assert len(resolved["attempts"]) == 2
    assert scratch.exists()
    pidfile = scratch / "db" / "postmaster.pid"
    if pidfile.exists():
        assert not psutil.pid_exists(abs(int(pidfile.read_text().splitlines()[0])))
    require_launchable(state)


def test_abandon_keeps_original_files_and_stops_interrupted_scratch(checkpoint, server):
    from tracker.platform.embedded_db import stop_server
    from tracker.platform.windows_recovery import require_launchable

    state = server.pgdata.parent
    stop_server(server.pgdata)
    (state / "secret.key").write_bytes(b"retained synthetic key")
    files = [state / "secret.key", state / "db.owner.json", *list((state / "db.auth").glob("*"))]
    originals = {path: path.read_bytes() for path in files if path.is_file()}
    record, scratch = _interrupted(checkpoint, state)
    result = _cli("abandon", state)
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)["phase"] == "abandoned"
    assert json.loads(result.stdout)["attempts"] == record["attempts"]
    pidfile = scratch / "db" / "postmaster.pid"
    if pidfile.exists():
        assert not psutil.pid_exists(abs(int(pidfile.read_text().splitlines()[0])))
    assert scratch.exists()
    for path, value in originals.items():
        assert path.read_bytes() == value
    require_launchable(state)
    resumed = ensure_server(server.pgdata, database="probe")
    assert psql(resumed, "SELECT count(*) FROM job_observations") == "3"
    assert psql(resumed, "SELECT stage FROM pursuits") == "saved"


@pytest.mark.parametrize("boundary", ["journal", "initializing"])
def test_interruption_before_a_listening_postmaster_can_retry(checkpoint, tmp_path, boundary):
    from tracker.platform.windows_recovery import read_recovery

    state = tmp_path / "retained"
    record, scratch = _interrupted(checkpoint, state, boundary)
    result = _cli("retry", state)
    assert result.returncode == 0, result.stderr
    resolved = read_recovery(state)
    assert resolved["phase"] == "verified"
    assert resolved["attempts"][0] == record["attempts"][0]
    assert len(resolved["attempts"]) == 2
    if boundary == "initializing":
        assert scratch.exists()


def test_changed_checkpoint_cannot_silently_replace_a_retry(checkpoint, tmp_path):
    from tracker.platform.windows_recovery import read_recovery, require_launchable

    state = tmp_path / "retained"
    record, _scratch = _interrupted(checkpoint, state)
    path = checkpoint / "checkpoint.json"
    manifest = json.loads(path.read_text())
    manifest["diagnostic"] = "changed after interruption"
    path.write_text(json.dumps(manifest))
    assert hashlib.sha256(path.read_bytes()).hexdigest() != record["manifest_sha256"]
    result = _cli("retry", state)
    assert result.returncode != 0
    assert "changed" in result.stderr
    assert read_recovery(state)["phase"] == "failed"
    assert _cli("abandon", state).returncode == 0
    require_launchable(state)


@pytest.mark.parametrize("damage", ["json", "phase", "kind", "state", "attempt", "digest"])
def test_damaged_journal_blocks_abandon_and_database_start(checkpoint, tmp_path, damage):
    from tracker.platform.windows_recovery import RecoveryError, read_recovery, require_launchable

    state = tmp_path / "retained"
    result = _cli("begin", state, "--checkpoint", checkpoint)
    assert result.returncode == 0, result.stderr
    record = read_recovery(state)
    if damage != "json":
        key, value = {"phase": ("phase", "unknown"), "kind": ("kind", "package-promotion"),
                      "state": ("state", str(tmp_path / "foreign")), "attempt": ("attempts", ["../db"]),
                      "digest": ("archive_sha256", "bad")}[damage]
        record[key] = value
    path = state / "recovery" / "check.json"
    path.write_text("{" if damage == "json" else json.dumps(record))
    with pytest.raises(RecoveryError, match="damaged"):
        require_launchable(state)
    result = _cli("abandon", state)
    assert result.returncode != 0
    assert "damaged" in result.stderr
    assert path.exists()


@pytest.mark.parametrize("name", ["desktop.lock", "engine.lock"])
def test_live_engine_lease_blocks_journal_creation(checkpoint, tmp_path, name):
    from tracker.platform import filelock
    from tracker.platform.windows_private import private_directory

    state = tmp_path / "retained"
    private_directory(state)
    private_directory(state / "launcher")
    with (state / "launcher" / name).open("a+b") as lease:
        filelock.lock(lease, blocking=False)
        result = _cli("begin", state, "--checkpoint", checkpoint)
        assert result.returncode != 0
        assert not (state / "recovery").exists()


@contextmanager
def _app_holds(path):
    """The native host's lease: the file opened without sharing."""
    import ctypes
    from ctypes import wintypes

    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.CreateFileW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, ctypes.c_void_p,
                                   wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE]
    kernel.CreateFileW.restype = wintypes.HANDLE
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    read_write, share_none, open_always, normal = 0xC0000000, 0, 4, 0x80
    handle = kernel.CreateFileW(str(path), read_write, share_none, None, open_always, normal, None)
    assert handle != wintypes.HANDLE(-1).value, ctypes.get_last_error()
    try:
        yield
    finally:
        assert kernel.CloseHandle(handle)


@contextmanager
def _engine_holds(path):
    """An engine's lease, held by another process through the engine's own code."""
    code = ("import sys\nfrom pathlib import Path\nfrom tracker.platform.windows_leases import lease\n"
            "with lease(Path(sys.argv[1])):\n    print('held', flush=True)\n    sys.stdin.read()\n")
    holder = subprocess.Popen([sys.executable, "-c", code, str(path)], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                              text=True, env={**os.environ, "PYTHONPATH": str(Path(__file__).resolve().parents[1])})
    try:
        assert holder.stdout.readline().strip() == "held"
        yield
    finally:
        holder.stdin.close()
        holder.wait(timeout=20)


@pytest.mark.parametrize("command", ["recovery", "restore", "checkpoint"])
@pytest.mark.parametrize(("holder", "name"), [(_app_holds, "desktop.lock"), (_engine_holds, "engine.lock")],
                         ids=["app", "engine"])
def test_every_operator_command_refuses_a_held_lease_before_changing_state(
    checkpoint, server, tmp_path, command, holder, name,
):
    from tracker.platform.embedded_db import stop_server
    from tracker.platform.windows_private import private_directory

    stop_server(server.pgdata)
    state = server.pgdata.parent
    private_directory(state / "launcher")
    arguments = {
        "recovery": ["recovery", "begin", "--state", state, "--checkpoint", checkpoint],
        "restore": ["restore", "begin", "--state", state, "--checkpoint", checkpoint, "--preserve-current"],
        "checkpoint": ["checkpoint", "create", "--pgdata", server.pgdata, "--database", "probe",
                       "--destination", tmp_path / "blocked", "--verification-state", tmp_path / "blocked-verify"],
    }[command]
    with holder(state / "launcher" / name):
        result = subprocess.run(_command("status", state)[:5] + [str(item) for item in arguments],
                                env={**os.environ, "__PYVENV_LAUNCHER__": sys.executable},
                                capture_output=True, text=True, timeout=60)
    assert result.returncode != 0
    assert f"{name} is held" in result.stderr
    assert not (state / "recovery").exists()
    assert not (server.pgdata / "postmaster.pid").exists()
    assert not (tmp_path / "blocked").exists() and not (tmp_path / "blocked-verify").exists()


def test_running_source_database_refuses_drill_without_a_journal(checkpoint, server):
    result = _cli("begin", server.pgdata.parent, "--checkpoint", checkpoint)
    assert result.returncode != 0
    assert "Stop the current database" in result.stderr
    assert not (server.pgdata.parent / "recovery").exists()
    assert psql(server, "SELECT count(*) FROM jobs") == "2"


def test_foreign_process_in_scratch_pidfile_blocks_resolution(checkpoint, tmp_path):
    """A live process that is not PostgreSQL, started when the record says."""
    state = tmp_path / "retained"
    _record, scratch = _interrupted(checkpoint, state)
    path = scratch / "db" / "postmaster.pid"
    original = path.read_bytes()
    lines = original.decode().splitlines()
    lines[0], lines[2] = str(os.getpid()), str(int(psutil.Process().create_time()))
    path.write_text("\n".join(lines) + "\n")
    try:
        result = _cli("abandon", state)
        assert result.returncode != 0
        assert "Cannot verify" in result.stderr
        assert path.exists()
    finally:
        path.write_bytes(original)
        result = _cli("abandon", state)
        assert result.returncode == 0, result.stderr


def test_a_recycled_pid_in_a_scratch_pidfile_does_not_block_resolution(checkpoint, tmp_path):
    """Windows reuses process IDs: a live process that started at another time
    than the record is not the postmaster, which has exited."""
    from tracker.platform.windows_recovery import read_recovery

    state = tmp_path / "retained"
    _record, scratch = _interrupted(checkpoint, state)
    path = scratch / "db" / "postmaster.pid"
    lines = path.read_text().splitlines()
    lines[0], lines[2] = str(os.getpid()), str(int(psutil.Process().create_time()) - 600)
    path.write_text("\n".join(lines) + "\n")
    result = _cli("abandon", state)
    assert result.returncode == 0, result.stderr
    assert read_recovery(state)["phase"] == "abandoned"
    assert path.exists(), "the record is retained with its attempt"
    assert psutil.Process(os.getpid()).is_running()


def test_public_journal_cannot_authorize_launch(checkpoint, tmp_path):
    from tracker.platform.windows_private import PrivatePathError
    from tracker.platform.windows_recovery import require_launchable

    state = tmp_path / "retained"
    result = _cli("begin", state, "--checkpoint", checkpoint)
    assert result.returncode == 0, result.stderr
    path = state / "recovery" / "check.json"
    subprocess.run(["icacls", str(path), "/grant", "*S-1-1-0:(R)"], check=True, capture_output=True)
    try:
        with pytest.raises(PrivatePathError, match="another account"):
            require_launchable(state)
        assert _cli("abandon", state).returncode != 0
    finally:
        subprocess.run(["icacls", str(path), "/remove:g", "*S-1-1-0"], check=True, capture_output=True)

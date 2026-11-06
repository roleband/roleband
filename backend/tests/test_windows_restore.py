"""Checkpoint promotion preserves failed data and the retained account secrets."""

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
from cryptography.fernet import Fernet

from tests.embedded_utils import psql
from tests.test_windows_checkpoint import server as server
from tracker.platform.embedded_db import ensure_server, stop_server

pytestmark = pytest.mark.skipif(sys.platform != "win32", reason="Windows restore requires Windows")


@pytest.fixture
def bound_checkpoint(server, tmp_path):
    from alembic.script import ScriptDirectory

    from tracker.platform.windows_checkpoint import create_checkpoint

    heads = ScriptDirectory(str(Path(__file__).resolve().parents[1] / "alembic")).get_heads()
    assert len(heads) == 1
    psql(server, f"UPDATE alembic_version SET version_num='{heads[0]}'")
    key = Fernet.generate_key()
    (server.pgdata.parent / "secret.key").write_bytes(key)
    encrypted = Fernet(key).encrypt(b"retained synthetic credential").decode()
    psql(server, f"CREATE TABLE sealed_settings(value text); INSERT INTO sealed_settings VALUES ('{encrypted}')")
    checkpoint = create_checkpoint(server, tmp_path / "checkpoint", tmp_path / "drill")
    psql(server, "INSERT INTO jobs(id,title) VALUES (3,'Failed candidate history');"
         "INSERT INTO job_observations(job_id,observed_on) VALUES (3,'2026-11-06')")
    stop_server(server.pgdata)
    return checkpoint


def _command(action, state, *extra):
    return [psutil.Process().exe(), "-I", "-B", str(Path(__file__).resolve().parents[1] / "desktop.py"),
            "--source", "restore", action, "--state", str(state), *map(str, extra)]


def _cli(action, state, *extra):
    return subprocess.run(_command(action, state, *extra), env={**os.environ, "__PYVENV_LAUNCHER__": sys.executable},
                          capture_output=True, text=True, encoding="utf-8", timeout=240)


def _files(directory):
    return {path.relative_to(directory).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in directory.rglob("*") if path.is_file()}


def test_restore_promotes_verified_history_and_preserves_the_failed_cluster(bound_checkpoint, server):
    state = server.pgdata.parent
    original = _files(server.pgdata)
    secrets = {path: path.read_bytes() for path in (state / "secret.key", state / "db.owner.json", state / "db.auth/pgpass.conf")}
    result = _cli("begin", state, "--checkpoint", bound_checkpoint, "--preserve-current")
    assert result.returncode == 0, result.stderr
    record = json.loads(result.stdout)
    assert record["phase"] == "complete"
    retained = Path(record["retained_database"])
    assert _files(retained) == original
    assert retained.is_relative_to(state / "recovery")
    assert not (state / "db/postmaster.pid").exists()
    assert all(path.read_bytes() == value for path, value in secrets.items())
    restored = ensure_server(server.pgdata, database="probe")
    assert psql(restored, "SELECT count(*) FROM jobs") == "2"
    assert psql(restored, "SELECT count(*) FROM job_observations") == "3"
    assert psql(restored, "SELECT stage FROM pursuits") == "saved"
    encrypted = psql(restored, "SELECT value FROM sealed_settings").encode()
    assert Fernet((state / "secret.key").read_bytes()).decrypt(encrypted) == b"retained synthetic credential"
    assert _cli("status", state).returncode == 0


def test_repair_runtime_restores_without_opening_a_newer_incompatible_database(bound_checkpoint, server):
    from tracker.platform.embedded_db import EmbeddedDbError
    from tracker.platform.windows_storage import StorageCompatibilityError, read_json, write_json

    state = server.pgdata.parent
    path = state / "db.auth/cluster.json"
    marker = read_json(path)
    marker["minimum_reader"] = 2
    write_json(path, marker)
    with pytest.raises((EmbeddedDbError, StorageCompatibilityError), match="requires Windows reader"):
        ensure_server(server.pgdata, database="probe")
    original = _files(server.pgdata)
    result = _cli("begin", state, "--checkpoint", bound_checkpoint, "--preserve-current")
    assert result.returncode == 0, result.stderr
    record = json.loads(result.stdout)
    assert _files(Path(record["retained_database"])) == original
    assert read_json(path)["minimum_reader"] == 1
    restored = ensure_server(server.pgdata, database="probe")
    assert psql(restored, "SELECT count(*) FROM jobs") == "2"


@pytest.mark.parametrize("case", ["key", "password", "schema", "unbound"])
def test_untrusted_restore_input_is_refused_before_changing_the_database(bound_checkpoint, server, case):
    state = server.pgdata.parent
    if case == "key":
        (state / "secret.key").write_bytes(Fernet.generate_key())
    elif case == "password":
        path = state / "db.auth/pgpass.conf"
        path.write_bytes(path.read_bytes() + b"\n")
    else:
        path = bound_checkpoint / "checkpoint.json"
        manifest = json.loads(path.read_text())
        if case == "schema":
            manifest["facts"]["schema_heads"] = ["unknown_future_schema"]
        else:
            manifest.pop("retained_profile")
        path.write_text(json.dumps(manifest))
    before = _files(server.pgdata)
    result = _cli("begin", state, "--checkpoint", bound_checkpoint, "--preserve-current")
    assert result.returncode != 0
    assert "does not bind" in result.stderr
    assert not (state / "recovery/restore.json").exists()
    assert _files(server.pgdata) == before


def test_active_database_or_missing_preservation_flag_cannot_begin_restore(bound_checkpoint, server):
    state = server.pgdata.parent
    refused = _cli("begin", state, "--checkpoint", bound_checkpoint)
    assert refused.returncode != 0 and "--preserve-current" in refused.stderr
    ensure_server(server.pgdata, database="probe")
    refused = _cli("begin", state, "--checkpoint", bound_checkpoint, "--preserve-current")
    assert refused.returncode != 0 and "Stop the current database" in refused.stderr
    assert not (state / "recovery/restore.json").exists()


def test_legacy_storage_adoption_keeps_credentials_and_retains_the_old_metadata(server):
    from tracker.platform.windows_storage import read_json, write_json

    state = server.pgdata.parent
    stop_server(server.pgdata)
    marker = state / "db.auth/cluster.json"
    legacy = {"format": 1, "pgdata": str(server.pgdata), "version": 16}
    write_json(marker, legacy)
    password = (state / "db.auth/pgpass.conf").read_bytes()
    resumed = ensure_server(server.pgdata, database="probe")
    assert read_json(marker)["format"] == 2
    assert read_json(marker)["minimum_reader"] == 1
    retained = list((state / "db.auth").glob("cluster.legacy-*.json"))
    assert len(retained) == 1 and read_json(retained[0]) == legacy
    assert (state / "db.auth/pgpass.conf").read_bytes() == password
    assert psql(resumed, "SELECT count(*) FROM jobs") == "2"


@contextmanager
def _deny_rename(path):
    import ctypes
    from ctypes import wintypes

    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.CreateFileW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, ctypes.c_void_p,
                                   wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE]
    kernel.CreateFileW.restype = wintypes.HANDLE
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    handle = kernel.CreateFileW(str(path), 0x80000000, 3, None, 3, 0x02000000, None)
    assert handle != wintypes.HANDLE(-1).value, ctypes.get_last_error()
    try:
        yield
    finally:
        assert kernel.CloseHandle(handle)


@pytest.mark.parametrize("resolution", ["resume", "resume_after_retaining", "abort"])
def test_directory_sharing_failure_preserves_original_and_can_be_resolved(bound_checkpoint, server, resolution):
    from tracker.platform.windows_recovery import RecoveryError, require_launchable

    state = server.pgdata.parent
    before = _files(server.pgdata)
    with _deny_rename(server.pgdata):
        result = _cli("begin", state, "--checkpoint", bound_checkpoint, "--preserve-current")
    assert result.returncode != 0 and "PermissionError" in result.stderr
    record = json.loads((state / "recovery/restore.json").read_text())
    assert record["phase"] == "retaining"
    assert _files(server.pgdata) == before
    with pytest.raises(RecoveryError, match="unfinished"):
        require_launchable(state)
    with pytest.raises(RecoveryError, match="unfinished"):
        ensure_server(server.pgdata, database="probe")
    if resolution == "resume_after_retaining":
        retained = state / "recovery" / ("restore-" + record["id"]) / "retained-db"
        server.pgdata.rename(retained)
        assert _files(retained) == before
    result = _cli("abort" if resolution == "abort" else "resume", state)
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)["phase"] == ("aborted" if resolution == "abort" else "complete")
    if resolution == "abort":
        assert _files(server.pgdata) == before
    restored = ensure_server(server.pgdata, database="probe")
    assert psql(restored, "SELECT count(*) FROM jobs") == ("3" if resolution == "abort" else "2")


def _spawn(state, checkpoint):
    return subprocess.Popen(_command("begin", state, "--checkpoint", checkpoint, "--preserve-current"),
                            env={**os.environ, "__PYVENV_LAUNCHER__": sys.executable},
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding="utf-8")


def _wait_attempt(state, process):
    from tracker.platform.windows_storage import read_json

    deadline = time.monotonic() + 120
    while time.monotonic() < deadline:
        path = state / "recovery/restore.json"
        if path.exists():
            try:
                record = read_json(path)
            except (FileNotFoundError, PermissionError):
                time.sleep(0.002)
                continue
            if record["attempts"]:
                return record
        assert process.poll() is None, process.communicate()
        time.sleep(0.002)
    pytest.fail("Restore did not publish a staging attempt")


def test_resume_recognizes_directory_switch_completed_before_metadata_publication(bound_checkpoint, server):
    state = server.pgdata.parent
    before = _files(server.pgdata)
    process = _spawn(state, bound_checkpoint)
    try:
        _wait_attempt(state, process)
        with _deny_rename(state / "db.auth/cluster.json"):
            stdout, stderr = process.communicate(timeout=180)
        assert process.returncode != 0, stdout
        assert "PermissionError" in stderr
    finally:
        if process.poll() is None:
            process.kill()
            process.wait(timeout=10)
    record = json.loads((state / "recovery/restore.json").read_text())
    assert record["phase"] == "installing"
    retained = state / "recovery" / ("restore-" + record["id"]) / "retained-db"
    assert _files(retained) == before
    assert [server.pgdata.stat().st_dev, server.pgdata.stat().st_ino] == record["restored_directory"]
    refused = _cli("abort", state)
    assert refused.returncode != 0 and "switch has begun" in refused.stderr
    resumed = _cli("resume", state)
    assert resumed.returncode == 0, resumed.stderr
    assert _files(retained) == before
    assert json.loads(resumed.stdout)["phase"] == "complete"
    restored = ensure_server(server.pgdata, database="probe")
    assert psql(restored, "SELECT count(*) FROM jobs") == "2"


def test_resume_reestablishes_the_legacy_reader_fence_before_preparation(bound_checkpoint, server):
    from tracker.platform.windows_storage import read_json, write_json

    state = server.pgdata.parent
    marker = state / "db.auth/cluster.json"
    write_json(marker, {"format": 1, "pgdata": str(server.pgdata), "version": 16})
    before = _files(server.pgdata)
    with _deny_rename(marker):
        interrupted = _cli("begin", state, "--checkpoint", bound_checkpoint, "--preserve-current")
    assert interrupted.returncode != 0 and "PermissionError" in interrupted.stderr
    assert read_json(marker)["format"] == 1
    assert json.loads((state / "recovery/restore.json").read_text())["phase"] == "preparing"
    with _deny_rename(server.pgdata):
        interrupted = _cli("resume", state)
    assert interrupted.returncode != 0 and "PermissionError" in interrupted.stderr
    assert json.loads((state / "recovery/restore.json").read_text())["phase"] == "retaining"
    assert read_json(marker)["format"] == 2
    assert _files(server.pgdata) == before
    resumed = _cli("resume", state)
    assert resumed.returncode == 0, resumed.stderr
    assert _files(Path(json.loads(resumed.stdout)["retained_database"])) == before


def test_killed_coordinator_rebuilds_staging_and_rejects_a_changed_checkpoint(bound_checkpoint, server):
    state = server.pgdata.parent
    before = _files(server.pgdata)
    process = _spawn(state, bound_checkpoint)
    try:
        record = _wait_attempt(state, process)
        process.kill()
        process.communicate(timeout=10)
    finally:
        if process.poll() is None:
            process.kill()
            process.wait(timeout=10)
    assert record["phase"] == "preparing"
    assert _files(server.pgdata) == before
    manifest = bound_checkpoint / "checkpoint.json"
    original = manifest.read_bytes()
    manifest.write_bytes(original + b"\n")
    refused = _cli("resume", state)
    assert refused.returncode != 0 and "changed after" in refused.stderr
    assert _files(server.pgdata) == before
    manifest.write_bytes(original)
    resumed = _cli("resume", state)
    assert resumed.returncode == 0, resumed.stderr
    final = json.loads(resumed.stdout)
    assert final["attempts"][:1] == record["attempts"] and len(final["attempts"]) == 2
    assert _files(Path(final["retained_database"])) == before


@pytest.mark.parametrize("payload", ["{", "{}", "null", "[]"])
def test_damaged_restore_journal_blocks_every_ordinary_entry_point(tmp_path, payload):
    from tracker.platform.windows_private import private_directory

    state = tmp_path / "state"
    private_directory(state / "recovery")
    journal = state / "recovery/restore.json"
    journal.write_text(payload)
    for action in ("run", "prepare", "seed"):
        command = _command("status", state)[:5] + [action]
        result = subprocess.run(command, env={**os.environ, "ROLEBAND_STATE_DIR": str(state),
                                              "ROLEBAND_PGDATA": str(state / "db"),
                                              "ROLEBAND_CACHE_DIR": str(state / "cache"),
                                              "ROLEBAND_PLUGINS_DIR": str(state / "plugins"),
                                              "ROLEBAND_SECRET_KEY_FILE": str(state / "secret.key"),
                                              "__PYVENV_LAUNCHER__": sys.executable},
                                capture_output=True, text=True, timeout=30)
        assert result.returncode != 0
        assert "damaged" in result.stderr
        assert journal.read_text() == payload
        assert not (state / "db").exists()


@pytest.mark.parametrize("change", [{"format": True}, {"version": 16.0}, {"minimum_reader": True},
                                    {"minimum_reader": 0}, {"minimum_reader": 65536}, {"extra": 1}])
def test_invalid_storage_contract_never_authorizes_a_reader(tmp_path, change):
    from tracker.platform.windows_storage import StorageCompatibilityError, metadata, validate

    pgdata = tmp_path / "db"
    with pytest.raises(StorageCompatibilityError):
        validate({**metadata(pgdata), **change}, pgdata)


def test_failed_final_shutdown_cannot_leave_ordinary_startup_authorized(bound_checkpoint, server, monkeypatch):
    from tracker.platform import windows_restore
    from tracker.platform.windows_recovery import RecoveryError, require_launchable

    state = server.pgdata.parent
    quiesce = windows_restore._quiesce

    def failed_final_shutdown(pgdata):
        if pgdata == server.pgdata:
            raise OSError("synthetic unavailable shutdown boundary")
        return quiesce(pgdata)

    try:
        with monkeypatch.context() as boundary:
            boundary.setattr(windows_restore, "_quiesce", failed_final_shutdown)
            with pytest.raises(OSError, match="unavailable shutdown"):
                windows_restore.restore(state, "begin", bound_checkpoint)
        with pytest.raises(RecoveryError, match="unfinished"):
            require_launchable(state)
        with pytest.raises(RecoveryError, match="unfinished"):
            ensure_server(server.pgdata, database="probe")
    finally:
        quiesce(server.pgdata)
    resumed = _cli("resume", state)
    assert resumed.returncode == 0, resumed.stderr
    assert json.loads(resumed.stdout)["phase"] == "complete"


def test_open_metadata_reader_keeps_its_snapshot_without_blocking_atomic_publication(tmp_path):
    from tracker.platform.windows_fs import reader
    from tracker.platform.windows_private import private_directory
    from tracker.platform.windows_storage import read_json, write_json

    private_directory(tmp_path / "state")
    path = tmp_path / "state/metadata.json"
    write_json(path, {"phase": "preparing"})
    with reader(path) as snapshot:
        write_json(path, {"phase": "prepared"})
        assert json.load(snapshot) == {"phase": "preparing"}
        assert read_json(path) == {"phase": "prepared"}


def test_metadata_replacement_preserves_the_target_when_deletion_sharing_is_denied(tmp_path):
    from tracker.platform.windows_private import private_directory
    from tracker.platform.windows_storage import read_json, write_json

    private_directory(tmp_path / "state")
    path = tmp_path / "state/metadata.json"
    write_json(path, {"phase": "preparing"})
    with _deny_rename(path), pytest.raises(PermissionError):
        write_json(path, {"phase": "prepared"})
    assert read_json(path) == {"phase": "preparing"}
    assert [entry.name for entry in path.parent.iterdir()] == ["metadata.json"], "no temporary file is left behind"

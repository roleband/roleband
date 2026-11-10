"""No Windows migration runs over retained data without a verified checkpoint of it."""

from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import time
import uuid
from pathlib import Path

import psutil
import pytest

from tests.embedded_utils import psql
from tests.test_windows_checkpoint import server as server
from tracker.platform.embedded_db import ensure_server, stop_server

pytestmark = pytest.mark.skipif(sys.platform != "win32", reason="Windows migration requires Windows")

BACKEND = Path(__file__).resolve().parents[1]
#: An earlier head; preparing from it runs every migration after it, the one adding `compare_selection.scope` first.
PREVIOUS = "a7d2f4c9e1b6"


def _record(state):
    return json.loads((state / "recovery" / "pre-migration.json").read_text(encoding="utf-8"))


def _checkpoints(state):
    folder = state / "recovery" / "pre-migration"
    return sorted(path.name for path in folder.iterdir()) if folder.exists() else []


class TestTheGuard:
    def test_a_verified_bound_checkpoint_is_made_and_recorded(self, server, tmp_path):
        from tracker.platform.windows_checkpoint import verify_checkpoint
        from tracker.platform.windows_migration import checkpoint_before_migration

        state = tmp_path / "state"
        checkpoint = checkpoint_before_migration(server, state, {"fixture_revision"}, {"next_revision"})
        manifest = json.loads((checkpoint / "checkpoint.json").read_text(encoding="utf-8"))
        assert manifest["verified"] is True
        assert manifest["facts"]["schema_heads"] == ["fixture_revision"]
        assert _record(state)["checkpoint"] == str(checkpoint)
        assert _record(state)["from_heads"] == ["fixture_revision"]
        assert _record(state)["to_heads"] == ["next_revision"]
        assert verify_checkpoint(checkpoint, tmp_path / "recheck")["verified"] is True

    def test_an_unchanged_database_reuses_its_checkpoint(self, server, tmp_path):
        from tracker.platform.windows_migration import checkpoint_before_migration

        state = tmp_path / "state"
        first = checkpoint_before_migration(server, state, {"fixture_revision"}, {"next_revision"})
        assert checkpoint_before_migration(server, state, {"fixture_revision"}, {"next_revision"}) == first
        assert len(_checkpoints(state)) == 1

    def test_history_written_since_the_checkpoint_gets_a_new_one(self, server, tmp_path):
        from tracker.platform.windows_migration import checkpoint_before_migration

        state = tmp_path / "state"
        first = checkpoint_before_migration(server, state, {"fixture_revision"}, {"next_revision"})
        psql(server, "INSERT INTO job_observations VALUES (2,'2026-11-07',null)")
        second = checkpoint_before_migration(server, state, {"fixture_revision"}, {"next_revision"})
        assert second != first
        assert _record(state)["checkpoint"] == str(second)
        assert first.exists(), "an earlier checkpoint is never removed"

    def test_an_update_keeps_the_checkpoint_from_before_its_first_migration(self, server, tmp_path):
        """A newer release taking over a failed update migrates what the failed version left; Undo still restores the
        data from before the update began."""
        from tracker.platform import windows_update_journal as journal
        from tracker.platform.windows_migration import checkpoint_before_migration
        from tracker.platform.windows_private import private_directory

        state = tmp_path / "state"
        private_directory(state)
        journal.begin(state, from_version="0.1.2", to_version="0.1.3", package=tmp_path / "u.msix", package_sha256="a" * 64)
        journal.resume(state, "0.1.3")
        first = checkpoint_before_migration(server, state, {"fixture_revision"}, {"next_revision"})
        psql(server, "INSERT INTO job_observations VALUES (2,'2026-11-09',null)")
        assert checkpoint_before_migration(server, state, {"failed_revision"}, {"newer_revision"}) == first
        assert _record(state)["from_heads"] == ["fixture_revision"]
        assert len(_checkpoints(state)) == 1

    @pytest.mark.parametrize("damage", ["archive", "missing"])
    def test_a_damaged_checkpoint_from_before_an_update_stops_its_next_migration(self, server, tmp_path, damage):
        """A newer release taking over a failed update would checkpoint what the failed version's migration left, and
        Undo would then restore that. Without the whole checkpoint from before the update, nothing migrates."""
        import shutil

        from tracker.platform import windows_update_journal as journal
        from tracker.platform.windows_checkpoint import CheckpointError
        from tracker.platform.windows_migration import checkpoint_before_migration
        from tracker.platform.windows_private import private_directory

        state = tmp_path / "state"
        private_directory(state)
        journal.begin(state, from_version="0.1.2", to_version="0.1.3", package=tmp_path / "u.msix", package_sha256="a" * 64)
        journal.resume(state, "0.1.3")
        first = checkpoint_before_migration(server, state, {"fixture_revision"}, {"next_revision"})
        psql(server, "INSERT INTO job_observations VALUES (2,'2026-11-09',null)")
        if damage == "archive":
            with (first / "database.dump").open("r+b") as archive:
                archive.seek(-1, os.SEEK_END)
                last = archive.read(1)
                archive.seek(-1, os.SEEK_END)
                archive.write(bytes([last[0] ^ 1]))
        else:
            shutil.rmtree(first)
        with pytest.raises(CheckpointError):
            checkpoint_before_migration(server, state, {"failed_revision"}, {"newer_revision"})
        assert _record(state)["checkpoint"] == str(first), "the record still names the update's way back"
        assert _checkpoints(state) == ([first.name] if damage == "archive" else []), "no other checkpoint replaces it"

    @pytest.mark.parametrize("updating", [True, False], ids=["during-an-update", "no-update"])
    def test_an_unreadable_record_stops_a_migration_only_during_an_update(self, server, tmp_path, updating):
        """During an update the record may name the way back from before it, so nothing replaces it; outside one, a
        new checkpoint protects the data as it is."""
        from tracker.platform import windows_update_journal as journal
        from tracker.platform.windows_checkpoint import CheckpointError
        from tracker.platform.windows_migration import checkpoint_before_migration
        from tracker.platform.windows_private import private_directory

        state = tmp_path / "state"
        private_directory(state)
        if updating:
            journal.begin(state, from_version="0.1.2", to_version="0.1.3", package=tmp_path / "u.msix", package_sha256="a" * 64)
            journal.resume(state, "0.1.3")
        first = checkpoint_before_migration(server, state, {"fixture_revision"}, {"next_revision"})
        record = state / "recovery" / "pre-migration.json"
        record.write_bytes(b"{not json")
        if updating:
            with pytest.raises(CheckpointError):
                checkpoint_before_migration(server, state, {"failed_revision"}, {"newer_revision"})
            assert record.read_bytes() == b"{not json", "the damaged record is kept for repair"
            assert _checkpoints(state) == [first.name], "no other checkpoint replaces it"
        else:
            second = checkpoint_before_migration(server, state, {"fixture_revision"}, {"next_revision"})
            assert second != first and _record(state)["checkpoint"] == str(second)

    def test_a_damaged_archive_is_not_reused(self, server, tmp_path):
        from tracker.platform.windows_migration import checkpoint_before_migration

        state = tmp_path / "state"
        first = checkpoint_before_migration(server, state, {"fixture_revision"}, {"next_revision"})
        with (first / "database.dump").open("r+b") as archive:
            archive.seek(-1, os.SEEK_END)
            last = archive.read(1)
            archive.seek(-1, os.SEEK_END)
            archive.write(bytes([last[0] ^ 1]))
        assert checkpoint_before_migration(server, state, {"fixture_revision"}, {"next_revision"}) != first

    def test_a_failed_checkpoint_raises_and_records_nothing(self, server, tmp_path, monkeypatch):
        from tracker.platform import windows_checkpoint
        from tracker.platform.windows_migration import checkpoint_before_migration

        def refuse(*args, **kwargs):
            raise windows_checkpoint.CheckpointError("pg_dump could not complete the recovery checkpoint")

        monkeypatch.setattr(windows_checkpoint, "_run", refuse)
        state = tmp_path / "state"
        with pytest.raises(windows_checkpoint.CheckpointError):
            checkpoint_before_migration(server, state, {"fixture_revision"}, {"next_revision"})
        assert not (state / "recovery" / "pre-migration.json").exists()


def _env(state):
    return {**os.environ, "__PYVENV_LAUNCHER__": sys.executable, "PYTHONDONTWRITEBYTECODE": "1",
            "ROLEBAND_STATE_DIR": str(state), "ROLEBAND_PGDATA": str(state / "db"),
            "ROLEBAND_CACHE_DIR": str(state / "cache"), "ROLEBAND_PLUGINS_DIR": str(state / "plugins"),
            "ROLEBAND_SECRET_KEY_FILE": str(state / "secret.key"), "ROLEBAND_DATABASE_URL": "",
            "ROLEBAND_NO_USAGE_STATS": "1"}


def _prepare(state):
    return subprocess.run([psutil.Process().exe(), "-I", "-B", str(BACKEND / "desktop.py"), "--source", "prepare"],
                          env=_env(state), cwd=BACKEND, capture_output=True, text=True, encoding="utf-8",
                          timeout=600)


@pytest.fixture
def retained(tmp_path):
    """An app-owned state at the previous schema head holding a saved role, stopped."""
    from tracker.platform.embedded_db import claim_cluster
    from tracker.platform.windows_private import private_directory

    state = tmp_path / "s"
    private_directory(state)
    claim_cluster(state / "db", "app")
    result = subprocess.run([sys.executable, "-m", "alembic", "upgrade", PREVIOUS], env=_env(state), cwd=BACKEND,
                            capture_output=True, text=True, encoding="utf-8", timeout=600)
    assert result.returncode == 0, (result.stderr + result.stdout)[-2000:]
    server = ensure_server(state / "db", database="roleband")
    psql(server, "CREATE TABLE retained_sentinel(title text); INSERT INTO retained_sentinel VALUES ('Retained role 中文')")
    stop_server(state / "db")
    try:
        yield state
    finally:
        if (state / "db" / "postmaster.pid").exists():
            stop_server(state / "db")


def _heads(state):
    server = ensure_server(state / "db", database="roleband")
    try:
        return psql(server, "SELECT version_num FROM alembic_version").split()
    finally:
        stop_server(state / "db")


class TestPreparation:
    def test_a_failed_migration_leaves_a_checkpoint_of_the_data_before_it(self, retained):
        from tracker.platform.windows_checkpoint import verify_checkpoint

        server = ensure_server(retained / "db", database="roleband")
        # A migration after PREVIOUS adds this column, so the upgrade fails and rolls back.
        psql(server, "ALTER TABLE compare_selection ADD COLUMN scope varchar(16)")
        stop_server(retained / "db")
        result = _prepare(retained)
        assert result.returncode != 0
        assert _heads(retained) == [PREVIOUS], "a failed upgrade leaves the previous schema"
        record = _record(retained)
        assert record["from_heads"] == [PREVIOUS]
        checkpoint = Path(record["checkpoint"])
        manifest = json.loads((checkpoint / "checkpoint.json").read_text(encoding="utf-8"))
        # The previous package's runtime promotes only a checkpoint at its own heads.
        assert manifest["facts"]["schema_heads"] == [PREVIOUS]
        assert manifest["retained_profile"] is not None, "the checkpoint is bound to the retained credentials"
        assert verify_checkpoint(checkpoint, retained.parent / "recheck")["verified"] is True
        assert _prepare(retained).returncode != 0
        assert _checkpoints(retained) == [checkpoint.name], "a retry over unchanged data reuses the checkpoint"

    def test_a_migration_runs_only_after_its_checkpoint(self, retained):
        result = _prepare(retained)
        assert result.returncode == 0, (result.stderr + result.stdout)[-2000:]
        assert _heads(retained) != [PREVIOUS]
        assert _record(retained)["from_heads"] == [PREVIOUS]
        assert len(_checkpoints(retained)) == 1
        server = ensure_server(retained / "db", database="roleband")
        try:
            assert "Retained role 中文" in psql(server, "SELECT title FROM retained_sentinel")
        finally:
            stop_server(retained / "db")

    def test_no_checkpoint_means_no_migration(self, retained):
        (retained / "recovery").mkdir()
        (retained / "recovery" / "pre-migration").write_text("not a directory")
        result = _prepare(retained)
        assert result.returncode != 0
        assert _heads(retained) == [PREVIOUS]
        assert not (retained / "recovery" / "pre-migration.json").exists()

    def test_a_current_schema_takes_no_checkpoint(self, retained):
        assert _prepare(retained).returncode == 0
        first = _checkpoints(retained)
        assert _prepare(retained).returncode == 0
        assert _checkpoints(retained) == first


def _free_port():
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return probe.getsockname()[1]


def _database_state(state):
    from tracker.platform.windows_fs import read_private

    try:
        return json.loads(read_private(state / "launcher" / "preparation.json", 65536)).get("database")
    except (OSError, ValueError):
        return None


def _engine(state):
    return subprocess.Popen(
        [psutil.Process().exe(), "-I", "-B", str(BACKEND / "desktop.py"), "--source", "run",
         "--marker", uuid.uuid4().hex, "--dry-run-network"],
        env={**_env(state), "ROLEBAND_API_PORT": str(_free_port())}, cwd=BACKEND,
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding="utf-8")


def _stop(engine):
    if engine.poll() is None:
        engine.stdin.write("stop\n")
        engine.stdin.close()
    try:
        return engine.communicate(timeout=120)[0]
    except subprocess.TimeoutExpired:
        for child in psutil.Process(engine.pid).children(recursive=True):
            child.kill()
        engine.kill()
        engine.communicate()
        raise


class TestTheEngine:
    def test_an_engine_start_migrates_retained_data_after_its_checkpoint(self, retained):
        """The engine runs preparation as a cancellable process, which may not start the checkpoint's
        scratch cluster; the start must still checkpoint and migrate."""
        engine = _engine(retained)
        try:
            deadline = time.monotonic() + 600
            while _database_state(retained) != "ready" and engine.poll() is None and time.monotonic() < deadline:
                time.sleep(0.5)
            ready = _database_state(retained) == "ready"
        finally:
            output = _stop(engine)
        log = (retained / "logs" / "preparation.log").read_text(encoding="utf-8", errors="replace")
        assert ready, (output + log)[-3000:]
        assert _heads(retained) != [PREVIOUS]
        record = _record(retained)
        assert record["from_heads"] == [PREVIOUS]
        assert _checkpoints(retained) == [Path(record["checkpoint"]).name], "preparation reuses the engine's checkpoint"
        server = ensure_server(retained / "db", database="roleband")
        try:
            assert "Retained role 中文" in psql(server, "SELECT title FROM retained_sentinel")
        finally:
            stop_server(retained / "db")

    def test_a_failed_migration_is_reported_by_an_engine_that_waits_to_be_stopped(self, retained):
        """The native host learns of a failed preparation from the engine's answer, and after an update offers
        Undo. An engine that exits instead reads as a crash, and every restart fails the same way."""
        server = ensure_server(retained / "db", database="roleband")
        # A migration after PREVIOUS adds this column, so the upgrade fails and rolls back.
        psql(server, "ALTER TABLE compare_selection ADD COLUMN scope varchar(16)")
        stop_server(retained / "db")
        engine = _engine(retained)
        try:
            deadline = time.monotonic() + 600
            while _database_state(retained) != "failed" and engine.poll() is None and time.monotonic() < deadline:
                time.sleep(0.5)
            reported = _database_state(retained)
            time.sleep(3)
            running = engine.poll() is None
        finally:
            output = _stop(engine)
        assert reported == "failed", output[-3000:]
        assert running, "the engine stays up, answering, until it is told to stop"
        assert engine.returncode == 0, output[-3000:]
        assert _heads(retained) == [PREVIOUS], "the failed upgrade rolled back"
        assert _record(retained)["from_heads"] == [PREVIOUS], "the checkpoint made before it stays recorded"

    def test_a_failed_checkpoint_is_reported_by_an_engine_that_waits_to_be_stopped(self, retained):
        """The engine takes the checkpoint itself before preparation; when it cannot, nothing migrates and the
        failure is reported the same way, never as an exit each restart repeats."""
        (retained / "recovery").mkdir()
        (retained / "recovery" / "pre-migration").write_text("not a directory")
        engine = _engine(retained)
        try:
            deadline = time.monotonic() + 600
            while _database_state(retained) != "failed" and engine.poll() is None and time.monotonic() < deadline:
                time.sleep(0.5)
            reported = _database_state(retained)
            time.sleep(3)
            running = engine.poll() is None
        finally:
            output = _stop(engine)
        assert reported == "failed", output[-3000:]
        assert running, "the engine stays up, answering, until it is told to stop"
        assert engine.returncode == 0, output[-3000:]
        assert _heads(retained) == [PREVIOUS], "nothing migrated"
        assert not (retained / "recovery" / "pre-migration.json").exists()
        # The engine's own checkpoint failed, not preparation on the same obstructed path.
        log = (retained / "logs" / "engine.log").read_text(encoding="utf-8", errors="replace")
        assert "pre-migration checkpoint failed" in log and "database preparation failed" not in log, log[-3000:]

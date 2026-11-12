"""Recovery copies must restore real history before becoming usable checkpoints."""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from dataclasses import replace
from pathlib import Path

import pytest

from tests.embedded_utils import psql
from tracker.platform.embedded_db import claim_cluster, ensure_server, stop_server

pytestmark = pytest.mark.skipif(sys.platform != "win32", reason="Windows embedded database requires Windows")


@pytest.fixture
def server(tmp_path):
    claim_cluster(tmp_path / "source" / "db", "app")
    server = ensure_server(tmp_path / "source" / "db", database="probe")
    psql(server, "CREATE TABLE alembic_version(version_num text PRIMARY KEY);"
         "INSERT INTO alembic_version VALUES ('fixture_revision');"
         "CREATE TABLE jobs(id integer PRIMARY KEY, title text NOT NULL, details jsonb);"
         "INSERT INTO jobs VALUES (1,'Éclair 中文', '{\"nullable\":null,\"values\":[1,2]}'),(2,'Preserved posting',null);"
         "CREATE TABLE job_observations(job_id integer REFERENCES jobs(id), observed_on date, observed_at timestamptz);"
         "INSERT INTO job_observations VALUES (1,'2025-01-01','2025-01-01T12:34:56+02'),"
         " (1,'2026-11-04','2026-11-04T18:12:30Z'),(2,'2026-11-04',null);"
         "CREATE TABLE pursuits(job_id integer REFERENCES jobs(id), stage text);"
         "INSERT INTO pursuits VALUES (1,'saved');"
         "ALTER TABLE jobs ADD COLUMN state varchar DEFAULT 'starting';"
         "ALTER TABLE jobs ADD CONSTRAINT ck_state CHECK (state IN ('starting','running'));"
         "CREATE UNIQUE INDEX uq_active_title ON jobs(title) WHERE state IN ('starting','running');"
         "CREATE SEQUENCE restored_sequence START 20; SELECT nextval('restored_sequence')")
    try:
        yield server
    finally:
        stop_server(server.pgdata)


def test_checkpoint_round_trip_keeps_unicode_history_saved_roles_and_sequences(server, tmp_path):
    from tracker.platform.windows_checkpoint import create_checkpoint, verify_checkpoint
    from tracker.platform.windows_private import require_private

    checkpoint = create_checkpoint(server, tmp_path / "checkpoint 中文", tmp_path / "verification 中文")
    manifest = json.loads((checkpoint / "checkpoint.json").read_text(encoding="utf-8"))
    assert manifest["verified"] is True
    assert manifest["facts"]["schema_heads"] == ["fixture_revision"]
    assert {item["name"]: item["rows"] for item in manifest["facts"]["tables"]} == {
        "alembic_version": 1, "jobs": 2, "job_observations": 3, "pursuits": 1,
    }
    for path in (checkpoint, checkpoint / "checkpoint.json", checkpoint / "database.dump"):
        require_private(path)
    assert not (tmp_path / "verification 中文" / "db" / "postmaster.pid").exists()
    assert (tmp_path / "verification 中文" / "db" / "PG_VERSION").exists()
    result = verify_checkpoint(checkpoint, tmp_path / "recheck")
    assert result["scratch_write"] == "rolled back"
    restored = ensure_server(tmp_path / "recheck" / "db", database="roleband_restore_check")
    try:
        assert psql(restored, "SELECT title FROM jobs WHERE id=1") == "Éclair 中文"
        assert psql(restored, "SELECT min(observed_on) FROM job_observations") == "2025-01-01"
        assert psql(restored, "SELECT observed_at AT TIME ZONE 'UTC' FROM job_observations ORDER BY observed_on LIMIT 1") == "2025-01-01 10:34:56"
        assert psql(restored, "SELECT stage FROM pursuits WHERE job_id=1") == "saved"
        assert psql(restored, "SELECT nextval('restored_sequence')") == "21"
        assert psql(restored, "SELECT to_regclass('pg_temp.roleband_restore_probe') IS NULL") == "t"
    finally:
        stop_server(restored.pgdata)
    assert psql(server, "SELECT last_value FROM restored_sequence") == "20"


def test_export_and_fingerprint_share_one_snapshot_despite_a_concurrent_commit(server, tmp_path, monkeypatch):
    from tracker.platform.windows_checkpoint import create_checkpoint

    run = subprocess.run

    def concurrent_write(argv, **kwargs):
        if str(argv[0]).endswith("pg_dump.exe"):
            psql(server, "INSERT INTO jobs VALUES (3,'committed after snapshot',null)")
        return run(argv, **kwargs)

    monkeypatch.setattr(subprocess, "run", concurrent_write)
    checkpoint = create_checkpoint(server, tmp_path / "snapshot", tmp_path / "verify")
    manifest = json.loads((checkpoint / "checkpoint.json").read_text())
    assert next(table["rows"] for table in manifest["facts"]["tables"] if table["name"] == "jobs") == 2
    assert psql(server, "SELECT count(*) FROM jobs") == "3"


def test_archive_checksum_failure_refuses_to_create_a_restore_cluster(server, tmp_path):
    from tracker.platform.windows_checkpoint import (
        CheckpointError,
        create_checkpoint,
        verify_checkpoint,
    )

    checkpoint = create_checkpoint(server, tmp_path / "checkpoint", tmp_path / "verify")
    archive = checkpoint / "database.dump"
    archive.write_bytes(archive.read_bytes()[:100])
    with pytest.raises(CheckpointError, match="checksum"):
        verify_checkpoint(checkpoint, tmp_path / "untouched")
    assert not (tmp_path / "untouched").exists()
    assert psql(server, "SELECT count(*) FROM job_observations") == "3"


def test_matching_checksum_does_not_make_a_truncated_archive_restorable(server, tmp_path):
    from tracker.platform.windows_checkpoint import (
        CheckpointError,
        create_checkpoint,
        verify_checkpoint,
    )

    checkpoint = create_checkpoint(server, tmp_path / "checkpoint", tmp_path / "verify")
    archive = checkpoint / "database.dump"
    archive.write_bytes(archive.read_bytes()[:100])
    path = checkpoint / "checkpoint.json"
    manifest = json.loads(path.read_text())
    manifest.update(sha256=hashlib.sha256(archive.read_bytes()).hexdigest(), bytes=archive.stat().st_size)
    path.write_text(json.dumps(manifest))
    with pytest.raises(CheckpointError, match="pg_restore"):
        verify_checkpoint(checkpoint, tmp_path / "damaged-restore")
    assert not (tmp_path / "damaged-restore" / "db" / "postmaster.pid").exists()
    assert psql(server, "SELECT title FROM jobs WHERE id=1") == "Éclair 中文"


def test_failed_creation_preserves_prior_checkpoint_and_never_publishes_a_manifest(server, tmp_path, monkeypatch):
    from tracker.platform.windows_checkpoint import CheckpointError, create_checkpoint

    prior = create_checkpoint(server, tmp_path / "prior", tmp_path / "first-verify")
    original = (prior / "database.dump").read_bytes()
    run = subprocess.run

    def damage_dump(argv, **kwargs):
        result = run(argv, **kwargs)
        if str(argv[0]).endswith("pg_dump.exe"):
            Path(argv[argv.index("--file") + 1]).write_bytes(b"damaged dump")
        return result

    monkeypatch.setattr(subprocess, "run", damage_dump)
    with pytest.raises(CheckpointError, match="pg_restore"):
        create_checkpoint(server, tmp_path / "failed", tmp_path / "failed-verify")
    assert not (tmp_path / "failed").exists()
    assert not list(tmp_path.glob("failed.partial-*/checkpoint.json"))
    assert list(tmp_path.glob("failed.partial-*/database.dump"))
    assert (prior / "database.dump").read_bytes() == original
    assert not (tmp_path / "failed-verify" / "db" / "postmaster.pid").exists()


def test_fresh_restore_storage_is_required_and_source_cannot_be_reused(server, tmp_path):
    from tracker.platform.windows_checkpoint import (
        CheckpointError,
        create_checkpoint,
        verify_checkpoint,
    )

    checkpoint = create_checkpoint(server, tmp_path / "checkpoint", tmp_path / "verify")
    with pytest.raises(FileExistsError):
        verify_checkpoint(checkpoint, tmp_path / "verify")
    with pytest.raises(CheckpointError, match="separate"):
        verify_checkpoint(checkpoint, server.pgdata.parent)
    with pytest.raises(CheckpointError, match="separate"):
        create_checkpoint(server, server.pgdata / "backup", tmp_path / "verify2")
    assert psql(server, "SELECT count(*) FROM jobs") == "2"


def test_restored_rows_must_match_even_when_the_archive_is_valid(server, tmp_path):
    from tracker.platform.windows_checkpoint import (
        CheckpointError,
        create_checkpoint,
        verify_checkpoint,
    )

    checkpoint = create_checkpoint(server, tmp_path / "checkpoint", tmp_path / "verify")
    path = checkpoint / "checkpoint.json"
    manifest = json.loads(path.read_text())
    manifest["facts"]["tables"][0]["data_sha256"] = "0" * 64
    path.write_text(json.dumps(manifest))
    with pytest.raises(CheckpointError, match="fingerprints"):
        verify_checkpoint(checkpoint, tmp_path / "mismatch")
    assert not (tmp_path / "mismatch" / "db" / "postmaster.pid").exists()


def test_a_database_made_by_an_older_runtime_keeps_checkpointing(server, tmp_path):
    """A database keeps the pgvector version it was made with; a restore gets the runtime's."""
    from tracker.platform.windows_checkpoint import (
        create_checkpoint,
        still_matches,
        verify_checkpoint,
    )

    default = psql(server, "SELECT default_version FROM pg_available_extensions WHERE name='vector'")
    assert default != "0.8.5"
    psql(server, "CREATE EXTENSION vector; UPDATE pg_extension SET extversion='0.8.5' WHERE extname='vector'")
    checkpoint = create_checkpoint(server, tmp_path / "checkpoint", tmp_path / "verify")
    manifest = json.loads((checkpoint / "checkpoint.json").read_text(encoding="utf-8"))
    assert ["vector", "0.8.5"] in manifest["facts"]["extensions"]
    assert verify_checkpoint(checkpoint, tmp_path / "recheck")["verified"] is True
    restored = ensure_server(tmp_path / "recheck" / "db", database="roleband_restore_check")
    try:
        assert psql(restored, "SELECT extversion FROM pg_extension WHERE extname='vector'") == default
    finally:
        stop_server(restored.pgdata)
    assert still_matches(server, checkpoint)


def test_a_manifest_naming_an_older_extension_version_still_restores(server, tmp_path):
    from tracker.platform.windows_checkpoint import create_checkpoint, verify_checkpoint

    psql(server, "CREATE EXTENSION vector")
    checkpoint = create_checkpoint(server, tmp_path / "checkpoint", tmp_path / "verify")
    path = checkpoint / "checkpoint.json"
    manifest = json.loads(path.read_text())
    manifest["facts"]["extensions"] = [[name, "0.8.5" if name == "vector" else version]
                                       for name, version in manifest["facts"]["extensions"]]
    path.write_text(json.dumps(manifest))
    assert verify_checkpoint(checkpoint, tmp_path / "recheck")["verified"] is True


def test_a_recorded_extension_the_restore_lacks_is_refused(server, tmp_path):
    from tracker.platform.windows_checkpoint import (
        CheckpointError,
        create_checkpoint,
        verify_checkpoint,
    )

    checkpoint = create_checkpoint(server, tmp_path / "checkpoint", tmp_path / "verify")
    path = checkpoint / "checkpoint.json"
    manifest = json.loads(path.read_text())
    assert "pg_trgm" not in [name for name, _version in manifest["facts"]["extensions"]]
    manifest["facts"]["extensions"] = sorted([*manifest["facts"]["extensions"], ["pg_trgm", "1.6"]])
    path.write_text(json.dumps(manifest))
    with pytest.raises(CheckpointError, match="fingerprints"):
        verify_checkpoint(checkpoint, tmp_path / "mismatch")


def test_empty_jobs_and_unsupported_manifest_do_not_establish_recovery(server, tmp_path):
    from tracker.platform.windows_checkpoint import (
        CheckpointError,
        create_checkpoint,
        verify_checkpoint,
    )

    checkpoint = create_checkpoint(server, tmp_path / "checkpoint", tmp_path / "verify")
    path = checkpoint / "checkpoint.json"
    manifest = json.loads(path.read_text())
    manifest["format"] = 2
    path.write_text(json.dumps(manifest))
    with pytest.raises(CheckpointError, match="Unsupported"):
        verify_checkpoint(checkpoint, tmp_path / "unsupported")
    assert not (tmp_path / "unsupported").exists()
    psql(server, "DELETE FROM pursuits; DELETE FROM job_observations; DELETE FROM jobs")
    with pytest.raises(CheckpointError, match="empty jobs"):
        create_checkpoint(server, tmp_path / "empty", tmp_path / "empty-verify")
    assert not (tmp_path / "empty").exists()


def test_sequence_changes_during_dump_prevent_publication(server, tmp_path, monkeypatch):
    from tracker.platform.windows_checkpoint import CheckpointError, create_checkpoint

    run = subprocess.run

    def concurrent_sequence(argv, **kwargs):
        if str(argv[0]).endswith("pg_dump.exe"):
            psql(server, "SELECT nextval('restored_sequence')")
        return run(argv, **kwargs)

    monkeypatch.setattr(subprocess, "run", concurrent_sequence)
    with pytest.raises(CheckpointError, match="Sequences changed"):
        create_checkpoint(server, tmp_path / "sequence-race", tmp_path / "unneeded-verify")
    assert not (tmp_path / "sequence-race").exists()
    assert not (tmp_path / "unneeded-verify").exists()


def _cli(*arguments):
    desktop = Path(__file__).resolve().parents[1] / "desktop.py"
    return subprocess.run([sys.executable, "-I", "-B", str(desktop), "--source", "checkpoint", *map(str, arguments)],
                          capture_output=True, text=True, encoding="utf-8", timeout=120)


def test_cli_uses_an_existing_stopped_app_cluster_and_preserves_its_history(server, tmp_path):
    stop_server(server.pgdata)
    result = _cli("create", "--pgdata", server.pgdata, "--database", "probe",
                  "--destination", tmp_path / "cli-checkpoint", "--verification-state", tmp_path / "cli-verify")
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)["verified"] is True
    assert not (server.pgdata / "postmaster.pid").exists()
    assert not (tmp_path / "cli-verify" / "db" / "postmaster.pid").exists()
    recheck = _cli("verify", "--checkpoint", tmp_path / "cli-checkpoint", "--verification-state", tmp_path / "cli-recheck")
    assert recheck.returncode == 0, recheck.stderr
    assert json.loads(recheck.stdout)["scratch_write"] == "rolled back"
    assert not (tmp_path / "cli-recheck" / "db" / "postmaster.pid").exists()
    resumed = ensure_server(server.pgdata, database="probe")
    assert psql(resumed, "SELECT stage FROM pursuits WHERE job_id=1") == "saved"


@pytest.mark.parametrize("name", ["desktop.lock", "engine.lock"])
def test_cli_refuses_a_live_lease_before_starting_postgres(server, tmp_path, name):
    from tracker.platform import filelock
    from tracker.platform.windows_private import private_directory

    stop_server(server.pgdata)
    launcher = server.pgdata.parent / "launcher"
    private_directory(launcher)
    with (launcher / name).open("a+b") as lease:
        filelock.lock(lease, blocking=False)
        result = _cli("create", "--pgdata", server.pgdata, "--database", "probe",
                      "--destination", tmp_path / "blocked", "--verification-state", tmp_path / "verify")
    assert result.returncode != 0
    assert not (server.pgdata / "postmaster.pid").exists()
    assert not (tmp_path / "blocked").exists()
    assert not (tmp_path / "verify").exists()


def test_cli_never_creates_a_misspelled_source_database(server, tmp_path):
    stop_server(server.pgdata)
    result = _cli("create", "--pgdata", server.pgdata, "--database", "misspelled_source",
                  "--destination", tmp_path / "absent", "--verification-state", tmp_path / "verify")
    assert result.returncode != 0
    assert "must already exist" in result.stderr
    assert not (server.pgdata / "postmaster.pid").exists()
    resumed = ensure_server(server.pgdata, database="probe")
    assert psql(resumed, "SELECT count(*) FROM pg_database WHERE datname='misspelled_source'") == "0"
    assert psql(resumed, "SELECT count(*) FROM job_observations") == "3"


def test_foreign_database_identity_is_refused_before_restore(server, tmp_path):
    from tracker.platform.windows_checkpoint import CheckpointError, create_checkpoint

    foreign = replace(server, database="a_different_database")
    with pytest.raises(CheckpointError, match="expected PG16 database"):
        create_checkpoint(foreign, tmp_path / "foreign", tmp_path / "verification")
    assert not (tmp_path / "foreign").exists()
    assert not (tmp_path / "verification").exists()
    assert psql(server, "SELECT count(*) FROM jobs") == "2"


def test_a_publicly_readable_archive_is_refused_before_creating_scratch_storage(server, tmp_path):
    from tracker.platform.windows_checkpoint import create_checkpoint, verify_checkpoint
    from tracker.platform.windows_private import PrivatePathError

    checkpoint = create_checkpoint(server, tmp_path / "checkpoint", tmp_path / "verify")
    archive = checkpoint / "database.dump"
    subprocess.run(["icacls", str(archive), "/grant", "*S-1-1-0:(R)"], check=True, capture_output=True)
    try:
        with pytest.raises(PrivatePathError, match="another account"):
            verify_checkpoint(checkpoint, tmp_path / "blocked")
        assert not (tmp_path / "blocked").exists()
    finally:
        subprocess.run(["icacls", str(archive), "/remove:g", "*S-1-1-0"], check=True, capture_output=True)


def test_a_junction_cannot_redirect_verification_into_source_storage(server, tmp_path):
    from tracker.platform.windows_checkpoint import create_checkpoint, verify_checkpoint
    from tracker.platform.windows_fs import ReparsePointError

    checkpoint = create_checkpoint(server, tmp_path / "checkpoint", tmp_path / "verify")
    junction = tmp_path / "redirected"
    subprocess.run(["cmd", "/c", "mklink", "/J", str(junction), str(server.pgdata.parent)],
                   check=True, capture_output=True)
    try:
        with pytest.raises(ReparsePointError):
            verify_checkpoint(checkpoint, junction / "nested-verification")
        assert not (server.pgdata.parent / "nested-verification").exists()
        assert psql(server, "SELECT count(*) FROM job_observations") == "3"
    finally:
        os.rmdir(junction)


def test_a_changed_check_rule_cannot_pass_as_a_cast_normalization(server, tmp_path, monkeypatch):
    import psycopg2

    from tracker.platform.windows_checkpoint import CheckpointError, create_checkpoint

    run = subprocess.run

    def change_restored_constraint(argv, **kwargs):
        result = run(argv, **kwargs)
        if str(argv[0]).endswith("pg_restore.exe") and result.returncode == 0:
            dsn = argv[argv.index("-d") + 1]
            with psycopg2.connect(dsn) as conn, conn.cursor() as cur:
                cur.execute("SELECT current_database()")
                assert cur.fetchone() == ("roleband_restore_check",)
                cur.execute("ALTER TABLE jobs DROP CONSTRAINT ck_state;"
                            "ALTER TABLE jobs ADD CONSTRAINT ck_state CHECK (state IN ('starting','a_different_rule'))")
        return result

    monkeypatch.setattr(subprocess, "run", change_restored_constraint)
    with pytest.raises(CheckpointError, match="fingerprints"):
        create_checkpoint(server, tmp_path / "changed-constraint", tmp_path / "verification")
    assert not (tmp_path / "changed-constraint").exists()
    assert psql(server, "SELECT count(*) FROM jobs") == "2"


def test_partitioned_history_and_materialized_summaries_restore_without_double_counting(server, tmp_path):
    from tracker.platform.windows_checkpoint import create_checkpoint

    psql(server, "CREATE TABLE partitioned_history(value integer, observed_on date) PARTITION BY RANGE(observed_on);"
         "CREATE TABLE partitioned_history_2025 PARTITION OF partitioned_history"
         " FOR VALUES FROM ('2025-01-01') TO ('2026-01-01');"
         "INSERT INTO partitioned_history VALUES (1,'2025-01-01'),(2,'2025-12-31');"
         "CREATE MATERIALIZED VIEW history_summary AS SELECT count(*) AS total FROM partitioned_history")
    checkpoint = create_checkpoint(server, tmp_path / "partitioned", tmp_path / "verification")
    manifest = json.loads((checkpoint / "checkpoint.json").read_text())
    tables = {table["name"]: table for table in manifest["facts"]["tables"]}
    assert tables["partitioned_history"]["rows"] == 0
    assert tables["partitioned_history_2025"]["rows"] == 2
    assert tables["history_summary"]["rows"] == 1

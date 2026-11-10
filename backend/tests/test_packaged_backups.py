"""Packaged backups protect existing archives before publishing and pruning."""

from __future__ import annotations

import subprocess
import sys
from datetime import datetime
from pathlib import Path

import pytest

from tests.embedded_utils import cluster_locale, destroy, psql
from tracker.platform.embedded_db import ensure_server


def _folder(path: Path) -> Path:
    """A backup folder as a person's machine has it: private to the account, as the backup itself requires."""
    if sys.platform == "win32":
        from tracker.platform.windows_private import private_directory

        path.parent.mkdir(parents=True, exist_ok=True)
        private_directory(path)
    else:
        path.mkdir(parents=True)
    return path


def _assert_private(path: Path, mode: int) -> None:
    if sys.platform == "win32":
        from tracker.platform.windows_private import require_private

        require_private(path)
    else:
        assert path.stat().st_mode & 0o777 == mode, path


@pytest.fixture
def server(tmp_path):
    server = ensure_server(tmp_path / "db", database="probe", locale=cluster_locale())
    psql(server, "CREATE TABLE jobs (id integer, title text); INSERT INTO jobs VALUES (1, 'kept posting')")
    try:
        yield server
    finally:
        destroy(server.pgdata)


def test_backup_verifies_publishes_monthly_and_prunes_only_daily(server, tmp_path):
    from tracker.platform.backups import dump_database

    out = _folder(tmp_path / "user home" / ".roleband" / "backups")
    for day in range(1, 16):
        (out / f"roleband_202601{day:02d}_063000.dump").write_bytes(b"prior backup")
    archive = dump_database(server, out, now=datetime(2026, 2, 1, 6, 30))
    assert archive.is_file()
    restored = subprocess.run(
        [str(server.tool("pg_restore")), "--file=-", str(archive)], check=True, capture_output=True, text=True,
    ).stdout
    assert "kept posting" in restored
    assert len(list(out.glob("*.dump"))) == 14
    assert not (out / "roleband_20260101_063000.dump").exists()
    assert (out / "monthly" / archive.name).read_bytes() == archive.read_bytes()
    _assert_private(archive, 0o600)
    _assert_private(out, 0o700)
    _assert_private(out / "monthly", 0o700)
    for dump in out.rglob("*.dump"):
        _assert_private(dump, 0o600)


@pytest.mark.parametrize("failed_tool", ["pg_dump", "pg_restore"])
def test_failed_dump_or_verification_keeps_prior_archives(server, tmp_path, monkeypatch, failed_tool):
    from tracker.platform import backups

    out = _folder(tmp_path / "backups")
    prior = out / "roleband_20260101_063000.dump"
    prior.write_bytes(b"prior good backup")
    run = subprocess.run

    def fail(argv, **kwargs):
        if argv[0] == str(server.tool(failed_tool)):
            return subprocess.CompletedProcess(argv, 1, "", "broken tool")
        return run(argv, **kwargs)

    monkeypatch.setattr(backups.subprocess, "run", fail)
    with pytest.raises(backups.BackupError, match=failed_tool):
        backups.dump_database(server, out)
    assert list(out.rglob("*.dump")) == [prior]
    assert prior.read_bytes() == b"prior good backup"
    assert not list(out.glob("*.partial"))


def test_empty_database_cannot_supersede_a_prior_monthly_backup(server, tmp_path):
    from tracker.platform.backups import BackupError, dump_database

    psql(server, "DELETE FROM jobs")
    out = _folder(tmp_path / "backups")
    monthly = _folder(out / "monthly")
    prior = monthly / "roleband_20260101_063000.dump"
    prior.write_bytes(b"only surviving archive")
    with pytest.raises(BackupError, match="empty"):
        dump_database(server, out)
    assert list(out.rglob("*.dump")) == [prior]

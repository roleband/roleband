"""A source run never starts the Mac app's database.

The app writes `db.owner.json` beside the cluster it makes. A checkout's command
or test run that resolves the same folder (no `ROLEBAND_PGDATA`, so the default
`~/.roleband/db`) and starts it with the checkout's Postgres leaves a server the
app reads as a source install's, and the app then starts no engine of its own.
Every case here points the default at a scratch state folder with
`ROLEBAND_STATE_DIR`, so nothing reaches the real one.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from tests.embedded_utils import stop_clusters_under
from tracker import config
from tracker.platform import embedded_db

pytestmark = pytest.mark.skipif(sys.platform == "win32", reason="macOS and POSIX tooling runs on the Mac")

BACKEND = Path(__file__).resolve().parents[1]


@pytest.fixture
def default_state(monkeypatch, tmp_path):
    """The default database folder, moved to a scratch state, with nothing naming another."""
    state = tmp_path / "state"
    state.mkdir()
    monkeypatch.setenv("ROLEBAND_STATE_DIR", str(state))
    monkeypatch.delenv("ROLEBAND_PGDATA", raising=False)
    monkeypatch.delenv("ROLEBAND_DATABASE_URL", raising=False)
    return state


@pytest.fixture
def started(monkeypatch):
    calls: list[Path] = []
    monkeypatch.setattr(embedded_db, "ensure_server", lambda pgdata, **_: calls.append(pgdata) or "server")
    return calls


def _source_settings() -> config.Settings:
    return config.Settings(_env_file=None)


@pytest.mark.parametrize("record", [json.dumps({"owner": "app"}), "not json", "[]"])
def test_a_source_run_refuses_the_default_database_the_app_recorded(default_state, started, record):
    (default_state / "db.owner.json").write_text(record)
    settings = _source_settings()
    assert settings.embedded_pgdata() == default_state / "db"

    with pytest.raises(embedded_db.ClusterOwnedElsewhere) as refused:
        settings.database_url  # noqa: B018 - resolving the URL is what starts the server

    assert "ROLEBAND_PGDATA" in str(refused.value)
    assert str(default_state / "db") in str(refused.value)
    assert started == []
    assert not (default_state / "db").exists()


def test_a_named_folder_the_app_recorded_is_refused_too(tmp_path, monkeypatch, started):
    pgdata = tmp_path / "elsewhere" / "db"
    pgdata.mkdir(parents=True)
    (pgdata / "PG_VERSION").write_text("16\n")
    embedded_db.owner_record(pgdata).write_text(json.dumps({"owner": "app"}))
    monkeypatch.setenv("ROLEBAND_PGDATA", str(pgdata))
    monkeypatch.delenv("ROLEBAND_DATABASE_URL", raising=False)

    with pytest.raises(embedded_db.ClusterOwnedElsewhere):
        _source_settings().ensure_embedded_server()
    assert started == []


def test_a_link_to_a_cluster_the_app_recorded_is_refused(tmp_path, monkeypatch, started):
    app = tmp_path / "app-state" / "db"
    app.mkdir(parents=True)
    embedded_db.owner_record(app).write_text(json.dumps({"owner": "app"}))
    link = tmp_path / "mine" / "db"
    link.parent.mkdir()
    link.symlink_to(app, target_is_directory=True)
    monkeypatch.setenv("ROLEBAND_PGDATA", str(link))
    monkeypatch.delenv("ROLEBAND_DATABASE_URL", raising=False)

    with pytest.raises(embedded_db.ClusterOwnedElsewhere):
        _source_settings().ensure_embedded_server()
    assert started == []


def test_a_source_run_still_opens_a_cluster_with_no_record(default_state, started):
    """Negative control: a source install's own cluster carries no record and opens."""
    pgdata = default_state / "db"
    pgdata.mkdir()
    (pgdata / "PG_VERSION").write_text("16\n")

    assert _source_settings().ensure_embedded_server() == "server"
    assert started == [pgdata]
    assert not embedded_db.owner_record(pgdata).exists()


PROBE = '''
import pytest


@pytest.mark.asyncio
async def test_needs_a_database(db_session):
    pass
'''


def test_the_suite_fails_by_name_instead_of_starting_the_apps_database(tmp_path):
    """The test harness resolves its server from the settings. With the default
    folder recorded as the app's, a test that needs a database fails and says what
    to set; no cluster is made or started there."""
    state = tmp_path / "state"
    state.mkdir()
    (state / "db.owner.json").write_text(json.dumps({"owner": "app"}))
    probe = tmp_path / "test_probe.py"
    probe.write_text(PROBE)
    env = {name: value for name, value in os.environ.items()
           if not name.startswith("PYTEST_") and name != "ROLEBAND_REQUIRE_INTEGRATION"}
    # Empty values outrank backend/.env, which may name the developer's own cluster.
    env.update(ROLEBAND_STATE_DIR=str(state), ROLEBAND_PGDATA="", ROLEBAND_DATABASE_URL="",
               ROLEBAND_CACHE_DIR=str(tmp_path / "cache"))
    try:
        run = subprocess.run(
            [sys.executable, "-m", "pytest", "-c", str(BACKEND / "pytest.ini"), "--rootdir", str(BACKEND),
             "-p", "tests.conftest", "-n", "0", "-p", "no:cacheprovider", "-q", str(probe)],
            cwd=BACKEND, env={**env, "PYTHONPATH": str(BACKEND)}, capture_output=True, text=True, timeout=300,
        )
    finally:
        stop_clusters_under(state)
    output = run.stdout + run.stderr
    assert run.returncode == 1, output[-3000:]
    assert "1 error" in output, output[-3000:]
    assert "does not open the installed app's database" in output, output[-3000:]
    assert "ROLEBAND_PGDATA" in output, output[-3000:]
    assert not (state / "db").exists(), "the run made a cluster in the app's folder"

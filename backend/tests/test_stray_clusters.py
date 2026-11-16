"""Throwaway clusters stop once nothing holds them, and nothing else is stopped.

A cluster outlives every process that opens it, and each running one holds one
of the machine's few shared memory segments. `scripts.stray_clusters` finds the
ones whose holders have all gone; a test run stops the one it used
(`pytest_unconfigure` in `conftest.py`). Both must leave alone a cluster still
held, a development database that merely idles, and an app's.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from scripts import stray_clusters
from scripts.stray_clusters import (
    HOLDERS,
    RunningCluster,
    _why_kept,
    live_holders,
    running_clusters,
    running_postmaster,
    stop_after_run,
    stop_unheld,
)

#: A PID no process has: above every platform's PID ceiling.
GONE = 2**30


def _cluster(path: Path, holders: list[int] | None) -> Path:
    path.mkdir(parents=True)
    if holders is not None:
        (path / HOLDERS).write_text(json.dumps(holders))
    return path


def test_live_holders_drop_exited_and_ignored_processes(tmp_path):
    pgdata = _cluster(tmp_path / "db", [os.getpid(), GONE])

    assert live_holders(pgdata) == (os.getpid(),)
    assert live_holders(pgdata, ignore=frozenset({os.getpid()})) == ()
    assert live_holders(_cluster(tmp_path / "unrecorded", None)) is None


def test_only_a_recorded_unclaimed_throwaway_cluster_is_a_stray(tmp_path, monkeypatch):
    monkeypatch.setattr(stray_clusters, "throwaway_places", lambda: (tmp_path / "scratch",))
    stray = _cluster(tmp_path / "scratch" / "db", [GONE])
    claimed = _cluster(tmp_path / "scratch" / "app", [GONE])
    (tmp_path / "scratch" / "app.owner.json").write_text('{"owner": "app"}\n')
    development = _cluster(tmp_path / "checkout" / "db", [GONE])
    unrecorded = _cluster(tmp_path / "scratch" / "pg_ctl", None)

    def state(pgdata: Path) -> str:
        holders = live_holders(pgdata)
        return RunningCluster(pgdata, 1, holders, _why_kept(pgdata, holders)).state

    assert state(stray) == "stray"
    assert state(claimed) == "kept"
    assert state(development) == "kept"
    assert state(unrecorded) == "kept"
    (stray / HOLDERS).write_text(json.dumps([os.getpid()]))
    assert state(stray) == "held"


def test_a_run_stops_a_throwaway_cluster_and_leaves_a_development_database(tmp_path, monkeypatch):
    """Only a cluster in a throwaway place is the run's to stop. A development
    database idles with no holder by design, whoever started it."""
    monkeypatch.setattr(stray_clusters, "throwaway_places", lambda: (tmp_path / "scratch",))
    monkeypatch.setattr(stray_clusters, "running_postmaster", lambda _pgdata: True)
    stopped: list[Path] = []
    monkeypatch.setattr(stray_clusters, "stop_unheld", lambda pgdata, **_: stopped.append(pgdata) or True)
    throwaway = _cluster(tmp_path / "scratch" / "db", [GONE])
    development = _cluster(tmp_path / "checkout" / "db", [GONE])

    assert stop_after_run(development) is False
    assert stop_after_run(throwaway) is True
    assert stopped == [throwaway.resolve()]


def test_a_stale_lock_file_naming_another_process_is_never_signalled(tmp_path, monkeypatch):
    """A crashed server leaves `postmaster.pid` behind, and its PID may since be
    another process's: here this test's own. Nothing is stopped and `pg_ctl`,
    which would signal that PID, never runs."""
    pytest.importorskip("pixeltable_pgserver", reason="embedded Postgres wheel not installed")
    pgdata = _cluster(tmp_path / "db", [GONE])
    (pgdata / "postmaster.pid").write_text(f"{os.getpid()}\n{pgdata}\n")
    (pgdata / "PG_VERSION").write_text("16\n")
    monkeypatch.setattr(stray_clusters.subprocess, "run", lambda *_a, **_k: pytest.fail("pg_ctl was run"))

    assert running_postmaster(pgdata) is False
    assert stop_unheld(pgdata) is False


def test_a_run_never_stops_an_apps_cluster(tmp_path, monkeypatch):
    monkeypatch.setattr(stray_clusters, "throwaway_places", lambda: (tmp_path,))
    monkeypatch.setattr(stray_clusters, "running_postmaster", lambda _pgdata: True)
    monkeypatch.setattr(stray_clusters, "stop_unheld", lambda *_a, **_k: pytest.fail("stopped an app's cluster"))
    claimed = _cluster(tmp_path / "db", [GONE])
    (tmp_path / "db.owner.json").write_text('{"owner": "app"}\n')

    assert stop_after_run(claimed) is False


@pytest.mark.skipif(os.name == "nt", reason="the holder record is POSIX's; Windows' runner stops its own clusters")
def test_a_real_cluster_stops_only_once_no_holder_but_the_ignored_remains(tmp_path_factory):
    pytest.importorskip("pixeltable_pgserver", reason="embedded Postgres wheel not installed")
    from tests.embedded_utils import cluster_locale, destroy
    from tracker.platform.embedded_db import ensure_server

    pgdata = (tmp_path_factory.mktemp("pg") / "db").resolve()
    ensure_server(pgdata, database="probe", locale=cluster_locale())
    try:
        listed = {cluster.pgdata: cluster for cluster in running_clusters()}
        assert listed[pgdata].state == "held"
        assert os.getpid() in (listed[pgdata].holders or ())

        assert stop_unheld(pgdata) is False, "this process holds it"
        assert pgdata in {cluster.pgdata for cluster in running_clusters()}

        record = (pgdata / HOLDERS).read_text()
        (pgdata / HOLDERS).unlink()
        assert stop_unheld(pgdata, ignore=frozenset({os.getpid()})) is False, "no record, owner unknown"
        (pgdata / HOLDERS).write_text(record)

        assert stop_unheld(pgdata, ignore=frozenset({os.getpid()})) is True
        assert pgdata not in {cluster.pgdata for cluster in running_clusters()}
        assert stop_unheld(pgdata) is False, "nothing left to stop"

        # The handle this process cached is retired: opening it again starts it.
        ensure_server(pgdata, database="probe", locale=cluster_locale())
        assert pgdata in {cluster.pgdata for cluster in running_clusters()}
    finally:
        destroy(pgdata)

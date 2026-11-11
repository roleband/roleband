"""Watchdog alert de-duplication + backup-freshness detection."""

from __future__ import annotations

import os
import re
import sys
from datetime import UTC, datetime, timedelta

import pytest

from tracker.health import freshness, stale_derivations
from tracker.workflows import watchdog


def test_stale_derivations_reads_the_status_payload():
    # Populated when a producing pass is stale; empty/absent when clean.
    assert stale_derivations({"derivations_stale": ["similarity", "skill_demand"]}) == [
        "similarity",
        "skill_demand",
    ]
    assert stale_derivations({"derivations_stale": []}) == []
    assert stale_derivations({}) == []  # older API payloads lack the key


def test_derivations_stale_alert_has_a_message():
    # dispatch_alerts KeyErrors on a firing key with no ALERT_KEYS entry,
    # so a new firing condition must ship its human text in the same change.
    assert watchdog.ALERT_KEYS["derivations_stale"] == "banner-derivations-stale"
    assert watchdog.banner("banner-derivations-stale")


# Health banners reach the desktop when something breaks, read by someone who
# never needs to know how RoleBand is built (docs/copy.md, rule 6).
_INTERNAL_PARTS = re.compile(
    r"\b(api|scheduler|derived|derivations?|statistics|stale|health check|pass|unreachable)\b",
    re.IGNORECASE,
)


@pytest.mark.parametrize("key", ["db_down", "api_down", "stale_data", "derivations_stale"])
def test_health_banners_name_no_internal_parts(key):
    text = watchdog.banner(watchdog.ALERT_KEYS[key])
    assert text and _INTERNAL_PARTS.search(text) is None, text


@pytest.mark.parametrize("key", ["db_down", "api_down"])
def test_recovery_banners_name_the_app(key):
    # Outside the app's window the reader may not know which app is talking.
    assert "RoleBand" in watchdog.banner(watchdog.ALERT_KEYS[key])


def test_derivations_stale_notifies_only_when_newly_firing(monkeypatch):
    notified: list[str] = []
    monkeypatch.setattr(watchdog, "notify", lambda title, msg: notified.append(msg))
    monkeypatch.setattr(watchdog, "_append_alert", lambda *a, **k: None)

    # Newly stale this tick -> one notification.
    assert watchdog.dispatch_alerts({}, {"derivations_stale": True}) == ["derivations_stale"]
    assert notified == [watchdog.banner("banner-derivations-stale")]
    # Still stale next tick -> suppressed (edge-triggered).
    notified.clear()
    assert watchdog.dispatch_alerts({"derivations_stale": True}, {"derivations_stale": True}) == []
    assert notified == []


def _dump(dir_path, name: str, *, age_hours: float):
    """Write a dump file whose mtime is ``age_hours`` in the past."""
    path = dir_path / name
    path.write_bytes(b"PGDMP")
    stamp = (datetime.now(UTC) - timedelta(hours=age_hours)).timestamp()
    os.utime(path, (stamp, stamp))
    return path


def test_only_newly_firing_conditions_notify(monkeypatch):
    notified: list[str] = []
    logged: list[str] = []
    monkeypatch.setattr(watchdog, "notify", lambda title, msg: notified.append(msg))
    monkeypatch.setattr(watchdog, "_append_alert", logged.append)

    prev = {"api_down": True}  # already firing last tick -> suppressed
    firing = {"api_down": True, "db_down": True}  # db_down is new this tick

    dispatched = watchdog.dispatch_alerts(prev, firing)

    assert dispatched == ["db_down"]
    assert len(notified) == 1
    assert notified == [watchdog.banner("banner-db-down")]
    assert logged == notified  # same message reaches the alerts log


def test_persisting_condition_does_not_renotify(monkeypatch):
    calls: list[str] = []
    monkeypatch.setattr(watchdog, "notify", lambda *a, **k: calls.append("notify"))
    monkeypatch.setattr(watchdog, "_append_alert", lambda *a, **k: calls.append("log"))

    assert watchdog.dispatch_alerts({"api_down": True}, {"api_down": True}) == []
    assert calls == []


def test_recovered_condition_is_not_dispatched(monkeypatch):
    monkeypatch.setattr(watchdog, "notify", lambda *a, **k: None)
    monkeypatch.setattr(watchdog, "_append_alert", lambda *a, **k: None)

    # Was firing, now false -> nothing to dispatch (no false "recovered" alert).
    assert watchdog.dispatch_alerts({"db_down": True}, {"db_down": False}) == []


def test_no_backups_reads_as_no_backup_time(tmp_path):
    # The data-loss state: the directory exists and is empty. This must
    # not read as "fine", which is what an mtime-of-the-directory check would do.
    assert watchdog.newest_backup_at(tmp_path) is None


def test_missing_backup_directory_reads_as_no_backup_time(tmp_path):
    assert watchdog.newest_backup_at(tmp_path / "never_created") is None


def test_newest_backup_wins_over_older_ones(tmp_path):
    _dump(tmp_path, "roleband_20260701_000000.dump", age_hours=500)
    _dump(tmp_path, "roleband_20260723_000000.dump", age_hours=3)
    _dump(tmp_path, "roleband_20260710_000000.dump", age_hours=200)

    found = watchdog.newest_backup_at(tmp_path)

    assert found is not None
    age_hours = (datetime.now(UTC) - found).total_seconds() / 3600
    assert 2.5 < age_hours < 3.5  # picked the 3h-old dump, not the first or last listed


def test_unrelated_files_do_not_count_as_backups(tmp_path):
    # A stale log sitting next to the dumps must not mask a missing backup.
    (tmp_path / "backup.log").write_text("backup_db: wrote ...")
    (tmp_path / "roleband_20260723.dump.partial").write_bytes(b"trunc")

    assert watchdog.newest_backup_at(tmp_path) is None


def test_backup_older_than_threshold_is_stale(tmp_path):
    _dump(tmp_path, "roleband_20260721_063000.dump", age_hours=40)

    _, stale = freshness(watchdog.newest_backup_at(tmp_path), datetime.now(UTC), 36)

    assert stale is True


def test_last_nights_backup_is_not_stale(tmp_path):
    _dump(tmp_path, "roleband_20260723_063000.dump", age_hours=10)

    _, stale = freshness(watchdog.newest_backup_at(tmp_path), datetime.now(UTC), 36)

    assert stale is False


class TestDatabaseRecovery:
    """The DB-down branch starts the embedded server itself.

    This branch is the only thing standing between a stopped database and a
    night of missed work.
    """

    def test_starts_the_embedded_server_and_reports_success(self, monkeypatch):
        started: list[bool] = []

        class _Settings:
            database_url_override = None
            db_embedded = True

            def ensure_embedded_server(self):
                started.append(True)
                return object()

        monkeypatch.setattr(watchdog, "get_settings", _Settings)
        assert watchdog.recover_db() is None
        assert started == [True]

    def test_startup_failure_is_reported_not_raised(self, monkeypatch, tmp_path):
        # The pass must continue to the remaining checks (API health, stuck
        # runs, backups); a database that will not start is an alert, not a
        # crash that skips everything after it.
        from tracker.platform.embedded_db import EmbeddedDbError

        class _Settings:
            database_url_override = None
            db_embedded = True

            def embedded_pgdata(self):
                return tmp_path / "db"

            def ensure_embedded_server(self):
                raise EmbeddedDbError("could not start: FATAL could not create lock file")

        monkeypatch.setattr(watchdog, "get_settings", _Settings)
        monkeypatch.setattr(watchdog, "stop_server", lambda pgdata: False)
        failure = watchdog.recover_db()
        assert failure is not None
        assert "could not create lock file" in failure  # server log tail reaches the operator

    def test_a_broken_running_server_is_restarted_not_reattached(self, monkeypatch, tmp_path):
        # A postmaster running from a deleted worktree venv attaches but cannot
        # load extensions, and only a restart from an intact install tree heals
        # it. The recovery must escalate.
        from tracker.platform.embedded_db import EmbeddedDbError

        ensures: list[int] = []
        stops: list[object] = []

        class _Settings:
            database_url_override = None
            db_embedded = True

            def embedded_pgdata(self):
                return tmp_path / "db"

            def ensure_embedded_server(self):
                ensures.append(1)
                if len(ensures) == 1:
                    raise EmbeddedDbError("missing required extension(s): vector, pg_trgm")
                return object()

        monkeypatch.setattr(watchdog, "get_settings", _Settings)
        monkeypatch.setattr(watchdog, "stop_server", lambda pgdata: stops.append(pgdata) or True)

        assert watchdog.recover_db() is None  # healed, not merely reported
        assert len(ensures) == 2  # attach failed -> restarted -> ensured again
        assert stops == [tmp_path / "db"]  # the broken server was actually bounced

    def test_a_restart_that_also_fails_reports_both_errors(self, monkeypatch, tmp_path):
        from tracker.platform.embedded_db import EmbeddedDbError

        class _Settings:
            database_url_override = None
            db_embedded = True

            def embedded_pgdata(self):
                return tmp_path / "db"

            def ensure_embedded_server(self):
                raise EmbeddedDbError("missing required extension(s): vector")

        monkeypatch.setattr(watchdog, "get_settings", _Settings)
        monkeypatch.setattr(watchdog, "stop_server", lambda pgdata: True)
        failure = watchdog.recover_db() or ""
        assert "missing required extension" in failure
        assert "initial attach error" in failure

    @pytest.mark.skipif(sys.platform == "win32", reason="macOS and POSIX tooling runs on the Mac")
    def test_another_installations_cluster_is_reported_never_stopped(self, monkeypatch, tmp_path):
        # The Mac app's cluster may be running for the app right now. A source watchdog that the
        # ownership guard refuses must not take the restart path and stop it.
        import json

        from tracker import config

        state = tmp_path / "state"
        state.mkdir()
        (state / "db.owner.json").write_text(json.dumps({"owner": "app"}))
        monkeypatch.setenv("ROLEBAND_STATE_DIR", str(state))
        monkeypatch.delenv("ROLEBAND_PGDATA", raising=False)
        monkeypatch.delenv("ROLEBAND_DATABASE_URL", raising=False)
        stops: list[object] = []
        monkeypatch.setattr(watchdog, "get_settings", lambda: config.Settings(_env_file=None))
        monkeypatch.setattr(watchdog, "stop_server", lambda pgdata: stops.append(pgdata) or True)

        failure = watchdog.recover_db() or ""
        assert "ROLEBAND_PGDATA" in failure
        assert stops == []

    def test_an_external_database_is_not_ours_to_restart(self, monkeypatch):
        class _Settings:
            database_url_override = "postgresql://u@elsewhere/db"
            db_embedded = True

            def ensure_embedded_server(self):  # pragma: no cover - must not run
                raise AssertionError("must not start a server when an external URL is set")

        monkeypatch.setattr(watchdog, "get_settings", _Settings)
        assert "external database" in (watchdog.recover_db() or "")


async def _scan_reading(
    db_session, *, last_finished_ago: timedelta, phase: str = "collecting",
    last_progress_ago: timedelta | None = None,
):
    """A live scan job and its run, which finished its last company `last_finished_ago`
    and, when given, last read anything `last_progress_ago`."""
    from sqlalchemy import select

    from tracker.company_store import ensure_builtins, ensure_source_bindings
    from tracker.db.models import JobRun, Notification, ScrapeRun, ScrapeSourceRun, SourceBinding

    now = datetime.now(UTC)
    await ensure_builtins(db_session)
    await ensure_source_bindings(db_session)
    binding = (await db_session.scalars(select(SourceBinding).limit(1))).one()
    job = JobRun(job="scan", key="scan", trigger="schedule", state="running")
    run = ScrapeRun(started_at=now - timedelta(hours=5), heartbeat_at=now, status="running")
    db_session.add_all([job, run])
    await db_session.flush()
    db_session.add(Notification(
        created_at=now, priority="low", category="sync_started", title="Scanning",
        source_type="run", source_id=run.id, meta={"progress": {
            "phase": phase,
            "last_progress_at_ms": (
                int((now - last_progress_ago).timestamp() * 1000)
                if last_progress_ago is not None else None
            ),
        }},
    ))
    finished = now - last_finished_ago
    db_session.add(ScrapeSourceRun(
        run_id=run.id, binding_id=binding.id, company_slug=binding.company_slug,
        provider_key="greenhouse", scan_mode="reconcile", outcome="ok",
        started_at=finished, finished_at=finished,
    ))
    await db_session.commit()
    return job


@pytest.mark.asyncio
async def test_a_scan_that_finishes_no_company_for_too_long_is_stopped(db_session):
    """Judged by progress: five hours of reading is no reason to stop a scan,
    and nearly an hour with no company finished is, since every company stops
    by its own budget."""
    from tracker.config import get_settings

    settings = get_settings()
    job = await _scan_reading(db_session, last_finished_ago=timedelta(minutes=50))

    assert await watchdog.stop_stuck_scan(db_session, now=datetime.now(UTC), settings=settings)
    await db_session.commit()
    await db_session.refresh(job)
    assert job.cancel_reason == "stuck"


@pytest.mark.asyncio
async def test_a_long_scan_still_finishing_companies_is_left_alone(db_session):
    from tracker.config import get_settings

    settings = get_settings()
    job = await _scan_reading(db_session, last_finished_ago=timedelta(minutes=5))

    assert not await watchdog.stop_stuck_scan(db_session, now=datetime.now(UTC), settings=settings)
    await db_session.refresh(job)
    assert job.cancel_requested_at is None


@pytest.mark.asyncio
async def test_the_passes_after_collection_are_not_judged(db_session):
    from tracker.config import get_settings

    settings = get_settings()
    await _scan_reading(db_session, last_finished_ago=timedelta(minutes=50), phase="finishing")

    assert not await watchdog.stop_stuck_scan(db_session, now=datetime.now(UTC), settings=settings)


@pytest.mark.asyncio
async def test_a_long_full_read_still_reading_is_left_alone(db_session):
    """A full read has no time ceiling, so a large careers page can keep one
    company reading for hours with no company finished. Its progress is what
    shows it is working."""
    from tracker.config import get_settings

    settings = get_settings()
    job = await _scan_reading(
        db_session, last_finished_ago=timedelta(hours=2), last_progress_ago=timedelta(seconds=30),
    )

    assert not await watchdog.stop_stuck_scan(db_session, now=datetime.now(UTC), settings=settings)
    await db_session.refresh(job)
    assert job.cancel_requested_at is None


@pytest.mark.asyncio
async def test_a_scan_whose_reading_stopped_too_long_ago_is_stopped(db_session):
    """Progress that stopped counts like a company that stopped finishing."""
    from tracker.config import get_settings

    settings = get_settings()
    job = await _scan_reading(
        db_session, last_finished_ago=timedelta(hours=2), last_progress_ago=timedelta(minutes=50),
    )

    assert await watchdog.stop_stuck_scan(db_session, now=datetime.now(UTC), settings=settings)
    await db_session.commit()
    await db_session.refresh(job)
    assert job.cancel_reason == "stuck"

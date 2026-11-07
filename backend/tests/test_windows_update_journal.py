"""A package update is settled by the version that runs next, and nothing opens the database mid-way."""

from __future__ import annotations

import json
import sys

import httpx
import pytest
from cryptography.hazmat.primitives.asymmetric import ed25519

from tests.test_windows_migration import retained as retained

pytestmark = pytest.mark.skipif(sys.platform != "win32", reason="Windows update requires Windows")

SHA = "a" * 64


@pytest.fixture
def state(tmp_path):
    from tracker.platform.windows_private import private_directory

    private_directory(tmp_path / "state")
    return tmp_path / "state"


def _begin(state, tmp_path):
    from tracker.platform import windows_update_journal as journal

    return journal.begin(state, from_version="0.1.2", to_version="0.1.3", package=tmp_path / "update.msix",
                         package_sha256=SHA)


def _launchable(state):
    from tracker.platform.windows_recovery import RecoveryError, require_launchable

    try:
        require_launchable(state)
        return "accepted"
    except RecoveryError as error:
        return "unfinished" if "unfinished" in str(error) else "damaged"


def test_the_new_version_prepares_then_completes(state, tmp_path):
    from tracker.platform import windows_update_journal as journal

    _begin(state, tmp_path)
    assert _launchable(state) == "unfinished", "nothing opens the database while the package switches"
    assert journal.resume(state, "0.1.3")["phase"] == "preparing"
    assert _launchable(state) == "accepted"
    assert journal.settle(state, "0.1.3", prepared=True)["phase"] == "complete"
    assert _launchable(state) == "accepted"


def test_the_old_version_starting_again_means_the_switch_never_happened(state, tmp_path):
    from tracker.platform import windows_update_journal as journal

    _begin(state, tmp_path)
    assert journal.resume(state, "0.1.2")["phase"] == "aborted"
    assert _launchable(state) == "accepted"


def test_a_failed_preparation_blocks_everything_until_recovery(state, tmp_path):
    from tracker.platform import windows_update_journal as journal

    _begin(state, tmp_path)
    journal.resume(state, "0.1.3")
    assert journal.settle(state, "0.1.3", prepared=False)["phase"] == "failed"
    assert _launchable(state) == "unfinished"
    assert journal.resume(state, "0.1.3")["phase"] == "failed", "a restart does not hide the failure"


def test_only_the_new_version_settles_its_preparation(state, tmp_path):
    from tracker.platform import windows_update_journal as journal
    from tracker.platform.windows_recovery import RecoveryError

    _begin(state, tmp_path)
    with pytest.raises(RecoveryError):
        journal.settle(state, "0.1.3", prepared=True)
    journal.resume(state, "0.1.3")
    with pytest.raises(RecoveryError):
        journal.settle(state, "0.1.2", prepared=True)


def test_a_second_update_waits_for_the_first_to_settle(state, tmp_path):
    from tracker.platform import windows_update_journal as journal
    from tracker.platform.windows_recovery import RecoveryError

    _begin(state, tmp_path)
    with pytest.raises(RecoveryError, match="unsettled"):
        _begin(state, tmp_path)
    journal.resume(state, "0.1.2")
    assert _begin(state, tmp_path)["phase"] == "applying"


def test_the_database_chokepoint_refuses_mid_update(state, tmp_path):
    from tracker.platform.embedded_db import ensure_server
    from tracker.platform.windows_recovery import RecoveryError

    _begin(state, tmp_path)
    with pytest.raises(RecoveryError, match="unfinished"):
        ensure_server(state / "db", database="roleband")
    assert not (state / "db").exists()


def _retained_update(state, tmp_path):
    from tracker.platform.windows_packages import download
    from tracker.platform.windows_release import Identity, prepare, verify_offer

    key = ed25519.Ed25519PrivateKey.generate()
    identity = Identity("roleband/roleband-trials", key.public_key().public_bytes_raw(), "RoleBand.Windows.Trial",
                        "CN=RoleBand Windows Trial")
    built = tmp_path / "built.msix"
    built.write_bytes(b"PK update" * 100)
    files = prepare(built, tmp_path / "release", identity, key, version="0.1.3", revision=0, commit="e" * 40)
    signed = tuple(path.read_bytes() for path in files[1:])
    offer = verify_offer(identity, "0.0.0", *signed)
    transport = httpx.MockTransport(lambda request: httpx.Response(200, content=files[0].read_bytes()))
    return identity, download(state, identity, offer, signed, "0.1.2", transport=transport)


def test_begin_journals_only_a_verified_retained_package_with_the_engine_stopped(state, tmp_path, capsys):
    from scripts.windows_update import _begin as begin_command
    from tracker.platform.windows_leases import ENGINE, lease
    from tracker.platform.windows_private import private_directory

    identity, package = _retained_update(state, tmp_path)
    stray = tmp_path / "stray.msix"
    stray.write_bytes(package.read_bytes())
    assert begin_command(state, identity, stray, "0.1.2") == 1
    private_directory(state / "launcher")
    with lease(state / "launcher" / ENGINE):
        assert begin_command(state, identity, package, "0.1.2") == 1
    assert not (state / "recovery" / "update.json").exists()
    assert begin_command(state, identity, package, "0.1.2") == 0
    record = json.loads((state / "recovery" / "update.json").read_text(encoding="utf-8"))
    assert (record["phase"], record["to_version"], record["package"]) == ("applying", "0.1.3", str(package.resolve()))
    capsys.readouterr()


class TestRecovery:
    """Returning to the previous version puts back the database this update's migration replaced."""

    @staticmethod
    def _as_previous_runtime(monkeypatch, heads):
        from alembic.script import ScriptDirectory

        # The checkout carries the new migrations; the previous package's runtime ends at `heads`.
        monkeypatch.setattr(ScriptDirectory, "get_heads", lambda self: list(heads))

    @staticmethod
    def _failed_update(state):
        from tracker.platform import windows_update_journal as journal

        journal.begin(state, from_version="0.1.2", to_version="0.1.3", package=state.parent / "update.msix",
                      package_sha256=SHA)
        journal.resume(state, "0.1.3")
        return journal

    def test_a_migrated_database_is_put_back_and_the_migrated_one_kept(self, retained, monkeypatch):
        from tests.test_windows_migration import PREVIOUS, _heads, _prepare
        from tracker.platform.embedded_db import ensure_server, stop_server

        journal = self._failed_update(retained)
        assert _prepare(retained).returncode == 0, "the new version migrates behind its checkpoint"
        assert _heads(retained) != [PREVIOUS]
        record = json.loads((retained / "recovery" / "pre-migration.json").read_text(encoding="utf-8"))
        assert record["update_id"] == journal.read(retained)["id"]
        journal.settle(retained, "0.1.3", prepared=False)
        journal.recover_begin(retained, "0.1.3")
        self._as_previous_runtime(monkeypatch, [PREVIOUS])
        assert journal.recover_database(retained, "0.1.2")["phase"] == "recovered"
        monkeypatch.undo()
        assert _heads(retained) == [PREVIOUS]
        server = ensure_server(retained / "db", database="roleband")
        try:
            from tests.embedded_utils import psql

            assert "Retained role" in psql(server, "SELECT title FROM retained_sentinel")
        finally:
            stop_server(retained / "db")
        kept = list((retained / "recovery").glob("restore-*/retained-db/PG_VERSION"))
        assert len(kept) == 1, "the migrated database is kept beside the restored one"

    def test_without_a_checkpoint_for_this_update_the_database_stays(self, retained):
        from tests.test_windows_migration import PREVIOUS, _heads

        journal = self._failed_update(retained)
        journal.settle(retained, "0.1.3", prepared=False)
        journal.recover_begin(retained, "0.1.3")
        assert journal.recover_database(retained, "0.1.2")["phase"] == "recovered"
        assert _heads(retained) == [PREVIOUS]
        assert not list((retained / "recovery").glob("restore-*"))

    def test_a_checkpoint_from_an_earlier_update_is_never_restored(self, retained):
        from tracker.platform.windows_storage import write_json

        journal = self._failed_update(retained)
        write_json(retained / "recovery" / "pre-migration.json",
                   {"format": 1, "checkpoint": str(retained / "recovery" / "pre-migration" / "old"),
                    "from_heads": [], "to_heads": [], "created_at": "2026-01-01T00:00:00+00:00",
                    "update_id": "f" * 32})
        journal.settle(retained, "0.1.3", prepared=False)
        journal.recover_begin(retained, "0.1.3")
        assert journal.recover_database(retained, "0.1.2")["phase"] == "recovered"
        assert not list((retained / "recovery").glob("restore-*"))

    def test_only_the_new_version_hands_back_and_only_the_previous_one_finishes(self, state, tmp_path):
        from tracker.platform import windows_update_journal as journal
        from tracker.platform.windows_recovery import RecoveryError

        _begin(state, tmp_path)
        journal.resume(state, "0.1.3")
        with pytest.raises(RecoveryError):
            journal.recover_begin(state, "0.1.3")
        journal.settle(state, "0.1.3", prepared=False)
        with pytest.raises(RecoveryError):
            journal.recover_begin(state, "0.1.2")
        journal.recover_begin(state, "0.1.3")
        assert _launchable(state) == "unfinished"
        with pytest.raises(RecoveryError):
            journal.recover_database(state, "0.1.3")
        assert journal.recover_database(state, "0.1.2")["phase"] == "recovered"
        assert _launchable(state) == "accepted"

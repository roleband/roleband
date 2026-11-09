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


def test_a_new_version_stopped_while_preparing_prepares_again_at_its_next_start(state, tmp_path):
    from tracker.platform import windows_update_journal as journal

    _begin(state, tmp_path)
    first = journal.resume(state, "0.1.3")
    again = journal.resume(state, "0.1.3")
    assert (first["phase"], again["phase"], again["id"]) == ("preparing", "preparing", first["id"]), \
        "a kill mid-preparation neither completes nor fails the update"
    assert _launchable(state) == "accepted"
    assert journal.settle(state, "0.1.3", prepared=False)["phase"] == "failed"
    assert journal.resume(state, "0.1.3")["phase"] == "failed", "and a failure it then records stays for Undo"


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


def _undone(state, tmp_path):
    from tracker.platform import windows_update_journal as journal

    _begin(state, tmp_path)
    journal.resume(state, "0.1.3")
    journal.settle(state, "0.1.3", prepared=False)
    journal.recover_begin(state, "0.1.3")
    return journal.recovered(state, "0.1.2")


def test_status_says_how_the_last_update_ended_and_holds_back_the_undone_version(state, tmp_path, monkeypatch, capsys):
    import base64

    from scripts import windows_update
    from tracker.platform import releases
    from tracker.platform.windows_release import Identity, prepare
    from tracker.platform.windows_updates import CHECK

    key = ed25519.Ed25519PrivateKey.generate()
    identity = Identity("roleband/roleband-trials", key.public_key().public_bytes_raw(), "RoleBand.Windows.Trial",
                        "CN=RoleBand Windows Trial")
    built = tmp_path / "built.msix"
    built.write_bytes(b"PK update 0.1.3" * 100)
    signed = [path.read_bytes() for path in prepare(built, tmp_path / "release", identity, key, version="0.1.3",
                                                     revision=0, commit="e" * 40)[1:]]
    (state / "launcher").mkdir()
    (state / CHECK).write_text(json.dumps({"offer": dict(zip(("checksum", "metadata", "signature"),
                                                             (base64.b64encode(part).decode() for part in signed), strict=True))}))
    stamped = tmp_path / "release-identity.json"
    stamped.write_text(json.dumps({"format": 1, "feed": identity.feed,
                                   "release_public_key": base64.b64encode(identity.release_key).decode(),
                                   "package_name": identity.package_name, "publisher": identity.publisher}))
    monkeypatch.setattr(windows_update, "identity_path", lambda: stamped)
    monkeypatch.setattr(releases, "running_version", lambda *_: "0.1.2")
    monkeypatch.setenv("ROLEBAND_STATE_DIR", str(state))

    def status():
        assert windows_update.main(["status", "--state", str(state)]) == 0
        return json.loads(capsys.readouterr().out)

    assert status()["offer"] == "0.1.3", "before any update, the kept offer stands"
    _undone(state, tmp_path)
    answer = status()
    since = answer["update"].pop("since")
    assert answer["update"] == {"phase": "recovered", "from": "0.1.2", "to": "0.1.3", "running": "from", "package": "update.msix"}
    assert since == pytest.approx((state / "recovery" / "update.json").stat().st_mtime), "when the journal last changed"
    assert answer["offer"] is None, "the version that was undone is not offered again"


def _keeper(state, tmp_path):
    from tracker.platform.windows_packages import download
    from tracker.platform.windows_release import Identity, prepare, verify_offer

    key = ed25519.Ed25519PrivateKey.generate()
    identity = Identity("roleband/roleband-trials", key.public_key().public_bytes_raw(), "RoleBand.Windows.Trial",
                        "CN=RoleBand Windows Trial")

    def kept(version):
        built = tmp_path / f"built-{version}.msix"
        built.write_bytes(f"PK update {version}".encode() * 100)
        files = prepare(built, tmp_path / f"release-{version}", identity, key, version=version, revision=0,
                        commit="e" * 40)
        signed = tuple(path.read_bytes() for path in files[1:])
        offer = verify_offer(identity, "0.0.0", *signed)
        transport = httpx.MockTransport(lambda request: httpx.Response(200, content=files[0].read_bytes()))
        return download(state, identity, offer, signed, "0.1.2", transport=transport)

    return identity, kept


def _retained_update(state, tmp_path, *, keep_running=True):
    identity, kept = _keeper(state, tmp_path)
    if keep_running:
        kept("0.1.2")
    return identity, kept("0.1.3")


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


def test_begin_refuses_an_update_that_could_not_be_undone(state, tmp_path, capsys):
    from scripts.windows_update import _begin as begin_command

    identity, package = _retained_update(state, tmp_path, keep_running=False)
    assert begin_command(state, identity, package, "0.1.2") == 1
    assert "could not be undone" in capsys.readouterr().out
    assert not (state / "recovery" / "update.json").exists()


def _failed(state, tmp_path):
    from tracker.platform import windows_update_journal as journal

    _begin(state, tmp_path)
    journal.resume(state, "0.1.3")
    return journal.settle(state, "0.1.3", prepared=False)


class TestNoOneIsStuck:
    """A broken update always has a way out: Undo, a newer release from the app, or a newer release by hand."""

    def test_a_newer_release_takes_over_a_failed_update_and_undo_still_returns_to_the_version_before(self, state, tmp_path):
        from tracker.platform import windows_update_journal as journal

        failed = _failed(state, tmp_path)
        taken = journal.begin(state, from_version="0.1.3", to_version="0.1.4", package=tmp_path / "next.msix",
                              package_sha256=SHA)
        assert (taken["id"], taken["from_version"], taken["to_version"], taken["phase"]) == (
            failed["id"], "0.1.2", "0.1.4", "applying"), "the same update, with the same way back"
        assert journal.resume(state, "0.1.4")["phase"] == "preparing"
        journal.settle(state, "0.1.4", prepared=False)
        journal.recover_begin(state, "0.1.4")
        assert journal.recovered(state, "0.1.2")["phase"] == "recovered"

    def test_a_takeover_windows_did_not_switch_to_leaves_the_failed_version_failed(self, state, tmp_path):
        from tracker.platform import windows_update_journal as journal

        _failed(state, tmp_path)
        journal.begin(state, from_version="0.1.3", to_version="0.1.4", package=tmp_path / "next.msix", package_sha256=SHA)
        record = journal.resume(state, "0.1.3")
        assert (record["phase"], record["to_version"]) == ("failed", "0.1.3"), "Undo stays one press away"
        assert journal.recover_begin(state, "0.1.3")["phase"] == "recovering"

    @pytest.mark.parametrize("phase", ["applying", "preparing", "failed", "recovering"])
    def test_a_newer_release_installed_by_hand_takes_over_whatever_was_unfinished(self, state, tmp_path, phase):
        from tracker.platform import windows_update_journal as journal

        record = _begin(state, tmp_path)
        if phase != "applying":
            journal.resume(state, "0.1.3")
        if phase in {"failed", "recovering"}:
            journal.settle(state, "0.1.3", prepared=False)
        if phase == "recovering":
            journal.recover_begin(state, "0.1.3")
        taken = journal.resume(state, "0.1.4")
        assert (taken["id"], taken["from_version"], taken["to_version"], taken["phase"]) == (
            record["id"], "0.1.2", "0.1.4", "preparing")
        assert _launchable(state) == "accepted", "the newer version starts"

    @pytest.mark.parametrize("phase", ["preparing", "failed"])
    def test_the_previous_version_installed_by_hand_finishes_the_undo_itself(self, state, tmp_path, phase):
        from tracker.platform import windows_update_journal as journal

        _begin(state, tmp_path)
        journal.resume(state, "0.1.3")
        if phase == "failed":
            journal.settle(state, "0.1.3", prepared=False)
        assert journal.resume(state, "0.1.2")["phase"] == "recovering", "as if Undo had been pressed"
        assert journal.recover_database(state, "0.1.2")["phase"] == "recovered"
        assert _launchable(state) == "accepted"

    def test_only_a_failed_update_is_taken_over_from_the_app(self, state, tmp_path):
        from tracker.platform import windows_update_journal as journal
        from tracker.platform.windows_recovery import RecoveryError

        _begin(state, tmp_path)
        journal.resume(state, "0.1.3")
        with pytest.raises(RecoveryError, match="unsettled"):
            journal.begin(state, from_version="0.1.3", to_version="0.1.4", package=tmp_path / "n.msix", package_sha256=SHA)
        journal.settle(state, "0.1.3", prepared=False)
        with pytest.raises(RecoveryError, match="unsettled"):
            journal.begin(state, from_version="0.1.3", to_version="0.1.3", package=tmp_path / "n.msix", package_sha256=SHA)

    def test_cleaning_up_packages_never_removes_the_version_an_unfinished_update_returns_to(self, state, tmp_path):
        from tracker.platform.windows_packages import retained

        identity, kept = _keeper(state, tmp_path)
        kept("0.1.2")
        _failed(state, tmp_path)
        kept("0.1.3")
        kept("0.1.4")
        assert [offer.version for offer, _ in retained(state, identity)] == ["0.1.4", "0.1.3", "0.1.2"]

    def test_a_damaged_journal_removes_no_package(self, state, tmp_path):
        from tracker.platform.windows_fs import publish
        from tracker.platform.windows_packages import retained

        identity, kept = _keeper(state, tmp_path)
        kept("0.1.2")
        publish(state / "recovery" / "update.json", b'{"format": 9}')
        kept("0.1.3")
        kept("0.1.4")
        assert len(retained(state, identity)) == 3

    def test_undo_downloads_the_previous_version_when_it_is_not_kept(self, state, tmp_path, monkeypatch, capsys):
        from scripts.windows_update import _recover_begin
        from tracker.platform import windows_packages, windows_update_journal

        identity, kept = _keeper(state, tmp_path)
        _failed(state, tmp_path)
        fetched = []

        def fetch(state_, identity_, version, **_kwargs):
            fetched.append(version)
            return kept(version)

        monkeypatch.setattr(windows_packages, "retain_running", fetch)
        assert _recover_begin(state, identity, "0.1.3") == 0
        answer = json.loads(capsys.readouterr().out)
        assert (fetched, answer["phase"]) == (["0.1.2"], "recovering")
        assert answer["package"].endswith("RoleBand-0.1.2-Windows-x64.msix")
        assert windows_update_journal.read(state)["phase"] == "recovering"

    def test_an_undo_that_cannot_fetch_the_previous_version_says_so_and_changes_nothing(self, state, tmp_path,
                                                                                       monkeypatch, capsys):
        from scripts.windows_update import _recover_begin
        from tracker.platform import windows_packages, windows_update_journal

        identity, _kept = _keeper(state, tmp_path)
        _failed(state, tmp_path)

        def offline(*_args, **_kwargs):
            raise httpx.ConnectError("offline")

        monkeypatch.setattr(windows_packages, "retain_running", offline)
        assert _recover_begin(state, identity, "0.1.3") == 1
        answer = json.loads(capsys.readouterr().out)
        assert (answer["status"], answer["kind"]) == ("refused", "offline") and "0.1.2" in answer["reason"]
        assert windows_update_journal.read(state)["phase"] == "failed", "Undo stays one press away"

    def test_an_undo_whose_previous_release_is_gone_says_trying_again_cannot_help(self, state, tmp_path, monkeypatch, capsys):
        from scripts.windows_update import _recover_begin
        from tracker.platform import windows_packages, windows_update_journal
        from tracker.platform.windows_updates import ReleaseMissing

        identity, _kept = _keeper(state, tmp_path)
        _failed(state, tmp_path)

        def gone(*_args, **_kwargs):
            raise ReleaseMissing("A release file is not published")

        monkeypatch.setattr(windows_packages, "retain_running", gone)
        assert _recover_begin(state, identity, "0.1.3") == 1
        answer = json.loads(capsys.readouterr().out)
        assert (answer["status"], answer["kind"]) == ("refused", "missing")
        assert "no longer published" in answer["reason"]
        assert windows_update_journal.read(state)["phase"] == "failed", "a newer release can still take over"

    def test_a_failed_version_may_begin_a_newer_update_when_the_version_before_it_is_kept(self, state, tmp_path, capsys):
        from scripts.windows_update import _begin as begin_command
        from tracker.platform import windows_update_journal
        from tracker.platform.windows_private import private_directory

        identity, kept = _keeper(state, tmp_path)
        kept("0.1.2")
        _failed(state, tmp_path)
        package = kept("0.1.4")
        private_directory(state / "launcher")
        assert begin_command(state, identity, package, "0.1.3") == 0, capsys.readouterr().out
        record = windows_update_journal.read(state)
        assert (record["from_version"], record["to_version"], record["phase"]) == ("0.1.2", "0.1.4", "applying")

"""Windows state uses the known folder and refuses unsafe credential storage."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.skipif(sys.platform != "win32", reason="Windows state discovery requires Windows")


def test_known_folder_does_not_trust_localappdata_environment(monkeypatch, tmp_path):
    from tracker.platform.windows_state import local_app_data

    actual = local_app_data()
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "foreign"))
    assert local_app_data() == actual
    assert actual.is_absolute() and actual.is_dir()


def test_known_folder_disables_package_specific_redirection(monkeypatch, tmp_path):
    import ctypes
    from ctypes import wintypes
    from types import SimpleNamespace

    from tracker.platform import windows_state

    allocation = ctypes.create_unicode_buffer(str(tmp_path))
    released = []

    def lookup(_folder, flags, token, output):
        assert flags == 0x00010000
        assert token is None
        ctypes.cast(output, ctypes.POINTER(wintypes.LPWSTR))[0] = ctypes.cast(allocation, wintypes.LPWSTR)
        return 0

    boundary = SimpleNamespace(SHGetKnownFolderPath=lookup, CoTaskMemFree=lambda value: released.append(value.value))
    monkeypatch.setattr(windows_state.ctypes, "WinDLL", lambda *_args, **_kwargs: boundary)
    assert windows_state.local_app_data() == tmp_path
    assert released == [str(tmp_path)]


def test_default_state_and_installed_roots_follow_the_known_folder(monkeypatch):
    from tracker.platform.paths import installed_data_roots, user_data_dir
    from tracker.platform.windows_state import local_app_data

    monkeypatch.delenv("ROLEBAND_STATE_DIR", raising=False)
    installed = local_app_data() / "RoleBand"
    assert user_data_dir() == installed / "data"
    assert set(installed_data_roots()) == {installed, Path.home() / ".roleband"}


@pytest.fixture
def installed_roots(monkeypatch, tmp_path):
    """Both installed roots moved under `tmp_path`, so a broken guard writes there."""
    from tracker.platform import windows_state

    home, known = tmp_path / "profile", tmp_path / "LocalAppData"
    monkeypatch.setenv("USERPROFILE", str(home))
    monkeypatch.setattr(windows_state, "local_app_data", lambda: known)
    return known / "RoleBand", home / ".roleband"


def test_recovery_refuses_installed_state_before_creating_anything(installed_roots, tmp_path):
    from tracker.platform.windows_recovery import RecoveryError, recovery_leases

    for root in installed_roots:
        for state in (root, root / "nested" / "state"):
            with pytest.raises(RecoveryError), recovery_leases(state):
                pytest.fail("an installed root was leased")
            assert not root.exists()
    # A sibling sharing the root's name prefix is ordinary trial state.
    sibling = installed_roots[0].parent / "RoleBandTrials" / "trial"
    with recovery_leases(sibling):
        assert (sibling / "launcher" / "desktop.lock").is_file()


def test_an_installed_release_restores_its_own_data_and_nothing_else(installed_roots, monkeypatch, tmp_path):
    """Undo's restore runs in the installed app on its own state; a trial, a source run or a release started on
    other state still never reaches installed data."""
    from tracker.platform import paths
    from tracker.platform.windows_recovery import RecoveryError, recovery_leases

    own, mac = installed_roots
    monkeypatch.setattr(paths, "DATA_DIR", own)
    monkeypatch.setattr(paths, "RELEASE", False)
    with pytest.raises(RecoveryError), recovery_leases(own):
        pytest.fail("a trial leased an installed root")
    monkeypatch.setattr(paths, "RELEASE", True)
    with recovery_leases(own):
        assert (own / "launcher" / "desktop.lock").is_file()
    with pytest.raises(RecoveryError), recovery_leases(mac):
        pytest.fail("a release leased another app's data")
    monkeypatch.setattr(paths, "DATA_DIR", tmp_path / "other-state")
    with pytest.raises(RecoveryError), recovery_leases(own):
        pytest.fail("a release started on other state leased the installed root")


def test_only_a_release_marker_makes_a_release_build(tmp_path):
    from tracker.platform.paths import release_channel

    assert not release_channel(tmp_path), "no marker: a checkout or a trial"
    (tmp_path / "build.json").write_text('{"format": 1, "channel": "release"}', encoding="utf-8")
    assert release_channel(tmp_path)
    for text in ('{"format": 1, "channel": "trial"}', '{"format": 2, "channel": "release"}', "not json", "[]"):
        (tmp_path / "build.json").write_text(text, encoding="utf-8")
        assert not release_channel(tmp_path), text


def test_checkpoint_command_refuses_installed_state(installed_roots, monkeypatch, tmp_path, capsys):
    from scripts import windows_checkpoint

    # The command points these at the state it was given; restore them afterwards.
    for name in ("ROLEBAND_STATE_DIR", "ROLEBAND_PGDATA", "ROLEBAND_CACHE_DIR", "ROLEBAND_PLUGINS_DIR",
                 "ROLEBAND_SECRET_KEY_FILE", "ROLEBAND_DATABASE_URL", "ROLEBAND_NO_USAGE_STATS"):
        monkeypatch.setenv(name, os.environ.get(name, ""))
    for root in installed_roots:
        pgdata = root / "db"
        pgdata.mkdir(parents=True)
        (pgdata / "PG_VERSION").write_text("16\n")
        monkeypatch.setattr(sys, "argv", [
            "windows_checkpoint", "create", "--pgdata", str(pgdata), "--database", "roleband",
            "--destination", str(tmp_path / "checkpoint"), "--verification-state", str(tmp_path / "verify"),
        ])
        with pytest.raises(SystemExit) as stopped:
            windows_checkpoint.main()
        assert stopped.value.code == 2
        assert "installed app" in capsys.readouterr().err
        assert sorted(path.name for path in root.iterdir()) == ["db"]
    assert not (tmp_path / "checkpoint").exists()


def test_a_junction_into_installed_state_is_still_installed_state(installed_roots, tmp_path):
    import _winapi

    from tracker.platform.paths import within_installed_data

    installed = installed_roots[0]
    installed.mkdir(parents=True)
    elsewhere = tmp_path / "trials" / "trial"
    elsewhere.parent.mkdir(parents=True)
    _winapi.CreateJunction(str(installed), str(elsewhere))
    assert within_installed_data(elsewhere / "db"), "the junction leads into an installed app's data"
    assert not within_installed_data(tmp_path / "trials" / "other" / "db")


def test_packaged_paths_and_defaults_share_explicit_retained_state(tmp_path):
    backend = Path(__file__).resolve().parents[1]
    state = tmp_path / "私有 retained state"
    env = {key: value for key, value in os.environ.items() if not key.startswith("ROLEBAND_")}
    env.update({"ROLEBAND_STATE_DIR": str(state), "ROLEBAND_PACKAGED": "1", "PYTHONDONTWRITEBYTECODE": "1"})
    code = (
        "import json; from tracker.platform.paths import DATA_DIR; from tracker.config import Settings; "
        "from tracker.platform.secrets import key_path; s=Settings(); "
        "print(json.dumps([str(p) for p in [DATA_DIR,s.embedded_pgdata(),s.cache_dir(),s.plugins_dir(),key_path()]]))"
    )
    result = subprocess.run([sys.executable, "-c", code], cwd=backend, env=env, capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stderr
    assert [Path(item) for item in json.loads(result.stdout)] == [state, state / "db", state / "cache", state / "plugins", state / "secret.key"]
    assert not state.exists()


def test_private_preparation_and_fernet_keys_are_readable_only_by_this_account(tmp_path, monkeypatch):
    from tracker.platform import preparation
    from tracker.platform.secrets import seal, unseal
    from tracker.platform.windows_private import require_private

    state = tmp_path / "state"
    monkeypatch.setenv("ROLEBAND_STATE_DIR", str(state))
    monkeypatch.delenv("ROLEBAND_SECRET_KEY_FILE", raising=False)
    preparation.update(state, database="ready", service="ready")
    encrypted = seal("synthetic API key")
    assert unseal(encrypted) == "synthetic API key"
    require_private(state / "secret.key")
    require_private(state / "launcher" / "preparation.json")
    assert preparation.read(state).ready


def test_discovery_refuses_an_acl_readable_by_everyone(tmp_path):
    from tracker.platform.local_http import Authority, Client

    state = tmp_path / "state"
    authority = Authority(state, "http://127.0.0.1:58329")
    try:
        subprocess.run(["icacls", str(authority.path), "/grant", "*S-1-1-0:(R)"], capture_output=True, check=True)
        with pytest.raises(PermissionError):
            Client(state)
    finally:
        authority.close()


def test_windows_source_discovery_never_claims_a_mac_installation(tmp_path):
    from tracker.platform.launcher import installed_checkout, register_installation

    assert not installed_checkout(tmp_path, home=tmp_path)
    assert not register_installation(tmp_path, {}, home=tmp_path)
    assert not (tmp_path / ".roleband").exists()


def test_windows_packaged_mode_cannot_disable_http_authentication(monkeypatch):
    from tracker.platform import local_http

    monkeypatch.setattr(local_http, "PACKAGED", True)
    monkeypatch.setenv("ROLEBAND_LOCAL_AUTH", "0")
    assert local_http.required()


def test_relative_state_override_is_refused_before_any_storage_is_created(monkeypatch):
    from tracker.platform.paths import user_data_dir

    monkeypatch.setenv("ROLEBAND_STATE_DIR", "relative-state")
    with pytest.raises(ValueError, match="must be absolute"):
        user_data_dir()


def test_a_fernet_key_with_an_unsafe_acl_is_unavailable_and_never_rewritten(tmp_path, monkeypatch):
    from tracker.platform import secrets

    path = tmp_path / "private" / "secret.key"
    monkeypatch.setenv(secrets.KEY_FILE_ENV, str(path))
    sealed = secrets.seal("synthetic secret")
    before = path.read_bytes()
    subprocess.run(["icacls", str(path), "/grant", "*S-1-1-0:(R)"], capture_output=True, check=True)
    assert secrets.unseal_or_none(sealed) is None
    with pytest.raises(secrets.SecretUnavailable):
        secrets.seal("replacement")
    assert path.read_bytes() == before


def test_failed_known_folder_lookup_does_not_fall_back_to_an_environment_path(monkeypatch, tmp_path):
    from types import SimpleNamespace

    from tracker.platform import windows_state

    def lookup(*_args):
        return -2147467259

    def release(*_args):
        raise AssertionError("a failed lookup returned no allocation")

    boundary = SimpleNamespace(SHGetKnownFolderPath=lookup, CoTaskMemFree=release)
    monkeypatch.setattr(windows_state.ctypes, "WinDLL", lambda *_args, **_kwargs: boundary)
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "untrusted"))
    with pytest.raises(OSError, match="LocalAppData lookup failed"):
        windows_state.local_app_data()
    assert not (tmp_path / "untrusted").exists()


@pytest.mark.asyncio
async def test_authenticated_api_refuses_an_entry_point_without_exclusive_socket_ownership(monkeypatch, tmp_path):
    from tracker.api import app as composition

    state = tmp_path / "refused-entry"
    monkeypatch.setenv("ROLEBAND_LOCAL_AUTH", "1")
    monkeypatch.delenv("ROLEBAND_HTTP_EXCLUSIVE", raising=False)
    monkeypatch.setattr(composition, "DATA_DIR", state)
    with pytest.raises(ValueError, match="exclusive HTTP server"):
        async with composition._lifespan(composition.app):
            raise AssertionError("An unsafe entry point became available")
    assert not state.exists()

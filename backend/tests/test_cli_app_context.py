"""The `app` context the Mac app writes so the `roleband` command reaches its engine.

Every case uses a scratch home, so the person's real context file is never read or
written. The client's own reader (`tracker.cli.contexts.resolve`) checks what was
written: a context file it would refuse is no context at all.
"""

from __future__ import annotations

import json
import os
import stat
import sys
from pathlib import Path

import pytest

from tracker.cli import contexts
from tracker.cli.errors import ClientError
from tracker.platform import cli_context
from tracker.supervisor import prepare

pytestmark = pytest.mark.skipif(sys.platform == "win32", reason="the app context is written by the Mac app")


@pytest.fixture
def home(tmp_path, monkeypatch) -> Path:
    root = tmp_path / "home"
    root.mkdir()
    monkeypatch.setenv("HOME", str(root))
    monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
    monkeypatch.delenv(cli_context.CONFIG_ENV, raising=False)
    return root


def _file(home: Path) -> Path:
    return cli_context.context_file({}, home)


def _write(path: Path, document: object) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(document)
    path.write_text(text, encoding="utf-8")
    return text


def test_a_new_machine_gets_the_app_context_and_the_command_resolves_it(home):
    assert contexts.config_path() == _file(home)
    with pytest.raises(ClientError) as before:
        contexts.resolve(None)
    assert before.value.code == "context_required"

    assert cli_context.write_app_context(_file(home), 8010) == cli_context.WRITTEN

    reached = contexts.resolve(None)
    assert (reached.name, reached.url, reached.workspace_id) == ("app", "http://127.0.0.1:8010", None)
    assert stat.S_IMODE(_file(home).stat().st_mode) == 0o600
    assert stat.S_IMODE(_file(home).parent.stat().st_mode) == 0o700


def test_a_second_start_leaves_the_file_as_it_is(home):
    path = _file(home)
    cli_context.write_app_context(path, 8010)
    before = path.read_bytes()
    assert cli_context.write_app_context(path, 8010) == cli_context.UNCHANGED
    assert path.read_bytes() == before


def test_a_file_that_already_says_so_keeps_its_own_layout(home):
    path = _file(home)
    text = _write(path, {"format": 1, "current": "app", "contexts": {"app": {"url": "http://127.0.0.1:8010"}}})
    assert cli_context.write_app_context(path, 8010) == cli_context.UNCHANGED
    assert path.read_text(encoding="utf-8") == text


def test_a_new_port_moves_the_app_context_and_keeps_the_persons_own(home):
    path = _file(home)
    pinned = "ws_" + "a" * 32
    _write(path, {
        "format": 1,
        "current": "dev",
        "contexts": {
            "dev": {"url": "http://127.0.0.1:8011"},
            "app": {"url": "http://127.0.0.1:8010", "workspace_id": pinned},
        },
    })

    assert cli_context.write_app_context(path, 8020) == cli_context.WRITTEN

    assert contexts.resolve(None).name == "dev"
    assert contexts.resolve("dev").url == "http://127.0.0.1:8011"
    app = contexts.resolve("app")
    assert (app.url, app.workspace_id) == ("http://127.0.0.1:8020", pinned)


def test_a_file_with_contexts_but_none_current_makes_the_app_current(home):
    path = _file(home)
    _write(path, {"format": 1, "contexts": {"dev": {"url": "http://127.0.0.1:8011"}}})
    assert cli_context.write_app_context(path, 8010) == cli_context.WRITTEN
    assert contexts.resolve(None).name == "app"
    assert contexts.resolve("dev").url == "http://127.0.0.1:8011"


@pytest.mark.parametrize("text", [
    "{not json",
    json.dumps({"format": 2, "contexts": {}}),
    json.dumps({"format": 1, "contexts": [], "current": "dev"}),
    json.dumps({"format": 1, "contexts": {}, "notes": "mine"}),
    json.dumps(["format", 1]),
    # json keeps a repeated key's last value, which would lose the first `contexts`.
    '{"format": 1, "contexts": {"dev": {"url": "http://127.0.0.1:8011"}}, "contexts": {}}',
    # The app entry is replaced, so a field the command refuses would be dropped by the write.
    json.dumps({"format": 1, "contexts": {"app": {"url": "http://127.0.0.1:8010", "notes": "mine"}}}),
    json.dumps({"format": 1, "contexts": {"app": "http://127.0.0.1:8010"}}),
    json.dumps({"format": 1, "contexts": {"app": {"url": "http://127.0.0.1:8010", "workspace_id": "mine"}}}),
    # A url the command refuses is the person's to fix, like any other field of the entry.
    json.dumps({"format": 1, "contexts": {"app": {"url": 42}}}),
    json.dumps({"format": 1, "contexts": {"app": {"url": "http://localhost:8010"}}}),
    json.dumps({"format": 1, "contexts": {"app": {"url": "http://[::1:8011"}}}),
])
def test_a_file_the_command_would_refuse_is_left_alone(home, text):
    path = _file(home)
    path.parent.mkdir(parents=True)
    path.write_text(text, encoding="utf-8")
    with pytest.raises(ClientError):
        contexts.resolve("app")
    assert cli_context.write_app_context(path, 8010) == cli_context.KEPT_FOREIGN
    assert path.read_text(encoding="utf-8") == text


@pytest.mark.parametrize("current", [42, "Not A Name", ""])
def test_a_current_the_command_would_refuse_is_left_alone(home, current):
    path = _file(home)
    text = _write(path, {"format": 1, "current": current, "contexts": {}})
    with pytest.raises(ClientError) as refused:
        contexts.resolve(None)
    assert refused.value.code == "context_invalid"
    assert cli_context.write_app_context(path, 8010) == cli_context.KEPT_FOREIGN
    assert path.read_text(encoding="utf-8") == text


def test_a_link_put_in_place_after_the_check_is_not_read_through(home, tmp_path, monkeypatch):
    """The link check and the read are two steps; the read itself refuses a link, so one that
    appears between them is still left alone."""
    path = _file(home)
    path.parent.mkdir(parents=True)
    victim = tmp_path / "victim.json"
    victim.write_text(json.dumps({"format": 1, "contexts": {}}), encoding="utf-8")
    path.symlink_to(victim)
    monkeypatch.setattr(Path, "is_symlink", lambda self: False)
    assert cli_context.write_app_context(path, 8010) == cli_context.KEPT_FOREIGN
    assert json.loads(victim.read_text(encoding="utf-8")) == {"format": 1, "contexts": {}}
    assert os.path.islink(path)


def test_a_link_at_a_staging_name_is_never_followed(home, tmp_path):
    """The write stages its text beside the file; a link left at a staging name must neither
    have its target truncated nor end up as the context file."""
    path = _file(home)
    path.parent.mkdir(parents=True)
    victim = tmp_path / "victim.txt"
    victim.write_text("kept", encoding="utf-8")
    for pid in range(os.getpid() - 2, os.getpid() + 3):
        (path.parent / f".{path.name}.{pid}.partial").symlink_to(victim)
    assert cli_context.write_app_context(path, 8010) == cli_context.WRITTEN
    assert victim.read_text(encoding="utf-8") == "kept"
    assert not path.is_symlink()
    assert contexts.resolve(None).port == 8010
    assert sorted(p.name for p in path.parent.iterdir() if not p.is_symlink()) == [path.name]


def test_a_linked_context_file_is_left_alone(home, tmp_path):
    kept = tmp_path / "dotfiles" / "cli.json"
    text = _write(kept, {"format": 1, "current": "dev", "contexts": {"dev": {"url": "http://127.0.0.1:8011"}}})
    path = _file(home)
    path.parent.mkdir(parents=True)
    path.symlink_to(kept)
    assert cli_context.write_app_context(path, 8010) == cli_context.KEPT_FOREIGN
    assert path.is_symlink() and kept.read_text(encoding="utf-8") == text


def test_the_file_follows_the_same_overrides_as_the_command(home, tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))
    assert contexts.config_path() == tmp_path / "xdg" / "roleband" / "cli.json"
    monkeypatch.setenv(cli_context.CONFIG_ENV, str(tmp_path / "chosen.json"))
    assert contexts.config_path() == tmp_path / "chosen.json"
    assert cli_context.context_file(os.environ, home) == contexts.config_path()


def test_a_named_file_is_found_without_a_home_folder(tmp_path, monkeypatch):
    """A command started with no HOME or USERPROFILE, as an agent host may start it, still
    reaches the file the environment names."""

    def no_home() -> Path:
        raise RuntimeError("Could not determine home directory.")

    monkeypatch.setattr(Path, "home", no_home)
    monkeypatch.setenv(cli_context.CONFIG_ENV, str(tmp_path / "chosen.json"))
    assert contexts.config_path() == tmp_path / "chosen.json"
    monkeypatch.delenv(cli_context.CONFIG_ENV)
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))
    assert contexts.config_path() == tmp_path / "xdg" / "roleband" / "cli.json"


# --------------------------------------------------------------------------- #
# The app's engine start
# --------------------------------------------------------------------------- #


def test_the_engine_start_names_its_own_port(home):
    assert prepare.write_app_context(home, 8123) == cli_context.WRITTEN
    assert contexts.resolve(None).url == "http://127.0.0.1:8123"


@pytest.mark.skipif(hasattr(os, "geteuid") and os.geteuid() == 0, reason="root writes through permissions")
def test_a_context_file_that_cannot_be_written_does_not_stop_the_engine(home):
    locked = home / ".config"
    locked.mkdir(mode=0o500)
    try:
        assert prepare.write_app_context(home, 8010) == "failed"
    finally:
        locked.chmod(0o755)
    assert not _file(home).exists()

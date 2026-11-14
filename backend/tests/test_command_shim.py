"""The `roleband` command an installed Mac app puts in `~/.local/bin`.

Every case uses a scratch home with its own `Applications` folder, so the person's real
`~/.local/bin` and apps are never read or written. The bundle's interpreter is a script that
prints the arguments it was given, so a case sees exactly what the shim runs.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

from tracker.platform import command_shim
from tracker.supervisor import prepare

pytestmark = pytest.mark.skipif(sys.platform == "win32", reason="the shim is a POSIX script for the Mac app")


def _bundle(folder: Path, name: str = "RoleBand.app") -> tuple[Path, Path]:
    app = folder / name
    python = app / "Contents/Resources/python/bin/python3.12"
    python.parent.mkdir(parents=True)
    python.write_text('#!/bin/sh\nfor argument in "$@"; do printf "%s\\n" "$argument"; done\n')
    python.chmod(0o755)
    entry = app / command_shim.ENTRY
    entry.parent.mkdir(parents=True)
    entry.write_text("")
    return app, python


@pytest.fixture
def home(tmp_path) -> Path:
    root = tmp_path / "home"
    (root / "Applications").mkdir(parents=True)
    return root


def _run(shim: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run([str(shim), *args], capture_output=True, text=True, timeout=10,
                          env={"PATH": "/usr/bin:/bin"})


def test_the_shim_runs_the_bundles_client_isolated_with_the_arguments_as_given(home):
    app, python = _bundle(home / "Applications", "Role Band's.app")
    assert command_shim.install(app, python, home) == command_shim.WRITTEN
    shim = command_shim.shim_path(home)
    assert os.access(shim, os.X_OK)
    result = _run(shim, "describe", "two words", "$HOME", "")
    assert result.returncode == 0, result.stderr
    assert result.stdout.split("\n")[:-1] == [
        "-I", "-B", str(app / command_shim.ENTRY), "client", "describe", "two words", "$HOME", "",
    ]


def test_a_second_install_leaves_the_file_as_it_is(home):
    app, python = _bundle(home / "Applications")
    command_shim.install(app, python, home)
    shim = command_shim.shim_path(home)
    before = shim.stat().st_mtime_ns
    assert command_shim.install(app, python, home) == command_shim.UNCHANGED
    assert shim.stat().st_mtime_ns == before


def test_a_moved_app_is_picked_up_at_its_next_start(home):
    first, python = _bundle(home / "Applications")
    command_shim.install(first, python, home)
    second, python = _bundle(home / "Applications", "RoleBand Copy.app")
    assert command_shim.install(second, python, home) == command_shim.WRITTEN
    assert str(second) in command_shim.shim_path(home).read_text()


def test_a_stale_shim_prints_one_line_and_exits_with_engine_unavailable(home):
    app, python = _bundle(home / "Applications")
    command_shim.install(app, python, home)
    app.rename(home / "elsewhere.app")
    result = _run(command_shim.shim_path(home), "status")
    assert result.returncode == command_shim.STALE_EXIT == 3
    assert result.stdout == ""
    lines = result.stderr.splitlines()
    assert len(lines) == 1, result.stderr
    assert "Open RoleBand once" in lines[0] and str(app) in lines[0]


@pytest.mark.parametrize("where", ["Volumes/RoleBand", "AppTranslocation/0A1B/d", "Downloads"])
def test_an_app_outside_applications_writes_nothing(home, tmp_path, where):
    app, python = _bundle(tmp_path / where)
    assert command_shim.install(app, python, home) == command_shim.NOT_INSTALLED
    assert not (home / ".local").exists()


def test_an_interpreter_outside_the_bundle_writes_nothing(home):
    app, _ = _bundle(home / "Applications")
    assert command_shim.install(app, Path(sys.executable), home) == command_shim.NOT_INSTALLED
    assert not (home / ".local").exists()


@pytest.mark.parametrize("kind", ["file", "link"])
def test_a_roleband_command_the_person_put_there_is_left_alone(home, tmp_path, kind):
    app, python = _bundle(home / "Applications")
    shim = command_shim.shim_path(home)
    shim.parent.mkdir(parents=True)
    if kind == "file":
        shim.write_text("#!/bin/sh\necho mine\n")
    else:
        own = tmp_path / "own-roleband"
        own.write_text("#!/bin/sh\necho mine\n")
        shim.symlink_to(own)
    before = shim.read_text()
    assert command_shim.install(app, python, home) == command_shim.KEPT_FOREIGN
    assert shim.read_text() == before
    assert shim.is_symlink() is (kind == "link")


def test_path_lookup_matches_the_folder_however_it_is_spelled(home):
    folder = home / ".local" / "bin"
    folder.mkdir(parents=True)
    assert command_shim.directory_on_path(folder, f"/usr/bin{os.pathsep}{folder}/")
    assert not command_shim.directory_on_path(folder, "/usr/bin:/bin")
    assert not command_shim.directory_on_path(folder, None)


# --------------------------------------------------------------------------- #
# The app's engine start
# --------------------------------------------------------------------------- #


def test_the_engine_start_writes_the_shim_for_its_own_bundle(home, monkeypatch):
    app, python = _bundle(home / "Applications")
    monkeypatch.setattr(prepare, "REPO_ROOT", app / "Contents" / "Resources")
    monkeypatch.setattr(sys, "executable", str(python))
    assert prepare.write_command_shim(home) == command_shim.WRITTEN
    assert f"app={app}" in command_shim.shim_path(home).read_text()


def test_an_engine_start_from_a_disk_image_writes_nothing(home, tmp_path, monkeypatch):
    app, python = _bundle(tmp_path / "Volumes" / "RoleBand")
    monkeypatch.setattr(prepare, "REPO_ROOT", app / "Contents" / "Resources")
    monkeypatch.setattr(sys, "executable", str(python))
    assert prepare.write_command_shim(home) == command_shim.NOT_INSTALLED
    assert not (home / ".local").exists()


@pytest.mark.skipif(hasattr(os, "geteuid") and os.geteuid() == 0, reason="root writes through permissions")
def test_a_shim_that_cannot_be_written_does_not_stop_the_engine(home, monkeypatch):
    app, python = _bundle(home / "Applications")
    monkeypatch.setattr(prepare, "REPO_ROOT", app / "Contents" / "Resources")
    monkeypatch.setattr(sys, "executable", str(python))
    locked = home / ".local"
    locked.mkdir(mode=0o500)
    try:
        assert prepare.write_command_shim(home) == "failed"
    finally:
        locked.chmod(0o755)
    assert not command_shim.shim_path(home).exists()

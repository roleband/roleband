"""A secret reaches disk only in a file whose ACL has already been checked private."""

from __future__ import annotations

import sys

import pytest

pytestmark = pytest.mark.skipif(sys.platform != "win32", reason="Windows private storage requires Windows")


def test_a_published_record_is_written_only_into_a_file_already_checked(tmp_path, monkeypatch):
    from tracker.platform import windows_private
    from tracker.platform.windows_fs import publish

    folder = tmp_path / "launcher"
    windows_private.private_directory(folder)
    real = windows_private.require_private
    sizes_when_checked = []

    def require_private(path):
        if path.name.startswith(".http-engine-"):
            sizes_when_checked.append(path.stat().st_size)
        return real(path)

    monkeypatch.setattr(windows_private, "require_private", require_private)
    publish(folder / "http-engine.json", b'{"secret": "00"}')

    assert sizes_when_checked == [0]
    assert (folder / "http-engine.json").read_bytes() == b'{"secret": "00"}'


def test_the_database_password_file_is_written_only_into_a_file_already_checked(tmp_path, monkeypatch):
    from tracker.platform import windows_db
    from tracker.platform.windows_private import private_directory

    folder = tmp_path / "db.auth"
    private_directory(folder)
    real = windows_db.require_private
    sizes_when_checked = []

    def require_private(path):
        sizes_when_checked.append(path.stat().st_size)
        return real(path)

    monkeypatch.setattr(windows_db, "require_private", require_private)
    windows_db._write(folder / "pgpass.conf", "127.0.0.1:*:*:postgres:secret\n")

    assert sizes_when_checked == [0]
    assert (folder / "pgpass.conf").read_text(encoding="utf-8") == "127.0.0.1:*:*:postgres:secret\n"

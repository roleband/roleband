"""Desktop notifications: the macOS notifier's argv, and the alert files the Windows app shows."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from tracker import osnotify
from tracker.osnotify import build_command

CONTRACT = json.loads(
    (Path(__file__).resolve().parents[2] / "launcher/windows/contracts/engine-alerts.json").read_text(encoding="utf-8")
)


def test_osascript_fallback_shape():
    cmd = build_command("RoleBand", "hi there", has_terminal_notifier=False)
    assert cmd == ["osascript", "-e", 'display notification "hi there" with title "RoleBand"']


def test_osascript_downgrades_double_quotes():
    # Embedded double quotes would break the AppleScript string literal; they
    # must be downgraded to single quotes.
    cmd = build_command('T"t', 'm"g', has_terminal_notifier=False)
    assert cmd == ["osascript", "-e", "display notification \"m'g\" with title \"T't\""]


def test_osascript_includes_subtitle():
    cmd = build_command("RoleBand", "body", subtitle="sub", has_terminal_notifier=False)
    assert cmd[2].endswith('subtitle "sub"')


def test_terminal_notifier_preferred_when_available():
    cmd = build_command("RoleBand", "body", subtitle="sub", has_terminal_notifier=True)
    assert cmd[0] == "terminal-notifier"
    assert "-subtitle" in cmd and "sub" in cmd


@pytest.fixture
def commands(monkeypatch) -> list[list[str]]:
    """Every notifier command started; none actually runs."""
    started: list[list[str]] = []
    monkeypatch.setattr(subprocess, "run", lambda cmd, **_: started.append(list(cmd)))
    return started


def _alerts(folder: Path) -> list[Path]:
    return sorted(entry for entry in folder.glob("*.json") if not entry.name.startswith("."))


def test_macos_still_posts_the_banner_itself(monkeypatch, commands, tmp_path):
    monkeypatch.setattr(sys, "platform", "darwin")
    monkeypatch.setenv(osnotify.ALERTS_ENV, str(tmp_path / "alerts"))
    monkeypatch.setattr(osnotify.shutil, "which", lambda _name: None)

    assert osnotify.notify("RoleBand", "The scan failed.")

    assert commands == [["osascript", "-e", 'display notification "The scan failed." with title "RoleBand"']]
    assert not (tmp_path / "alerts").exists(), "macOS never writes alert files"


def test_windows_hands_the_alert_to_the_app_and_starts_no_program(monkeypatch, commands, tmp_path):
    folder = tmp_path / "alerts"
    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setenv(CONTRACT["environment"], str(folder))

    assert osnotify.notify("RoleBand", "Scan \"failed\" <again> & é", subtitle="Today")

    assert commands == [], "no osascript, which Windows does not have"
    [alert] = _alerts(folder)
    record = json.loads(alert.read_text(encoding="utf-8"))
    assert set(record) == set(CONTRACT["example"])
    assert record["format"] == CONTRACT["format"]
    assert (record["title"], record["message"], record["subtitle"]) == ("RoleBand", "Scan \"failed\" <again> & é", "Today")
    assert record["created_at"].endswith("+00:00")
    assert not list(folder.glob(".*")), "no partial file is left behind"


def test_windows_alerts_of_one_clock_tick_all_arrive_in_order(monkeypatch, commands, tmp_path):
    """Windows' clock can read the same for every alert of one watchdog pass."""
    folder = tmp_path / "alerts"
    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setenv(osnotify.ALERTS_ENV, str(folder))
    monkeypatch.setattr(osnotify.time, "time_ns", lambda: 1_700_000_000_000_000_000)

    for message in ("first", "second", "third"):
        assert osnotify.notify("RoleBand", message)

    assert [json.loads(path.read_text(encoding="utf-8"))["message"] for path in _alerts(folder)] == [
        "first", "second", "third",
    ]


def test_a_windows_engine_no_app_started_shows_nothing_and_does_not_fail(monkeypatch, commands, tmp_path):
    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.delenv(osnotify.ALERTS_ENV, raising=False)
    monkeypatch.chdir(tmp_path)

    assert osnotify.notify("RoleBand", "The scan failed.") is False

    assert commands == []
    assert list(tmp_path.iterdir()) == []


def test_alerts_the_app_is_not_taking_stop_piling_up(monkeypatch, commands, tmp_path):
    folder = tmp_path / "alerts"
    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setenv(osnotify.ALERTS_ENV, str(folder))
    for _ in range(osnotify.MAX_PENDING_ALERTS):
        assert osnotify.notify("RoleBand", "waiting")

    assert osnotify.notify("RoleBand", "one too many") is False

    assert len(_alerts(folder)) == osnotify.MAX_PENDING_ALERTS
    assert all(json.loads(path.read_text(encoding="utf-8"))["message"] == "waiting" for path in _alerts(folder))


def test_a_folder_that_cannot_be_written_is_logged_not_raised(monkeypatch, commands, tmp_path):
    blocker = tmp_path / "alerts"
    blocker.write_text("a file where the folder should be", encoding="utf-8")
    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setenv(osnotify.ALERTS_ENV, str(blocker))

    assert osnotify.notify("RoleBand", "The scan failed.") is False

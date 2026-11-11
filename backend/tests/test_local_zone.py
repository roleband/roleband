"""One answer to "this machine's time zone", read the same way by every calendar.

The Board's and the statistics' "today" and the schedule plan's days read one
resolver: on a host whose `TZ` differs from `/etc/localtime` (a container, a
shell with `TZ` set) two resolvers would put "today" on two calendars.
"""

from __future__ import annotations

import shutil
import zoneinfo
from datetime import UTC, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from tracker.platform import local_zone as zone_module
from tracker.platform.local_zone import local_zone
from tracker.platform.util import local_day_start_utc

#: Fourteen hours ahead of UTC, so no machine this runs on shares its day.
FAR = "Pacific/Kiritimati"


def test_today_follows_the_zone_tz_names(monkeypatch):
    monkeypatch.setenv("TZ", FAR)
    now = datetime(2026, 10, 26, 11, 30, tzinfo=UTC)  # 01:30 on the 27th at UTC+14
    assert local_zone() == ZoneInfo(FAR)
    assert local_day_start_utc(now) == datetime(2026, 10, 26, 10, 0, tzinfo=UTC)

    monkeypatch.setenv("TZ", "UTC")
    assert local_day_start_utc(now) == datetime(2026, 10, 26, 0, 0, tzinfo=UTC), "read again, never cached"


def _zone_file(name: str) -> Path:
    for root in zoneinfo.TZPATH:
        candidate = Path(root) / name
        if candidate.is_file():
            return candidate
    pytest.skip(f"no zoneinfo file for {name} on this machine")


def test_a_copied_localtime_is_read_for_its_rules(monkeypatch, tmp_path):
    """A container copies the zone file instead of linking it: there is no name
    to read, but the rules are there, daylight saving included."""
    copied = tmp_path / "localtime"
    shutil.copyfile(_zone_file("Europe/Stockholm"), copied)
    monkeypatch.delenv("TZ", raising=False)
    monkeypatch.setattr(zone_module, "_LOCALTIME", copied)
    zone = local_zone()
    assert datetime(2026, 7, 1, 12, tzinfo=zone).utcoffset().total_seconds() == 7200
    assert datetime(2026, 12, 1, 12, tzinfo=zone).utcoffset().total_seconds() == 3600


def test_an_unreadable_machine_is_utc(monkeypatch, tmp_path):
    monkeypatch.setenv("TZ", "Not/AZone")
    monkeypatch.setattr(zone_module, "_LOCALTIME", tmp_path / "missing")
    assert local_zone() == ZoneInfo("UTC")


def test_the_zone_the_windows_host_names_is_read_after_tz(monkeypatch, tmp_path):
    """Windows keeps no IANA zone of its own; the host passes the one it converts."""
    monkeypatch.setattr(zone_module, "_LOCALTIME", tmp_path / "missing")
    monkeypatch.delenv("TZ", raising=False)
    monkeypatch.setenv(zone_module.WINDOWS_ZONE, FAR)
    assert local_zone() == ZoneInfo(FAR)
    monkeypatch.setenv("TZ", "UTC")
    assert local_zone() == ZoneInfo("UTC"), "TZ still overrides"
    monkeypatch.delenv("TZ")
    monkeypatch.setenv(zone_module.WINDOWS_ZONE, "Not/AZone")
    assert local_zone() == ZoneInfo("UTC")

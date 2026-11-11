"""Timeout time excludes suspend and is independent of wall-clock adjustments."""

from __future__ import annotations

import sys

import pytest

from tracker.supervisor import clock


def test_sleep_gap_does_not_advance_awake_time_and_is_reported_once():
    detector = clock.SleepDetector(wall=1000, awake=10)
    assert detector.slept(wall=1001, awake=11) == 0
    assert detector.slept(wall=1601, awake=11) == 600
    assert detector.slept(wall=1602, awake=12) == 0


def test_small_wall_clock_adjustment_does_not_report_suspend():
    detector = clock.SleepDetector(wall=1000, awake=10)
    assert detector.slept(wall=990, awake=11) == 0
    assert detector.slept(wall=1000, awake=12) == 0


@pytest.mark.skipif(sys.platform != "win32", reason="Windows process control requires Windows")
def test_native_awake_counter_uses_100_nanosecond_units(monkeypatch):
    import ctypes

    def query(pointer):
        ctypes.cast(pointer, ctypes.POINTER(ctypes.c_uint64)).contents.value = 123_456_789
        return 1

    monkeypatch.setattr(clock, "_query_awake", query)
    assert clock.awake_seconds() == pytest.approx(12.3456789)


@pytest.mark.skipif(sys.platform != "win32", reason="Windows process control requires Windows")
def test_native_awake_failure_does_not_fall_back_to_a_suspend_counting_clock(monkeypatch):
    monkeypatch.setattr(clock, "_query_awake", lambda _pointer: 0)
    with pytest.raises(OSError):
        clock.awake_seconds()


def test_real_awake_counter_is_monotonic():
    first = clock.awake_seconds()
    assert first >= 0
    assert clock.awake_seconds() >= first

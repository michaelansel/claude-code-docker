"""Tests for schedule and interval trigger helpers."""

import threading
import time
from datetime import timedelta

import pytest

from claude_docker import (
    _interval_trigger_thread,
    _parse_interval_duration,
    _schedule_trigger_thread,
    _validate_trigger,
)


# --- _parse_interval_duration ---

class TestParseIntervalDuration:
    def test_seconds(self):
        assert _parse_interval_duration("30s") == timedelta(seconds=30)

    def test_minutes(self):
        assert _parse_interval_duration("15m") == timedelta(minutes=15)

    def test_hours(self):
        assert _parse_interval_duration("4h") == timedelta(hours=4)

    def test_days(self):
        assert _parse_interval_duration("1d") == timedelta(days=1)

    def test_large_value(self):
        assert _parse_interval_duration("999s") == timedelta(seconds=999)

    def test_zero_raises(self):
        with pytest.raises(ValueError, match="value must be > 0"):
            _parse_interval_duration("0s")

    def test_empty_raises(self):
        with pytest.raises(ValueError):
            _parse_interval_duration("")

    def test_bad_unit_raises(self):
        with pytest.raises(ValueError):
            _parse_interval_duration("5x")

    def test_no_unit_raises(self):
        with pytest.raises(ValueError):
            _parse_interval_duration("100")

    def test_negative_raises(self):
        with pytest.raises(ValueError):
            _parse_interval_duration("-5s")

    def test_float_raises(self):
        with pytest.raises(ValueError):
            _parse_interval_duration("1.5h")


# --- _validate_trigger ---

class TestValidateTrigger:
    # schedule triggers
    def test_schedule_valid(self):
        assert _validate_trigger({"type": "schedule", "cron": "0 6 * * *", "timezone": "UTC"}) is None

    def test_schedule_valid_tz(self):
        assert _validate_trigger({"type": "schedule", "cron": "*/5 * * * *", "timezone": "America/Vancouver"}) is None

    def test_schedule_missing_cron(self):
        err = _validate_trigger({"type": "schedule", "timezone": "UTC"})
        assert err is not None
        assert "cron" in err

    def test_schedule_missing_timezone(self):
        err = _validate_trigger({"type": "schedule", "cron": "0 6 * * *"})
        assert err is not None
        assert "timezone" in err

    def test_schedule_invalid_timezone(self):
        err = _validate_trigger({"type": "schedule", "cron": "0 6 * * *", "timezone": "Not/AReal/Zone"})
        assert err is not None
        assert "timezone" in err

    # interval triggers
    def test_interval_valid(self):
        assert _validate_trigger({"type": "interval", "after": "4h"}) is None

    def test_interval_missing_after(self):
        err = _validate_trigger({"type": "interval"})
        assert err is not None
        assert "after" in err

    def test_interval_bad_duration(self):
        err = _validate_trigger({"type": "interval", "after": "bad"})
        assert err is not None

    def test_interval_zero_duration(self):
        err = _validate_trigger({"type": "interval", "after": "0m"})
        assert err is not None

    # script triggers
    def test_script_valid(self):
        assert _validate_trigger({"type": "script", "command": "python3 check.py"}) is None

    def test_script_missing_command(self):
        err = _validate_trigger({"type": "script"})
        assert err is not None
        assert "command" in err

    # c3po triggers
    def test_c3po_valid(self):
        assert _validate_trigger({"type": "c3po"}) is None

    # unknown type
    def test_unknown_type_no_error(self):
        assert _validate_trigger({"type": "unknown_future_type"}) is None


# --- _interval_trigger_thread ---

class TestIntervalTriggerThread:
    def test_fires_after_duration(self):
        done = threading.Event()
        stop = threading.Event()
        t = threading.Thread(
            target=_interval_trigger_thread,
            args=(timedelta(seconds=0.1), done, stop),
            daemon=True,
        )
        t.start()
        assert done.wait(timeout=2.0), "interval trigger did not fire"

    def test_respects_stop_event(self):
        done = threading.Event()
        stop = threading.Event()
        t = threading.Thread(
            target=_interval_trigger_thread,
            args=(timedelta(seconds=60), done, stop),
            daemon=True,
        )
        t.start()
        time.sleep(0.05)
        stop.set()
        t.join(timeout=3.0)
        assert not t.is_alive(), "interval trigger thread did not stop"
        assert not done.is_set(), "done should not be set after stop"


# --- _schedule_trigger_thread ---

class TestScheduleTriggerThread:
    def test_respects_stop_event(self):
        done = threading.Event()
        stop = threading.Event()
        t = threading.Thread(
            target=_schedule_trigger_thread,
            args=("0 3 * * *", "UTC", done, stop),
            daemon=True,
        )
        t.start()
        time.sleep(0.05)
        stop.set()
        t.join(timeout=3.0)
        assert not t.is_alive(), "schedule trigger thread did not stop"
        assert not done.is_set(), "done should not be set after stop"

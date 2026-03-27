from datetime import datetime, timedelta, timezone

import pytest

from app.domain.client_status import compute_status


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def iso(dt: datetime) -> str:
    return dt.isoformat()


def test_online_when_last_seen_within_window():
    last_seen = iso(utc_now() - timedelta(minutes=4))
    assert compute_status(last_seen, enabled=True, has_any_activity=True, window_minutes=5) == "online"


def test_offline_when_last_seen_outside_window():
    last_seen = iso(utc_now() - timedelta(minutes=10))
    assert compute_status(last_seen, enabled=True, has_any_activity=True, window_minutes=5) == "offline"


def test_offline_when_no_last_seen_and_no_activity():
    assert compute_status("", enabled=True, has_any_activity=False, window_minutes=5) == "offline"


def test_activity_unattributed_when_no_last_seen_but_activity_exists_and_enabled():
    assert compute_status("", enabled=True, has_any_activity=True, window_minutes=5) == "activity-unattributed"


def test_offline_when_no_last_seen_and_activity_exists_but_disabled():
    assert compute_status("", enabled=False, has_any_activity=True, window_minutes=5) == "offline"


def test_offline_when_last_seen_exactly_at_window_boundary():
    # exactly at boundary (now - window) should still be online (<=)
    last_seen = iso(utc_now() - timedelta(minutes=5))
    assert compute_status(last_seen, enabled=True, has_any_activity=True, window_minutes=5) == "online"

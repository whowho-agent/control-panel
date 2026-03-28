from datetime import datetime, timedelta, timezone

import pytest

from app.domain.activity_log import parse_activity_lines


def _ts(offset_seconds: int = 0) -> str:
    t = datetime.now(timezone.utc) - timedelta(seconds=offset_seconds)
    return t.strftime("%Y/%m/%d %H:%M:%S")


def _line(offset_seconds: int = 0, ip: str = "1.2.3.4", dest: str = "google.com:443", email: str = "alice", inbound: str = "frontend-in") -> str:
    return f"{_ts(offset_seconds)} from tcp:{ip}:12345 accepted tcp:{dest} [{inbound} -> to-relay] email: {email}"


def _since(minutes: int = 5) -> datetime:
    return datetime.now(timezone.utc) - timedelta(minutes=minutes)


def test_empty_input_returns_empty() -> None:
    assert parse_activity_lines([], _since()) == []


def test_non_frontend_in_lines_filtered_out() -> None:
    line = _line(inbound="some-other-inbound")
    assert parse_activity_lines([line], _since()) == []


def test_lines_older_than_since_filtered_out() -> None:
    old_line = _line(offset_seconds=400)  # 6+ minutes ago
    assert parse_activity_lines([old_line], _since(minutes=5)) == []


def test_recent_line_parsed_correctly() -> None:
    entries = parse_activity_lines([_line(offset_seconds=10, ip="5.5.5.5", dest="t.me:443", email="bob")], _since())
    assert len(entries) == 1
    assert entries[0].source_ip == "5.5.5.5"
    assert entries[0].destination == "t.me:443"
    assert entries[0].email == "bob"


def test_results_sorted_newest_first() -> None:
    lines = [_line(offset_seconds=60, email="old"), _line(offset_seconds=5, email="new")]
    entries = parse_activity_lines(lines, _since())
    assert entries[0].email == "new"
    assert entries[1].email == "old"


def test_limit_caps_output() -> None:
    lines = [_line(offset_seconds=i, email=f"user{i}") for i in range(10)]
    entries = parse_activity_lines(lines, _since(), limit=3)
    assert len(entries) == 3


def test_tcp_prefix_before_ip_handled() -> None:
    line = _line(offset_seconds=5)
    assert "tcp:" in line
    entries = parse_activity_lines([line], _since())
    assert len(entries) == 1
    assert entries[0].source_ip == "1.2.3.4"


def test_optional_milliseconds_handled() -> None:
    t = datetime.now(timezone.utc)
    line = f"{t.strftime('%Y/%m/%d %H:%M:%S.%f')} from 1.2.3.4:9999 accepted tcp:x.com:80 [frontend-in -> to-relay] email: x"
    entries = parse_activity_lines([line], _since())
    assert len(entries) == 1


def test_line_without_email_has_empty_email() -> None:
    ts = _ts(10)
    line = f"{ts} from 1.2.3.4:9999 accepted tcp:x.com:80 [frontend-in -> to-relay]"
    entries = parse_activity_lines([line], _since())
    assert len(entries) == 1
    assert entries[0].email == ""

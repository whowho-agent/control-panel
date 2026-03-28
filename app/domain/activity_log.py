import re
from dataclasses import dataclass
from datetime import datetime, timezone

_LINE_RE = re.compile(
    r"^(?P<ts>\d{4}/\d{2}/\d{2} \d{2}:\d{2}:\d{2}(?:\.\d+)?) "
    r"from (?:(?:tcp|udp):)?(?P<ip>[\d.]+):\d+ accepted (?:(?:tcp|udp):)?(?P<dest>\S+) \[(?P<inbound>[^\]]+) ->"
)
_EMAIL_RE = re.compile(r"email:\s+(\S+)")


@dataclass(slots=True, frozen=True)
class ActivityLogEntry:
    timestamp: datetime
    time_str: str
    source_ip: str
    destination: str
    email: str


def parse_activity_lines(lines: list[str], since: datetime, limit: int = 100) -> list[ActivityLogEntry]:
    """Parse access log lines, return entries since `since`, newest-first, capped at `limit`."""
    entries: list[ActivityLogEntry] = []
    for line in lines:
        match = _LINE_RE.search(line)
        if not match or match.group("inbound") != "frontend-in":
            continue
        ts_raw = match.group("ts")
        fmt = "%Y/%m/%d %H:%M:%S.%f" if "." in ts_raw else "%Y/%m/%d %H:%M:%S"
        ts = datetime.strptime(ts_raw, fmt).replace(tzinfo=timezone.utc)
        if ts < since:
            continue
        em = _EMAIL_RE.search(line)
        entries.append(ActivityLogEntry(
            timestamp=ts,
            time_str=ts.strftime("%H:%M:%S"),
            source_ip=match.group("ip"),
            destination=match.group("dest"),
            email=em.group(1) if em else "",
        ))
    entries.sort(key=lambda e: e.timestamp, reverse=True)
    return entries[:limit]

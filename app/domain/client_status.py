from datetime import datetime, timedelta, timezone


def compute_status(
    last_seen: str,
    enabled: bool,
    has_any_activity: bool,
    window_minutes: int,
) -> str:
    """Return 'online', 'offline', or 'activity-unattributed'."""
    if last_seen:
        seen_dt = datetime.fromisoformat(last_seen.replace("Z", "+00:00"))
        now = datetime.now(timezone.utc)
        if now - seen_dt <= timedelta(minutes=window_minutes):
            return "online"
        return "offline"
    if has_any_activity and enabled:
        return "activity-unattributed"
    return "offline"

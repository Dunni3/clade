"""Human-friendly timestamp formatting for mailbox messages."""

from datetime import datetime, timezone
from zoneinfo import ZoneInfo

# Default timezone for display. Hardcoded to America/New_York for now.
# Uses canonical IANA key (not legacy "US/Eastern" which is missing in some environments).
# See research_notes/ for the open problem of per-brother timezone support.
DEFAULT_TZ = "America/New_York"


def format_timestamp(
    utc_iso: str, tz_name: str = DEFAULT_TZ, now: datetime | None = None
) -> str:
    """Convert a UTC ISO timestamp to a human-friendly string.

    Examples:
        "Feb 8, 10:30 AM EST (5 min ago)"
        "Feb 7, 3:00 PM EST (1 day ago)"
        "Jan 30, 9:15 AM EST"  (older than 7 days — no relative time)

    Args:
        utc_iso: ISO 8601 UTC timestamp (e.g. "2026-02-08T15:30:00Z").
        tz_name: IANA timezone name for display (default: America/New_York).
        now: Override "now" for testing. Must be timezone-aware (UTC).
    """
    utc_dt = datetime.fromisoformat(utc_iso.replace("Z", "+00:00"))

    if now is None:
        now = datetime.now(timezone.utc)

    tz = ZoneInfo(tz_name)
    local_dt = utc_dt.astimezone(tz)

    # e.g. "EST" or "EDT"
    tz_abbrev = local_dt.strftime("%Z")
    # e.g. "Feb 8, 10:30 AM EST"
    time_str = local_dt.strftime("%b %-d, %-I:%M %p") + f" {tz_abbrev}"

    # Relative time
    delta = now - utc_dt
    total_seconds = int(delta.total_seconds())

    if total_seconds < 0:
        relative = "in the future"
    elif total_seconds < 60:
        relative = "just now"
    elif total_seconds < 3600:
        mins = total_seconds // 60
        relative = f"{mins} min ago"
    elif total_seconds < 86400:
        hours = total_seconds // 3600
        relative = f"{hours} hr ago"
    elif total_seconds < 604800:  # 7 days
        days = total_seconds // 86400
        relative = f"{days} day{'s' if days != 1 else ''} ago"
    else:
        relative = None

    if relative:
        return f"{time_str} ({relative})"
    return time_str

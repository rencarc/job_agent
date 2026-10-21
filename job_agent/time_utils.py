"""Explicit UTC instants; naive upstream timestamps use the source's timezone."""
from datetime import datetime, timezone
from zoneinfo import ZoneInfo


def utc_datetime(value: str, *, naive_zone: str = "UTC") -> datetime:
    result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if result.tzinfo is None:
        result = result.replace(tzinfo=timezone.utc if naive_zone == "UTC" else ZoneInfo(naive_zone))
    return result.astimezone(timezone.utc)


def is_recent(value: str, cutoff: str | None) -> bool:
    # Unknown publication dates are retained, with explicit metadata for review.
    if not cutoff or not value:
        return True
    return utc_datetime(value) >= utc_datetime(cutoff)

"""Time (NFR-8): UTC inside, ISO 8601 text. Showing local time with the zone name is the UI's job."""

from datetime import UTC, datetime


def utc_now() -> datetime:
    """The current time as an aware UTC datetime."""
    return datetime.now(UTC)


def to_iso(dt: datetime) -> str:
    """Format an aware datetime as `YYYY-MM-DDTHH:MM:SS.ffffffZ` (UTC).

    Always six fractional digits, so the text has a fixed width and sorts the same as the time does.
    Naive datetimes are refused: their zone is unknown, so any answer would be a guess.
    """
    if dt.tzinfo is None or dt.utcoffset() is None:
        raise ValueError("naive datetime refused: pass a timezone-aware datetime")
    return dt.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%S.%fZ")

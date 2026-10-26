"""NFR-8: UTC inside, naive datetimes refused."""

from datetime import UTC, datetime, timedelta, timezone

import pytest

from shelfsync.clock import to_iso, utc_now


def test_to_iso_gives_utc_with_z_and_microseconds() -> None:
    assert to_iso(datetime(2026, 10, 26, 9, 5, 3, 120, tzinfo=UTC)) == "2026-10-26T09:05:03.000120Z"


def test_to_iso_converts_other_zones_to_utc() -> None:
    plus_two = timezone(timedelta(hours=2))
    assert to_iso(datetime(2026, 10, 26, 11, 0, 0, tzinfo=plus_two)) == "2026-10-26T09:00:00.000000Z"


def test_to_iso_refuses_naive_datetimes() -> None:
    with pytest.raises(ValueError, match="naive"):
        to_iso(datetime(2026, 10, 26, 9, 0, 0))


def test_utc_now_is_aware_utc() -> None:
    now = utc_now()
    assert now.utcoffset() == timedelta(0)
    assert to_iso(now).endswith("Z")

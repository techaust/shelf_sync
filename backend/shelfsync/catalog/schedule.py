"""When the scheduled reads are due (SYNC-01, SYNC-03), and the same-night retry rule. Pure: no database, no clock.

**The snapshot's night.** The snapshot runs at `snapshot_time`, Windows local time (the `db/daily.py` pattern: the
local wall time turned into UTC through `LocalTime`, so a daylight-saving change neither skips nor repeats a night).
The night is the local date of the latest `snapshot_time` at or before now. A store's night is due when it has no row
yet, when it waits for a retry whose time has come, or when an attempt was left `running` (the app ended during it).
A PC off or asleep at that time catches up at the next check after it starts or wakes; a sleep across several nights
catches up the latest one only.

**The same-night retry (Lead (proposed), m3.2; L1: PluginWay stalled for about an hour one evening):** an attempt that
failed is tried again 30 minutes later, at most 3 attempts a night, unless waiting can't change its reason (the store's
state, its keys, its version, the snapshot's limits) or the store is auto-paused (the failure that paused it is
counted first, in the same transaction, `db.snapshots.record_failed`).
An attempt stopped by the app's shutdown is due again at the next start. One store's failure never holds up
another's: each store's night is its own.

**APL-12** (the owner, 11 2026-11-18) counts failed **reads**: each snapshot attempt that fails counts once, as an
incremental or a full read does (`db.catalog.count_failed_read`); 10 in a row auto-pause the store. A slow evening
of a few failed reads recovers on its own at the next read that works.

**A wrong clock (F6):** a last incremental, or the scheduler's start, later than now (the clock went back) makes the
incremental due now, so a clock moved back never holds the incrementals off.
"""

from dataclasses import dataclass
from datetime import datetime, timedelta

from shelfsync.db.daily import LocalTime

RETRY_AFTER = timedelta(minutes=30)
DEFER_AFTER = timedelta(minutes=5)
ATTEMPTS_MAX = 3
# Reasons waiting can't change: no retry the same night (the store's state, its keys, its version, the snapshot's
# limits, an address that moved, a night already done).
NOT_RETRIED = frozenset(
    {
        "paused",
        "auto_paused",
        "store_removed",
        "address_changed",
        "keys_missing",
        "keys_refused",
        "forbidden",
        "wc_too_old",
        "too_many_pages",
        "too_many_variable",
        "trash_unlisted",
        "snapshot_too_large",
        "no_catalog",
        "night_done",
        "interrupted",
    }
)


@dataclass(frozen=True)
class SnapshotTime:
    hour: int
    minute: int

    def __post_init__(self) -> None:
        if not (0 <= self.hour <= 23 and 0 <= self.minute <= 59):
            raise ValueError("a snapshot time is 00:00 to 23:59")


def latest_slot(now: datetime, local: LocalTime, at: SnapshotTime) -> datetime:
    """The latest `at` local time at or before `now` (aware), in UTC."""
    wall = local.to_local(now).replace(hour=at.hour, minute=at.minute, second=0, microsecond=0)
    slot = local.to_utc(wall)
    if slot > now:
        slot = local.to_utc(wall - timedelta(days=1))
    return slot


def next_slot(now: datetime, local: LocalTime, at: SnapshotTime) -> datetime:
    """The first `at` local time after `now`, in UTC."""
    wall = local.to_local(latest_slot(now, local, at)).replace(hour=at.hour, minute=at.minute, second=0, microsecond=0)
    return local.to_utc(wall + timedelta(days=1))


def night_of(now: datetime, local: LocalTime, at: SnapshotTime) -> str:
    """The night `now` belongs to: the local date of the latest snapshot time, `YYYY-MM-DD`."""
    return local.to_local(latest_slot(now, local, at)).date().isoformat()


def night_due(
    state: str | None,
    next_try_at: str | None,
    now_iso: str,
    started_at: str | None = None,
    slot_iso: str | None = None,
) -> bool:
    """Whether a store's night is due, from its row (`state` None: no row yet). Times are `clock.to_iso` texts. An
    `ok` night that started before the night's latest slot (`snapshot_time` was moved later the same day) is due
    again (review 2)."""
    if state is None or state == "running":
        return True
    if state == "retry":
        return next_try_at is None or next_try_at <= now_iso
    if state == "ok" and started_at is not None and slot_iso is not None:
        return started_at < slot_iso
    return False


def retry_at(reason: str, attempt: int, finished: datetime, *, auto_paused: bool) -> datetime | None:
    """When a failed attempt's night is tried again: 30 minutes later; at once for an attempt the app's shutdown
    stopped (it is due at the next start, and doesn't use one of the night's attempts: review 1); None when the night
    is over (`failed`)."""
    if auto_paused or reason in NOT_RETRIED:
        return None
    if reason == "stopped":
        return finished
    if attempt >= ATTEMPTS_MAX:
        return None
    return finished + RETRY_AFTER


def deferred_until(at: datetime) -> datetime:
    """Review 1 (Lead (proposed)): a night that couldn't start an attempt (the store's slot was busy, the database
    failed before the attempt) is tried again this long after, without using an attempt, so the scheduler doesn't
    pick it at every 60-second check and hold off the incrementals."""
    return at + DEFER_AFTER


def incremental_due(now: datetime, since: datetime, last_started: datetime | None, interval_minutes: int) -> datetime:
    """When the next scheduled incremental is due: one interval after the last one started (any incremental, Sync now
    included), or after the scheduler started when none has since. Either later than `now` (the clock went back):
    due now (F6)."""
    if since > now or (last_started is not None and last_started > now):
        return now
    base = since if last_started is None or last_started < since else last_started
    return base + timedelta(minutes=interval_minutes)

"""The daily database backup and its retention (BAK-01).

**When.** At 02:00 Windows local time. A run that was missed (the PC was off or asleep) is caught up at the next start
or wake: the loop looks at the wall clock every 60 seconds, so a sleep is noticed within a minute. "Due" means the
newest daily backup is older than the latest 02:00 that has passed; the newest backup's time comes from its file
name, so no state is stored. A database with no daily backup yet is due at once.

**What.** `backups\\daily-YYYYMMDDTHHMMSSZ.db` (UTC in the name): an online backup (the sqlite3 backup API) on the
scheduler's own connection into `....db.part`, then `journal_mode=DELETE` and `integrity_check` (`write_checked_copy`,
shared with the pre-migration backup), then one `os.replace`. A `.part` left by a crash is removed at the next start.
A failure is logged (the error type only) and tried again at the next due time or the next start; the app keeps
running.

**Retention.** Only a plain file (never a link, never a file with several names) whose name is exactly
`daily-<UTC stamp>.db` is ever deleted, and only the oldest ones beyond the newest `db_backups_kept`. It runs only after
a new backup passed its check (a failed backup prunes nothing), and at once when the setting is lowered.
`pre-migration-*`, `pre-rollback-*` and the file `update\\state.json` names are never touched, whatever their names.
"""

import contextlib
import json
import logging
import os
import re
import sqlite3
import threading
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path

from shelfsync.clock import utc_now
from shelfsync.db.backup import DAILY_PREFIX, BackupError, write_checked_copy
from shelfsync.db.migrate import applied_versions
from shelfsync.db.settings import BACKUPS_KEPT_MAX, BACKUPS_KEPT_MIN, DEFAULTS, get_setting
from shelfsync.paths import DataPaths, is_plain_file, remove_entry
from shelfsync.update.layout import UpdatePaths
from shelfsync.update.state import MAX_STATE_BYTES, StateError, state_from_json

_log = logging.getLogger("shelfsync.db")

DUE_HOUR = 2  # 02:00 Windows local time
CHECK_SECONDS = 60.0  # the loop's wall-clock check, so a sleep is noticed within a minute
STOP_WAIT_SECONDS = 2.0  # how long a stop waits for a backup that is running

STAMP_FORMAT = "%Y%m%dT%H%M%SZ"
_DAILY_NAME = re.compile(r"^daily-(\d{8}T\d{6}Z)\.db$")
_DAILY_PART = re.compile(r"^daily-\d{8}T\d{6}Z\.db\.part(-journal|-wal|-shm)?$")  # and SQLite's side files
FUTURE_MARGIN = timedelta(days=1)  # a daily stamp later than now + this is a wrong clock's, not a backup made


def daily_name(moment: datetime) -> str:
    return f"{DAILY_PREFIX}{moment.astimezone(UTC).strftime(STAMP_FORMAT)}.db"


def name_time(name: str) -> datetime | None:
    """The UTC time in a daily backup's file name, or None if the name isn't exactly a daily backup's."""
    match = _DAILY_NAME.fullmatch(name)
    if match is None:
        return None
    try:
        return datetime.strptime(match.group(1), STAMP_FORMAT).replace(tzinfo=UTC)
    except ValueError:  # a date that doesn't exist: not one of ours
        return None


@dataclass(frozen=True)
class LocalTime:
    """Windows local time. `to_local` turns an aware UTC time into a naive local one; `to_utc` turns a naive local time
    into aware UTC. The defaults use the system zone through `astimezone()` (`tzdata` isn't locked, so no `zoneinfo`);
    tests pass a fake zone to move the clock across a daylight-saving change."""

    to_local: Callable[[datetime], datetime] = lambda moment: moment.astimezone().replace(tzinfo=None)
    to_utc: Callable[[datetime], datetime] = lambda naive: naive.astimezone().astimezone(UTC)


def latest_slot(now: datetime, local: LocalTime) -> datetime:
    """The most recent 02:00 local time at or before `now`, in UTC."""
    wall = local.to_local(now).replace(hour=DUE_HOUR, minute=0, second=0, microsecond=0)
    slot = local.to_utc(wall)
    if slot > now:
        slot = local.to_utc(wall - timedelta(days=1))
    return slot


def next_slot(now: datetime, local: LocalTime) -> datetime:
    """The first 02:00 local time after `now`, in UTC."""
    wall = local.to_local(latest_slot(now, local)).replace(hour=DUE_HOUR, minute=0, second=0, microsecond=0)
    return local.to_utc(wall + timedelta(days=1))


def daily_backups(paths: DataPaths) -> list[tuple[datetime, Path]]:
    """Every daily backup in backups\\ (plain files with an exact daily name), oldest first."""
    found: list[tuple[datetime, Path]] = []
    try:
        entries = list(paths.backups.iterdir())
    except OSError:
        return []
    for entry in entries:
        moment = name_time(entry.name)
        if moment is not None and is_plain_file(entry):
            found.append((moment, entry))
    found.sort(key=lambda item: (item[0], item[1].name))
    return found


def _protected(paths: DataPaths) -> set[Path]:
    """The file `update\\state.json` names (the backup a kept version still needs), by path and resolved path. A
    read-only look: nothing is set aside, removed or logged by the updater's loader; a missing, large, malformed or
    linked file protects nothing extra (a daily name can't be a pre-migration path anyway)."""
    protected: set[Path] = set()
    path = UpdatePaths(paths).state_json
    try:
        if not is_plain_file(path):
            return protected
        with path.open("rb") as handle:
            raw = handle.read(MAX_STATE_BYTES + 1)
        if len(raw) > MAX_STATE_BYTES:
            return protected
        record = state_from_json(json.loads(raw.decode("utf-8"))).backup
    except OSError, ValueError, StateError:
        return protected
    if record is not None:
        named = Path(record.path)
        protected.add(named)
        with contextlib.suppress(OSError):
            protected.add(named.resolve())
    return protected


def is_wrong_clock(moment: datetime, now: datetime) -> bool:
    """A stamp later than now plus a day: written by a wrong clock, so it is no backup made, and never outranks a real
    one."""
    return moment > now + FUTURE_MARGIN


def prune(paths: DataPaths, keep: int, now: datetime | None = None) -> list[str]:
    """Delete the daily backups beyond the newest `keep` (see the module text). Wrong-clock stamps (`is_wrong_clock`)
    rank as the oldest, so they go first and never push out a real backup. Returns the names deleted. One that can't
    be deleted is logged and skipped."""
    keep = max(keep, BACKUPS_KEPT_MIN)
    moment_now = now if now is not None else utc_now()
    found = sorted(
        daily_backups(paths), key=lambda item: (not is_wrong_clock(item[0], moment_now), item[0], item[1].name)
    )
    protected = _protected(paths)
    removed: list[str] = []
    for _, entry in found[: max(len(found) - keep, 0)]:
        try:
            if entry in protected or entry.resolve() in protected or not is_plain_file(entry):
                continue
            remove_entry(entry)
        except OSError as error:
            _log.warning("A daily backup beyond the number kept couldn't be removed: %s", type(error).__name__)
            continue
        removed.append(entry.name)
    if removed:
        _log.info("%d old daily backup(s) removed; the newest %d are kept", len(removed), keep)
    return removed


def kept_setting(connection: sqlite3.Connection) -> int:
    """`db_backups_kept`, or the default if the stored value is out of range, not a number or not even JSON."""
    try:
        value = get_setting(connection, "db_backups_kept")
    except ValueError:
        _log.warning("The stored setting 'db_backups_kept' isn't valid; the default is used")
        return int(DEFAULTS["db_backups_kept"])
    if type(value) is int and BACKUPS_KEPT_MIN <= value <= BACKUPS_KEPT_MAX:
        return value
    return int(DEFAULTS["db_backups_kept"])


class DailyBackups:
    """The scheduler. `connect` opens a connection to the database (one per run, closed after: the scheduler's own).
    `now` and `local` are replaceable for tests; `interval` is the wall-clock check (60 s)."""

    def __init__(
        self,
        paths: DataPaths,
        connect: Callable[[], sqlite3.Connection],
        now: Callable[[], datetime] = utc_now,
        local: LocalTime | None = None,
        interval: float = CHECK_SECONDS,
    ) -> None:
        self._paths = paths
        self._connect = connect
        self._now = now
        self._local = local if local is not None else LocalTime()
        self._interval = interval
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._lock = threading.Lock()  # one backup or prune at a time
        self._failed_slot: datetime | None = None  # the slot a failed run was for: retried at the next one

    @property
    def paths(self) -> DataPaths:
        return self._paths

    # ---- what is due ----------------------------------------------------------------------------------------------

    def last_backup(self) -> tuple[datetime, Path] | None:
        """The newest real daily backup (a wrong-clock stamp doesn't count)."""
        now = self._now()
        found = [item for item in daily_backups(self._paths) if not is_wrong_clock(item[0], now)]
        return found[-1] if found else None

    def is_due(self) -> bool:
        now = self._now()
        slot = latest_slot(now, self._local)
        if self._failed_slot == slot:
            return False  # tried for this slot and failed: the next slot (or the next start) tries again
        last = self.last_backup()
        return last is None or last[0] < slot

    def next_run(self) -> datetime:
        """When the next backup will be made: now if one is due, otherwise the next 02:00 local time."""
        now = self._now()
        return now if self.is_due() else next_slot(now, self._local)

    # ---- running --------------------------------------------------------------------------------------------------

    def run_once(self) -> bool:
        """Make one backup now, then prune. True if it was made and checked; False if it failed (logged, retried at the
        next due time). Never raises for a failed backup."""
        with self._lock:
            moment = self._now()
            slot = latest_slot(moment, self._local)
            final = self._paths.backups / daily_name(moment)
            part = final.with_name(final.name + ".part")
            made = False
            try:
                self._paths.backups.mkdir(parents=True, exist_ok=True)
                connection = self._connect()
                try:
                    kept = kept_setting(connection)  # before the copy: a bad stored value can't leave a .part behind
                    versions = applied_versions(connection)
                    if not versions:
                        raise BackupError("backup_failed")
                    write_checked_copy(connection, part, max(versions))
                finally:
                    connection.close()
                os.replace(part, final)
                made = True
                with contextlib.suppress(Exception):  # the setting may have been lowered while the copy ran
                    again = self._connect()
                    try:
                        kept = kept_setting(again)
                    finally:
                        again.close()
            except Exception as error:  # whatever it was, it is logged, the slot is remembered and no .part stays
                _log.error(
                    "The daily database backup failed (%s); it will be tried again at the next due time", _why(error)
                )
                self._failed_slot = slot
                return False
            finally:
                if not made:
                    for leftover in _part_files(part):
                        with contextlib.suppress(OSError):
                            leftover.unlink(missing_ok=True)
            self._failed_slot = None
            _log.info("The daily database backup was made")
            try:
                prune(self._paths, kept, moment)  # only now: the new backup passed its check
            except Exception as error:  # a retention problem never fails or stops the backup
                _log.warning("Pruning old daily backups failed: %s", type(error).__name__)
            return True

    def prune_now(self) -> list[str]:
        """Apply the kept number at once (the setting was lowered): removes the oldest daily backups beyond the newest
        `db_backups_kept`. Returns the names removed."""
        if not self._lock.acquire(blocking=False):
            return []  # a backup is running: it prunes when it is done, so a save never waits on it
        try:
            connection = self._connect()
            try:
                kept = kept_setting(connection)
            finally:
                connection.close()
            return prune(self._paths, kept, self._now())
        finally:
            self._lock.release()

    # ---- start and stop -------------------------------------------------------------------------------------------

    def clean_parts(self) -> None:
        """Remove `daily-*.db.part` (and its `-journal`, `-wal`, `-shm`) left by a crash."""
        try:
            entries = list(self._paths.backups.iterdir())
        except OSError:
            return
        for entry in entries:
            if _DAILY_PART.fullmatch(entry.name):
                try:
                    remove_entry(entry)
                except OSError as error:
                    _log.warning("A leftover partial backup couldn't be removed: %s", type(error).__name__)

    def start(self) -> None:
        if self._thread is not None and self._thread.is_alive():
            self._stop.clear()  # a stop that timed out is called off: the old loop keeps running
            return  # the previous loop is still winding down: no second one beside it
        self.clean_parts()
        self._stop.clear()
        self._thread = threading.Thread(target=self._loop, name="daily-backup", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        """Ask the loop to end and wait a bounded time. A backup that is still running is left to finish on its own
        daemon thread; its `.part` is cleaned at the next start if the process ends first."""
        self._stop.set()
        thread = self._thread
        if thread is not None:
            thread.join(timeout=STOP_WAIT_SECONDS)

    def _loop(self) -> None:
        while True:
            try:
                if self.is_due():
                    self.run_once()
            except Exception as error:  # nothing here may stop the schedule or the app
                _log.warning("The daily backup check failed: %s", type(error).__name__)
            if self._stop.wait(self._interval):
                return


def _part_files(part: Path) -> list[Path]:
    """The `.part` and the side files SQLite may have made beside it."""
    return [part, *(part.with_name(part.name + suffix) for suffix in ("-journal", "-wal", "-shm"))]


def _why(error: Exception) -> str:
    return error.code if isinstance(error, BackupError) else type(error).__name__

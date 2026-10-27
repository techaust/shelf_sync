"""The Settings > Backup keep settings and the daily backup's state (BAK-01, SET-05).

Behind the guard in `secure/middleware.py` (a session, and Origin plus `X-ShelfSync: 1` for the PUT). A wrong shape is
the fixed 422 `invalid_request` that never echoes the request.

    GET  /api/settings/backup   the two settings, the newest daily backup (time and size), the next run and the count
    PUT  /api/settings/backup   both settings (all required, unknown fields refused); answers what was saved

Lowering `db_backups_kept` removes the surplus daily backups at once (`DailyBackups.prune_now`).
`snapshot_retention_days` is only stored for now: the catalog snapshots it governs arrive in M3. Times are UTC ISO
8601; the screen shows them in Windows local time with the zone name.
"""

import sqlite3
import threading
import uuid
import weakref
from collections.abc import Callable

from fastapi import APIRouter
from pydantic import BaseModel, ConfigDict, Field, StrictInt

from shelfsync.api.app_settings import stored_values, validators_for
from shelfsync.api.errors import ErrorResponse
from shelfsync.clock import to_iso
from shelfsync.db.daily import DailyBackups, daily_backups
from shelfsync.db.migrate import migrate
from shelfsync.db.settings import (
    BACKUPS_KEPT_MAX,
    BACKUPS_KEPT_MIN,
    SNAPSHOT_DAYS_MAX,
    SNAPSHOT_DAYS_MIN,
    set_setting,
)

BACKUP_SETTINGS_PATH = "/api/settings/backup"
_KEYS = ("db_backups_kept", "snapshot_retention_days")


class BackupSettingsValues(BaseModel):
    """The two settings. Strict types, so `true` is never a count and `"7"` is never a number of days."""

    model_config = ConfigDict(extra="forbid")
    db_backups_kept: StrictInt = Field(ge=BACKUPS_KEPT_MIN, le=BACKUPS_KEPT_MAX)
    snapshot_retention_days: StrictInt = Field(ge=SNAPSHOT_DAYS_MIN, le=SNAPSHOT_DAYS_MAX)


class BackupSettingsResponse(BackupSettingsValues):
    last_backup_at: str | None  # UTC ISO 8601; None before the first daily backup
    last_backup_bytes: int | None
    next_backup_at: str | None  # UTC ISO 8601: now if one is due, else the next 02:00 local time; None with no schedule
    daily_count: int  # daily backups in backups\


_VALIDATORS = validators_for(BackupSettingsValues)


class BackupSettingsService:
    """What the routes and the app's lifespan talk to. `connect` opens a connection to the database (one per call,
    closed after). `daily` is the scheduler (None: no schedule, as in tests and a copy with no data folder)."""

    def __init__(self, connect: Callable[[], sqlite3.Connection], daily: DailyBackups | None = None) -> None:
        self._connect = connect
        self._daily = daily
        self._lock = threading.Lock()  # one save at a time
        self._keeper: sqlite3.Connection | None = None  # holds a development database's memory open

    @classmethod
    def development(cls) -> BackupSettingsService:
        """Settings in memory and no schedule: no test reaches a file by accident."""
        uri = f"file:shelfsync-backup-settings-{uuid.uuid4().hex}?mode=memory&cache=shared"

        def connect() -> sqlite3.Connection:
            return sqlite3.connect(uri, uri=True, isolation_level=None, check_same_thread=False)

        keeper = connect()
        migrate(keeper)
        service = cls(connect)
        service._keeper = keeper
        weakref.finalize(service, keeper.close)
        return service

    def start(self) -> None:
        if self._daily is not None:
            self._daily.start()

    def stop(self) -> None:
        if self._daily is not None:
            self._daily.stop()

    def read(self) -> BackupSettingsResponse:
        connection = self._connect()
        try:
            values = stored_values(connection, _VALIDATORS, _KEYS)
        finally:
            connection.close()
        daily = self._daily
        if daily is None:
            return BackupSettingsResponse(
                **values, last_backup_at=None, last_backup_bytes=None, next_backup_at=None, daily_count=0
            )
        found = daily_backups(daily.paths)
        last_at: str | None = None
        last_bytes: int | None = None
        if found:
            moment, path = found[-1]
            last_at = to_iso(moment)
            try:
                last_bytes = path.stat().st_size
            except OSError:
                last_bytes = None
        return BackupSettingsResponse(
            **values,
            last_backup_at=last_at,
            last_backup_bytes=last_bytes,
            next_backup_at=to_iso(daily.next_run()),
            daily_count=len(found),
        )

    def save(self, new: BackupSettingsValues) -> BackupSettingsValues:
        with self._lock:
            connection = self._connect()
            try:
                connection.execute("BEGIN IMMEDIATE")  # both or none
                try:
                    before = stored_values(connection, _VALIDATORS, _KEYS)
                    for key in _KEYS:
                        set_setting(connection, key, getattr(new, key))
                    connection.execute("COMMIT")
                except BaseException:
                    connection.execute("ROLLBACK")
                    raise
            finally:
                connection.close()
            if self._daily is not None and new.db_backups_kept < before["db_backups_kept"]:
                self._daily.prune_now()  # lowered: the surplus goes at once
            return BackupSettingsValues(**new.model_dump())


def make_backup_settings_router(service: BackupSettingsService) -> APIRouter:
    router = APIRouter()

    @router.get(BACKUP_SETTINGS_PATH, response_model=BackupSettingsResponse)
    def get_backup_settings() -> BackupSettingsResponse:
        return service.read()

    @router.put(
        BACKUP_SETTINGS_PATH,
        response_model=BackupSettingsValues,
        responses={422: {"model": ErrorResponse}},
    )
    def put_backup_settings(body: BackupSettingsValues) -> BackupSettingsValues:
        return service.save(body)

    return router

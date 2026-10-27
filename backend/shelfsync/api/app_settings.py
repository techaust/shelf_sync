"""The Settings > App API (SET-06, LOG-01): port, theme, Start with Windows, notifications, log retention.

Behind the guard in `secure/middleware.py` (a session, and Origin plus `X-ShelfSync: 1` for the PUT), so neither route
needs its own check. A wrong shape is the fixed 422 `invalid_request` that never echoes the request.

    GET  /api/settings/app   the five settings and `installed` (whether this copy is the installed one)
    PUT  /api/settings/app   all five, unknown fields refused; answers what was saved and what the save did

What a save does at once: Start with Windows is applied (an installed copy writes or removes the Run value; a failure
is a 200 with `start_with_windows_applied: false`, never a 500); the log retention is applied to the running handler
and the old log files are pruned. The port takes effect at the next start (`restart_needed`). Notifications are only
saved: nothing reads the setting before M5 (SYS-05).
"""

import logging
import sqlite3
import uuid
import weakref
from collections.abc import Callable
from dataclasses import dataclass
from logging.handlers import TimedRotatingFileHandler
from typing import Literal

from fastapi import APIRouter
from pydantic import BaseModel, ConfigDict, Field, StrictBool, StrictInt

from shelfsync.api.errors import ErrorResponse
from shelfsync.db.migrate import migrate
from shelfsync.db.settings import get_setting, set_setting
from shelfsync.logs import set_log_retention
from shelfsync.platform.autostart import AutostartError, FakeRunKey, RunKey, apply_start_with_windows, is_installed_copy
from shelfsync.ports import DEFAULT_PORT, LAST_PORT

_log = logging.getLogger("shelfsync.api.settings")

APP_SETTINGS_PATH = "/api/settings/app"
MAX_LOG_RETENTION_DAYS = 365

Theme = Literal["system", "light", "dark"]
_KEYS = ("port", "theme", "start_with_windows", "notifications", "log_retention_days")


class AppSettingsValues(BaseModel):
    """The five settings. Strict types, so `true` is never a port and `"30"` is never a number of days."""

    model_config = ConfigDict(extra="forbid")
    port: StrictInt = Field(ge=DEFAULT_PORT, le=LAST_PORT)
    theme: Theme
    start_with_windows: StrictBool
    notifications: StrictBool
    log_retention_days: StrictInt = Field(ge=1, le=MAX_LOG_RETENTION_DAYS)


class AppSettingsResponse(AppSettingsValues):
    installed: bool  # this copy is the installed one (a development copy never writes the Run key)


class AppSettingsSaved(AppSettingsValues):
    restart_needed: bool  # the port changed: it takes effect at the next start
    start_with_windows_applied: bool  # false: the Run value couldn't be written or removed


@dataclass(frozen=True)
class SaveOutcome:
    values: AppSettingsValues
    restart_needed: bool
    start_with_windows_applied: bool


class AppSettingsService:
    """What the routes talk to: reads and saves through `db/settings.py` and applies what a save decides at once.

    `connect` opens a connection to the database (one per call, closed after). `handler` is the running log handler
    (None: nothing to update). `run_key` and `installed` are replaceable for tests; by default the real Run key is
    used and `is_installed_copy()` decides whether it is written."""

    def __init__(
        self,
        connect: Callable[[], sqlite3.Connection],
        handler: TimedRotatingFileHandler | None = None,
        run_key: RunKey | None = None,
        installed: Callable[[], bool] = is_installed_copy,
    ) -> None:
        self._connect = connect
        self._handler = handler
        self._run_key = run_key
        self._installed = installed
        self._keeper: sqlite3.Connection | None = None  # holds a development database's memory open

    @classmethod
    def development(cls) -> AppSettingsService:
        """The default for tests and a copy with no database behind it: settings in memory, no log handler and a Run key
        that is never the real one."""
        uri = f"file:shelfsync-settings-{uuid.uuid4().hex}?mode=memory&cache=shared"

        def connect() -> sqlite3.Connection:
            return sqlite3.connect(uri, uri=True, isolation_level=None, check_same_thread=False)

        keeper = connect()
        migrate(keeper)
        service = cls(connect, None, FakeRunKey(), lambda: False)
        service._keeper = keeper
        weakref.finalize(service, keeper.close)  # closed with the service, so no connection is left to the collector
        return service

    def read(self) -> AppSettingsResponse:
        connection = self._connect()
        try:
            values = {key: get_setting(connection, key) for key in _KEYS}
        finally:
            connection.close()
        return AppSettingsResponse(**values, installed=self._installed())

    def save(self, new: AppSettingsValues) -> SaveOutcome:
        connection = self._connect()
        try:
            before = get_setting(connection, "port")
            connection.execute("BEGIN IMMEDIATE")  # all five or none
            try:
                for key in _KEYS:
                    set_setting(connection, key, getattr(new, key))
                connection.execute("COMMIT")
            except BaseException:
                connection.execute("ROLLBACK")
                raise
        finally:
            connection.close()
        applied = self._apply_start_with_windows(new.start_with_windows)
        if self._handler is not None:
            set_log_retention(self._handler, new.log_retention_days)
        return SaveOutcome(values=new, restart_needed=new.port != before, start_with_windows_applied=applied)

    def _apply_start_with_windows(self, enabled: bool) -> bool:
        try:
            outcome = apply_start_with_windows(enabled, self._run_key, installed=self._installed())
        except AutostartError as error:
            _log.warning("Start with Windows couldn't be applied (%s)", error)
            return False
        _log.info("Start with Windows: %s", outcome)
        return True


def make_app_settings_router(service: AppSettingsService) -> APIRouter:
    router = APIRouter()

    @router.get(APP_SETTINGS_PATH, response_model=AppSettingsResponse)
    def get_app_settings() -> AppSettingsResponse:
        return service.read()

    @router.put(
        APP_SETTINGS_PATH,
        response_model=AppSettingsSaved,
        responses={422: {"model": ErrorResponse}},
    )
    def put_app_settings(body: AppSettingsValues) -> AppSettingsSaved:
        outcome = service.save(body)
        return AppSettingsSaved(
            **outcome.values.model_dump(),
            restart_needed=outcome.restart_needed,
            start_with_windows_applied=outcome.start_with_windows_applied,
        )

    return router

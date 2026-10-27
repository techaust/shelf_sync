"""The Settings > App API (SET-06, LOG-01): port, theme, Start with Windows, notifications, log retention.

Behind the guard in `secure/middleware.py` (a session, and Origin plus `X-ShelfSync: 1` for the PUT), so neither route
needs its own check. A wrong shape is the fixed 422 `invalid_request` that never echoes the request.

    GET  /api/settings/app   the five settings and `installed` (whether this copy is the installed one)
    PUT  /api/settings/app   all five, unknown fields refused; answers what was saved and what the save did

What a save does at once: Start with Windows is applied when it changed (or at the first save after start): an
installed copy writes or removes the Run value; a failure is a 200 with `start_with_windows_result: "failed"`, never a
500. The log retention is applied to the running handler, and the old log files are pruned, when it changed. The port
takes effect at the next start (`restart_needed`: the saved port differs from the one the server is bound to).
Notifications are only saved: nothing reads the setting before M5 (SYS-05).
"""

import logging
import sqlite3
import threading
import uuid
import weakref
from collections.abc import Callable
from logging.handlers import TimedRotatingFileHandler
from typing import Annotated, Any, Literal

from fastapi import APIRouter
from pydantic import BaseModel, ConfigDict, Field, StrictBool, StrictInt, TypeAdapter

from shelfsync.api.errors import ErrorResponse
from shelfsync.db.migrate import migrate
from shelfsync.db.settings import DEFAULTS, get_setting, set_setting
from shelfsync.logs import MAX_LOG_RETENTION_DAYS, set_log_retention
from shelfsync.platform.autostart import FakeRunKey, RunKey, apply_start_with_windows_safely, is_installed_copy
from shelfsync.ports import DEFAULT_PORT, LAST_PORT

_log = logging.getLogger("shelfsync.api.settings")

APP_SETTINGS_PATH = "/api/settings/app"

Theme = Literal["system", "light", "dark"]
StartWithWindowsResult = Literal["applied", "not_installed", "failed"]
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
    restart_needed: (
        bool  # the saved port differs from the one the server is bound to: it takes effect at the next start
    )
    start_with_windows_result: StartWithWindowsResult  # "not_installed": a development copy never writes the Run key


_VALIDATORS: dict[str, TypeAdapter[Any]] = {
    key: TypeAdapter(Annotated[field.annotation, field])  # type: ignore[arg-type]
    for key, field in AppSettingsValues.model_fields.items()
}


def stored_app_settings(connection: sqlite3.Connection) -> dict[str, Any]:
    """The five stored App settings. One that is out of range or of the wrong type (a hand-edited database) is the
    default, with a warning naming the key only, so a read never fails. Start-up reads them through this too."""
    values: dict[str, Any] = {}
    for key in _KEYS:
        try:
            values[key] = _VALIDATORS[key].validate_python(get_setting(connection, key))
        except ValueError:  # includes JSON errors and pydantic's validation errors
            _log.warning("The stored setting '%s' isn't valid; the default is used", key)
            values[key] = DEFAULTS[key]
    return values


class AppSettingsService:
    """What the routes talk to: reads and saves through `db/settings.py` and applies what a save decides at once.

    `connect` opens a connection to the database (one per call, closed after). `bound_port` is the port the server
    is actually bound to (`restart_needed` compares with it, not with the stored value). `handler` is the running log
    handler (None: nothing to update). `run_key` and `installed` are replaceable for tests; by default the real Run
    key is used and `is_installed_copy()` decides whether it is written."""

    def __init__(
        self,
        connect: Callable[[], sqlite3.Connection],
        bound_port: int,
        handler: TimedRotatingFileHandler | None = None,
        run_key: RunKey | None = None,
        installed: Callable[[], bool] = is_installed_copy,
    ) -> None:
        self._connect = connect
        self._bound_port = bound_port
        self._handler = handler
        self._run_key = run_key
        self._installed = installed
        self._lock = threading.Lock()  # one save at a time: the Run key and the handler follow the commit order
        self._run_key_applied = False  # the Run value is made to match once per start, then only when it changes
        self._keeper: sqlite3.Connection | None = None  # holds a development database's memory open

    @classmethod
    def development(cls, bound_port: int = DEFAULT_PORT) -> AppSettingsService:
        """The default for tests and a copy with no database behind it: settings in memory, no log handler and a Run key
        that is never the real one."""
        uri = f"file:shelfsync-settings-{uuid.uuid4().hex}?mode=memory&cache=shared"

        def connect() -> sqlite3.Connection:
            return sqlite3.connect(uri, uri=True, isolation_level=None, check_same_thread=False)

        keeper = connect()
        migrate(keeper)
        service = cls(connect, bound_port, None, FakeRunKey(), lambda: False)
        service._keeper = keeper
        weakref.finalize(service, keeper.close)  # closed with the service, so no connection is left to the collector
        return service

    def read(self) -> AppSettingsResponse:
        connection = self._connect()
        try:
            values = stored_app_settings(connection)
        finally:
            connection.close()
        return AppSettingsResponse(**values, installed=self._installed())

    def save(self, new: AppSettingsValues) -> AppSettingsSaved:
        """Saves all five in one transaction, then applies what changed. `start_with_windows_result`: "applied" (the
        Run value was made to match, or already did), "failed" (Windows refused; tried again at the next save),
        "not_installed" (a development copy touches nothing). When the setting is unchanged and was already applied
        since the start, the Run key isn't touched again: the result is "applied" for an installed copy and
        "not_installed" otherwise."""
        with self._lock:
            connection = self._connect()
            try:
                connection.execute("BEGIN IMMEDIATE")  # all five or none
                try:
                    before = stored_app_settings(connection)
                    for key in _KEYS:
                        set_setting(connection, key, getattr(new, key))
                    connection.execute("COMMIT")
                except BaseException:
                    connection.execute("ROLLBACK")
                    raise
            finally:
                connection.close()
            result = self._apply_start_with_windows(new.start_with_windows, before["start_with_windows"])
            handler = self._handler
            if handler is not None and (
                new.log_retention_days != before["log_retention_days"] or handler.backupCount != new.log_retention_days
            ):
                set_log_retention(handler, new.log_retention_days)
            return AppSettingsSaved(
                **new.model_dump(),
                restart_needed=new.port != self._bound_port,
                start_with_windows_result=result,
            )

    def _apply_start_with_windows(self, enabled: bool, before: bool) -> StartWithWindowsResult:
        installed = self._installed()
        if self._run_key_applied and enabled == before:
            return "applied" if installed else "not_installed"
        outcome = apply_start_with_windows_safely(enabled, self._run_key, installed=installed)
        if outcome == "failed":
            self._run_key_applied = False  # the stored value no longer matches Windows: the next save tries again
            return "failed"
        self._run_key_applied = True
        return "not_installed" if outcome == "skipped" else "applied"


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
        return service.save(body)

    return router

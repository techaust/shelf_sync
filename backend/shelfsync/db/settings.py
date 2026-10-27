"""Settings stored as JSON in the `setting` table. Defaults live in code, not as rows (04 section 4)."""

import json
import sqlite3
from collections.abc import Callable
from typing import Any

from shelfsync.ports import DEFAULT_PORT, LAST_PORT

BACKUPS_KEPT_MIN, BACKUPS_KEPT_MAX = 1, 30  # BAK-01: how many daily database backups are kept
SNAPSHOT_DAYS_MIN, SNAPSHOT_DAYS_MAX = 1, 365  # SET-05: how long catalog snapshots are kept (stored now, used in M3)

DEFAULTS: dict[str, Any] = {
    "port": DEFAULT_PORT,
    "theme": "system",
    "start_with_windows": True,
    "notifications": True,
    "log_retention_days": 30,
    "db_backups_kept": 7,
    "snapshot_retention_days": 30,
}


def _in_range(key: str, low: int, high: int) -> Callable[[Any], None]:
    def check(value: Any) -> None:
        if not low <= value <= high:
            raise ValueError(f"Setting '{key}' must be between {low} and {high}.")

    return check


# One rule per key beyond its type (the type is always the default's exact type, so True is not accepted for an int
# setting). A key with no entry has no rule beyond its type. The port stays inside 47615-47624, the range the "all in
# use" notice names (M1a.1 re-check).
_VALIDATORS: dict[str, Callable[[Any], None]] = {
    "port": _in_range("port", DEFAULT_PORT, LAST_PORT),
    "db_backups_kept": _in_range("db_backups_kept", BACKUPS_KEPT_MIN, BACKUPS_KEPT_MAX),
    "snapshot_retention_days": _in_range("snapshot_retention_days", SNAPSHOT_DAYS_MIN, SNAPSHOT_DAYS_MAX),
}


def _check(key: str, value: Any) -> None:
    if key not in DEFAULTS:
        raise KeyError(f"Unknown setting '{key}'.")
    expected = type(DEFAULTS[key])
    if type(value) is not expected:  # exact type, so True is not accepted for an int setting
        raise TypeError(f"Setting '{key}' must be {expected.__name__}, not {type(value).__name__}.")
    rule = _VALIDATORS.get(key)
    if rule is not None:
        rule(value)


def get_setting(connection: sqlite3.Connection, key: str) -> Any:
    """The stored value, or the default if nothing is stored."""
    if key not in DEFAULTS:
        raise KeyError(f"Unknown setting '{key}'.")
    row = connection.execute("SELECT value_json FROM setting WHERE key = ?", (key,)).fetchone()
    return DEFAULTS[key] if row is None else json.loads(row[0])


def set_setting(connection: sqlite3.Connection, key: str, value: Any) -> None:
    _check(key, value)
    connection.execute(
        "INSERT INTO setting (key, value_json) VALUES (?, ?) "
        "ON CONFLICT(key) DO UPDATE SET value_json = excluded.value_json",
        (key, json.dumps(value)),
    )


def get_all_settings(connection: sqlite3.Connection) -> dict[str, Any]:
    return {key: get_setting(connection, key) for key in DEFAULTS}

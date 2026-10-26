"""Settings stored as JSON in the `setting` table. Defaults live in code, not as rows (04 section 4)."""

import json
import sqlite3
from typing import Any

DEFAULTS: dict[str, Any] = {
    "port": 47615,
    "theme": "system",
    "start_with_windows": True,
    "notifications": True,
    "log_retention_days": 30,
}


def _check(key: str, value: Any) -> None:
    if key not in DEFAULTS:
        raise KeyError(f"Unknown setting '{key}'.")
    expected = type(DEFAULTS[key])
    if type(value) is not expected:  # exact type, so True is not accepted for an int setting
        raise TypeError(f"Setting '{key}' must be {expected.__name__}, not {type(value).__name__}.")


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

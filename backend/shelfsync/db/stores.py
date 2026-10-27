"""The `store` table (SET-01, ERR-01): list, get, insert, update, soft delete and save a test result.

Every function takes an open connection and **never commits**: the caller owns the transaction (the connection is in
autocommit mode, see `db/connection.py`), so a save that also writes Credential Manager entries can roll the row back.
A removed store keeps its row (`removed_at`) because history from M3 points at store ids; reads skip removed rows
except `all_ids`, which "Remove my data" and the start-up read of the secrets need.
"""

import sqlite3
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

# The columns `update_store` may set: a fixed list, so no caller-chosen text ever reaches the SQL.
EDITABLE_COLUMNS = frozenset({"name", "url", "code", "shape", "color", "spacing_ms", "main_button", "state"})

_COLUMNS = (
    "id, name, url, code, shape, color, spacing_ms, main_button, state, wc_version, wp_version, health, "
    "health_reason, http_status, latency_ms, downloadable_count, tested_at, created_at"
)


class UrlTaken(Exception):
    """Another live store has this URL."""


class CodeTaken(Exception):
    """Another live store has this two-letter code."""


@dataclass(frozen=True)
class StoreRow:
    id: int
    name: str
    url: str
    code: str
    shape: str
    color: str
    spacing_ms: int
    main_button: str
    state: str
    wc_version: str | None
    wp_version: str | None
    health: str
    health_reason: str | None
    http_status: int | None
    latency_ms: int | None
    downloadable_count: int | None
    tested_at: str | None
    created_at: str


@dataclass(frozen=True)
class SavedTest:
    """What one read test found, as it is saved on the row (`health` is the state the chip shows)."""

    health: str
    reason: str | None
    http_status: int | None
    latency_ms: int | None
    wc_version: str | None
    wp_version: str | None
    downloadable_count: int | None
    tested_at: str


def _row(values: tuple[Any, ...]) -> StoreRow:
    return StoreRow(*values)


def _raise_conflict(error: sqlite3.IntegrityError) -> None:
    text = str(error)
    if "store.url" in text:
        raise UrlTaken from None
    if "store.code" in text:
        raise CodeTaken from None
    raise error


def list_live(connection: sqlite3.Connection) -> list[StoreRow]:
    """The stores that aren't removed, oldest first."""
    rows = connection.execute(
        f"SELECT {_COLUMNS} FROM store WHERE removed_at IS NULL ORDER BY id"  # nosec B608  # a fixed column list
    ).fetchall()
    return [_row(row) for row in rows]


def get_store(connection: sqlite3.Connection, store_id: int) -> StoreRow | None:
    row = connection.execute(
        f"SELECT {_COLUMNS} FROM store WHERE id = ? AND removed_at IS NULL",  # nosec B608  # a fixed column list
        (store_id,),
    ).fetchone()
    return None if row is None else _row(row)


def all_ids(connection: sqlite3.Connection) -> list[int]:
    """Every store id ever used, removed ones too (their Credential Manager entries must be swept as well)."""
    return [row[0] for row in connection.execute("SELECT id FROM store ORDER BY id")]


def insert_store(
    connection: sqlite3.Connection,
    *,
    name: str,
    url: str,
    code: str,
    shape: str,
    color: str,
    spacing_ms: int,
    main_button: str,
    created_at: str,
) -> int:
    """Add a store and return its id. Raises `UrlTaken` or `CodeTaken`."""
    try:
        cursor = connection.execute(
            "INSERT INTO store (name, url, code, shape, color, spacing_ms, main_button, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (name, url, code, shape, color, spacing_ms, main_button, created_at),
        )
    except sqlite3.IntegrityError as error:
        _raise_conflict(error)
        raise  # not reached: _raise_conflict always raises
    if cursor.lastrowid is None:  # an INSERT always has one
        raise sqlite3.DatabaseError("the insert gave no row id")
    return cursor.lastrowid


def update_store(connection: sqlite3.Connection, store_id: int, changes: Mapping[str, Any]) -> bool:
    """Set the given editable columns on a live store. False if there is no such store. `UrlTaken` / `CodeTaken` on
    a clash. A changed URL also puts the health back to `unknown` (the old result was about another address)."""
    unknown = set(changes) - EDITABLE_COLUMNS
    if unknown:
        raise KeyError(f"Not an editable store column: {sorted(unknown)[0]}")
    if not changes:
        return get_store(connection, store_id) is not None
    assignments = [f"{column} = ?" for column in changes]
    values = list(changes.values())
    try:
        cursor = connection.execute(
            # the column names come from EDITABLE_COLUMNS (checked above) and the values are bound
            f"UPDATE store SET {', '.join(assignments)} WHERE id = ? AND removed_at IS NULL",  # nosec B608
            (*values, store_id),
        )
    except sqlite3.IntegrityError as error:
        _raise_conflict(error)
        raise
    if cursor.rowcount == 0:
        return False
    if "url" in changes:
        reset_health(connection, store_id)
    return True


def reset_health(connection: sqlite3.Connection, store_id: int) -> None:
    """Back to `unknown`: the address or the keys changed, so the last result no longer says anything."""
    connection.execute(
        "UPDATE store SET health = 'unknown', health_reason = NULL, http_status = NULL, latency_ms = NULL, "
        "wc_version = NULL, wp_version = NULL, downloadable_count = NULL, tested_at = NULL WHERE id = ?",
        (store_id,),
    )


def save_test_result(connection: sqlite3.Connection, store_id: int, result: SavedTest) -> None:
    connection.execute(
        "UPDATE store SET health = ?, health_reason = ?, http_status = ?, latency_ms = ?, wc_version = ?, "
        "wp_version = ?, downloadable_count = ?, tested_at = ? WHERE id = ? AND removed_at IS NULL",
        (
            result.health,
            result.reason,
            result.http_status,
            result.latency_ms,
            result.wc_version,
            result.wp_version,
            result.downloadable_count,
            result.tested_at,
            store_id,
        ),
    )


def soft_delete(connection: sqlite3.Connection, store_id: int, removed_at: str) -> bool:
    """Mark a live store removed. Its URL and code are free again (the unique indexes cover live rows only)."""
    cursor = connection.execute(
        "UPDATE store SET removed_at = ? WHERE id = ? AND removed_at IS NULL", (removed_at, store_id)
    )
    return cursor.rowcount > 0

"""The database side of the export file, payload version 1 (SET-05): what is read for an export and what an import
writes. Pure SQLite: no secrets, no JSON, no validation (the API's models validate; `api/backup.py` ties it together).

Payload v1 is `{settings, stores, storage, catalog, secrets}`:
- `settings`: every setting that is not a storage setting (port, theme, Start with Windows, notifications, log
  retention, the two backup settings);
- `storage`: the five storage settings (`STORAGE_KEYS`), so no setting is in the file twice;
- `stores`: each live store's identity, not its health or its id (`STORE_FIELDS`);
- `catalog`: `null` until M3 adds one as format version 2;
- `secrets`: only in an encrypted file (`api/backup.py`).

An import writes only into an install with no live store (`live_store_count`), in the caller's transaction: nothing
here commits, so the caller can write Credential Manager before it does and roll everything back on a failure.
"""

import sqlite3
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from shelfsync.db.migrate import applied_versions, discover
from shelfsync.db.settings import DEFAULTS, set_setting
from shelfsync.db.stores import StoreRow, insert_store, list_live, update_store

# The five storage settings (SET-02); every other key of `DEFAULTS` is a plain setting.
STORAGE_KEYS: tuple[str, ...] = (
    "s3_endpoint",
    "s3_region",
    "s3_bucket",
    "keep_previous_files",
    "download_link_template",
)
SETTINGS_KEYS: tuple[str, ...] = tuple(key for key in DEFAULTS if key not in STORAGE_KEYS)
STORE_FIELDS: tuple[str, ...] = ("code", "name", "url", "shape", "color", "spacing_ms", "main_button", "state")


@dataclass(frozen=True)
class StoreImport:
    """One store to add: exactly the exported fields, already validated."""

    code: str
    name: str
    url: str
    shape: str
    color: str
    spacing_ms: int
    main_button: str
    state: str


def highest_known_schema() -> int:
    """The highest migration this app carries: a file written under a newer schema is refused."""
    return discover()[-1].version


def highest_applied_schema(connection: sqlite3.Connection) -> int:
    """The highest migration the database has applied: what an export records."""
    return max(applied_versions(connection))


def read_stores(connection: sqlite3.Connection) -> list[StoreRow]:
    """The live stores, oldest first."""
    return list_live(connection)


def write_import(
    connection: sqlite3.Connection,
    *,
    settings: Mapping[str, Any],
    stores: Sequence[StoreImport],
    created_at: str,
) -> list[int]:
    """Write every setting and add every store, in the caller's open transaction; returns the new store ids in the
    order given. `UrlTaken` or `CodeTaken` (from `db/stores.py`) when a live store already holds an address or a
    code: the caller has checked there is none, so this only happens in a race, and it rolls back."""
    for key, value in settings.items():
        set_setting(connection, key, value)
    ids: list[int] = []
    for store in stores:
        store_id = insert_store(
            connection,
            name=store.name,
            url=store.url,
            code=store.code,
            shape=store.shape,
            color=store.color,
            spacing_ms=store.spacing_ms,
            main_button=store.main_button,
            created_at=created_at,
        )
        if store.state != "active":
            update_store(connection, store_id, {"state": store.state})
        ids.append(store_id)
    return ids

"""The nightly snapshot's tables (migration 0004; SYNC-03, SYNC-04, APL-14's dates): one row per store per night
(`snapshot_night`) and the products' states stored as changes (`snapshot_state`). Plain `sqlite3`.

**A night** is the local date of the night's `snapshot_time`. Its row goes `running` at each attempt (the attempt
counted), then `ok`, `retry` (with `next_try_at`), `failed` or `skipped` (with the reason).

**One store's snapshot that worked is saved in one transaction** (`save_snapshot`): the catalog part
(`db.catalog.apply_products`: trashed and deleted products, and changed ones, reported once), the states (a product in
the same state as its row of the store's previous `ok` night only moves that row's `last_night`; any other gets a new
row), the night's row (`ok` and its counts), and the retention. A failed or stopped snapshot changes none of it.

**Retention (SYNC-03):** the nights older than `snapshot_retention_days` (counting the night saved as the first) are
deleted, with the state rows whose `last_night` is older still; a row that still reaches a kept night stays whole.

**The dates a product can be restored to** (`restorable_nights`, APL-14 in M5) are the `ok` nights of its store
between the `first_night` and `last_night` of one of its rows.
"""

import hashlib
import json
import sqlite3
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, timedelta

from shelfsync.catalog.changes import TRASH
from shelfsync.catalog.model import Product, downloads_json, meta_json
from shelfsync.db.catalog import ApplySummary, apply_products, guard_store

NIGHT_STATES = ("running", "ok", "retry", "failed", "skipped")
ATTEMPTS_MAX = 3  # the first attempt and up to 2 more the same night (Lead (proposed), m3.2)
VARIATIONS_JSON_MAX = 4 * 1024 * 1024  # migration 0004's CHECK on `variations_json`


class SnapshotTooLarge(Exception):
    """A product's variations would pass `variations_json`'s limit: the snapshot isn't saved."""


@dataclass(frozen=True)
class NightRow:
    store_id: int
    night: str
    state: str
    attempts: int
    started_at: str | None
    finished_at: str | None
    next_try_at: str | None
    reason: str | None
    http_status: int | None
    listing: str | None
    products: int | None
    trashed: int | None
    not_seen: int | None
    variable: int | None


_NIGHT_COLUMNS = (
    "store_id, night, state, attempts, started_at, finished_at, next_try_at, reason, http_status, listing, products, "
    "trashed, not_seen, variable"
)


def _begin(connection: sqlite3.Connection) -> None:
    connection.execute("BEGIN IMMEDIATE")


def _rollback(connection: sqlite3.Connection) -> None:
    if connection.in_transaction:
        connection.execute("ROLLBACK")


def night_row(connection: sqlite3.Connection, store_id: int, night: str) -> NightRow | None:
    row = connection.execute(
        f"SELECT {_NIGHT_COLUMNS} FROM snapshot_night WHERE store_id = ? AND night = ?",  # nosec B608  # fixed columns
        (store_id, night),
    ).fetchone()
    return None if row is None else NightRow(*row)


def nights_of(connection: sqlite3.Connection, night: str) -> dict[int, NightRow]:
    """Every store's row for one night."""
    rows = connection.execute(
        f"SELECT {_NIGHT_COLUMNS} FROM snapshot_night WHERE night = ?",  # nosec B608  # fixed columns
        (night,),
    )
    return {row[0]: NightRow(*row) for row in rows}


def latest_nights(connection: sqlite3.Connection) -> dict[int, NightRow]:
    """Each store's latest night row."""
    rows = connection.execute(
        f"SELECT {_NIGHT_COLUMNS} FROM snapshot_night n WHERE night = "  # nosec B608  # fixed columns
        "(SELECT max(night) FROM snapshot_night m WHERE m.store_id = n.store_id)"
    )
    return {row[0]: NightRow(*row) for row in rows}


def start_attempt(connection: sqlite3.Connection, store_id: int, night: str, at: str) -> int:
    """A snapshot attempt starts: the night is `running` and its attempts go up by one. Returns the attempt's number
    (1 to 3). `ValueError` when the night has no attempt left or is already done (`ok`, `failed`, `skipped`)."""
    _begin(connection)
    try:
        row = connection.execute(
            "SELECT state, attempts FROM snapshot_night WHERE store_id = ? AND night = ?", (store_id, night)
        ).fetchone()
        if row is not None and (row[0] in ("ok", "failed", "skipped") or row[1] >= ATTEMPTS_MAX):
            raise ValueError("this night's snapshot is done")
        connection.execute(
            "INSERT INTO snapshot_night (store_id, night, state, attempts, started_at) VALUES (?, ?, 'running', 1, ?) "
            "ON CONFLICT (store_id, night) DO UPDATE SET state = 'running', attempts = attempts + 1, "
            "started_at = excluded.started_at, finished_at = NULL, next_try_at = NULL, reason = NULL, "
            "http_status = NULL",
            (store_id, night, at),
        )
        (attempts,) = connection.execute(
            "SELECT attempts FROM snapshot_night WHERE store_id = ? AND night = ?", (store_id, night)
        ).fetchone()
        connection.execute("COMMIT")
    except BaseException:
        _rollback(connection)
        raise
    return int(attempts)


def record_failed(
    connection: sqlite3.Connection,
    store_id: int,
    night: str,
    *,
    reason: str,
    http_status: int | None,
    at: str,
    retry_at: str | None,
) -> None:
    """An attempt that didn't work: `retry` until `retry_at` when given, else `failed`. Nothing else changes."""
    connection.execute(
        "UPDATE snapshot_night SET state = ?, finished_at = ?, next_try_at = ?, reason = ?, http_status = ? "
        "WHERE store_id = ? AND night = ?",
        ("retry" if retry_at is not None else "failed", at, retry_at, reason, http_status, store_id, night),
    )


def record_skipped(connection: sqlite3.Connection, store_id: int, night: str, *, reason: str, at: str) -> None:
    """The store's night is skipped (paused, auto-paused, no catalog yet): done for that night, with the reason."""
    connection.execute(
        "INSERT INTO snapshot_night (store_id, night, state, attempts, finished_at, reason) "
        "VALUES (?, ?, 'skipped', 0, ?, ?) ON CONFLICT (store_id, night) DO UPDATE SET state = 'skipped', "
        "finished_at = excluded.finished_at, next_try_at = NULL, reason = excluded.reason",
        (store_id, night, at, reason),
    )


# ---- saving a snapshot that worked ---------------------------------------------------------------------------------


@dataclass(frozen=True)
class SnapshotSummary:
    catalog: ApplySummary  # what the snapshot did to the catalog, with the changes it found
    products: int
    trashed: int
    not_seen: int  # catalog products the listing didn't hold
    new_rows: int  # state rows added (a product new, changed, or seen again after a night it was missing)
    extended: int  # state rows whose `last_night` moved
    pruned_nights: int
    pruned_rows: int


def _variations_json(variations: Sequence[Product]) -> str:
    text = json.dumps(
        [
            [row.wc_id, row.status, json.loads(downloads_json(row.downloads)), json.loads(meta_json(row.meta))]
            for row in variations
        ],
        ensure_ascii=False,
        separators=(",", ":"),
    )
    if len(text) > VARIATIONS_JSON_MAX:
        raise SnapshotTooLarge
    return text


def state_fields(product: Product, variations: Sequence[Product]) -> tuple[str, str, str, str, str, str, str]:
    """(status, slug, type, downloads_json, meta_json, variations_json, state_sha256) of one product."""
    downloads = downloads_json(product.downloads)
    meta = meta_json(product.meta)
    varied = _variations_json(variations)
    canonical = json.dumps(
        [product.status, product.slug, product.type, downloads, meta, varied], ensure_ascii=False, separators=(",", ":")
    )
    digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    return product.status, product.slug, product.type, downloads, meta, varied, digest


def previous_ok_night(connection: sqlite3.Connection, store_id: int, night: str) -> str | None:
    row = connection.execute(
        "SELECT max(night) FROM snapshot_night WHERE store_id = ? AND state = 'ok' AND night < ?", (store_id, night)
    ).fetchone()
    return None if row is None or row[0] is None else str(row[0])


def cutoff_night(night: str, retention_days: int) -> str:
    """The oldest night kept: `retention_days` nights counting `night` itself."""
    return (date.fromisoformat(night) - timedelta(days=max(retention_days, 1) - 1)).isoformat()


def save_snapshot(
    connection: sqlite3.Connection,
    store_id: int,
    night: str,
    products: Sequence[Product],
    variations: dict[int, Sequence[Product]],
    *,
    listing: str,
    at: str,
    read_url: str,
    retention_days: int,
) -> SnapshotSummary:
    """Save one store's snapshot that worked, in one transaction (the module text says what that does).
    `AddressMoved` or `StoreRemoved` (and nothing saved) as for a full read; `SnapshotTooLarge` likewise."""
    _begin(connection)
    try:
        guard_store(connection, store_id, read_url)
        fields = {product.wc_id: state_fields(product, variations.get(product.wc_id, ())) for product in products}
        previous = previous_ok_night(connection, store_id, night)
        latest: dict[int, tuple[int, str]] = {}
        if previous is not None:
            for row_id, wc_id, digest in connection.execute(
                "SELECT id, wc_id, state_sha256 FROM snapshot_state WHERE store_id = ? AND last_night = ?",
                (store_id, previous),
            ):
                latest[wc_id] = (row_id, digest)
        catalog = apply_products(connection, store_id, products, at=at, source="snapshot", seen_last_night=set(latest))
        extend: list[tuple[str, int]] = []
        insert: list[tuple[object, ...]] = []
        for wc_id, state in fields.items():
            held = latest.get(wc_id)
            if held is not None and held[1] == state[6]:
                extend.append((night, held[0]))
            else:
                insert.append((store_id, wc_id, *state, night, night))
        connection.executemany("UPDATE snapshot_state SET last_night = ? WHERE id = ?", extend)
        connection.executemany(
            "INSERT INTO snapshot_state (store_id, wc_id, status, slug, type, downloads_json, meta_json, "
            "variations_json, state_sha256, first_night, last_night) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            insert,
        )
        trashed = sum(1 for product in products if product.status == TRASH)
        read = {product.wc_id for product in products}
        not_seen = sum(
            1
            for (wc_id,) in connection.execute("SELECT wc_id FROM store_product WHERE store_id = ?", (store_id,))
            if wc_id not in read
        )
        connection.execute(
            "UPDATE snapshot_night SET state = 'ok', finished_at = ?, next_try_at = NULL, reason = NULL, "
            "http_status = NULL, listing = ?, products = ?, trashed = ?, not_seen = ?, variable = ? "
            "WHERE store_id = ? AND night = ?",
            (at, listing, len(products), trashed, not_seen, len(variations), store_id, night),
        )
        cutoff = cutoff_night(night, retention_days)
        pruned_rows = connection.execute("DELETE FROM snapshot_state WHERE last_night < ?", (cutoff,)).rowcount
        pruned_nights = connection.execute("DELETE FROM snapshot_night WHERE night < ?", (cutoff,)).rowcount
        connection.execute("COMMIT")
    except BaseException:
        _rollback(connection)
        raise
    return SnapshotSummary(
        catalog, len(products), trashed, not_seen, len(insert), len(extend), pruned_nights, pruned_rows
    )


# ---- what the API reads --------------------------------------------------------------------------------------------


def restorable_nights(connection: sqlite3.Connection, store_id: int, wc_id: int) -> list[str]:
    """The nights one store product can be restored to (local dates, newest first): its store's `ok` nights that one
    of its state rows spans."""
    rows = connection.execute(
        "SELECT DISTINCT n.night FROM snapshot_night n JOIN snapshot_state s ON s.store_id = n.store_id "
        "AND n.night BETWEEN s.first_night AND s.last_night "
        "WHERE n.store_id = ? AND s.wc_id = ? AND n.state = 'ok' ORDER BY n.night DESC",
        (store_id, wc_id),
    )
    return [row[0] for row in rows]

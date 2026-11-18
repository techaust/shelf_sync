"""The nightly snapshot's tables (migration 0004; SYNC-03, SYNC-04, APL-14's dates): one row per store per night
(`snapshot_night`) and the products' states stored as changes (`snapshot_state`). Plain `sqlite3`.

**A night** is the local date of the night's `snapshot_time`. Its row goes `running` at each attempt (the attempt
numbered), then `ok`, `retry` (with `next_try_at`), `failed` or `skipped` (with the reason). A failed attempt is
recorded and counted as one failed read (APL-12, `db.catalog.count_failed_read`) in one transaction, and its retry is
decided from the state that transaction wrote (an attempt that auto-paused the store isn't retried).

**One store's snapshot that worked is saved in one transaction** (`save_snapshot`): the catalog part
(`db.catalog.apply_products`: new products added, trashed, deleted and changed ones reported once), the changes handed
to the sink (F4), the failed reads back to 0, the states (a product in the same state as its row of the store's
previous `ok` night only moves that row's `last_night`; any other gets a new row), the night's row (`ok` and its
counts) and the retention. A failed or stopped snapshot changes none of it. A night later than the PC's night of the
attempt's start plus a day is refused (`NightAhead`, F5).

**Retention (SYNC-03; F5, Lead (proposed)):** per store. A night of that store is deleted only when it is both older
than `snapshot_retention_days` nights (counting the night saved as the first) **and** outside the store's newest
`snapshot_retention_days` `ok` nights, so a clock that jumped forward costs at most the nights it pushed out, never
the whole history. State rows whose `last_night` is older than the oldest night kept go too; a row that still reaches a
kept night stays whole.

**The dates a product can be restored to** (`restorable_nights`, APL-14 in M5) are the `ok` nights of its store
between the `first_night` and `last_night` of one of its rows.
"""

import hashlib
import json
import sqlite3
from collections.abc import Collection, Sequence
from dataclasses import dataclass
from datetime import date, datetime, timedelta

from shelfsync.catalog.changes import TRASH
from shelfsync.catalog.model import Product, downloads_json, meta_json
from shelfsync.catalog.schedule import ATTEMPTS_MAX, deferred_until, retry_at
from shelfsync.clock import to_iso
from shelfsync.db.catalog import (
    ApplySummary,
    ChangeSink,
    apply_products,
    count_failed_read,
    guard_store,
    is_auto_paused,
    reset_failed_reads,
)

NIGHT_STATES = ("running", "ok", "retry", "failed", "skipped")
VARIATIONS_JSON_MAX = 4 * 1024 * 1024  # migration 0004's CHECK on `variations_json`


class SnapshotTooLarge(Exception):
    """A product's variations would pass `variations_json`'s limit: the snapshot isn't saved."""


class NightAhead(Exception):
    """The night is later than the PC's night of the attempt's start plus a day (a clock that jumped): not saved."""


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
    unconfirmed: int | None = None


_NIGHT_COLUMNS = (
    "store_id, night, state, attempts, started_at, finished_at, next_try_at, reason, http_status, listing, products, "
    "trashed, not_seen, variable, unconfirmed"
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
    at: datetime,
    attempt: int,
) -> bool:
    """An attempt that didn't work, in one transaction: counted as one failed read (unless its reason never counts),
    then `retry` until the time `catalog.schedule.retry_at` gives from the state just written, or `failed`. An
    attempt the app's shutdown stopped gives its attempt back (review 1). Nothing else changes. True when this attempt
    auto-paused the store."""
    stamp = to_iso(at)
    _begin(connection)
    try:
        paused = count_failed_read(connection, store_id, reason, stamp)
        again = retry_at(reason, attempt, at, auto_paused=paused or is_auto_paused(connection, store_id))
        if reason == "stopped":
            connection.execute(
                "UPDATE snapshot_night SET attempts = max(attempts - 1, 0) WHERE store_id = ? AND night = ?",
                (store_id, night),
            )
        connection.execute(
            "UPDATE snapshot_night SET state = ?, finished_at = ?, next_try_at = ?, reason = ?, http_status = ? "
            "WHERE store_id = ? AND night = ?",
            (
                "retry" if again is not None else "failed",
                stamp,
                to_iso(again) if again is not None else None,
                reason,
                http_status,
                store_id,
                night,
            ),
        )
        connection.execute("COMMIT")
    except BaseException:
        _rollback(connection)
        raise
    return paused


def record_deferred(connection: sqlite3.Connection, store_id: int, night: str, *, reason: str, at: datetime) -> None:
    """The night couldn't start an attempt (`busy`, a database error before it): `retry` a few minutes later
    (`catalog.schedule.deferred_until`), using no attempt and counting nothing (review 1)."""
    connection.execute(
        "INSERT INTO snapshot_night (store_id, night, state, attempts, finished_at, next_try_at, reason) "
        "VALUES (?, ?, 'retry', 0, ?, ?, ?) ON CONFLICT (store_id, night) DO UPDATE SET state = 'retry', "
        "finished_at = excluded.finished_at, next_try_at = excluded.next_try_at, reason = excluded.reason "
        "WHERE snapshot_night.state IN ('retry', 'running')",
        (store_id, night, to_iso(at), to_iso(deferred_until(at)), reason),
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
    not_seen: int  # present catalog products a 404 confirmed deleted (F10)
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


def state_fields(product: Product, variations: Sequence[Product]) -> tuple[str, str, str, int, str, str, str, str]:
    """(status, slug, type, downloadable, downloads_json, meta_json, variations_json, state_sha256) of one product."""
    downloads = downloads_json(product.downloads)
    meta = meta_json(product.meta)
    varied = _variations_json(variations)
    flag = int(product.downloadable)
    canonical = json.dumps(
        [product.status, product.slug, product.type, flag, downloads, meta, varied],
        ensure_ascii=False,
        separators=(",", ":"),
    )
    digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    return product.status, product.slug, product.type, flag, downloads, meta, varied, digest


def previous_ok_night(connection: sqlite3.Connection, store_id: int, night: str) -> str | None:
    row = connection.execute(
        "SELECT max(night) FROM snapshot_night WHERE store_id = ? AND state = 'ok' AND night < ?", (store_id, night)
    ).fetchone()
    return None if row is None or row[0] is None else str(row[0])


def cutoff_night(night: str, retention_days: int) -> str:
    """The oldest night kept by age: `retention_days` nights counting `night` itself."""
    return (date.fromisoformat(night) - timedelta(days=max(retention_days, 1) - 1)).isoformat()


def latest_allowed_night(started_night: str) -> str:
    """F5: the latest night an attempt may save: the PC's night of its start, plus one day."""
    return (date.fromisoformat(started_night) + timedelta(days=1)).isoformat()


def _prune(connection: sqlite3.Connection, store_id: int, night: str, retention_days: int) -> tuple[int, int]:
    """Retention for one store (the module text). Returns (nights deleted, state rows deleted)."""
    kept_ok = [
        row[0]
        for row in connection.execute(
            "SELECT night FROM snapshot_night WHERE store_id = ? AND state = 'ok' ORDER BY night DESC LIMIT ?",
            (store_id, max(retention_days, 1)),
        )
    ]
    floor = cutoff_night(night, retention_days)
    if kept_ok:
        floor = min(floor, kept_ok[-1])
    nights = connection.execute(
        "DELETE FROM snapshot_night WHERE store_id = ? AND night < ?", (store_id, floor)
    ).rowcount
    rows = connection.execute(
        "DELETE FROM snapshot_state WHERE store_id = ? AND last_night < ?", (store_id, floor)
    ).rowcount
    return nights, rows


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
    deleted: Collection[int] = (),
    latest_night: str | None = None,
    sink: ChangeSink | None = None,
    unconfirmed: int = 0,
) -> SnapshotSummary:
    """Save one store's snapshot that worked, in one transaction (the module text says what that does). `deleted`: the
    catalog products a 404 confirmed gone. `latest_night`: the latest night this attempt may save (F5).
    `AddressMoved`, `StoreRemoved`, `SnapshotTooLarge` or `NightAhead`, and nothing saved; anything `sink` raises rolls
    it all back too."""
    if latest_night is not None and night > latest_night:
        raise NightAhead
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
        catalog = apply_products(connection, store_id, products, at=at, source="snapshot", deleted=deleted)
        extend: list[tuple[str, int]] = []
        insert: list[tuple[object, ...]] = []
        for wc_id, state in fields.items():
            held = latest.get(wc_id)
            if held is not None and held[1] == state[7]:
                extend.append((night, held[0]))
            else:
                insert.append((store_id, wc_id, *state, night, night))
        connection.executemany("UPDATE snapshot_state SET last_night = ? WHERE id = ?", extend)
        connection.executemany(
            "INSERT INTO snapshot_state (store_id, wc_id, status, slug, type, downloadable, downloads_json, meta_json, "
            "variations_json, state_sha256, first_night, last_night) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            insert,
        )
        trashed = sum(1 for product in products if product.status == TRASH)
        reset_failed_reads(connection, store_id)
        connection.execute(
            "UPDATE snapshot_night SET state = 'ok', finished_at = ?, next_try_at = NULL, reason = NULL, "
            "http_status = NULL, listing = ?, products = ?, trashed = ?, not_seen = ?, variable = ?, unconfirmed = ? "
            "WHERE store_id = ? AND night = ?",
            (at, listing, len(products), trashed, catalog.not_seen, len(variations), unconfirmed, store_id, night),
        )
        pruned_nights, pruned_rows = _prune(connection, store_id, night, retention_days)
        if sink is not None and catalog.changes:
            sink(connection, store_id, list(catalog.changes))
        connection.execute("COMMIT")
    except BaseException:
        _rollback(connection)
        raise
    return SnapshotSummary(
        catalog, len(products), trashed, catalog.not_seen, len(insert), len(extend), pruned_nights, pruned_rows
    )


# ---- what the runner and the API read ------------------------------------------------------------------------------


def expected_products(connection: sqlite3.Connection, store_id: int, night: str) -> tuple[set[int], int]:
    """F2 and review 1: the catalog products a snapshot must find or confirm deleted: every one not yet confirmed
    deleted that is present, or that a snapshot has seen (so a product in the trash, then purged, is still looked
    for, and a backlog left unconfirmed one night is looked for the next); and the store's catalog size (its present
    products) for the cap on asking for them by id. `night` is kept for the callers' symmetry."""
    del night
    rows = connection.execute(
        "SELECT p.wc_id, p.gone_at IS NULL FROM store_product p WHERE p.store_id = ? AND p.deleted_at IS NULL AND "
        "(p.gone_at IS NULL OR EXISTS (SELECT 1 FROM snapshot_state s WHERE s.store_id = p.store_id "
        "AND s.wc_id = p.wc_id))",
        (store_id,),
    )
    expected: set[int] = set()
    present = 0
    for wc_id, is_present in rows:
        expected.add(wc_id)
        present += int(is_present)
    return expected, present


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

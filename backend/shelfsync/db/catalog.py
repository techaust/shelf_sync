"""The catalog tables (migration 0003): saving one store's full read, the per-store sync state, and the reads the API
needs. Plain `sqlite3`; the rules themselves are the pure functions in `catalog/`.

**One store's read is saved in one transaction** (`save_store_read`), after it fully succeeded: its rows are upserted,
rows it no longer returned get `gone_at` (never deleted), new products are linked (`catalog.linking.plan_links`), its
slot downloads are rebuilt (`catalog.slots.plan_slots`) and its `sync_state` records the read. Any failure rolls all of
it back, so a failed or stopped read changes nothing for that store. The failure count is the one thing written while
a read runs (`record_failure`, `record_success`): it must survive the read failing.
"""

import json
import sqlite3
from collections import defaultdict
from collections.abc import Iterable, Sequence
from dataclasses import dataclass

from shelfsync.catalog.linking import KnownLink, Placed, plan_links
from shelfsync.catalog.model import Product
from shelfsync.catalog.slots import SlotRef, plan_slots


class SlugTaken(Exception):
    """Another item already has this canonical slug."""


def _begin(connection: sqlite3.Connection) -> None:
    connection.execute("BEGIN IMMEDIATE")


def _rollback(connection: sqlite3.Connection) -> None:
    if connection.in_transaction:
        connection.execute("ROLLBACK")


# ---- sync state --------------------------------------------------------------------------------------------------


@dataclass(frozen=True)
class SyncStateRow:
    store_id: int
    read_started_at: str | None
    read_finished_at: str | None
    read_reason: str | None
    read_http_status: int | None
    read_pages: int | None
    read_rows: int | None
    read_total: int | None
    last_ok_at: str | None
    failures_in_row: int
    auto_paused_at: str | None
    auto_pause_reason: str | None


_STATE_COLUMNS = (
    "store_id, read_started_at, read_finished_at, read_reason, read_http_status, read_pages, read_rows, read_total, "
    "last_ok_at, failures_in_row, auto_paused_at, auto_pause_reason"
)


def _ensure_state(connection: sqlite3.Connection, store_id: int) -> None:
    connection.execute("INSERT INTO sync_state (store_id) VALUES (?) ON CONFLICT (store_id) DO NOTHING", (store_id,))


def sync_states(connection: sqlite3.Connection) -> dict[int, SyncStateRow]:
    rows = connection.execute(f"SELECT {_STATE_COLUMNS} FROM sync_state")  # nosec B608  # a fixed column list
    return {row[0]: SyncStateRow(*row) for row in rows}


def sync_state(connection: sqlite3.Connection, store_id: int) -> SyncStateRow | None:
    row = connection.execute(
        f"SELECT {_STATE_COLUMNS} FROM sync_state WHERE store_id = ?",  # nosec B608  # a fixed column list
        (store_id,),
    ).fetchone()
    return None if row is None else SyncStateRow(*row)


def record_read_started(connection: sqlite3.Connection, store_id: int, at: str) -> None:
    _begin(connection)
    try:
        _ensure_state(connection, store_id)
        connection.execute("UPDATE sync_state SET read_started_at = ? WHERE store_id = ?", (at, store_id))
        connection.execute("COMMIT")
    except BaseException:
        _rollback(connection)
        raise


def record_read_failed(
    connection: sqlite3.Connection,
    store_id: int,
    *,
    reason: str,
    http_status: int | None,
    pages: int,
    total: int | None,
    at: str,
) -> None:
    """A read that didn't work: its outcome only. The catalog data and `last_ok_at` stay as they were."""
    _begin(connection)
    try:
        _ensure_state(connection, store_id)
        connection.execute(
            "UPDATE sync_state SET read_finished_at = ?, read_reason = ?, read_http_status = ?, read_pages = ?, "
            "read_rows = 0, read_total = ? WHERE store_id = ?",
            (at, reason, http_status, pages, total, store_id),
        )
        connection.execute("COMMIT")
    except BaseException:
        _rollback(connection)
        raise


def record_failure(connection: sqlite3.Connection, store_id: int, reason: str, at: str, limit: int) -> bool:
    """One failed request (APL-12). True when the store is auto-paused now (this one reached `limit` in a row, or it
    already was)."""
    _begin(connection)
    try:
        _ensure_state(connection, store_id)
        connection.execute(
            "UPDATE sync_state SET failures_in_row = failures_in_row + 1 WHERE store_id = ?", (store_id,)
        )
        count, paused_at = connection.execute(
            "SELECT failures_in_row, auto_paused_at FROM sync_state WHERE store_id = ?", (store_id,)
        ).fetchone()
        paused = paused_at is not None or count >= limit
        if paused_at is None and count >= limit:
            connection.execute(
                "UPDATE sync_state SET auto_paused_at = ?, auto_pause_reason = ? WHERE store_id = ?",
                (at, reason, store_id),
            )
        connection.execute("COMMIT")
    except BaseException:
        _rollback(connection)
        raise
    return bool(paused)


def record_success(connection: sqlite3.Connection, store_id: int) -> None:
    """A request worked: the failures in a row go back to 0 (an auto-pause stays until the owner resumes)."""
    connection.execute(
        "UPDATE sync_state SET failures_in_row = 0 WHERE store_id = ? AND failures_in_row <> 0", (store_id,)
    )


def resume_store(connection: sqlite3.Connection, store_id: int) -> None:
    """The owner resumed an auto-paused store: the pause and the count are cleared."""
    connection.execute(
        "UPDATE sync_state SET auto_paused_at = NULL, auto_pause_reason = NULL, failures_in_row = 0 WHERE store_id = ?",
        (store_id,),
    )


# ---- saving a read -----------------------------------------------------------------------------------------------


@dataclass(frozen=True)
class SaveSummary:
    rows: int
    gone: int
    new_items: int
    new_links: int
    main_by_single: int  # products whose main slot came from the one-download rule
    unslotted: int  # downloads not put in a slot (a repeated name on one product)


def _downloads_json(product: Product) -> str:
    return json.dumps(
        [{"id": item.id, "name": item.name, "file": item.file} for item in product.downloads],
        ensure_ascii=False,
        separators=(",", ":"),
    )


def _meta_json(product: Product) -> str:
    return json.dumps([[key, value] for key, value in product.meta], ensure_ascii=False, separators=(",", ":"))


def known_links(connection: sqlite3.Connection) -> list[KnownLink]:
    """Every link on a store that isn't removed, with its product's slug and whether it is present."""
    rows = connection.execute(
        "SELECT l.catalog_item_id, l.store_id, l.wc_id, p.slug, p.gone_at IS NULL FROM item_link l "
        "JOIN store_product p ON p.store_id = l.store_id AND p.wc_id = l.wc_id "
        "JOIN store s ON s.id = l.store_id WHERE s.removed_at IS NULL"
    )
    return [KnownLink(item, store, wc_id, slug, bool(present)) for item, store, wc_id, slug, present in rows]


def _taken_slugs(connection: sqlite3.Connection) -> set[str]:
    rows = connection.execute("SELECT canonical_slug FROM catalog_item WHERE canonical_slug IS NOT NULL")
    return {row[0] for row in rows}


def _slots_of(connection: sqlite3.Connection, item_ids: Iterable[int]) -> dict[int, list[SlotRef]]:
    wanted = set(item_ids)
    found: dict[int, list[SlotRef]] = defaultdict(list)
    for slot_id, item_id, name, is_main in connection.execute(
        "SELECT id, catalog_item_id, name, is_main FROM slot ORDER BY id"
    ):
        if item_id in wanted:
            found[item_id].append(SlotRef(slot_id, name, bool(is_main)))
    return found


def save_store_read(
    connection: sqlite3.Connection,
    store_id: int,
    products: Sequence[Product],
    *,
    total: int | None,
    pages: int,
    at: str,
) -> SaveSummary:
    """Save one store's successful full read in one transaction (the module text says what that does). The main
    slot's name is the store's `main_button` as it is when the read is saved."""
    _begin(connection)
    try:
        row = connection.execute("SELECT main_button FROM store WHERE id = ?", (store_id,)).fetchone()
        if row is None:
            raise sqlite3.IntegrityError("no such store")
        summary = _save(connection, store_id, products, row[0], at)
        _ensure_state(connection, store_id)
        connection.execute(
            "UPDATE sync_state SET read_finished_at = ?, read_reason = NULL, read_http_status = NULL, read_pages = ?, "
            "read_rows = ?, read_total = ?, last_ok_at = ? WHERE store_id = ?",
            (at, pages, len(products), total, at, store_id),
        )
        connection.execute("COMMIT")
    except BaseException:
        _rollback(connection)
        raise
    return summary


def _save(
    connection: sqlite3.Connection, store_id: int, products: Sequence[Product], main_button: str, at: str
) -> SaveSummary:
    present_before = {
        row[0]
        for row in connection.execute(
            "SELECT wc_id FROM store_product WHERE store_id = ? AND gone_at IS NULL", (store_id,)
        )
    }
    connection.executemany(
        "INSERT INTO store_product (store_id, wc_id, slug, title, type, status, modified_gmt, downloads_json, "
        "meta_json, seen_at, gone_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL) "
        "ON CONFLICT (store_id, wc_id) DO UPDATE SET slug = excluded.slug, title = excluded.title, "
        "type = excluded.type, status = excluded.status, modified_gmt = excluded.modified_gmt, "
        "downloads_json = excluded.downloads_json, meta_json = excluded.meta_json, seen_at = excluded.seen_at, "
        "gone_at = NULL",
        [
            (
                store_id,
                product.wc_id,
                product.slug,
                product.title,
                product.type,
                product.status,
                product.modified_gmt,
                _downloads_json(product),
                _meta_json(product),
                at,
            )
            for product in products
        ],
    )
    gone = present_before - {product.wc_id for product in products}
    connection.executemany(
        "UPDATE store_product SET gone_at = ? WHERE store_id = ? AND wc_id = ?",
        [(at, store_id, wc_id) for wc_id in sorted(gone)],
    )

    plan = plan_links(store_id, products, known_links(connection), _taken_slugs(connection))
    new_ids: list[int] = []
    for item in plan.new_items:
        cursor = connection.execute(
            "INSERT INTO catalog_item (canonical_slug, title, type, created_at) VALUES (?, ?, ?, ?)",
            (item.canonical_slug, item.title, item.type, at),
        )
        if cursor.lastrowid is None:  # an INSERT always has one
            raise sqlite3.DatabaseError("the insert gave no row id")
        new_ids.append(cursor.lastrowid)
    connection.executemany(
        "INSERT INTO item_link (catalog_item_id, store_id, wc_id) VALUES (?, ?, ?)",
        [
            (link.item_id if link.item_id is not None else new_ids[link.new_item or 0], store_id, link.wc_id)
            for link in plan.links
        ],
    )

    item_of = {
        wc_id: item_id
        for item_id, wc_id in connection.execute(
            "SELECT catalog_item_id, wc_id FROM item_link WHERE store_id = ?", (store_id,)
        )
    }
    slots = _slots_of(connection, (item_of[product.wc_id] for product in products))
    connection.execute("DELETE FROM slot_download WHERE store_id = ?", (store_id,))
    main_by_single = 0
    unslotted = 0
    for product in products:
        item_id = item_of[product.wc_id]
        slot_plan = plan_slots(product.downloads, main_button, slots[item_id])
        main_by_single += slot_plan.main_by_single
        unslotted += slot_plan.unslotted
        new_slot_ids: list[int] = []
        for new_slot in slot_plan.new_slots:
            cursor = connection.execute(
                "INSERT INTO slot (catalog_item_id, name, is_main, slug) VALUES (?, ?, ?, NULL)",
                (item_id, new_slot.name, int(new_slot.is_main)),
            )
            if cursor.lastrowid is None:  # an INSERT always has one
                raise sqlite3.DatabaseError("the insert gave no row id")
            new_slot_ids.append(cursor.lastrowid)
            slots[item_id].append(SlotRef(cursor.lastrowid, new_slot.name, new_slot.is_main))
        connection.executemany(
            "INSERT INTO slot_download (slot_id, store_id, wc_download_id, file_url) VALUES (?, ?, ?, ?)",
            [
                (
                    assignment.slot_id if assignment.slot_id is not None else new_slot_ids[assignment.new_slot or 0],
                    store_id,
                    assignment.download.id,
                    assignment.download.file,
                )
                for assignment in slot_plan.assignments
            ],
        )
    return SaveSummary(len(products), len(gone), len(plan.new_items), len(plan.links), main_by_single, unslotted)


# ---- what the API reads ------------------------------------------------------------------------------------------


@dataclass(frozen=True)
class LinkRow:
    item_id: int
    store_id: int
    wc_id: int
    slug: str
    title: str
    status: str
    gone: bool


@dataclass(frozen=True)
class ItemRow:
    id: int
    canonical_slug: str | None
    title: str
    type: str
    created_at: str


@dataclass(frozen=True)
class SlotDownloadRow:
    store_id: int
    wc_download_id: str
    file_url: str


@dataclass(frozen=True)
class SlotRow:
    id: int
    name: str
    is_main: bool
    downloads: tuple[SlotDownloadRow, ...]


_LINKS = (
    "SELECT l.catalog_item_id, l.store_id, l.wc_id, p.slug, p.title, p.status, p.gone_at IS NOT NULL FROM item_link l "
    "JOIN store_product p ON p.store_id = l.store_id AND p.wc_id = l.wc_id "
    "JOIN store s ON s.id = l.store_id WHERE s.removed_at IS NULL"
)


def items(connection: sqlite3.Connection) -> list[ItemRow]:
    rows = connection.execute("SELECT id, canonical_slug, title, type, created_at FROM catalog_item ORDER BY id")
    return [ItemRow(*row) for row in rows]


def item(connection: sqlite3.Connection, item_id: int) -> ItemRow | None:
    row = connection.execute(
        "SELECT id, canonical_slug, title, type, created_at FROM catalog_item WHERE id = ?", (item_id,)
    ).fetchone()
    return None if row is None else ItemRow(*row)


def links(connection: sqlite3.Connection, item_id: int | None = None) -> list[LinkRow]:
    """The links on stores that aren't removed (of one item, or of every item), by item then store."""
    if item_id is None:
        rows = connection.execute(_LINKS + " ORDER BY l.catalog_item_id, l.store_id, l.wc_id")
    else:
        rows = connection.execute(
            _LINKS + " AND l.catalog_item_id = ? ORDER BY l.store_id, l.wc_id",  # nosec B608  # fixed text
            (item_id,),
        )
    return [LinkRow(a, b, c, d, e, f, bool(g)) for a, b, c, d, e, f, g in rows]


def slot_counts(connection: sqlite3.Connection) -> dict[int, int]:
    return dict(connection.execute("SELECT catalog_item_id, COUNT(*) FROM slot GROUP BY catalog_item_id"))


def slots(connection: sqlite3.Connection, item_id: int) -> list[SlotRow]:
    """One item's slots, the main one first, with their downloads on stores that aren't removed."""
    downloads: dict[int, list[SlotDownloadRow]] = defaultdict(list)
    for slot_id, store_id, download_id, file_url in connection.execute(
        "SELECT d.slot_id, d.store_id, d.wc_download_id, d.file_url FROM slot_download d "
        "JOIN slot t ON t.id = d.slot_id JOIN store s ON s.id = d.store_id "
        "WHERE t.catalog_item_id = ? AND s.removed_at IS NULL ORDER BY d.store_id",
        (item_id,),
    ):
        downloads[slot_id].append(SlotDownloadRow(store_id, download_id, file_url))
    rows = connection.execute(
        "SELECT id, name, is_main FROM slot WHERE catalog_item_id = ? ORDER BY is_main DESC, id", (item_id,)
    )
    return [SlotRow(slot_id, name, bool(is_main), tuple(downloads[slot_id])) for slot_id, name, is_main in rows]


def active_store_ids(connection: sqlite3.Connection) -> set[int]:
    return {row[0] for row in connection.execute("SELECT id FROM store WHERE removed_at IS NULL AND state = 'active'")}


def set_canonical_slug(connection: sqlite3.Connection, item_id: int, slug: str) -> bool:
    """False when there is no such item; `SlugTaken` when another item has the slug. Changes nothing on any store."""
    try:
        cursor = connection.execute("UPDATE catalog_item SET canonical_slug = ? WHERE id = ?", (slug, item_id))
    except sqlite3.IntegrityError:
        raise SlugTaken from None
    return cursor.rowcount > 0


def placed_products(connection: sqlite3.Connection) -> list[Placed]:
    """Every present product on a store that isn't removed, with its item: the input of `near_misses`."""
    return [
        Placed(link.item_id, link.store_id, link.wc_id, link.slug, link.title)
        for link in links(connection)
        if not link.gone
    ]

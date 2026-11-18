"""SYNC-01, SYNC-03, SYNC-04, CAT-02: the incremental save and the snapshot save (`db/catalog.py`,
`db/snapshots.py`): the watermark, products upserted, emptied downloads kept, new products linked or ignored, a repeat
changing nothing, the changes reported once, the snapshot states stored as changes, the nights a product can be
restored to, and retention."""

from contextlib import closing
from dataclasses import replace

import pytest

from shelfsync.catalog.model import Download, Product
from shelfsync.db import catalog as db
from shelfsync.db import snapshots
from tests.catalog_support import Db, make_db, product

AT = "2026-11-17T12:00:00.000000Z"
LATER = "2026-11-17T12:15:00.000000Z"
TABLES = ("store_product", "catalog_item", "item_link", "slot", "slot_download")


def p(wc_id: int, slug: str | None = None, *, modified: str = "2026-11-10T10:00:00", **changes: object) -> Product:
    return replace(product(wc_id, slug), modified_gmt=modified, **changes)  # type: ignore[arg-type]


def url_of(rig: Db, store_id: int) -> str:
    [(url,)] = rig.rows("SELECT url FROM store WHERE id = ?", store_id)
    return str(url)


def full(rig: Db, store_id: int, products: list[Product], at: str = AT) -> None:
    with closing(rig.connect()) as connection:
        db.save_store_read(
            connection, store_id, products, total=len(products), pages=1, at=at, read_url=url_of(rig, store_id)
        )


def inc(rig: Db, store_id: int, products: list[Product], at: str = LATER) -> db.ApplySummary:
    with closing(rig.connect()) as connection:
        return db.save_incremental(connection, store_id, products, at=at, read_url=url_of(rig, store_id))


def night(
    rig: Db,
    store_id: int,
    date: str,
    products: list[Product],
    variations: dict[int, list[Product]] | None = None,
    retention: int = 30,
) -> snapshots.SnapshotSummary:
    with closing(rig.connect()) as connection:
        snapshots.start_attempt(connection, store_id, date, AT)
        return snapshots.save_snapshot(
            connection,
            store_id,
            date,
            products,
            {key: tuple(value) for key, value in (variations or {}).items()},
            listing="include_status",
            at=f"{date}T02:05:00.000000Z",
            read_url=url_of(rig, store_id),
            retention_days=retention,
        )


def watermark(rig: Db, store_id: int) -> str | None:
    [(value,)] = rig.rows("SELECT watermark_gmt FROM sync_state WHERE store_id = ?", store_id)
    return None if value is None else str(value)


def dump(rig: Db) -> list[list[tuple[object, ...]]]:
    return [rig.rows(f"SELECT * FROM {table} ORDER BY 1, 2") for table in TABLES]


@pytest.fixture
def rig() -> Db:
    return make_db()


# ---- the watermark (SYNC-01) ---------------------------------------------------------------------------------------


def test_a_full_read_sets_the_watermark_to_the_largest_date_it_saved(rig: Db) -> None:
    gf = rig.add_store("GF")
    full(rig, gf, [p(1, modified="2026-11-10T08:00:00"), p(2, modified="2026-11-12T09:00:00"), p(3)])
    assert watermark(rig, gf) == "2026-11-12T09:00:00"


def test_the_watermark_moves_only_forward_and_only_from_store_dates(rig: Db) -> None:
    """SYNC-01: never back (an older date returned in the overlap), never from the PC's clock (an empty incremental
    leaves it), and a date more than a day past the PC's clock is never taken."""
    gf = rig.add_store("GF")
    full(rig, gf, [p(1, modified="2026-11-12T09:00:00")])
    inc(rig, gf, [p(1, modified="2026-11-12T08:59:00")])
    assert watermark(rig, gf) == "2026-11-12T09:00:00"
    inc(rig, gf, [])
    assert watermark(rig, gf) == "2026-11-12T09:00:00"
    inc(rig, gf, [p(2, modified="2026-11-15T07:30:00"), p(3, modified="2099-01-01T00:00:00")])
    assert watermark(rig, gf) == "2026-11-15T07:30:00"


# ---- the incremental save ------------------------------------------------------------------------------------------


def test_a_changed_product_is_saved_and_reported_with_its_before_and_after(rig: Db) -> None:
    gf = rig.add_store("GF")
    full(rig, gf, [p(1, "alpha"), p(2, "beta")])
    new_downloads = (Download("d1", "Download", "file-1-v2"),)
    summary = inc(rig, gf, [p(1, "alpha-renamed", downloads=new_downloads, modified="2026-11-12T00:00:00")])
    assert (summary.updated, summary.added, summary.ignored) == (1, 0, 0)
    [change] = summary.changes
    assert (change.kind, change.wc_id, change.fields, change.source) == (
        "changed",
        1,
        ("downloads", "slug"),
        "incremental",
    )
    assert change.before.slug == "alpha" and change.after is not None and change.after.downloads == new_downloads
    assert rig.rows("SELECT slug, downloads_json FROM store_product WHERE wc_id = 1") == [
        ("alpha-renamed", '[{"id":"d1","name":"Download","file":"file-1-v2"}]')
    ]
    assert sorted(rig.rows("SELECT file_url FROM slot_download")) == [("file-1-v2",), ("file-2",)]


def test_a_product_whose_downloads_were_removed_is_kept_with_them_emptied(rig: Db) -> None:
    gf = rig.add_store("GF")
    full(rig, gf, [p(1), p(2)])
    summary = inc(rig, gf, [p(1, downloads=())])
    assert [change.fields for change in summary.changes] == [("downloads",)]
    assert rig.rows("SELECT downloads_json, gone_at FROM store_product WHERE wc_id = 1") == [("[]", None)]
    assert rig.rows("SELECT d.store_id, t.catalog_item_id FROM slot_download d JOIN slot t ON t.id = d.slot_id") == [
        (gf, 2)
    ]


def test_a_new_product_is_linked_when_it_has_downloads_and_ignored_otherwise(rig: Db) -> None:
    """CAT-02 through an incremental: a new downloadable product joins the item with its slug on another store; a new
    non-downloadable one, and a new trashed one, are ignored."""
    gf = rig.add_store("GF")
    pw = rig.add_store("PW")
    full(rig, gf, [p(1, "jupiterx")])
    full(rig, pw, [p(50, "other")])
    summary = inc(rig, pw, [p(51, "jupiterx"), p(52, "service", downloads=()), p(53, "gone", status="trash")])
    assert (summary.added, summary.new_links, summary.new_items, summary.ignored, summary.changes) == (1, 1, 0, 2, ())
    assert rig.rows("SELECT catalog_item_id FROM item_link WHERE store_id = ? AND wc_id = 51", pw) == [(1,)]
    assert rig.rows("SELECT COUNT(*) FROM store_product WHERE wc_id IN (52, 53)") == [(0,)]


def test_the_same_incremental_saved_twice_changes_nothing_the_second_time(rig: Db) -> None:
    gf = rig.add_store("GF")
    full(rig, gf, [p(1), p(2)])
    batch = [p(1, "moved", modified="2026-11-12T00:00:00"), p(3, "new", modified="2026-11-12T00:01:00")]
    first = inc(rig, gf, batch)
    assert first.updated == 1 and first.added == 1
    before = dump(rig)
    again = inc(rig, gf, batch, at="2026-11-17T12:30:00.000000Z")
    assert (again.updated, again.added, again.changes) == (0, 0, ())
    assert dump(rig) == before


def test_an_incremental_on_a_store_whose_address_changed_saves_nothing(rig: Db) -> None:
    gf = rig.add_store("GF")
    full(rig, gf, [p(1)])
    before = dump(rig)
    with closing(rig.connect()) as connection, pytest.raises(db.AddressMoved):
        db.save_incremental(connection, gf, [p(1, "x")], at=LATER, read_url="https://elsewhere.example")
    assert dump(rig) == before


def test_a_failed_incremental_records_its_outcome_only(rig: Db) -> None:
    gf = rig.add_store("GF")
    full(rig, gf, [p(1, modified="2026-11-12T09:00:00")])
    with closing(rig.connect()) as connection:
        db.record_incremental_started(connection, gf, LATER)
        db.record_incremental_failed(connection, gf, reason="timeout", http_status=None, at=LATER)
    assert rig.rows(
        "SELECT inc_started_at, inc_reason, inc_last_ok_at, watermark_gmt FROM sync_state WHERE store_id = ?", gf
    ) == [(LATER, "timeout", None, "2026-11-12T09:00:00")]


# ---- the snapshot (SYNC-03, SYNC-04) -------------------------------------------------------------------------------


def test_a_trashed_and_a_deleted_product_are_reported_once(rig: Db) -> None:
    """SYNC-04: a catalog product now in the trash is `trashed`, one missing from the listing is `deleted`; both are
    gone from the catalog; the next night reports neither again."""
    gf = rig.add_store("GF")
    full(rig, gf, [p(1), p(2), p(3)])
    first = night(rig, gf, "2026-11-18", [p(1), p(2, status="trash")])
    kinds = sorted((change.kind, change.wc_id) for change in first.catalog.changes)
    assert kinds == [("deleted", 3), ("trashed", 2)]
    assert (first.products, first.trashed, first.not_seen) == (2, 1, 1)
    assert rig.rows("SELECT wc_id, status, gone_at IS NOT NULL FROM store_product ORDER BY wc_id") == [
        (1, "publish", 0),
        (2, "trash", 1),
        (3, "publish", 1),
    ]
    second = night(rig, gf, "2026-11-19", [p(1), p(2, status="trash")])
    assert second.catalog.changes == ()


def test_a_product_deleted_after_a_full_read_marked_it_gone_is_still_reported_when_last_night_saw_it(rig: Db) -> None:
    gf = rig.add_store("GF")
    full(rig, gf, [p(1), p(2)])
    night(rig, gf, "2026-11-18", [p(1), p(2, downloads=())])
    full(rig, gf, [p(1)])  # the full read (downloadable only) marks 2 gone
    summary = night(rig, gf, "2026-11-19", [p(1)])
    assert [(change.kind, change.wc_id) for change in summary.catalog.changes] == [("deleted", 2)]


def test_the_snapshot_never_adds_a_product_and_keeps_the_titles(rig: Db) -> None:
    gf = rig.add_store("GF")
    full(rig, gf, [p(1)])
    summary = night(rig, gf, "2026-11-18", [replace(p(1), title=""), p(9)])
    assert summary.catalog.ignored == 1
    assert rig.rows("SELECT wc_id, title FROM store_product") == [(1, "Product 1")]


def test_states_are_stored_as_changes_and_the_restore_dates_follow_them(rig: Db) -> None:
    """SYNC-03 Accept (the dates a product can be restored to): an unchanged product only moves its row's last
    night; a changed one gets a new row; a night it was missing breaks its run."""
    gf = rig.add_store("GF")
    full(rig, gf, [p(1), p(2)])
    night(rig, gf, "2026-11-18", [p(1), p(2)])
    night(rig, gf, "2026-11-19", [p(1), p(2, downloads=(Download("d2", "Download", "file-2-v2"),))])
    night(rig, gf, "2026-11-20", [p(1)])  # 2 missing
    night(rig, gf, "2026-11-21", [p(1), p(2, downloads=(Download("d2", "Download", "file-2-v2"),))])
    assert rig.rows("SELECT wc_id, first_night, last_night FROM snapshot_state ORDER BY wc_id, first_night") == [
        (1, "2026-11-18", "2026-11-21"),
        (2, "2026-11-18", "2026-11-18"),
        (2, "2026-11-19", "2026-11-19"),
        (2, "2026-11-21", "2026-11-21"),
    ]
    with closing(rig.connect()) as connection:
        assert snapshots.restorable_nights(connection, gf, 1) == [
            "2026-11-21",
            "2026-11-20",
            "2026-11-19",
            "2026-11-18",
        ]
        assert snapshots.restorable_nights(connection, gf, 2) == ["2026-11-21", "2026-11-19", "2026-11-18"]
        assert snapshots.restorable_nights(connection, gf, 99) == []


def test_a_failed_night_is_not_a_restore_date(rig: Db) -> None:
    gf = rig.add_store("GF")
    full(rig, gf, [p(1)])
    night(rig, gf, "2026-11-18", [p(1)])
    with closing(rig.connect()) as connection:
        snapshots.start_attempt(connection, gf, "2026-11-19", AT)
        snapshots.record_failed(connection, gf, "2026-11-19", reason="timeout", http_status=None, at=AT, retry_at=None)
    night(rig, gf, "2026-11-20", [p(1)])
    with closing(rig.connect()) as connection:
        assert snapshots.restorable_nights(connection, gf, 1) == ["2026-11-20", "2026-11-18"]


def test_variations_are_part_of_the_state(rig: Db) -> None:
    """V30: a variation's downloads changing makes a new state row for its product."""
    gf = rig.add_store("GF")
    parent = replace(p(2), type="variable", downloads=())
    full(rig, gf, [p(1)])
    edition = replace(p(21), type="variation", slug="", title="")
    night(rig, gf, "2026-11-18", [p(1), parent], {2: [edition]})
    changed = replace(edition, downloads=(Download("e", "Edition", "edition-v2"),))
    night(rig, gf, "2026-11-19", [p(1), parent], {2: [changed]})
    rows = rig.rows("SELECT first_night, variations_json FROM snapshot_state WHERE wc_id = 2 ORDER BY first_night")
    assert [first for first, _ in rows] == ["2026-11-18", "2026-11-19"]
    assert "edition-v2" in str(rows[1][1]) and '"variable"' not in str(rows[1][1])
    assert rig.rows("SELECT variable FROM snapshot_night WHERE night = '2026-11-19'") == [(1,)]


def test_retention_keeps_the_last_n_nights_and_the_rows_that_reach_them(rig: Db) -> None:
    """SYNC-03: kept 30 days (setting): here 3 nights."""
    gf = rig.add_store("GF")
    full(rig, gf, [p(1), p(2)])
    night(rig, gf, "2026-11-18", [p(1), p(2)], retention=3)
    night(rig, gf, "2026-11-19", [p(1)], retention=3)
    night(rig, gf, "2026-11-20", [p(1)], retention=3)
    summary = night(rig, gf, "2026-11-21", [p(1)], retention=3)
    assert (summary.pruned_nights, summary.pruned_rows) == (1, 1)  # the 18th, and product 2's row that ended then
    assert rig.rows("SELECT night FROM snapshot_night ORDER BY night") == [
        ("2026-11-19",),
        ("2026-11-20",),
        ("2026-11-21",),
    ]
    assert rig.rows("SELECT wc_id, first_night, last_night FROM snapshot_state") == [(1, "2026-11-18", "2026-11-21")]
    with closing(rig.connect()) as connection:
        assert snapshots.restorable_nights(connection, gf, 1) == ["2026-11-21", "2026-11-20", "2026-11-19"]


def test_a_night_takes_at_most_three_attempts_and_a_done_night_none(rig: Db) -> None:
    gf = rig.add_store("GF")
    with closing(rig.connect()) as connection:
        for expected in (1, 2, 3):
            assert snapshots.start_attempt(connection, gf, "2026-11-18", AT) == expected
            snapshots.record_failed(
                connection, gf, "2026-11-18", reason="timeout", http_status=None, at=AT, retry_at=LATER
            )
        with pytest.raises(ValueError):
            snapshots.start_attempt(connection, gf, "2026-11-18", AT)
        snapshots.record_skipped(connection, gf, "2026-11-19", reason="paused", at=AT)
        with pytest.raises(ValueError):
            snapshots.start_attempt(connection, gf, "2026-11-19", AT)
        row = snapshots.night_row(connection, gf, "2026-11-18")
    assert row is not None and (row.state, row.attempts, row.next_try_at) == ("retry", 3, LATER)


def test_a_snapshot_whose_store_was_removed_saves_nothing(rig: Db) -> None:
    gf = rig.add_store("GF")
    full(rig, gf, [p(1)])
    before = dump(rig)
    with closing(rig.connect()) as connection:
        connection.execute("UPDATE store SET removed_at = ? WHERE id = ?", (AT, gf))
        snapshots.start_attempt(connection, gf, "2026-11-18", AT)
        with pytest.raises(db.StoreRemoved):
            snapshots.save_snapshot(
                connection,
                gf,
                "2026-11-18",
                [p(1, status="trash")],
                {},
                listing="include_status",
                at=AT,
                read_url=url_of(rig, gf),
                retention_days=30,
            )
    assert dump(rig) == before
    assert rig.rows("SELECT COUNT(*) FROM snapshot_state") == [(0,)]

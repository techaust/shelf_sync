"""SYNC-01, SYNC-03, SYNC-04, CAT-02, APL-12: the incremental save and the snapshot save (`db/catalog.py`,
`db/snapshots.py`): the watermark stepped back by the read's duration (F3), one downloadable rule (F8), new products
added by either read, a repeat changing nothing, the changes reported once and handed to the sink inside the save's
transaction (F4), deleted only when confirmed (F2), the snapshot states stored as changes, the restore dates, and
retention per store, safe against a clock that jumped (F5)."""

import sqlite3
from contextlib import closing
from dataclasses import replace
from datetime import UTC, datetime
from typing import Any

import pytest

from shelfsync.catalog.changes import Change
from shelfsync.catalog.model import Download, Product
from shelfsync.db import catalog as db
from shelfsync.db import snapshots
from tests.catalog_support import Db, make_db, product

AT = "2026-11-17T12:00:00.000000Z"
LATER = "2026-11-17T12:15:00.000000Z"
TABLES = ("store_product", "catalog_item", "item_link", "slot", "slot_download")


def p(wc_id: int, slug: str | None = None, *, modified: str = "2026-11-10T10:00:00", **changes: Any) -> Product:
    return replace(product(wc_id, slug), modified_gmt=modified, **changes)


def url_of(rig: Db, store_id: int) -> str:
    [(url,)] = rig.rows("SELECT url FROM store WHERE id = ?", store_id)
    return str(url)


def full(rig: Db, store_id: int, products: list[Product], at: str = AT, seconds: int = 0) -> None:
    with closing(rig.connect()) as connection:
        db.save_store_read(
            connection,
            store_id,
            products,
            total=len(products),
            pages=1,
            at=at,
            read_url=url_of(rig, store_id),
            seconds=seconds,
        )


def inc(rig: Db, store_id: int, products: list[Product], at: str = LATER, **options: Any) -> db.ApplySummary:
    with closing(rig.connect()) as connection:
        return db.save_incremental(connection, store_id, products, at=at, read_url=url_of(rig, store_id), **options)


def night(
    rig: Db,
    store_id: int,
    date: str,
    products: list[Product],
    variations: dict[int, list[Product]] | None = None,
    retention: int = 30,
    deleted: tuple[int, ...] = (),
    **options: Any,
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
            deleted=deleted,
            **options,
        )


def watermark(rig: Db, store_id: int) -> str | None:
    [(value,)] = rig.rows("SELECT watermark_gmt FROM sync_state WHERE store_id = ?", store_id)
    return None if value is None else str(value)


def dump(rig: Db) -> list[list[tuple[object, ...]]]:
    return [rig.rows(f"SELECT * FROM {table} ORDER BY 1, 2") for table in TABLES]


@pytest.fixture
def rig() -> Db:
    return make_db()


# ---- the watermark (SYNC-01, F3) -----------------------------------------------------------------------------------


def test_a_full_read_sets_the_watermark_to_the_largest_date_it_saved_less_its_duration(rig: Db) -> None:
    gf = rig.add_store("GF")
    full(rig, gf, [p(1, modified="2026-11-10T08:00:00"), p(2, modified="2026-11-12T09:00:00"), p(3)], seconds=180)
    assert watermark(rig, gf) == "2026-11-12T08:57:00"


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


def test_an_edit_made_during_a_long_read_is_read_by_the_next_incremental(rig: Db) -> None:
    """F3: a 3-minute read passed product 1 at its start; product 1 was edited at 10:01, product 9 at 10:02 was read.
    The watermark steps back 3 minutes (09:59), so the next incremental's `modified_after` (09:57) includes 10:01."""
    from shelfsync.catalog.watermark import modified_after

    gf = rig.add_store("GF")
    full(rig, gf, [p(1, modified="2026-11-10T09:00:00")])
    inc(rig, gf, [p(9, "late", modified="2026-11-10T10:02:00")], seconds=180)
    assert watermark(rig, gf) == "2026-11-10T09:59:00"
    assert modified_after(str(watermark(rig, gf))) < "2026-11-10T10:01:00"


# ---- the incremental save and the downloadable rule (F8) -----------------------------------------------------------


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


def test_a_version_edit_is_reported_as_changed(rig: Db) -> None:
    """F11: the `latest_version*` meta is a change field (`version`)."""
    gf = rig.add_store("GF")
    full(rig, gf, [p(1, meta=(("latest_version", "1.0"),))])
    [change] = inc(rig, gf, [p(1, meta=(("latest_version", "1.1"),))]).changes
    assert change.fields == ("version",) and change.after is not None
    assert change.after.version == (("latest_version", "1.1"),)


def test_a_product_with_its_files_removed_but_still_downloadable_stays_present(rig: Db) -> None:
    gf = rig.add_store("GF")
    full(rig, gf, [p(1), p(2)])
    summary = inc(rig, gf, [p(1, downloads=())])
    assert [change.fields for change in summary.changes] == [("downloads",)]
    assert rig.rows("SELECT downloads_json, gone_at FROM store_product WHERE wc_id = 1") == [("[]", None)]


def test_a_product_whose_downloadable_flag_turns_off_is_gone_and_back_when_it_turns_on(rig: Db) -> None:
    """F8: the flag decides, not the files; reported `changed` with `downloadable`; no flip-flop with a full read."""
    gf = rig.add_store("GF")
    full(rig, gf, [p(1), p(2)])
    [change] = inc(rig, gf, [p(1, downloadable=False)]).changes
    assert (change.kind, change.fields) == ("changed", ("downloadable",))
    assert rig.rows("SELECT downloadable, gone_at IS NOT NULL FROM store_product WHERE wc_id = 1") == [(0, 1)]
    assert rig.rows(  # its slot download is gone with it
        "SELECT COUNT(*) FROM slot_download d JOIN slot t ON t.id = d.slot_id JOIN item_link l "
        "ON l.catalog_item_id = t.catalog_item_id AND l.store_id = d.store_id WHERE l.wc_id = 1"
    ) == [(0,)]
    assert inc(rig, gf, [p(1, downloadable=False)]).changes == ()  # again: no change
    night(rig, gf, "2026-11-18", [p(1, downloadable=False), p(2)])  # the snapshot agrees
    assert rig.rows("SELECT downloadable, gone_at IS NOT NULL FROM store_product WHERE wc_id = 1") == [(0, 1)]
    full(rig, gf, [p(2)])  # a full read (downloadable=true) doesn't hold it either: still gone
    assert rig.rows("SELECT gone_at IS NOT NULL FROM store_product WHERE wc_id = 1") == [(1,)]
    [back] = inc(rig, gf, [p(1)], at="2026-11-18T10:00:00.000000Z").changes
    assert back.fields == ("downloadable",)
    assert rig.rows("SELECT downloadable, gone_at FROM store_product WHERE wc_id = 1") == [(1, None)]


def test_a_new_product_is_added_when_downloadable_and_ignored_otherwise(rig: Db) -> None:
    """CAT-02 through an incremental: a new downloadable product joins the item with its slug on another store; a new
    non-downloadable one (whatever its files), and a new trashed one, are ignored."""
    gf = rig.add_store("GF")
    pw = rig.add_store("PW")
    full(rig, gf, [p(1, "jupiterx")])
    full(rig, pw, [p(50, "other")])
    summary = inc(
        rig,
        pw,
        [p(51, "jupiterx"), p(52, "service", downloadable=False), p(53, "gone", status="trash"), p(54, downloads=())],
    )
    assert (summary.added, summary.new_links, summary.ignored, summary.changes) == (2, 2, 2, ())
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


def test_an_incremental_on_a_store_whose_address_changed_saves_nothing_and_resets_nothing(rig: Db) -> None:
    gf = rig.add_store("GF")
    full(rig, gf, [p(1)])
    with closing(rig.connect()) as connection:
        connection.execute("UPDATE sync_state SET failures_in_row = 3 WHERE store_id = ?", (gf,))
    before = dump(rig)
    with closing(rig.connect()) as connection, pytest.raises(db.AddressMoved):
        db.save_incremental(connection, gf, [p(1, "x")], at=LATER, read_url="https://elsewhere.example")
    assert dump(rig) == before
    assert rig.rows("SELECT failures_in_row FROM sync_state") == [(3,)]


def test_a_failed_incremental_records_its_outcome_and_counts_once(rig: Db) -> None:
    gf = rig.add_store("GF")
    full(rig, gf, [p(1, modified="2026-11-12T09:00:00")])
    with closing(rig.connect()) as connection:
        db.record_incremental_started(connection, gf, LATER)
        assert db.record_incremental_failed(connection, gf, reason="timeout", http_status=None, at=LATER) is False
    assert rig.rows(
        "SELECT inc_started_at, inc_reason, inc_last_ok_at, watermark_gmt, failures_in_row FROM sync_state"
    ) == [(LATER, "timeout", None, "2026-11-12T09:00:00", 1)]


def test_the_change_sink_runs_inside_the_save_and_an_exception_rolls_it_back(rig: Db) -> None:
    """F4: m3.3's Cleanup rows are written in the save's transaction; a sink that raises leaves nothing saved."""
    gf = rig.add_store("GF")
    full(rig, gf, [p(1, "alpha")])
    seen: list[tuple[bool, int, list[Change]]] = []

    def sink(connection: sqlite3.Connection, store_id: int, changes: list[Change]) -> None:
        seen.append((connection.in_transaction, store_id, changes))

    inc(rig, gf, [p(1, "beta", modified="2026-11-12T00:00:00")], sink=sink)
    assert [(inside, store, [c.wc_id for c in changes]) for inside, store, changes in seen] == [(True, gf, [1])]
    before = [*dump(rig), rig.rows("SELECT * FROM sync_state")]

    def broken(connection: sqlite3.Connection, store_id: int, changes: list[Change]) -> None:
        raise RuntimeError("m3.3 failed")

    with pytest.raises(RuntimeError):
        inc(rig, gf, [p(1, "gamma", modified="2026-11-13T00:00:00")], at="2026-11-17T13:00:00.000000Z", sink=broken)
    assert [*dump(rig), rig.rows("SELECT * FROM sync_state")] == before
    with closing(rig.connect()) as connection, pytest.raises(RuntimeError):
        snapshots.start_attempt(connection, gf, "2026-11-18", AT)
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
            sink=broken,
        )
    assert rig.rows("SELECT COUNT(*) FROM snapshot_state") == [(0,)]
    assert rig.rows("SELECT status FROM store_product WHERE wc_id = 1") == [("publish",)]


# ---- the snapshot (SYNC-03, SYNC-04) -------------------------------------------------------------------------------


def test_a_trashed_and_a_confirmed_deleted_product_are_reported_once(rig: Db) -> None:
    """SYNC-04: a catalog product now in the trash is `trashed`, one a 404 confirmed is `deleted`; both are gone from
    the catalog; the next night reports neither again."""
    gf = rig.add_store("GF")
    full(rig, gf, [p(1), p(2), p(3)])
    first = night(rig, gf, "2026-11-18", [p(1), p(2, status="trash")], deleted=(3,))
    kinds = sorted((change.kind, change.wc_id) for change in first.catalog.changes)
    assert kinds == [("deleted", 3), ("trashed", 2)]
    assert (first.products, first.trashed, first.not_seen) == (2, 1, 1)
    assert rig.rows("SELECT wc_id, status, gone_at IS NOT NULL FROM store_product ORDER BY wc_id") == [
        (1, "publish", 0),
        (2, "trash", 1),
        (3, "publish", 1),
    ]
    second = night(rig, gf, "2026-11-19", [p(1), p(2, status="trash")])
    assert second.catalog.changes == () and second.not_seen == 0


def test_a_product_missing_from_the_listing_without_a_404_is_not_deleted(rig: Db) -> None:
    """F2: only `deleted` (a 404) deletes; a product merely absent from what the save is given is left as it is."""
    gf = rig.add_store("GF")
    full(rig, gf, [p(1), p(2)])
    summary = night(rig, gf, "2026-11-18", [p(1)])
    assert summary.catalog.changes == () and summary.not_seen == 0
    assert rig.rows("SELECT gone_at FROM store_product WHERE wc_id = 2") == [(None,)]


def test_not_seen_counts_only_products_present_before_the_save(rig: Db) -> None:
    """F10: a deleted product that was already gone (a full read had marked it) is reported, not counted."""
    gf = rig.add_store("GF")
    full(rig, gf, [p(1), p(2)])
    full(rig, gf, [p(1)])  # 2 gone
    summary = night(rig, gf, "2026-11-18", [p(1)], deleted=(2,))
    assert [change.kind for change in summary.catalog.changes] == ["deleted"] and summary.not_seen == 0


def test_the_snapshot_adds_new_downloadable_products_and_refreshes_titles(rig: Db) -> None:
    """F3: each night is a complete reconciliation (the incrementals can miss an edit)."""
    gf = rig.add_store("GF")
    full(rig, gf, [p(1)])
    summary = night(rig, gf, "2026-11-18", [replace(p(1), title="Renamed"), p(9, "nine"), p(10, downloadable=False)])
    assert (summary.catalog.added, summary.catalog.ignored) == (1, 1)
    assert rig.rows("SELECT wc_id, title FROM store_product ORDER BY wc_id") == [(1, "Renamed"), (9, "Product 9")]
    assert rig.rows("SELECT title FROM catalog_item ORDER BY id") == [("Renamed",), ("Product 9",)]


def test_states_are_stored_as_changes_and_the_restore_dates_follow_them(rig: Db) -> None:
    """SYNC-03 Accept (the dates a product can be restored to): an unchanged product only moves its row's last
    night; a changed one gets a new row; a night it was missing breaks its run."""
    gf = rig.add_store("GF")
    full(rig, gf, [p(1), p(2)])
    v2 = (Download("d2", "Download", "file-2-v2"),)
    night(rig, gf, "2026-11-18", [p(1), p(2)])
    night(rig, gf, "2026-11-19", [p(1), p(2, downloads=v2)])
    night(rig, gf, "2026-11-20", [p(1)])  # 2 not listed (no 404 asked for here)
    night(rig, gf, "2026-11-21", [p(1), p(2, downloads=v2)])
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


def test_the_downloadable_flag_is_part_of_the_state(rig: Db) -> None:
    gf = rig.add_store("GF")
    full(rig, gf, [p(1)])
    night(rig, gf, "2026-11-18", [p(1)])
    night(rig, gf, "2026-11-19", [p(1, downloadable=False)])
    assert rig.rows("SELECT downloadable, first_night FROM snapshot_state ORDER BY first_night") == [
        (1, "2026-11-18"),
        (0, "2026-11-19"),
    ]


def test_a_failed_night_is_not_a_restore_date_and_its_attempt_counts_once(rig: Db) -> None:
    gf = rig.add_store("GF")
    full(rig, gf, [p(1)])
    night(rig, gf, "2026-11-18", [p(1)])
    moment = datetime(2026, 11, 19, 2, 5, tzinfo=UTC)
    with closing(rig.connect()) as connection:
        snapshots.start_attempt(connection, gf, "2026-11-19", AT)
        assert (
            snapshots.record_failed(
                connection, gf, "2026-11-19", reason="timeout", http_status=None, at=moment, attempt=3
            )
            is False
        )
    assert rig.rows("SELECT state, next_try_at FROM snapshot_night WHERE night = '2026-11-19'") == [("failed", None)]
    assert rig.rows("SELECT failures_in_row FROM sync_state") == [(1,)]
    night(rig, gf, "2026-11-20", [p(1)])
    assert rig.rows("SELECT failures_in_row FROM sync_state") == [(0,)]  # a night that worked resets it
    with closing(rig.connect()) as connection:
        assert snapshots.restorable_nights(connection, gf, 1) == ["2026-11-20", "2026-11-18"]


def test_an_attempt_that_pauses_the_store_is_not_retried(rig: Db) -> None:
    """The retry is decided from the state written in the same transaction (F1)."""
    gf = rig.add_store("GF")
    full(rig, gf, [p(1)])
    with closing(rig.connect()) as connection:
        connection.execute("UPDATE sync_state SET failures_in_row = 9 WHERE store_id = ?", (gf,))
        snapshots.start_attempt(connection, gf, "2026-11-18", AT)
        paused = snapshots.record_failed(
            connection,
            gf,
            "2026-11-18",
            reason="server_error",
            http_status=500,
            at=datetime(2026, 11, 18, 2, 5, tzinfo=UTC),
            attempt=1,
        )
    assert paused
    assert rig.rows("SELECT state, next_try_at FROM snapshot_night") == [("failed", None)]
    assert rig.rows("SELECT failures_in_row, auto_pause_reason FROM sync_state") == [(10, "server_error")]


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
    assert "edition-v2" in str(rows[1][1])
    assert rig.rows("SELECT variable FROM snapshot_night WHERE night = '2026-11-19'") == [(1,)]


# ---- retention (SYNC-03, F5) ---------------------------------------------------------------------------------------


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


def test_a_clock_jump_forward_costs_at_most_the_nights_it_pushes_out(rig: Db) -> None:
    """F5: a night far ahead (a wrong clock) is kept with the store's newest N `ok` nights; the real ones before it
    stay, so the history isn't wiped."""
    gf = rig.add_store("GF")
    full(rig, gf, [p(1)])
    for date in ("2026-11-18", "2026-11-19", "2026-11-20"):
        night(rig, gf, date, [p(1)], retention=3)
    night(rig, gf, "2027-06-01", [p(1)], retention=3)
    assert rig.rows("SELECT night FROM snapshot_night ORDER BY night") == [
        ("2026-11-19",),
        ("2026-11-20",),
        ("2027-06-01",),
    ]
    with closing(rig.connect()) as connection:
        assert snapshots.restorable_nights(connection, gf, 1)[1:] == ["2026-11-20", "2026-11-19"]


def test_retention_is_per_store(rig: Db) -> None:
    gf = rig.add_store("GF")
    pw = rig.add_store("PW")
    full(rig, gf, [p(1)])
    full(rig, pw, [p(5)])
    night(rig, pw, "2026-11-01", [p(5)], retention=3)
    night(rig, gf, "2026-11-20", [p(1)], retention=3)
    assert rig.rows("SELECT store_id, night FROM snapshot_night ORDER BY store_id") == [
        (gf, "2026-11-20"),
        (pw, "2026-11-01"),
    ]


def test_a_night_ahead_of_the_pcs_clock_is_refused(rig: Db) -> None:
    """F5: a night later than the PC's night of the attempt's start plus a day isn't saved."""
    gf = rig.add_store("GF")
    full(rig, gf, [p(1)])
    assert snapshots.latest_allowed_night("2026-11-18") == "2026-11-19"
    with pytest.raises(snapshots.NightAhead):
        night(rig, gf, "2026-11-20", [p(1)], latest_night="2026-11-19")
    assert night(rig, gf, "2026-11-19", [p(1)], latest_night="2026-11-19").products == 1


def test_a_night_takes_at_most_three_attempts_and_a_done_night_none(rig: Db) -> None:
    gf = rig.add_store("GF")
    full(rig, gf, [p(1)])
    moment = datetime(2026, 11, 18, 2, 5, tzinfo=UTC)
    with closing(rig.connect()) as connection:
        for expected in (1, 2):
            assert snapshots.start_attempt(connection, gf, "2026-11-18", AT) == expected
            snapshots.record_failed(
                connection, gf, "2026-11-18", reason="timeout", http_status=None, at=moment, attempt=expected
            )
        assert snapshots.start_attempt(connection, gf, "2026-11-18", AT) == 3
        snapshots.record_failed(connection, gf, "2026-11-18", reason="timeout", http_status=None, at=moment, attempt=3)
        with pytest.raises(ValueError):
            snapshots.start_attempt(connection, gf, "2026-11-18", AT)
        snapshots.record_skipped(connection, gf, "2026-11-19", reason="paused", at=AT)
        with pytest.raises(ValueError):
            snapshots.start_attempt(connection, gf, "2026-11-19", AT)
        row = snapshots.night_row(connection, gf, "2026-11-18")
    assert row is not None and (row.state, row.attempts, row.next_try_at) == ("failed", 3, None)


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


def test_the_expected_products_are_the_present_ones_and_last_nights(rig: Db) -> None:
    """F2: what a snapshot must find or confirm deleted, and the catalog size for the cap."""
    gf = rig.add_store("GF")
    full(rig, gf, [p(1), p(2), p(3)])
    night(rig, gf, "2026-11-18", [p(1), p(2), p(3, downloadable=False)])
    with closing(rig.connect()) as connection:
        assert snapshots.expected_products(connection, gf) == ([1, 2, 3], 2)

"""CAT-01, CAT-02, CAT-04, CAT-05, APL-12, SYS-07: migration 0003 and the catalog tables (`db/catalog.py`): one store's
read saved in one transaction, links that never move, `gone_at`, slots, the sync state and the failure count."""

import sqlite3
from contextlib import closing

import pytest

from shelfsync.catalog.model import Download, Product
from shelfsync.db import catalog as db
from shelfsync.db.wizard import marks, set_mark
from tests.catalog_support import Db, make_db, product

AT = "2026-11-17T12:00:00.000000Z"
LATER = "2026-11-17T13:00:00.000000Z"


@pytest.fixture
def store() -> Db:
    return make_db()


def save(rig: Db, store_id: int, products: list[Product], at: str = AT) -> db.SaveSummary:
    with closing(rig.connect()) as connection:
        return db.save_store_read(connection, store_id, products, total=len(products), pages=1, at=at)


def links(rig: Db) -> list[tuple[int, int, int]]:
    return rig.rows("SELECT catalog_item_id, store_id, wc_id FROM item_link ORDER BY store_id, wc_id")


# ---- the schema ------------------------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("column", "value"),
    [
        ("slug", "s" * 201),
        ("title", "t" * 1001),
        ("type", ""),
        ("type", "x" * 41),
        ("status", "x" * 41),
        ("modified_gmt", "2026-10-25"),
        ("downloads_json", "not json"),
        ("downloads_json", "[" + "1," * 140000 + "1]"),
        ("meta_json", "{"),
        ("wc_id", 0),
    ],
    ids=lambda value: str(value)[:20],
)
def test_a_store_product_column_refuses_what_its_check_forbids(store: Db, column: str, value: object) -> None:
    store_id = store.add_store("GF")
    good = {
        "store_id": store_id,
        "wc_id": 1,
        "slug": "a",
        "title": "A",
        "type": "simple",
        "status": "publish",
        "modified_gmt": "2026-10-25T10:00:00",
        "downloads_json": "[]",
        "meta_json": "[]",
        "seen_at": AT,
    }
    good[column] = value
    with closing(store.connect()) as connection, pytest.raises(sqlite3.IntegrityError):
        connection.execute(
            f"INSERT INTO store_product ({', '.join(good)}) VALUES ({', '.join('?' * len(good))})",
            tuple(good.values()),
        )


def test_the_foreign_keys_refuse_a_link_to_a_product_that_is_not_there(store: Db) -> None:
    store_id = store.add_store("GF")
    with closing(store.connect()) as connection:
        connection.execute("INSERT INTO catalog_item (title, type, created_at) VALUES ('A', 'simple', ?)", (AT,))
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                "INSERT INTO item_link (catalog_item_id, store_id, wc_id) VALUES (1, ?, 99)", (store_id,)
            )


def test_two_items_may_have_no_slug_but_never_the_same_one(store: Db) -> None:
    with closing(store.connect()) as connection:
        for slug in (None, None, "x"):
            connection.execute(
                "INSERT INTO catalog_item (canonical_slug, title, type, created_at) VALUES (?, 'A', 'simple', ?)",
                (slug, AT),
            )
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                "INSERT INTO catalog_item (canonical_slug, title, type, created_at) VALUES ('x', 'B', 'simple', ?)",
                (AT,),
            )


# ---- saving a read ---------------------------------------------------------------------------------------------------


def test_the_first_store_makes_one_item_per_product_with_its_slug(store: Db) -> None:
    """CAT-01, CAT-04: each product gets an item whose canonical slug starts as its URL slug."""
    gf = store.add_store("GF")
    summary = save(store, gf, [product(1, "alpha"), product(2, "beta")])
    assert (summary.rows, summary.new_items, summary.new_links, summary.gone) == (2, 2, 2, 0)
    assert store.rows("SELECT id, canonical_slug, title FROM catalog_item ORDER BY id") == [
        (1, "alpha", "Product 1"),
        (2, "beta", "Product 2"),
    ]
    state = store.rows("SELECT read_reason, read_rows, read_total, last_ok_at FROM sync_state")
    assert state == [(None, 2, 2, AT)]


def test_the_second_store_links_by_identical_slug_and_the_rest_get_items_of_their_own(store: Db) -> None:
    """CAT-02: same URL slug on another store and none on this one: linked."""
    gf, pw = store.add_store("GF"), store.add_store("PW")
    save(store, gf, [product(1294, "jupiterx"), product(10, "only-gf")])
    save(store, pw, [product(1373, "jupiterx"), product(20, "only-pw")])
    assert links(store) == [(1, gf, 10), (2, gf, 1294), (3, pw, 20), (2, pw, 1373)]  # in WooCommerce id order


def test_ids_and_links_are_stable_across_two_reads_and_a_slug_change_does_not_move_a_link(store: Db) -> None:
    """CAT-02: an item is identified by its links; a re-read changes no id, and a slug edited on a store keeps its
    link (m3.3 reports the change)."""
    gf, pw = store.add_store("GF"), store.add_store("PW")
    save(store, gf, [product(1, "alpha"), product(2, "beta")])
    save(store, pw, [product(7, "alpha")])
    before = links(store)
    save(store, gf, [product(1, "alpha-renamed"), product(2, "beta")], at=LATER)
    save(store, pw, [product(7, "alpha")], at=LATER)
    assert links(store) == before
    assert store.rows("SELECT id, canonical_slug FROM catalog_item ORDER BY id") == [(1, "alpha"), (2, "beta")]
    assert store.rows("SELECT slug FROM store_product WHERE wc_id = 1") == [("alpha-renamed",)]


def test_a_product_no_longer_returned_gets_gone_at_and_is_never_deleted(store: Db) -> None:
    gf = store.add_store("GF")
    save(store, gf, [product(1), product(2)])
    summary = save(store, gf, [product(2)], at=LATER)
    assert summary.gone == 1
    assert store.rows("SELECT wc_id, gone_at FROM store_product ORDER BY wc_id") == [(1, LATER), (2, None)]
    assert len(links(store)) == 2  # the link stays
    save(store, gf, [product(1), product(2)], at="2026-11-17T14:00:00.000000Z")
    assert store.rows("SELECT wc_id, gone_at FROM store_product ORDER BY wc_id") == [(1, None), (2, None)]


def test_a_failed_save_changes_nothing_for_that_store(store: Db, monkeypatch: pytest.MonkeyPatch) -> None:
    """A read is saved in one transaction: a failure half way rolls back the rows, the links and the slots."""
    gf = store.add_store("GF")
    save(store, gf, [product(1, "alpha")])
    before = [store.rows(f"SELECT * FROM {table}") for table in ("store_product", "catalog_item", "item_link", "slot")]

    def broken(*_: object) -> object:
        raise sqlite3.OperationalError("disk I/O error")

    monkeypatch.setattr(db, "plan_slots", broken)
    with pytest.raises(sqlite3.OperationalError):
        save(store, gf, [product(1, "alpha"), product(2, "beta")], at=LATER)
    after = [store.rows(f"SELECT * FROM {table}") for table in ("store_product", "catalog_item", "item_link", "slot")]
    assert after == before
    assert store.rows("SELECT last_ok_at FROM sync_state") == [(AT,)]


def test_a_slug_held_as_an_owners_canonical_slug_gives_a_new_item_no_slug(store: Db) -> None:
    """CAT-04: the owner renamed item 1 to `alpha`; a later product with the URL slug `alpha` gets an item of its own
    with no canonical slug (never a made-up one), and the owner's slug stays."""
    gf, pw = store.add_store("GF"), store.add_store("PW")
    save(store, gf, [product(1, "jupiterx-website-builder")])
    with closing(store.connect()) as connection:
        assert db.set_canonical_slug(connection, 1, "alpha")
    save(store, pw, [product(5, "alpha")])
    assert store.rows("SELECT id, canonical_slug FROM catalog_item ORDER BY id") == [(1, "alpha"), (2, None)]
    assert links(store) == [(1, gf, 1), (2, pw, 5)]


def test_the_slug_edit_refuses_a_slug_another_item_has(store: Db) -> None:
    gf = store.add_store("GF")
    save(store, gf, [product(1, "alpha"), product(2, "beta")])
    with closing(store.connect()) as connection:
        with pytest.raises(db.SlugTaken):
            db.set_canonical_slug(connection, 2, "alpha")
        assert db.set_canonical_slug(connection, 2, "beta")  # its own slug again is fine
        assert not db.set_canonical_slug(connection, 99, "gamma")


def test_slots_pair_the_main_download_and_the_extras_by_name_across_stores(store: Db) -> None:
    """CAT-05: the multi-download products show all their slots with each store's download id."""
    gf, pw = store.add_store("GF"), store.add_store("PW", main_button="Get it")
    two = (Download("g-main", "Download", "f1"), Download("g-docs", "Documentation", "f2"))
    save(store, gf, [product(1694, "multi", downloads=two)])
    save(
        store,
        pw,
        [
            product(
                1821, "multi", downloads=(Download("p-docs", "Documentation", "f4"), Download("p-main", "Get it", "f3"))
            )
        ],
    )
    with closing(store.connect()) as connection:
        slots = db.slots(connection, 1)
    assert [(slot.name, slot.is_main) for slot in slots] == [("Download", True), ("Documentation", False)]
    assert [[(d.store_id, d.wc_download_id) for d in slot.downloads] for slot in slots] == [
        [(gf, "g-main"), (pw, "p-main")],
        [(gf, "g-docs"), (pw, "p-docs")],
    ]


def test_slot_ids_stay_the_same_across_reads(store: Db) -> None:
    gf = store.add_store("GF")
    save(store, gf, [product(1, "a", downloads=(Download("x", "Download", "f"), Download("y", "Extra", "g")))])
    first = store.rows("SELECT id, name FROM slot ORDER BY id")
    save(
        store, gf, [product(1, "a", downloads=(Download("x", "Download", "f2"), Download("y", "Extra", "g")))], at=LATER
    )
    assert store.rows("SELECT id, name FROM slot ORDER BY id") == first
    assert store.rows("SELECT file_url FROM slot_download ORDER BY slot_id") == [("f2",), ("g",)]


def test_a_gone_products_slot_downloads_go_but_its_slots_stay(store: Db) -> None:
    gf = store.add_store("GF")
    save(store, gf, [product(1), product(2)])
    save(store, gf, [product(2)], at=LATER)
    assert store.rows("SELECT COUNT(*) FROM slot") == [(2,)]
    assert store.rows("SELECT COUNT(*) FROM slot_download") == [(1,)]


def test_the_save_counts_main_slots_from_the_one_download_rule_and_unslotted_downloads(store: Db) -> None:
    gf = store.add_store("GF")
    summary = save(
        store,
        gf,
        [
            product(1, downloads=(Download("a", "Theme package", "f"),)),
            product(2, downloads=(Download("b", "Download", "f"), Download("c", "Download", "g"))),
        ],
    )
    assert (summary.main_by_single, summary.unslotted) == (1, 1)


def test_the_mirror_keeps_only_the_fields_fetched(store: Db) -> None:
    gf = store.add_store("GF")
    save(store, gf, [product(1)])
    columns = [row[1] for row in store.rows("PRAGMA table_info(store_product)")]
    assert columns == [
        "store_id",
        "wc_id",
        "slug",
        "title",
        "type",
        "status",
        "modified_gmt",
        "downloads_json",
        "meta_json",
        "seen_at",
        "gone_at",
    ]
    assert store.rows("SELECT downloads_json, meta_json FROM store_product") == [
        ('[{"id":"d1","name":"Download","file":"file-1"}]', "[]")
    ]


# ---- the sync state and the failure count ----------------------------------------------------------------------------


def test_ten_failures_in_a_row_auto_pause_and_resume_clears_it(store: Db) -> None:
    """APL-12: the 10th failure in a row pauses the store's sync; a success resets the count; resume clears both."""
    gf = store.add_store("GF")
    with closing(store.connect()) as connection:
        assert [db.record_failure(connection, gf, "server_error", AT, 10) for _ in range(9)] == [False] * 9
        db.record_success(connection, gf)
        assert db.sync_state(connection, gf).failures_in_row == 0  # type: ignore[union-attr]
        results = [db.record_failure(connection, gf, "cloudflare_52x", AT, 10) for _ in range(10)]
        assert results == [False] * 9 + [True]
        state = db.sync_state(connection, gf)
        assert state is not None
        assert (state.failures_in_row, state.auto_paused_at, state.auto_pause_reason) == (10, AT, "cloudflare_52x")
        db.record_success(connection, gf)  # a success doesn't lift an auto-pause: only the owner does
        assert db.sync_state(connection, gf).auto_paused_at == AT  # type: ignore[union-attr]
        db.resume_store(connection, gf)
        state = db.sync_state(connection, gf)
        assert state is not None and (state.failures_in_row, state.auto_paused_at) == (0, None)


def test_a_failed_read_is_recorded_without_touching_the_last_good_one(store: Db) -> None:
    gf = store.add_store("GF")
    save(store, gf, [product(1)])
    with closing(store.connect()) as connection:
        db.record_read_started(connection, gf, LATER)
        db.record_read_failed(connection, gf, reason="count_mismatch", http_status=None, pages=3, total=250, at=LATER)
        state = db.sync_state(connection, gf)
    assert state is not None
    assert (state.read_reason, state.read_total, state.last_ok_at, state.read_started_at) == (
        "count_mismatch",
        250,
        AT,
        LATER,
    )


def test_the_wizard_marks_are_saved_and_a_damaged_one_reads_as_not_done(store: Db) -> None:
    with closing(store.connect()) as connection:
        set_mark(connection, "test", True)
        set_mark(connection, "test", False)
        set_mark(connection, "storage", True)
        connection.execute("INSERT INTO wizard (step, state_json) VALUES ('catalog', '[1]')")
        assert marks(connection) == {"test": False, "storage": True, "catalog": False}

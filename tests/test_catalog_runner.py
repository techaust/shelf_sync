"""CAT-01, CAT-02, APL-12, ERR-02: the background catalog run (`catalog/runner.py`) over fake stores: one store after
another, links by slug, progress, paused and auto-paused stores skipped, the failure count across runs, resume, the
stop at shutdown changing nothing, and the client factory seam."""

import logging
import sqlite3
import threading
from contextlib import closing

import httpx
import pytest

from shelfsync.catalog import runner as runner_module
from shelfsync.catalog.runner import KeysMissing, SyncRunner
from shelfsync.db.catalog import clear_address_guard
from tests.catalog_support import CatalogRig, FakeCatalogStore, make_catalog_rig, raw_product, wait_for
from tests.store_support import system_status


def test_a_run_reads_every_store_one_after_another_and_links_by_slug() -> None:
    """CAT-01, CAT-02: each store's rows saved, shared slugs linked; the second store starts after the first ends."""
    rig = make_catalog_rig(fake_time=True)
    gf = rig.add_store("GF", [raw_product(10, "only-gf"), raw_product(1294, "jupiterx")])
    pw = rig.add_store("PW", [raw_product(1373, "jupiterx")])
    rig.run()
    hosts = [request.url.host for request in rig.sites.requests]
    assert hosts == ["store-gf.example"] * 2 + ["store-pw.example"] * 2  # never interleaved
    state = rig.service.runner.state()
    assert state.outcomes == {gf: None, pw: None} and not state.running and state.finished_at is not None
    assert rig.db.rows("SELECT catalog_item_id, store_id, wc_id FROM item_link ORDER BY store_id, wc_id") == [
        (1, gf, 10),
        (2, gf, 1294),
        (2, pw, 1373),
    ]
    assert rig.db.rows("SELECT store_id, read_reason, read_rows, read_total FROM sync_state ORDER BY store_id") == [
        (gf, None, 2, 2),
        (pw, None, 1, 1),
    ]


def test_ids_are_stable_across_two_runs() -> None:
    rig = make_catalog_rig(fake_time=True)
    rig.add_store("GF", [raw_product(1, "alpha"), raw_product(2, "beta")])
    rig.add_store("PW", [raw_product(7, "beta")])
    rig.run()
    first = rig.db.rows("SELECT * FROM item_link ORDER BY store_id, wc_id")
    items = rig.db.rows("SELECT id, canonical_slug FROM catalog_item ORDER BY id")
    rig.run()
    assert rig.db.rows("SELECT * FROM item_link ORDER BY store_id, wc_id") == first
    assert rig.db.rows("SELECT id, canonical_slug FROM catalog_item ORDER BY id") == items


def test_a_paused_store_is_skipped_and_shown_as_such() -> None:
    rig = make_catalog_rig(fake_time=True)
    gf = rig.add_store("GF", [raw_product(1)], state="paused")
    pw = rig.add_store("PW", [raw_product(2)])
    rig.run()
    assert rig.service.runner.state().outcomes == {gf: "paused", pw: None}
    assert {request.url.host for request in rig.sites.requests} == {"store-pw.example"}


def test_ten_failures_in_a_row_across_runs_auto_pause_the_store_until_it_is_resumed() -> None:
    """APL-12: every failed attempt counts and the count is kept across runs (4 per run: the request and its 3
    retries); at 10 the store is auto-paused, later runs skip it, and Resume clears it. `store.state` (the owner's
    pause) is never changed."""
    rig = make_catalog_rig(fake_time=True)
    gf = rig.add_store("GF", [raw_product(1)])
    rig.sites.stores["GF"].status_answer = httpx.Response(500)
    for expected in (4, 8):
        rig.run()
        assert rig.db.rows("SELECT failures_in_row, auto_paused_at FROM sync_state") == [(expected, None)]
    rig.run()
    [(count, paused_at, why)] = rig.db.rows("SELECT failures_in_row, auto_paused_at, auto_pause_reason FROM sync_state")
    assert (count, why) == (10, "server_error") and paused_at is not None
    assert rig.service.runner.state().outcomes == {gf: "server_error"}
    sent = len(rig.sites.requests)
    rig.run()
    assert rig.service.runner.state().outcomes == {gf: "auto_paused"} and len(rig.sites.requests) == sent
    assert rig.db.rows("SELECT state FROM store") == [("active",)]
    assert rig.service.resume(gf)
    rig.sites.stores["GF"].status_answer = None
    rig.run()
    assert rig.service.runner.state().outcomes == {gf: None}
    assert rig.db.rows("SELECT failures_in_row, auto_paused_at FROM sync_state") == [(0, None)]
    assert not rig.service.resume(999)


def test_a_524_and_a_429_are_replayed_and_the_run_still_saves() -> None:
    """APL-12 Accept, through the runner."""
    rig = make_catalog_rig(fake_time=True)
    gf = rig.add_store("GF", [raw_product(1)])
    rig.sites.stores["GF"].answers = [httpx.Response(524), httpx.Response(429, headers={"Retry-After": "3"})]
    rig.run()
    assert rig.service.runner.state().outcomes == {gf: None}
    assert rig.time is not None and rig.time.waits == [0.15, 2.0, 3.0]
    assert rig.db.rows("SELECT failures_in_row FROM sync_state") == [(0,)]


def test_a_store_below_5_8_and_one_with_no_products_fail_with_their_reasons_and_the_others_still_run() -> None:
    """ERR-02: the wizard stops at that store with the reason (shown from `sync_state`)."""
    rig = make_catalog_rig(fake_time=True)
    old = rig.add_store("GF", [raw_product(1)])
    rig.sites.stores["GF"].status_answer = system_status("5.7.0")
    empty = rig.add_store("PW", [])
    good = rig.add_store("TS", [raw_product(3)])
    rig.run()
    assert rig.service.runner.state().outcomes == {old: "wc_too_old", empty: "no_products", good: None}
    assert rig.db.rows("SELECT store_id, read_reason FROM sync_state ORDER BY store_id") == [
        (old, "wc_too_old"),
        (empty, "no_products"),
        (good, None),
    ]


def test_a_failed_read_changes_nothing_of_that_stores_catalog() -> None:
    rig = make_catalog_rig(fake_time=True)
    gf = rig.add_store("GF", [raw_product(1, "alpha"), raw_product(2, "beta")])
    rig.run()
    before = [rig.db.rows(f"SELECT * FROM {table}") for table in ("store_product", "catalog_item", "item_link", "slot")]
    rig.sites.stores["GF"].rows = [raw_product(1, "alpha")]
    rig.sites.stores["GF"].total_header = "5"  # a count that never matches
    rig.run()
    assert rig.service.runner.state().outcomes == {gf: "count_mismatch"}
    after = [rig.db.rows(f"SELECT * FROM {table}") for table in ("store_product", "catalog_item", "item_link", "slot")]
    assert after == before


def test_a_stop_during_a_read_saves_nothing_and_starts_no_other_store() -> None:
    """The app's shutdown: the store being read is left as it was, and no later store starts."""
    rig = make_catalog_rig(fake_time=True)
    gf = rig.add_store("GF", [raw_product(1, "alpha")])
    rig.add_store("PW", [raw_product(2, "alpha")])
    rig.run()
    before = [rig.db.rows(f"SELECT * FROM {table}") for table in ("store_product", "item_link", "sync_state")]
    assert rig.time is not None
    rig.sites.stores["GF"].rows = [raw_product(1, "alpha"), raw_product(3, "new")]
    rig.time.stop_after = len(rig.time.waits) + 1  # the stop arrives during the next wait (before GF's products page)
    assert rig.service.start_sync()
    rig.service.runner.join(30.0)
    assert rig.service.runner.state().outcomes == {gf: "stopped"}
    after = [rig.db.rows(f"SELECT * FROM {table}") for table in ("store_product", "item_link")]
    assert after == before[:2]
    assert rig.db.rows("SELECT read_reason FROM sync_state WHERE store_id = ?", gf) == [("stopped",)]


def test_a_read_that_finished_as_the_stop_came_is_not_saved() -> None:
    rig = make_catalog_rig(fake_time=True)
    gf = rig.add_store("GF", [raw_product(1)])
    assert rig.time is not None
    clock = rig.time
    rig.sites.stores["GF"].before_page = lambda page: clock.stop()  # the stop arrives while the last page is read
    rig.run()
    assert rig.service.runner.state().outcomes == {gf: "stopped"}
    assert rig.db.rows("SELECT COUNT(*) FROM store_product") == [(0,)]


def test_keys_missing_and_a_factory_error_are_outcomes_and_the_next_store_still_runs() -> None:
    rig = make_catalog_rig(fake_time=True)
    gf = rig.add_store("GF", [raw_product(1)])
    pw = rig.add_store("PW", [raw_product(2)])
    ts = rig.add_store("TS", [raw_product(3)])
    real = rig.service.runner._factory

    def factory(row):  # type: ignore[no-untyped-def]
        if row.id == gf:
            raise KeysMissing
        if row.id == pw:
            raise RuntimeError("a bug, with text that must not be logged")
        return real(row)

    rig.service.runner._factory = factory
    rig.run()
    assert rig.service.runner.state().outcomes == {gf: "keys_missing", pw: "internal", ts: None}


def _progress(rig: CatalogRig) -> tuple[int, int, int]:
    current = rig.service.runner.state().current
    assert current is not None
    return current.store_id, current.page, current.pages


def test_one_run_at_a_time_with_progress_while_it_runs() -> None:
    rig = make_catalog_rig()
    gf = rig.add_store("GF", [raw_product(n) for n in range(1, 151)], spacing_ms=50)
    gate = threading.Event()
    rig.sites.gate = gate
    assert rig.service.start_sync()
    assert not rig.service.start_sync()  # 409 in the API
    wait_for(lambda: rig.service.runner.state().current is not None)
    assert rig.service.runner.state().current.store_id == gf  # type: ignore[union-attr]
    seen: list[tuple[int, int, int]] = []
    rig.sites.stores["GF"].before_page = lambda page: seen.append(_progress(rig))
    gate.set()
    rig.service.runner.join(30.0)
    assert seen == [(gf, 0, 0), (gf, 1, 2)]  # before page 1, then before page 2: page 1 of 2 read, 100 rows
    state = rig.service.runner.state()
    assert not state.running and state.current is None and state.outcomes == {gf: None}
    assert rig.service.start_sync()  # free again
    rig.service.runner.join(30.0)


def test_stop_on_a_real_event_ends_a_run_that_waits_and_saves_nothing() -> None:
    rig = make_catalog_rig()
    gf = rig.add_store("GF", [raw_product(1)], spacing_ms=5000)  # a 5-second wait before the products page
    assert rig.service.start_sync()
    wait_for(lambda: len(rig.sites.requests) == 1)
    rig.service.stop()
    assert not rig.service.runner.state().running
    assert rig.service.runner.state().outcomes == {gf: "stopped"}
    assert rig.db.rows("SELECT COUNT(*) FROM store_product") == [(0,)]


def test_a_runner_with_no_store_finishes_at_once() -> None:
    rig = make_catalog_rig()
    runner: SyncRunner = rig.service.runner
    assert runner.start()
    runner.join(10.0)
    assert runner.state().outcomes == {} and not runner.state().running


def test_the_reader_gets_each_stores_own_spacing() -> None:
    rig = make_catalog_rig(fake_time=True)
    rig.add_store("GF", [raw_product(1)], spacing_ms=1000)
    rig.run()
    assert rig.time is not None and rig.time.waits == [1.0]


def test_a_store_page_never_carries_a_key_in_the_url() -> None:
    rig = make_catalog_rig(fake_time=True)
    rig.add_store("GF", [raw_product(1)])
    rig.run()
    assert all("consumer" not in str(request.url) and "ck_" not in str(request.url) for request in rig.sites.requests)
    assert isinstance(rig.sites.stores["GF"], FakeCatalogStore)


# ---- the analyst's findings (m3.1 early check) ---------------------------------------------------------------------


def test_a_store_whose_address_changed_is_refused_before_any_request_and_keeps_its_catalog() -> None:
    """Finding 2: links are keyed by (store, WooCommerce id), so another shop's products would take the old ones'
    places. Refused with `address_changed` until the guard is cleared (a later task decides how)."""
    rig = make_catalog_rig(fake_time=True)
    gf = rig.add_store("GF", [raw_product(1, "alpha")])
    rig.run()
    before = rig.db.rows("SELECT * FROM store_product")
    with closing(rig.db.connect()) as connection:
        connection.execute("UPDATE store SET url = 'https://store-pw.example' WHERE id = ?", (gf,))
    rig.sites.stores["PW"] = FakeCatalogStore(rows=[raw_product(1, "other-shops-product")])
    sent = len(rig.sites.requests)
    rig.run()
    assert rig.service.runner.state().outcomes == {gf: "address_changed"}
    assert len(rig.sites.requests) == sent  # nothing was asked of the new address
    assert rig.db.rows("SELECT * FROM store_product") == before
    assert rig.db.rows("SELECT read_reason FROM sync_state") == [("address_changed",)]
    with closing(rig.db.connect()) as connection:
        clear_address_guard(connection, gf)
    rig.run()
    assert rig.service.runner.state().outcomes == {gf: None}


def test_an_address_changed_during_a_read_saves_nothing() -> None:
    rig = make_catalog_rig(fake_time=True)
    gf = rig.add_store("GF", [raw_product(1, "alpha")])

    def move(page: int) -> None:
        with closing(rig.db.connect()) as connection:
            connection.execute("UPDATE store SET url = 'https://moved.example' WHERE id = ?", (gf,))

    rig.sites.stores["GF"].before_page = move
    rig.run()
    assert rig.service.runner.state().outcomes == {gf: "address_changed"}
    assert rig.db.rows("SELECT COUNT(*) FROM store_product") == [(0,)]
    assert rig.db.rows("SELECT read_reason FROM sync_state") == [("address_changed",)]


def test_a_database_error_during_the_save_is_recorded_on_a_fresh_connection(monkeypatch: pytest.MonkeyPatch) -> None:
    """Finding 1 (c): the outcome reaches `sync_state` even though the read's own connection failed."""
    rig = make_catalog_rig(fake_time=True)
    gf = rig.add_store("GF", [raw_product(1)])

    def broken(*_: object, **__: object) -> None:
        raise sqlite3.OperationalError("disk I/O error")

    monkeypatch.setattr(runner_module, "save_store_read", broken)
    rig.run()
    assert rig.service.runner.state().outcomes == {gf: "database_error"}
    assert rig.db.rows("SELECT read_reason FROM sync_state") == [("database_error",)]


def test_an_outcome_that_cannot_be_recorded_at_all_is_only_logged(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    rig = make_catalog_rig(fake_time=True)
    gf = rig.add_store("GF", [raw_product(1)])

    def broken(*_: object, **__: object) -> None:
        raise RuntimeError("a bug")

    monkeypatch.setattr(runner_module, "save_store_read", broken)
    monkeypatch.setattr(runner_module, "record_read_failed", broken)
    caplog.set_level(logging.ERROR, logger="shelfsync.catalog")
    rig.run()
    assert rig.service.runner.state().outcomes == {gf: "internal"}
    assert any("couldn't be recorded (RuntimeError)" in record.getMessage() for record in caplog.records)
    assert all("a bug" not in record.getMessage() for record in caplog.records)


def test_after_stop_no_run_starts() -> None:
    """Finding 6: a `POST /api/sync` after the shutdown must not start a run."""
    rig = make_catalog_rig()
    rig.add_store("GF", [raw_product(1)])
    rig.service.stop()
    assert not rig.service.start_sync()
    assert rig.sites.requests == []

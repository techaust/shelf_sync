"""m3.2 review 1 (SYNC-01, SYNC-03, SYNC-04, SYNC-05, APL-12): a bulk deletion clears over a few nights without failing
one; a partly honoured listing never deletes; a full read reports the outside changes it brings; a full read with no
usable date keeps the watermark; a busy or broken night start is deferred without using an attempt; a stopped attempt
gives its attempt back; "auto-paused by this read" only."""

import logging
import sqlite3
from contextlib import closing
from datetime import UTC, datetime, timedelta

import pytest

from shelfsync.catalog import runner as runner_module
from shelfsync.catalog.runner import RunPlan
from shelfsync.db import catalog as db
from shelfsync.db import snapshots
from tests.store_support import PRODUCTS
from tests.sync_support import SyncRig, make_sync_rig, row

START = datetime(2026, 11, 18, 10, 0, tzinfo=UTC)


def night(rig: SyncRig, day: int) -> None:
    rig.at(datetime(2026, 11, day, 10, 30, tzinfo=UTC))
    assert rig.service.runner.start(RunPlan("snapshot", night=f"2026-11-{day}"))
    rig.service.runner.join(60.0)


def deleted_reports(rig: SyncRig) -> list[int]:
    return [change.wc_id for _, found in rig.changes for change in found if change.kind == "deleted"]


def by_id_requests(rig: SyncRig, code: str) -> int:
    store = rig.store(code)
    return sum(1 for request in store.requests if request.url.path.startswith(PRODUCTS + "/"))


# ---- the high finding: a bulk deletion -----------------------------------------------------------------------------


def test_25_purged_products_clear_over_two_nights_each_reported_deleted_once() -> None:
    """425 products, 25 trashed then purged from the trash: the cap is 20 (5 % of 400 present, at most 20), so the
    first night confirms 20 and leaves 5, the second confirms the 5; both nights `ok`."""
    rig = make_sync_rig(START)
    gf = rig.add_store("GF", [row(wc_id) for wc_id in range(1, 426)])
    rig.run("full")
    store = rig.store("GF")
    purged = list(range(401, 426))
    for wc_id in purged:
        store.find(wc_id)["status"] = "trash"
    night(rig, 18)  # the trashing is seen
    store.rows = [item for item in store.rows if item["id"] not in purged]  # emptied from the trash
    night(rig, 19)
    night(rig, 20)
    night(rig, 21)
    assert rig.rows("SELECT night, state, unconfirmed, not_seen FROM snapshot_night WHERE store_id = ?", gf) == [
        ("2026-11-18", "ok", 0, 0),
        ("2026-11-19", "ok", 5, 0),  # not_seen counts present rows only: these were gone (trashed) already
        ("2026-11-20", "ok", 0, 0),
        ("2026-11-21", "ok", 0, 0),
    ]
    assert sorted(deleted_reports(rig)) == purged  # each exactly once
    assert rig.rows("SELECT COUNT(*) FROM store_product WHERE deleted_at IS NOT NULL") == [(25,)]
    assert by_id_requests(rig, "GF") == 25  # 20, then 5, then none


def test_a_listing_that_leaves_drafts_out_never_deletes_them_and_asks_for_cap_a_night() -> None:
    """A partly honoured `include_status`: the drafts are missing from the listing but exist. 100 products, cap 5:
    each night 5 are asked for (200: read), the rest left unconfirmed; nothing deleted; the night `ok`."""
    rig = make_sync_rig(START)
    rows = [row(wc_id) for wc_id in range(1, 91)] + [row(wc_id, status="draft") for wc_id in range(91, 101)]
    gf = rig.add_store("GF", rows)
    rig.run("full")
    rig.store("GF").unlisted = set(range(91, 101))
    night(rig, 18)
    night(rig, 19)
    assert rig.rows("SELECT state, unconfirmed FROM snapshot_night WHERE store_id = ?", gf) == [("ok", 5), ("ok", 5)]
    assert deleted_reports(rig) == []
    assert rig.rows("SELECT COUNT(*) FROM store_product WHERE gone_at IS NOT NULL OR deleted_at IS NOT NULL") == [(0,)]
    assert by_id_requests(rig, "GF") == 10  # 5 a night


# ---- the medium finding: a full read reports outside changes -------------------------------------------------------


def test_a_change_brought_by_a_full_read_is_reported_once() -> None:
    rig = make_sync_rig(START)
    rig.add_store("GF", [row(1, "alpha"), row(2, "beta")])
    rig.run("full")
    rig.store("GF").find(1)["slug"] = "alpha-renamed"
    rig.run("full")  # the wizard's Build catalog, again
    found = [
        (change.kind, change.wc_id, change.fields, change.source) for _, changes in rig.changes for change in changes
    ]
    assert found == [("changed", 1, ("slug",), "full")]
    rig.run("incremental")
    assert len(rig.changes) == 1  # not again


# ---- the lows --------------------------------------------------------------------------------------------------------


def test_a_full_read_with_no_usable_date_keeps_the_watermark() -> None:
    rig = make_sync_rig(START)
    rig.add_store("GF", [row(1, modified="2026-11-12T09:00:00")])
    rig.run("full")
    rig.store("GF").rows = [row(1, modified=None)]
    rig.run("full")
    assert rig.rows("SELECT watermark_gmt FROM sync_state") == [("2026-11-12T09:00:00",)]


def test_a_busy_slot_defers_the_night_five_minutes_without_using_an_attempt() -> None:
    rig = make_sync_rig(START)
    gf = rig.add_store("GF", [row(1)])
    rig.run("full")
    assert rig.stores.slots.claim(gf)  # a Test connection holds the slot for the whole wait
    try:
        assert rig.service.runner.start(RunPlan("snapshot", night="2026-11-18"))
        rig.service.runner.join(60.0)
    finally:
        rig.stores.slots.release(gf)
    [(state, attempts, reason, next_try, finished)] = rig.rows(
        "SELECT state, attempts, reason, next_try_at, finished_at FROM snapshot_night"
    )
    assert (state, attempts, reason) == ("retry", 0, "busy")
    assert datetime.fromisoformat(next_try) - datetime.fromisoformat(finished) == timedelta(minutes=5)
    assert rig.rows("SELECT failures_in_row FROM sync_state") == [(0,)]
    assert rig.service.scheduler.snapshot_plan(rig.time.wall()) is None  # not picked at every check


def test_a_database_error_before_the_attempt_defers_the_night_too(monkeypatch: pytest.MonkeyPatch) -> None:
    rig = make_sync_rig(START)
    rig.add_store("GF", [row(1)])
    rig.run("full")

    def broken(self: object, store_id: int, plan: RunPlan) -> str | None:
        raise sqlite3.OperationalError("database is locked")

    monkeypatch.setattr(runner_module.SyncRunner, "_skip_reason", broken)
    assert rig.service.runner.start(RunPlan("snapshot", night="2026-11-18"))
    rig.service.runner.join(60.0)
    assert rig.rows("SELECT state, attempts, reason FROM snapshot_night") == [("retry", 0, "database_error")]


def test_a_stopped_attempt_gives_its_attempt_back() -> None:
    rig = make_sync_rig(START)
    gf = rig.add_store("GF", [row(1)])
    rig.run("full")
    moment = datetime(2026, 11, 18, 2, 5, tzinfo=UTC)
    with closing(rig.db.connect()) as connection:
        for _ in range(3):
            attempt = snapshots.start_attempt(connection, gf, "2026-11-18", "t")
            snapshots.record_failed(
                connection, gf, "2026-11-18", reason="stopped", http_status=None, at=moment, attempt=attempt
            )
        row_now = snapshots.night_row(connection, gf, "2026-11-18")
    assert row_now is not None and (row_now.state, row_now.attempts) == ("retry", 0)
    assert row_now.next_try_at == "2026-11-18T02:05:00.000000Z"  # due at the next start


def test_count_failed_read_says_paused_only_for_the_read_that_paused(caplog: pytest.LogCaptureFixture) -> None:
    rig = make_sync_rig(START)
    gf = rig.add_store("GF", [row(1)])
    with closing(rig.db.connect()) as connection:
        results = [
            db.record_incremental_failed(connection, gf, reason="timeout", http_status=None, at="t") for _ in range(11)
        ]
    assert results == [False] * 9 + [True, False]
    rig.run("full")  # the store is auto-paused: skipped, nothing logged as a new pause
    with caplog.at_level(logging.WARNING, logger="shelfsync.catalog"):
        rig.store("GF").fail = lambda request: None
        rig.run("incremental")
    assert "now auto-paused" not in caplog.text

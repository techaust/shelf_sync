"""SYNC-01, SYNC-03, SYNC-04, SYNC-05, APL-12, V28, V30: the incremental and the snapshot through the runner on fake
stores: Sync now incremental once a catalog exists, an edit seen and a repeat changing nothing, the watermark moving
only after a read that worked, the changes handed on, the trash listing's fallback recorded, variations, the 50
variable products limit, retention from its setting, a stop saving nothing, only GETs, and nothing secret logged."""

from contextlib import closing
from datetime import UTC, datetime
from pathlib import Path

import httpx
import pytest

from shelfsync import logs
from shelfsync.catalog.changes import Change
from shelfsync.catalog.runner import RunPlan
from tests.catalog_support import download
from tests.store_support import KEY, PRODUCTS, SECRET
from tests.sync_support import SyncRig, make_sync_rig, row, variation

START = datetime(2026, 11, 18, 10, 0, tzinfo=UTC)
TABLES = ("store_product", "catalog_item", "item_link", "slot", "slot_download")


def rig_with(*codes: str) -> tuple[SyncRig, dict[str, int]]:
    rig = make_sync_rig(START)
    ids = {code: rig.add_store(code, [row(1, "alpha"), row(2, "beta")]) for code in codes}
    assert rig.run() == "full"  # Sync now before any catalog: a full read
    return rig, ids


def snapshot(rig: SyncRig, night: str = "2026-11-18") -> None:
    assert rig.service.runner.start(RunPlan("snapshot", night=night, scheduled=True))
    rig.service.runner.join(30.0)


def dump(rig: SyncRig) -> list[list[tuple[object, ...]]]:
    return [rig.rows(f"SELECT * FROM {table} ORDER BY 1, 2") for table in TABLES]


def all_changes(rig: SyncRig) -> list[Change]:
    return [change for _, found in rig.changes for change in found]


# ---- Sync now (SYNC-05) and the incremental (SYNC-01) --------------------------------------------------------------


def test_sync_now_is_incremental_once_every_active_store_has_a_full_read() -> None:
    rig, _ = rig_with("GF", "PW")
    assert rig.run() == "incremental"
    assert rig.run("full") == "full"  # the wizard's Build catalog asks for one
    rig.add_store("TS", [row(9)])  # a store with no full read yet: Sync now reads in full again
    assert rig.run() == "full"
    with closing(rig.db.connect()) as connection:
        connection.execute("UPDATE store SET state = 'paused' WHERE code = 'TS'")
    assert rig.run() == "incremental"  # a paused store doesn't count


def test_an_edit_on_the_store_is_seen_by_the_next_incremental_and_a_repeat_changes_nothing() -> None:
    """SYNC-01 Accept, on a fake store: the edit is saved and handed on as a change; the next incremental reads it
    again (the overlap) and changes nothing."""
    rig, ids = rig_with("GF")
    gf = ids["GF"]
    edited = rig.store("GF").find(1)
    edited["slug"] = "alpha-new"
    edited["date_modified_gmt"] = "2026-11-18T09:59:00"
    assert rig.run("incremental") == "incremental"
    assert rig.service.runner.state().outcomes == {gf: None}
    [change] = all_changes(rig)
    assert (change.kind, change.wc_id, change.fields) == ("changed", 1, ("slug",))
    assert rig.rows("SELECT watermark_gmt, inc_rows, inc_changed, inc_reason FROM sync_state") == [
        ("2026-11-18T09:59:00", 2, 1, None)  # product 2 sits at the old watermark: read again, unchanged
    ]
    before = dump(rig)
    rig.run("incremental")
    assert dump(rig) == before and len(rig.changes) == 1
    assert rig.rows("SELECT inc_rows, inc_changed FROM sync_state") == [(1, 0)]
    since = [request.url.params.get("modified_after") for request in rig.store("GF").product_requests()]
    assert since[-1] == "2026-11-18T09:57:00"


def test_a_failed_incremental_leaves_the_watermark_and_the_catalog_as_they_were() -> None:
    rig, ids = rig_with("GF")
    [(watermark,)] = rig.rows("SELECT watermark_gmt FROM sync_state")
    rig.store("GF").find(1)["date_modified_gmt"] = "2026-11-18T09:00:00"
    rig.store("GF").fail = lambda request: httpx.Response(500) if request.url.path.endswith(PRODUCTS) else None
    before = dump(rig)
    rig.run("incremental")
    assert rig.service.runner.state().outcomes == {ids["GF"]: "server_error"}
    assert dump(rig) == before
    assert rig.rows("SELECT watermark_gmt, inc_reason, inc_http_status, failures_in_row FROM sync_state") == [
        (watermark, "server_error", 500, 1)  # one failed read (APL-12 counts reads)
    ]


def test_an_edit_to_a_low_id_product_during_a_three_minute_read_is_caught_by_the_next_incremental() -> None:
    """F3: products 1-150 were bulk-edited at 10:00 and product 250 at 10:03; the incremental reads page 1, is held
    3 minutes on page 2 (a 429 with `Retry-After: 60`, three times), and meanwhile product 1 is edited again at
    10:00:30. The read ends with product 1's older state; the watermark steps back by the read's duration, so the next
    incremental asks from before 10:00:30 and saves product 1's new state."""
    rig = make_sync_rig(START)
    rig.add_store("GF", [row(wc_id, modified="2026-11-17T09:00:00") for wc_id in range(1, 251)])
    rig.run("full")
    store = rig.store("GF")
    for wc_id in range(1, 151):
        store.find(wc_id)["date_modified_gmt"] = "2026-11-18T10:00:00"
    store.find(250)["date_modified_gmt"] = "2026-11-18T10:03:00"
    held = {"page_two": 0}

    def slow_page_two(request: httpx.Request) -> httpx.Response | None:
        on_page_two = request.url.path.endswith(PRODUCTS) and request.url.params.get("page") == "2"
        if on_page_two and held["page_two"] < 3:
            held["page_two"] += 1
            if held["page_two"] == 1:
                store.find(1)["slug"] = "edited-during-the-read"
                store.find(1)["date_modified_gmt"] = "2026-11-18T10:00:30"
            return httpx.Response(429, headers={"Retry-After": "60"})
        return None

    store.fail = slow_page_two
    first_slug = store.find(1)["slug"]  # what page 1 reads (the edit lands while page 2 is held)
    rig.run("incremental")
    [(watermark,)] = rig.rows("SELECT watermark_gmt FROM sync_state")
    assert watermark < "2026-11-18T10:00:30"  # 10:03 less more than 3 minutes
    assert rig.rows("SELECT slug FROM store_product WHERE wc_id = 1") == [(first_slug,)]  # the read's older state
    store.fail = None
    rig.run("incremental")
    assert rig.rows("SELECT slug FROM store_product WHERE wc_id = 1") == [("edited-during-the-read",)]


def test_an_incremental_skips_a_store_with_no_full_read_and_reads_the_others() -> None:
    rig, ids = rig_with("GF")
    new = rig.add_store("PW", [row(5)])
    rig.run("incremental")
    assert rig.service.runner.state().outcomes == {ids["GF"]: None, new: "no_full_read"}
    assert not any(request.url.host == "store-pw.example" for request in rig.sites.requests)


# ---- the snapshot (SYNC-03, SYNC-04) -------------------------------------------------------------------------------


def test_the_snapshot_finds_a_product_trashed_and_one_deleted_outside_shelfsync() -> None:
    """SYNC-04 Accept, on a fake store: the changes are handed on (m3.3 makes them Cleanup issues)."""
    rig, ids = rig_with("GF")
    gf = ids["GF"]
    store = rig.store("GF")
    store.find(2)["status"] = "trash"
    store.rows.append(row(3, "old-slider__trashed", status="trash"))  # in the trash, never in the catalog
    snapshot(rig)
    store.rows = [item for item in store.rows if item["id"] != 1]  # deleted the next day
    snapshot(rig, "2026-11-19")
    kinds = [(change.kind, change.wc_id, change.source) for change in all_changes(rig)]
    assert kinds == [("trashed", 2, "snapshot"), ("deleted", 1, "snapshot")]
    assert {store_id for store_id, _ in rig.changes} == {gf}
    assert rig.rows("SELECT night, state, listing, products, trashed, not_seen FROM snapshot_night") == [
        ("2026-11-18", "ok", "include_status", 3, 2, 0),
        ("2026-11-19", "ok", "include_status", 2, 2, 1),
    ]


@pytest.mark.parametrize("behaviour", ["refused", "ignored", "any_only"])
def test_the_night_records_the_two_listing_fallback(behaviour: str) -> None:
    """V28 (not verified on a store): the night says which listing was used."""
    rig, _ = rig_with("GF")
    rig.store("GF").include_status = behaviour
    rig.store("GF").rows.append(row(3, status="trash"))
    snapshot(rig)
    assert rig.rows("SELECT state, listing, trashed FROM snapshot_night") == [("ok", "two_listings", 1)]


def test_a_variations_downloads_are_kept_in_the_snapshot() -> None:
    rig, _ = rig_with("GF")
    rig.store("GF").rows.append(row(3, product_type="variable", downloads=[]))
    rig.store("GF").variations = {3: [variation(31, key="lumen-pro.zip")]}
    snapshot(rig)
    [(variations,)] = rig.rows("SELECT variations_json FROM snapshot_state WHERE wc_id = 3")
    assert "lumen-pro.zip" in variations
    assert rig.rows("SELECT variable FROM snapshot_night") == [(1,)]


def test_more_than_50_variable_products_stop_that_stores_snapshot_and_no_retry_is_planned() -> None:
    rig, ids = rig_with("GF", "PW")
    rig.store("GF").rows.extend(row(100 + n, product_type="variable", downloads=[]) for n in range(51))
    snapshot(rig)
    assert rig.rows("SELECT store_id, state, reason, next_try_at FROM snapshot_night ORDER BY store_id") == [
        (ids["GF"], "failed", "too_many_variable", None),
        (ids["PW"], "ok", None, None),
    ]


def test_retention_follows_its_setting() -> None:
    """SYNC-03: kept 30 days (setting `snapshot_retention_days`): here 2."""
    rig, _ = rig_with("GF")
    rig.set("snapshot_retention_days", "2")
    for day in (18, 19, 20):  # the clock moves with the nights (a night ahead of it is refused, F5)
        rig.at(datetime(2026, 11, day, 10, 30, tzinfo=UTC))
        snapshot(rig, f"2026-11-{day}")

    assert rig.rows("SELECT night FROM snapshot_night ORDER BY night") == [("2026-11-19",), ("2026-11-20",)]


def test_a_stop_during_the_snapshot_saves_nothing_and_the_night_is_due_at_the_next_start() -> None:
    rig, ids = rig_with("GF")
    rig.store("GF").find(2)["status"] = "trash"
    before = dump(rig)
    rig.time.stop_after = len(rig.time.waits) + 2  # the stop arrives during a wait inside the snapshot's read
    snapshot(rig)
    assert rig.service.runner.state().outcomes == {ids["GF"]: "stopped"}
    assert dump(rig) == before and rig.rows("SELECT COUNT(*) FROM snapshot_state") == [(0,)]
    [(state, next_try, finished)] = rig.rows("SELECT state, next_try_at, finished_at FROM snapshot_night")
    assert state == "retry" and next_try == finished


def test_every_request_of_every_kind_of_run_is_a_get() -> None:
    rig, _ = rig_with("GF", "PW")
    rig.run("incremental")
    snapshot(rig)
    assert len(rig.sites.requests) > 8
    assert {request.method for request in rig.sites.requests} == {"GET"}
    assert all(KEY not in str(request.url) and SECRET not in str(request.url) for request in rig.sites.requests)


def test_the_incremental_and_snapshot_logs_carry_no_address_key_slug_or_file_even_with_redaction_off(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capfd: pytest.CaptureFixture[str]
) -> None:
    """LOG-01, the m3.1 never-logged pattern: retries, an answer echoing the keys, a trashed product and a change."""
    monkeypatch.setattr(logs, "redact", lambda text: text)
    handler = logs.configure_logging(tmp_path, retention_days=1)
    try:
        rig = make_sync_rig(START)
        rig.add_store("GF", [row(1, "secret-slug", downloads=[download(key="obj-key.zip")]), row(2, "other-slug")])
        rig.run()
        store = rig.store("GF")
        store.find(1)["date_modified_gmt"] = "2026-11-18T09:00:00"
        store.find(1)["downloads"] = [download(key="obj-key-2.zip")]
        sent = {"n": 0}

        def flaky(request: httpx.Request) -> httpx.Response | None:
            sent["n"] += 1
            if sent["n"] in (2, 3):
                return httpx.Response(429, headers={"Retry-After": "1"}, content=f"{KEY}:{SECRET}".encode())
            return None

        store.fail = flaky
        rig.run("incremental")
        store.fail = None
        store.find(2)["status"] = "trash"
        snapshot(rig)
        store.fail = lambda request: httpx.Response(500, content=f"<html>{KEY}</html>".encode())
        snapshot(rig, "2026-11-19")
        handler.flush()
    finally:
        logs.remove_logging(handler)
    log_text = (tmp_path / logs.LOG_FILE_NAME).read_text(encoding="utf-8")
    assert "Store GF incremental read: ok" in log_text and "snapshot of 2026-11-18, attempt 1: ok" in log_text
    assert "changes found outside ShelfSync (changed 1, trashed 0, deleted 0)" in log_text
    captured = capfd.readouterr()
    everything = log_text + captured.out + captured.err
    for forbidden in (
        KEY,
        SECRET,
        KEY[3:],
        "store-gf.example",
        "secret-slug",
        "other-slug",
        "obj-key",
        "modified_after",
        "include_status=",
        "per_page",
        "<html>",
    ):
        assert forbidden not in everything, forbidden

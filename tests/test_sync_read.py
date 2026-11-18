"""SYNC-01, SYNC-03, SYNC-04, APL-12 (GETs), V28, V30: the incremental read and the snapshot read
(`apply/catalog_read.py`) against a fake WooCommerce built from its REST docs (`tests/sync_support.py`): the exact
requests, the 2-minute overlap, `downloadable` read strictly (F8), the read's own duration (F3), the `include_status`
listing and its fallback, a missing product confirmed by id before it is deleted (F2), variations, the 50 variable
products limit, and nothing but GETs, with no key in any URL."""

import logging
from typing import Any

import httpx
import pytest

from shelfsync.apply.catalog_read import (
    INCLUDE_STATUS,
    INCREMENTAL_FIELDS,
    LISTING_FIELDS,
    MISSING_MAX,
    SNAPSHOT_FIELDS,
    TWO_LISTINGS,
    VARIABLE_MAX,
    VARIATION_FIELDS,
    CatalogRead,
    SnapshotRead,
    log_incremental,
    log_snapshot,
    missing_cap,
    read_incremental,
    read_snapshot,
)
from shelfsync.apply.woocommerce import WooClient
from tests.catalog_support import download
from tests.store_support import KEY, PRODUCTS, SECRET, STORE_URL, SYSTEM_STATUS
from tests.sync_support import FakeSyncStore, row, variation

WATERMARK = "2026-11-10T10:00:00"


def incremental(store: FakeSyncStore, watermark: str = WATERMARK, **options: Any) -> CatalogRead:
    with WooClient(STORE_URL, KEY, SECRET, transport=store.transport, monotonic=store.time.monotonic) as client:
        return read_incremental(
            client,
            watermark=watermark,
            spacing_ms=150,
            stop=store.time,
            monotonic=store.time.monotonic,
            now=store.time.wall,
            **options,
        )


def snapshot(store: FakeSyncStore, **options: Any) -> SnapshotRead:
    with WooClient(STORE_URL, KEY, SECRET, transport=store.transport, monotonic=store.time.monotonic) as client:
        return read_snapshot(
            client,
            spacing_ms=150,
            stop=store.time,
            monotonic=store.time.monotonic,
            now=store.time.wall,
            **options,
        )


def queries(store: FakeSyncStore) -> list[dict[str, str]]:
    return [dict(request.url.params) for request in store.product_requests()]


def by_id(store: FakeSyncStore) -> list[str]:
    return [request.url.path for request in store.requests if request.url.path.startswith(PRODUCTS + "/")]


def assert_only_gets_and_no_key_in_a_url(store: FakeSyncStore) -> None:
    """APL-12: only GETs; the keys go in the Authorization header, never a URL."""
    assert {request.method for request in store.requests} == {"GET"}
    for request in store.requests:
        assert KEY not in str(request.url) and SECRET not in str(request.url)
        assert "consumer" not in str(request.url)
        assert request.headers["authorization"].startswith("Basic ")


# ---- the incremental read (SYNC-01) --------------------------------------------------------------------------------


def test_the_incremental_asks_for_what_changed_since_the_watermark_less_two_minutes() -> None:
    """SYNC-01: the exact query (the full read's fields and `downloadable`), no `downloadable` filter, GMT dates; a
    product changed at the watermark itself and one 90 s before it are both read again (the overlap)."""
    store = FakeSyncStore(
        rows=[
            row(1, modified="2026-11-10T09:57:59"),  # before the overlap: not read
            row(2, modified="2026-11-10T09:58:30"),  # inside the overlap
            row(3, modified=WATERMARK),  # the watermark itself
            row(4, modified="2026-11-11T08:00:00", downloadable=False),  # its flag turned off: still read
        ]
    )
    result = incremental(store)
    assert result.ok and [product.wc_id for product in result.products] == [2, 3, 4]
    assert [product.downloadable for product in result.products] == [True, True, False]
    assert not result.products[2].in_catalog
    assert [request.url.path for request in store.requests] == [SYSTEM_STATUS, PRODUCTS]
    assert queries(store) == [
        {
            "modified_after": "2026-11-10T09:58:00",
            "dates_are_gmt": "true",
            "status": "any",
            "orderby": "id",
            "order": "asc",
            "per_page": "100",
            "page": "1",
            "_fields": INCREMENTAL_FIELDS,
        }
    ]
    assert INCREMENTAL_FIELDS == LISTING_FIELDS + ",downloadable"
    assert_only_gets_and_no_key_in_a_url(store)


def test_an_incremental_with_nothing_new_is_a_result_not_no_products() -> None:
    store = FakeSyncStore(rows=[row(1, modified="2026-11-01T00:00:00")])
    result = incremental(store)
    assert result.ok and result.products == () and result.total == 0


def test_an_incremental_reads_every_page_with_the_count_check() -> None:
    store = FakeSyncStore(rows=[row(wc_id, modified="2026-11-11T00:00:00") for wc_id in range(1, 251)])
    result = incremental(store)
    assert result.ok and len(result.products) == 250 and result.pages == 3
    assert [query["page"] for query in queries(store)] == ["1", "2", "3"]


def test_a_failed_incremental_returns_no_products_after_its_retries() -> None:
    """APL-12: a 500 on the listing is retried 3 times; the read then ends with its reason (the runner counts it once,
    `tests/test_sync_failures.py`)."""
    store = FakeSyncStore(rows=[row(1, modified="2026-11-11T00:00:00")])
    store.fail = lambda request: httpx.Response(500) if request.url.path.endswith(PRODUCTS) else None
    result = incremental(store)
    assert (result.reason, result.products, len(store.product_requests())) == ("server_error", (), 4)


@pytest.mark.parametrize("flag", [None, 1, 0, "true", "false", [True]])
def test_downloadable_must_be_a_real_bool_or_the_read_fails_closed(flag: Any) -> None:
    """F8: strict bool, on incremental and snapshot rows alike."""
    raw = row(1, modified="2026-11-11T00:00:00")
    if flag is None:
        del raw["downloadable"]
    else:
        raw["downloadable"] = flag
    assert (incremental(FakeSyncStore(rows=[raw])).bad_field, snapshot(FakeSyncStore(rows=[raw])).bad_field) == (
        "downloadable",
        "downloadable",
    )


@pytest.mark.parametrize(
    "bad",
    ["", "yesterday", "2026-11-10 10:00:00", "2026-11-10T10:00:00Z", "0000-01-01T00:00:00", "٢٠٢٦-11-10T10:00:00"],
)
def test_a_watermark_that_isnt_a_store_date_sends_nothing(bad: str) -> None:
    """F7: ASCII digits only (Arabic-Indic digits are `\\d` in Python's regexes)."""
    store = FakeSyncStore(rows=[row(1)])
    with pytest.raises(ValueError):
        incremental(store, watermark=bad)
    assert store.requests == []


def test_a_store_date_in_unicode_digits_fails_the_read_closed() -> None:
    raw = row(1, modified="２０２６-11-11T00:00:00")  # fullwidth digits
    assert incremental(FakeSyncStore(rows=[raw])).bad_field == "date_modified_gmt"


def test_the_read_reports_its_own_duration_from_the_first_listing_request_to_the_last_answer() -> None:
    """F3: whole seconds rounded up, on the monotonic clock; `system_status` isn't part of it."""
    store = FakeSyncStore(rows=[row(wc_id, modified="2026-11-11T00:00:00") for wc_id in range(1, 201)])
    result = incremental(store)
    assert result.ok and result.seconds == 1  # two pages 0.15 s apart: 0.15 s, rounded up
    slow = FakeSyncStore(rows=[row(1, modified="2026-11-11T00:00:00")])
    sent = {"once": False}

    def throttled(request: httpx.Request) -> httpx.Response | None:
        if request.url.path.endswith(PRODUCTS) and not sent["once"]:
            sent["once"] = True
            return httpx.Response(429, headers={"Retry-After": "40"})
        return None

    slow.fail = throttled
    assert incremental(slow).seconds == 41  # the 40 s wait and the spacing, rounded up


# ---- the snapshot read (SYNC-03, SYNC-04, V28) ---------------------------------------------------------------------


def snapshot_rows() -> list[dict[str, Any]]:
    return [
        row(1),
        row(2, status="draft"),
        row(3, "old-slider__trashed", status="trash"),
        row(4, downloads=[], downloadable=False),  # not downloadable: still in the snapshot
        row(5, status="private"),
    ]


def test_the_snapshot_lists_every_product_with_include_status_any_trash() -> None:
    """SYNC-03, SYNC-04: the probe, then one listing with `include_status=any,trash`; trash and non-downloadable
    products included; the snapshot's fields (`name` and `downloadable` among them, F3, F8)."""
    store = FakeSyncStore(rows=snapshot_rows())
    result = snapshot(store)
    assert result.ok and result.listing == INCLUDE_STATUS
    assert [product.wc_id for product in result.products] == [1, 2, 3, 4, 5]
    assert result.trashed == 1 and result.products[2].status == "trash"
    assert result.products[0].title == "Product 1" and result.products[3].downloadable is False
    assert queries(store) == [
        {
            "include_status": "trash",
            "orderby": "id",
            "order": "asc",
            "per_page": "1",
            "page": "1",
            "_fields": SNAPSHOT_FIELDS,
        },
        {
            "include_status": "any,trash",
            "orderby": "id",
            "order": "asc",
            "per_page": "100",
            "page": "1",
            "_fields": SNAPSHOT_FIELDS,
        },
    ]
    assert {"name", "downloadable"} <= set(SNAPSHOT_FIELDS.split(","))
    assert_only_gets_and_no_key_in_a_url(store)


@pytest.mark.parametrize("behaviour", ["refused", "ignored", "any_only"])
def test_a_store_that_refuses_or_doesnt_honour_include_status_gets_two_listings(behaviour: str) -> None:
    """V28 not verified: refused (`rest_invalid_param`), ignored (an older WooCommerce), or `any,trash` read as `any`:
    `status=any` then `status=trash`, and the result says so."""
    store = FakeSyncStore(rows=snapshot_rows(), include_status=behaviour)
    result = snapshot(store)
    assert result.ok and result.listing == TWO_LISTINGS
    assert [product.wc_id for product in result.products] == [1, 2, 3, 4, 5]
    assert result.trashed == 1
    statuses = [query.get("status") for query in queries(store) if "status" in query]
    assert statuses == ["any", "trash"]


def test_a_store_that_holds_no_trash_keeps_the_one_listing() -> None:
    store = FakeSyncStore(rows=[row(1), row(2)])
    result = snapshot(store)
    assert result.ok and result.listing == INCLUDE_STATUS and result.trashed == 0
    assert len(store.product_requests()) == 2


@pytest.mark.parametrize("behaviour", ["refused", "ignored"])
def test_a_store_that_cant_list_its_trash_fails_the_snapshot(behaviour: str) -> None:
    """Without a trash listing a trashed product would read as deleted: the snapshot fails (`trash_unlisted`)."""
    store = FakeSyncStore(rows=snapshot_rows(), include_status="refused", status_trash=behaviour)
    result = snapshot(store)
    assert (result.reason, result.products) == ("trash_unlisted", ())


def test_a_store_with_no_products_fails_the_snapshot() -> None:
    """A store answering an empty listing would make every catalog product read as deleted: `no_products`."""
    result = snapshot(FakeSyncStore(rows=[]))
    assert result.reason == "no_products"


# ---- a missing product is asked for by id before it is deleted (F2) ------------------------------------------------


def test_a_missing_catalog_product_is_deleted_only_after_a_404() -> None:
    store = FakeSyncStore(rows=[row(1), row(2)])
    result = snapshot(store, expected={1, 2, 9}, catalog_size=100)
    assert result.ok and result.deleted == (9,)
    assert by_id(store) == [f"{PRODUCTS}/9"]
    assert store.requests[-1].url.params["_fields"] == SNAPSHOT_FIELDS


def test_a_product_the_listing_missed_but_the_store_still_has_is_used_as_read() -> None:
    """F2: a partly honoured listing (or a race): `GET /products/{id}` answers 200, so it is read, not deleted."""
    store = FakeSyncStore(rows=[row(1), row(2, status="trash"), row(3)], unlisted={2, 3})
    result = snapshot(store, expected={1, 2, 3}, catalog_size=100)
    assert result.ok and result.deleted == ()
    statuses = [(product.wc_id, product.status) for product in result.products]
    assert statuses == [(1, "publish"), (2, "trash"), (3, "publish")]


def test_the_two_listing_race_a_product_restored_from_the_trash_between_them_is_kept() -> None:
    """F2, the race: the `status=any` listing ran while the product was in the trash, the `status=trash` listing after
    it was restored: neither holds it, and the by-id read finds it."""
    store = FakeSyncStore(rows=[row(1), row(2, status="trash")], include_status="refused")
    seen = {"any": False}

    def restore_after_the_any_listing(request: httpx.Request) -> httpx.Response | None:
        if request.url.params.get("status") == "any":
            seen["any"] = True
        elif request.url.params.get("status") == "trash" and seen["any"]:
            store.find(2)["status"] = "publish"
        return None

    store.fail = restore_after_the_any_listing
    result = snapshot(store, expected={1, 2}, catalog_size=100)
    assert result.ok and result.deleted == () and result.listing == TWO_LISTINGS
    assert [(product.wc_id, product.status) for product in result.products] == [(1, "publish"), (2, "publish")]


def test_more_missing_products_than_the_cap_fail_the_night_before_any_is_asked_for() -> None:
    """F2 (Lead (proposed)): the smaller of 20 and 5 % of the store's catalog, rounded up, at least 1."""
    assert [missing_cap(size) for size in (0, 1, 13, 20, 100, 400, 2398)] == [1, 1, 1, 1, 5, 20, 20]
    assert MISSING_MAX == 20
    store = FakeSyncStore(rows=[row(1)])
    result = snapshot(store, expected={1, *range(100, 106)}, catalog_size=100)  # 6 missing, cap 5
    assert (result.reason, result.products, by_id(store)) == ("too_many_missing", (), [])
    assert snapshot(FakeSyncStore(rows=[row(1)]), expected={1, *range(100, 105)}, catalog_size=100).ok


def test_a_hostile_by_id_answer_fails_closed() -> None:
    store = FakeSyncStore(rows=[row(1), row(2)], unlisted={2})
    other = row(3)
    store.fail = lambda request: (  # the answer is another product
        httpx.Response(200, json=other) if request.url.path == f"{PRODUCTS}/2" else None
    )
    result = snapshot(store, expected={1, 2}, catalog_size=100)
    assert (result.reason, result.bad_field, result.bad_page) == ("bad_response", "id", 0)


# ---- variations and limits -----------------------------------------------------------------------------------------


def test_each_variable_products_variations_are_read() -> None:
    """SYNC-03, V30: a variation's downloads; the variations' query."""
    store = FakeSyncStore(
        rows=[row(1), row(2, product_type="variable", downloads=[])],
        variations={2: [variation(21), variation(20, status="private")]},
    )
    result = snapshot(store)
    assert result.ok
    [(parent, rows)] = result.variations
    assert parent == 2 and [item.wc_id for item in rows] == [20, 21]
    assert rows[1].downloads[0].name == "Edition 21" and rows[0].status == "private"
    assert rows[0].type == "variation" and rows[0].slug == ""
    request = store.requests[-1]
    assert request.url.path == f"{PRODUCTS}/2/variations"
    assert dict(request.url.params) == {
        "orderby": "id",
        "order": "asc",
        "per_page": "100",
        "page": "1",
        "_fields": VARIATION_FIELDS,
    }


def test_more_than_50_variable_products_stop_the_snapshot_before_any_variation_is_read() -> None:
    store = FakeSyncStore(rows=[row(wc_id, product_type="variable") for wc_id in range(1, VARIABLE_MAX + 2)])
    result = snapshot(store)
    assert result.reason == "too_many_variable" and result.products == ()
    assert not any("variations" in request.url.path for request in store.requests)
    exactly = FakeSyncStore(rows=[row(wc_id, product_type="variable") for wc_id in range(1, VARIABLE_MAX + 1)])
    assert snapshot(exactly).ok


def test_a_variations_listing_that_is_hostile_fails_closed() -> None:
    store = FakeSyncStore(rows=[row(1, product_type="variable")], variations={1: [{"id": "x"}]})
    result = snapshot(store)
    assert (result.reason, result.bad_field) == ("bad_response", "id")


def test_a_524_during_the_snapshot_is_retried_and_the_read_works() -> None:
    """APL-12 in the snapshot: a retried 524."""
    store = FakeSyncStore(rows=[row(1)])
    sent = {"done": False}

    def once(request: httpx.Request) -> httpx.Response | None:
        if request.url.params.get("include_status") == "any,trash" and not sent["done"]:
            sent["done"] = True
            return httpx.Response(524)
        return None

    store.fail = once
    result = snapshot(store)
    assert result.ok and 2.0 in store.time.waits


def test_the_log_lines_carry_counts_and_codes_only(caplog: pytest.LogCaptureFixture) -> None:
    store = FakeSyncStore(rows=[row(1, downloads=[download(key="secret-name.zip")])])
    with caplog.at_level(logging.INFO, logger="shelfsync.catalog"):
        log_snapshot("GF", "2026-11-18", 2, snapshot(store))
        log_incremental("GF", incremental(FakeSyncStore(rows=[row(1, modified="2026-11-11T00:00:00")])), 1)
    text = caplog.text
    assert "Store GF snapshot of 2026-11-18, attempt 2: ok (listing include_status" in text
    assert "Store GF incremental read: ok (pages 1, rows 1, changed 1" in text
    for leaked in ("store-a.example", KEY, SECRET, "secret-name", "product-1", "include_status=", "_fields"):
        assert leaked not in text

"""SYNC-01, SYNC-03, SYNC-04, APL-12 (GETs), V28, V30: the incremental read and the snapshot read
(`apply/catalog_read.py`) against a fake WooCommerce built from its REST docs (`tests/sync_support.py`): the exact
requests, the 2-minute overlap, the `include_status` listing and its fallback, variations, the 50 variable products
limit, and nothing but GETs, with no key in any URL."""

import logging
from typing import Any

import httpx
import pytest

from shelfsync.apply.catalog_read import (
    INCLUDE_STATUS,
    LISTING_FIELDS,
    SNAPSHOT_FIELDS,
    TWO_LISTINGS,
    VARIABLE_MAX,
    VARIATION_FIELDS,
    CatalogRead,
    MemoryFailureCount,
    SnapshotRead,
    log_incremental,
    log_snapshot,
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
            failures=options.pop("failures", MemoryFailureCount()),
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
            failures=options.pop("failures", MemoryFailureCount()),
            monotonic=store.time.monotonic,
            now=store.time.wall,
            **options,
        )


def queries(store: FakeSyncStore) -> list[dict[str, str]]:
    return [dict(request.url.params) for request in store.product_requests()]


def assert_only_gets_and_no_key_in_a_url(store: FakeSyncStore) -> None:
    """APL-12: only GETs; the keys go in the Authorization header, never a URL."""
    assert {request.method for request in store.requests} == {"GET"}
    for request in store.requests:
        assert KEY not in str(request.url) and SECRET not in str(request.url)
        assert "consumer" not in str(request.url)
        assert request.headers["authorization"].startswith("Basic ")


# ---- the incremental read (SYNC-01) --------------------------------------------------------------------------------


def test_the_incremental_asks_for_what_changed_since_the_watermark_less_two_minutes() -> None:
    """SYNC-01: the exact query, no `downloadable` filter, GMT dates; a product changed at the watermark itself and
    one 90 s before it are both read again (the overlap)."""
    store = FakeSyncStore(
        rows=[
            row(1, modified="2026-11-10T09:57:59"),  # before the overlap: not read
            row(2, modified="2026-11-10T09:58:30"),  # inside the overlap
            row(3, modified=WATERMARK),  # the watermark itself
            row(4, modified="2026-11-11T08:00:00", downloads=[]),  # its downloads were removed: still read
        ]
    )
    result = incremental(store)
    assert result.ok and [product.wc_id for product in result.products] == [2, 3, 4]
    assert result.products[2].downloads == ()
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
            "_fields": LISTING_FIELDS,
        }
    ]
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


def test_a_failed_incremental_returns_no_products_and_counts_its_failures() -> None:
    """APL-12: a 500 on the listing is retried 3 times, every attempt counted."""
    store = FakeSyncStore(rows=[row(1, modified="2026-11-11T00:00:00")])
    store.fail = lambda request: httpx.Response(500) if request.url.path.endswith(PRODUCTS) else None
    failures = MemoryFailureCount()
    result = incremental(store, failures=failures)
    assert (result.reason, result.products, failures.count) == ("server_error", (), 4)


@pytest.mark.parametrize("bad", ["", "yesterday", "2026-11-10 10:00:00", "2026-11-10T10:00:00Z", "0000-01-01T00:00:00"])
def test_a_watermark_that_isnt_a_store_date_sends_nothing(bad: str) -> None:
    store = FakeSyncStore(rows=[row(1)])
    with pytest.raises(ValueError):
        incremental(store, watermark=bad)
    assert store.requests == []


# ---- the snapshot read (SYNC-03, SYNC-04, V28) ---------------------------------------------------------------------


def snapshot_rows() -> list[dict[str, Any]]:
    return [
        row(1),
        row(2, status="draft"),
        row(3, "old-slider__trashed", status="trash"),
        row(4, downloads=[]),  # not downloadable: still in the snapshot
        row(5, status="private"),
    ]


def test_the_snapshot_lists_every_product_with_include_status_any_trash() -> None:
    """SYNC-03, SYNC-04: the probe, then one listing with `include_status=any,trash`; trash and non-downloadable
    products included; the snapshot's fields (no `name`)."""
    store = FakeSyncStore(rows=snapshot_rows())
    result = snapshot(store)
    assert result.ok and result.listing == INCLUDE_STATUS
    assert [product.wc_id for product in result.products] == [1, 2, 3, 4, 5]
    assert result.trashed == 1 and result.products[2].status == "trash"
    assert all(product.title == "" for product in result.products)
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


def test_a_524_during_the_snapshot_is_retried_and_counted_then_reset() -> None:
    """APL-12 in the snapshot: a retried 524, then a usable page sets the count back to 0."""
    store = FakeSyncStore(rows=[row(1)])
    sent = {"done": False}

    def once(request: httpx.Request) -> httpx.Response | None:
        if request.url.params.get("include_status") == "any,trash" and not sent["done"]:
            sent["done"] = True
            return httpx.Response(524)
        return None

    store.fail = once
    failures = MemoryFailureCount()
    result = snapshot(store, failures=failures)
    assert result.ok and failures.count == 0 and 2.0 in store.time.waits


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

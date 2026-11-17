"""CAT-01, APL-12 (GETs), ERR-02: the paged catalog reader (`apply/catalog_read.py`) against a fake WooCommerce built
from its REST docs (httpx.MockTransport, RFC 2606 hosts): the exact requests, spacing, retries (a 524 and a 429
replayed, `Retry-After` in both forms and capped), the failure count and auto-pause, the count check, the bounds,
hostile answers, the stop, the log line, and the cookie drop (Test connection included)."""

import base64
import json
import logging
import warnings
from datetime import UTC, datetime, timedelta
from email.utils import format_datetime
from typing import Any

import httpx
import pytest

from shelfsync import __version__
from shelfsync.apply.catalog_read import (
    BACKOFF_SECONDS,
    LISTING_FIELDS,
    PAGE_MAX_BYTES,
    CatalogRead,
    MemoryFailureCount,
    _Session,
    is_retried,
    read_catalog,
    read_store_catalog,
    retry_delay,
)
from shelfsync.apply.woocommerce import MAX_BODY_BYTES, NonGetRefused, ReadRefused, WooClient, run_read_test
from shelfsync.catalog.model import META_JSON_MAX, meta_json
from tests.catalog_support import FakeCatalogStore, FakeTime, download, raw_product
from tests.store_support import (
    KEY,
    PRODUCTS,
    SECRET,
    STORE_URL,
    SYSTEM_STATUS,
    FakeWoo,
    system_status,
    unread,
    wp_error,
)


def rows(count: int, start: int = 1) -> list[dict[str, Any]]:
    return [raw_product(wc_id) for wc_id in range(start, start + count)]


def read(
    store: FakeCatalogStore,
    spacing_ms: int = 150,
    failures: MemoryFailureCount | None = None,
    **options: Any,
) -> CatalogRead:
    with WooClient(STORE_URL, KEY, SECRET, transport=store.transport, monotonic=store.time.monotonic) as client:
        return read_catalog(
            client,
            spacing_ms=spacing_ms,
            stop=store.time,
            failures=failures if failures is not None else MemoryFailureCount(),
            monotonic=store.time.monotonic,
            now=store.time.wall,
            **options,
        )


def answer(status: int, headers: dict[str, str] | None = None, body: bytes = b"") -> httpx.Response:
    return httpx.Response(status, headers=headers or {}, content=body)


def page_of(body: Any, total: int | str = 1, pages: int | str = 1) -> httpx.Response:
    return httpx.Response(
        200, headers={"X-WP-Total": str(total), "X-WP-TotalPages": str(pages)}, content=json.dumps(body).encode()
    )


# ---- the requests (contract) ---------------------------------------------------------------------------------------


def test_a_full_read_sends_exactly_these_gets_spaced_apart_with_the_key_only_in_the_header() -> None:
    """CAT-01: system_status, then products pages 1 to N, in order; Basic auth in the header, never in a URL."""
    store = FakeCatalogStore(rows=rows(250))
    result = read(store)
    assert result.ok and len(result.products) == 250 and result.total == 250 and result.pages == 3
    assert [p.wc_id for p in result.products] == list(range(1, 251))
    assert [r.method for r in store.requests] == ["GET"] * 4
    assert [r.url.path for r in store.requests] == [SYSTEM_STATUS, PRODUCTS, PRODUCTS, PRODUCTS]
    assert dict(store.requests[0].url.params) == {"_fields": "environment"}
    for page, request in enumerate(store.requests[1:], start=1):
        assert dict(request.url.params) == {
            "downloadable": "true",
            "status": "any",
            "orderby": "id",
            "order": "asc",
            "per_page": "100",
            "page": str(page),
            "_fields": "id,slug,name,type,status,date_modified_gmt,downloads,meta_data",
        }
    expected = "Basic " + base64.b64encode(f"{KEY}:{SECRET}".encode()).decode()
    for request in store.requests:
        assert request.headers["Authorization"] == expected
        assert request.headers["User-Agent"] == f"ShelfSync/{__version__}"
        assert "cookie" not in request.headers
        assert KEY not in str(request.url) and SECRET not in str(request.url) and "consumer_" not in str(request.url)
    assert store.time.waits == [0.15, 0.15, 0.15]  # the spacing between every two requests, none before the first
    assert (result.requests, result.wc_version, result.http_status) == (4, "11.2.1", None)


def test_the_fields_asked_for_are_the_ones_the_table_keeps() -> None:
    assert LISTING_FIELDS == "id,slug,name,type,status,date_modified_gmt,downloads,meta_data"


def test_a_caller_may_ask_for_more_spacing() -> None:
    store = FakeCatalogStore(rows=rows(3))
    read(store, spacing_ms=1000)
    assert store.time.waits == [1.0]


def test_only_the_wanted_fields_are_kept_and_the_title_is_unescaped() -> None:
    meta = [
        {"id": 1, "key": "_price", "value": "9"},
        {"id": 2, "key": "latest_version", "value": "1.2.3"},
        {"id": 3, "key": "latest_version_js-composer-theme", "value": "7.9"},
        {"id": 4, "key": "_edit_lock", "value": {"nested": ["anything"]}},
    ]
    raw = raw_product(1294, "jupiterx", "JupiterX &#8211; Builder &amp; Theme", meta=meta)
    raw["description"] = "<p>long text</p>"  # a field not asked for, if a store sends it anyway
    result = read(FakeCatalogStore(rows=[raw]))
    [found] = result.products
    assert found.title == "JupiterX – Builder & Theme"
    assert found.meta == (("latest_version", "1.2.3"), ("latest_version_js-composer-theme", "7.9"))
    assert not hasattr(found, "description")


# ---- ERR-02 --------------------------------------------------------------------------------------------------------


def test_a_store_below_woocommerce_5_8_is_refused_before_any_product_is_read() -> None:
    store = FakeCatalogStore(rows=rows(3), status_answer=system_status("5.7.9"))
    result = read(store)
    assert (result.reason, result.products) == ("wc_too_old", ())
    assert [r.url.path for r in store.requests] == [SYSTEM_STATUS]


def test_a_store_with_no_downloadable_products_fails_with_no_products() -> None:
    result = read(FakeCatalogStore(rows=[]))
    assert result.reason == "no_products"


@pytest.mark.parametrize("environment", [{"theme": {}}, [], {"environment": {"version": "<b>9</b>"}}])
def test_an_unreadable_system_status_is_a_bad_response(environment: Any) -> None:
    store = FakeCatalogStore(rows=rows(1), status_answer=httpx.Response(200, json=environment))
    assert read(store).reason == "bad_response"


@pytest.mark.parametrize("status", [200, 500])
def test_a_body_nested_too_deep_for_json_is_read_as_not_json_not_a_crash(status: int) -> None:
    """`json` raises RecursionError (not a ValueError) for 100,000 open brackets; `woocommerce._json` reads it as not
    JSON: a 200 is `not_woocommerce` (as in Test connection), a 500 a `server_error` (retried, then given up)."""
    store = FakeCatalogStore(rows=rows(1), status_answer=httpx.Response(status, content=b"[" * 100_000))
    assert read(store).reason == ("not_woocommerce" if status == 200 else "server_error")


def test_a_products_page_nested_too_deep_is_a_bad_response_naming_the_page() -> None:
    store = FakeCatalogStore(rows=rows(150))
    deep = httpx.Response(200, headers={"X-WP-Total": "150", "X-WP-TotalPages": "2"}, content=b"[" * 100_000)
    store.before_page = lambda page: store.answers.append(deep) if page == 1 else None
    result = read(store)
    assert (result.reason, result.bad_field, result.bad_page) == ("bad_response", "json", 2)


# ---- retries (APL-12) ----------------------------------------------------------------------------------------------


def test_a_524_is_retried_after_two_seconds_and_the_read_completes() -> None:
    """APL-12 Accept: a Cloudflare 524 replayed."""
    store = FakeCatalogStore(rows=rows(3), answers=[answer(524)])
    failures = MemoryFailureCount()
    result = read(store, failures=failures)
    assert result.ok and len(result.products) == 3
    assert store.time.waits == [0.15, BACKOFF_SECONDS[0]]
    assert failures.count == 0  # the success reset it


def test_a_429_with_retry_after_seconds_waits_that_long() -> None:
    """APL-12 Accept: a 429 replayed, with `Retry-After: 7`."""
    store = FakeCatalogStore(rows=rows(3), answers=[answer(429, {"Retry-After": "7"})])
    assert read(store).ok
    assert store.time.waits == [0.15, 7.0]


def test_retry_after_as_an_http_date_and_its_cap_and_floor() -> None:
    now = datetime(2026, 11, 17, 12, 0, tzinfo=UTC)
    headers = httpx.Headers({"Retry-After": format_datetime(now + timedelta(seconds=30), usegmt=True)})
    assert retry_delay(headers, 0, now) == 30.0
    assert retry_delay(httpx.Headers({"Retry-After": "3600"}), 0, now) == 60.0  # never more than 60 s
    assert retry_delay(httpx.Headers({"Retry-After": "9" * 40}), 0, now) == 60.0
    past = format_datetime(now - timedelta(minutes=5), usegmt=True)
    assert retry_delay(httpx.Headers({"Retry-After": past}), 0, now) == 0.0
    far = format_datetime(now + timedelta(days=2), usegmt=True)
    assert retry_delay(httpx.Headers({"Retry-After": far}), 0, now) == 60.0
    for bad in ("soon", "-5", "1.5", ""):
        assert retry_delay(httpx.Headers({"Retry-After": bad}), 1, now) == BACKOFF_SECONDS[1]
    assert [retry_delay(None, attempt, now) for attempt in range(3)] == [2.0, 4.0, 8.0]


def test_a_retry_after_shorter_than_the_spacing_still_waits_the_spacing() -> None:
    store = FakeCatalogStore(rows=rows(3), answers=[answer(429, {"Retry-After": "0"})])
    read(store, spacing_ms=1000)
    assert store.time.waits == [1.0, 1.0]


def test_a_failure_that_lasts_through_three_retries_ends_the_read_with_its_reason() -> None:
    store = FakeCatalogStore(rows=rows(3), answers=[answer(502)] * 4)
    failures = MemoryFailureCount()
    result = read(store, failures=failures)
    assert (result.reason, result.http_status, result.products) == ("server_error", 502, ())
    assert store.time.waits == [0.15, 2.0, 4.0, 8.0]
    assert len(store.product_requests()) == 4 and failures.count == 4


@pytest.mark.parametrize(
    ("first", "reason"),
    [
        (answer(429), "rate_limited"),
        (answer(520), "cloudflare_52x"),
        (answer(527), "cloudflare_52x"),
        (answer(500), "server_error"),
        (wp_error(503, "unavailable"), "server_error"),
        (answer(503, {"Content-Type": "text/html"}, b"<html>busy</html>"), "blocked"),
    ],
)
def test_every_retried_status_is_retried(first: httpx.Response, reason: str) -> None:
    """Review 1, finding 10: the failed attempt is counted with its reason, and its status is the last failure's."""

    class Recording(MemoryFailureCount):
        def __init__(self) -> None:
            super().__init__()
            self.reasons: list[str] = []

        def failed(self, why: str) -> bool:
            self.reasons.append(why)
            return super().failed(why)

    store = FakeCatalogStore(rows=rows(2), answers=[first])
    failures = Recording()
    result = read(store, failures=failures)
    assert result.ok and len(store.product_requests()) == 2
    assert failures.reasons == [reason] and result.http_status == first.status_code


@pytest.mark.parametrize("error", [httpx.ReadTimeout("slow"), httpx.ConnectError("refused")])
def test_a_timeout_or_an_unreachable_get_is_retried(error: Exception) -> None:
    def fail(request: httpx.Request) -> httpx.Response:
        raise error

    store = FakeCatalogStore(rows=rows(2), answers=[fail])
    assert read(store).ok


@pytest.mark.parametrize(
    ("first", "reason"),
    [
        (wp_error(401, "woocommerce_rest_cannot_view"), "keys_refused"),
        (wp_error(403, "woocommerce_rest_cannot_view"), "forbidden"),
        (answer(403, {"Content-Type": "text/html"}, b"<html>no</html>"), "blocked"),
        (answer(301, {"Location": "https://elsewhere.example/"}), "redirected"),
        (answer(404), "not_woocommerce"),
        (answer(418), "bad_response"),
    ],
)
def test_nothing_else_is_retried(first: httpx.Response, reason: str) -> None:
    store = FakeCatalogStore(rows=rows(2), answers=[first])
    result = read(store)
    assert result.reason == reason and len(store.product_requests()) == 1


def test_which_reasons_are_retried() -> None:
    assert is_retried("blocked", 503) and not is_retried("blocked", 403)
    for reason in ("rate_limited", "cloudflare_52x", "server_error", "timeout", "unreachable"):
        assert is_retried(reason, None)
    for reason in ("keys_refused", "forbidden", "redirected", "tls_error", "bad_response", "not_woocommerce"):
        assert not is_retried(reason, 500)


# ---- GET only ------------------------------------------------------------------------------------------------------


@pytest.mark.parametrize("method", ["POST", "PUT", "PATCH", "DELETE", "HEAD"])
def test_the_retry_code_refuses_any_method_but_get_before_sending(method: str) -> None:
    store = FakeCatalogStore(rows=rows(1))
    time = store.time
    with WooClient(STORE_URL, KEY, SECRET, transport=store.transport, monotonic=time.monotonic) as client:
        session = _Session(
            client,
            spacing_seconds=0.15,
            stop=time,
            failures=MemoryFailureCount(),
            monotonic=time.monotonic,
            now=time.wall,
            deadline=time.now + 600,
        )
        with pytest.raises(NonGetRefused):
            session.request(method, PRODUCTS, {}, MAX_BODY_BYTES)
    assert store.requests == [] and time.waits == []


def test_no_request_but_a_get_is_ever_sent_even_with_retries_and_a_re_read() -> None:
    store = FakeCatalogStore(rows=rows(150), answers=[answer(524), answer(429)])
    store.total_header = "151"  # never matches: two full listings
    read(store)
    assert len(store.requests) > 5 and {request.method for request in store.requests} == {"GET"}


# ---- failures in a row and auto-pause ------------------------------------------------------------------------------


def test_the_tenth_failure_in_a_row_auto_pauses_the_store_and_ends_the_read() -> None:
    """APL-12: every failed attempt counts, across runs (the count starts where the last run left it)."""
    failures = MemoryFailureCount(start=8)
    store = FakeCatalogStore(rows=rows(2), status_answer=answer(500))
    result = read(store, failures=failures)
    assert (result.reason, result.auto_paused) == ("server_error", True)
    assert failures.count == 10 and failures.paused_reason == "server_error"
    assert len(store.requests) == 2  # the 9th and 10th; no retry after the pause


def test_a_success_resets_the_count() -> None:
    failures = MemoryFailureCount(start=5)
    assert read(FakeCatalogStore(rows=rows(2), answers=[answer(500)]), failures=failures).ok
    assert failures.count == 0


# ---- the count check -----------------------------------------------------------------------------------------------


def test_a_count_mismatch_is_read_again_once_and_a_good_re_read_is_kept() -> None:
    store = FakeCatalogStore(rows=rows(150))
    reads: list[int] = []

    def before(page: int) -> None:
        reads.append(page)
        store.total_header = "151" if len(reads) <= 2 else None  # the first listing's total doesn't match

    store.before_page = before
    result = read(store)
    assert result.ok and len(result.products) == 150
    assert reads == [1, 2, 1, 2]


def test_two_mismatches_fail_with_count_mismatch_and_return_nothing() -> None:
    store = FakeCatalogStore(rows=rows(150), total_header="149")
    result = read(store)
    assert (result.reason, result.products, result.total) == ("count_mismatch", (), 149)
    assert len(store.product_requests()) == 4


def test_an_id_seen_twice_or_out_of_order_is_a_mismatch() -> None:
    twice = FakeCatalogStore(rows=[*rows(2), raw_product(2)])
    assert read(twice).reason == "count_mismatch"
    backwards = FakeCatalogStore(rows=[raw_product(5), raw_product(3)])
    assert read(backwards).reason == "count_mismatch"


# ---- the bounds ----------------------------------------------------------------------------------------------------


def test_more_than_forty_pages_is_refused_before_page_two() -> None:
    store = FakeCatalogStore(rows=rows(3), pages_header="41")
    result = read(store)
    assert result.reason == "too_many_pages" and len(store.product_requests()) == 1


def test_a_page_over_eight_mebibytes_is_a_bad_response_and_one_just_under_is_read() -> None:
    padding = {"id": 1, "key": "_padding", "value": "x" * (PAGE_MAX_BYTES - 600)}
    big = raw_product(1, meta=[padding])
    assert read(FakeCatalogStore(rows=[big])).ok
    padding["value"] = "x" * (PAGE_MAX_BYTES + 1)
    store = FakeCatalogStore(rows=[raw_product(1, meta=[padding])])
    assert read(store).reason == "bad_response"
    assert len(store.product_requests()) == 1  # an over-long answer isn't retried


def test_the_test_connections_one_mebibyte_cap_is_unchanged_and_a_caller_can_raise_it() -> None:
    body = b"[" + b" " * MAX_BODY_BYTES + b"]"
    woo = FakeWoo(products_answer=httpx.Response(200, content=body))
    with WooClient(STORE_URL, KEY, SECRET, transport=woo.transport, monotonic=lambda: 0.0) as client:
        with pytest.raises(ReadRefused, match="bad_response"):
            client.get(PRODUCTS, {}, deadline=10.0)
        assert client.get(PRODUCTS, {}, deadline=10.0, max_bytes=2 * MAX_BODY_BYTES).body == body


def test_the_whole_read_of_a_store_stops_at_ten_minutes() -> None:
    store = FakeCatalogStore(rows=rows(250))
    store.before_page = lambda page: setattr(store.time, "now", store.time.now + 400.0)
    result = read(store)
    assert result.reason == "timeout" and result.products == ()


def test_a_retry_wait_that_would_pass_the_bound_ends_the_read_at_once() -> None:
    store = FakeCatalogStore(rows=rows(2), answers=[answer(429, {"Retry-After": "50"})])
    result = read(store, store_seconds=30.0)
    assert result.reason == "timeout" and store.time.waits == [0.15]


# ---- hostile answers -----------------------------------------------------------------------------------------------


def _with(**changes: Any) -> dict[str, Any]:
    raw = raw_product(1)
    raw.update(changes)
    return raw


HOSTILE: list[tuple[str, httpx.Response]] = [
    ("not a list", page_of({"id": 1})),
    ("not json", httpx.Response(200, headers={"X-WP-Total": "1", "X-WP-TotalPages": "1"}, content=b"[{")),
    ("not utf-8", httpx.Response(200, headers={"X-WP-Total": "1", "X-WP-TotalPages": "1"}, content=b"[\xff]")),
    ("deep nest", httpx.Response(200, headers={"X-WP-Total": "1", "X-WP-TotalPages": "1"}, content=b"[" * 100000)),
    ("101 rows", page_of(rows(101), total=101)),
    ("no id", page_of([{k: v for k, v in raw_product(1).items() if k != "id"}])),
    ("text id", page_of([_with(id="1")])),
    ("bool id", page_of([_with(id=True)])),
    ("float id", page_of([_with(id=1.0)])),
    ("zero id", page_of([_with(id=0)])),
    ("huge id", page_of([_with(id=2**63)])),
    ("slug number", page_of([_with(slug=5)])),
    ("slug too long", page_of([_with(slug="s" * 201)])),
    ("title too long", page_of([_with(name="t" * 1001)])),
    ("odd type", page_of([_with(type="Simple Product")])),
    ("odd status", page_of([_with(status="")])),
    ("odd date", page_of([_with(date_modified_gmt="yesterday")])),
    ("no date", page_of([{k: v for k, v in raw_product(1).items() if k != "date_modified_gmt"}])),
    ("downloads not a list", page_of([_with(downloads={"a": 1})])),
    ("too many downloads", page_of([_with(downloads=[download(key=str(n)) for n in range(51)])])),
    ("download not an object", page_of([_with(downloads=["x"])])),
    ("download id empty", page_of([_with(downloads=[download(download_id="")])])),
    ("download id too long", page_of([_with(downloads=[download(download_id="x" * 65)])])),
    ("download number id", page_of([_with(downloads=[{"id": 5, "name": "Download", "file": "f"}])])),
    ("file too long", page_of([_with(downloads=[{"id": "a", "name": "Download", "file": "f" * 2049}])])),
    ("meta not a list", page_of([_with(meta_data={"key": "x"})])),
    ("meta without key", page_of([_with(meta_data=[{"value": "x"}])])),
    ("no total", httpx.Response(200, headers={"X-WP-TotalPages": "1"}, content=b"[]")),
    ("odd total", page_of(rows(1), total="1e3")),
    ("negative total", page_of(rows(1), total="-1")),
    ("huge total", page_of(rows(1), total="9" * 10)),
    ("odd pages", page_of(rows(1), pages="two")),
]


@pytest.mark.parametrize("response", [case[1] for case in HOSTILE], ids=[case[0] for case in HOSTILE])
def test_a_hostile_answer_ends_the_read_with_bad_response_and_saves_nothing(response: httpx.Response) -> None:
    store = FakeCatalogStore(rows=rows(1), answers=[response])
    result = read(store)
    assert (result.reason, result.products) == ("bad_response", ())
    assert len(store.product_requests()) == 1  # not retried


TEXT_PROBES: list[tuple[str, dict[str, Any], str]] = [
    # (id, the row's changes, the field named): the analyst's three probes first
    ("lone surrogate title", {"name": "Bad \ud800 title"}, "name"),
    (
        "control characters in downloads",
        {"downloads": [{"id": f"{n:032x}", "name": "\x01" * 200, "file": "\x01" * 2048} for n in range(50)]},
        "downloads_json",
    ),
    ("NUL in a slug", {"slug": "a\x00b"}, "slug"),
    ("NUL in a title by entity", {"name": "a&#0;b\x00"}, "name"),
    ("lone surrogate in a file", {"downloads": [{"id": "a", "name": "Download", "file": "\udfff"}]}, "downloads.file"),
    ("NUL in a download id", {"downloads": [{"id": "a\x00", "name": "Download", "file": "f"}]}, "downloads.id"),
]


@pytest.mark.parametrize(("changes", "field_name"), [p[1:] for p in TEXT_PROBES], ids=[p[0] for p in TEXT_PROBES])
def test_text_the_database_could_not_hold_is_a_bad_response_naming_its_field(
    changes: dict[str, Any], field_name: str
) -> None:
    """Analyst finding 1: a NUL, a lone surrogate, or a download or meta list whose stored JSON would pass its CHECK
    (control characters take six characters once escaped) fail in the reader, not in the save."""
    raw = raw_product(1)
    raw.update(changes)
    result = read(FakeCatalogStore(rows=[raw]))
    assert (result.reason, result.products, result.bad_field, result.bad_page) == ("bad_response", (), field_name, 1)


def test_the_largest_lists_that_fit_their_limits_are_read() -> None:
    downloads = [{"id": f"{n:032x}", "name": "n" * 200, "file": "f" * 2048} for n in range(50)]
    meta = [{"key": "latest_version" + "k" * 239 + f"{n:02d}", "value": "v" * 200} for n in range(50)]
    [found] = read(FakeCatalogStore(rows=[raw_product(1, downloads=downloads, meta=meta)])).products
    assert len(found.downloads) == 50 and len(found.meta) == 50


def test_a_whole_listing_over_its_byte_cap_is_a_bad_response() -> None:
    """Analyst finding 7 (Lead (proposed): 64 MiB); here with a small cap."""
    store = FakeCatalogStore(rows=rows(250))
    result = read(store, listing_max_bytes=60_000)
    assert (result.reason, result.bad_field) == ("bad_response", "listing_bytes")
    assert result.bad_page is not None and result.bad_page > 1


def test_a_bad_header_names_itself_and_page_one() -> None:
    result = read(FakeCatalogStore(rows=rows(1), total_header="many"))
    assert (result.reason, result.bad_field, result.bad_page) == ("bad_response", "x-wp-total", 1)
    result = read(FakeCatalogStore(rows=rows(1), status_answer=httpx.Response(200, json={"environment": {}})))
    assert (result.reason, result.bad_field, result.bad_page) == ("bad_response", "version", None)


def test_an_empty_slug_a_trashed_slug_and_no_downloads_are_read_as_they_are() -> None:
    raws = [raw_product(1, "", status="draft"), raw_product(2, "old-slider__trashed"), raw_product(3, downloads=[])]
    result = read(FakeCatalogStore(rows=raws))
    assert [(p.slug, p.status, len(p.downloads)) for p in result.products] == [
        ("", "draft", 1),
        ("old-slider__trashed", "publish", 1),
        ("product-3", "publish", 0),
    ]


# ---- the stop ------------------------------------------------------------------------------------------------------


def test_a_stop_during_a_wait_ends_the_read_with_stopped_and_nothing() -> None:
    store = FakeCatalogStore(rows=rows(250))
    store.time.stop_after = 2  # the stop arrives during the second wait
    result = read(store)
    assert (result.reason, result.products) == ("stopped", ())
    assert len(store.requests) == 2


def test_a_stop_asked_before_the_read_sends_nothing() -> None:
    store = FakeCatalogStore(rows=rows(1))
    store.time.stop()
    assert read(store).reason == "stopped" and store.requests == []


# ---- the log -------------------------------------------------------------------------------------------------------


def test_one_line_per_read_with_the_code_outcome_counts_and_last_status_and_nothing_else(
    caplog: pytest.LogCaptureFixture,
) -> None:
    # The catalog logger's own level is set here, so the result doesn't hang on what an earlier test or import left.
    caplog.set_level(logging.DEBUG)
    caplog.set_level(logging.DEBUG, logger="shelfsync.catalog")
    leaky = [raw_product(1, "secret-slug", f"Title {KEY}", downloads=[download(key="bucket-object-key.zip")])]
    hostile = [raw_product(1, "secret-slug", f"Title {KEY}\x00", downloads=[download(key="bucket-object-key.zip")])]
    for store in (
        FakeCatalogStore(rows=leaky, answers=[answer(524)]),
        FakeCatalogStore(rows=leaky, answers=[wp_error(401, f"woocommerce_rest_cannot_view {KEY}:{SECRET}")]),
        FakeCatalogStore(rows=hostile),
    ):
        with WooClient(STORE_URL, KEY, SECRET, transport=store.transport, monotonic=store.time.monotonic) as client:
            read_store_catalog(
                client,
                "GF",
                spacing_ms=150,
                stop=store.time,
                failures=MemoryFailureCount(),
                monotonic=store.time.monotonic,
                now=store.time.wall,
            )
    lines = [record.getMessage() for record in caplog.records if record.name.startswith("shelfsync")]
    assert lines == [
        "Store GF catalog read: ok (pages 1, rows 1, last failure HTTP 524)",
        "Store GF catalog read: keys_refused (pages 0, rows 0, last failure HTTP 401)",
        "Store GF catalog read: bad_response (pages 1, rows 0, last failure HTTP None; field name on page 1)",
    ]
    everything = "\n".join(record.getMessage() for record in caplog.records)
    for forbidden in ("store-a.example", KEY, SECRET, "secret-slug", "bucket-object-key", "downloadable", "Basic"):
        assert forbidden not in everything


# ---- cookies -------------------------------------------------------------------------------------------------------

BENIGN_COOKIE = f"wp_session=SECRET-{KEY}; Path=/"
HOSTILE_COOKIES = [
    "cf_bm=abc; Path=/; Expires=Wed, 99 Foo 2026 99:99:99 GMT",  # http.cookiejar can't read this date and warns
    "x=1; Domain=elsewhere.example; Max-Age=nonsense",
]


def cookies(*values: str) -> list[tuple[str, str]]:
    return [("Set-Cookie", value) for value in values]


def cookie_answer(request: httpx.Request) -> httpx.Response:
    headers = [*cookies(BENIGN_COOKIE, *HOSTILE_COOKIES), ("Set-Cookie2", "y=1; Version=1")]
    if request.url.path.endswith(SYSTEM_STATUS):
        body: Any = {"environment": {"version": "11.2.1", "wp_version": "7.1"}}
    else:
        headers += [("X-WP-Total", "1"), ("X-WP-TotalPages", "1")]
        body = [raw_product(1)]
    return unread(httpx.Response(200, headers=headers, json=body))


def test_the_control_a_plain_client_keeps_a_cookie_and_warns_about_one_it_cannot_read() -> None:
    """Without the drop, httpx's jar keeps the store's cookie, and `http.cookiejar` warns about a cookie it can't
    read (t8's side note; `logging.captureWarnings` would put that warning in the app log)."""
    benign = httpx.MockTransport(lambda request: httpx.Response(200, headers=cookies(BENIGN_COOKIE)))
    with httpx.Client(transport=benign) as plain:
        plain.get(STORE_URL + SYSTEM_STATUS)
        assert len(plain.cookies.jar) == 1
    hostile = httpx.MockTransport(lambda request: httpx.Response(200, headers=cookies(HOSTILE_COOKIES[0])))
    with httpx.Client(transport=hostile) as plain, pytest.warns(UserWarning, match="cookiejar"):
        plain.get(STORE_URL + SYSTEM_STATUS)


def test_no_cookie_is_kept_logged_or_warned_about_in_a_catalog_read_or_a_test_connection(
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.DEBUG)
    time = FakeTime()
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        with WooClient(
            STORE_URL, KEY, SECRET, transport=httpx.MockTransport(cookie_answer), monotonic=time.monotonic
        ) as client:
            result = read_catalog(
                client,
                spacing_ms=150,
                stop=time,
                failures=MemoryFailureCount(),
                monotonic=time.monotonic,
                now=time.wall,
            )
            outcome = run_read_test(client, 150, "GF", sleep=lambda seconds: None, monotonic=time.monotonic)
            assert len(client._client.cookies.jar) == 0
    assert result.ok and outcome.ok
    assert caught == []
    text = "\n".join(record.getMessage() for record in caplog.records)
    for part in ("wp_session", "SECRET-", "cf_bm", KEY, "Set-Cookie", "cookiejar"):
        assert part not in text


def test_the_transport_drops_every_set_cookie_header_and_keeps_the_rest() -> None:
    from shelfsync.apply.woocommerce import GetOnlyTransport

    transport = GetOnlyTransport(httpx.MockTransport(cookie_answer))
    response = transport.handle_request(httpx.Request("GET", STORE_URL + PRODUCTS))
    assert "set-cookie" not in response.headers and "set-cookie2" not in response.headers
    assert response.headers["x-wp-total"] == "1"
    transport.close()


# ---- review 2 (m3.1) -----------------------------------------------------------------------------------------------

META_SKIPS: list[tuple[str, list[dict[str, Any]], int | None]] = [
    # (id, meta_data, entries skipped): the analyst's meta probe, and the cases that used to fail the whole read
    (
        "control characters in meta",
        [{"key": "latest_version" + "\x01" * 200 + str(n), "value": "\x01" * 200} for n in range(50)],
        None,  # some are skipped until the stored JSON fits
    ),
    ("NUL in a meta key", [{"key": "latest_version\x00", "value": "1"}], 1),
    ("surrogate in a meta value", [{"key": "latest_version", "value": "\ud83d"}], 1),
    ("latest_version not text", [{"key": "latest_version", "value": ["1"]}], 1),
    ("latest_version too long", [{"key": "latest_version", "value": "1" * 201}], 1),
    ("a key too long", [{"key": "latest_version" + "k" * 300, "value": "1"}], 1),
    ("past the 50 kept", [{"key": f"latest_version_{n}", "value": "1"} for n in range(52)], 3),  # 1 + 52 - 50
]


@pytest.mark.parametrize(("meta", "skipped"), [m[1:] for m in META_SKIPS], ids=[m[0] for m in META_SKIPS])
def test_an_unusable_latest_version_entry_is_skipped_and_counted_not_the_whole_read(
    meta: list[dict[str, Any]], skipped: int | None
) -> None:
    """Review 2, finding 4 (Lead (proposed)): a bad `latest_version*` entry costs only itself; good ones stay."""
    good = {"id": 9, "key": "latest_version", "value": "2.0"}
    result = read(FakeCatalogStore(rows=[raw_product(1, meta=[good, *meta])])).products
    [found] = result
    assert found.meta[0] == ("latest_version", "2.0")
    if skipped is None:
        assert found.meta_skipped > 0 and len(meta_json(found.meta)) <= META_JSON_MAX
    else:
        assert found.meta_skipped == skipped and len(found.meta) == 1 + len(meta) - skipped


def test_a_store_that_keeps_sending_a_bad_page_is_auto_paused_after_ten() -> None:
    """Review 2, finding 2: a 200 the reader can't use counts as a failed request for APL-12, and `system_status`
    answering doesn't reset the count, so ten reads that each get a bad page auto-pause the store."""
    failures = MemoryFailureCount()
    for run in range(1, 11):
        result = read(FakeCatalogStore(rows=rows(1), answers=[page_of({"id": 1})]), failures=failures)
        assert (result.reason, result.bad_field, failures.count) == ("bad_response", "page", run)
    assert result.auto_paused and failures.paused_reason == "bad_response"
    failures = MemoryFailureCount()
    for run in range(1, 4):
        store = FakeCatalogStore(rows=rows(1), status_answer=page_of({"theme": {}}))  # a 200 with no environment
        result = read(store, failures=failures)
        assert (result.reason, result.bad_field, failures.count) == ("bad_response", "environment", run)
    assert read(FakeCatalogStore(rows=rows(1)), failures=failures).ok and failures.count == 0  # a usable page


def test_a_400_on_a_later_page_is_read_as_the_listing_shrinking_and_read_once_more() -> None:
    """Review 2, finding 3: WooCommerce answers 400 for a page past the last (not verified on a store): the listing
    ended early, so the count check reads it again; a second short listing is `count_mismatch`."""
    store = FakeCatalogStore(rows=rows(150))
    calls: list[int] = []

    def page_two_gone(request: httpx.Request) -> httpx.Response:
        return httpx.Response(400, json={"code": "rest_post_invalid_page_number", "message": "x", "data": {}})

    def before(page: int) -> None:
        calls.append(page)
        if page == 1 and len(calls) == 1:
            store.answers.append(page_two_gone)

    store.before_page = before
    failures = MemoryFailureCount()
    result = read(store, failures=failures)
    assert result.ok and len(result.products) == 150 and failures.count == 0
    always = FakeCatalogStore(rows=rows(150))
    always.before_page = lambda page: always.answers.append(page_two_gone) if page == 1 else None
    assert read(always).reason == "count_mismatch"

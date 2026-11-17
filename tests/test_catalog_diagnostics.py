"""CAT-01, APL-12: the reader's diagnostics for the L1 dry read (t9), against fakes only (httpx.MockTransport, RFC
2606 hosts): the observer's record of every attempt (a normal read, a 429 replayed, a timeout before the headers and
one during the body, the other refusals), the response facts as fixed words read before the cookie drop (with their
allowlists), the reader options (`meta`, `per_page`, `max_pages`), and the app's read unchanged without them."""

import inspect
import string
from typing import Any

import httpx
import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from shelfsync.apply import catalog_read
from shelfsync.apply.catalog_read import (
    CACHE_WORDS,
    COOKIE_WORDS,
    LISTING_FIELDS,
    LISTING_FIELDS_NO_META,
    MAX_PAGES,
    PER_PAGE,
    SERVER_WORDS,
    Attempt,
    CatalogRead,
    FactsTransport,
    MemoryFailureCount,
    ResponseFacts,
    listing_params,
    read_catalog,
    response_facts,
)
from shelfsync.apply.woocommerce import WooClient
from shelfsync.catalog import runner
from tests.catalog_support import FakeCatalogStore, make_catalog_rig, raw_product
from tests.store_support import KEY, SECRET, STORE_URL, StallingStream, stalling


def rows(count: int, start: int = 1, **options: Any) -> list[dict[str, Any]]:
    return [raw_product(wc_id, **options) for wc_id in range(start, start + count)]


def read(
    store: FakeCatalogStore,
    *,
    transport: httpx.BaseTransport | None = None,
    **options: Any,
) -> CatalogRead:
    time = store.time
    with WooClient(STORE_URL, KEY, SECRET, transport=transport or store.transport, monotonic=time.monotonic) as client:
        return read_catalog(
            client,
            spacing_ms=150,
            stop=time,
            failures=MemoryFailureCount(),
            monotonic=time.monotonic,
            now=time.wall,
            **options,
        )


def observed(store: FakeCatalogStore, **options: Any) -> tuple[CatalogRead, list[Attempt]]:
    seen: list[Attempt] = []
    return read(store, observe=seen.append, **options), seen


def brief(attempt: Attempt) -> tuple[Any, ...]:
    return (attempt.what, attempt.page, attempt.attempt, attempt.outcome, attempt.http_status, attempt.headers)


# ---- the observer's records -----------------------------------------------------------------------------------------


def test_a_normal_read_gives_one_record_per_request_with_its_status_bytes_and_time() -> None:
    store = FakeCatalogStore(rows=rows(250))
    store.before_page = lambda page: setattr(store.time, "now", store.time.now + 0.25 * page)
    result, seen = observed(store)
    assert result.ok and len(seen) == result.requests == 4
    assert [brief(a) for a in seen] == [
        ("system_status", None, 1, "ok", 200, True),
        ("products", 1, 1, "ok", 200, True),
        ("products", 2, 1, "ok", 200, True),
        ("products", 3, 1, "ok", 200, True),
    ]
    assert [a.elapsed_ms for a in seen] == [0, 250, 500, 750]  # the request alone, never the spacing before it
    assert seen[0].body_bytes is not None and seen[0].body_bytes > 0
    assert max(a.body_bytes or 0 for a in seen[1:]) == result.largest_page_bytes
    assert all(a.facts is None for a in seen)  # no `FactsTransport`: no facts


def test_a_429_replayed_is_two_attempts_at_the_same_page() -> None:
    """APL-12 Accept: the 429 and its retry, each recorded with its attempt number."""
    store = FakeCatalogStore(rows=rows(3), answers=[httpx.Response(429, headers={"Retry-After": "7"})])
    result, seen = observed(store)
    assert result.ok
    assert [brief(a) for a in seen] == [
        ("system_status", None, 1, "ok", 200, True),
        ("products", 1, 1, "rate_limited", 429, True),
        ("products", 1, 2, "ok", 200, True),
    ]
    assert seen[1].body_bytes == 0


def test_a_timeout_before_the_headers_says_nothing_came() -> None:
    def silent(request: httpx.Request) -> httpx.Response:
        store.time.now += 30.0
        raise httpx.ReadTimeout("no answer")

    store = FakeCatalogStore(rows=rows(3), answers=[silent])
    result, seen = observed(store)
    assert result.ok
    first = seen[1]
    assert brief(first) == ("products", 1, 1, "timeout", None, False)
    assert (first.body_bytes, first.elapsed_ms) == (0, 30_000)
    assert brief(seen[2]) == ("products", 1, 2, "ok", 200, True)


def test_a_timeout_during_the_body_says_the_headers_had_arrived_and_how_many_bytes_came() -> None:
    store = FakeCatalogStore(rows=rows(3), answers=[stalling(200, [b"[" + b" " * 4095, b" " * 4096])])
    result, seen = observed(store)
    assert result.ok and result.http_status is None  # the read's own result is as it always was
    assert brief(seen[1]) == ("products", 1, 1, "timeout", 200, True)
    assert seen[1].body_bytes == 8192


def test_a_body_that_passes_the_stores_bound_is_recorded_the_same_way() -> None:
    store = FakeCatalogStore(rows=rows(3))
    store.answers = [
        lambda request: httpx.Response(
            200,
            stream=StallingStream([b"[" * 10], before_chunk=lambda: setattr(store.time, "now", store.time.now + 700.0)),
        )
    ]
    result, seen = observed(store)
    assert result.reason == "timeout"
    assert brief(seen[-1]) == ("products", 1, 1, "timeout", 200, True) and seen[-1].body_bytes == 10


def _connect_error(request: httpx.Request) -> httpx.Response:
    raise httpx.ConnectError("refused")


@pytest.mark.parametrize(
    ("answer", "outcome", "status", "headers", "body_bytes"),
    [
        (httpx.Response(301, headers={"Location": "https://elsewhere.example/"}), "redirected", 301, True, None),
        (httpx.Response(200, headers={"Content-Length": str(9 * 1024 * 1024)}), "bad_response", None, True, None),
        (_connect_error, "unreachable", None, None, None),  # with no `FactsTransport`, not known
        (httpx.Response(503, content=b"<html>busy</html>"), "blocked", 503, True, 17),
    ],
    ids=["redirect", "too long", "unreachable", "503 page"],
)
def test_every_other_outcome_is_recorded_with_what_is_known(
    answer: Any, outcome: str, status: int | None, headers: bool | None, body_bytes: int | None
) -> None:
    store = FakeCatalogStore(rows=rows(3), answers=[answer])
    _, seen = observed(store)
    assert brief(seen[1]) == ("products", 1, 1, outcome, status, headers) and seen[1].body_bytes == body_bytes


def test_with_the_facts_transport_a_failed_connection_says_whether_headers_came() -> None:
    store = FakeCatalogStore(rows=rows(3), answers=[_connect_error])
    _, seen = observed(store, transport=FactsTransport(store.transport), facts=None)
    assert seen[1].headers is None  # the transport is there, but the reader wasn't given it
    store = FakeCatalogStore(rows=rows(3), answers=[_connect_error])
    facts = FactsTransport(store.transport)
    _, seen = observed(store, transport=facts, facts=facts)
    assert seen[1].headers is False and seen[1].facts is None
    assert seen[2].facts is not None  # the retry's answer came


def test_a_400_past_the_last_page_is_recorded_as_past_the_end() -> None:
    store = FakeCatalogStore(rows=rows(150))
    gone = httpx.Response(400, json={"code": "rest_post_invalid_page_number", "message": "x", "data": {}})
    store.before_page = lambda page: store.answers.append(gone) if page == 1 and len(store.requests) == 2 else None
    result, seen = observed(store)
    assert result.ok
    assert ("products", 2, 1, "past_the_end", 400, True) in [brief(a) for a in seen]


def test_an_auto_pause_still_records_the_attempt_that_caused_it() -> None:
    store = FakeCatalogStore(rows=rows(2), status_answer=httpx.Response(500))
    seen: list[Attempt] = []
    result = read_catalog_with(store, MemoryFailureCount(start=9), seen)
    assert result.auto_paused and [brief(a) for a in seen] == [("system_status", None, 1, "server_error", 500, True)]


def read_catalog_with(store: FakeCatalogStore, failures: MemoryFailureCount, seen: list[Attempt]) -> CatalogRead:
    time = store.time
    with WooClient(STORE_URL, KEY, SECRET, transport=store.transport, monotonic=time.monotonic) as client:
        return read_catalog(
            client,
            spacing_ms=150,
            stop=time,
            failures=failures,
            monotonic=time.monotonic,
            now=time.wall,
            observe=seen.append,
        )


# ---- the response facts ---------------------------------------------------------------------------------------------

STORE_COOKIES = [
    ("Set-Cookie", "__cf_bm=VALUE-ONE.abc; path=/; expires=Wed, 18-Nov-26 10:00:00 GMT; HttpOnly; Secure"),
    ("Set-Cookie", "wordpress_logged_in_0123456789abcdef0123456789abcdef=VALUE-TWO; path=/"),
    ("Set-Cookie", "wp-settings-time-1=VALUE-THREE; path=/"),
    ("Set-Cookie", "mystery_cookie=VALUE-FOUR; path=/"),
    ("Set-Cookie2", "__cf_bm=VALUE-FIVE; Version=1"),
]
FACT_HEADERS = [
    ("Server", "cloudflare"),
    ("CF-RAY", "8f00aa11bb22cc33-LHR"),
    ("CF-Cache-Status", "DYNAMIC"),
    *STORE_COOKIES,
]


def with_headers(store: FakeCatalogStore, extra: list[tuple[str, str]]) -> httpx.MockTransport:
    """The fake store's answers, each with `extra` headers added (repeated names kept)."""

    def handler(request: httpx.Request) -> httpx.Response:
        response = store(request)
        return httpx.Response(
            response.status_code, headers=[*response.headers.multi_items(), *extra], stream=response.stream
        )

    return httpx.MockTransport(handler)


def test_the_facts_are_read_before_the_cookie_drop_and_no_cookie_is_kept_or_sent_back() -> None:
    store = FakeCatalogStore(rows=rows(150))
    facts = FactsTransport(with_headers(store, FACT_HEADERS))
    seen: list[Attempt] = []
    time = store.time
    with WooClient(STORE_URL, KEY, SECRET, transport=facts, monotonic=time.monotonic) as client:
        result = read_catalog(
            client,
            spacing_ms=150,
            stop=time,
            failures=MemoryFailureCount(),
            monotonic=time.monotonic,
            now=time.wall,
            observe=seen.append,
            facts=facts,
        )
        assert len(client._client.cookies.jar) == 0
    assert result.ok and len(seen) == 3
    expected = ResponseFacts(True, "cloudflare", "dynamic", ("__cf_bm", "wordpress_logged_in", "wp-settings"), 1)
    assert all(attempt.facts == expected for attempt in seen)
    assert all("cookie" not in request.headers for request in store.requests)
    text = repr(seen)
    for part in ("VALUE-", "mystery", "0123456789abcdef", "8f00aa11", "LHR", "path=", "store-a"):
        assert part not in text


@pytest.mark.parametrize(
    ("server", "word"),
    [
        ("cloudflare", "cloudflare"),
        ("nginx/1.25.3", "nginx"),
        ("Apache/2.4.62 (Ubuntu)", "apache"),
        ("LiteSpeed", "litespeed"),
        ("openresty/1.21.4.1", "openresty"),
        ("  NGINX  ", "nginx"),
        ("nginx, cloudflare", "nginx"),  # two `Server` headers, joined by httpx
        ("Microsoft-IIS/10.0", "other"),
        ("store-a.example", "other"),
        ("", "other"),
        (None, "none"),
    ],
)
def test_the_server_header_becomes_one_fixed_word(server: str | None, word: str) -> None:
    headers = httpx.Headers({} if server is None else {"Server": server})
    assert response_facts(headers).server == word


@pytest.mark.parametrize(
    ("value", "word"),
    [
        ("HIT", "hit"),
        ("miss", "miss"),
        ("Dynamic", "dynamic"),
        ("BYPASS", "bypass"),
        ("EXPIRED", "expired"),
        ("REVALIDATED", "other"),
        ("hit; secret", "other"),
        (None, "none"),
    ],
)
def test_cf_cache_status_becomes_one_fixed_word(value: str | None, word: str) -> None:
    headers = httpx.Headers({} if value is None else {"CF-Cache-Status": value})
    assert response_facts(headers).cache == word


@pytest.mark.parametrize(
    ("cookie", "word"),
    [
        ("__cf_bm=a", "__cf_bm"),
        ("cf_clearance=a", "cf_clearance"),
        ("_cfuvid=a", "_cfuvid"),
        ("PHPSESSID=a", "PHPSESSID"),
        (" PHPSESSID =a", "PHPSESSID"),
        ("wordpress_logged_in=a", "wordpress_logged_in"),
        ("wordpress_logged_in_abc123=a", "wordpress_logged_in"),
        ("wordpress_sec_abc123=a", "wordpress_sec"),
        ("wp-settings-1=a", "wp-settings"),
        ("wp-settings-time-1=a", "wp-settings"),
        ("phpsessid=a", None),  # names are case-sensitive
        ("PHPSESSIDX=a", None),
        ("wordpress_abc123=a", None),  # WordPress's admin cookie: not listed
        ("wordpress_logged_inx=a", None),
        ("wp-settingsx=a", None),
        ("__cf_bm", None),  # no `=`: no cookie name
        ("=a", None),
    ],
)
def test_only_allowlisted_cookie_names_are_kept_and_any_other_is_counted(cookie: str, word: str | None) -> None:
    facts = response_facts(httpx.Headers([("Set-Cookie", cookie)]))
    assert (facts.cookies, facts.other_cookies) == (((word,), 0) if word else ((), 1))


def test_no_header_at_all_gives_none_and_nothing() -> None:
    assert response_facts(httpx.Headers()) == ResponseFacts(False, "none", "none", (), 0)


_HEADER_TEXT = st.text(alphabet=string.ascii_letters + string.digits + string.punctuation + " ", max_size=60)


@settings(max_examples=200, deadline=None)
@given(
    server=_HEADER_TEXT,
    cache=_HEADER_TEXT,
    cookies=st.lists(st.tuples(_HEADER_TEXT, _HEADER_TEXT), max_size=6),
)
def test_whatever_the_headers_say_the_facts_hold_fixed_words_and_counts_only(
    server: str, cache: str, cookies: list[tuple[str, str]]
) -> None:
    marker = "QZXMARKER"
    headers = httpx.Headers(
        [
            ("Server", server + marker),
            ("CF-Cache-Status", cache + marker),
            *(("Set-Cookie", f"{name}{marker}={value}{marker}") for name, value in cookies),
        ]
    )
    facts = response_facts(headers)
    assert facts.server in (*SERVER_WORDS, "other", "none")
    assert facts.cache in (*CACHE_WORDS, "other", "none")
    assert set(facts.cookies) <= set(COOKIE_WORDS) and len(facts.cookies) + facts.other_cookies <= len(cookies)
    assert marker.lower() not in repr(facts).lower()


def test_the_facts_transport_hands_the_answer_on_unchanged_and_its_facts_once() -> None:
    inner = httpx.MockTransport(lambda request: httpx.Response(200, headers=FACT_HEADERS, content=b"[]"))
    facts = FactsTransport(inner)
    assert facts.take() is None and not facts.seen()
    response = facts.handle_request(httpx.Request("GET", STORE_URL))
    assert response.headers.get_list("set-cookie") == [value for name, value in STORE_COOKIES if name == "Set-Cookie"]
    assert facts.seen() and facts.take() is not None and facts.take() is None
    facts.close()


# ---- the reader options (L1 only) -----------------------------------------------------------------------------------


def test_meta_false_asks_without_meta_data_and_keeps_no_latest_version_data() -> None:
    latest = [{"id": 1, "key": "latest_version", "value": "2.0"}]
    store = FakeCatalogStore(rows=rows(3, meta=latest))
    result = read(store, meta=False)
    assert result.ok and all(p.meta == () and p.meta_skipped == 0 for p in result.products)
    assert store.product_requests()[0].url.params["_fields"] == LISTING_FIELDS_NO_META
    assert LISTING_FIELDS_NO_META + ",meta_data" == LISTING_FIELDS
    bare = [{k: v for k, v in row.items() if k != "meta_data"} for row in rows(3)]
    assert read(FakeCatalogStore(rows=bare), meta=False).ok  # as the store answers it: no `meta_data` at all
    assert read(FakeCatalogStore(rows=bare)).reason == "bad_response"  # the control: the app needs it


def test_per_page_and_max_pages_change_the_pages_asked_for() -> None:
    store = FakeCatalogStore(rows=rows(130))
    result = read(store, per_page=25, max_pages=160)
    assert result.ok and len(result.products) == 130 and result.pages == 6
    sent = [dict(request.url.params) for request in store.product_requests()]
    assert sent == [listing_params(page, per_page=25) for page in range(1, 7)]
    assert {params["per_page"] for params in sent} == {"25"}
    store = FakeCatalogStore(rows=rows(130))
    assert read(store, per_page=25, max_pages=5).reason == "too_many_pages" and len(store.product_requests()) == 1


def test_the_options_together_send_exactly_what_listing_params_builds() -> None:
    store = FakeCatalogStore(rows=rows(60))
    assert read(store, per_page=50, meta=False).ok
    sent = [dict(request.url.params) for request in store.product_requests()]
    assert sent == [listing_params(1, per_page=50, meta=False), listing_params(2, per_page=50, meta=False)]


def test_a_page_with_more_rows_than_asked_for_is_a_bad_response() -> None:
    page = httpx.Response(200, headers={"X-WP-Total": "26", "X-WP-TotalPages": "1"}, json=rows(26))
    result = read(FakeCatalogStore(rows=rows(26), answers=[page]), per_page=25)
    assert (result.reason, result.bad_field, result.bad_page) == ("bad_response", "page", 1)


@pytest.mark.parametrize(
    "options",
    [{"per_page": 24}, {"per_page": 101}, {"max_pages": 0}, {"per_page": 25, "max_pages": 161}, {"max_pages": 41}],
)
def test_options_outside_their_range_are_refused_before_anything_is_sent(options: dict[str, Any]) -> None:
    store = FakeCatalogStore(rows=rows(3))
    with pytest.raises(ValueError):
        read(store, **options)
    assert store.requests == []


# ---- the app's read is unchanged ------------------------------------------------------------------------------------


def _replay() -> FakeCatalogStore:
    """A store that answers with a 524, a 429, a stall during the body and a 400 past the end on the way."""
    store = FakeCatalogStore(
        rows=rows(150, meta=[{"id": 1, "key": "latest_version", "value": "1.0"}]),
        answers=[httpx.Response(524), httpx.Response(429, headers={"Retry-After": "3"}), stalling(200, [b"[ "])],
    )
    gone = httpx.Response(400, json={"code": "rest_post_invalid_page_number", "message": "x", "data": {}})
    store.before_page = lambda page: store.answers.append(gone) if len(store.requests) == 5 else None
    return store


def test_without_an_observer_the_read_is_the_same_requests_and_the_same_result() -> None:
    plain = _replay()
    result = read(plain)
    watched = _replay()
    facts = FactsTransport(watched.transport)
    seen: list[Attempt] = []
    observed_result = read(watched, transport=facts, observe=seen.append, facts=facts)
    assert observed_result == result and result.ok
    assert len(seen) == result.requests == len(plain.requests)
    assert [(r.method, str(r.url), r.headers.multi_items()) for r in plain.requests] == [
        (r.method, str(r.url), r.headers.multi_items()) for r in watched.requests
    ]
    assert plain.time.waits == watched.time.waits
    assert [a.outcome for a in seen].count("past_the_end") == 1


def test_the_defaults_are_the_apps_and_the_runner_sets_none_of_the_l1_options(monkeypatch: pytest.MonkeyPatch) -> None:
    defaults = {
        name: parameter.default
        for name, parameter in inspect.signature(read_catalog).parameters.items()
        if name in ("observe", "facts", "meta", "per_page", "max_pages")
    }
    assert defaults == {"observe": None, "facts": None, "meta": True, "per_page": PER_PAGE, "max_pages": MAX_PAGES}
    calls: list[dict[str, Any]] = []
    real = catalog_read.read_catalog

    def spy(client: WooClient, **options: Any) -> CatalogRead:
        calls.append(options)
        return real(client, **options)

    monkeypatch.setattr(runner, "read_catalog", spy)
    rig = make_catalog_rig(fake_time=True)
    rig.add_store("GF", rows(120))
    rig.run()
    assert len(calls) == 1 and not {"observe", "facts", "meta", "per_page", "max_pages"} & calls[0].keys()
    sent = [dict(r.url.params) for r in rig.sites.requests if r.url.path.endswith("/products")]
    assert sent == [listing_params(1), listing_params(2)]
    assert sent[0]["per_page"] == "100" and sent[0]["_fields"] == LISTING_FIELDS

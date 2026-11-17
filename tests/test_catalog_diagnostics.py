"""CAT-01, APL-12: the reader's diagnostics for the L1 dry read (t9), against fakes only (httpx.MockTransport, RFC
2606 hosts): the observer's record of every attempt (a normal read, a 429 replayed, a timeout before the headers and
one during the body, the other refusals), the response facts as fixed words read before the cookie drop (with their
allowlists), the reader options (`meta`, `per_page`, `max_pages`), and the app's read unchanged without them."""

import ast
import gc
import inspect
import string
import weakref
from collections.abc import Iterator
from dataclasses import replace
from pathlib import Path
from typing import Any

import httpx
import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from shelfsync.apply import catalog_read
from shelfsync.apply.catalog_read import (
    CACHE_WORDS,
    COOKIE_WORDS,
    ERROR_WORDS,
    HINT_HEADERS,
    LISTING_FIELDS,
    LISTING_FIELDS_NO_META,
    MAX_PAGES,
    PER_PAGE,
    SERVER_WORDS,
    STAGES,
    Attempt,
    CatalogRead,
    FactsTransport,
    MemoryFailureCount,
    ResponseFacts,
    Wire,
    error_word,
    listing_params,
    read_catalog,
    response_facts,
)
from shelfsync.apply.woocommerce import DECLARED_MAX, NonGetRefused, WooClient
from shelfsync.catalog import runner
from tests.catalog_support import FakeCatalogStore, FakeTime, make_catalog_rig, raw_product
from tests.store_support import KEY, PRODUCTS, SECRET, STORE_URL, StallingStream, stalling


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
    ("CF-Mitigated", "challenge-VALUE-SIX"),
    ("X-LiteSpeed-Cache", "hit-VALUE-SEVEN"),
    ("X-RateLimit-Remaining", "VALUE-EIGHT"),
    ("X-Powered-By", "VALUE-NINE"),
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
    expected = ResponseFacts(
        True,
        "cloudflare",
        "dynamic",
        ("__cf_bm", "wordpress_logged_in", "wp-settings"),
        1,
        content="json",  # system_status's answer (`json=`); the fake's pages carry no Content-Type
        cf_mitigated=True,
        retry_after=False,
        hints=("x-litespeed-cache", "x-ratelimit-remaining"),
    )
    assert [attempt.facts for attempt in seen] == [expected, *[replace(expected, content="none")] * 2]
    assert all("cookie" not in request.headers for request in store.requests)
    text = repr(seen)
    for part in ("VALUE-", "mystery", "0123456789abcdef", "8f00aa11", "LHR", "path=", "store-a", "challenge"):
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
    assert response_facts(httpx.Headers()) == ResponseFacts(False, "none", "none", (), 0, "none", False, False, ())


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
    assert facts.take() is None
    response = facts.handle_request(httpx.Request("GET", STORE_URL))
    assert response.headers.get_list("set-cookie") == [value for name, value in STORE_COOKIES if name == "Set-Cookie"]
    wire = facts.take()
    assert wire is not None and wire.facts is not None and facts.take() is None
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
        if name in L1_OPTIONS
    }
    assert defaults == {
        "observe": None,
        "facts": None,
        "meta": True,
        "per_page": PER_PAGE,
        "max_pages": MAX_PAGES,
        "attempt_seconds": None,
    }
    calls: list[dict[str, Any]] = []
    real = catalog_read.read_catalog

    def spy(client: WooClient, **options: Any) -> CatalogRead:
        calls.append(options)
        return real(client, **options)

    monkeypatch.setattr(runner, "read_catalog", spy)
    rig = make_catalog_rig(fake_time=True)
    rig.add_store("GF", rows(120))
    rig.run()
    assert len(calls) == 1 and not L1_OPTIONS & calls[0].keys()
    sent = [dict(r.url.params) for r in rig.sites.requests if r.url.path.endswith("/products")]
    assert sent == [listing_params(1), listing_params(2)]
    assert sent[0]["per_page"] == "100" and sent[0]["_fields"] == LISTING_FIELDS


L1_OPTIONS = frozenset({"observe", "facts", "meta", "per_page", "max_pages", "attempt_seconds"})


def test_no_app_caller_sets_an_l1_option_or_the_read_timeout() -> None:
    """Only L1 (`catalog/report.py`) passes `read_seconds` to `WooClient` or an L1 option to the reader; inside the
    reader they are only handed on. Every other caller in the app keeps today's values (finding 5, the lead's
    decision)."""
    backend = Path(__file__).resolve().parents[1] / "backend" / "shelfsync"
    found: dict[str, set[str]] = {}
    for path in backend.rglob("*.py"):
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if isinstance(node, ast.Call):
                for keyword in node.keywords:
                    if keyword.arg in L1_OPTIONS | {"read_seconds"}:
                        found.setdefault(path.relative_to(backend).as_posix(), set()).add(keyword.arg)
    assert set(found) <= {"catalog/report.py", "apply/catalog_read.py"}
    assert found.get("apply/catalog_read.py", set()) <= {"observe", "facts", "attempt_seconds", "meta", "per_page"}


# ---- the stage of a stall: httpcore's trace events (the analyst's finding 1) ---------------------------------------


class Clock:
    def __init__(self) -> None:
        self.now = 50.0

    def monotonic(self) -> float:
        return self.now


class Secretive:
    """What httpcore's `info` holds: the request, with its address, query and `Authorization`."""

    def __init__(self) -> None:
        self.text = f"https://store-a.example/wp-json/wc/v3/products?consumer_key={KEY} Authorization: Basic {SECRET}"


def traced(events: list[tuple[str, float]], response: httpx.Response | Exception, clock: Clock) -> httpx.MockTransport:
    """A transport that fires httpcore-named trace events (each after moving the clock) through the request's
    `trace` extension, with a secret-laden `info`, then answers or fails."""

    def handler(request: httpx.Request) -> httpx.Response:
        trace = request.extensions["trace"]
        for name, after in events:
            clock.now += after
            trace(name, {"request": Secretive(), "return_value": Secretive()})
        if isinstance(response, Exception):
            raise response
        return response

    return httpx.MockTransport(handler)


NEW_CONNECTION = [
    ("connection.connect_tcp.started", 0.0),
    ("connection.connect_tcp.complete", 0.05),
    ("connection.start_tls.started", 0.0),
    ("connection.start_tls.complete", 0.1),
    ("http11.send_request_headers.started", 0.0),
    ("http11.send_request_headers.complete", 0.0),
    ("http11.send_request_body.started", 0.0),
    ("http11.send_request_body.complete", 0.0),
    ("http11.receive_response_headers.started", 0.0),
    ("http11.receive_response_headers.complete", 0.6),
]


def wire_of(transport: FactsTransport) -> Wire:
    """One GET through `transport`, its body read to the end (or its failure), and its `Wire`."""
    request = httpx.Request("GET", STORE_URL + "/x")
    try:
        response = transport.handle_request(request)
        stream = response.stream
        assert isinstance(stream, httpx.SyncByteStream)
        for _ in stream:
            pass
        stream.close()
    except httpx.TransportError:
        pass
    wire = transport.take()
    assert wire is not None
    return wire


def test_a_new_connection_read_to_its_end_is_done_with_its_header_time() -> None:
    clock = Clock()
    events = [*NEW_CONNECTION, ("http11.receive_response_body.started", 0.0)]
    events += [("http11.receive_response_body.complete", 0.0), ("http11.response_closed.started", 0.0)]
    wire = wire_of(FactsTransport(traced(events, httpx.Response(200, content=b"[]"), clock), monotonic=clock.monotonic))
    assert (wire.stage, wire.new_connection, wire.headers_ms, wire.error) == ("done", True, 750, None)


def test_a_kept_alive_connection_is_not_new() -> None:
    clock = Clock()
    wire = wire_of(FactsTransport(traced(NEW_CONNECTION[4:], httpx.Response(200), clock), monotonic=clock.monotonic))
    assert (wire.stage, wire.new_connection, wire.headers_ms) == ("headers", False, 600)


def failing(steps: int, event: str, after: float) -> list[tuple[str, float]]:
    """The first `steps` events of a new connection, then `event` (a `.failed` one) after `after` seconds."""
    return [*NEW_CONNECTION[:steps], (event, after)]


@pytest.mark.parametrize(
    ("events", "error", "stage", "word"),
    [
        (failing(1, "connection.connect_tcp.failed", 10.0), httpx.ConnectTimeout("x"), "connect", "connect_timeout"),
        (failing(3, "connection.start_tls.failed", 0.1), httpx.ConnectError("x"), "tls", "connect_error"),
        (failing(5, "http11.send_request_headers.failed", 0.0), httpx.WriteTimeout("x"), "send", "write_timeout"),
        (failing(9, "http11.receive_response_headers.failed", 30.0), httpx.ReadTimeout("x"), "headers", "read_timeout"),
        (NEW_CONNECTION[4:9], httpx.RemoteProtocolError("x"), "headers", "protocol_error"),
        ([], httpx.PoolTimeout("x"), None, "pool_timeout"),
        ([], httpx.ReadError("x"), None, "read_error"),
        ([], httpx.UnsupportedProtocol("x"), None, "other"),
    ],
    ids=["connect", "tls", "send", "headers", "protocol", "pool", "read error", "other"],
)
def test_a_request_that_fails_names_its_stage_and_its_error_word(
    events: list[tuple[str, float]], error: Exception, stage: str | None, word: str
) -> None:
    clock = Clock()
    wire = wire_of(FactsTransport(traced(events, error, clock), monotonic=clock.monotonic))
    assert (wire.stage, wire.error, wire.facts, wire.headers_ms) == (stage, word, None, None)
    assert word in ERROR_WORDS and (stage is None or stage in STAGES)


def test_unknown_or_malformed_event_names_are_ignored() -> None:
    clock = Clock()
    events = [
        ("http11.response_closed.started", 0.0),
        ("connection.close.started", 0.0),
        ("connection.connect_tcp.retried", 0.0),
        ("connect_tcp.started", 0.0),
        ("nothing", 0.0),
        ("", 0.0),
    ]
    wire = wire_of(FactsTransport(traced(events, httpx.Response(200), clock), monotonic=clock.monotonic))
    assert (wire.stage, wire.new_connection) == (None, False)


def test_the_trace_callback_never_keeps_info() -> None:
    """The analyst's finding 1: `info` holds the request (its address and `Authorization`); nothing of it is kept."""
    clock = Clock()
    facts = FactsTransport(httpx.MockTransport(lambda request: httpx.Response(200)), monotonic=clock.monotonic)
    request = httpx.Request("GET", STORE_URL)
    facts.handle_request(request)
    callback = request.extensions["trace"]
    info = Secretive()
    alive = weakref.ref(info)
    for name, _ in NEW_CONNECTION:
        callback(name, {"request": info, "exception": RuntimeError(info.text), "return_value": info})
    del info
    gc.collect()
    assert alive() is None  # no reference to it is left anywhere
    recorder = callback.__self__
    wire = facts.take()
    for text in (repr(wire), repr(vars(facts)), repr(vars(recorder))):
        assert KEY not in text and SECRET not in text and "store-a" not in text and "consumer_key" not in text


@pytest.mark.parametrize(
    ("error", "word"),
    [
        (httpx.ConnectTimeout("x"), "connect_timeout"),
        (httpx.ReadTimeout("x"), "read_timeout"),
        (httpx.WriteTimeout("x"), "write_timeout"),
        (httpx.PoolTimeout("x"), "pool_timeout"),
        (httpx.ConnectError("x"), "connect_error"),
        (httpx.ReadError("x"), "read_error"),
        (httpx.RemoteProtocolError("x"), "protocol_error"),
        (httpx.LocalProtocolError("x"), "protocol_error"),
        (httpx.WriteError("x"), "other"),
        (ValueError(KEY), "other"),
    ],
)
def test_the_error_word_comes_from_the_class_only(error: Exception, word: str) -> None:
    assert error_word(error) == word


def test_the_facts_transport_refuses_a_request_that_is_not_a_get() -> None:
    called: list[httpx.Request] = []

    def answer(request: httpx.Request) -> httpx.Response:
        called.append(request)
        return httpx.Response(200)

    facts = FactsTransport(httpx.MockTransport(answer))
    for method in ("POST", "PUT", "DELETE", "HEAD"):
        with pytest.raises(NonGetRefused):
            facts.handle_request(httpx.Request(method, STORE_URL))
    assert called == [] and facts.take() is None


# ---- the shape of a trickle: the counting stream (findings 2 and 3) ------------------------------------------------


class TimedStream(httpx.SyncByteStream):
    """A body: each step moves the clock (a `Clock`, or a store's `FakeTime`), then sends its chunk, or raises its
    error."""

    def __init__(self, clock: Clock | FakeTime, steps: list[tuple[float, bytes | Exception]]) -> None:
        self.clock = clock
        self.steps = steps

    def __iter__(self) -> Iterator[bytes]:
        for after, step in self.steps:
            self.clock.now += after
            if isinstance(step, Exception):
                raise step
            yield step


@pytest.mark.parametrize(
    ("length", "declared"),
    [("5000", 5000), (None, None), ("abc", None), ("-1", None), (" 5", None), ("9" * 20, DECLARED_MAX)],
)
def test_the_body_is_counted_and_timed_as_it_comes(length: str | None, declared: int | None) -> None:
    clock = Clock()
    steps: list[tuple[float, bytes | Exception]] = [(0.2, b"a" * 100), (1.0, b"b" * 50), (3.0, b""), (0.5, b"c" * 10)]
    steps.append((30.0, httpx.ReadTimeout("stalled")))
    headers = {} if length is None else {"Content-Length": length}

    def answer(request: httpx.Request) -> httpx.Response:
        clock.now += 0.4
        return httpx.Response(200, headers=headers, stream=TimedStream(clock, steps))

    wire = wire_of(FactsTransport(httpx.MockTransport(answer), monotonic=clock.monotonic))
    # first byte at 0.6 s; the gaps: 1.0 s, then 3.5 s (an empty chunk isn't a byte), then the 30 s stall
    assert (wire.headers_ms, wire.first_byte_ms, wire.longest_gap_ms) == (400, 600, 30_000)
    assert (wire.received, wire.declared_bytes, wire.error, wire.stage) == (160, declared, "read_timeout", None)


def test_a_body_read_to_its_end_has_no_error_and_its_gaps_between_chunks() -> None:
    clock = Clock()
    steps: list[tuple[float, bytes | Exception]] = [(0.1, b"[" * 10), (2.5, b"]" * 10), (0.5, b"")]
    facts = FactsTransport(
        httpx.MockTransport(lambda request: httpx.Response(200, stream=TimedStream(clock, steps))),
        monotonic=clock.monotonic,
    )
    wire = wire_of(facts)
    assert (wire.first_byte_ms, wire.longest_gap_ms, wire.received, wire.error) == (100, 2500, 20, None)


def test_with_the_facts_transport_a_connection_dropped_mid_body_keeps_its_bytes() -> None:
    """The analyst's finding 3: an `unreachable` mid-body still reports the bytes that came, and that headers came."""
    clock = Clock()
    steps: list[tuple[float, bytes | Exception]] = [(0.1, b"[" * 700), (1.0, httpx.ReadError("connection reset"))]
    store = FakeCatalogStore(rows=rows(3), answers=[httpx.Response(200, stream=TimedStream(clock, steps))])
    facts = FactsTransport(store.transport, monotonic=clock.monotonic)
    result, seen = observed(store, transport=facts, facts=facts)
    assert result.ok
    first = seen[1]
    assert brief(first) == ("products", 1, 1, "unreachable", None, True)
    assert first.body_bytes == 700 and first.wire is not None and first.wire.error == "read_error"
    store = FakeCatalogStore(rows=rows(3), answers=[httpx.Response(200, stream=TimedStream(Clock(), steps))])
    _, seen = observed(store)
    assert (seen[1].body_bytes, seen[1].headers, seen[1].wire) == (None, None, None)  # not known without it


def test_the_answer_passes_through_the_counting_stream_unchanged() -> None:
    """Replacing `response.stream` works in httpx 0.28.1: the client wraps it once more (`BoundSyncStream`) and reads
    it whole; the reader gets the same products, and the bytes counted are the bytes read."""
    plain = read(FakeCatalogStore(rows=rows(150)))
    store = FakeCatalogStore(rows=rows(150))
    facts = FactsTransport(store.transport)
    result, seen = observed(store, transport=facts, facts=facts)
    assert result == plain
    assert all(a.wire is not None and a.body_bytes == a.wire.received > 0 for a in seen)
    assert max(a.body_bytes or 0 for a in seen[1:]) == result.largest_page_bytes


# ---- the attempt bound and which limit ended a timeout (finding 4) -------------------------------------------------


def _trickle(store: FakeCatalogStore, seconds: float) -> None:
    store.answers = [
        lambda request: httpx.Response(
            200,
            stream=StallingStream(
                [b"[" * 10], before_chunk=lambda: setattr(store.time, "now", store.time.now + seconds)
            ),
        )
    ]


def with_facts(
    store: FakeCatalogStore, read_seconds: float = 30.0, **options: Any
) -> tuple[CatalogRead, list[Attempt]]:
    """A read through a `FactsTransport`, as L1 makes it (the store's own clock), every attempt observed."""
    time = store.time
    facts = FactsTransport(store.transport, monotonic=time.monotonic)
    seen: list[Attempt] = []
    with WooClient(
        STORE_URL, KEY, SECRET, transport=facts, monotonic=time.monotonic, read_seconds=read_seconds
    ) as client:
        result = read_catalog(
            client,
            spacing_ms=1000,
            stop=time,
            failures=MemoryFailureCount(),
            monotonic=time.monotonic,
            now=time.wall,
            observe=seen.append,
            facts=facts,
            **options,
        )
    return result, seen


def _stalls_after(store: FakeCatalogStore, every: float, until: float, stall: float) -> None:
    """Page 1's first answer: a byte every `every` seconds up to `until`, then nothing for `stall` seconds, when httpx's
    read timeout (restarted at each socket read) fires: the reviewer's probes."""
    steps: list[tuple[float, bytes | Exception]] = [(every, b"[") for _ in range(round(until / every))]
    steps.append((stall, httpx.ReadTimeout("no byte within the read timeout")))
    store.answers = [lambda request: httpx.Response(200, stream=TimedStream(store.time, steps))]


def test_a_trickle_past_the_attempt_bound_caught_by_the_clients_own_check_is_attempt_bound() -> None:
    """WooClient's check between chunks fired (no exception behind the timeout): the attempt's bound ended it, and
    the retry reads on."""
    store = FakeCatalogStore(rows=rows(3))
    _trickle(store, 130.0)
    result, seen = with_facts(store, attempt_seconds=120.0)
    assert result.ok
    assert (seen[1].outcome, seen[1].ended, seen[1].body_bytes) == ("timeout", "attempt_bound", 10)
    assert seen[1].wire is not None and seen[1].wire.error is None
    assert all(a.ended is None for a in seen if a.outcome != "timeout")
    store = FakeCatalogStore(rows=rows(3))
    _trickle(store, 130.0)
    _, seen = observed(store, attempt_seconds=120.0)
    assert seen[1].ended == "read_timeout"  # without a facts transport only the slack can tell, and 10 s is past it


@pytest.mark.parametrize(
    ("read_seconds", "every", "until", "stall"),
    [(30.0, 10.0, 110.0, 30.0), (90.0, 10.0, 40.0, 90.0)],
    ids=["read 30 s, trickle to 110 s", "read 90 s, trickle to 40 s"],
)
def test_a_read_timeout_after_the_last_byte_past_the_attempt_bound_is_read_timeout(
    read_seconds: float, every: float, until: float, stall: float
) -> None:
    """Review 1, finding 1 (the reviewer's two probes): httpx's read timeout fired a whole read timeout after the
    last byte, past the attempt's deadline but not near it: httpx's own timeout, not the bound."""
    store = FakeCatalogStore(rows=rows(3))
    _stalls_after(store, every, until, stall)
    result, seen = with_facts(store, read_seconds=read_seconds, attempt_seconds=120.0)
    assert result.ok
    first = seen[1]
    assert first.wire is not None
    assert (first.outcome, first.ended, first.wire.error) == ("timeout", "read_timeout", "read_timeout")
    assert (first.wire.longest_gap_ms, first.elapsed_ms) == (round(stall * 1000), round((until + stall) * 1000))
    assert first.elapsed_ms > 120_000


def test_the_same_stall_past_the_store_bound_is_read_timeout_and_the_read_ends_between_requests() -> None:
    store = FakeCatalogStore(rows=rows(3))
    _stalls_after(store, 10.0, 90.0, 30.0)
    result, seen = with_facts(store, store_seconds=100.0)
    assert result.reason == "timeout"
    assert (seen[-1].outcome, seen[-1].ended, seen[-1].elapsed_ms) == ("timeout", "read_timeout", 120_000)
    assert len(seen) == 2  # the retry's wait would pass the bound: the read ended between requests


def test_a_trickle_past_the_store_bound_caught_by_the_clients_own_check_is_store_bound() -> None:
    store = FakeCatalogStore(rows=rows(3))
    _trickle(store, 700.0)
    result, seen = with_facts(store)  # no attempt bound: client.get has the store's deadline
    assert result.reason == "timeout" and seen[-1].ended == "store_bound"
    store = FakeCatalogStore(rows=rows(3))
    _trickle(store, 700.0)
    result, seen = with_facts(store, attempt_seconds=120.0)  # the attempt's deadline was the one client.get had
    assert result.reason == "timeout" and seen[-1].ended == "attempt_bound"


def test_the_attempt_bound_is_the_deadline_the_client_gets() -> None:
    store = FakeCatalogStore(rows=rows(3))
    read(store, attempt_seconds=20.0)
    assert {request.extensions["timeout"]["read"] for request in store.requests} == {20.0}
    plain = FakeCatalogStore(rows=rows(3))
    read(plain)
    assert {request.extensions["timeout"]["read"] for request in plain.requests} == {30.0}


def test_a_read_timeout_with_no_bound_near_is_read_timeout() -> None:
    def silent(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("no answer")

    store = FakeCatalogStore(rows=rows(3), answers=[silent])
    _, seen = with_facts(store, attempt_seconds=120.0)
    assert (seen[1].outcome, seen[1].ended) == ("timeout", "read_timeout")


@pytest.mark.parametrize(("early", "ended"), [(0.1, "attempt_bound"), (0.0, "attempt_bound"), (0.5, "read_timeout")])
@pytest.mark.parametrize("facts", [True, False], ids=["facts", "no facts"])
def test_a_timeout_within_the_slack_of_a_bound_is_labelled_by_the_bound(early: float, ended: str, facts: bool) -> None:
    """A timeout cut short by the deadline fires at it, give or take a timer that wakes early (`BOUND_SLACK_SECONDS`
    is 0.25 s); 0.5 s early is httpx's own."""

    def late(request: httpx.Request) -> httpx.Response:
        store.time.now += 120.0 - early
        raise httpx.ReadTimeout("x")

    store = FakeCatalogStore(rows=rows(3), answers=[late])
    _, seen = with_facts(store, attempt_seconds=120.0) if facts else observed(store, attempt_seconds=120.0)
    assert seen[1].ended == ended


@pytest.mark.parametrize("seconds", [0.0, -1.0])
def test_an_attempt_bound_that_is_not_above_zero_is_refused(seconds: float) -> None:
    store = FakeCatalogStore(rows=rows(3))
    with pytest.raises(ValueError):
        read(store, attempt_seconds=seconds)
    assert store.requests == []


# ---- the wait before each attempt (finding 6) -----------------------------------------------------------------------


def test_each_attempt_says_how_long_was_waited_before_it() -> None:
    store = FakeCatalogStore(rows=rows(150), answers=[httpx.Response(429, headers={"Retry-After": "7"})])
    _, seen = observed(store)
    assert [a.waited_ms for a in seen] == [0, 150, 7000, 150]


# ---- the other fixed-word facts (finding 6) -------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("value", "word"),
    [
        ("application/json; charset=UTF-8", "json"),
        ("Application/JSON", "json"),
        ("application/problem+json", "json"),
        ("text/html; charset=utf-8", "html"),
        ("text/plain", "other"),
        ("text/json", "other"),
        ("", "other"),
        (None, "none"),
    ],
)
def test_the_content_type_becomes_one_fixed_word(value: str | None, word: str) -> None:
    headers = httpx.Headers({} if value is None else {"Content-Type": value})
    assert response_facts(headers).content == word


def test_cf_mitigated_retry_after_and_the_origin_hints_are_names_present_only() -> None:
    headers = httpx.Headers(
        [
            ("Retry-After", "120"),
            ("cf-mitigated", "challenge"),
            ("X-Cache", "HIT from secret-host.example"),
            ("X-Sucuri-ID", "18018"),
            ("X-Turbo-Charged-By", "LiteSpeed"),
            ("X-Ratelimit-Limit", "100"),
            ("X-Unknown-Hint", "1"),
        ]
    )
    facts = response_facts(headers)
    assert (facts.cf_mitigated, facts.retry_after) == (True, True)
    assert facts.hints == ("x-turbo-charged-by", "x-sucuri-id", "x-cache", "x-ratelimit-limit")
    assert set(facts.hints) <= set(HINT_HEADERS) and "secret-host" not in repr(facts)
    assert (response_facts(httpx.Headers()).hints, response_facts(httpx.Headers()).retry_after) == ((), False)


# ---- the read timeout (finding 5) -----------------------------------------------------------------------------------


@pytest.mark.parametrize(("seconds", "allowed"), [(30, True), (90, True), (120, True), (29.9, False), (121, False)])
def test_the_read_timeout_is_accepted_only_from_30_to_120_seconds(seconds: float, allowed: bool) -> None:
    store = FakeCatalogStore(rows=rows(1))
    if not allowed:
        with pytest.raises(ValueError):
            WooClient(STORE_URL, KEY, SECRET, transport=store.transport, read_seconds=seconds)
        return
    with WooClient(STORE_URL, KEY, SECRET, transport=store.transport, read_seconds=seconds) as client:
        client.get(PRODUCTS, {}, deadline=10_000_000.0)
    timeout = store.requests[0].extensions["timeout"]
    assert (timeout["connect"], timeout["read"]) == (10.0, float(seconds))

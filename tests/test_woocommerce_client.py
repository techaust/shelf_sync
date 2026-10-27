"""SET-01, ERR-01: the WooCommerce read client and the read test, against fakes built from the WooCommerce REST docs
(httpx.MockTransport, RFC 2606 hosts only). Every reason, the two GETs and their spacing, Basic auth in the header and
never in a URL, no redirect followed, the 1 MiB cap, and GET only."""

import base64
import logging
import ssl
from collections.abc import Callable

import httpx
import pytest

from shelfsync import __version__
from shelfsync.apply.woocommerce import (
    MAX_BODY_BYTES,
    GetOnlyTransport,
    NonGetRefused,
    ReadOutcome,
    WooClient,
    health_for,
    run_read_test,
)
from tests.store_support import (
    KEY,
    PRODUCTS,
    SECRET,
    STORE_URL,
    SYSTEM_STATUS,
    FakeWoo,
    html,
    products,
    system_status,
    wp_error,
)


def run(woo: FakeWoo, spacing_ms: int = 150, url: str = STORE_URL) -> ReadOutcome:
    with WooClient(url, KEY, SECRET, transport=woo.transport, monotonic=woo.time.monotonic) as client:
        return run_read_test(client, spacing_ms, "SA", sleep=woo.time.sleep, monotonic=woo.time.monotonic)


# ---- the success path -----------------------------------------------------------------------------------------------


def test_a_good_store_makes_exactly_two_gets_spaced_apart_with_basic_auth_in_the_header() -> None:
    woo = FakeWoo(latency=0.25)
    outcome = run(woo, spacing_ms=300)
    assert outcome == ReadOutcome(None, 200, 250, "9.4.1", "6.7.1", 42)
    assert outcome.ok and outcome.health == "connected"
    assert [r.method for r in woo.requests] == ["GET", "GET"]
    assert [r.url.path for r in woo.requests] == [SYSTEM_STATUS, PRODUCTS]
    assert woo.time.slept == [0.3]  # the spacing sits between the two
    expected = "Basic " + base64.b64encode(f"{KEY}:{SECRET}".encode()).decode()
    for request in woo.requests:
        assert request.headers["Authorization"] == expected
        assert request.headers["User-Agent"] == f"ShelfSync/{__version__}"
        assert KEY not in str(request.url) and SECRET not in str(request.url)
        assert "consumer_" not in str(request.url) and request.url.scheme == "https"
        assert request.url.host == "store-a.example"
    assert dict(woo.requests[0].url.params) == {"_fields": "environment"}
    assert dict(woo.requests[1].url.params) == {
        "downloadable": "true",
        "status": "any",
        "per_page": "1",
        "_fields": "id",
    }


def test_a_store_in_a_sub_folder_is_asked_under_its_path() -> None:
    woo = FakeWoo()
    run(woo, url="https://store-a.example/shop")
    assert [r.url.path for r in woo.requests] == ["/shop" + SYSTEM_STATUS, "/shop" + PRODUCTS]


def test_the_timeouts_are_ten_to_connect_and_thirty_to_read() -> None:
    woo = FakeWoo()
    run(woo)
    assert woo.requests[0].extensions["timeout"] == {"connect": 10.0, "read": 30.0, "write": 30.0, "pool": 30.0}


def test_zero_downloadable_products_is_ok_with_a_warning() -> None:
    outcome = run(FakeWoo(products_answer=products(total=0, body=[])))
    assert outcome.ok and outcome.downloadable_count == 0 and outcome.warning == "no_downloadable_products"


def test_a_newer_major_version_is_compared_by_number_not_text() -> None:
    assert run(FakeWoo(status=system_status("10.0.0"))).ok  # "10.0" < "5.8" as text, but not as numbers
    assert run(FakeWoo(status=system_status("5.8.0"))).ok
    assert run(FakeWoo(status=system_status("9.4.0-rc.1"))).ok


# ---- every reason ---------------------------------------------------------------------------------------------------


def _raise(error: Exception) -> Callable[[httpx.Request], httpx.Response]:
    def handler(request: httpx.Request) -> httpx.Response:
        raise error

    return handler


def _tls_failure(request: httpx.Request) -> httpx.Response:
    error = httpx.ConnectError("[SSL: CERTIFICATE_VERIFY_FAILED]")
    error.__cause__ = ssl.SSLCertVerificationError("certificate verify failed")
    raise error


REASONS: list[tuple[str, dict[str, object], str, str, int | None]] = [
    # (id, FakeWoo arguments, reason, health, http_status)
    ("dns", {"status": _raise(httpx.ConnectError("name resolution failed"))}, "unreachable", "unreachable", None),
    ("reset", {"status": _raise(httpx.ReadError("reset"))}, "unreachable", "unreachable", None),
    ("connect timeout", {"status": _raise(httpx.ConnectTimeout("slow"))}, "timeout", "unreachable", None),
    ("read timeout", {"status": _raise(httpx.ReadTimeout("slow"))}, "timeout", "unreachable", None),
    ("tls", {"status": _tls_failure}, "tls_error", "unreachable", None),
    ("firewall 403", {"status": html(403)}, "blocked", "unreachable", 403),
    ("challenge 503", {"status": html(503)}, "blocked", "unreachable", 503),
    ("404", {"status": html(404)}, "not_woocommerce", "unreachable", 404),
    ("no route", {"status": wp_error(404, "rest_no_route")}, "not_woocommerce", "unreachable", 404),
    ("not json", {"status": httpx.Response(200, content=b"<html>hello</html>")}, "not_woocommerce", "unreachable", 200),
    ("429", {"status": httpx.Response(429)}, "rate_limited", "unreachable", 429),
    ("cloudflare 520", {"status": httpx.Response(520)}, "cloudflare_52x", "unreachable", 520),
    ("cloudflare 527", {"status": httpx.Response(527)}, "cloudflare_52x", "unreachable", 527),
    ("500", {"status": httpx.Response(500)}, "server_error", "unreachable", 500),
    ("503 json", {"status": wp_error(503, "service_unavailable")}, "server_error", "unreachable", 503),
    ("418", {"status": httpx.Response(418)}, "bad_response", "unreachable", 418),
    ("no environment", {"status": httpx.Response(200, json={"theme": {}})}, "bad_response", "unreachable", 200),
    ("a list", {"status": httpx.Response(200, json=[1])}, "bad_response", "unreachable", 200),
    ("no version", {"status": httpx.Response(200, json={"environment": {"wp_version": "6.7"}})}, "bad_response", "unreachable", 200),
    ("odd version", {"status": system_status("<b>9</b>")}, "bad_response", "unreachable", 200),
    ("401", {"status": wp_error(401, "woocommerce_rest_cannot_view")}, "keys_refused", "refused", 401),
    ("forbidden", {"status": wp_error(403, "woocommerce_rest_cannot_view")}, "forbidden", "refused", 403),
    ("too old", {"status": system_status("5.7.9")}, "wc_too_old", "refused", 200),
]  # fmt: skip


@pytest.mark.parametrize(
    ("arguments", "reason", "health", "status"), [r[1:] for r in REASONS], ids=[r[0] for r in REASONS]
)
def test_every_reason_in_the_first_get(
    arguments: dict[str, object], reason: str, health: str, status: int | None
) -> None:
    woo = FakeWoo(**arguments)  # type: ignore[arg-type]
    outcome = run(woo)
    assert (outcome.reason, outcome.health, outcome.http_status) == (reason, health, status)
    assert not outcome.ok
    assert len(woo.requests) <= 1  # a failure stops the test: no second GET, no retry
    assert woo.time.slept == []


SECOND_GET_REASONS: list[tuple[str, FakeWoo, str, str]] = [
    ("401", FakeWoo(products_answer=wp_error(401, "woocommerce_rest_cannot_view")), "keys_refused", "refused"),
    ("forbidden", FakeWoo(products_answer=wp_error(403, "woocommerce_rest_cannot_view")), "forbidden", "refused"),
    ("blocked", FakeWoo(products_answer=html(403)), "blocked", "unreachable"),
    ("500", FakeWoo(products_answer=httpx.Response(502)), "server_error", "unreachable"),
    ("no total", FakeWoo(products_answer=products(total=None)), "bad_response", "unreachable"),
    ("odd total", FakeWoo(products_answer=products(total="many")), "bad_response", "unreachable"),
    ("negative total", FakeWoo(products_answer=products(total="-1")), "bad_response", "unreachable"),
    ("huge total", FakeWoo(products_answer=products(total="9" * 20)), "bad_response", "unreachable"),
    ("not a list", FakeWoo(products_answer=products(body={"id": 1})), "bad_response", "unreachable"),
    ("timeout", FakeWoo(products_answer=_raise(httpx.ReadTimeout("slow"))), "timeout", "unreachable"),
]


@pytest.mark.parametrize(
    ("woo", "reason", "health"), [r[1:] for r in SECOND_GET_REASONS], ids=[r[0] for r in SECOND_GET_REASONS]
)
def test_every_reason_in_the_second_get(woo: FakeWoo, reason: str, health: str) -> None:
    outcome = run(woo)
    assert (outcome.reason, outcome.health) == (reason, health)
    assert len(woo.requests) == 2 and woo.time.slept == [0.15]
    assert outcome.wc_version == "9.4.1"  # what the first GET found is kept
    assert outcome.latency_ms is None and outcome.downloadable_count is None


def test_health_for_maps_every_reason_to_the_chip_state() -> None:
    assert health_for(None) == "connected"
    for reason in ("keys_refused", "forbidden", "wc_too_old"):
        assert health_for(reason) == "refused"
    for reason in ("unreachable", "timeout", "tls_error", "redirected", "blocked", "not_woocommerce"):
        assert health_for(reason) == "unreachable"


# ---- redirects, size, time ------------------------------------------------------------------------------------------


def test_a_redirect_is_not_followed_and_names_the_target_host_and_the_keys_never_go_there() -> None:
    def moved(request: httpx.Request) -> httpx.Response:
        return httpx.Response(301, headers={"Location": "https://Other-Shop.example/wp-json/wc/v3/system_status"})

    woo = FakeWoo(status=moved)
    outcome = run(woo)
    assert (outcome.reason, outcome.health, outcome.detail, outcome.http_status) == (
        "redirected",
        "unreachable",
        "other-shop.example",
        301,
    )
    assert len(woo.requests) == 1  # the target was never asked
    assert {request.url.host for request in woo.requests} == {"store-a.example"}


@pytest.mark.parametrize("status", [301, 302, 303, 307, 308])
def test_every_redirect_status_is_a_result(status: int) -> None:
    woo = FakeWoo(status=httpx.Response(status, headers={"Location": "https://elsewhere.example/"}))
    assert run(woo).reason == "redirected"


def test_a_redirect_without_a_usable_target_still_reports_redirected_with_no_host() -> None:
    assert run(FakeWoo(status=httpx.Response(302))).detail is None
    assert run(FakeWoo(status=httpx.Response(302, headers={"Location": "/login"}))).detail is None
    assert run(FakeWoo(status=httpx.Response(302, headers={"Location": "https://bad host/"}))).detail is None


def test_a_body_over_one_mebibyte_is_refused() -> None:
    big = httpx.Response(200, content=b"x" * (MAX_BODY_BYTES + 1))
    outcome = run(FakeWoo(status=big))
    assert outcome.reason == "bad_response"


def test_a_body_of_exactly_one_mebibyte_is_read() -> None:
    padding = " " * (MAX_BODY_BYTES - 80)
    status = httpx.Response(
        200, content=('{"environment":{"version":"9.4.1","wp_version":"6.7"}' + padding + "}").encode()
    )
    assert len(status.content) <= MAX_BODY_BYTES
    assert run(FakeWoo(status=status)).ok


def test_the_whole_test_gives_up_after_sixty_seconds() -> None:
    woo = FakeWoo()
    woo.status = lambda request: (setattr(woo.time, "now", woo.time.now + 61.0), system_status())[1]  # type: ignore[assignment]
    outcome = run(woo)
    assert outcome.reason == "timeout"
    assert [r.url.path for r in woo.requests] == [SYSTEM_STATUS]  # the second GET never started


def test_a_slow_body_stops_at_the_deadline() -> None:
    woo = FakeWoo()

    def slow(request: httpx.Request) -> httpx.Response:
        woo.time.now += 61.0
        return system_status()

    woo.status = slow
    with WooClient(STORE_URL, KEY, SECRET, transport=woo.transport, monotonic=woo.time.monotonic) as client:
        # the response arrives after the deadline, before its body is read
        with pytest.raises(Exception, match="timeout"):
            client.get(SYSTEM_STATUS, {}, deadline=woo.time.now + 60.0)


# ---- GET only and HTTPS only ----------------------------------------------------------------------------------------


@pytest.mark.parametrize("method", ["POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"])
def test_the_transport_refuses_any_method_but_get(method: str) -> None:
    seen: list[str] = []

    def inner(request: httpx.Request) -> httpx.Response:
        seen.append(request.method)
        return httpx.Response(200)

    transport = GetOnlyTransport(httpx.MockTransport(inner))
    with pytest.raises(NonGetRefused):
        transport.handle_request(httpx.Request(method, "https://store-a.example/x"))
    assert seen == []
    assert transport.handle_request(httpx.Request("GET", "https://store-a.example/x")).status_code == 200
    transport.close()


@pytest.mark.parametrize("method", ["POST", "PUT", "PATCH", "DELETE"])
def test_a_client_that_is_asked_to_write_cannot(method: str) -> None:
    """Contract: the client's own httpx client, whatever calls it, cannot send a write; and the class offers no write."""
    woo = FakeWoo()
    client = WooClient(STORE_URL, KEY, SECRET, transport=woo.transport)
    with pytest.raises(NonGetRefused):
        client._client.request(method, STORE_URL + PRODUCTS, json={"name": "x"})
    assert woo.requests == []
    public = {name for name in dir(client) if not name.startswith("_")}
    assert public == {"get", "close"}  # nothing else until M5
    client.close()


def test_the_client_is_built_with_no_redirects_and_no_environment() -> None:
    client = WooClient(STORE_URL, KEY, SECRET, transport=FakeWoo().transport)
    assert client._client.follow_redirects is False
    assert client._client.trust_env is False
    client.close()


@pytest.mark.parametrize("url", ["http://store-a.example", "ftp://store-a.example", "store-a.example", "https://"])
def test_a_store_that_is_not_https_is_refused_before_anything_is_sent(url: str) -> None:
    with pytest.raises(ValueError, match="https"):
        WooClient(url, KEY, SECRET, transport=FakeWoo().transport)


@pytest.mark.parametrize("name", ["consumer_key", "consumer_secret", "api_key", "Consumer_Key"])
def test_credentials_never_go_in_a_query_string(name: str) -> None:
    woo = FakeWoo()
    with WooClient(STORE_URL, KEY, SECRET, transport=woo.transport) as client, pytest.raises(ValueError, match="query"):
        client.get(SYSTEM_STATUS, {name: KEY}, deadline=2000.0)
    assert woo.requests == []


# ---- the log --------------------------------------------------------------------------------------------------------


def test_the_log_names_the_store_by_its_code_and_holds_no_address_key_or_body(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.DEBUG)
    run(FakeWoo(status=wp_error(401, "woocommerce_rest_cannot_view")))
    run(FakeWoo())
    text = "\n".join(record.getMessage() for record in caplog.records)
    assert "Store SA read test: keys_refused (HTTP 401)" in text
    assert "Store SA read test: ok (HTTP 200)" in text
    for forbidden in ("store-a.example", KEY, SECRET, "woocommerce_rest_cannot_view", "Authorization", "Basic"):
        assert forbidden not in text

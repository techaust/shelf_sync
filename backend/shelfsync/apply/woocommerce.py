"""The WooCommerce REST client, read side only (SET-01, ERR-01; 04 section 7, 06 section 3).

Rules this module keeps:
- HTTP Basic over HTTPS, nothing else: the consumer key and secret are in the `Authorization` header and **never** in a
  URL or a query string. A request to a non-HTTPS address is refused before it is built.
- one client with `trust_env=False` (no proxy variable or `.netrc` file ever sees the keys), explicit timeouts and
  **no redirects**: a 3xx is a result (`redirected`, naming the target host), and the keys never go there.
- the answer is streamed and read at most `MAX_BODY_BYTES` (1 MiB); more is a `bad_response`.
- **GET only.** `WooClient` has no method for any other verb until M5, and `GetOnlyTransport` refuses one even if a
  later change reaches for it: the contract test builds a client and tries.
- logs name a store by its code, never its address, and hold the reason and the status, never a body or a header.

`run_read_test` is the Test connection of Settings (two GETs, `spacing_ms` apart). Every outcome is one of the fixed
`Reason` values; nothing from a response is passed on as text except a version number that matched a strict pattern
and the host name a redirect pointed at.
"""

import json
import logging
import re
import ssl
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

import httpx

from shelfsync import __version__

_log = logging.getLogger("shelfsync.stores")

MAX_BODY_BYTES = 1024 * 1024
TOTAL_SECONDS = 60.0
CONNECT_SECONDS = 10.0
READ_SECONDS = 30.0
MIN_WC_VERSION = (5, 8)
SYSTEM_STATUS_PATH = "/wp-json/wc/v3/system_status"
PRODUCTS_PATH = "/wp-json/wc/v3/products"
_REDIRECTS = frozenset({301, 302, 303, 307, 308})
_VERSION = re.compile(r"[0-9A-Za-z.+_-]{1,32}")
_HOST = re.compile(r"[a-z0-9.-]{1,253}")
_WC_MAJOR_MINOR = re.compile(r"(\d+)\.(\d+)")

# The reasons (the screen words are in docs/13), and the health each shows on the chip.
UNREACHABLE_REASONS = frozenset(
    {
        "unreachable",
        "timeout",
        "tls_error",
        "redirected",
        "blocked",
        "not_woocommerce",
        "rate_limited",
        "cloudflare_52x",
        "server_error",
        "bad_response",
    }
)
REFUSED_REASONS = frozenset({"keys_refused", "forbidden", "wc_too_old"})


def health_for(reason: str | None) -> str:
    if reason is None:
        return "connected"
    return "refused" if reason in REFUSED_REASONS else "unreachable"


class ReadRefused(Exception):
    """A request stopped before there was a usable answer. `reason` is one of the fixed reasons, `detail` the host
    a redirect named (a host name only). The message never holds a URL, key or body."""

    def __init__(self, reason: str, detail: str | None = None, status: int | None = None) -> None:
        super().__init__(reason)
        self.reason = reason
        self.detail = detail
        self.status = status  # the HTTP status, when an answer arrived (a redirect)


class NonGetRefused(Exception):
    """Something tried to send a request that isn't a GET. Until M5 the client reads and never writes."""


class GetOnlyTransport(httpx.BaseTransport):
    """Wraps the real transport and refuses any request whose method isn't GET, whatever code built it."""

    def __init__(self, inner: httpx.BaseTransport) -> None:
        self._inner = inner

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        if request.method != "GET":
            raise NonGetRefused("only GET requests are sent to a store")
        return self._inner.handle_request(request)

    def close(self) -> None:
        self._inner.close()


@dataclass(frozen=True)
class WooResponse:
    status: int
    headers: httpx.Headers
    body: bytes


def _is_tls_error(error: BaseException) -> bool:
    seen: set[int] = set()
    current: BaseException | None = error
    while current is not None and id(current) not in seen:
        if isinstance(current, ssl.SSLError):
            return True
        seen.add(id(current))
        current = current.__cause__ or current.__context__
    return False


def _redirect_host(location: str | None) -> str | None:
    """The host a redirect points at, lowercased, or None. A relative target stays on the store's own host."""
    if not location:
        return None
    try:
        host = httpx.URL(location).host.lower()
    except httpx.InvalidURL:
        return None
    return host if _HOST.fullmatch(host) else None


class WooClient:
    """GET requests to one store. `transport` is for tests (httpx.MockTransport)."""

    def __init__(
        self,
        base_url: str,
        consumer_key: str,
        consumer_secret: str,
        *,
        transport: httpx.BaseTransport | None = None,
        monotonic: Callable[[], float] = time.monotonic,
    ) -> None:
        url = httpx.URL(base_url)
        if url.scheme != "https" or not url.host:
            raise ValueError("a store address must be https")
        self._base = base_url.rstrip("/")
        self._monotonic = monotonic
        self._client = httpx.Client(
            transport=GetOnlyTransport(transport if transport is not None else httpx.HTTPTransport()),
            auth=httpx.BasicAuth(consumer_key, consumer_secret),
            headers={"User-Agent": f"ShelfSync/{__version__}", "Accept": "application/json"},
            follow_redirects=False,
            trust_env=False,
        )

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> WooClient:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def get(self, path: str, params: dict[str, str], deadline: float) -> WooResponse:
        """One GET. `deadline` is a time on this client's monotonic clock after which the whole test has run out.
        Raises `ReadRefused` for a transport failure, a timeout, a redirect and an over-long body."""
        if any(name.lower().startswith("consumer_") or "key" in name.lower() for name in params):
            raise ValueError("credentials never go in a query string")
        remaining = deadline - self._monotonic()
        if remaining <= 0:
            raise ReadRefused("timeout")
        timeout = httpx.Timeout(min(READ_SECONDS, remaining), connect=min(CONNECT_SECONDS, remaining))
        try:
            with self._client.stream("GET", self._base + path, params=params, timeout=timeout) as response:
                if response.status_code in _REDIRECTS:
                    raise ReadRefused(
                        "redirected", _redirect_host(response.headers.get("location")), response.status_code
                    )
                body = b""
                for chunk in response.iter_bytes():
                    body += chunk
                    if len(body) > MAX_BODY_BYTES:
                        raise ReadRefused("bad_response")
                    if self._monotonic() > deadline:
                        raise ReadRefused("timeout")
                return WooResponse(response.status_code, response.headers, body)
        except httpx.TimeoutException:
            raise ReadRefused("timeout") from None
        except httpx.TransportError as error:
            raise ReadRefused("tls_error" if _is_tls_error(error) else "unreachable") from None


@dataclass(frozen=True)
class ReadOutcome:
    """The result of one read test. `reason` is None when it worked."""

    reason: str | None
    http_status: int | None = None
    latency_ms: int | None = None
    wc_version: str | None = None
    wp_version: str | None = None
    downloadable_count: int | None = None
    detail: str | None = None  # the host a redirect named
    warning: str | None = None  # `no_downloadable_products`

    @property
    def ok(self) -> bool:
        return self.reason is None

    @property
    def health(self) -> str:
        return health_for(self.reason)


def _json(body: bytes) -> Any:
    """The parsed body, or the `_NOT_JSON` marker."""
    try:
        return json.loads(body.decode("utf-8"))
    except ValueError:  # includes UnicodeDecodeError and JSONDecodeError
        return _NOT_JSON


_NOT_JSON = object()


def classify(response: WooResponse) -> str | None:
    """The reason a non-success answer stands for, or None for a 200. The body is only looked at to tell WooCommerce's
    own JSON error from a firewall's page."""
    status = response.status
    if status == 429:
        return "rate_limited"
    if 520 <= status <= 527:
        return "cloudflare_52x"
    if status == 401:
        return "keys_refused"
    data = _json(response.body)
    is_wp_error = isinstance(data, dict) and isinstance(data.get("code"), str)
    if is_wp_error and data["code"] == "rest_no_route":
        return "not_woocommerce"
    if status == 403:
        return "forbidden" if is_wp_error else "blocked"
    if status == 404:
        return "not_woocommerce"
    if status == 503 and not is_wp_error:
        return "blocked"
    if status >= 500:
        return "server_error"
    if status != 200:
        return "bad_response"
    if data is _NOT_JSON:
        return "not_woocommerce"
    return None


def _version_tuple(version: str) -> tuple[int, int] | None:
    match = _WC_MAJOR_MINOR.match(version)
    return (int(match.group(1)), int(match.group(2))) if match else None


def _clean_version(value: Any) -> str | None:
    return value if isinstance(value, str) and _VERSION.fullmatch(value) else None


def run_read_test(
    client: WooClient,
    spacing_ms: int,
    code: str,
    *,
    sleep: Callable[[float], None] = time.sleep,
    monotonic: Callable[[], float] = time.monotonic,
) -> ReadOutcome:
    """The two GETs of Test connection, `spacing_ms` apart, within 60 seconds in all. No retries. `code` is the store's
    two-letter code, the only name the log line carries."""
    outcome = _read_test(client, spacing_ms, sleep, monotonic)
    _log.info("Store %s read test: %s (HTTP %s)", code, outcome.reason or "ok", outcome.http_status)
    return outcome


def _read_test(
    client: WooClient, spacing_ms: int, sleep: Callable[[float], None], monotonic: Callable[[], float]
) -> ReadOutcome:
    deadline = monotonic() + TOTAL_SECONDS
    status: int | None = None
    wc_version: str | None = None
    wp_version: str | None = None
    try:
        first = client.get(SYSTEM_STATUS_PATH, {"_fields": "environment"}, deadline)
        status = first.status
        reason = classify(first)
        if reason is not None:
            return ReadOutcome(reason, status)
        data = _json(first.body)
        environment = data.get("environment") if isinstance(data, dict) else None
        if not isinstance(environment, dict):
            return ReadOutcome("bad_response", status)
        wc_version = _clean_version(environment.get("version"))
        wp_version = _clean_version(environment.get("wp_version"))
        parsed = _version_tuple(wc_version) if wc_version else None
        if parsed is None or wp_version is None:
            return ReadOutcome("bad_response", status)
        if parsed < MIN_WC_VERSION:
            return ReadOutcome("wc_too_old", status, None, wc_version, wp_version)

        sleep(spacing_ms / 1000)
        started = monotonic()
        second = client.get(
            PRODUCTS_PATH, {"downloadable": "true", "status": "any", "per_page": "1", "_fields": "id"}, deadline
        )
        latency_ms = max(0, round((monotonic() - started) * 1000))
        status = second.status
        reason = classify(second)
        if reason is not None:
            return ReadOutcome(reason, status, None, wc_version, wp_version)
        total = second.headers.get("x-wp-total")
        if (
            total is None
            or not total.isascii()
            or not total.isdigit()
            or len(total) > 9
            or not isinstance(_json(second.body), list)
        ):
            return ReadOutcome("bad_response", status, None, wc_version, wp_version)
        count = int(total)
        return ReadOutcome(
            None,
            status,
            latency_ms,
            wc_version,
            wp_version,
            count,
            warning="no_downloadable_products" if count == 0 else None,
        )
    except ReadRefused as refused:
        return ReadOutcome(
            refused.reason, refused.status or status, None, wc_version, wp_version, detail=refused.detail
        )

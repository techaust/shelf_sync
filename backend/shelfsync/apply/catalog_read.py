"""The catalog reader (CAT-01, APL-12 for GETs, ERR-02): every downloadable product of one store, read-only, page by
page, through `WooClient` (GET only, no redirects, no cookies, `trust_env` off; `apply/woocommerce.py`).

The requests, in order (and nothing else):
1. `GET /wp-json/wc/v3/system_status?_fields=environment`: below WooCommerce 5.8 the store is refused (`wc_too_old`).
2. `GET /wp-json/wc/v3/products?downloadable=true&status=any&orderby=id&order=asc&per_page=100&page=<n>&_fields=…` for
   n = 1 … N, where N is page 1's `X-WP-TotalPages`; more than 40 pages is refused (`too_many_pages`) before page 2.

Rules this module keeps:
- **Spacing (APL-12):** at least the store's `spacing_ms` between any two requests to it (a caller may ask for more).
- **Retries (APL-12), GETs only:** 429, 5xx and 520 to 527 (`rate_limited`, `cloudflare_52x`, `server_error`, and
  `blocked` when it came as a 503), and `timeout` and `unreachable` (Lead (proposed): a GET changes nothing), are
  retried up to 3 times, waiting 2, 4 and 8 s, or the `Retry-After` (seconds or an HTTP date) when given, never more
  than 60 s. Nothing else is retried. `_Session.request` refuses any method but GET before it sends or retries anything.
- **Failures in a row:** every failed attempt is counted, and so is a 200 the reader can't use; a **usable products
  page** resets the count (`FailureCount`, which the runner keeps in `sync_state` across runs). `system_status`
  answering doesn't reset it, so a store that answers it but keeps sending a bad page still reaches 10 (m3.1
  review 2). At 10 the store is auto-paused and the read ends.
- **The count check:** the rows read must equal page 1's `X-WP-Total`, with no id seen twice and the ids ascending
  across the pages. If not, the whole listing is read once more; if it still doesn't match, `count_mismatch`.
- **Bounds:** 10 minutes for one store's whole read (`timeout`); 8 MiB per page (`PAGE_MAX_BYTES`) and 64 MiB per
  listing (`LISTING_MAX_BYTES`), both Lead (proposed); the field limits of `catalog/model.py`. A hostile answer ends
  the read with `bad_response`: a page that isn't a JSON list, more than 100 rows on a page, a row without an integer
  `id`, a wrong type, an over-long field, a text with a NUL or a lone surrogate, a download list whose stored JSON
  would pass its limit, or a bad `X-WP-Total` / `X-WP-TotalPages`. Such a 200 counts as a failed request for the
  failures in a row (`_Session.bad`). The result names the failing field (a fixed identifier from this code, never a
  value) and the page. A failed or stopped read returns no products: the caller saves nothing. A `latest_version*`
  meta entry that can't be kept is skipped and counted instead (`Product.meta_skipped`; Lead (proposed)).
- **Pages that run out:** a 400 on page 2 or later (WooCommerce's answer past the last page, not verified on a store)
  ends that listing early, so the count check reads it once more.
- **Stop:** the read stops between requests and during every wait when asked (`stopped`).
- **Logs:** one line per store per read: its code, the outcome, pages, rows, the HTTP status of the last failure, and
  for `bad_response` the field and page. Never an address, key, cookie, query string, header or body.

For the L1 dry read only (t9, to tell why a store stalls; the app's runner never sets any of these, and with their
defaults nothing changes: the same requests, the same results):
- **`observe`** is called once per attempt (the first try and each retry) with an `Attempt`: what was asked (and the
  page), the attempt number, the outcome (`ok`, `past_the_end` or the fixed reason), the HTTP status, the time it took
  and the wait before it, the body bytes, whether the answer's headers had arrived, for a timeout which limit ended
  it, and the `Wire` when `facts` is given.
- **`facts`**, a `FactsTransport`, is the transport the caller builds its `WooClient` on. `WooClient` wraps it in
  `GetOnlyTransport`, so it sees each answer's headers **before** `GetOnlyTransport` drops `Set-Cookie`: it keeps only
  fixed words from them (`response_facts`), never a value. It also times the request's stages through httpcore's
  `trace` extension (the event names only, never their `info`) and counts and times the body as it comes (`Wire`).
  The cookie drop stays as it is, so no cookie is kept, parsed or sent back.
- **`meta=False`** asks for the products without `meta_data` (no `latest_version` data, no error); **`per_page`**
  (25 to 100) and **`max_pages`** (at most 4,000 rows in all, as with 40 pages of 100) change the listing's pages.
- **`attempt_seconds`** bounds one attempt (the store's bound still holds): `client.get` gets the earlier of the two.
"""

import html
import json
import logging
import re
import time
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from itertools import pairwise
from typing import Any, NoReturn, Protocol

import httpx

from shelfsync.apply.woocommerce import (
    MIN_WC_VERSION,
    PRODUCTS_PATH,
    SYSTEM_STATUS_PATH,
    NonGetRefused,
    ReadRefused,
    WooClient,
    WooResponse,
    _clean_version,
    _json,
    _version_tuple,
    classify,
    declared_length,
)
from shelfsync.catalog.model import (
    DOWNLOAD_FILE_MAX,
    DOWNLOAD_ID_MAX,
    DOWNLOAD_NAME_MAX,
    DOWNLOADS_JSON_MAX,
    DOWNLOADS_MAX,
    META_JSON_MAX,
    META_KEPT_MAX,
    META_KEY_MAX,
    META_PREFIX,
    META_VALUE_MAX,
    SLUG_MAX,
    TITLE_MAX,
    Download,
    Product,
    downloads_json,
    meta_json,
)
from shelfsync.catalog.watermark import modified_after
from shelfsync.clock import utc_now

_log = logging.getLogger("shelfsync.catalog")

PAGE_MAX_BYTES = 8 * 1024 * 1024  # one products page (Lead (proposed); L1 measures the real size)
LISTING_MAX_BYTES = 64 * 1024 * 1024  # one whole listing, every page together (Lead (proposed))
PER_PAGE = 100
MAX_PAGES = 40
RETRIES = 3
BACKOFF_SECONDS = (2.0, 4.0, 8.0)
RETRY_AFTER_MAX_SECONDS = 60.0
STORE_SECONDS = 600.0  # one store's whole read
FAILURES_TO_PAUSE = 10
LISTING_FIELDS = "id,slug,name,type,status,date_modified_gmt,downloads,meta_data"
LISTING_FIELDS_NO_META = "id,slug,name,type,status,date_modified_gmt,downloads"  # L1's `meta=False` only
PER_PAGE_MIN = 25  # L1's smallest page (`per_page`)
MAX_ROWS = MAX_PAGES * PER_PAGE  # what `max_pages` times `per_page` may reach (L1 only; the app keeps 40 of 100)
SYSTEM_STATUS_PARAMS = {"_fields": "environment"}  # the first request's query (also what L1 shows)
WC_ID_MAX = 2**63 - 1

# Retried, whatever the status; `blocked` only when it came as a 503 (a 403 firewall page isn't retried).
RETRIED_REASONS = frozenset({"rate_limited", "cloudflare_52x", "server_error", "timeout", "unreachable"})

# The outcomes this module adds to woocommerce.py's reasons (fixed words; the screens' text is in docs/13).
READ_REASONS = frozenset({"too_many_pages", "count_mismatch", "no_products", "auto_paused", "stopped"})

_WORD = re.compile(r"[a-z0-9_-]{1,40}")
_GMT = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}")
_COUNT = re.compile(r"[0-9]{1,9}")


def listing_params(page: int, *, per_page: int = PER_PAGE, meta: bool = True) -> dict[str, str]:
    """The query of one products page (contract-tested). `per_page` and `meta` are L1's options; the app keeps the
    defaults."""
    return {
        "downloadable": "true",
        "status": "any",
        "orderby": "id",
        "order": "asc",
        "per_page": str(per_page),
        "page": str(page),
        "_fields": LISTING_FIELDS if meta else LISTING_FIELDS_NO_META,
    }


# ---- L1's diagnostics (t9): fixed words and numbers about each answer and each attempt, never a value --------------

SERVER_WORDS = ("cloudflare", "nginx", "apache", "litespeed", "openresty")  # else `other`, or `none` when absent
CACHE_WORDS = ("hit", "miss", "dynamic", "bypass", "expired")  # `cf-cache-status`; else `other`, or `none`
CONTENT_WORDS = ("json", "html")  # `content-type`; else `other`, or `none`
COOKIE_WORDS = (
    "__cf_bm",
    "cf_clearance",
    "_cfuvid",
    "PHPSESSID",
    "wordpress_logged_in",
    "wordpress_sec",
    "wp-settings",
)
# Origin hints: only whether each of these header names is there, never its value.
HINT_HEADERS = (
    "x-litespeed-cache",
    "x-turbo-charged-by",
    "x-sucuri-id",
    "x-sucuri-cache",
    "x-cache",
    "x-ratelimit-limit",
    "x-ratelimit-remaining",
)
# WordPress names these with a suffix (`wordpress_logged_in_<hash of the site address>`, `wp-settings-1`,
# `wp-settings-time-1`): the family's word is kept, never the suffix (it would identify the store).
_COOKIE_FAMILIES = (("wordpress_logged_in", "_"), ("wordpress_sec", "_"), ("wp-settings", "-"))
_COOKIE_EXACT = frozenset({"__cf_bm", "cf_clearance", "_cfuvid", "PHPSESSID"})
_SERVER_TOKEN = re.compile(r"[^/\s(,;]*")

STAGES = ("connect", "tls", "send", "headers", "body", "done")
# httpcore's trace events (`<prefix>.<name>.started|complete|failed`; httpcore 1.0.9 `_trace.py`,
# `_sync/connection.py`, `_sync/http11.py`): the name decides the stage, and nothing else of the event is kept.
_TRACE_STAGES = {
    "connection.connect_tcp": "connect",
    "connection.start_tls": "tls",
    "http11.send_request_headers": "send",
    "http11.send_request_body": "send",
    "http11.receive_response_headers": "headers",
    "http11.receive_response_body": "body",
}
_TRACE_PHASES = frozenset({"started", "complete", "failed"})
_ERROR_CLASSES: tuple[tuple[type[Exception], str], ...] = (
    (httpx.ConnectTimeout, "connect_timeout"),
    (httpx.ReadTimeout, "read_timeout"),
    (httpx.WriteTimeout, "write_timeout"),
    (httpx.PoolTimeout, "pool_timeout"),
    (httpx.ConnectError, "connect_error"),
    (httpx.ReadError, "read_error"),
    (httpx.ProtocolError, "protocol_error"),
)
ERROR_WORDS = (*(word for _, word in _ERROR_CLASSES), "other")
TIMEOUT_WORDS = ("connect_timeout", "read_timeout", "write_timeout", "pool_timeout")  # httpx's own timeouts
# What ended a timed-out attempt (`_Session._ended`): httpx's own timeout, by its word, or a bound.
ENDED_WORDS = (*TIMEOUT_WORDS, "attempt_bound", "store_bound")


def ms_between(later: float, earlier: float) -> int:
    """Whole milliseconds from `earlier` to `later` (two readings of one monotonic clock), never below 0."""
    return max(0, round((later - earlier) * 1000))


@dataclass(frozen=True)
class ResponseFacts:
    """What one answer's headers say, in fixed words only: `cf-ray` present, the `server` header's product
    (`SERVER_WORDS`, `other` or `none`), `cf-cache-status` (`CACHE_WORDS`, `other` or `none`), the names of the
    cookies the store set that are in `COOKIE_WORDS` (each once, in that order), how many others it set, the
    `content-type` (`CONTENT_WORDS`, `other` or `none`), whether `cf-mitigated` and `retry-after` are there, and which
    of `HINT_HEADERS` are there (in that order)."""

    cf_ray: bool
    server: str
    cache: str
    cookies: tuple[str, ...]
    other_cookies: int
    content: str = "none"
    cf_mitigated: bool = False
    retry_after: bool = False
    hints: tuple[str, ...] = ()


def _word_of(value: str | None, words: tuple[str, ...]) -> str:
    if value is None:
        return "none"
    word = value.strip().lower()
    return word if word in words else "other"


def _cookie_word(header: str) -> str | None:
    """The allowlisted word for one `Set-Cookie` header's cookie name, or None (an unlisted name, or no name)."""
    name, equals, _ = header.partition("=")
    name = name.strip()
    if not equals:
        return None
    if name in _COOKIE_EXACT:
        return name
    for family, joiner in _COOKIE_FAMILIES:
        if name == family or name.startswith(family + joiner):
            return family
    return None


def _content_word(value: str | None) -> str:
    """`json` for `application/json` or an `application/…+json` type, `html` for `text/html`, else `other` (`none`:
    no header)."""
    if value is None:
        return "none"
    media = value.partition(";")[0].strip().lower()
    if media == "application/json" or (media.startswith("application/") and media.endswith("+json")):
        return "json"
    return "html" if media == "text/html" else "other"


def response_facts(headers: httpx.Headers) -> ResponseFacts:
    """The facts of one answer's headers, `Set-Cookie` and `Set-Cookie2` included (so this must see them before
    `GetOnlyTransport` drops them). Nothing from a header is kept but a fixed word, a yes or no, or a count."""
    server = headers.get("server")
    token = _SERVER_TOKEN.match(server.strip().lower()) if server is not None else None
    found: set[str] = set()
    others = 0
    for header in (*headers.get_list("set-cookie"), *headers.get_list("set-cookie2")):
        word = _cookie_word(header)
        if word is None:
            others += 1
        else:
            found.add(word)
    return ResponseFacts(
        cf_ray="cf-ray" in headers,
        server=_word_of(token.group() if token is not None else None, SERVER_WORDS),
        cache=_word_of(headers.get("cf-cache-status"), CACHE_WORDS),
        cookies=tuple(word for word in COOKIE_WORDS if word in found),
        other_cookies=others,
        content=_content_word(headers.get("content-type")),
        cf_mitigated="cf-mitigated" in headers,
        retry_after="retry-after" in headers,
        hints=tuple(name for name in HINT_HEADERS if name in headers),
    )


def error_word(error: BaseException) -> str:
    """The fixed word for the exception that ended a request (`ERROR_WORDS`), from its class only."""
    for kind, word in _ERROR_CLASSES:
        if isinstance(error, kind):
            return word
    return "other"


@dataclass(frozen=True)
class Wire:
    """What `FactsTransport` saw of one request, numbers and fixed words only. `facts` is None when no answer's
    headers arrived. `stage` is the last stage httpcore started (or the one that failed; `done` once the body was read
    to its end), from `STAGES`, None when no trace event came (a test transport). `new_connection`: a TCP connection
    was opened for it (else a kept-alive one was used, or no trace event came). The times are milliseconds from the
    request's start: `headers_ms` when the headers were in, `first_byte_ms` the first body byte, `longest_gap_ms` the
    longest wait for the body after its first byte (between two chunks, or from the last chunk to the body's end or
    failure). `received` is every body byte that came, even on a connection that then dropped; `declared_bytes` the
    `Content-Length`; `error` the `ERROR_WORDS` word of the exception that ended it, if one did."""

    facts: ResponseFacts | None = None
    stage: str | None = None
    new_connection: bool = False
    headers_ms: int | None = None
    first_byte_ms: int | None = None
    longest_gap_ms: int | None = None
    received: int = 0
    declared_bytes: int | None = None
    error: str | None = None


@dataclass(frozen=True)
class InFlight:
    """The request in flight when a read was stopped (Ctrl+C): its `Wire` so far, how long it had run, and the
    silence still open (`quiet_ms` since `quiet_since`: `last byte`, `headers` or `request start`)."""

    wire: Wire
    so_far_ms: int
    quiet_ms: int
    quiet_since: str


class _WireRecorder:
    """One request's `Wire`, built as it goes. `trace` is httpcore's `trace` extension callback: it keeps the event's
    name, through `_TRACE_STAGES` only, and the time; its `info` (which holds the request, with its address and
    `Authorization`) is never looked at or kept."""

    def __init__(self, monotonic: Callable[[], float]) -> None:
        self._monotonic = monotonic
        self._started = monotonic()
        self._last_byte: float | None = None
        self.wire = Wire()

    def _ms(self, moment: float) -> int:
        return ms_between(moment, self._started)

    def in_flight(self) -> InFlight:
        """This request as it stands (Ctrl+C mid-request): its `Wire`, how long it has run, and the silence still
        open, measured on this recorder's clock since the last body byte, else since the headers, else since the
        request started (`KeyboardInterrupt` isn't an `Exception`, so `body_ended` never measured it)."""
        moment = self._monotonic()
        so_far = ms_between(moment, self._started)
        if self._last_byte is not None:
            return InFlight(self.wire, so_far, ms_between(moment, self._last_byte), "last byte")
        if self.wire.headers_ms is not None:
            return InFlight(self.wire, so_far, max(0, so_far - self.wire.headers_ms), "headers")
        return InFlight(self.wire, so_far, so_far, "request start")

    def trace(self, name: str, info: object) -> None:  # `info` is never read: it holds the request
        base, _, phase = name.rpartition(".")
        stage = _TRACE_STAGES.get(base)
        if stage is None or phase not in _TRACE_PHASES:
            return
        if phase != "complete":
            self.wire = replace(self.wire, stage=stage)
            if base == "connection.connect_tcp" and phase == "started":
                self.wire = replace(self.wire, new_connection=True)
        elif stage == "headers":
            self.wire = replace(self.wire, headers_ms=self._ms(self._monotonic()))
        elif stage == "body":
            self.wire = replace(self.wire, stage="done")

    def answered(self, headers: httpx.Headers) -> None:
        """The headers are in (`handle_request` returned): their facts, the declared length, and their time when no
        trace event gave it."""
        headers_ms = self.wire.headers_ms
        self.wire = replace(
            self.wire,
            facts=response_facts(headers),
            declared_bytes=declared_length(headers.get("content-length")),
            headers_ms=headers_ms if headers_ms is not None else self._ms(self._monotonic()),
        )

    def failed(self, error: Exception) -> None:
        self.wire = replace(self.wire, error=error_word(error))

    def chunk(self, size: int) -> None:
        if size <= 0:
            return
        moment = self._monotonic()
        if self._last_byte is None:
            self.wire = replace(self.wire, first_byte_ms=self._ms(moment))
        else:
            self._gap(self._last_byte, moment)
        self._last_byte = moment
        self.wire = replace(self.wire, received=self.wire.received + size)

    def body_ended(self, error: Exception | None) -> None:
        if self._last_byte is not None:
            self._gap(self._last_byte, self._monotonic())
        if error is not None:
            self.failed(error)

    def _gap(self, since: float, moment: float) -> None:
        gap = ms_between(moment, since)
        if self.wire.longest_gap_ms is None or gap > self.wire.longest_gap_ms:
            self.wire = replace(self.wire, longest_gap_ms=gap)


class _CountingStream(httpx.SyncByteStream):
    """The answer's body, passed on chunk by chunk as it is, counted and timed for its `Wire`."""

    def __init__(self, inner: httpx.SyncByteStream, recorder: _WireRecorder) -> None:
        self._inner = inner
        self._recorder = recorder

    def __iter__(self) -> Iterator[bytes]:
        try:
            for chunk in self._inner:
                self._recorder.chunk(len(chunk))
                yield chunk
        except Exception as error:
            self._recorder.body_ended(error)
            raise
        self._recorder.body_ended(None)

    def close(self) -> None:
        self._inner.close()


class FactsTransport(httpx.BaseTransport):
    """L1's transport (t9): the caller builds its `WooClient` on it, and `WooClient` wraps it in `GetOnlyTransport`
    (`GetOnlyTransport(FactsTransport(real))`). So each answer comes through here first, with its headers and before
    `GetOnlyTransport` drops its cookies (httpx 0.28.1 runs `handle_request`, then extracts cookies, then the response
    hooks). It keeps a `Wire` of each request, fixed words and numbers only, and hands the answer on unchanged but for
    its body stream, which is wrapped to count and time it (httpx's own client wraps it the same way next,
    `BoundSyncStream`). It gives the request httpcore's `trace` extension (`_WireRecorder.trace`), and refuses any
    request but a GET itself (as `GetOnlyTransport` does before it). `take` returns the last request's `Wire`, once."""

    def __init__(self, inner: httpx.BaseTransport, *, monotonic: Callable[[], float] = time.monotonic) -> None:
        self._inner = inner
        self._monotonic = monotonic
        self._recorder: _WireRecorder | None = None

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        if request.method != "GET":
            raise NonGetRefused("only GET requests are sent to a store")
        recorder = self._recorder = _WireRecorder(self._monotonic)
        request.extensions["trace"] = recorder.trace
        try:
            response = self._inner.handle_request(request)
        except Exception as error:
            recorder.failed(error)
            raise
        recorder.answered(response.headers)
        if isinstance(response.stream, httpx.SyncByteStream):
            response.stream = _CountingStream(response.stream, recorder)
        return response

    def take(self) -> Wire | None:
        """The last request's `Wire` (None when no request went through since the last `take`)."""
        recorder, self._recorder = self._recorder, None
        return recorder.wire if recorder is not None else None

    def take_in_flight(self) -> InFlight | None:
        """For a read stopped mid-request (Ctrl+C, review 2 and its re-check): the request in flight as it stands
        (`_WireRecorder.in_flight`); None when no request was in flight (each finished one was taken by the reader)."""
        recorder, self._recorder = self._recorder, None
        return recorder.in_flight() if recorder is not None else None

    def close(self) -> None:
        self._inner.close()


@dataclass(frozen=True)
class Attempt:
    """One attempt (the first try or a retry), for L1's trace. `page` is the products page (None: `system_status`;
    `what` names which); `attempt` 1 to 4; `outcome` `ok` (an answer the reader takes), `past_the_end` (a 400 on page
    2 or later) or the fixed reason; `http_status` when an answer arrived. `headers`: True when the answer's headers
    arrived, False when nothing came, None when that isn't known (a connection that failed with no `facts`
    transport). `body_bytes`: the body bytes that came (for a timeout, or with a `facts` transport a dropped
    connection, what came before it ended), None when not known. `elapsed_ms` is the request alone; `waited_ms` the
    wait before it (the spacing, a back-off or a `Retry-After`). `ended`, for a timeout only: httpx's own timeout by
    its word (`connect_timeout`, `read_timeout`, `write_timeout`, `pool_timeout`), or `attempt_bound` or `store_bound`
    (`_Session._ended`). `wire` when the read has a `FactsTransport`
    (`facts` is its `Wire.facts`)."""

    page: int | None
    attempt: int
    outcome: str
    http_status: int | None
    elapsed_ms: int
    body_bytes: int | None
    headers: bool | None
    wire: Wire | None = None
    waited_ms: int = 0
    ended: str | None = None

    @property
    def what(self) -> str:
        return "system_status" if self.page is None else "products"

    @property
    def facts(self) -> ResponseFacts | None:
        return self.wire.facts if self.wire is not None else None


Observe = Callable[[Attempt], None]


class FailureCount(Protocol):
    """Failed requests in a row for one store (APL-12), kept across runs by the caller."""

    def failed(self, reason: str) -> bool:
        """Count one failed attempt; True when the store is now auto-paused (the read then ends)."""
        ...

    def succeeded(self) -> None:
        """A request worked: the count goes back to 0."""
        ...


class MemoryFailureCount:
    """A count kept in memory only (the L1 dry read, tests)."""

    def __init__(self, start: int = 0, limit: int = FAILURES_TO_PAUSE) -> None:
        self.count = start
        self.limit = limit
        self.paused_reason: str | None = None

    def failed(self, reason: str) -> bool:
        self.count += 1
        if self.count >= self.limit:
            self.paused_reason = reason
            return True
        return False

    def succeeded(self) -> None:
        self.count = 0


class Stop(Protocol):
    """`threading.Event` is one: `wait` returns True when a stop was asked for (at once, or during the wait)."""

    def is_set(self) -> bool: ...

    def wait(self, timeout: float | None = None) -> bool: ...


Progress = Callable[[int, int, int], None]  # (page, pages, rows so far)


@dataclass(frozen=True)
class CatalogRead:
    """One store's read. `reason` is None when it worked; then `products` holds every row, in id order. A failed
    read has no products. `http_status` is the status of the last failed request (when one answered). For a
    `bad_response`, `bad_field` names what was wrong (a fixed identifier such as `name` or `downloads.file`, never a
    value) and `bad_page` the products page (None: `system_status`)."""

    reason: str | None
    products: tuple[Product, ...] = ()
    total: int | None = None  # page 1's X-WP-Total
    pages: int = 0  # products pages read in the last listing
    http_status: int | None = None
    wc_version: str | None = None
    largest_page_bytes: int = 0
    requests: int = 0
    auto_paused: bool = False
    bad_field: str | None = None
    bad_page: int | None = None

    @property
    def ok(self) -> bool:
        return self.reason is None


class BadAnswer(Exception):
    """The store's answer isn't what the reader accepts: the read ends with `bad_response`. `field` is a fixed
    identifier from this code (never a value from the answer)."""

    def __init__(self, field: str) -> None:
        super().__init__(field)
        self.field = field


class _End(Exception):
    """The read ends here with `reason` (and, for a `bad_response`, the field and the page)."""

    def __init__(self, reason: str, field: str | None = None, page: int | None = None) -> None:
        super().__init__(reason)
        self.reason = reason
        self.field = field
        self.page = page


def retry_delay(headers: httpx.Headers | None, attempt: int, now: datetime) -> float:
    """How long to wait before retry number `attempt + 1`: the `Retry-After` (seconds, or an HTTP date) when it is
    given and readable, at most 60 s and never below 0; otherwise 2, 4, 8 s."""
    backoff = BACKOFF_SECONDS[min(attempt, len(BACKOFF_SECONDS) - 1)]
    value = headers.get("retry-after", "").strip() if headers is not None else ""
    if not value:
        return backoff
    seconds: float | None
    if value.isascii() and value.isdigit():
        seconds = float(value) if len(value) <= 10 else RETRY_AFTER_MAX_SECONDS
    else:
        try:
            moment = parsedate_to_datetime(value)
        except TypeError, ValueError, IndexError, OverflowError:
            return backoff
        if moment.tzinfo is None:
            moment = moment.replace(tzinfo=UTC)  # RFC 9110: an HTTP date is always GMT
        seconds = (moment - now).total_seconds()
    return min(max(seconds, 0.0), RETRY_AFTER_MAX_SECONDS)


def is_retried(reason: str, status: int | None) -> bool:
    return reason in RETRIED_REASONS or (reason == "blocked" and status == 503)


def is_param_refused(response: WooResponse) -> bool:
    """A 400 whose body is WordPress's REST error for a parameter it refused (`rest_invalid_param`)."""
    if response.status != 400:
        return False
    data = _json(response.body)
    return isinstance(data, dict) and data.get("code") == "rest_invalid_param"


@dataclass(frozen=True)
class _Try:
    """One attempt as the observer sees it: the products page (None: `system_status`), its number (1 to 4), the wait
    before it, when it started, and the deadline `client.get` was given."""

    page: int | None
    number: int
    waited_ms: int
    started: float
    deadline: float


class _Session:
    """The requests of one store's read: spacing, retries, the failure count, the time bound and the stop."""

    def __init__(
        self,
        client: WooClient,
        *,
        spacing_seconds: float,
        stop: Stop,
        failures: FailureCount,
        monotonic: Callable[[], float],
        now: Callable[[], datetime],
        deadline: float,
        observe: Observe | None = None,
        facts: FactsTransport | None = None,
        attempt_seconds: float | None = None,
    ) -> None:
        self._client = client
        self._spacing = spacing_seconds
        self._stop = stop
        self._failures = failures
        self._monotonic = monotonic
        self._now = now
        self._deadline = deadline
        self._observe = observe
        self._facts = facts
        self._attempt_seconds = attempt_seconds
        # The client's read timeout, to tell whether a deadline shortened it (`_ended`). Read from the client's own
        # attribute: `WooClient`'s public surface stays `get` and `close` until M5 (the GET-only contract test).
        self._read_seconds: float = client._read_seconds
        self._sent = False
        self.requests = 0
        self.last_failure_status: int | None = None
        self.auto_paused = False

    def _pause(self, seconds: float) -> None:
        if seconds <= 0:
            return
        if self._monotonic() + seconds > self._deadline:
            raise _End("timeout")  # the wait alone would pass the store's bound
        if self._stop.wait(seconds):
            raise _End("stopped")

    def _note_answer(self, tried: _Try | None, outcome: str, response: WooResponse) -> None:
        """An answer came (headers and body): hand the attempt to `observe`, when there is one."""
        if tried is not None and (observe := self._observe) is not None:
            self._emit(observe, tried, outcome, response.status, len(response.body), True)

    def _note_refused(self, tried: _Try | None, refused: ReadRefused) -> None:
        """No usable answer: hand the attempt to `observe`, when there is one. A timeout says whether the headers had
        arrived (`ReadRefused.headers_status`), the bytes read before it ended, and which limit ended it; a redirect,
        and an over-long or unreadable body (`bad_response`), are refused only once the headers are in; for a failed
        connection it is known only through the `facts` transport (`_emit`), else None."""
        if tried is None or (observe := self._observe) is None:
            return
        status = refused.status if refused.status is not None else refused.headers_status
        body_bytes: int | None = None
        headers: bool | None = None
        timeout = refused.reason == "timeout"
        if timeout:
            headers, body_bytes = refused.headers_status is not None, refused.received
        elif refused.reason in ("redirected", "bad_response"):
            headers = True
        self._emit(observe, tried, refused.reason, status, body_bytes, headers, timeout=timeout)

    def _ended(self, tried: _Try, wire: Wire | None) -> str:
        """What ended a timed-out attempt (reviews 1 and 2, the lead's decisions), from facts, not the clock's distance
        to a deadline. `WooClient.get` sets its timeouts once, from the deadline it is given: the read timeout (and the
        write and pool ones) is `min(read_seconds, remaining)`, the connect one `min(10 s, remaining)`, and httpx
        applies each per phase. So the deadline is what ended the attempt when:
        - `WooClient`'s own check between chunks fired (a timeout with no exception behind it: the `Wire` holds no
          error), or
        - the deadline shortened the timeout (`deadline - started < read_seconds`) and the error isn't
          `connect_timeout` (the 10 s connect timeout is its own).
        It is then `store_bound` when that deadline was the store's, else `attempt_bound`. Otherwise it is httpx's own
        timeout, by its word (`TIMEOUT_WORDS`; `read_timeout` when there is no `Wire`, or for a timeout httpx didn't
        name). No slack is needed any more: nothing here compares the clock with the deadline. Without a `facts`
        transport the first test can't be made, so a trickle caught by `WooClient`'s check reads as `read_timeout`."""
        which = "store_bound" if tried.deadline >= self._deadline else "attempt_bound"
        if wire is not None and wire.error is None:
            return which
        error = wire.error if wire is not None and wire.error in TIMEOUT_WORDS else "read_timeout"
        if tried.deadline - tried.started < self._read_seconds and error != "connect_timeout":
            return which
        return error

    def _emit(
        self,
        observe: Observe,
        tried: _Try,
        outcome: str,
        status: int | None,
        body_bytes: int | None,
        headers: bool | None,
        *,
        timeout: bool = False,
    ) -> None:
        """Build the `Attempt` and hand it on. With a `facts` transport its `Wire` gives the body bytes (every byte
        that came, a dropped connection's too) and whether headers arrived."""
        wire = self._facts.take() if self._facts is not None else None
        if wire is not None:
            body_bytes, headers = wire.received, wire.facts is not None
        observe(
            Attempt(
                page=tried.page,
                attempt=tried.number,
                outcome=outcome,
                http_status=status,
                elapsed_ms=ms_between(self._monotonic(), tried.started),
                body_bytes=body_bytes,
                headers=headers,
                wire=wire,
                waited_ms=tried.waited_ms,
                ended=self._ended(tried, wire) if timeout else None,
            )
        )

    def usable(self) -> None:
        """A products page was read and parsed: the failures in a row go back to 0."""
        self._failures.succeeded()

    def bad(self, field: str, page: int | None) -> NoReturn:
        """An answer came (a 200) but can't be used: it counts as a failed request for APL-12 (a store that keeps
        sending a bad page is auto-paused after 10 in a row, m3.1 review 2), then the read ends with
        `bad_response`, naming the field and the page."""
        if self._failures.failed("bad_response"):
            self.auto_paused = True
        raise _End("bad_response", field, page)

    def request(
        self,
        method: str,
        path: str,
        params: dict[str, str],
        max_bytes: int,
        *,
        page: int | None = None,
        past_the_end: bool = False,
        refusable: bool = False,
    ) -> WooResponse:
        """One request with its retries. Only a GET is ever sent or retried: any other method is refused here,
        before anything is sent (and `GetOnlyTransport` refuses one too). With `page` (a products page's number), a
        200 is returned as it is (the caller parses it, and a body that isn't a JSON list is its `bad_response`);
        otherwise a 200 that isn't JSON is `not_woocommerce`, as in Test connection. With `past_the_end` (pages 2 and
        later), a 400 is returned as it is too, neither a success nor a failure: WooCommerce's answer to a page past
        the last one, which the caller treats as the listing having shrunk while it was read (m3.1 review 2; not
        verified on a store). With `refusable` (m3.2: a parameter the store may not accept, `include_status`), a 400
        whose body is WordPress's `rest_invalid_param` error is returned as it is too, neither a success nor a
        failure: the caller falls back to another listing. Each attempt goes to `observe` when there is one, before
        anything else is done with it."""
        if method != "GET":
            raise NonGetRefused("only GET requests are sent or retried")
        delay = self._spacing if self._sent else 0.0
        attempt = 0
        while True:
            before = self._monotonic() if self._observe is not None else 0.0
            self._pause(delay)
            if self._stop.is_set():
                raise _End("stopped")
            if self._monotonic() >= self._deadline:
                raise _End("timeout")
            self._sent = True
            self.requests += 1
            headers: httpx.Headers | None = None
            # Without an observer or an attempt bound (the app), no clock is read here and `client.get` gets the
            # store's deadline, as always.
            timed = self._observe is not None or self._attempt_seconds is not None
            started = self._monotonic() if timed else 0.0
            deadline = self._deadline
            if self._attempt_seconds is not None:
                deadline = min(deadline, started + self._attempt_seconds)
            tried = None
            if self._observe is not None:
                tried = _Try(page, attempt + 1, ms_between(started, before), started, deadline)
            try:
                response = self._client.get(path, params, deadline, max_bytes=max_bytes)
            except ReadRefused as refused:
                reason = refused.reason
                status = refused.status
                self._note_refused(tried, refused)
            else:
                if past_the_end and response.status == 400:
                    self._note_answer(tried, "past_the_end", response)
                    return response
                if refusable and is_param_refused(response):
                    self._note_answer(tried, "param_refused", response)
                    return response
                answered = None if page is not None and response.status == 200 else classify(response)
                self._note_answer(tried, answered or "ok", response)
                if answered is None:
                    return response  # the caller resets the count once the answer proved usable
                reason, status, headers = answered, response.status, response.headers
            self.last_failure_status = status
            if self._failures.failed(reason):
                self.auto_paused = True
                raise _End(reason)
            if not is_retried(reason, status) or attempt >= RETRIES:
                raise _End(reason)
            delay = max(self._spacing, retry_delay(headers, attempt, self._now()))
            attempt += 1


def read_catalog(
    client: WooClient,
    *,
    spacing_ms: int,
    stop: Stop,
    failures: FailureCount,
    progress: Progress | None = None,
    monotonic: Callable[[], float] = time.monotonic,
    now: Callable[[], datetime] = utc_now,
    store_seconds: float = STORE_SECONDS,
    page_max_bytes: int = PAGE_MAX_BYTES,
    listing_max_bytes: int = LISTING_MAX_BYTES,
    observe: Observe | None = None,
    facts: FactsTransport | None = None,
    meta: bool = True,
    per_page: int = PER_PAGE,
    max_pages: int = MAX_PAGES,
    attempt_seconds: float | None = None,
) -> CatalogRead:
    """Read one store's catalog (the module text says how). Never raises for anything the store answers.
    `observe`, `facts`, `meta`, `per_page`, `max_pages` and `attempt_seconds` are L1's (t9; the module text): the
    app leaves them as they are. A `per_page` outside 25 to 100, a `max_pages` below 1 or past 4,000 rows, or an
    `attempt_seconds` that isn't above 0, is a `ValueError` before anything is sent."""
    shape = ListingShape(per_page, max_pages, meta)
    if attempt_seconds is not None and not attempt_seconds > 0:
        raise ValueError("attempt_seconds must be above 0")
    session = _Session(
        client,
        spacing_seconds=spacing_ms / 1000,
        stop=stop,
        failures=failures,
        monotonic=monotonic,
        now=now,
        deadline=monotonic() + store_seconds,
        observe=observe,
        facts=facts,
        attempt_seconds=attempt_seconds,
    )
    wc_version: str | None = None
    state = _Listing()
    try:
        wc_version = _check_version(session)
        query = shape.query()
        for _attempt in range(2):
            state = _Listing()
            _read_listing(session, state, query, page_max_bytes, listing_max_bytes, progress)
            if state.consistent():
                return CatalogRead(
                    None,
                    tuple(state.rows),
                    state.total,
                    state.pages,
                    session.last_failure_status,
                    wc_version,
                    state.largest,
                    session.requests,
                )
        raise _End("count_mismatch")
    except _End as end:
        return CatalogRead(
            end.reason,
            (),
            state.total,
            state.pages,
            session.last_failure_status,
            wc_version,
            state.largest,
            session.requests,
            session.auto_paused,
            end.field,
            end.page,
        )


def read_store_catalog(client: WooClient, code: str, **options: Any) -> CatalogRead:
    """`read_catalog` plus its one log line. `code` is the store's two-letter code, the only name the line carries."""
    result = read_catalog(client, **options)
    log_read(code, result)
    return result


def describe_bad(result: CatalogRead | SnapshotRead) -> str:
    """`; field <name> on page <n>` for a `bad_response` that named one (the page is `system_status` for the first
    request), else nothing."""
    if result.bad_field is None:
        return ""
    where = "system_status" if result.bad_page is None else f"page {result.bad_page}"
    return f"; field {result.bad_field} on {where}"


def log_read(code: str, result: CatalogRead) -> None:
    level = logging.INFO if result.ok else logging.WARNING
    _log.log(
        level,
        "Store %s catalog read: %s (pages %d, rows %d, last failure HTTP %s%s)%s",
        code,
        result.reason or "ok",
        result.pages,
        len(result.products),
        result.http_status,
        describe_bad(result),
        "; the store's sync is now auto-paused" if result.auto_paused else "",
    )


def _check_version(session: _Session) -> str:
    response = session.request("GET", SYSTEM_STATUS_PATH, dict(SYSTEM_STATUS_PARAMS), 1024 * 1024)
    data = _json(response.body)
    environment = data.get("environment") if isinstance(data, dict) else None
    if not isinstance(environment, dict):
        session.bad("environment", None)
    version = _clean_version(environment.get("version"))
    parsed = _version_tuple(version) if version else None
    if version is None or parsed is None:
        session.bad("version", None)
    if parsed < MIN_WC_VERSION:
        raise _End("wc_too_old")
    return version


@dataclass(frozen=True)
class ListingShape:
    """The listing's pages: `per_page` rows each, at most `max_pages`, with or without `meta_data` (L1's options;
    the app's are 100, 40 and with). L1 builds one to show its request list (`params`); the reader builds its own from
    the same values."""

    per_page: int = PER_PAGE
    max_pages: int = MAX_PAGES
    meta: bool = True

    def __post_init__(self) -> None:
        if not PER_PAGE_MIN <= self.per_page <= PER_PAGE:
            raise ValueError(f"per_page must be {PER_PAGE_MIN} to {PER_PAGE}")
        if self.max_pages < 1 or self.max_pages * self.per_page > MAX_ROWS:
            raise ValueError(f"max_pages must be at least 1 and reach at most {MAX_ROWS} rows")

    def params(self, page: int) -> dict[str, str]:
        return listing_params(page, per_page=self.per_page, meta=self.meta)

    def query(self) -> Query:
        per_page, meta = self.per_page, self.meta
        return Query(
            PRODUCTS_PATH, self.params, lambda body: parse_page(body, per_page=per_page, meta=meta), self.max_pages
        )


@dataclass(frozen=True)
class Query:
    """One paged listing: its path, each page's query, how a page is parsed, and the most pages it may have.
    `empty_ok`: no rows is a result (an incremental with nothing new, a trash listing, a product with no variations),
    else it is `no_products`. `refusable`: page 1 may answer WordPress's `rest_invalid_param` 400, which
    `_read_listing` raises as `Refused` for the caller to fall back."""

    path: str
    params: Callable[[int], dict[str, str]]
    parse: Callable[[bytes], list[Product]]
    max_pages: int
    empty_ok: bool = False
    refusable: bool = False


class Refused(Exception):
    """Page 1 of a `refusable` listing answered `rest_invalid_param`: the store doesn't accept that query."""


@dataclass
class _Listing:
    rows: list[Product] = field(default_factory=list)
    total: int | None = None
    pages: int = 0
    largest: int = 0
    size: int = 0  # every page's bytes together

    def consistent(self) -> bool:
        """As many rows as page 1's `X-WP-Total`, every id once, ascending across the pages."""
        if len(self.rows) != self.total:
            return False
        return all(earlier.wc_id < later.wc_id for earlier, later in pairwise(self.rows))

    def add_page(
        self, session: _Session, page: int, body: bytes, listing_max_bytes: int, parse: Callable[[bytes], list[Product]]
    ) -> None:
        self.pages = page
        self.largest = max(self.largest, len(body))
        self.size += len(body)
        if self.size > listing_max_bytes:
            session.bad("listing_bytes", page)
        try:
            rows = parse(body)
        except BadAnswer as bad:
            session.bad(bad.field, page)
        self.rows.extend(rows)
        session.usable()


def _count(session: _Session, headers: httpx.Headers, name: str) -> int:
    value = headers.get(name)
    if value is None or _COUNT.fullmatch(value) is None:
        session.bad(name, 1)
    return int(value)


def _read_listing(
    session: _Session,
    listing: _Listing,
    query: Query,
    page_max_bytes: int,
    listing_max_bytes: int,
    progress: Progress | None,
) -> None:
    first = session.request("GET", query.path, query.params(1), page_max_bytes, page=1, refusable=query.refusable)
    if query.refusable and is_param_refused(first):
        raise Refused
    listing.total = _count(session, first.headers, "x-wp-total")
    pages = _count(session, first.headers, "x-wp-totalpages")
    if pages > query.max_pages:
        raise _End("too_many_pages")
    listing.add_page(session, 1, first.body, listing_max_bytes, query.parse)
    if listing.total == 0 and not listing.rows and not query.empty_ok:
        raise _End("no_products")
    if progress is not None:
        progress(1, max(pages, 1), len(listing.rows))
    for page in range(2, pages + 1):
        response = session.request("GET", query.path, query.params(page), page_max_bytes, page=page, past_the_end=True)
        if response.status == 400:
            return  # the pages ran out early: the count check reads the listing once more
        listing.add_page(session, page, response.body, listing_max_bytes, query.parse)
        if progress is not None:
            progress(page, pages, len(listing.rows))


def parse_page(body: bytes, *, per_page: int = PER_PAGE, meta: bool = True, kind: str = "product") -> list[Product]:
    """One products page: a JSON list of at most `per_page` products (100 in the app). `BadAnswer` for anything
    else. With `meta=False` (L1's option), `meta_data` isn't read: the products have no `latest_version` data.
    `kind` (m3.2) says which fields the rows have: `product` (the full and incremental reads), `snapshot` (no `name`:
    the title is empty) or `variation` (no `name`, `slug` or `type`: the slug is empty, the type `variation`)."""
    try:
        data = json.loads(body.decode("utf-8"))
    except ValueError, RecursionError:  # UnicodeDecodeError and JSONDecodeError are ValueErrors; a deep nest recurses
        raise BadAnswer("json") from None
    if not isinstance(data, list) or len(data) > per_page:
        raise BadAnswer("page")
    return [parse_product(raw, meta=meta, kind=kind) for raw in data]


def _clean(value: str, name: str) -> str:
    """A text the database can hold as it is: no NUL and no lone surrogate (JSON's `\\ud800` escape makes one, and
    UTF-8 can't encode it)."""
    if "\x00" in value:
        raise BadAnswer(name)
    try:
        value.encode("utf-8")
    except UnicodeEncodeError:
        raise BadAnswer(name) from None
    return value


def _text(raw: dict[str, Any], key: str, longest: int, shortest: int = 0, name: str | None = None) -> str:
    value = raw.get(key)
    if not isinstance(value, str) or not shortest <= len(value) <= longest:
        raise BadAnswer(name or key)
    return _clean(value, name or key)


def _word(raw: dict[str, Any], key: str) -> str:
    value = raw.get(key)
    if not isinstance(value, str) or _WORD.fullmatch(value) is None:
        raise BadAnswer(key)
    return value


ROW_KINDS = ("product", "snapshot", "variation")


def parse_product(raw: Any, *, meta: bool = True, kind: str = "product") -> Product:
    """One product, with the limits of `catalog/model.py`. `BadAnswer` names the field (never its value). With
    `meta=False` (L1's option), `meta_data` is neither read nor checked: no `latest_version` data, no error. `kind`:
    see `parse_page`."""
    if kind not in ROW_KINDS:
        raise ValueError("unknown row kind")
    if not isinstance(raw, dict):
        raise BadAnswer("row")
    wc_id = raw.get("id")
    if type(wc_id) is not int or not 1 <= wc_id <= WC_ID_MAX:
        raise BadAnswer("id")
    slug = _text(raw, "slug", SLUG_MAX) if kind != "variation" else ""
    raw_title = _text(raw, "name", TITLE_MAX) if kind == "product" else ""
    title = _clean(html.unescape(raw_title), "name")
    if len(title) > TITLE_MAX:  # not expected (unescaping never lengthens), checked so the table's CHECK always holds
        raise BadAnswer("name")
    kept, meta_skipped = _meta(raw.get("meta_data")) if meta else ((), 0)
    if "date_modified_gmt" not in raw:
        raise BadAnswer("date_modified_gmt")
    modified = raw["date_modified_gmt"]
    if modified is not None and (not isinstance(modified, str) or _GMT.fullmatch(modified) is None):
        raise BadAnswer("date_modified_gmt")
    return Product(
        wc_id=wc_id,
        slug=slug,
        title=title,
        type=_word(raw, "type") if kind != "variation" else "variation",
        status=_word(raw, "status"),
        modified_gmt=modified,
        downloads=_downloads(raw.get("downloads")),
        meta=kept,
        entities=title != raw_title,
        meta_skipped=meta_skipped,
    )


def _downloads(value: Any) -> tuple[Download, ...]:
    if not isinstance(value, list) or len(value) > DOWNLOADS_MAX:
        raise BadAnswer("downloads")
    found: list[Download] = []
    for raw in value:
        if not isinstance(raw, dict):
            raise BadAnswer("downloads")
        found.append(
            Download(
                id=_text(raw, "id", DOWNLOAD_ID_MAX, 1, "downloads.id"),
                name=_text(raw, "name", DOWNLOAD_NAME_MAX, name="downloads.name"),
                file=_text(raw, "file", DOWNLOAD_FILE_MAX, name="downloads.file"),
            )
        )
    downloads = tuple(found)
    if len(downloads_json(downloads)) > DOWNLOADS_JSON_MAX:  # escaped control characters take six characters each
        raise BadAnswer("downloads_json")
    return downloads


def _meta(value: Any) -> tuple[tuple[tuple[str, str], ...], int]:
    """The entries whose key starts with `latest_version`, and how many such entries were skipped (Lead
    (proposed), m3.1 review 2): one whose key or value can't be kept (a value that isn't text or is longer than
    200, a key longer than 255, a NUL or a lone surrogate in either), any past the 50 kept, and the last ones while
    the stored JSON would pass its limit. A bad entry costs only itself, never the store's read. `meta_data` must
    still be a list of objects with a text key (the rest of it is never stored)."""
    if not isinstance(value, list):
        raise BadAnswer("meta_data")
    kept: list[tuple[str, str]] = []
    skipped = 0
    for raw in value:
        if not isinstance(raw, dict) or not isinstance(raw.get("key"), str):
            raise BadAnswer("meta_data")
        key: str = raw["key"]
        if not key.startswith(META_PREFIX):
            continue
        try:
            if len(key) > META_KEY_MAX or len(kept) >= META_KEPT_MAX:
                raise BadAnswer("meta_data.key")
            entry = (_clean(key, "meta_data.key"), _text(raw, "value", META_VALUE_MAX, name="meta_data.value"))
        except BadAnswer:
            skipped += 1
            continue
        kept.append(entry)
    while kept and len(meta_json(tuple(kept))) > META_JSON_MAX:
        kept.pop()
        skipped += 1
    return tuple(kept), skipped


# ---- m3.2: the incremental read and the nightly snapshot -----------------------------------------------------------
#
# Both use the same session as the full read (`_Session`: GET only, the spacing, APL-12's retries and the failure
# count, the store's 10-minute bound, the stop) and the same checks on every page (`_read_listing`: the count check
# read once more on a mismatch, hostile answers failing closed, the page and listing caps).
#
# **The incremental read (SYNC-01):** `system_status`, then `GET /products?modified_after=<watermark - 2 min>&
# dates_are_gmt=true&status=any&orderby=id&order=asc&per_page=100&page=<n>&_fields=<the full read's>`, with no
# `downloadable` filter (a product whose downloads were removed must still be seen). No row is a result.
#
# **The snapshot (SYNC-03, SYNC-04):** `system_status`; a one-row probe `include_status=trash` (is the parameter
# known? a store that ignores it answers with a product that isn't in the trash); then the listing with
# `include_status=any,trash` and `_fields=id,slug,status,type,date_modified_gmt,downloads,meta_data`. The listing is
# kept only when its trashed rows are as many as the probe's `X-WP-Total`; otherwise, or when the store refuses the
# parameter (`rest_invalid_param`), it falls back to two listings, `status=any` then `status=trash` (`listing` says
# which was used). Then each variable product's `GET /products/{id}/variations` (at most 50 variable products, else
# `too_many_variable`; at most 4 pages of 100 variations each, else `too_many_pages`).

SNAPSHOT_FIELDS = "id,slug,status,type,date_modified_gmt,downloads,meta_data"
VARIATION_FIELDS = "id,status,date_modified_gmt,downloads,meta_data"
VARIABLE_MAX = 50  # more variable products than this stops the store's snapshot (V30: none on the real stores)
VARIATION_PAGES = 4  # at most 400 variations on one product (Lead (proposed))
TRASH = "trash"
INCLUDE_STATUS = "include_status"  # the listing used: one listing with `include_status=any,trash`
TWO_LISTINGS = "two_listings"  # the fallback: `status=any`, then `status=trash`
SNAPSHOT_REASONS = frozenset({"too_many_variable", "trash_unlisted"})


def incremental_params(page: int, since: str) -> dict[str, str]:
    """The query of one incremental page (contract-tested)."""
    return {
        "modified_after": since,
        "dates_are_gmt": "true",
        "status": "any",
        "orderby": "id",
        "order": "asc",
        "per_page": str(PER_PAGE),
        "page": str(page),
        "_fields": LISTING_FIELDS,
    }


def snapshot_params(page: int, statuses: tuple[str, str], *, per_page: int = PER_PAGE) -> dict[str, str]:
    """The query of one snapshot page. `statuses` is (`include_status`, `any,trash`), (`include_status`, `trash`) for
    the probe, or (`status`, `any` or `trash`) for the fallback."""
    name, value = statuses
    return {
        name: value,
        "orderby": "id",
        "order": "asc",
        "per_page": str(per_page),
        "page": str(page),
        "_fields": SNAPSHOT_FIELDS,
    }


def variation_params(page: int) -> dict[str, str]:
    return {"orderby": "id", "order": "asc", "per_page": str(PER_PAGE), "page": str(page), "_fields": VARIATION_FIELDS}


def variations_path(wc_id: int) -> str:
    if type(wc_id) is not int or not 1 <= wc_id <= WC_ID_MAX:
        raise ValueError("a product id")
    return f"{PRODUCTS_PATH}/{wc_id}/variations"


@dataclass(frozen=True)
class SnapshotRead:
    """One store's snapshot read. `reason` is None when it worked; then `products` holds every product (trash
    included) in id order, `variations` each variable product's variations (by its id, in id order), and `listing`
    which listing was used (`INCLUDE_STATUS` or `TWO_LISTINGS`). A failed read has no products. The rest as
    `CatalogRead`."""

    reason: str | None
    products: tuple[Product, ...] = ()
    variations: tuple[tuple[int, tuple[Product, ...]], ...] = ()
    listing: str | None = None
    pages: int = 0
    http_status: int | None = None
    wc_version: str | None = None
    requests: int = 0
    auto_paused: bool = False
    bad_field: str | None = None
    bad_page: int | None = None

    @property
    def ok(self) -> bool:
        return self.reason is None

    @property
    def trashed(self) -> int:
        return sum(1 for product in self.products if product.status == TRASH)


@dataclass
class _Totals:
    pages: int = 0


def _session(
    client: WooClient,
    *,
    spacing_ms: int,
    stop: Stop,
    failures: FailureCount,
    monotonic: Callable[[], float],
    now: Callable[[], datetime],
    store_seconds: float,
) -> _Session:
    return _Session(
        client,
        spacing_seconds=spacing_ms / 1000,
        stop=stop,
        failures=failures,
        monotonic=monotonic,
        now=now,
        deadline=monotonic() + store_seconds,
    )


def _consistent(
    session: _Session,
    query: Query,
    totals: _Totals,
    page_max_bytes: int,
    listing_max_bytes: int,
    progress: Progress | None = None,
) -> list[Product]:
    """One listing that passed the count check (read once more on a mismatch, then `count_mismatch`)."""
    for _attempt in range(2):
        state = _Listing()
        try:
            _read_listing(session, state, query, page_max_bytes, listing_max_bytes, progress)
        finally:
            totals.pages += state.pages
        if state.consistent():
            return state.rows
    raise _End("count_mismatch")


def read_incremental(
    client: WooClient,
    *,
    watermark: str,
    spacing_ms: int,
    stop: Stop,
    failures: FailureCount,
    progress: Progress | None = None,
    monotonic: Callable[[], float] = time.monotonic,
    now: Callable[[], datetime] = utc_now,
    store_seconds: float = STORE_SECONDS,
    page_max_bytes: int = PAGE_MAX_BYTES,
    listing_max_bytes: int = LISTING_MAX_BYTES,
) -> CatalogRead:
    """The products changed since `watermark` (SYNC-01; the section text says how). Never raises for anything the
    store answers; `ValueError` before anything is sent when `watermark` isn't a store date."""
    since = modified_after(watermark)
    session = _session(
        client,
        spacing_ms=spacing_ms,
        stop=stop,
        failures=failures,
        monotonic=monotonic,
        now=now,
        store_seconds=store_seconds,
    )
    query = Query(PRODUCTS_PATH, lambda page: incremental_params(page, since), parse_page, MAX_PAGES, empty_ok=True)
    totals = _Totals()
    wc_version: str | None = None
    try:
        wc_version = _check_version(session)
        rows = _consistent(session, query, totals, page_max_bytes, listing_max_bytes, progress)
    except _End as end:
        return CatalogRead(
            end.reason,
            (),
            None,
            totals.pages,
            session.last_failure_status,
            wc_version,
            requests=session.requests,
            auto_paused=session.auto_paused,
            bad_field=end.field,
            bad_page=end.page,
        )
    return CatalogRead(
        None, tuple(rows), len(rows), totals.pages, session.last_failure_status, wc_version, requests=session.requests
    )


def _probe_trash(session: _Session, page_max_bytes: int) -> tuple[int, list[Product]] | None:
    """`include_status=trash`, one row: (`X-WP-Total`, the row) when the store accepts the parameter, None when it
    refuses it (`rest_invalid_param`)."""
    params = snapshot_params(1, (INCLUDE_STATUS, TRASH), per_page=1)
    response = session.request("GET", PRODUCTS_PATH, params, page_max_bytes, page=1, refusable=True)
    if is_param_refused(response):
        return None
    total = _count(session, response.headers, "x-wp-total")
    try:
        rows = parse_page(response.body, per_page=1, kind="snapshot")
    except BadAnswer as bad:
        session.bad(bad.field, 1)
    session.usable()
    return total, rows


def _snapshot_query(statuses: tuple[str, str], *, empty_ok: bool, refusable: bool) -> Query:
    return Query(
        PRODUCTS_PATH,
        lambda page: snapshot_params(page, statuses),
        lambda body: parse_page(body, kind="snapshot"),
        MAX_PAGES,
        empty_ok=empty_ok,
        refusable=refusable,
    )


def _snapshot_products(
    session: _Session, totals: _Totals, page_max_bytes: int, listing_max_bytes: int, progress: Progress | None
) -> tuple[list[Product], str]:
    probe = _probe_trash(session, page_max_bytes)
    if probe is not None and all(row.status == TRASH for row in probe[1]):
        query = _snapshot_query((INCLUDE_STATUS, "any," + TRASH), empty_ok=False, refusable=True)
        try:
            rows = _consistent(session, query, totals, page_max_bytes, listing_max_bytes, progress)
        except Refused:
            pass
        else:
            if sum(1 for row in rows if row.status == TRASH) == probe[0]:
                return rows, INCLUDE_STATUS
    present = _consistent(
        session,
        _snapshot_query(("status", "any"), empty_ok=True, refusable=False),
        totals,
        page_max_bytes,
        listing_max_bytes,
        progress,
    )
    try:
        trashed = _consistent(
            session,
            _snapshot_query(("status", TRASH), empty_ok=True, refusable=True),
            totals,
            page_max_bytes,
            listing_max_bytes,
        )
    except Refused:
        raise _End("trash_unlisted") from None
    if any(row.status != TRASH for row in trashed):
        raise _End("trash_unlisted")  # the store ignored `status=trash`: the trash can't be listed
    merged = {row.wc_id: row for row in present}
    merged.update((row.wc_id, row) for row in trashed)  # moved to the trash between the two listings
    if not merged:
        raise _End("no_products")
    return [merged[wc_id] for wc_id in sorted(merged)], TWO_LISTINGS


def read_snapshot(
    client: WooClient,
    *,
    spacing_ms: int,
    stop: Stop,
    failures: FailureCount,
    progress: Progress | None = None,
    monotonic: Callable[[], float] = time.monotonic,
    now: Callable[[], datetime] = utc_now,
    store_seconds: float = STORE_SECONDS,
    page_max_bytes: int = PAGE_MAX_BYTES,
    listing_max_bytes: int = LISTING_MAX_BYTES,
) -> SnapshotRead:
    """Every product of one store, trash included, and every variable product's variations (SYNC-03, SYNC-04; the
    section text says how). Never raises for anything the store answers."""
    session = _session(
        client,
        spacing_ms=spacing_ms,
        stop=stop,
        failures=failures,
        monotonic=monotonic,
        now=now,
        store_seconds=store_seconds,
    )
    totals = _Totals()
    wc_version: str | None = None
    try:
        wc_version = _check_version(session)
        products, listing = _snapshot_products(session, totals, page_max_bytes, listing_max_bytes, progress)
        variable = [product.wc_id for product in products if product.type == "variable"]
        if len(variable) > VARIABLE_MAX:
            raise _End("too_many_variable")
        variations: list[tuple[int, tuple[Product, ...]]] = []
        for wc_id in variable:
            query = Query(
                variations_path(wc_id),
                variation_params,
                lambda body: parse_page(body, kind="variation"),
                VARIATION_PAGES,
                empty_ok=True,
            )
            rows = _consistent(session, query, totals, page_max_bytes, listing_max_bytes)
            variations.append((wc_id, tuple(rows)))
    except _End as end:
        return SnapshotRead(
            end.reason,
            pages=totals.pages,
            http_status=session.last_failure_status,
            wc_version=wc_version,
            requests=session.requests,
            auto_paused=session.auto_paused,
            bad_field=end.field,
            bad_page=end.page,
        )
    return SnapshotRead(
        None,
        tuple(products),
        tuple(variations),
        listing,
        totals.pages,
        session.last_failure_status,
        wc_version,
        session.requests,
    )


def log_incremental(code: str, result: CatalogRead, changed: int) -> None:
    level = logging.INFO if result.ok else logging.WARNING
    _log.log(
        level,
        "Store %s incremental read: %s (pages %d, rows %d, changed %d, last failure HTTP %s%s)%s",
        code,
        result.reason or "ok",
        result.pages,
        len(result.products),
        changed,
        result.http_status,
        describe_bad(result),
        "; the store's sync is now auto-paused" if result.auto_paused else "",
    )


def log_snapshot(code: str, night: str, attempt: int, result: SnapshotRead) -> None:
    level = logging.INFO if result.ok else logging.WARNING
    _log.log(
        level,
        "Store %s snapshot of %s, attempt %d: %s (listing %s, pages %d, products %d, trashed %d, variable %d, "
        "last failure HTTP %s%s)%s",
        code,
        night,
        attempt,
        result.reason or "ok",
        result.listing or "none",
        result.pages,
        len(result.products),
        result.trashed,
        len(result.variations),
        result.http_status,
        describe_bad(result),
        "; the store's sync is now auto-paused" if result.auto_paused else "",
    )

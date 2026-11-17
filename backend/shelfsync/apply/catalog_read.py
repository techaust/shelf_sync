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
  page), the attempt number, the outcome (`ok`, `past_the_end` or the fixed reason), the HTTP status, the time it took,
  the body bytes, whether the answer's headers had arrived, and the `ResponseFacts` when `facts` is given.
- **`facts`**, a `FactsTransport`, is the transport the caller builds its `WooClient` on. `WooClient` wraps it in
  `GetOnlyTransport`, so it sees each answer's headers **before** `GetOnlyTransport` drops `Set-Cookie`: it keeps only
  fixed words from them (`response_facts`), never a value, and hands the answer on unchanged. The cookie drop stays as
  it is, so no cookie is kept, parsed or sent back.
- **`meta=False`** asks for the products without `meta_data` (no `latest_version` data, no error); **`per_page`**
  (25 to 100) and **`max_pages`** (at most 4,000 rows in all, as with 40 pages of 100) change the listing's pages.
"""

import html
import json
import logging
import re
import time
from collections.abc import Callable
from dataclasses import dataclass, field
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


# ---- L1's diagnostics (t9): fixed words about each answer and each attempt, never a value ---------------------------

SERVER_WORDS = ("cloudflare", "nginx", "apache", "litespeed", "openresty")  # else `other`, or `none` when absent
CACHE_WORDS = ("hit", "miss", "dynamic", "bypass", "expired")  # `cf-cache-status`; else `other`, or `none`
COOKIE_WORDS = (
    "__cf_bm",
    "cf_clearance",
    "_cfuvid",
    "PHPSESSID",
    "wordpress_logged_in",
    "wordpress_sec",
    "wp-settings",
)
# WordPress names these with a suffix (`wordpress_logged_in_<hash of the site address>`, `wp-settings-1`,
# `wp-settings-time-1`): the family's word is kept, never the suffix (it would identify the store).
_COOKIE_FAMILIES = (("wordpress_logged_in", "_"), ("wordpress_sec", "_"), ("wp-settings", "-"))
_COOKIE_EXACT = frozenset({"__cf_bm", "cf_clearance", "_cfuvid", "PHPSESSID"})
_SERVER_TOKEN = re.compile(r"[^/\s(,;]*")


@dataclass(frozen=True)
class ResponseFacts:
    """What one answer's headers say, in fixed words only: `cf-ray` present, the `server` header's product
    (`SERVER_WORDS`, `other` or `none`), `cf-cache-status` (`CACHE_WORDS`, `other` or `none`), the names of the
    cookies the store set that are in `COOKIE_WORDS` (each once, in that order), and how many others it set."""

    cf_ray: bool
    server: str
    cache: str
    cookies: tuple[str, ...]
    other_cookies: int


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


def response_facts(headers: httpx.Headers) -> ResponseFacts:
    """The facts of one answer's headers, `Set-Cookie` and `Set-Cookie2` included (so this must see them before
    `GetOnlyTransport` drops them). Nothing from a header is kept but a fixed word or a count."""
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
    )


class FactsTransport(httpx.BaseTransport):
    """L1's transport (t9): the caller builds its `WooClient` on it, and `WooClient` wraps it in `GetOnlyTransport`
    (`GetOnlyTransport(FactsTransport(real))`). So each answer comes through here first, with its headers and before
    `GetOnlyTransport` drops its cookies: this keeps `response_facts` of it and hands the answer on unchanged (the
    body isn't read here). It never sees a request but a GET (`GetOnlyTransport` refuses any other before calling
    it). `take` returns the facts of the last answer, once."""

    def __init__(self, inner: httpx.BaseTransport) -> None:
        self._inner = inner
        self._last: ResponseFacts | None = None

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        self._last = None
        response = self._inner.handle_request(request)
        self._last = response_facts(response.headers)
        return response

    def seen(self) -> bool:
        """Whether an answer's headers came through since the last request started."""
        return self._last is not None

    def take(self) -> ResponseFacts | None:
        last, self._last = self._last, None
        return last

    def close(self) -> None:
        self._inner.close()


@dataclass(frozen=True)
class Attempt:
    """One attempt (the first try or a retry), for L1's trace. `what` is `system_status` or `products` (`page` its
    number); `attempt` 1 to 4; `outcome` `ok` (an answer the reader takes), `past_the_end` (a 400 on page 2 or later)
    or the fixed reason; `http_status` when an answer arrived. `headers`: True when the answer's headers arrived,
    False when nothing came, None when that isn't known (a connection that failed with no `facts` transport).
    `body_bytes`: the body read (for a timeout, what came before it ended), None when not known. `facts` when the read
    has a `FactsTransport` and an answer arrived."""

    what: str
    page: int | None
    attempt: int
    outcome: str
    http_status: int | None
    elapsed_ms: int
    body_bytes: int | None
    headers: bool | None
    facts: ResponseFacts | None = None


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

    def _note_answer(self, page: int | None, attempt: int, started: float, outcome: str, response: WooResponse) -> None:
        """An answer came (headers and body): hand the attempt to `observe`, when there is one."""
        if (observe := self._observe) is not None:
            self._emit(observe, page, attempt, started, outcome, response.status, len(response.body), True)

    def _note_refused(self, page: int | None, attempt: int, started: float, refused: ReadRefused) -> None:
        """No usable answer: hand the attempt to `observe`, when there is one. A timeout says whether the headers had
        arrived (`ReadRefused.headers_status`) and the bytes read before it ended; a redirect, and an over-long or
        unreadable body (`bad_response`), are refused only once the headers are in; for a failed connection it is
        known only through the `facts` transport (it saw an answer or it didn't), else None."""
        if (observe := self._observe) is None:
            return
        status = refused.status if refused.status is not None else refused.headers_status
        body_bytes: int | None = None
        headers: bool | None
        if refused.reason == "timeout":
            headers, body_bytes = refused.headers_status is not None, refused.received
        elif refused.reason in ("redirected", "bad_response"):
            headers = True
        else:
            headers = None if self._facts is None else self._facts.seen()
        self._emit(observe, page, attempt, started, refused.reason, status, body_bytes, headers)

    def _emit(
        self,
        observe: Observe,
        page: int | None,
        attempt: int,
        started: float,
        outcome: str,
        status: int | None,
        body_bytes: int | None,
        headers: bool | None,
    ) -> None:
        observe(
            Attempt(
                what="products" if page is not None else "system_status",
                page=page,
                attempt=attempt + 1,
                outcome=outcome,
                http_status=status,
                elapsed_ms=max(0, round((self._monotonic() - started) * 1000)),
                body_bytes=body_bytes,
                headers=headers,
                facts=self._facts.take() if self._facts is not None else None,
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
    ) -> WooResponse:
        """One request with its retries. Only a GET is ever sent or retried: any other method is refused here,
        before anything is sent (and `GetOnlyTransport` refuses one too). With `page` (a products page's number), a
        200 is returned as it is (the caller parses it, and a body that isn't a JSON list is its `bad_response`);
        otherwise a 200 that isn't JSON is `not_woocommerce`, as in Test connection. With `past_the_end` (pages 2 and
        later), a 400 is returned as it is too, neither a success nor a failure: WooCommerce's answer to a page past
        the last one, which the caller treats as the listing having shrunk while it was read (m3.1 review 2; not
        verified on a store). Each attempt goes to `observe` when there is one, before anything else is done with it."""
        if method != "GET":
            raise NonGetRefused("only GET requests are sent or retried")
        delay = self._spacing if self._sent else 0.0
        attempt = 0
        while True:
            self._pause(delay)
            if self._stop.is_set():
                raise _End("stopped")
            if self._monotonic() >= self._deadline:
                raise _End("timeout")
            self._sent = True
            self.requests += 1
            headers: httpx.Headers | None = None
            started = self._monotonic() if self._observe is not None else 0.0
            try:
                response = self._client.get(path, params, self._deadline, max_bytes=max_bytes)
            except ReadRefused as refused:
                reason = refused.reason
                status = refused.status
                self._note_refused(page, attempt, started, refused)
            else:
                if past_the_end and response.status == 400:
                    self._note_answer(page, attempt, started, "past_the_end", response)
                    return response
                answered = None if page is not None and response.status == 200 else classify(response)
                self._note_answer(page, attempt, started, answered or "ok", response)
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
) -> CatalogRead:
    """Read one store's catalog (the module text says how). Never raises for anything the store answers.
    `observe`, `facts`, `meta`, `per_page` and `max_pages` are L1's (t9; the module text): the app leaves them as
    they are. A `per_page` outside 25 to 100, or a `max_pages` below 1 or past 4,000 rows, is a `ValueError` before
    anything is sent."""
    shape = _Shape(per_page, max_pages, meta)
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
    )
    wc_version: str | None = None
    state = _Listing()
    try:
        wc_version = _check_version(session)
        for _attempt in range(2):
            state = _Listing()
            _read_listing(session, state, shape, page_max_bytes, listing_max_bytes, progress)
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


def describe_bad(result: CatalogRead) -> str:
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
class _Shape:
    """The listing's pages: `per_page` rows each, at most `max_pages`, with or without `meta_data` (L1's options;
    the app's are 100, 40 and with)."""

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

    def add_page(self, session: _Session, page: int, body: bytes, listing_max_bytes: int, shape: _Shape) -> None:
        self.pages = page
        self.largest = max(self.largest, len(body))
        self.size += len(body)
        if self.size > listing_max_bytes:
            session.bad("listing_bytes", page)
        try:
            rows = parse_page(body, per_page=shape.per_page, meta=shape.meta)
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
    shape: _Shape,
    page_max_bytes: int,
    listing_max_bytes: int,
    progress: Progress | None,
) -> None:
    first = session.request("GET", PRODUCTS_PATH, shape.params(1), page_max_bytes, page=1)
    listing.total = _count(session, first.headers, "x-wp-total")
    pages = _count(session, first.headers, "x-wp-totalpages")
    if pages > shape.max_pages:
        raise _End("too_many_pages")
    listing.add_page(session, 1, first.body, listing_max_bytes, shape)
    if listing.total == 0 and not listing.rows:
        raise _End("no_products")
    if progress is not None:
        progress(1, max(pages, 1), len(listing.rows))
    for page in range(2, pages + 1):
        response = session.request(
            "GET", PRODUCTS_PATH, shape.params(page), page_max_bytes, page=page, past_the_end=True
        )
        if response.status == 400:
            return  # the pages ran out early: the count check reads the listing once more
        listing.add_page(session, page, response.body, listing_max_bytes, shape)
        if progress is not None:
            progress(page, pages, len(listing.rows))


def parse_page(body: bytes, *, per_page: int = PER_PAGE, meta: bool = True) -> list[Product]:
    """One products page: a JSON list of at most `per_page` products (100 in the app). `BadAnswer` for anything
    else. With `meta=False` (L1's option), `meta_data` isn't read: the products have no `latest_version` data."""
    try:
        data = json.loads(body.decode("utf-8"))
    except ValueError, RecursionError:  # UnicodeDecodeError and JSONDecodeError are ValueErrors; a deep nest recurses
        raise BadAnswer("json") from None
    if not isinstance(data, list) or len(data) > per_page:
        raise BadAnswer("page")
    return [parse_product(raw, meta=meta) for raw in data]


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


def parse_product(raw: Any, *, meta: bool = True) -> Product:
    """One product, with the limits of `catalog/model.py`. `BadAnswer` names the field (never its value). With
    `meta=False` (L1's option), `meta_data` is neither read nor checked: no `latest_version` data, no error."""
    if not isinstance(raw, dict):
        raise BadAnswer("row")
    wc_id = raw.get("id")
    if type(wc_id) is not int or not 1 <= wc_id <= WC_ID_MAX:
        raise BadAnswer("id")
    slug = _text(raw, "slug", SLUG_MAX)
    raw_title = _text(raw, "name", TITLE_MAX)
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
        type=_word(raw, "type"),
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

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
- **Failures in a row:** every failed attempt is counted and a success resets the count (`FailureCount`, which the
  runner keeps in `sync_state` across runs); at 10 the store is auto-paused and the read ends.
- **The count check:** the rows read must equal page 1's `X-WP-Total`, with no id seen twice and the ids ascending
  across the pages. If not, the whole listing is read once more; if it still doesn't match, `count_mismatch`.
- **Bounds:** 10 minutes for one store's whole read (`timeout`); 8 MiB per page (`PAGE_MAX_BYTES`) and 64 MiB per
  listing (`LISTING_MAX_BYTES`), both Lead (proposed); the field limits of `catalog/model.py`. A hostile answer ends
  the read with `bad_response`: a page that isn't a JSON list, more than 100 rows on a page, a row without an integer
  `id`, a wrong type, an over-long field, a text with a NUL or a lone surrogate, a download or meta list whose stored
  JSON would pass its limit, or a bad `X-WP-Total` / `X-WP-TotalPages`. The result names the failing field (a fixed
  identifier from this code, never a value) and the page. A failed or stopped read returns no products: the caller
  saves nothing.
- **Stop:** the read stops between requests and during every wait when asked (`stopped`).
- **Logs:** one line per store per read: its code, the outcome, pages, rows, the HTTP status of the last failure, and
  for `bad_response` the field and page. Never an address, key, cookie, query string, header or body.
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
from typing import Any, Protocol

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
WC_ID_MAX = 2**63 - 1

# Retried, whatever the status; `blocked` only when it came as a 503 (a 403 firewall page isn't retried).
RETRIED_REASONS = frozenset({"rate_limited", "cloudflare_52x", "server_error", "timeout", "unreachable"})

# The outcomes this module adds to woocommerce.py's reasons (fixed words; the screens' text is in docs/13).
READ_REASONS = frozenset({"too_many_pages", "count_mismatch", "no_products", "auto_paused", "stopped"})

_WORD = re.compile(r"[a-z0-9_-]{1,40}")
_GMT = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}")
_COUNT = re.compile(r"[0-9]{1,9}")


def listing_params(page: int) -> dict[str, str]:
    """The query of one products page (contract-tested)."""
    return {
        "downloadable": "true",
        "status": "any",
        "orderby": "id",
        "order": "asc",
        "per_page": str(PER_PAGE),
        "page": str(page),
        "_fields": LISTING_FIELDS,
    }


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
    ) -> None:
        self._client = client
        self._spacing = spacing_seconds
        self._stop = stop
        self._failures = failures
        self._monotonic = monotonic
        self._now = now
        self._deadline = deadline
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

    def request(
        self, method: str, path: str, params: dict[str, str], max_bytes: int, *, page: bool = False
    ) -> WooResponse:
        """One request with its retries. Only a GET is ever sent or retried: any other method is refused here,
        before anything is sent (and `GetOnlyTransport` refuses one too). With `page`, a 200 is returned as it is (the
        caller parses it, and a body that isn't a JSON list is its `bad_response`); otherwise a 200 that isn't JSON is
        `not_woocommerce`, as in Test connection."""
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
            try:
                response = self._client.get(path, params, self._deadline, max_bytes=max_bytes)
            except ReadRefused as refused:
                reason = refused.reason
                status = refused.status
            else:
                answered = None if page and response.status == 200 else classify(response)
                if answered is None:
                    self._failures.succeeded()
                    return response
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
) -> CatalogRead:
    """Read one store's catalog (the module text says how). Never raises for anything the store answers."""
    session = _Session(
        client,
        spacing_seconds=spacing_ms / 1000,
        stop=stop,
        failures=failures,
        monotonic=monotonic,
        now=now,
        deadline=monotonic() + store_seconds,
    )
    wc_version: str | None = None
    state = _Listing()
    try:
        wc_version = _check_version(session)
        for _attempt in range(2):
            state = _Listing()
            _read_listing(session, state, page_max_bytes, listing_max_bytes, progress)
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
    response = session.request("GET", SYSTEM_STATUS_PATH, {"_fields": "environment"}, 1024 * 1024)
    data = _json(response.body)
    environment = data.get("environment") if isinstance(data, dict) else None
    if not isinstance(environment, dict):
        raise _End("bad_response", "environment")
    version = _clean_version(environment.get("version"))
    parsed = _version_tuple(version) if version else None
    if version is None or parsed is None:
        raise _End("bad_response", "version")
    if parsed < MIN_WC_VERSION:
        raise _End("wc_too_old")
    return version


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

    def add_page(self, page: int, body: bytes, listing_max_bytes: int) -> None:
        self.pages = page
        self.largest = max(self.largest, len(body))
        self.size += len(body)
        if self.size > listing_max_bytes:
            raise _End("bad_response", "listing_bytes", page)
        try:
            self.rows.extend(parse_page(body))
        except BadAnswer as bad:
            raise _End("bad_response", bad.field, page) from None


def _count(headers: httpx.Headers, name: str) -> int:
    value = headers.get(name)
    if value is None or _COUNT.fullmatch(value) is None:
        raise _End("bad_response", name, 1)
    return int(value)


def _read_listing(
    session: _Session, listing: _Listing, page_max_bytes: int, listing_max_bytes: int, progress: Progress | None
) -> None:
    first = session.request("GET", PRODUCTS_PATH, listing_params(1), page_max_bytes, page=True)
    listing.total = _count(first.headers, "x-wp-total")
    pages = _count(first.headers, "x-wp-totalpages")
    if pages > MAX_PAGES:
        raise _End("too_many_pages")
    listing.add_page(1, first.body, listing_max_bytes)
    if listing.total == 0 and not listing.rows:
        raise _End("no_products")
    if progress is not None:
        progress(1, max(pages, 1), len(listing.rows))
    for page in range(2, pages + 1):
        response = session.request("GET", PRODUCTS_PATH, listing_params(page), page_max_bytes, page=True)
        listing.add_page(page, response.body, listing_max_bytes)
        if progress is not None:
            progress(page, pages, len(listing.rows))


def parse_page(body: bytes) -> list[Product]:
    """One products page: a JSON list of at most 100 products. `BadAnswer` for anything else."""
    try:
        data = json.loads(body.decode("utf-8"))
    except ValueError, RecursionError:  # UnicodeDecodeError and JSONDecodeError are ValueErrors; a deep nest recurses
        raise BadAnswer("json") from None
    if not isinstance(data, list) or len(data) > PER_PAGE:
        raise BadAnswer("page")
    return [parse_product(raw) for raw in data]


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


def parse_product(raw: Any) -> Product:
    """One product, with the limits of `catalog/model.py`. `BadAnswer` names the field (never its value)."""
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
        meta=_meta(raw.get("meta_data")),
        entities=title != raw_title,
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


def _meta(value: Any) -> tuple[tuple[str, str], ...]:
    """Only the entries whose key starts with `latest_version` are kept; every entry must still be an object with a
    text key (the rest of `meta_data` is never stored)."""
    if not isinstance(value, list):
        raise BadAnswer("meta_data")
    kept: list[tuple[str, str]] = []
    for raw in value:
        if not isinstance(raw, dict) or not isinstance(raw.get("key"), str):
            raise BadAnswer("meta_data")
        key: str = raw["key"]
        if not key.startswith(META_PREFIX):
            continue
        if len(key) > META_KEY_MAX or len(kept) >= META_KEPT_MAX:
            raise BadAnswer("meta_data.key")
        kept.append((_clean(key, "meta_data.key"), _text(raw, "value", META_VALUE_MAX, name="meta_data.value")))
    meta = tuple(kept)
    if len(meta_json(meta)) > META_JSON_MAX:
        raise BadAnswer("meta_json")
    return meta

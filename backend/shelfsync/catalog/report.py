"""L1, the dry first read of the live stores (m3.0 §2; CAT-01, CAT-02, CAT-03, CAT-05, APL-12, ERR-02).

    PYTHONPATH=backend uv run python -m shelfsync.catalog.report [--store GF] [--spacing-ms 1000] [--yes]
        [--trace] [--no-meta] [--per-page 25|50|100] [--read-seconds 30..120]

Run by the owner in Windows PowerShell outside the Claude app (04-A V36), only after the owner's go-ahead, with
`Tee-Object` into `.logs\\`. What it does:
- refuses to run while ShelfSync runs (it takes the app's own instance lock, `tray/instance.py`: the per-user
  mutex, and `instance.lock` in the data folder when that file exists), and holds that lock until it ends, so the
  app can't start meanwhile; quit ShelfSync from the tray first;
- reads the data folder's live stores (`SHELFSYNC_DATA_DIR`, or `%LOCALAPPDATA%\\ShelfSync`) from the database opened
  **read-only** (`mode=ro&immutable=1`: with nothing running and no `-wal` file, every commit is in the main file,
  and SQLite then makes no `-wal` or `-shm` file; a `-wal` left by a ShelfSync that didn't close cleanly is refused
  with a message); it never migrates and reads only the `store` table, so an installed app still at schema 2 is
  fine; and their keys from Credential Manager (a read failure stops it, never reads as missing keys);
- prints the requests it will make (paths and parameters, never the address) and waits for Enter (`--yes` skips it);
- reads every active store one after another with the app's reader (`apply/catalog_read.py`: GET only, retries,
  bounds), at least **1,000 ms** between requests (`--spacing-ms`, never lower; a store's own spacing when higher),
  with a failure count kept in memory per store;
- links the stores in memory through the pure functions (`catalog/linking.py`, `slots.py`, `names.py`);
- **saves nothing:** no database write, no file, no app log file; its log lines go to the console only, with the HTTP
  libraries held at the app's quiet levels (`logs.QUIET_LOGGERS`) and every line through the log redaction;
- prints **counts only** (m3.0 §2, "What L1 prints", plus the analyst's additions). No slug, title, address, key or
  file name is printed; the three near-miss pairs of 01-A §2 are reported as found or not, by number;
- prints a timing summary after each store's counts (t9): how its read ended, requests, the median and slowest
  attempt, the largest page, the timeouts by stage and by what ended them, and the request number of the first stall;
  on Ctrl+C, the summary of the attempts made so far in the store being read;
The diagnostics (t9, to tell why a store stalls; one setting at a time, each run with the owner's go-ahead):
- `--trace` prints one line per attempt as it ends: local time, the request number in that store's read, what was
  asked, the try, the outcome, which limit ended a timeout and the stage reached, the error word, the connection, the
  times (headers, first byte, longest gap, the whole attempt, the wait before it), the bytes, and the answer's facts,
  all fixed words and numbers (`apply/catalog_read.py`'s `Attempt`, `Wire` and `ResponseFacts`);
- `--no-meta` asks for the products without `meta_data` (the meta counts then read "not asked");
- `--per-page` 25, 50 or 100 (the default): the pages line up (page p of 100 is pages 4p-3 to 4p of 25), the most
  pages grows so no row is lost to the 4,000 cap, and each store's time limit grows to 600 s x 100 / per page;
- `--read-seconds` 30 (the default, the app's) to 120: the read timeout;
- every attempt is bounded at `ATTEMPT_SECONDS` (120 s, Lead (proposed)), within the store's time limit.
The request list shown at the start is built from the same settings as the read (`ListingShape`, `listing_params`).
Exit code: 0 when every store read worked, 1 when one didn't (or the stores couldn't be read), 2 for a usage error.
"""

import argparse
import logging
import re
import sqlite3
import statistics
import sys
import threading
import time
from collections import Counter, defaultdict
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import TextIO

import httpx

from shelfsync.apply.catalog_read import (
    MAX_ROWS,
    PER_PAGE,
    RETRIES,
    STORE_SECONDS,
    SYSTEM_STATUS_PARAMS,
    Attempt,
    CatalogRead,
    FactsTransport,
    ListingShape,
    MemoryFailureCount,
    ResponseFacts,
    Stop,
    Wire,
    describe_bad,
    read_store_catalog,
)
from shelfsync.apply.woocommerce import (
    PRODUCTS_PATH,
    READ_SECONDS,
    READ_SECONDS_RANGE,
    SYSTEM_STATUS_PATH,
    WooClient,
)
from shelfsync.catalog.linking import KnownLink, Placed, near_misses, plan_links
from shelfsync.catalog.model import META_PREFIX, Product
from shelfsync.catalog.names import (
    TRASHED_SUFFIX,
    is_canonical_slug,
    is_linkable_slug,
    normalise_title,
    wp_suffix_pair,
)
from shelfsync.catalog.slots import StoreDownloads, main_download, plan_item_slots
from shelfsync.clock import utc_now
from shelfsync.logs import QUIET_LOGGERS, redact
from shelfsync.paths import DataPaths, resolve_data_paths
from shelfsync.platform.secrets import SecretStore, SecretStoreError, default_secret_store
from shelfsync.secure.credentials import StoreCredentials
from shelfsync.secure.redact import register_secret
from shelfsync.tray.instance import CombinedInstanceLock, InstanceLock, WindowsFileLock, WindowsInstanceLock

MIN_SPACING_MS = 1000
PER_PAGE_CHOICES = (25, 50, 100)  # so the pages line up across runs (the analyst's finding 7)
ATTEMPT_SECONDS = 120.0  # L1's bound on one attempt, within the store's (Lead (proposed), t9 early check)
# The three near-miss pairs of 01-A §2 (their slugs are public there). Reported by number, found or not.
KNOWN_NEAR_MISSES: tuple[frozenset[str], ...] = (
    frozenset({"jetformbuilder-mailpoet-action-add-on", "jetformbuilder-mailpoet-action-addon"}),
    frozenset({"openpos-woocommerce-point-of-salepos-82-addons", "openpos-woocommerce-point-of-salepos82-addons"}),
    frozenset({"css-igniter-lense-wordpress-theme", "css-igniter-lense-wordpress-theme-2"}),
)
_SHORTCODE = re.compile(r'\[amazon_s3 object="([^"\]]+)"\]')


class ReportError(Exception):
    """Something the owner can fix; the message says what and never holds an address or a key."""


@dataclass(frozen=True)
class StoreRef:
    id: int
    code: str
    url: str
    spacing_ms: int
    main_button: str
    state: str


TransportFactory = Callable[[StoreRef], httpx.BaseTransport]


@dataclass(frozen=True)
class Settings:
    """What one L1 run reads with: the spacing, the listing's shape, each store's time limit, the read timeout, the
    bound on one attempt, whether each attempt is printed, and the local time zone's name (the trace's times)."""

    spacing_ms: int
    shape: ListingShape
    store_seconds: float
    read_seconds: int
    attempt_seconds: float
    trace: bool
    zone: str


def settings_from(args: argparse.Namespace, zone: str) -> Settings:
    """The run's settings from its arguments: below 100 a page, the most pages grows to the 4,000-row cap and each
    store's time limit to 600 s x 100 / per page (the lead's decision). `zone` is the local time zone's name."""
    per_page: int = args.per_page
    return Settings(
        spacing_ms=args.spacing_ms,
        shape=ListingShape(per_page, MAX_ROWS // per_page, not args.no_meta),
        store_seconds=STORE_SECONDS * PER_PAGE / per_page,
        read_seconds=args.read_seconds,
        attempt_seconds=ATTEMPT_SECONDS,
        trace=args.trace,
        zone=zone,
    )


def read_stores(database: Path) -> list[StoreRef]:
    """The live stores, from the database opened read-only (no migration, the `store` table only). The caller holds
    the app's instance lock, so ShelfSync isn't running: with no `-wal` file every commit is in the main file, and
    `immutable=1` keeps SQLite from making a `-wal` or `-shm` file (`mode=ro` alone makes both and leaves them).
    A `-wal` file means a ShelfSync that didn't close cleanly: refused, since `immutable=1` would read past its
    commits (Lead (proposed), m3.1 review 1)."""
    if not database.is_file():
        raise ReportError("ShelfSync's database isn't in the data folder. Start ShelfSync once and add the stores.")
    if database.with_name(database.name + "-wal").exists():
        raise ReportError(
            "ShelfSync didn't close cleanly last time, so its database has changes not yet merged. Start ShelfSync, "
            "quit it from the tray, then run this again."
        )
    uri = database.resolve().as_uri() + "?mode=ro&immutable=1"
    try:
        connection = sqlite3.connect(uri, uri=True)
    except sqlite3.Error as error:
        raise ReportError(f"The database couldn't be opened read-only ({type(error).__name__}).") from None
    try:
        rows = connection.execute(
            "SELECT id, code, url, spacing_ms, main_button, state FROM store WHERE removed_at IS NULL ORDER BY id"
        ).fetchall()
    except sqlite3.Error as error:
        raise ReportError(f"The stores couldn't be read ({type(error).__name__}).") from None
    finally:
        connection.close()
    return [StoreRef(*row) for row in rows]


# ---- what is printed ------------------------------------------------------------------------------------------------


def _query(params: dict[str, str]) -> str:
    return "&".join(f"{name}={value}" for name, value in params.items())


def plan_lines(stores: Sequence[StoreRef], settings: Settings) -> list[str]:
    """The settings in effect and the requests, built from the reader's own parameters (`SYSTEM_STATUS_PARAMS`, and
    the run's `ListingShape`, whose `params` is `listing_params`), the page shown as `1..N`."""
    shape = settings.shape
    first = shape.params(1)
    params = _query({**first, "page": "1..N"})
    lines = [
        "ShelfSync L1, the dry first read: read-only, nothing is saved. These requests go to each active store, one "
        "store after another:",
        f"Settings: {shape.per_page} products a page, at most {shape.max_pages} pages; fields {first['_fields']}; at "
        f"most {settings.store_seconds:,.0f} s for each store's read and {settings.attempt_seconds:,.0f} s for one "
        f"request, each plus up to the read timeout after the last byte; read timeout {settings.read_seconds} s; "
        f"times are local, {settings.zone}" + ("; one line per request (--trace)" if settings.trace else ""),
    ]
    for store in stores:
        if store.state != "active":
            lines.append(f"Store {store.code}: skipped (paused in Settings)")
            continue
        lines += [
            f"Store {store.code}, at least {max(store.spacing_ms, settings.spacing_ms):,} ms between requests:",
            f"  GET {SYSTEM_STATUS_PATH}?{_query(SYSTEM_STATUS_PARAMS)}",
            f"  GET {PRODUCTS_PATH}?{params}",
        ]
    lines.append(
        f"N is page 1's X-WP-TotalPages (at most {shape.max_pages}). A request answered 429, 5xx or 520-527, or that "
        "timed out, is tried again up to 3 times. GET only; the keys are sent in a header, never in an address."
    )
    return lines


def _bases(product: Product) -> list[str]:
    """Each download's file name without `.zip`, for a shortcode link (other forms give none)."""
    bases = []
    for download in product.downloads:
        match = _SHORTCODE.fullmatch(download.file.strip())
        if match is not None:
            bases.append(match.group(1).rsplit("/", 1)[-1].removesuffix(".zip"))
    return bases


def _stem_matches(suffix: str, bases: Sequence[str]) -> bool:
    """`latest_version_<x>`'s `<x>` matches a file stem (Lead (proposed), correction 5): the file name without `.zip`
    is `<x>`, or `<x>-` and a version starting with a digit."""
    return any(
        base == suffix or (base.startswith(suffix + "-") and base[len(suffix) + 1 : len(suffix) + 2].isdigit())
        for base in bases
    )


def store_lines(store: StoreRef, result: CatalogRead, meta: bool = True) -> list[str]:
    """One store's counts (or why its read failed). Counts and fixed words only. Without `meta` (`--no-meta`) the
    meta counts read "not asked", never 0."""
    head = f"Store {store.code}"
    if not result.ok:
        status = f", HTTP {result.http_status}" if result.http_status is not None else ""
        lines = [f"{head}: FAILED, {result.reason}{status}{describe_bad(result)}"]
        lines.append(f"  requests sent {result.requests}, products pages read {result.pages}")
        if result.auto_paused:
            lines.append("  10 failed requests in a row: the app would auto-pause this store")
        return lines
    products = result.products
    downloads = [download for product in products for download in product.downloads]
    named = by_single = no_main = unslotted = 0
    for product in products:
        index, single = main_download(product.downloads, store.main_button)
        named += index is not None and not single
        by_single += single
        no_main += index is None and bool(product.downloads)
        alone = StoreDownloads(store.id, product.downloads, store.main_button)
        unslotted += plan_item_slots([alone], []).counts[store.id].unslotted
    plain = matched = unmatched = 0
    for product in products:
        bases = _bases(product)
        for key, _ in product.meta:
            if key == META_PREFIX:
                plain += 1
            elif key.startswith(META_PREFIX + "_"):
                if _stem_matches(key[len(META_PREFIX) + 1 :], bases):
                    matched += 1
                else:
                    unmatched += 1
    statuses = Counter(product.status for product in products)
    types = Counter(product.type for product in products)
    counts = Counter(min(len(product.downloads), 2) for product in products)
    shortcodes = sum(_SHORTCODE.fullmatch(download.file.strip()) is not None for download in downloads)
    return [
        f"{head}: WooCommerce {result.wc_version}",
        f"  rows read {len(products):,}, X-WP-Total {result.total:,}" if result.total is not None else "",
        f"  products pages {result.pages}, largest page {result.largest_page_bytes:,} bytes, "
        f"requests {result.requests}",
        "  statuses: " + ", ".join(f"{word} {count:,}" for word, count in sorted(statuses.items())),
        "  types: " + ", ".join(f"{word} {count:,}" for word, count in sorted(types.items())),
        f"  products with 0 downloads {counts[0]:,}, 1 download {counts[1]:,}, 2 or more {counts[2]:,}",
        f"  main download named like the store's main button {named:,}; found by the one-download rule "
        f"{by_single:,}; none found {no_main:,}",
        f"  downloads in no slot (a name repeated on one product) {unslotted:,}",
        f"  download links: shortcode {shortcodes:,}, other {len(downloads) - shortcodes:,}",
        f"  meta latest_version {plain:,}; latest_version_<x> matching a file stem {matched:,}, matching none "
        f"{unmatched:,}; skipped as unusable {sum(product.meta_skipped for product in products):,}"
        if meta
        else "  meta not asked (--no-meta)",
        f"  titles with HTML entities {sum(product.entities for product in products):,}",
        f"  slugs outside the canonical pattern {sum(not is_canonical_slug(p.slug) for p in products):,}, of them "
        f"empty {sum(not p.slug for p in products):,} and trashed {_trashed(products):,}",
        f"  duplicates (Lead (proposed)): the same normalised title again {_same_title_again(products):,}; a slug "
        f"with its -N form {_suffix_forms(products):,}",
    ]


def _trashed(products: Sequence[Product]) -> int:
    return sum(product.slug.endswith(TRASHED_SUFFIX) for product in products)


def _same_title_again(products: Sequence[Product]) -> int:
    titles = Counter(normalise_title(product.title) for product in products)
    return sum(count - 1 for title, count in titles.items() if title and count > 1)


def _suffix_forms(products: Sequence[Product]) -> int:
    slugs = {product.slug for product in products if is_linkable_slug(product.slug)}
    return sum(1 for slug in slugs if (base := slug.rsplit("-", 1)[0]) in slugs and wp_suffix_pair(base, slug))


def cross_lines(reports: Sequence[tuple[StoreRef, CatalogRead]]) -> list[str]:
    """Across the stores whose read worked, linked in memory with the app's own rules."""
    done = [(store, result) for store, result in reports if result.ok]
    if len(done) < 2:
        return ["Across stores: needs two stores read without a failure."]
    known: list[KnownLink] = []
    taken: set[str] = set()
    next_id = 1
    item_of: dict[tuple[int, int], int] = {}
    for store, result in done:
        by_id = {product.wc_id: product for product in result.products}
        plan = plan_links(store.id, result.products, known, taken)
        new_ids = []
        for new_item in plan.new_items:
            new_ids.append(next_id)
            next_id += 1
            if new_item.canonical_slug is not None:
                taken.add(new_item.canonical_slug)
        for link in plan.links:
            item = link.item_id if link.item_id is not None else new_ids[link.new_item or 0]
            item_of[(store.id, link.wc_id)] = item
            known.append(KnownLink(item, store.id, link.wc_id, by_id[link.wc_id].slug, True))
    stores_of: dict[int, set[int]] = defaultdict(set)
    per_store: Counter[tuple[int, int]] = Counter()
    for (store_id, _), item in item_of.items():
        stores_of[item].add(store_id)
        per_store[(item, store_id)] += 1
    every = {store.id for store, _ in done}
    slug_stores: dict[str, set[int]] = defaultdict(set)
    slug_titles: dict[str, set[str]] = defaultdict(set)
    placed: list[Placed] = []
    for store, result in done:
        for product in result.products:
            placed.append(
                Placed(item_of[(store.id, product.wc_id)], store.id, product.wc_id, product.slug, product.title)
            )
            if is_linkable_slug(product.slug):
                slug_stores[product.slug].add(store.id)
                slug_titles[product.slug].add(normalise_title(product.title))
    pairs = near_misses(placed)
    found = [frozenset({pair.first.slug, pair.second.slug}) for pair in pairs]
    known_found = ", ".join(
        f"pair {n} {'yes' if known_pair in found else 'no'}" for n, known_pair in enumerate(KNOWN_NEAR_MISSES, 1)
    )
    shared = [slug for slug, stores in slug_stores.items() if len(stores) > 1]
    return [
        f"Across {len(done)} stores:",
        f"  slugs on every store {sum(stores == every for stores in slug_stores.values()):,}, on one store only "
        f"{sum(len(stores) == 1 for stores in slug_stores.values()):,}",
        f"  the same slug with a different title {sum(len(slug_titles[slug]) > 1 for slug in shared):,}",
        f"  items {len(stores_of):,}, linked on every store {sum(stores == every for stores in stores_of.values()):,}",
        f"  items that would have two present products on one store {sum(count > 1 for count in per_store.values()):,}",
        f"  near-miss pairs {len(pairs):,}; the three of 01-A section 2: {known_found}",
    ]


# ---- the diagnostics (t9): fixed words and numbers only -------------------------------------------------------------


def _ms(label: str, value: int | None) -> str:
    return f"{label} {value:,} ms" if value is not None else f"{label} none"


def _yes(value: bool) -> str:
    return "yes" if value else "no"


def _connection(wire: Wire | None) -> str:
    """`new connection`, `connection reused`, or `connection unknown` when no trace event came (so neither is known)."""
    if wire is None or (wire.stage is None and not wire.new_connection):
        return "connection unknown"
    return "new connection" if wire.new_connection else "connection reused"


def _bytes(received: int | None, declared: int | None) -> str:
    if received is None:
        return "bytes unknown"
    return f"{received:,} of {declared:,} bytes" if declared is not None else f"{received:,} bytes, no length given"


def facts_text(facts: ResponseFacts | None) -> str:
    """The answer's facts, words from `apply/catalog_read.py`'s fixed lists and counts only."""
    if facts is None:
        return "no answer"
    cookies = " ".join(facts.cookies) if facts.cookies else "none"
    hints = " ".join(facts.hints) if facts.hints else "none"
    return (
        f"server {facts.server}, cf-ray {_yes(facts.cf_ray)}, cf-cache {facts.cache}, content {facts.content}, "
        f"cf-mitigated {_yes(facts.cf_mitigated)}, retry-after {_yes(facts.retry_after)}, "
        f"hints {hints}, cookies {cookies}, other cookies {facts.other_cookies}"
    )


def trace_line(code: str, number: int, attempt: Attempt, local: datetime) -> str:
    """One attempt, as `--trace` prints it: the local time (`HH:MM:SS`), the store's code, the request number in its
    read, what was asked, the try, the outcome and status, which limit ended a timeout, the stage reached and the error
    word, then the connection, the times, the bytes and the facts. Nothing from a response but fixed words and
    numbers."""
    wire = attempt.wire
    what = "system_status" if attempt.page is None else f"products page {attempt.page}"
    status = f" HTTP {attempt.http_status}" if attempt.http_status is not None else ""
    how = [f"ended {attempt.ended}"] if attempt.ended is not None else []
    how.append(f"stage {wire.stage if wire is not None and wire.stage is not None else 'unknown'}")
    if wire is not None and wire.error is not None:
        how.append(f"error {wire.error}")
    details = [
        _connection(wire),
        _ms("headers", wire.headers_ms if wire is not None else None),
        _ms("first byte", wire.first_byte_ms if wire is not None else None),
        _ms("longest gap", wire.longest_gap_ms if wire is not None else None),
        _bytes(attempt.body_bytes, wire.declared_bytes if wire is not None else None),
        f"took {attempt.elapsed_ms / 1000:,.1f} s",
        f"waited {attempt.waited_ms:,} ms",
    ]
    return (
        f"{local:%H:%M:%S} {code} #{number} {what} try {attempt.attempt}: {attempt.outcome}{status} "
        f"({', '.join(how)}); {', '.join(details)}; {facts_text(attempt.facts)}"
    )


def _counts(counter: Counter[str]) -> str:
    return ", ".join(f"{word} {count:,}" for word, count in sorted(counter.items())) or "none"


def read_ended(attempts: Sequence[Attempt], result: CatalogRead | None) -> str:
    """How a store's read ended, for its summary: `ok`, the `CatalogRead` reason, `stopped by Ctrl+C` (no result),
    and for a `timeout` that the reader's own bound checks raised between requests (the wait before a request, or the
    deadline check before one, never seen by `observe`; review 1) the words "between requests at the store's bound".
    A timeout that ended the read itself is the last attempt's: its fourth try, or the one that auto-paused the
    store."""
    if result is None:
        return "stopped by Ctrl+C"
    if result.reason is None:
        return "ok"
    if result.reason != "timeout":
        return result.reason
    last = attempts[-1] if attempts else None
    if last is not None and last.outcome == "timeout" and (last.attempt > RETRIES or result.auto_paused):
        return "timeout"
    return "timeout, between requests at the store's bound"


def timing_lines(code: str, attempts: Sequence[Attempt], result: CatalogRead | None) -> list[str]:
    """One store's timing summary: how its read ended (`read_ended`), requests, the median and slowest attempt, the
    largest products answer, the timeouts (after the headers or not, by the stage reached and by what ended them), and
    the request number of the first stall. `result` is None when Ctrl+C stopped the read: the summary is of the
    attempts made so far."""
    ended = read_ended(attempts, result)
    if not attempts:
        return [f"Timing, store {code}: read {ended}; no requests sent"]
    times = [attempt.elapsed_ms for attempt in attempts]
    pages = [attempt.body_bytes or 0 for attempt in attempts if attempt.page is not None and attempt.outcome == "ok"]
    timeouts = [attempt for attempt in attempts if attempt.outcome == "timeout"]
    first = next((number for number, attempt in enumerate(attempts, 1) if attempt.outcome == "timeout"), None)
    after_headers = sum(attempt.headers is True for attempt in timeouts)
    stages = Counter(
        attempt.wire.stage if attempt.wire is not None and attempt.wire.stage is not None else "unknown"
        for attempt in timeouts
    )
    ends = Counter(attempt.ended or "unknown" for attempt in timeouts)
    return [
        f"Timing, store {code}: read {ended}; requests {len(attempts):,}, median "
        f"{statistics.median(times) / 1000:,.1f} s, slowest {max(times) / 1000:,.1f} s; largest page "
        f"{max(pages, default=0):,} bytes",
        f"  timeouts {len(timeouts):,}: after the headers {after_headers:,}, before them or not known "
        f"{len(timeouts) - after_headers:,}; first stall at request {first if first is not None else 'none'}",
        f"  timeouts by stage: {_counts(stages)}; by what ended them: {_counts(ends)}",
    ]


# ---- the command ----------------------------------------------------------------------------------------------------


class _Redacted(logging.Filter):
    """Every console line through the app's log redaction (a store key registered when it was read is masked)."""

    def filter(self, record: logging.LogRecord) -> bool:
        record.msg = redact(record.getMessage())
        record.args = ()
        return True


def _spacing(value: str) -> int:
    try:
        number = int(value)
    except ValueError:
        raise argparse.ArgumentTypeError("a whole number of milliseconds") from None
    if number < MIN_SPACING_MS:
        raise argparse.ArgumentTypeError(f"at least {MIN_SPACING_MS} ms between requests to a live store")
    return number


def _read_seconds(value: str) -> int:
    low, high = (int(bound) for bound in READ_SECONDS_RANGE)
    try:
        number = int(value)
    except ValueError:
        raise argparse.ArgumentTypeError("a whole number of seconds") from None
    if not low <= number <= high:
        raise argparse.ArgumentTypeError(f"{low} to {high} seconds")
    return number


def parse_args(argv: Sequence[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="python -m shelfsync.catalog.report",
        description="L1: read every active store's catalog, read-only, and print counts only. Nothing is saved.",
    )
    parser.add_argument("--store", metavar="CODE", help="read only the store with this two-letter code")
    parser.add_argument(
        "--spacing-ms",
        type=_spacing,
        default=MIN_SPACING_MS,
        help=f"milliseconds between two requests to a store (at least {MIN_SPACING_MS}, the default)",
    )
    parser.add_argument("--yes", action="store_true", help="start without waiting for Enter")
    parser.add_argument(
        "--trace", action="store_true", help="print one line per request: its stages, times, bytes and fixed-word facts"
    )
    parser.add_argument(
        "--no-meta", action="store_true", help="ask for the products without meta_data (no latest_version counts)"
    )
    parser.add_argument(
        "--per-page",
        type=int,
        choices=PER_PAGE_CHOICES,
        default=PER_PAGE,
        help=f"products a page: 25, 50 or {PER_PAGE} (the default); below {PER_PAGE} the store's time limit grows",
    )
    parser.add_argument(
        "--read-seconds",
        type=_read_seconds,
        default=int(READ_SECONDS),
        help=f"the read timeout in seconds, {int(READ_SECONDS)} (the default, the app's) to "
        f"{int(READ_SECONDS_RANGE[1])}",
    )
    return parser.parse_args(argv)


def main(
    argv: Sequence[str] | None = None,
    *,
    secrets_factory: Callable[[], SecretStore] = default_secret_store,
    transport_factory: TransportFactory | None = None,
    confirm: Callable[[str], str] = input,
    out: TextIO | None = None,
    err: TextIO | None = None,
    make_stop: Callable[[], Stop] = threading.Event,
    monotonic: Callable[[], float] = time.monotonic,
    now: Callable[[], datetime] = utc_now,
    instance_lock: Callable[[DataPaths], InstanceLock] | None = None,
) -> int:
    args = parse_args(argv)
    stdout = out if out is not None else sys.stdout
    stderr = err if err is not None else sys.stderr

    def say(text: str, stream: TextIO = stdout) -> None:
        if text:
            stream.write(text + "\n")
            stream.flush()

    handler = logging.StreamHandler(stderr)
    handler.setFormatter(logging.Formatter("%(message)s"))
    handler.addFilter(_Redacted())
    root = logging.getLogger()
    root.addHandler(handler)
    root.setLevel(logging.INFO)
    for name, level in QUIET_LOGGERS.items():
        logging.getLogger(name).setLevel(level)
    try:
        paths = resolve_data_paths()
        if not paths.database.is_file():
            raise ReportError("ShelfSync's database isn't in the data folder. Start ShelfSync once and add the stores.")
        lock = _nothing_runs(paths, instance_lock or app_instance_lock)
        try:
            return _run(
                args, paths, secrets_factory, transport_factory, confirm, say, stderr, make_stop, monotonic, now
            )
        finally:
            lock.release()
    except ReportError as error:
        say(str(error), stderr)
        return 1
    except SecretStoreError as error:
        say(f"Credential Manager couldn't be read ({type(error).__name__}). Nothing more was done.", stderr)
        return 1
    except KeyboardInterrupt:
        say("Stopped. Nothing was saved.", stderr)
        return 1
    finally:
        root.removeHandler(handler)


def app_instance_lock(paths: DataPaths) -> InstanceLock:
    """The running app's own lock (`tray/instance.py`, what a second launch uses to find the running copy): the
    per-user mutex, and `instance.lock` in the data folder when that file exists (it is opened, never made). Off
    Windows the mutex refuses to be built (`OSError`)."""
    mutex = WindowsInstanceLock()
    if paths.instance_lock.is_file():
        return CombinedInstanceLock(mutex, WindowsFileLock(paths.instance_lock))
    return mutex


def _nothing_runs(paths: DataPaths, make_lock: Callable[[DataPaths], InstanceLock]) -> InstanceLock:
    """Take the app's instance lock, or refuse: ShelfSync is running (or whether it is can't be told). The caller
    holds it to the end, so the app can't start meanwhile."""
    try:
        lock = make_lock(paths)
        taken = lock.acquire()
    except OSError as error:
        raise ReportError(
            f"Couldn't tell whether ShelfSync is running ({type(error).__name__}). Nothing was read."
        ) from None
    if not taken:
        raise ReportError(
            "ShelfSync is running. Quit it first (right-click its icon in the taskbar's notification area, then "
            "Quit), then run this again. Nothing was read."
        )
    return lock


def _run(
    args: argparse.Namespace,
    paths: DataPaths,
    secrets_factory: Callable[[], SecretStore],
    transport_factory: TransportFactory | None,
    confirm: Callable[[str], str],
    say: Callable[..., None],
    stderr: TextIO,
    make_stop: Callable[[], Stop],
    monotonic: Callable[[], float],
    now: Callable[[], datetime],
) -> int:
    stores = read_stores(paths.database)
    if args.store is not None:
        stores = [store for store in stores if store.code == args.store]
        if not stores:
            say(f"No live store has the code {args.store!r}.", stderr)
            return 2
    if not stores:
        say("There are no stores to read.", stderr)
        return 1
    settings = settings_from(args, now().astimezone().tzname() or "zone unknown")
    for line in plan_lines(stores, settings):
        say(line)
    if not args.yes:
        confirm("Press Enter to start, or Ctrl+C to stop: ")
    credentials = StoreCredentials(secrets_factory())
    stop = make_stop()
    reports: list[tuple[StoreRef, CatalogRead]] = []
    for store in stores:
        if store.state != "active":
            continue
        key, secret = credentials.read(store.id)  # a Credential Manager failure stops the command
        if key is None or secret is None:
            say(f"Store {store.code}: FAILED, keys_missing (no key pair saved in Credential Manager)")
            reports.append((store, CatalogRead("keys_missing")))
            continue
        register_secret(key)
        register_secret(secret)
        attempts: list[Attempt] = []
        try:
            result = _read_one(store, key, secret, settings, attempts, transport_factory, say, stop, monotonic, now)
        except KeyboardInterrupt:
            for line in timing_lines(store.code, attempts, None):  # what was gathered before Ctrl+C (review 1)
                say(line)
            raise
        reports.append((store, result))
        for line in [*store_lines(store, result, settings.shape.meta), *timing_lines(store.code, attempts, result)]:
            say(line)
    for line in cross_lines(reports):
        say(line)
    return 0 if reports and all(result.ok for _, result in reports) else 1


def _read_one(
    store: StoreRef,
    key: str,
    secret: str,
    settings: Settings,
    attempts: list[Attempt],
    transport_factory: TransportFactory | None,
    say: Callable[..., None],
    stop: Stop,
    monotonic: Callable[[], float],
    now: Callable[[], datetime],
) -> CatalogRead:
    """One store's read with the run's settings, through a `FactsTransport` (on the real transport, or a test's), every
    attempt kept in `attempts` and, with `--trace`, printed as it ends (local time)."""

    def observe(attempt: Attempt) -> None:
        attempts.append(attempt)
        if settings.trace:
            say(trace_line(store.code, len(attempts), attempt, now().astimezone()))

    inner = transport_factory(store) if transport_factory is not None else httpx.HTTPTransport()
    facts = FactsTransport(inner, monotonic=monotonic)
    shape = settings.shape
    try:
        client = WooClient(
            store.url, key, secret, transport=facts, monotonic=monotonic, read_seconds=settings.read_seconds
        )
    except Exception:
        facts.close()  # WooClient refused its arguments (an address that isn't https): the transport isn't left open
        raise
    with client:
        return read_store_catalog(
            client,
            store.code,
            spacing_ms=max(store.spacing_ms, settings.spacing_ms),
            stop=stop,
            failures=MemoryFailureCount(),
            monotonic=monotonic,
            now=now,
            store_seconds=settings.store_seconds,
            observe=observe,
            facts=facts,
            meta=shape.meta,
            per_page=shape.per_page,
            max_pages=shape.max_pages,
            attempt_seconds=settings.attempt_seconds,
        )


if __name__ == "__main__":
    sys.exit(main())

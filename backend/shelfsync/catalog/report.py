"""L1, the dry first read of the live stores (m3.0 §2; CAT-01, CAT-02, CAT-03, CAT-05, APL-12, ERR-02).

    PYTHONPATH=backend uv run python -m shelfsync.catalog.report [--store GF] [--spacing-ms 1000] [--yes]

Run by the owner in Windows PowerShell outside the Claude app (04-A V36), only after the owner's go-ahead, with
`Tee-Object` into `.logs\\`. What it does:
- reads the data folder's live stores (`SHELFSYNC_DATA_DIR`, or `%LOCALAPPDATA%\\ShelfSync`) from the database opened
  **read-only** (a `mode=ro` URI; it never migrates and reads only the `store` table, so an installed app still at
  schema 2 is fine), and their keys from Credential Manager;
- prints the requests it will make (paths and parameters, never the address) and waits for Enter (`--yes` skips it);
- reads every active store one after another with the app's reader (`apply/catalog_read.py`: GET only, retries,
  bounds), at least **1,000 ms** between requests (`--spacing-ms`, never lower; a store's own spacing when higher),
  with a failure count kept in memory per store;
- links the stores in memory through the pure functions (`catalog/linking.py`, `slots.py`, `names.py`);
- **saves nothing:** no database write, no file, no app log file; its log lines go to the console only, with the HTTP
  libraries held at the app's quiet levels (`logs.QUIET_LOGGERS`) and every line through the log redaction;
- prints **counts only** (m3.0 §2, "What L1 prints", plus the analyst's additions). No slug, title, address, key or
  file name is printed; the three near-miss pairs of 01-A §2 are reported as found or not, by number.
Exit code: 0 when every store read worked, 1 when one didn't (or the stores couldn't be read), 2 for a usage error.
"""

import argparse
import logging
import re
import sqlite3
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
    LISTING_FIELDS,
    MAX_PAGES,
    PER_PAGE,
    CatalogRead,
    MemoryFailureCount,
    Stop,
    describe_bad,
    read_store_catalog,
)
from shelfsync.apply.woocommerce import PRODUCTS_PATH, SYSTEM_STATUS_PATH, WooClient
from shelfsync.catalog.linking import KnownLink, Placed, near_misses, plan_links
from shelfsync.catalog.model import META_PREFIX, Product
from shelfsync.catalog.names import TRASHED_SUFFIX, is_canonical_slug, is_linkable_slug, normalise_title
from shelfsync.catalog.slots import main_download, plan_slots
from shelfsync.clock import utc_now
from shelfsync.logs import QUIET_LOGGERS, redact
from shelfsync.paths import resolve_data_paths
from shelfsync.platform.secrets import SecretStore, SecretStoreError, default_secret_store
from shelfsync.secure.credentials import StoreCredentials

MIN_SPACING_MS = 1000
# The three near-miss pairs of 01-A §2 (their slugs are public there). Reported by number, found or not.
KNOWN_NEAR_MISSES: tuple[frozenset[str], ...] = (
    frozenset({"jetformbuilder-mailpoet-action-add-on", "jetformbuilder-mailpoet-action-addon"}),
    frozenset({"openpos-woocommerce-point-of-salepos-82-addons", "openpos-woocommerce-point-of-salepos82-addons"}),
    frozenset({"css-igniter-lense-wordpress-theme", "css-igniter-lense-wordpress-theme-2"}),
)
_SHORTCODE = re.compile(r'\[amazon_s3 object="([^"\]]+)"\]')
_WP_SUFFIX = re.compile(r"(.+)-(?:[2-9]|[1-9][0-9]+)")


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


def read_stores(database: Path) -> list[StoreRef]:
    """The live stores, from the database opened read-only (no migration, the `store` table only).

    `mode=ro` alone would make SQLite create the `-wal` and `-shm` files of a WAL database that has none and leave
    them behind. With no `-wal` beside it, the app isn't running and everything is in the main file, so `immutable=1`
    is added and nothing is created (Lead (proposed)); while the app runs, its `-wal` exists and a plain `mode=ro` read
    sees its latest commits."""
    if not database.is_file():
        raise ReportError("ShelfSync's database isn't in the data folder. Start ShelfSync once and add the stores.")
    wal = database.with_name(database.name + "-wal")
    uri = database.resolve().as_uri() + ("?mode=ro" if wal.exists() else "?mode=ro&immutable=1")
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


def plan_lines(stores: Sequence[StoreRef], spacing_ms: int) -> list[str]:
    params = f"downloadable=true&status=any&orderby=id&order=asc&per_page={PER_PAGE}&page=1..N&_fields={LISTING_FIELDS}"
    lines = [
        "ShelfSync L1, the dry first read: read-only, nothing is saved. These requests go to each active store, one "
        "store after another:"
    ]
    for store in stores:
        if store.state != "active":
            lines.append(f"Store {store.code}: skipped (paused in Settings)")
            continue
        lines += [
            f"Store {store.code}, at least {max(store.spacing_ms, spacing_ms):,} ms between requests:",
            f"  GET {SYSTEM_STATUS_PATH}?_fields=environment",
            f"  GET {PRODUCTS_PATH}?{params}",
        ]
    lines.append(
        f"N is page 1's X-WP-TotalPages (at most {MAX_PAGES}). A request answered 429, 5xx or 520-527, or that timed "
        "out, is tried again up to 3 times. GET only; the keys are sent in a header, never in an address."
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


def store_lines(store: StoreRef, result: CatalogRead) -> list[str]:
    """One store's counts (or why its read failed). Counts and fixed words only."""
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
        unslotted += plan_slots(product.downloads, store.main_button, []).unslotted
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
        f"{unmatched:,}",
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
    return sum(1 for slug in slugs if (match := _WP_SUFFIX.fullmatch(slug)) is not None and match.group(1) in slugs)


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
        return _run(args, secrets_factory, transport_factory, confirm, say, stderr, make_stop, monotonic, now)
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


def _run(
    args: argparse.Namespace,
    secrets_factory: Callable[[], SecretStore],
    transport_factory: TransportFactory | None,
    confirm: Callable[[str], str],
    say: Callable[..., None],
    stderr: TextIO,
    make_stop: Callable[[], Stop],
    monotonic: Callable[[], float],
    now: Callable[[], datetime],
) -> int:
    stores = read_stores(resolve_data_paths().database)
    if args.store is not None:
        stores = [store for store in stores if store.code == args.store]
        if not stores:
            say(f"No live store has the code {args.store!r}.", stderr)
            return 2
    if not stores:
        say("There are no stores to read.", stderr)
        return 1
    for line in plan_lines(stores, args.spacing_ms):
        say(line)
    if not args.yes:
        confirm("Press Enter to start, or Ctrl+C to stop: ")
    credentials = StoreCredentials(secrets_factory())
    stop = make_stop()
    reports: list[tuple[StoreRef, CatalogRead]] = []
    for store in stores:
        if store.state != "active":
            continue
        pair = credentials.pair(store.id)
        if pair is None:
            say(f"Store {store.code}: FAILED, keys_missing (no key pair saved in Credential Manager)")
            reports.append((store, CatalogRead("keys_missing")))
            continue
        transport = transport_factory(store) if transport_factory is not None else None
        with WooClient(
            store.url, pair.consumer_key, pair.consumer_secret, transport=transport, monotonic=monotonic
        ) as client:
            result = read_store_catalog(
                client,
                store.code,
                spacing_ms=max(store.spacing_ms, args.spacing_ms),
                stop=stop,
                failures=MemoryFailureCount(),
                monotonic=monotonic,
                now=now,
            )
        reports.append((store, result))
        for line in store_lines(store, result):
            say(line)
    for line in cross_lines(reports):
        say(line)
    return 0 if reports and all(result.ok for _, result in reports) else 1


if __name__ == "__main__":
    sys.exit(main())

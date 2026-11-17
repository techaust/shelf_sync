"""Helpers for the catalog tests (m3.1): products as a store's REST answer has them (WooCommerce REST docs: the
`products` list with `_fields=id,slug,name,type,status,date_modified_gmt,downloads,meta_data`), a fake store that pages
them, a fake time with a stop, and a database with stores in it. RFC 2606 host names and made-up titles only."""

import json
import math
import shutil
import sqlite3
import tempfile
import threading
import uuid
import weakref
from collections.abc import Callable
from contextlib import closing
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import httpx

from shelfsync.catalog.model import Download, Product
from shelfsync.catalog.service import CatalogService, store_clients
from shelfsync.clock import to_iso
from shelfsync.db.connection import connect
from shelfsync.db.migrate import migrate
from shelfsync.db.stores import insert_store
from shelfsync.platform.secrets import MemorySecretStore
from shelfsync.secure.credentials import StoreCredentials
from tests.store_support import KEY, PRODUCTS, SECRET, SYSTEM_STATUS, system_status, unread

# The three near-miss pairs of 01-A section 2 (their slugs are public there); the titles are made up.
NEAR_MISS_PAIRS: list[tuple[str, str, str]] = [
    ("jetformbuilder-mailpoet-action-add-on", "jetformbuilder-mailpoet-action-addon", "Form Mailer Add-on"),
    (
        "openpos-woocommerce-point-of-salepos-82-addons",
        "openpos-woocommerce-point-of-salepos82-addons",
        "Point Of Sale Addons",
    ),
    ("css-igniter-lense-wordpress-theme", "css-igniter-lense-wordpress-theme-2", "Lense Theme"),
]


def download(name: str = "Download", key: str = "plugin-1.0.zip", download_id: str | None = None) -> dict[str, str]:
    return {
        "id": download_id if download_id is not None else uuid.uuid5(uuid.NAMESPACE_URL, name + key).hex,
        "name": name,
        "file": f'[amazon_s3 object="{key}"]',
    }


def raw_product(
    wc_id: int,
    slug: str | None = None,
    title: str | None = None,
    *,
    downloads: list[dict[str, str]] | None = None,
    meta: list[dict[str, Any]] | None = None,
    status: str = "publish",
    product_type: str = "simple",
    modified: str | None = "2026-10-25T10:00:00",
) -> dict[str, Any]:
    """One row as `GET /products?_fields=...` answers it."""
    return {
        "id": wc_id,
        "slug": slug if slug is not None else f"product-{wc_id}",
        "name": title if title is not None else f"Product {wc_id}",
        "type": product_type,
        "status": status,
        "date_modified_gmt": modified,
        "downloads": downloads if downloads is not None else [download(key=f"product-{wc_id}-1.0.zip")],
        "meta_data": meta if meta is not None else [{"id": 1, "key": "_edit_lock", "value": "x"}],
    }


def product(
    wc_id: int, slug: str | None = None, title: str | None = None, downloads: tuple[Download, ...] | None = None
) -> Product:
    """A checked product (what the reader hands on)."""
    return Product(
        wc_id=wc_id,
        slug=slug if slug is not None else f"product-{wc_id}",
        title=title if title is not None else f"Product {wc_id}",
        type="simple",
        status="publish",
        modified_gmt="2026-10-25T10:00:00",
        downloads=downloads if downloads is not None else (Download(f"d{wc_id}", "Download", f"file-{wc_id}"),),
        meta=(),
    )


class FakeTime:
    """A clock, a wall clock and a stop event that only move when told to. `wait` is the stop's: it records the wait
    and moves the clock, and answers True once `stop_after` waits have happened (or `stop()` was called)."""

    def __init__(self) -> None:
        self.now = 1000.0
        self.waits: list[float] = []
        self.stopped = False
        self.stop_after: int | None = None
        self.on_wait: Callable[[], None] | None = None

    def monotonic(self) -> float:
        return self.now

    def wall(self) -> datetime:
        return datetime(2026, 11, 17, 12, 0, tzinfo=UTC) + timedelta(seconds=self.now - 1000.0)

    def is_set(self) -> bool:
        return self.stopped

    def wait(self, timeout: float | None = None) -> bool:
        self.waits.append(timeout or 0.0)
        self.now += timeout or 0.0
        if self.on_wait is not None:
            self.on_wait()
        if self.stop_after is not None and len(self.waits) >= self.stop_after:
            self.stopped = True
        return self.stopped

    def stop(self) -> None:
        self.stopped = True

    def set(self) -> None:  # `threading.Event`'s name, so the runner can stop it
        self.stopped = True


Answer = Callable[[httpx.Request], httpx.Response] | httpx.Response


@dataclass
class FakeCatalogStore:
    """A WooCommerce store's `system_status` and paged `products` answers, from `rows`. `answers` holds one-off
    answers to give instead, in order, for the products path (a 524, a 429...); `status_answer` replaces
    `system_status`'s; `pages_header` and `total_header` replace the headers' values. Every request is recorded."""

    rows: list[dict[str, Any]] = field(default_factory=list)
    time: FakeTime = field(default_factory=FakeTime)
    answers: list[Answer] = field(default_factory=list)
    status_answer: Answer | None = None
    pages_header: str | None = None
    total_header: str | None = None
    extra_headers: dict[str, str] = field(default_factory=dict)
    requests: list[httpx.Request] = field(default_factory=list)
    before_page: Callable[[int], None] | None = None

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        path = request.url.path
        if path.endswith(SYSTEM_STATUS):
            answer = self.status_answer if self.status_answer is not None else system_status("11.2.1", "7.1.3")
            return unread(answer(request) if callable(answer) else answer)
        if not path.endswith(PRODUCTS):
            return httpx.Response(404, json={"code": "rest_no_route", "message": "x", "data": {"status": 404}})
        if self.answers:
            answer = self.answers.pop(0)
            return unread(answer(request) if callable(answer) else answer)
        page = int(request.url.params.get("page", "1"))
        if self.before_page is not None:
            self.before_page(page)
        per_page = int(request.url.params.get("per_page", "10"))
        body = self.rows[(page - 1) * per_page : page * per_page]
        headers = {
            "X-WP-Total": self.total_header if self.total_header is not None else str(len(self.rows)),
            "X-WP-TotalPages": self.pages_header
            if self.pages_header is not None
            else str(math.ceil(len(self.rows) / per_page)),
            **self.extra_headers,
        }
        return unread(httpx.Response(200, headers=headers, content=json.dumps(body).encode()))

    @property
    def transport(self) -> httpx.MockTransport:
        return httpx.MockTransport(self)

    def product_requests(self) -> list[httpx.Request]:
        return [request for request in self.requests if request.url.path.endswith(PRODUCTS)]


# ---- a database with stores ----------------------------------------------------------------------------------------


@dataclass
class Db:
    """A database file with the migrations applied, opened as the app opens its own (`db/connection.py`: WAL, foreign
    keys, the busy timeout). A file, not shared-cache memory: there a reader and the runner's writer meet table locks
    that don't wait (SQLITE_LOCKED), which the app's WAL file never has."""

    path: Path

    def connect(self) -> sqlite3.Connection:
        return connect(self.path)

    def add_store(
        self, code: str, *, main_button: str = "Download", state: str = "active", spacing_ms: int = 150
    ) -> int:
        with closing(self.connect()) as connection:
            store_id = insert_store(
                connection,
                name=f"Store {code}",
                url=f"https://store-{code.lower()}.example",
                code=code,
                shape="circle",
                color="indigo",
                spacing_ms=spacing_ms,
                main_button=main_button,
                created_at=to_iso(FakeTime().wall()),
            )
            if state != "active":
                connection.execute("UPDATE store SET state = ? WHERE id = ?", (state, store_id))
        return store_id

    def rows(self, sql: str, *args: Any) -> list[tuple[Any, ...]]:
        with closing(self.connect()) as connection:
            return connection.execute(sql, args).fetchall()


def make_db() -> Db:
    """A new database in its own temporary folder, removed (best effort) when the test is done with it."""
    folder = Path(tempfile.mkdtemp(prefix="shelfsync-catalog-"))
    db = Db(folder / "catalog.db")
    with closing(db.connect()) as connection:
        migrate(connection)
    weakref.finalize(db, shutil.rmtree, folder, ignore_errors=True)
    return db


def wait_for(condition: Callable[[], bool], seconds: float = 10.0) -> None:
    """Wait (real time) for a background thread to reach a state."""
    event = threading.Event()
    for _ in range(int(seconds * 100)):
        if condition():
            return
        event.wait(0.01)
    raise AssertionError("the condition was never met")


# ---- several stores behind one transport, and a service wired to them ----------------------------------------------


@dataclass
class Sites:
    """Each fake store answers for its own host (`https://store-<code>.example`); `gate` (when set) holds every answer
    until it is opened, so a test can see a run in progress."""

    stores: dict[str, FakeCatalogStore] = field(default_factory=dict)
    gate: threading.Event | None = None
    requests: list[httpx.Request] = field(default_factory=list)

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        if self.gate is not None:
            self.gate.wait(10.0)
        code = request.url.host.removeprefix("store-").removesuffix(".example").upper()
        return self.stores[code](request)

    def transport(self) -> httpx.BaseTransport:
        return httpx.MockTransport(self)


@dataclass
class CatalogRig:
    db: Db
    sites: Sites
    secrets: MemorySecretStore
    service: CatalogService
    time: FakeTime | None

    def add_store(self, code: str, rows: list[dict[str, Any]], **options: Any) -> int:
        store_id = self.db.add_store(code, **options)
        StoreCredentials(self.secrets).save(store_id, KEY, SECRET)
        self.sites.stores[code] = FakeCatalogStore(rows=rows)
        return store_id

    def run(self) -> None:
        """One full run, to the end."""
        assert self.service.start_sync()
        self.service.runner.join(30.0)
        assert not self.service.runner.state().running


def make_catalog_rig(fake_time: bool = False) -> CatalogRig:
    """A database, fake stores and a `CatalogService`. With `fake_time` the waits, the clocks and the stop are one
    `FakeTime` (no real waiting: for retries and auto-pause); otherwise real time with a real stop (for shutdowns)."""
    db = make_db()
    sites = Sites()
    secrets = MemorySecretStore()
    time = FakeTime() if fake_time else None
    if time is not None:
        clock = time
        service = CatalogService(
            db.connect,
            store_clients(secrets, sites.transport, monotonic=clock.monotonic),
            now=clock.wall,
            monotonic=clock.monotonic,
            make_stop=lambda: clock,
        )
    else:
        service = CatalogService(db.connect, store_clients(secrets, sites.transport))
    return CatalogRig(db, sites, secrets, service, time)

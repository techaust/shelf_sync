"""Helpers for the m3.2 tests: a fake WooCommerce store that honours what the incremental and the snapshot ask for
(WooCommerce REST docs, products list: `modified_after` with `dates_are_gmt`, `status` (default `any`: not trash),
`include_status` (a comma-separated list; takes precedence over `status`), `downloadable`, `orderby=id`, `order=asc`,
`per_page`, `page`, `_fields`; and `GET /products/{id}/variations`). What isn't verified on a store is a switch:
`include_status` honoured, ignored (an older WooCommerce that doesn't know it), refused (`rest_invalid_param`) or
`any_only` (`any,trash` read as `any`); `status=trash` honoured, ignored or refused; whether `modified_after` includes
its boundary. RFC 2606 hosts and made-up names only."""

import json
import math
import re
from collections.abc import Callable
from contextlib import closing
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx

from shelfsync.catalog.runner import RunKind, RunPlan
from shelfsync.catalog.service import CatalogService, store_clients
from shelfsync.db.daily import LocalTime
from shelfsync.platform.secrets import MemorySecretStore
from shelfsync.secure.credentials import StoreCredentials
from shelfsync.store_service import StoreService
from tests.catalog_support import Db, FakeTime, Sites, download, make_db
from tests.store_support import KEY, PRODUCTS, SECRET, SYSTEM_STATUS, system_status, unread, wp_error

_VARIATIONS = re.compile(r".*/wp-json/wc/v3/products/(\d+)/variations")
_ONE = re.compile(r".*/wp-json/wc/v3/products/(\d+)")

UTC_ZONE = LocalTime(
    to_local=lambda moment: moment.replace(tzinfo=None), to_utc=lambda naive: naive.replace(tzinfo=UTC)
)

# A fake New York (as `tests/test_db_daily.py`): UTC-4 before 2026-11-01 06:00 UTC, UTC-5 after (the clocks go back).
FALL = datetime(2026, 11, 1, 6, 0, tzinfo=UTC)
FAKE_NEW_YORK = LocalTime(
    to_local=lambda moment: (moment + timedelta(hours=-4 if moment < FALL else -5)).replace(tzinfo=None),
    to_utc=lambda naive: (
        summer if (summer := (naive + timedelta(hours=4)).replace(tzinfo=UTC)) < FALL else naive + timedelta(hours=5)
    ).replace(tzinfo=UTC),
)
# A fake zone whose clocks go forward: UTC+1 before 2026-03-29 01:00 UTC, UTC+2 after (02:00 local becomes 03:00).
SPRING = datetime(2026, 3, 29, 1, 0, tzinfo=UTC)
FAKE_BERLIN = LocalTime(
    to_local=lambda moment: (moment + timedelta(hours=1 if moment < SPRING else 2)).replace(tzinfo=None),
    to_utc=lambda naive: (
        winter if (winter := (naive - timedelta(hours=1)).replace(tzinfo=UTC)) < SPRING else naive - timedelta(hours=2)
    ).replace(tzinfo=UTC),
)


def row(
    wc_id: int,
    slug: str | None = None,
    *,
    status: str = "publish",
    product_type: str = "simple",
    modified: str | None = "2026-11-10T10:00:00",
    downloads: list[dict[str, str]] | None = None,
    meta: list[dict[str, Any]] | None = None,
    title: str | None = None,
    downloadable: bool = True,
) -> dict[str, Any]:
    """One product as the store holds it (every field the readers may ask for)."""
    return {
        "id": wc_id,
        "slug": slug if slug is not None else f"product-{wc_id}",
        "name": title if title is not None else f"Product {wc_id}",
        "type": product_type,
        "status": status,
        "date_modified_gmt": modified,
        "downloadable": downloadable,
        "downloads": downloads if downloads is not None else [download(key=f"product-{wc_id}-1.0.zip")],
        "meta_data": meta if meta is not None else [{"id": 1, "key": "latest_version", "value": "1.0"}],
    }


def variation(wc_id: int, *, status: str = "publish", key: str | None = None) -> dict[str, Any]:
    return {
        "id": wc_id,
        "status": status,
        "date_modified_gmt": "2026-11-10T10:00:00",
        "downloads": [download(name=f"Edition {wc_id}", key=key or f"variation-{wc_id}.zip")],
        "meta_data": [],
    }


@dataclass
class FakeSyncStore:
    rows: list[dict[str, Any]] = field(default_factory=list)
    variations: dict[int, list[dict[str, Any]]] = field(default_factory=dict)
    include_status: str = "honoured"  # "ignored", "refused", "any_only"
    status_trash: str = "honoured"  # "ignored", "refused"
    boundary_inclusive: bool = False
    time: FakeTime = field(default_factory=FakeTime)
    fail: Callable[[httpx.Request], httpx.Response | None] | None = None
    requests: list[httpx.Request] = field(default_factory=list)
    version: str = "11.3.0"
    unlisted: set[int] = field(default_factory=set)  # ids no listing holds, though `GET /products/{id}` has them

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        if self.fail is not None:
            answer = self.fail(request)
            if answer is not None:
                return unread(answer)
        path = request.url.path
        params = request.url.params
        if path.endswith(SYSTEM_STATUS):
            return unread(system_status(self.version))
        match = _VARIATIONS.fullmatch(path)
        if match is not None:
            selected: list[dict[str, Any]] | httpx.Response = sorted(
                self.variations.get(int(match.group(1)), []), key=lambda item: item["id"]
            )
        elif path.endswith(PRODUCTS):
            selected = self._select(params)
        elif (one := _ONE.fullmatch(path)) is not None:
            return unread(self._one(int(one.group(1)), params.get("_fields")))
        else:
            return unread(wp_error(404, "rest_no_route"))
        if isinstance(selected, httpx.Response):
            return unread(selected)
        per_page = int(params.get("per_page", "10"))
        page = int(params.get("page", "1"))
        fields = params.get("_fields")
        body = selected[(page - 1) * per_page : page * per_page]
        if fields is not None:
            wanted = fields.split(",")
            body = [{key: item[key] for key in wanted if key in item} for item in body]
        headers = {"X-WP-Total": str(len(selected)), "X-WP-TotalPages": str(math.ceil(len(selected) / per_page))}
        return unread(httpx.Response(200, headers=headers, content=json.dumps(body).encode()))

    def _one(self, wc_id: int, fields: str | None) -> httpx.Response:
        """`GET /products/{id}`: the product (a trashed one too: assumed, item 9 records it), else WooCommerce's
        404 `woocommerce_rest_product_invalid_id`."""
        found = [item for item in self.rows if item["id"] == wc_id]
        if not found:
            return wp_error(404, "woocommerce_rest_product_invalid_id")
        body = found[0]
        if fields is not None:
            body = {key: body[key] for key in fields.split(",") if key in body}
        return httpx.Response(200, json=body)

    def _select(self, params: httpx.QueryParams) -> list[dict[str, Any]] | httpx.Response:
        selected = [item for item in self.rows if item["id"] not in self.unlisted]
        if params.get("downloadable") == "true":
            selected = [item for item in selected if item.get("downloadable", True)]
        include = params.get("include_status")
        if include is not None and self.include_status == "refused":
            return wp_error(400, "rest_invalid_param")
        if include is not None and self.include_status != "ignored":
            wanted = set(include.split(","))
            if self.include_status == "any_only" and "any" in wanted:
                wanted.discard("trash")  # `any,trash` read as `any`; `trash` alone still works
            selected = [
                item for item in selected if ("any" in wanted and item["status"] != "trash") or item["status"] in wanted
            ]
        else:
            status = params.get("status", "any")
            if status == "trash" and self.status_trash == "refused":
                return wp_error(400, "rest_invalid_param")
            if status == "trash" and self.status_trash == "ignored":
                status = "any"
            selected = [
                item
                for item in selected
                if (item["status"] != "trash" if status == "any" else item["status"] == status)
            ]
        since = params.get("modified_after")
        if since is not None:
            selected = [
                item
                for item in selected
                if item["date_modified_gmt"] is not None
                and (
                    item["date_modified_gmt"] > since
                    or (self.boundary_inclusive and item["date_modified_gmt"] == since)
                )
            ]
        return sorted(selected, key=lambda item: item["id"])

    @property
    def transport(self) -> httpx.MockTransport:
        return httpx.MockTransport(self)

    def product_requests(self) -> list[httpx.Request]:
        return [request for request in self.requests if request.url.path.endswith(PRODUCTS)]

    def find(self, wc_id: int) -> dict[str, Any]:
        return next(item for item in self.rows if item["id"] == wc_id)


# ---- a database, fake stores and a scheduled service on one fake clock ---------------------------------------------


class SyncTime(FakeTime):
    """`FakeTime` whose wall clock starts at `base` and can be set (`set_wall`, never backwards). Waits move both."""

    def __init__(self, base: datetime) -> None:
        super().__init__()
        self.base = base

    def wall(self) -> datetime:
        return self.base + timedelta(seconds=self.now - 1000.0)

    def set_wall(self, moment: datetime) -> None:
        target = 1000.0 + (moment - self.base).total_seconds()
        if target < self.now:
            raise ValueError("the fake clock never goes back")
        self.now = target


@dataclass
class SyncRig:
    db: Db
    sites: Sites
    secrets: MemorySecretStore
    service: CatalogService
    time: SyncTime
    stores: StoreService
    changes: list[tuple[int, list[Any]]]

    def add_store(self, code: str, rows: list[dict[str, Any]], **options: Any) -> int:
        store_id = self.db.add_store(code, **options)
        StoreCredentials(self.secrets).save(store_id, KEY, SECRET)
        self.sites.stores[code] = FakeSyncStore(rows=rows, time=self.time)  # type: ignore[assignment]
        return store_id

    def store(self, code: str) -> FakeSyncStore:
        found = self.sites.stores[code]
        assert isinstance(found, FakeSyncStore)
        return found

    def run(self, kind: RunKind | None = None) -> RunKind:
        started = self.service.start_sync(kind)
        assert started is not None
        self.service.runner.join(30.0)
        assert not self.service.runner.state().running
        return started

    def tick(self) -> RunPlan | None:
        plan = self.service.scheduler.tick()
        if plan is not None:
            self.service.runner.join(30.0)
            assert not self.service.runner.state().running
        return plan

    def at(self, moment: datetime) -> None:
        self.time.set_wall(moment)

    def rows(self, sql: str, *args: Any) -> list[tuple[Any, ...]]:
        return self.db.rows(sql, *args)

    def set(self, key: str, value_json: str) -> None:
        with closing(self.db.connect()) as connection:
            connection.execute(
                "INSERT INTO setting (key, value_json) VALUES (?, ?) "
                "ON CONFLICT (key) DO UPDATE SET value_json = excluded.value_json",
                (key, value_json),
            )


def make_sync_rig(start: datetime, local: LocalTime = UTC_ZONE) -> SyncRig:
    """A database, fake stores and a `CatalogService` with its scheduler, every wait, clock and stop on one
    `SyncTime` (no real waiting). The scheduler's thread isn't started: a test calls `tick()`."""
    db = make_db()
    sites = Sites()
    secrets = MemorySecretStore()
    clock = SyncTime(start)
    stores = StoreService(open_connection=db.connect, secrets=secrets, transport=httpx.MockTransport(sites))
    changes: list[tuple[int, list[Any]]] = []

    def sink(connection: Any, store_id: int, found: list[Any]) -> None:
        assert connection.in_transaction  # F4: inside the save's transaction
        changes.append((store_id, found))

    service = CatalogService(
        db.connect,
        store_clients(secrets, sites.transport, monotonic=clock.monotonic),
        now=clock.wall,
        monotonic=clock.monotonic,
        make_stop=lambda: clock,
        slots=stores.slots,
        local=local,
        on_changes=sink,
    )
    return SyncRig(db, sites, secrets, service, clock, stores, changes)

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
from dataclasses import dataclass, field
from typing import Any

import httpx

from tests.catalog_support import FakeTime, download
from tests.store_support import PRODUCTS, SYSTEM_STATUS, system_status, unread, wp_error

_VARIATIONS = re.compile(r".*/wp-json/wc/v3/products/(\d+)/variations")


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
) -> dict[str, Any]:
    """One product as the store holds it (every field the readers may ask for)."""
    return {
        "id": wc_id,
        "slug": slug if slug is not None else f"product-{wc_id}",
        "name": title if title is not None else f"Product {wc_id}",
        "type": product_type,
        "status": status,
        "date_modified_gmt": modified,
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

    def _select(self, params: httpx.QueryParams) -> list[dict[str, Any]] | httpx.Response:
        selected = list(self.rows)
        if params.get("downloadable") == "true":
            selected = [item for item in selected if item["downloads"]]
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

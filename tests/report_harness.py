"""Runs `python -m shelfsync.catalog.report` against fake stores, in its own process (tests/test_catalog_report.py
starts it with `python -m tests.report_harness <report arguments>`, `SHELFSYNC_DATA_DIR` set to a test folder).

Fresh process: the report's logging set-up (its console handler, the quiet HTTP loggers) is seen as it is on the owner's
PC, with nothing a test session left behind. No socket is opened: every store is an httpx.MockTransport (RFC 2606
hosts). The products carry marker text (slugs, titles, file names, and the 01-A near-miss slugs) the parent checks
never reaches the output; so do the answers' headers (cookies, `cf-ray`, server, cache) and the trace events' `info`
(the request, its address with a key in the query, and its `Authorization`), for `--trace` (t9)."""

import sys
from typing import Any

import httpx

from shelfsync.catalog import report
from shelfsync.paths import resolve_data_paths
from shelfsync.platform.secrets import MemorySecretStore
from shelfsync.secure.credentials import StoreCredentials
from shelfsync.tray.instance import FakeInstanceLock
from tests.catalog_support import NEAR_MISS_PAIRS, FakeCatalogStore, FakeTime, Sites, download, raw_product
from tests.store_support import KEY, SECRET

MARK = "zq-marker"  # in every slug, title and file name below


def gf_rows() -> list[dict[str, Any]]:
    rows = [
        raw_product(
            1, f"{MARK}-shared", f"{MARK} Shared &amp; Title", downloads=[download("Download", f"{MARK}-a-1.0.zip")]
        ),
        raw_product(
            2,
            f"{MARK}-multi",
            f"{MARK} Multi",
            downloads=[download("Download", f"{MARK}-m-2.0.zip"), download("Docs", f"{MARK}-docs.zip")],
            meta=[
                {"id": 1, "key": "latest_version", "value": "2.0"},
                {"id": 2, "key": f"latest_version_{MARK}-m", "value": "2.0"},
                {"id": 3, "key": "latest_version_stale-thing", "value": "1.0"},
            ],
        ),
        raw_product(3, "", f"{MARK} Draft", status="draft"),
    ]
    rows += [raw_product(10 + n, first, f"{MARK} {title}") for n, (first, _, title) in enumerate(NEAR_MISS_PAIRS)]
    return rows


def pw_rows() -> list[dict[str, Any]]:
    rows = [raw_product(5, f"{MARK}-shared", f"{MARK} Shared & Title", downloads=[download("Get it", f"{MARK}-a.zip")])]
    rows += [raw_product(20 + n, second, f"{MARK} {title}") for n, (_, second, title) in enumerate(NEAR_MISS_PAIRS)]
    return rows


# What a store's answer may carry that L1 must never print (t9): cookie values and a hashed WordPress cookie name, a
# `cf-ray` value, a server and cache text, and origin-hint values. Each holds the marker.
LEAKY_HEADERS = [
    ("Set-Cookie", f"__cf_bm={MARK}-cookie-value; path=/; HttpOnly"),
    ("Set-Cookie", f"wordpress_logged_in_{MARK}hash={MARK}-session; path=/"),
    ("Set-Cookie", f"{MARK}_unlisted=1; path=/"),
    ("CF-RAY", f"{MARK}-ray-LHR"),
    ("Server", f"{MARK}-server/1.0"),
    ("CF-Cache-Status", f"{MARK}-cache"),
    ("X-Cache", f"HIT from {MARK}.example"),
]
TRACE_EVENTS = (
    "connection.connect_tcp.started",
    "connection.connect_tcp.complete",
    "http11.send_request_headers.started",
    "http11.send_request_headers.complete",
    "http11.receive_response_headers.started",
    "http11.receive_response_headers.complete",
    "http11.receive_response_body.started",
    "http11.receive_response_body.complete",
)


def traced(sites: Sites) -> httpx.MockTransport:
    """The fake stores behind httpcore-named trace events whose `info` holds what httpcore's does (the request, with
    its address and `Authorization`), plus an address with a key in its query; every answer gets `LEAKY_HEADERS`."""

    def handler(request: httpx.Request) -> httpx.Response:
        trace = request.extensions.get("trace")
        info = {
            "request": request,
            "url": f"{request.url}?consumer_key={KEY}&consumer_secret={SECRET}",
            "authorization": request.headers.get("Authorization", ""),
        }
        if trace is not None:
            for name in TRACE_EVENTS:
                trace(name, info)
        response = sites(request)
        return httpx.Response(
            response.status_code, headers=[*response.headers.multi_items(), *LEAKY_HEADERS], stream=response.stream
        )

    return httpx.MockTransport(handler)


def main() -> int:
    ids = {store.code: store.id for store in report.read_stores(resolve_data_paths().database)}
    secrets = MemorySecretStore()
    for store_id in ids.values():
        StoreCredentials(secrets).save(store_id, KEY, SECRET)
    sites = Sites({"GF": FakeCatalogStore(rows=gf_rows()), "PW": FakeCatalogStore(rows=pw_rows())})
    clock = FakeTime()
    return report.main(
        sys.argv[1:],
        secrets_factory=lambda: secrets,
        transport_factory=lambda store: traced(sites),
        confirm=lambda prompt: "",
        make_stop=lambda: clock,
        monotonic=clock.monotonic,
        now=clock.wall,
        # A fake of the app's instance lock: the owner's own ShelfSync may be running on this PC, and the
        # real mutex is per Windows user (tested in process with a lock that is taken).
        instance_lock=lambda paths: FakeInstanceLock(),
    )


if __name__ == "__main__":
    sys.exit(main())

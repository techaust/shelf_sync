"""SYNC-01, SYNC-03, SYNC-04, 04-A V3, V28 on the real test site (`-m teststack`, this PC only; m3.2 item 9). Every
connection goes to 127.0.0.1 (`laragon.LoopbackOnlyTransport`). Reads use ShelfSync's own `WooClient` with the site's
**Read** pair; the few writes go through `testenv.seed.SeedClient` with the **Read/Write** pair and are undone by
`seed` at the end of each test that writes (`run_seed`, never `--reset`). Run after `python -m testenv.laragon seed`:

    uv run pytest -m teststack tests/test_teststack_sync.py --no-cov

Each test that finds out how WooCommerce behaves writes the fact (fixed words and numbers, never a key) to
`.logs/m3.2-teststack-facts.jsonl` for 04-A; the tests assert only what ShelfSync's design depends on.
"""

import json
import time
from collections.abc import Iterator
from contextlib import closing
from pathlib import Path
from typing import Any

import pytest

from shelfsync.apply.catalog_read import INCREMENTAL_FIELDS, SNAPSHOT_FIELDS, product_path
from shelfsync.apply.woocommerce import PRODUCTS_PATH, WooClient
from shelfsync.catalog.runner import RunPlan
from shelfsync.catalog.service import CatalogService
from shelfsync.platform.secrets import KeyringSecretStore
from shelfsync.store_service import BusySlots
from testenv import laragon, seed
from testenv.catalog import site_clients
from tests.catalog_support import Db, make_db

pytestmark = pytest.mark.teststack

REPO = Path(__file__).resolve().parents[1]
FACTS = REPO / ".logs" / "m3.2-teststack-facts.jsonl"
SITE = laragon.parse_site(laragon.DEFAULT_SITE)


def record(fact: str, **values: Any) -> None:
    FACTS.parent.mkdir(exist_ok=True)
    with FACTS.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps({"fact": fact, **values}, sort_keys=True) + "\n")


@pytest.fixture
def secrets() -> KeyringSecretStore:
    return KeyringSecretStore(laragon.SERVICE)


@pytest.fixture
def reader(secrets: KeyringSecretStore) -> Iterator[WooClient]:
    pair = laragon.read_pair(secrets, laragon.pairs_for(SITE)[0])
    assert pair is not None, "run `python -m testenv.laragon keys` first"
    context = laragon.tls_context(laragon.default_cert(SITE))
    with WooClient(SITE.url, pair[0], pair[1], transport=laragon.make_transport(context, SITE.host)) as client:
        yield client


@pytest.fixture
def writer(secrets: KeyringSecretStore) -> Iterator[seed.SeedClient]:
    cert = laragon.default_cert(SITE)
    with seed._read_write_client(SITE, cert, secrets, laragon.make_transport) as client:
        yield client
    seed.run_seed(
        SITE,
        cert,
        secrets,
        laragon.DEFAULT_MOTO,
        laragon.DEFAULT_BUCKET,
        laragon.DEFAULT_REGION,
        laragon.make_transport,
    )


def get(client: WooClient, path: str, params: dict[str, str]) -> tuple[Any, Any, int]:
    response = client.get(path, params, time.monotonic() + 60, max_bytes=8 * 1024 * 1024)
    return json.loads(response.body or b"null"), response.headers, response.status


def by_slug(client: WooClient, slug: str) -> dict[str, Any]:
    data, _, _ = get(client, PRODUCTS_PATH, {"slug": slug, "status": "any", "_fields": SNAPSHOT_FIELDS})
    [found] = [row for row in data if row["slug"] == slug]
    return dict(found)


def total(client: WooClient, params: dict[str, str]) -> int:
    _, headers, status = get(client, PRODUCTS_PATH, {**params, "per_page": "1", "_fields": "id"})
    assert status == 200, params
    return int(headers["x-wp-total"])


def service_on(db: Db, secrets: KeyringSecretStore) -> tuple[CatalogService, int]:
    with closing(db.connect()) as connection:
        cursor = connection.execute(
            "INSERT INTO store (name, url, code, shape, color, created_at) VALUES "
            "('Test site', ?, 'TS', 'circle', 'indigo', '2026-11-18T00:00:00.000000Z')",
            (SITE.url,),
        )
        assert cursor.lastrowid is not None
        store_id = cursor.lastrowid
    found: list[Any] = []

    def sink(connection: Any, store: int, changes: list[Any]) -> None:
        found.extend(changes)

    service = CatalogService(
        db.connect, site_clients(SITE, laragon.default_cert(SITE), secrets), slots=BusySlots(), on_changes=sink
    )
    service.found = found  # type: ignore[attr-defined]
    return service, store_id


def run(service: CatalogService, plan: RunPlan) -> None:
    assert service.runner.start(plan)
    service.runner.join(600.0)


# ---- reads only ----------------------------------------------------------------------------------------------------


def test_what_system_status_costs_next_to_an_incremental_page(reader: WooClient) -> None:
    """Review 1's live-store note: `system_status?_fields=environment` runs twice an hour's worth more than the
    listing on incrementals. Times (ms, median of 5, after one warm-up each) and body sizes, for 04-A and §3."""

    def timed(path: str, params: dict[str, str]) -> tuple[int, int]:
        get(reader, path, params)  # warm-up
        samples: list[float] = []
        size = 0
        for _ in range(5):
            started = time.perf_counter()
            body = reader.get(path, params, time.monotonic() + 60, max_bytes=8 * 1024 * 1024).body
            samples.append((time.perf_counter() - started) * 1000)
            size = len(body)
        return round(sorted(samples)[2]), size

    status_ms, status_bytes = timed("/wp-json/wc/v3/system_status", {"_fields": "environment"})
    since = "2099-01-01T00:00:00"  # nothing modified after: an empty incremental page
    page_ms, page_bytes = timed(
        PRODUCTS_PATH,
        {"modified_after": since, "dates_are_gmt": "true", "status": "any", "per_page": "100", "_fields": "id"},
    )
    record(
        "system_status cost",
        system_status_ms=status_ms,
        system_status_bytes=status_bytes,
        empty_incremental_page_ms=page_ms,
        empty_incremental_page_bytes=page_bytes,
    )


def test_v28_include_status_any_trash_counts_the_any_and_the_trash_listings(reader: WooClient) -> None:
    """V28: `include_status=any,trash` is accepted and its total is `status=any`'s plus `status=trash`'s; whether
    `status=trash` is accepted (F9); `downloadable` comes back in `_fields`."""
    both = total(reader, {"include_status": "any,trash"})
    present = total(reader, {"status": "any"})
    _, _, trash_status = get(reader, PRODUCTS_PATH, {"status": "trash", "per_page": "1", "_fields": "id"})
    trashed = total(reader, {"include_status": "trash"})
    record("include_status any,trash total", both=both, status_any=present, include_trash=trashed)
    record("status=trash accepted", http_status=trash_status)
    assert both == present + trashed and trashed >= 1  # old-slider is in the trash
    data, _, _ = get(reader, PRODUCTS_PATH, {"status": "any", "per_page": "5", "_fields": INCREMENTAL_FIELDS})
    flags = sorted({type(row.get("downloadable")).__name__ for row in data})
    record("downloadable in _fields", types=flags)
    assert flags == ["bool"]


def test_get_by_id_for_a_trashed_product_and_an_id_that_was_never_used(reader: WooClient) -> None:
    """F2: what `GET /products/{id}` answers for a trashed id, and for an unknown id (WooCommerce's 404 code)."""
    data, _, _ = get(reader, PRODUCTS_PATH, {"include_status": "trash", "per_page": "100", "_fields": "id,slug,status"})
    [trashed] = [row for row in data if str(row["slug"]).startswith("old-slider")]
    body, _, status = get(reader, product_path(trashed["id"]), {"_fields": "id,status"})
    record("GET a trashed id", http_status=status, status=body.get("status") if isinstance(body, dict) else None)
    unknown, _, missing = get(reader, product_path(2_000_000_000), {"_fields": "id"})
    record("GET an unknown id", http_status=missing, code=unknown.get("code") if isinstance(unknown, dict) else None)
    assert missing == 404 and isinstance(unknown, dict) and unknown.get("code") != "rest_no_route"


def test_modified_after_boundary_and_precision(reader: WooClient) -> None:
    """SYNC-01: whether `modified_after` includes a product modified at exactly that second."""
    aurora = by_slug(reader, "aurora")
    at = aurora["date_modified_gmt"]
    params = {"modified_after": at, "dates_are_gmt": "true", "status": "any", "per_page": "100", "_fields": "id"}
    data, _, _ = get(reader, PRODUCTS_PATH, params)
    record("modified_after includes its boundary", included=aurora["id"] in [row["id"] for row in data], date=at)


def test_the_snapshot_sees_old_slider_as_trashed(secrets: KeyringSecretStore) -> None:
    """SYNC-04 on the site: a full read, then the night's snapshot: `old-slider` is listed, in the trash."""
    db = make_db()
    service, store_id = service_on(db, secrets)
    run(service, RunPlan("full"))
    run(service, RunPlan("snapshot", night="2026-11-18"))
    assert service.runner.state().outcomes == {store_id: None}
    [(listing, trashed)] = db.rows("SELECT listing, trashed FROM snapshot_night")
    record("snapshot listing on the site", listing=listing, trashed=trashed)
    assert trashed >= 1
    assert db.rows("SELECT status FROM snapshot_state WHERE slug LIKE 'old-slider%'") == [("trash",)]


# ---- writes through SeedClient, undone by seed ---------------------------------------------------------------------


def test_v3_a_downloads_put_keeps_each_entrys_id(reader: WooClient, writer: seed.SeedClient) -> None:
    """V3: PUT Northwind's full `downloads` array with each entry's `id`; read it back."""
    northwind = by_slug(reader, "northwind")
    before = northwind["downloads"]
    writer.call("PUT", product_path(northwind["id"]), body={"downloads": before})
    after = by_slug(reader, "northwind")["downloads"]
    kept = [entry["id"] for entry in before] == [entry["id"] for entry in after]
    record("V3 downloads PUT keeps ids", kept=kept, entries=len(before))
    assert kept


def test_which_edits_move_date_modified_gmt(reader: WooClient, writer: seed.SeedClient) -> None:
    """SYNC-01's Accept depends on it: a downloads-only edit, a meta-only edit, a trash and a restore."""
    ember = by_slug(reader, "emberline")
    product = product_path(ember["id"])
    moves: dict[str, bool] = {}
    status_after_restore: str | None = None

    def edit(name: str, body: dict[str, Any] | None = None, method: str = "PUT") -> None:
        before = by_slug_any(reader, ember["id"])["date_modified_gmt"]
        time.sleep(1.1)  # the dates are whole seconds
        writer.call(method, product, body=body)
        moves[name] = by_slug_any(reader, ember["id"])["date_modified_gmt"] != before

    renamed = [{**entry, "name": entry["name"] + " (edit)"} for entry in ember["downloads"]]
    edit("downloads only", {"downloads": renamed})
    edit("meta only", {"meta_data": [{"key": "latest_version", "value": "9.9.9-test"}]})
    edit("trash", None, "DELETE")
    edit("restore from the trash", {"status": "publish"})
    status_after_restore = by_slug_any(reader, ember["id"])["status"]
    record("edits that move date_modified_gmt", restored_status=status_after_restore, **moves)
    assert moves["downloads only"], "a downloads-only edit must move the date, or SYNC-01 misses it"


def by_slug_any(reader: WooClient, wc_id: int) -> dict[str, Any]:
    body, _, status = get(reader, product_path(wc_id), {"_fields": SNAPSHOT_FIELDS})
    assert status == 200
    return dict(body)


def test_an_incremental_sees_an_edit_and_a_snapshot_sees_a_trashing(
    secrets: KeyringSecretStore, reader: WooClient, writer: seed.SeedClient
) -> None:
    """SYNC-01 and SYNC-04 Accept on the site: an edit through SeedClient is seen by the next incremental; a
    product trashed through SeedClient shows as trashed outside ShelfSync after the next snapshot; `seed` then puts
    it back (the `writer` fixture)."""
    db = make_db()
    service, store_id = service_on(db, secrets)
    run(service, RunPlan("full"))
    pixel = by_slug(reader, "pixel-forms")
    time.sleep(1.1)
    renamed = [{**entry, "name": entry["name"] + " (edit)"} for entry in pixel["downloads"]]
    writer.call("PUT", product_path(pixel["id"]), body={"downloads": renamed})
    run(service, RunPlan("incremental"))
    assert service.runner.state().outcomes == {store_id: None}
    found = service.found  # type: ignore[attr-defined]
    assert [(change.kind, change.wc_id) for change in found] == [("changed", pixel["id"])]
    aurora = by_slug(reader, "aurora")
    writer.call("DELETE", product_path(aurora["id"]))  # to the trash
    run(service, RunPlan("snapshot", night="2026-11-18"))
    assert ("trashed", aurora["id"]) in [(change.kind, change.wc_id) for change in found]

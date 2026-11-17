"""CAT-01, CAT-05, 04-A V1 and V27 on the test stack (m3.1 item 7): the catalog runner reads the Laragon test site
through the client seam (`testenv/catalog.py`).

Two kinds of test here:
- **offline** (always run): the seam itself, with the site's certificate made here and a fake WooCommerce behind it;
- **`-m teststack`** (deselected by default, this PC only): the real site `https://shelfsync-test.test`, after
  `python -m testenv.laragon seed`, with the harness's Read pair from Credential Manager (`ShelfSync-TestStack`). It
  checks CAT-01's count against `X-WP-Total`, that `setup-service` (not downloadable, V27) and the trashed
  `old-slider` (V1) aren't read, and the slots of the multi-download sample (Northwind). Every connection goes to
  127.0.0.1 (`laragon.LoopbackOnlyTransport`), so the conftest's outbound guard stays on.
"""

import ssl
from contextlib import closing
from pathlib import Path

import httpx
import pytest

from shelfsync.catalog.service import CatalogService
from shelfsync.platform.secrets import KeyringSecretStore, MemorySecretStore
from testenv import laragon
from testenv.catalog import site_clients
from tests.catalog_support import Db, FakeCatalogStore, make_db, raw_product
from tests.laragon_support import RO_KEY, RO_SECRET, SITE, basic, store_with_keys, write_site_cert

SITE_URL = f"https://{SITE}"


def site_store(db: Db, url: str = SITE_URL) -> int:
    with closing(db.connect()) as connection:
        cursor = connection.execute(
            "INSERT INTO store (name, url, code, shape, color, created_at) VALUES "
            "('Test site', ?, 'TS', 'circle', 'indigo', '2026-11-17T12:00:00.000000Z')",
            (url,),
        )
        assert cursor.lastrowid is not None
        return cursor.lastrowid


def run_once(service: CatalogService) -> None:
    assert service.start_sync()
    service.runner.join(600.0)
    assert not service.runner.state().running


# ---- offline: the seam ---------------------------------------------------------------------------------------------


@pytest.fixture
def cert_file(tmp_path: Path) -> Path:
    return write_site_cert(tmp_path / "trust", laragon.make_site_certificate(SITE))


def test_the_seam_reads_the_site_with_its_read_pair_through_a_new_transport_per_client(cert_file: Path) -> None:
    fake = FakeCatalogStore(rows=[raw_product(1, "aurora")])
    made: list[tuple[ssl.SSLContext, str]] = []

    def transports(context: ssl.SSLContext, host: str) -> httpx.BaseTransport:
        made.append((context, host))
        return httpx.MockTransport(fake)

    db = make_db()
    store_id = site_store(db)
    service = CatalogService(
        db.connect, site_clients(laragon.parse_site(SITE_URL), cert_file, store_with_keys(), transports)
    )
    run_once(service)
    assert service.runner.state().outcomes == {store_id: None}
    assert {request.headers["Authorization"] for request in fake.requests} == {basic(RO_KEY, RO_SECRET)}
    assert [host for _, host in made] == [SITE]  # one transport, for the one client of this run
    assert db.rows("SELECT slug FROM store_product") == [("aurora",)]


def test_the_seam_serves_the_test_site_only(cert_file: Path) -> None:
    db = make_db()
    other = site_store(db, "https://store-a.example")
    calls: list[str] = []

    def transports(context: ssl.SSLContext, host: str) -> httpx.BaseTransport:
        calls.append(host)
        return httpx.MockTransport(lambda request: httpx.Response(500))

    service = CatalogService(
        db.connect, site_clients(laragon.parse_site(SITE_URL), cert_file, store_with_keys(), transports)
    )
    run_once(service)
    assert service.runner.state().outcomes == {other: "internal"} and calls == []


def test_the_seam_needs_the_read_pair(cert_file: Path) -> None:
    with pytest.raises(laragon.HarnessError, match="read-only key pair"):
        site_clients(laragon.parse_site(SITE_URL), cert_file, MemorySecretStore())


# ---- the real test site (-m teststack) -----------------------------------------------------------------------------


@pytest.mark.teststack
def test_the_test_sites_catalog_is_read_and_counted_against_x_wp_total() -> None:
    site = laragon.parse_site(laragon.DEFAULT_SITE)
    secrets = KeyringSecretStore(laragon.SERVICE)
    db = make_db()
    store_id = site_store(db)
    service = CatalogService(db.connect, site_clients(site, laragon.default_cert(site), secrets))
    run_once(service)
    assert service.runner.state().outcomes == {store_id: None}
    [(rows, total, reason)] = db.rows("SELECT read_rows, read_total, read_reason FROM sync_state")
    assert reason is None and rows == total and rows > 0  # CAT-01
    slugs = {slug for (slug,) in db.rows("SELECT slug FROM store_product")}
    assert "setup-service" not in slugs  # V27: not downloadable, so not listed
    assert not {"old-slider", "old-slider__trashed"} & slugs  # V1: status=any leaves the trash out
    assert "lumen-suite" not in slugs  # a variable product isn't downloadable itself
    for expected in ("aurora", "pixel-forms", "northwind", "mosaic-gallery", "mosaic-gallery-bundle", "emberline"):
        assert expected in slugs
    [(item_id,)] = db.rows(
        "SELECT l.catalog_item_id FROM item_link l JOIN store_product p USING (store_id, wc_id) WHERE p.slug = ?",
        "northwind",
    )
    slots = db.rows(
        "SELECT t.name, t.is_main, d.wc_download_id <> '' FROM slot t JOIN slot_download d ON d.slot_id = t.id "
        "WHERE t.catalog_item_id = ? ORDER BY t.is_main DESC, t.id",
        item_id,
    )
    assert slots == [("Download", 1, 1), ("northwind-core-5.0.2.zip", 0, 1)]  # CAT-05: main and extra, with ids


@pytest.mark.teststack
def test_a_second_read_of_the_test_site_keeps_every_id() -> None:
    site = laragon.parse_site(laragon.DEFAULT_SITE)
    db = make_db()
    site_store(db)
    service = CatalogService(
        db.connect, site_clients(site, laragon.default_cert(site), KeyringSecretStore(laragon.SERVICE))
    )
    run_once(service)
    first = db.rows("SELECT * FROM item_link ORDER BY wc_id"), db.rows("SELECT id, catalog_item_id, name FROM slot")
    service = CatalogService(
        db.connect, site_clients(site, laragon.default_cert(site), KeyringSecretStore(laragon.SERVICE))
    )
    run_once(service)
    assert (
        db.rows("SELECT * FROM item_link ORDER BY wc_id"),
        db.rows("SELECT id, catalog_item_id, name FROM slot"),
    ) == first

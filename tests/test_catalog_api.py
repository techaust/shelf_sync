"""CAT-01, CAT-02, CAT-04, CAT-05, APL-12, ERR-02, UI-WIZ: the Sync, Catalog and wizard routes (`api/sync.py`,
`api/catalog.py`, `api/wizard.py`) behind the guard, on fake stores; the run stopped by the app's shutdown; and no
address, key, cookie, query string or body in the log, even with redaction off."""

import threading
from collections.abc import Iterator
from contextlib import closing
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx
import pytest
from fastapi.testclient import TestClient

from shelfsync import logs
from shelfsync.api.app import create_app
from shelfsync.catalog.service import WizardService
from shelfsync.platform.secrets import MemorySecretStore
from shelfsync.secure.token import InstallToken
from shelfsync.store_service import StoreService
from tests.catalog_support import NEAR_MISS_PAIRS, CatalogRig, download, make_catalog_rig, raw_product, wait_for
from tests.store_support import KEY, SECRET, wp_error
from tests.support import WRITE_HEADERS, FakeClock, Harness


@dataclass
class ApiRig:
    rig: CatalogRig
    harness: Harness
    client: TestClient
    storage: dict[str, bool]


def make_api_rig(fake_time: bool = True) -> ApiRig:
    rig = make_catalog_rig(fake_time=fake_time)
    storage = {"ready": False}
    wizard = WizardService(rig.db.connect, lambda: storage["ready"])
    stores = StoreService(open_connection=rig.db.connect, secrets=rig.secrets)
    install = MemorySecretStore()
    clock = FakeClock()
    app = create_app(
        47615, InstallToken(install), clock, ui_dir=None, stores=stores, catalog=rig.service, wizard=wizard
    )
    harness = Harness(app=app, store=install, clock=clock)
    return ApiRig(rig, harness, harness.signed_in_client(), storage)


@pytest.fixture
def api() -> Iterator[ApiRig]:
    rig = make_api_rig()
    yield rig
    rig.rig.service.stop()


def run_sync(api: ApiRig) -> dict[str, Any]:
    response = api.client.post("/api/sync", headers=WRITE_HEADERS)
    assert response.status_code == 202, response.text
    api.rig.service.runner.join(30.0)
    status = api.client.get("/api/sync")
    assert status.status_code == 200
    body: dict[str, Any] = status.json()
    assert body["running"] is False
    return body


# ---- sync ----------------------------------------------------------------------------------------------------------


def test_sync_starts_a_run_and_reports_each_stores_outcome(api: ApiRig) -> None:
    gf = api.rig.add_store("GF", [raw_product(1, "alpha"), raw_product(2, "beta")])
    pw = api.rig.add_store("PW", [], state="active")
    body = run_sync(api)
    by_store = {entry["store_id"]: entry for entry in body["stores"]}
    assert by_store[gf]["this_run"] == "ok" and by_store[gf]["rows"] == 2 and by_store[gf]["total"] == 2
    assert by_store[gf]["last_ok_at"] is not None and by_store[gf]["reason"] is None
    assert by_store[pw]["this_run"] == "no_products" and by_store[pw]["reason"] == "no_products"  # ERR-02
    assert by_store[pw]["auto_paused"] is False and by_store[pw]["failures_in_row"] == 0
    assert body["started_at"] and body["finished_at"] and body["current"] is None


def test_a_store_never_reached_shows_null_this_run(api: ApiRig) -> None:
    api.rig.add_store("GF", [raw_product(1)])
    body = api.client.get("/api/sync").json()
    assert body["running"] is False and body["stores"][0]["this_run"] is None and body["stores"][0]["rows"] is None


def test_a_second_start_while_one_runs_is_409_sync_running() -> None:
    api = make_api_rig(fake_time=False)
    api.rig.add_store("GF", [raw_product(1)], spacing_ms=50)
    gate = threading.Event()
    api.rig.sites.gate = gate
    try:
        assert api.client.post("/api/sync", headers=WRITE_HEADERS).status_code == 202
        second = api.client.post("/api/sync", headers=WRITE_HEADERS)
        assert (second.status_code, second.json()) == (409, {"error": "sync_running"})
        running = api.client.get("/api/sync").json()
        assert running["running"] is True
    finally:
        gate.set()
        api.rig.service.runner.join(30.0)


def test_resume_clears_an_auto_pause_and_an_unknown_store_is_404(api: ApiRig) -> None:
    gf = api.rig.add_store("GF", [raw_product(1)])
    api.rig.sites.stores["GF"].status_answer = httpx.Response(503, json={"code": "x", "message": "y"})
    for _ in range(3):
        run_sync(api)
    entry = api.client.get("/api/sync").json()["stores"][0]
    assert entry["auto_paused"] is True and entry["auto_pause_reason"] == "server_error"
    assert entry["failures_in_row"] == 10 and entry["http_status"] == 503
    assert run_sync(api)["stores"][0]["this_run"] == "auto_paused"
    assert api.client.post(f"/api/sync/stores/{gf}/resume", headers=WRITE_HEADERS).status_code == 204
    entry = api.client.get("/api/sync").json()["stores"][0]
    assert (entry["auto_paused"], entry["failures_in_row"]) == (False, 0)
    missing = api.client.post("/api/sync/stores/99/resume", headers=WRITE_HEADERS)
    assert (missing.status_code, missing.json()) == (404, {"error": "not_found"})


def test_the_writes_need_a_session_and_the_write_headers(api: ApiRig) -> None:
    anonymous = api.harness.client()
    assert anonymous.get("/api/sync").status_code == 401
    assert anonymous.get("/api/catalog").status_code == 401
    assert anonymous.get("/api/wizard").status_code == 401
    assert api.client.post("/api/sync").status_code == 403
    assert api.client.patch("/api/catalog/1", json={"canonical_slug": "a"}).status_code == 403
    assert api.client.put("/api/wizard/test", json={"done": True}).status_code == 403
    assert api.client.post("/api/sync/stores/1/resume").status_code == 403
    assert api.rig.service.runner.state().started_at is None  # nothing started


# ---- the catalog ---------------------------------------------------------------------------------------------------


def test_the_catalog_lists_every_item_with_its_links_and_whether_it_is_on_every_active_store(api: ApiRig) -> None:
    """CAT-02: linked by slug; the 3 near-miss pairs of 01-A stay apart (CAT-03: never linked silently)."""
    gf_rows = [raw_product(1, "shared", "Shared")] + [
        raw_product(10 + i, first, title) for i, (first, _, title) in enumerate(NEAR_MISS_PAIRS)
    ]
    pw_rows = [raw_product(5, "shared", "Shared")] + [
        raw_product(20 + i, second, title) for i, (_, second, title) in enumerate(NEAR_MISS_PAIRS)
    ]
    gf = api.rig.add_store("GF", gf_rows)
    pw = api.rig.add_store("PW", sorted(pw_rows, key=lambda row: row["id"]))
    run_sync(api)
    items = api.client.get("/api/catalog").json()["items"]
    assert len(items) == 7  # 1 shared + 3 + 3
    shared = next(item for item in items if item["canonical_slug"] == "shared")
    assert shared["on_every_active_store"] is True and shared["slot_count"] == 1
    assert [(link["store_id"], link["wc_id"], link["gone"]) for link in shared["links"]] == [
        (gf, 1, False),
        (pw, 5, False),
    ]
    assert sum(item["on_every_active_store"] for item in items) == 1
    assert set(items[0]) == {"id", "canonical_slug", "title", "type", "links", "slot_count", "on_every_active_store"}


def test_a_paused_store_does_not_count_for_on_every_active_store(api: ApiRig) -> None:
    api.rig.add_store("GF", [raw_product(1, "alpha")])
    pw = api.rig.add_store("PW", [raw_product(2, "beta")])
    run_sync(api)
    with closing(api.rig.db.connect()) as connection:
        connection.execute("UPDATE store SET state = 'paused' WHERE id = ?", (pw,))
    items = api.client.get("/api/catalog").json()["items"]
    assert [item["on_every_active_store"] for item in items] == [True, False]


def test_one_item_shows_its_slots_with_each_stores_download_ids(api: ApiRig) -> None:
    """CAT-05: the multi-download products show all their slots with the right IDs."""
    gf = api.rig.add_store("GF", [raw_product(1694, "multi", downloads=[download("Download", "a.zip", "g1")])])
    pw = api.rig.add_store(
        "PW",
        [raw_product(1821, "multi", downloads=[download("Download", "a.zip", "p1"), download("Docs", "d.zip", "p2")])],
    )
    run_sync(api)
    detail = api.client.get("/api/catalog/1")
    assert detail.status_code == 200
    body = detail.json()
    assert body["canonical_slug"] == "multi" and body["created_at"].endswith("Z")
    assert [(slot["name"], slot["is_main"]) for slot in body["slots"]] == [("Download", True), ("Docs", False)]
    assert [[(d["store_id"], d["wc_download_id"]) for d in slot["downloads"]] for slot in body["slots"]] == [
        [(gf, "g1"), (pw, "p1")],
        [(pw, "p2")],
    ]
    assert body["slots"][0]["downloads"][0]["file"] == '[amazon_s3 object="a.zip"]'
    assert api.client.get("/api/catalog/99").json() == {"error": "not_found"}
    assert api.client.get("/api/catalog/0").status_code == 422
    assert api.client.get(f"/api/catalog/{2**63}").status_code == 422


def test_the_slug_edit_valid_invalid_and_taken(api: ApiRig) -> None:
    """CAT-04: lowercase a-z, 0-9 and -, 1 to 200, no leading or trailing -; a slug in use is 409; nothing is sent to
    a store."""
    api.rig.add_store("GF", [raw_product(1, "jupiterx-website-builder"), raw_product(2, "other")])
    run_sync(api)
    sent = len(api.rig.sites.requests)
    edit = api.client.patch("/api/catalog/1", headers=WRITE_HEADERS, json={"canonical_slug": "jupiterx"})
    assert edit.status_code == 200 and edit.json()["canonical_slug"] == "jupiterx"
    assert api.client.get("/api/catalog/1").json()["links"][0]["slug"] == "jupiterx-website-builder"
    for bad in ("", "Jupiter", "-a", "a-", "a b", "a_b", "é", "a" * 201, 5, None):
        response = api.client.patch("/api/catalog/1", headers=WRITE_HEADERS, json={"canonical_slug": bad})
        assert (response.status_code, response.json()) == (422, {"error": "invalid_request"}), bad
    extra = api.client.patch("/api/catalog/1", headers=WRITE_HEADERS, json={"canonical_slug": "a", "title": "x"})
    assert extra.status_code == 422
    assert (
        api.client.patch("/api/catalog/1", headers=WRITE_HEADERS, json={"canonical_slug": "a" * 200}).status_code == 200
    )
    assert api.client.patch("/api/catalog/1", headers=WRITE_HEADERS, json={"canonical_slug": "a--1"}).status_code == 200
    taken = api.client.patch("/api/catalog/2", headers=WRITE_HEADERS, json={"canonical_slug": "a--1"})
    assert (taken.status_code, taken.json()) == (409, {"error": "slug_taken"})
    missing = api.client.patch("/api/catalog/9", headers=WRITE_HEADERS, json={"canonical_slug": "z"})
    assert (missing.status_code, missing.json()) == (404, {"error": "not_found"})
    assert len(api.rig.sites.requests) == sent  # nothing reached a store


# ---- the wizard ----------------------------------------------------------------------------------------------------


def _wizard(api: ApiRig) -> dict[str, Any]:
    response = api.client.get("/api/wizard")
    assert response.status_code == 200
    body: dict[str, Any] = response.json()
    return body


def test_the_wizard_starts_at_its_first_unfinished_step(api: ApiRig) -> None:
    """UI-WIZ: stores and storage from the data, test from the owner's mark, catalog from a full read of every active
    store."""
    fresh = _wizard(api)
    assert fresh["current"] == "stores"
    assert [(s["step"], s["done"], s["from_state"]) for s in fresh["steps"]] == [
        ("stores", False, True),
        ("storage", False, True),
        ("test", False, False),
        ("catalog", False, True),
    ]
    api.rig.add_store("GF", [raw_product(1)])
    assert _wizard(api)["current"] == "storage"
    api.storage["ready"] = True
    assert _wizard(api)["current"] == "test"  # an install from M2 starts here
    marked = api.client.put("/api/wizard/test", headers=WRITE_HEADERS, json={"done": True})
    assert marked.status_code == 200 and marked.json()["current"] == "catalog"
    run_sync(api)
    assert _wizard(api)["current"] is None
    assert api.client.put("/api/wizard/test", headers=WRITE_HEADERS, json={"done": False}).json()["current"] == "test"


def test_a_failed_store_read_keeps_the_wizard_at_the_catalog_step(api: ApiRig) -> None:
    """ERR-02: a store with 0 products: the wizard stays at the catalog step, and `GET /api/sync` says why."""
    api.rig.add_store("GF", [raw_product(1)])
    api.rig.add_store("PW", [])
    api.storage["ready"] = True
    api.client.put("/api/wizard/test", headers=WRITE_HEADERS, json={"done": True})
    body = run_sync(api)
    assert _wizard(api)["current"] == "catalog"
    assert [entry["reason"] for entry in body["stores"]] == [None, "no_products"]


def test_the_wizards_data_steps_cannot_be_marked_and_odd_requests_are_refused(api: ApiRig) -> None:
    for step in ("stores", "storage", "catalog"):
        response = api.client.put(f"/api/wizard/{step}", headers=WRITE_HEADERS, json={"done": True})
        assert (response.status_code, response.json()) == (409, {"error": "wizard_step_from_state"})
    for path, body in (
        ("/api/wizard/teach", {"done": True}),
        ("/api/wizard/test", {"done": "yes"}),
        ("/api/wizard/test", {"done": 1}),
        ("/api/wizard/test", {"done": True, "x": 1}),
        ("/api/wizard/test", {}),
    ):
        response = api.client.put(path, headers=WRITE_HEADERS, json=body)
        assert (response.status_code, response.json()) == (422, {"error": "invalid_request"})


def test_the_finished_mark_ends_the_wizard_whatever_changes_later(api: ApiRig) -> None:
    """Analyst finding 9 (Lead (proposed)): the screen sets `finished` on leaving the catalog step."""
    assert _wizard(api)["finished"] is False
    api.rig.add_store("GF", [raw_product(1)])
    api.storage["ready"] = True
    api.client.put("/api/wizard/test", headers=WRITE_HEADERS, json={"done": True})
    run_sync(api)
    done = api.client.put("/api/wizard/finished", headers=WRITE_HEADERS, json={"done": True})
    assert done.status_code == 200 and done.json()["finished"] is True and done.json()["current"] is None
    api.rig.add_store("PW", [raw_product(2)])  # a new store with no catalog yet
    api.client.put("/api/wizard/test", headers=WRITE_HEADERS, json={"done": False})
    body = _wizard(api)
    assert body["current"] is None and body["finished"] is True
    assert [s["step"] for s in body["steps"]] == ["stores", "storage", "test", "catalog"]


def test_an_item_whose_only_links_are_on_removed_stores_is_left_out(api: ApiRig) -> None:
    """Analyst finding 14."""
    gf = api.rig.add_store("GF", [raw_product(1, "alpha")])
    api.rig.add_store("PW", [raw_product(2, "beta")])
    run_sync(api)
    with closing(api.rig.db.connect()) as connection:
        connection.execute("UPDATE store SET removed_at = '2026-11-17T13:00:00.000000Z' WHERE id = ?", (gf,))
    assert [item["canonical_slug"] for item in api.client.get("/api/catalog").json()["items"]] == ["beta"]


# ---- the shutdown --------------------------------------------------------------------------------------------------


def test_the_apps_shutdown_stops_a_running_read_and_changes_nothing() -> None:
    api = make_api_rig(fake_time=False)
    api.rig.add_store("GF", [raw_product(1, "alpha")], spacing_ms=5000)  # a 5-second wait before the products page
    with TestClient(api.harness.app, base_url="http://127.0.0.1:47615") as client:  # runs the lifespan
        client.cookies.update(api.client.cookies)
        assert client.post("/api/sync", headers=WRITE_HEADERS).status_code == 202
        wait_for(lambda: len(api.rig.sites.requests) == 1)
    # the lifespan has ended: the run was asked to stop and did, within the wait
    assert not api.rig.service.runner.state().running
    assert api.rig.service.runner.state().outcomes == {1: "stopped"}
    assert api.rig.db.rows("SELECT COUNT(*) FROM store_product") == [(0,)]
    assert api.rig.db.rows("SELECT COUNT(*) FROM catalog_item") == [(0,)]


# ---- the log -------------------------------------------------------------------------------------------------------


def test_the_sync_flows_write_no_address_key_cookie_query_or_body_anywhere_even_with_redaction_off(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capfd: pytest.CaptureFixture[str]
) -> None:
    """LOG-01, APL-12: a good read, retries, an answer that echoes the keys, cookies, a bad page and an auto-pause."""
    monkeypatch.setattr(logs, "redact", lambda text: text)
    handler = logs.configure_logging(tmp_path, retention_days=1)
    try:
        api = make_api_rig()
        api.rig.add_store(
            "GF", [raw_product(1, "secret-slug", "Secret Title", downloads=[download(key="obj-key.zip")])]
        )
        store = api.rig.sites.stores["GF"]
        store.extra_headers = {"Set-Cookie": f"wp_session={KEY}; Expires=Wed, 99 Foo 2026 99:99:99 GMT"}
        store.answers = [httpx.Response(524), httpx.Response(429, headers={"Retry-After": "1"})]
        run_sync(api)
        store.answers = [wp_error(401, f"woocommerce_rest_cannot_view {KEY}:{SECRET}")]
        run_sync(api)
        store.answers = [httpx.Response(200, headers={"X-WP-Total": "1", "X-WP-TotalPages": "1"}, content=b"<html>")]
        run_sync(api)
        store.status_answer = httpx.Response(500, content=f"<html>{KEY}</html>".encode())
        for _ in range(3):
            run_sync(api)
        handler.flush()
    finally:
        logs.remove_logging(handler)
    log_text = (tmp_path / logs.LOG_FILE_NAME).read_text(encoding="utf-8")
    assert "Store GF catalog read: ok" in log_text and "auto-paused" in log_text  # logging was on
    captured = capfd.readouterr()
    everything = log_text + captured.out + captured.err
    for forbidden in (
        KEY,
        SECRET,
        KEY[3:],
        "store-gf.example",
        "wp_session",
        "secret-slug",
        "Secret Title",
        "obj-key",
        "downloadable=",
        "per_page",
        "<html>",
        "woocommerce_rest_cannot_view",
        "cookiejar",
    ):
        assert forbidden not in everything, forbidden


# ---- the schema ----------------------------------------------------------------------------------------------------


def test_the_new_routes_are_in_the_openapi_schema_for_the_screens(api: ApiRig) -> None:
    paths = api.harness.app.openapi()["paths"]
    assert set(paths["/api/sync"]) == {"get", "post"}
    assert set(paths["/api/sync/stores/{store_id}/resume"]) == {"post"}
    assert set(paths["/api/catalog"]) == {"get"}
    assert set(paths["/api/catalog/{item_id}"]) == {"get", "patch"}
    assert set(paths["/api/wizard"]) == {"get"}
    assert set(paths["/api/wizard/{step}"]) == {"put"}

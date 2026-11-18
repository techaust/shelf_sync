"""SYNC-01, SYNC-03, SYNC-05: the m3.2 parts of the Sync and Catalog routes behind the guard: `POST /api/sync` with
its optional kind, `GET /api/sync`'s last incremental, latest night and next runs, `GET /api/catalog/{id}/snapshots`,
and the scheduler started by the lifespan of the app's service only."""

from datetime import UTC, datetime
from typing import Any

import httpx
import pytest
from fastapi.testclient import TestClient

from shelfsync.api.app import create_app
from shelfsync.catalog.runner import RunPlan
from shelfsync.catalog.runner import RunPlan as Plan
from shelfsync.catalog.service import CatalogService, choose_plan
from shelfsync.db.catalog import SyncStateRow
from shelfsync.platform.secrets import MemorySecretStore
from shelfsync.secure.token import InstallToken
from tests.support import WRITE_HEADERS, FakeClock, Harness
from tests.sync_support import SyncRig, make_sync_rig, row

START = datetime(2026, 11, 18, 10, 0, tzinfo=UTC)


def api_for(rig: SyncRig) -> TestClient:
    install = MemorySecretStore()
    clock = FakeClock()
    app = create_app(47615, InstallToken(install), clock, ui_dir=None, stores=rig.stores, catalog=rig.service)
    return Harness(app=app, store=install, clock=clock).signed_in_client()


@pytest.fixture
def rig() -> SyncRig:
    made = make_sync_rig(START)
    made.add_store("GF", [row(1, "alpha"), row(2, "beta")])
    made.add_store("PW", [row(7, "alpha")])
    return made


def post(client: TestClient, rig: SyncRig, body: Any = None) -> Any:
    response = (
        client.post("/api/sync", headers=WRITE_HEADERS)
        if body is None
        else client.post("/api/sync", json=body, headers=WRITE_HEADERS)
    )
    rig.service.runner.join(30.0)
    return response


def test_sync_now_reads_in_full_first_then_incrementally(rig: SyncRig) -> None:
    """SYNC-05: no kind: a full read until every active store has one, then an incremental."""
    client = api_for(rig)
    first = post(client, rig)
    assert first.status_code == 202 and first.json()["kind"] == "full"
    second = post(client, rig)
    assert second.status_code == 202 and second.json()["kind"] == "incremental"
    full = post(client, rig, {"kind": "full"})  # the wizard's Build catalog
    assert full.status_code == 202 and full.json()["kind"] == "full"
    explicit = post(client, rig, {"kind": "incremental"})
    assert explicit.json()["kind"] == "incremental"
    assert post(client, rig, {"kind": None}).json()["kind"] == "incremental"


@pytest.mark.parametrize("body", [{"kind": "snapshot"}, {"kind": "FULL"}, {"kind": 1}, {"other": True}, [1]])
def test_a_body_outside_the_rules_is_the_fixed_422(rig: SyncRig, body: Any) -> None:
    client = api_for(rig)
    response = post(client, rig, body)
    assert (response.status_code, response.json()) == (422, {"error": "invalid_request"})
    assert rig.sites.requests == []


def test_get_sync_shows_each_stores_last_incremental_latest_night_and_next_runs(rig: SyncRig) -> None:
    client = api_for(rig)
    post(client, rig)
    post(client, rig)  # an incremental
    assert rig.tick() is not None  # the night's snapshot (caught up at the first check)
    body = client.get("/api/sync").json()
    assert body["running"] is False and body["kind"] == "snapshot" and body["night"] == "2026-11-18"
    entry = body["stores"][0]
    assert entry["incremental"]["reason"] is None and entry["incremental"]["rows"] == 2
    assert entry["incremental"]["last_ok_at"] is not None and entry["incremental"]["changed"] == 0
    night = entry["snapshot"]
    assert (night["night"], night["state"], night["attempts"], night["listing"]) == (
        "2026-11-18",
        "ok",
        1,
        "include_status",
    )
    assert (night["products"], night["trashed"], night["not_seen"], night["variable"]) == (2, 0, 0, 0)
    assert entry["next_snapshot_at"] == "2026-11-19T02:00:00.000000Z"  # UTC zone in this rig
    assert entry["next_incremental_at"] is not None and entry["next_incremental_at"] > night["finished_at"]


def test_a_store_waiting_for_its_retry_shows_when(rig: SyncRig) -> None:
    client = api_for(rig)
    post(client, rig)
    rig.at(datetime(2026, 11, 19, 2, 0, 5, tzinfo=UTC))
    rig.store("GF").fail = lambda request: httpx.Response(524)
    rig.tick()
    entry = client.get("/api/sync").json()["stores"][0]
    assert entry["snapshot"]["state"] == "retry" and entry["snapshot"]["reason"] == "cloudflare_52x"
    assert entry["next_snapshot_at"] == entry["snapshot"]["next_try_at"]
    assert entry["next_snapshot_at"].startswith("2026-11-19T02:30")


def test_a_store_with_no_full_read_has_no_incremental_or_night_yet(rig: SyncRig) -> None:
    client = api_for(rig)
    entry = client.get("/api/sync").json()["stores"][0]
    assert entry["incremental"] is None and entry["snapshot"] is None and entry["next_incremental_at"] is None
    assert entry["next_snapshot_at"] is not None


def test_the_snapshots_route_lists_the_restore_dates_newest_first(rig: SyncRig) -> None:
    """SYNC-03 Accept: "Restore to date" lists the snapshot dates for a product."""
    client = api_for(rig)
    post(client, rig)
    for night in ("2026-11-18", "2026-11-19"):
        assert rig.service.runner.start(RunPlan("snapshot", night=night))
        rig.service.runner.join(30.0)
    items = client.get("/api/catalog").json()["items"]
    alpha = next(item for item in items if item["canonical_slug"] == "alpha")
    response = client.get(f"/api/catalog/{alpha['id']}/snapshots")
    assert response.status_code == 200
    body = response.json()
    assert body["item_id"] == alpha["id"]
    assert [(entry["wc_id"], entry["nights"]) for entry in body["stores"]] == [
        (1, ["2026-11-19", "2026-11-18"]),
        (7, ["2026-11-19", "2026-11-18"]),
    ]
    assert client.get("/api/catalog/999/snapshots").json() == {"error": "not_found"}
    assert client.get("/api/catalog/0/snapshots").status_code == 422


def test_the_lifespan_starts_the_scheduler_of_the_apps_service_only(monkeypatch: pytest.MonkeyPatch) -> None:
    started: list[bool] = []
    monkeypatch.setattr("shelfsync.catalog.scheduler.SyncScheduler.start", lambda self: started.append(True))
    for scheduled in (False, True):
        service = CatalogService.in_memory()
        service._scheduled = scheduled
        install = MemorySecretStore()
        app = create_app(47615, InstallToken(install), FakeClock(), ui_dir=None, catalog=service)
        with TestClient(app):
            pass
    assert started == [True]


def test_choose_plan() -> None:
    """SYNC-05 and review 1: the unbuilt stores in full, the others incrementally, in one run."""

    def state(store_id: int, ok: bool, watermark: bool) -> SyncStateRow:
        return SyncStateRow(
            store_id,
            None,
            None,
            None,
            None,
            None,
            None,
            None,
            "t" if ok else None,
            0,
            None,
            None,
            None,
            "2026-11-10T00:00:00" if watermark else None,
        )

    assert choose_plan(set(), {}) == Plan("full")
    assert choose_plan({1}, {1: state(1, True, True)}) == Plan("incremental")
    assert choose_plan({1, 2}, {1: state(1, True, True)}) == Plan("incremental", full_stores=frozenset({2}))
    assert choose_plan({1}, {1: state(1, True, False)}) == Plan("full")
    assert choose_plan({1, 2}, {}) == Plan("full")


def test_the_new_route_is_in_the_openapi_schema(rig: SyncRig) -> None:
    client = api_for(rig)
    paths = client.app.openapi()["paths"]  # type: ignore[attr-defined]
    assert set(paths["/api/catalog/{item_id}/snapshots"]) == {"get"}
    request = paths["/api/sync"]["post"].get("requestBody")
    assert request is not None and request.get("required") is not True

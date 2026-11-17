"""The Sync API (CAT-01, APL-12, ERR-02): start a full read of the stores' catalogs, follow it, and resume a store
whose sync was auto-paused.

Every route sits behind the guard in `secure/middleware.py` (a session, and Origin plus `X-ShelfSync: 1` for the
writes). Nothing here reads a store inside the request: `POST` only starts the background run (`catalog/runner.py`).

    POST /api/sync                       202 SyncResponse (started); 409 sync_running
    GET  /api/sync                       200 SyncResponse
    POST /api/sync/stores/{id}/resume    204 (the auto-pause and the failures in a row are cleared); 404 not_found

In m3.1 `POST /api/sync` is always a full read (it is also the wizard's "Build catalog"); m3.2 makes it incremental once
a catalog exists. The router's lifespan stops a running read when the app shuts down, leaving that store's data as it
was. Times are UTC ISO 8601.
"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Annotated, Any, Literal

from fastapi import APIRouter, FastAPI, Path, Response
from pydantic import BaseModel

from shelfsync.api.errors import ApiError, ErrorResponse
from shelfsync.catalog.service import CatalogService, StoreSync, SyncStatus

SYNC_PATH = "/api/sync"
StoreId = Annotated[int, Path(ge=1, le=2**63 - 1)]


class ProgressModel(BaseModel):
    store_id: int
    page: int  # 0 until the store's first products page has been read
    pages: int
    rows: int


class StoreSyncModel(BaseModel):
    store_id: int
    code: str
    state: Literal["active", "paused"]  # the owner's pause (Settings)
    read_started_at: str | None  # the last full read
    read_finished_at: str | None
    last_ok_at: str | None  # the last full read that worked
    reason: str | None  # the last full read's outcome: null when it worked (or none has run)
    http_status: int | None  # the status of its last failed request
    pages: int | None
    rows: int | None
    total: int | None  # X-WP-Total
    failures_in_row: int
    auto_paused: bool
    auto_paused_at: str | None
    auto_pause_reason: str | None
    this_run: str | None  # in the current (or last) run: "ok", a reason, "paused", "auto_paused"; null: not reached


class SyncResponse(BaseModel):
    running: bool
    started_at: str | None
    finished_at: str | None
    current: ProgressModel | None
    stores: list[StoreSyncModel]


def _store_model(entry: StoreSync) -> StoreSyncModel:
    row, state = entry.store, entry.state
    this_run = (entry.this_run or "ok") if entry.reached else None
    return StoreSyncModel(
        store_id=row.id,
        code=row.code,
        state="paused" if row.state == "paused" else "active",
        read_started_at=state.read_started_at if state else None,
        read_finished_at=state.read_finished_at if state else None,
        last_ok_at=state.last_ok_at if state else None,
        reason=state.read_reason if state else None,
        http_status=state.read_http_status if state else None,
        pages=state.read_pages if state else None,
        rows=state.read_rows if state else None,
        total=state.read_total if state else None,
        failures_in_row=state.failures_in_row if state else 0,
        auto_paused=bool(state and state.auto_paused_at),
        auto_paused_at=state.auto_paused_at if state else None,
        auto_pause_reason=state.auto_pause_reason if state else None,
        this_run=this_run,
    )


def sync_response(status: SyncStatus) -> SyncResponse:
    run = status.run
    current = run.current
    return SyncResponse(
        running=run.running,
        started_at=run.started_at,
        finished_at=run.finished_at,
        current=None if current is None else ProgressModel(**current.__dict__),
        stores=[_store_model(entry) for entry in status.stores],
    )


def make_sync_router(service: CatalogService) -> APIRouter:
    @asynccontextmanager
    async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
        try:
            yield
        finally:
            service.stop()  # the app is shutting down: a running read stops and saves nothing

    router = APIRouter(lifespan=lifespan)
    errors: dict[int | str, dict[str, Any]] = {409: {"model": ErrorResponse}}

    @router.post(SYNC_PATH, status_code=202, response_model=SyncResponse, responses=errors)
    def start_sync() -> SyncResponse:
        if not service.start_sync():
            raise ApiError(409, "sync_running")
        return sync_response(service.sync_status())

    @router.get(SYNC_PATH, response_model=SyncResponse)
    def get_sync() -> SyncResponse:
        return sync_response(service.sync_status())

    @router.post(f"{SYNC_PATH}/stores/{{store_id}}/resume", status_code=204, responses={404: {"model": ErrorResponse}})
    def resume_store(store_id: StoreId) -> Response:
        if not service.resume(store_id):
            raise ApiError(404, "not_found")
        return Response(status_code=204)

    return router

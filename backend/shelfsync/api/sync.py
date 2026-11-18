"""The Sync API (CAT-01, APL-12, ERR-02; m3.2: SYNC-01, SYNC-03, SYNC-05): start a read of the stores' catalogs,
follow it and the scheduled ones, and resume a store whose sync was auto-paused.

Every route sits behind the guard in `secure/middleware.py` (a session, and Origin plus `X-ShelfSync: 1` for the
writes). Nothing here reads a store inside the request: `POST` only starts the background run (`catalog/runner.py`).

    POST /api/sync                       body optional: {kind: "full" | "incremental" | null}. 202 SyncResponse
                                         (started); 409 sync_running (a run, scheduled ones included, is going);
                                         503 shutting_down (the app is stopping: no run starts)
    GET  /api/sync                       200 SyncResponse
    POST /api/sync/stores/{id}/resume    204 (the auto-pause and the failures in a row are cleared); 404 not_found

`POST /api/sync` without a kind (Sync now, SYNC-05) reads in full the active stores that have had no full read that
worked and incrementally the others, in one run (`kind` answers `incremental` then; `full` when none is built); the
wizard's "Build catalog" asks for `full`. An explicit `incremental` skips a store that has had no full read
(`no_full_read`). The snapshot is never started here: the scheduler starts it at `snapshot_time`
(`catalog/scheduler.py`). `GET` adds, per store, its last incremental, its latest snapshot night, and when each comes
next. The router's lifespan starts the scheduler (the app's service only) and, when the app shuts down, stops it and a
running read, leaving that store's data as it was. Times are UTC ISO 8601; a night is a local date (`YYYY-MM-DD`).
"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Annotated, Any, Literal

from fastapi import APIRouter, FastAPI, Path, Response
from pydantic import BaseModel, ConfigDict
from starlette.concurrency import run_in_threadpool

from shelfsync.api.errors import ApiError, ErrorResponse
from shelfsync.catalog.service import CatalogService, StoreSync, SyncStatus
from shelfsync.clock import to_iso
from shelfsync.db.snapshots import NightRow

SYNC_PATH = "/api/sync"
StoreId = Annotated[int, Path(ge=1, le=2**63 - 1)]


class SyncRequest(BaseModel):
    """`kind`: `full` (the wizard's Build catalog), `incremental`, or null/absent (Sync now: the app chooses)."""

    model_config = ConfigDict(extra="forbid", strict=True)
    kind: Literal["full", "incremental"] | None = None


class ProgressModel(BaseModel):
    store_id: int
    page: int  # 0 until the store's first products page has been read
    pages: int
    rows: int


class IncrementalModel(BaseModel):
    """The store's last incremental (SYNC-01)."""

    started_at: str | None
    finished_at: str | None
    last_ok_at: str | None  # the last one that worked
    reason: str | None  # its outcome: null when it worked
    http_status: int | None  # the status of its last failed request
    rows: int | None  # products it returned
    changed: int | None  # catalog rows it changed or added


class NightModel(BaseModel):
    """The store's latest snapshot night (SYNC-03, SYNC-04)."""

    night: str  # the local date of the night's snapshot time
    state: Literal["running", "ok", "retry", "failed", "skipped"]
    attempts: int  # 0 to 3
    started_at: str | None  # the last attempt's start
    finished_at: str | None
    next_try_at: str | None  # `retry`: when the same night is tried again
    reason: str | None  # why it failed or was skipped
    http_status: int | None
    listing: Literal["include_status", "two_listings"] | None  # how the trash was listed
    products: int | None  # products read, trash included
    trashed: int | None
    not_seen: int | None  # catalog products present before the save that a 404 confirmed deleted (F10)
    variable: int | None  # variable products whose variations were read
    unconfirmed: int | None  # catalog products missing from the listing, not confirmed either way yet (review 1)


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
    incremental: IncrementalModel | None  # null: none has run
    snapshot: NightModel | None  # null: no night yet
    next_incremental_at: str | None  # null: it can't have one (no full read, paused, auto-paused)
    next_snapshot_at: str | None


class SyncResponse(BaseModel):
    running: bool
    kind: Literal["full", "incremental", "snapshot"] | None  # the current (or last) run's
    night: str | None  # a snapshot run's night
    started_at: str | None
    finished_at: str | None
    current: ProgressModel | None
    stores: list[StoreSyncModel]


def _iso(moment: datetime | None) -> str | None:
    return None if moment is None else to_iso(moment)


def _night(row: NightRow | None) -> NightModel | None:
    if row is None:
        return None
    return NightModel(
        night=row.night,
        state=row.state,  # type: ignore[arg-type]  # the table's CHECK holds it to the five
        attempts=row.attempts,
        started_at=row.started_at,
        finished_at=row.finished_at,
        next_try_at=row.next_try_at,
        reason=row.reason,
        http_status=row.http_status,
        listing=row.listing,  # type: ignore[arg-type]  # the table's CHECK holds it to the two
        products=row.products,
        trashed=row.trashed,
        not_seen=row.not_seen,
        variable=row.variable,
        unconfirmed=row.unconfirmed,
    )


def _store_model(entry: StoreSync) -> StoreSyncModel:
    row, state = entry.store, entry.state
    this_run = (entry.this_run or "ok") if entry.reached else None
    incremental = None
    if state is not None and state.inc_started_at is not None:
        incremental = IncrementalModel(
            started_at=state.inc_started_at,
            finished_at=state.inc_finished_at,
            last_ok_at=state.inc_last_ok_at,
            reason=state.inc_reason,
            http_status=state.inc_http_status,
            rows=state.inc_rows,
            changed=state.inc_changed,
        )
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
        incremental=incremental,
        snapshot=_night(entry.night),
        next_incremental_at=_iso(entry.next_incremental_at),
        next_snapshot_at=_iso(entry.next_snapshot_at),
    )


def sync_response(status: SyncStatus) -> SyncResponse:
    run = status.run
    current = run.current
    return SyncResponse(
        running=run.running,
        kind=run.kind,
        night=run.night,
        started_at=run.started_at,
        finished_at=run.finished_at,
        current=None if current is None else ProgressModel(**current.__dict__),
        stores=[_store_model(entry) for entry in status.stores],
    )


def make_sync_router(service: CatalogService) -> APIRouter:
    @asynccontextmanager
    async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
        service.reopen()  # the app is starting: runs may start (a second lifespan of one app included)
        service.start_scheduler()  # the app's service only (`build_catalog_service`)
        try:
            yield
        finally:
            # the app is shutting down: the scheduler stops, no run starts from now on, a running read stops and
            # saves nothing. The stop waits up to 2 s for each, so it runs on a worker thread, never on the event loop.
            await run_in_threadpool(service.stop)

    router = APIRouter(lifespan=lifespan)
    errors: dict[int | str, dict[str, Any]] = {
        409: {"model": ErrorResponse},
        422: {"model": ErrorResponse},
        503: {"model": ErrorResponse},
    }

    @router.post(SYNC_PATH, status_code=202, response_model=SyncResponse, responses=errors)
    def start_sync(body: SyncRequest | None = None) -> SyncResponse:
        if service.start_sync(body.kind if body is not None else None) is None:
            raise ApiError(503, "shutting_down") if service.closed else ApiError(409, "sync_running")
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

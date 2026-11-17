"""The background catalog run (CAT-01, APL-12): one run at a time over every live store, **one store after another**,
never two at once, and never inside a request (`POST /api/sync` only starts it).

- Each store's client comes from a **factory** (`ClientFactory`): the app's reads the store's keys from Credential
  Manager; a test (and m3.2's test-only launcher) gives its own, with a fake or the test site's transport. The app
  itself gains no setting.
- A store the owner paused (`state = 'paused'`) or that is auto-paused (`sync_state.auto_paused_at`) is skipped and
  shown as such (`paused`, `auto_paused`).
- Progress (the store, page of pages, rows) is kept for `GET /api/sync`.
- **Stop:** `stop()` (the app's shutdown) is seen between requests and during every wait; the store being read is left
  exactly as it was (nothing of a stopped read is saved) and no later store is started.
- A read that worked is saved in one transaction (`db/catalog.py`); a failed one records only its outcome.
"""

import logging
import sqlite3
import threading
import time
from collections.abc import Callable
from contextlib import closing
from dataclasses import dataclass, field, replace
from datetime import datetime
from typing import Protocol

from shelfsync.apply.catalog_read import FAILURES_TO_PAUSE, CatalogRead, log_read, read_catalog
from shelfsync.apply.woocommerce import WooClient
from shelfsync.clock import to_iso, utc_now
from shelfsync.db.catalog import (
    record_failure,
    record_read_failed,
    record_read_started,
    record_success,
    save_store_read,
    sync_state,
)
from shelfsync.db.stores import StoreRow, list_live
from shelfsync.platform.secrets import SecretStoreError

_log = logging.getLogger("shelfsync.catalog")

STOP_WAIT_SECONDS = 2.0  # how long the app's shutdown waits for the run to notice the stop


class KeysMissing(Exception):
    """The store has no saved key pair."""


ClientFactory = Callable[[StoreRow], WooClient]


class StopSignal(Protocol):
    """`threading.Event` is one."""

    def is_set(self) -> bool: ...

    def wait(self, timeout: float | None = None) -> bool: ...

    def set(self) -> None: ...


@dataclass(frozen=True)
class StoreProgress:
    store_id: int
    page: int
    pages: int
    rows: int


@dataclass(frozen=True)
class RunState:
    """The current run (or the last one). `outcomes` holds each store's outcome in that run: None when its read worked,
    otherwise a reason (`paused` and `auto_paused` for a skipped store)."""

    running: bool = False
    started_at: str | None = None
    finished_at: str | None = None
    current: StoreProgress | None = None
    outcomes: dict[int, str | None] = field(default_factory=dict)


class _StoredFailures:
    """The failure count (APL-12) kept in `sync_state`, so it carries over to the next run."""

    def __init__(self, connection: sqlite3.Connection, store_id: int, now: Callable[[], datetime]) -> None:
        self._connection = connection
        self._store_id = store_id
        self._now = now

    def failed(self, reason: str) -> bool:
        return record_failure(self._connection, self._store_id, reason, to_iso(self._now()), FAILURES_TO_PAUSE)

    def succeeded(self) -> None:
        record_success(self._connection, self._store_id)


class SyncRunner:
    def __init__(
        self,
        open_connection: Callable[[], sqlite3.Connection],
        client_factory: ClientFactory,
        *,
        now: Callable[[], datetime] = utc_now,
        monotonic: Callable[[], float] = time.monotonic,
        make_stop: Callable[[], StopSignal] = threading.Event,
    ) -> None:
        self._open = open_connection
        self._factory = client_factory
        self._now = now
        self._monotonic = monotonic
        self._make_stop = make_stop
        self._stop: StopSignal = make_stop()
        self._lock = threading.Lock()
        self._state = RunState()
        self._thread: threading.Thread | None = None

    def state(self) -> RunState:
        with self._lock:
            return replace(self._state, outcomes=dict(self._state.outcomes))

    def start(self) -> bool:
        """Start a run on its own thread. False when one is running (or a stopped one hasn't ended yet)."""
        with self._lock:
            if self._thread is not None and self._thread.is_alive():
                return False
            self._stop = self._make_stop()
            self._state = RunState(running=True, started_at=to_iso(self._now()))
            self._thread = threading.Thread(target=self._run, name="catalog-sync", daemon=True)
            self._thread.start()
            return True

    def stop(self, wait_seconds: float = STOP_WAIT_SECONDS) -> None:
        """Ask the run to stop and wait a bounded time. A request in flight ends within its own timeouts; the run is a
        daemon thread, so it never holds the process."""
        self._stop.set()
        thread = self._thread
        if thread is not None:
            thread.join(timeout=wait_seconds)

    def join(self, timeout: float | None = None) -> None:
        thread = self._thread
        if thread is not None:
            thread.join(timeout)

    # ---- the run ---------------------------------------------------------------------------------------------------

    def _run(self) -> None:
        try:
            with closing(self._open()) as connection:
                stores = list_live(connection)
            for row in stores:
                if self._stop.is_set():
                    break
                outcome = self._read_one(row)
                with self._lock:
                    self._state.outcomes[row.id] = outcome
                if outcome == "stopped":
                    break
        except Exception as error:  # nothing here may end the app; the reason is in the log
            _log.error("The catalog sync stopped on an error (%s)", type(error).__name__)
        finally:
            with self._lock:
                self._state = replace(self._state, running=False, current=None, finished_at=to_iso(self._now()))

    def _progress(self, store_id: int) -> Callable[[int, int, int], None]:
        def report(page: int, pages: int, rows: int) -> None:
            with self._lock:
                self._state = replace(self._state, current=StoreProgress(store_id, page, pages, rows))

        return report

    def _read_one(self, row: StoreRow) -> str | None:
        """Read and save one store; its outcome. Never raises."""
        if row.state != "active":
            _log.info("Store %s catalog read: paused (skipped)", row.code)
            return "paused"
        with self._lock:
            self._state = replace(self._state, current=StoreProgress(row.id, 0, 0, 0))
        try:
            with closing(self._open()) as connection:
                state = sync_state(connection, row.id)
                if state is not None and state.auto_paused_at is not None:
                    _log.info("Store %s catalog read: auto_paused (skipped)", row.code)
                    return "auto_paused"
                record_read_started(connection, row.id, to_iso(self._now()))
                return self._read_and_save(connection, row)
        except sqlite3.Error as error:
            _log.error("Store %s catalog read: database_error (%s)", row.code, type(error).__name__)
            return "database_error"
        except Exception as error:  # a bug must not stop the other stores; its type is logged, never its text
            _log.error("Store %s catalog read: internal (%s)", row.code, type(error).__name__)
            return "internal"

    def _read_and_save(self, connection: sqlite3.Connection, row: StoreRow) -> str | None:
        try:
            client = self._factory(row)
        except KeysMissing:
            return self._failed(connection, row, CatalogRead("keys_missing"))
        except SecretStoreError:
            return self._failed(connection, row, CatalogRead("secrets_unavailable"))
        with client:
            result = read_catalog(
                client,
                spacing_ms=row.spacing_ms,
                stop=self._stop,
                failures=_StoredFailures(connection, row.id, self._now),
                progress=self._progress(row.id),
                monotonic=self._monotonic,
                now=self._now,
            )
        if result.ok and self._stop.is_set():
            result = replace(result, reason="stopped", products=())  # the app is shutting down: nothing is saved
        if not result.ok:
            return self._failed(connection, row, result)
        save_store_read(
            connection, row.id, result.products, total=result.total, pages=result.pages, at=to_iso(self._now())
        )
        log_read(row.code, result)
        return None

    def _failed(self, connection: sqlite3.Connection, row: StoreRow, result: CatalogRead) -> str:
        reason = result.reason or "internal"
        record_read_failed(
            connection,
            row.id,
            reason=reason,
            http_status=result.http_status,
            pages=result.pages,
            total=result.total,
            at=to_iso(self._now()),
        )
        log_read(row.code, result)
        return reason

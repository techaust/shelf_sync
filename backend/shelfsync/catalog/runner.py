"""The background catalog run (CAT-01, APL-12): one run at a time over every live store, **one store after another**,
never two at once, and never inside a request (`POST /api/sync` only starts it).

- Each store's client comes from a **factory** (`ClientFactory`): the app's reads the store's keys from Credential
  Manager; a test (and m3.2's test-only launcher) gives its own, with a fake or the test site's transport. The app
  itself gains no setting.
- **Each store's turn holds its busy slot** (`store_service.BusySlots`, shared with the stores service) for the whole
  read: an edit of its address or keys, its removal and its Test connection answer `busy` meanwhile, and a Test
  connection running when the turn comes is waited for (at most `CLAIM_WAIT_SECONDS`, else `busy`), so APL-12's
  spacing holds. Then, under the secrets lock, the store's row and keys are read **as they are now** (never the list
  read when the run began): a store removed since is skipped (`store_removed`), a store paused since is skipped
  (`paused`), and the client, `address_changed` and the save's `read_url` all use that row.
- A store that is auto-paused (`sync_state.auto_paused_at`) is skipped and shown as such (`auto_paused`).
- Progress (the store, page of pages, rows) is kept for `GET /api/sync`.
- **Stop:** `stop()` (the app's shutdown) is seen between requests and during every wait; the store being read is left
  exactly as it was (nothing of a stopped read is saved) and no later store is started.
- A read that worked is saved in one transaction (`db/catalog.py`); a failed one records only its outcome, and an
  outcome the read's own connection couldn't record (`database_error`, `internal`) is recorded on a fresh one.
- **The address guard:** a store whose address changed since its saved catalog was read is refused before any
  request (`address_changed`), and so is a save when the address changed during the read: links are keyed by the
  store and the WooCommerce id, so another shop's products would silently take the old ones' places. Resolving it is a
  later task (`db.catalog.clear_address_guard`).
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
    AddressMoved,
    StoreRemoved,
    address_changed,
    record_failure,
    record_read_failed,
    record_read_started,
    record_success,
    save_store_read,
    sync_state,
)
from shelfsync.db.stores import StoreRow, get_store, list_live
from shelfsync.platform.secrets import SecretStoreError
from shelfsync.secure.credentials import SECRETS_WRITE_LOCK
from shelfsync.store_service import BusySlots

_log = logging.getLogger("shelfsync.catalog")

STOP_WAIT_SECONDS = 2.0  # how long the app's shutdown waits for the run to notice the stop
# How long a store's turn waits for its busy slot (a Test connection takes at most 60 s plus 1 s of grace), and how
# often it looks again (Lead (proposed), m3.1 review 1).
CLAIM_WAIT_SECONDS = 70.0
CLAIM_POLL_SECONDS = 0.5


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
        slots: BusySlots,
        now: Callable[[], datetime] = utc_now,
        monotonic: Callable[[], float] = time.monotonic,
        make_stop: Callable[[], StopSignal] = threading.Event,
    ) -> None:
        self._open = open_connection
        self._factory = client_factory
        self._slots = slots
        self._now = now
        self._monotonic = monotonic
        self._make_stop = make_stop
        self._stop: StopSignal = make_stop()
        self._lock = threading.Lock()
        self._state = RunState()
        self._thread: threading.Thread | None = None
        self._closed = False

    def state(self) -> RunState:
        with self._lock:
            return replace(self._state, outcomes=dict(self._state.outcomes))

    def start(self) -> bool:
        """Start a run on its own thread. False when one is running (or a stopped one hasn't ended yet), and always
        after `stop()`: the app is shutting down, so no run may begin."""
        with self._lock:
            if self._closed or (self._thread is not None and self._thread.is_alive()):
                return False
            self._stop = self._make_stop()
            self._state = RunState(running=True, started_at=to_iso(self._now()))
            self._thread = threading.Thread(target=self._run, name="catalog-sync", daemon=True)
            self._thread.start()
            return True

    def stop(self, wait_seconds: float = STOP_WAIT_SECONDS) -> None:
        """Close the runner (no run starts after this), ask a running one to stop and wait a bounded time. A request
        in flight ends within its own timeouts; the run is a daemon thread, so it never holds the process."""
        with self._lock:
            self._closed = True
        self._stop.set()
        thread = self._thread
        if thread is not None:
            thread.join(timeout=wait_seconds)

    @property
    def closed(self) -> bool:
        """The app is shutting down (`stop()` was called and no lifespan has opened it again)."""
        with self._lock:
            return self._closed

    def reopen(self) -> None:
        """The app is starting (again): runs may start. The lifespan calls it, so a second lifespan of one app (tests;
        never the installed app) isn't left with a closed runner."""
        with self._lock:
            self._closed = False

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

    def _read_one(self, listed: StoreRow) -> str | None:
        """Read and save one store; its outcome. Never raises. The store's busy slot is held for the whole read."""
        with self._lock:
            self._state = replace(self._state, current=StoreProgress(listed.id, 0, 0, 0))
        try:
            skipped = self._skip_reason(listed.id)  # before the slot: a skipped store never waits for it
        except sqlite3.Error as error:
            _log.error("Store %s catalog read: database_error (%s)", listed.code, type(error).__name__)
            return self._record_on_fresh_connection(listed, "database_error")
        if skipped is not None:
            _log.info("Store %s catalog read: %s (skipped)", listed.code, skipped)
            return skipped
        refused = self._claim(listed.id)
        if refused is not None:
            _log.info("Store %s catalog read: %s (skipped)", listed.code, refused)
            return refused
        try:
            return self._read_claimed(listed)
        finally:
            self._slots.release(listed.id)

    def _skip_reason(self, store_id: int) -> str | None:
        """Why the store is skipped as it is now (`store_removed`, `paused`, `auto_paused`), or None. Checked before
        its busy slot is taken and again after (`_read_claimed`), since it can change while the turn waits."""
        with closing(self._open()) as connection:
            row = get_store(connection, store_id)
            if row is None:
                return "store_removed"
            if row.state != "active":
                return "paused"
            state = sync_state(connection, store_id)
        return "auto_paused" if state is not None and state.auto_paused_at is not None else None

    def _claim(self, store_id: int) -> str | None:
        """Take the store's busy slot, waiting while a Test connection or an edit holds it (at most
        `CLAIM_WAIT_SECONDS`). None when taken; else `busy`, or `stopped` when the app shuts down meanwhile."""
        deadline = self._monotonic() + CLAIM_WAIT_SECONDS
        while not self._slots.claim(store_id):
            if self._monotonic() >= deadline:
                return "busy"
            if self._stop.wait(CLAIM_POLL_SECONDS):
                return "stopped"
        return None

    def _current(self, store_id: int) -> tuple[StoreRow | None, WooClient | None, str | None]:
        """The store's row as it is now and a client built from it with its keys as they are now, read together under
        the secrets lock, so no edit falls between them (and, with the busy slot held, none can follow until the read
        ends). The row is None when the store was removed; the client is None for a store that isn't active or whose
        keys can't be had (the third value says why)."""
        with SECRETS_WRITE_LOCK:
            with closing(self._open()) as connection:
                row = get_store(connection, store_id)
            if row is None or row.state != "active":
                return row, None, None
            try:
                return row, self._factory(row), None
            except KeysMissing:
                return row, None, "keys_missing"
            except SecretStoreError:
                return row, None, "secrets_unavailable"

    def _read_claimed(self, listed: StoreRow) -> str | None:
        row = listed  # the code the log names, until the current row is read
        client: WooClient | None = None
        try:
            current, client, failure = self._current(listed.id)
            if current is None:
                _log.info("Store %s catalog read: store_removed (skipped)", listed.code)
                return "store_removed"
            row = current
            if row.state != "active":
                _log.info("Store %s catalog read: paused (skipped)", row.code)
                return "paused"
            with closing(self._open()) as connection:
                state = sync_state(connection, row.id)
                if state is not None and state.auto_paused_at is not None:
                    _log.info("Store %s catalog read: auto_paused (skipped)", row.code)
                    return "auto_paused"
                record_read_started(connection, row.id, to_iso(self._now()))
                if failure is not None or client is None:
                    return self._failed(connection, row, CatalogRead(failure or "internal"))
                if address_changed(connection, row.id, row.url):
                    return self._failed(connection, row, CatalogRead("address_changed"))  # no request is sent
                return self._read_and_save(connection, row, client)
        except AddressMoved:
            return self._record_on_fresh_connection(row, "address_changed")
        except StoreRemoved:
            return self._record_on_fresh_connection(row, "store_removed")
        except sqlite3.Error as error:
            _log.error("Store %s catalog read: database_error (%s)", row.code, type(error).__name__)
            return self._record_on_fresh_connection(row, "database_error")
        except Exception as error:  # a bug must not stop the other stores; its type is logged, never its text
            _log.error("Store %s catalog read: internal (%s)", row.code, type(error).__name__)
            return self._record_on_fresh_connection(row, "internal")
        finally:
            if client is not None:
                _close_quietly(client)

    def _record_on_fresh_connection(self, row: StoreRow, reason: str) -> str:
        """Record an outcome the read's own connection may not be able to (it failed on that connection). A second
        failure is only logged: the outcome is still reported in `GET /api/sync`'s `this_run`."""
        try:
            with closing(self._open()) as connection:
                record_read_failed(
                    connection, row.id, reason=reason, http_status=None, pages=0, total=None, at=to_iso(self._now())
                )
        except Exception as error:
            _log.error("Store %s: the outcome couldn't be recorded (%s)", row.code, type(error).__name__)
        if reason in ("address_changed", "store_removed"):
            log_read(row.code, CatalogRead(reason))
        return reason

    def _read_and_save(self, connection: sqlite3.Connection, row: StoreRow, client: WooClient) -> str | None:
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
            connection,
            row.id,
            result.products,
            total=result.total,
            pages=result.pages,
            at=to_iso(self._now()),
            read_url=row.url,
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


def _close_quietly(client: WooClient) -> None:
    try:
        client.close()
    except Exception as error:  # a close that fails changes nothing for the run
        _log.debug("A store client didn't close cleanly (%s)", type(error).__name__)

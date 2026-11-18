"""The background catalog runs (CAT-01, APL-12; m3.2: SYNC-01, SYNC-03, SYNC-04, SYNC-05): one run at a time over the
live stores, **one store after another**, never two at once, and never inside a request (`POST /api/sync` and the
scheduler only start it). A run is one `RunPlan`: a **full** read (m3.1; the wizard's Build catalog), an
**incremental** (every `sync_interval_minutes`, and Sync now once a catalog exists), or the **snapshot** of one night
for the stores it is due on.

- Each store's client comes from a **factory** (`ClientFactory`): the app's reads the store's keys from Credential
  Manager; a test (and m3.2's test-only launcher) gives its own, with a fake or the test site's transport. The app
  itself gains no setting.
- **Each store's turn holds its busy slot** (`store_service.BusySlots`, shared with the stores service) for the whole
  read: an edit of its address or keys, its removal and its Test connection answer `busy` meanwhile, and a Test
  connection running when the turn comes is waited for (at most `CLAIM_WAIT_SECONDS`, else `busy`), so APL-12's
  spacing holds. Then, under the secrets lock, the store's row and keys are read **as they are now** (never the list
  read when the run began): a store removed since is skipped (`store_removed`), a store paused since is skipped
  (`paused`), and the client, `address_changed` and the save's `read_url` all use that row.
- A store that is auto-paused (`sync_state.auto_paused_at`) is skipped and shown as such (`auto_paused`). An incremental
  skips a store without a watermark (`no_full_read`). A snapshot records a paused, auto-paused or not yet read
  store's night as `skipped` (`paused`, `auto_paused`, `no_catalog`).
- **APL-12 (the owner, 11 2026-11-18):** each read (a full read, an incremental, a snapshot attempt) that fails counts
  once, when its outcome is recorded (`db.catalog.count_failed_read`, in the same transaction); a read that worked
  sets the count to 0 in its save's transaction; reasons that never count are `db.catalog.NOT_COUNTED`.
- Progress (the store, page of pages, rows) is kept for `GET /api/sync`.
- **Stop:** `stop()` (the app's shutdown) is seen between requests and during every wait; the store being read is left
  exactly as it was (nothing of a stopped read is saved) and no later store is started.
- A read that worked is saved in one transaction (`db/catalog.py`, `db/snapshots.py`); a failed one records only its
  outcome, and an outcome the read's own connection couldn't record (`database_error`, `internal`) is recorded on a
  fresh one. A snapshot attempt that failed is tried again the same night (`catalog/schedule.py`).
- **The address guard:** a store whose address changed since its saved catalog was read is refused before any
  request (`address_changed`), and so is a save when the address changed during the read: links are keyed by the
  store and the WooCommerce id, so another shop's products would silently take the old ones' places. Resolving it is a
  later task (`db.catalog.clear_address_guard`).
- **Changes (F4):** the changes an incremental or a snapshot found (`catalog/changes.py`) go to `on_changes` **inside
  the save's transaction, with its connection** (m3.3 writes its Cleanup rows there); if it raises, the save rolls back
  and the read ends `internal` (not counted), to be read again next time. The log gets their counts only.
"""

import logging
import sqlite3
import threading
import time
from collections.abc import Callable
from contextlib import closing
from dataclasses import dataclass, field, replace
from datetime import datetime
from typing import Literal, Protocol

from shelfsync.apply.catalog_read import (
    CatalogRead,
    SnapshotRead,
    log_incremental,
    log_read,
    log_snapshot,
    read_catalog,
    read_incremental,
    read_snapshot,
)
from shelfsync.apply.woocommerce import WooClient
from shelfsync.catalog.changes import Change, counts
from shelfsync.catalog.schedule import SnapshotTime, night_of
from shelfsync.clock import to_iso, utc_now
from shelfsync.db import snapshots
from shelfsync.db.catalog import (
    AddressMoved,
    ChangeSink,
    StoreRemoved,
    SyncStateRow,
    address_changed,
    record_incremental_failed,
    record_incremental_started,
    record_read_failed,
    record_read_started,
    save_incremental,
    save_store_read,
    sync_state,
)
from shelfsync.db.daily import LocalTime
from shelfsync.db.settings import (
    DEFAULTS,
    SNAPSHOT_DAYS_MAX,
    SNAPSHOT_DAYS_MIN,
    SYNC_INTERVAL_MAX,
    SYNC_INTERVAL_MIN,
    get_setting,
    snapshot_hour_minute,
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

RunKind = Literal["full", "incremental", "snapshot"]
RUN_KINDS: tuple[RunKind, ...] = ("full", "incremental", "snapshot")


class KeysMissing(Exception):
    """The store has no saved key pair."""


ClientFactory = Callable[[StoreRow], WooClient]


class StopSignal(Protocol):
    """`threading.Event` is one."""

    def is_set(self) -> bool: ...

    def wait(self, timeout: float | None = None) -> bool: ...

    def set(self) -> None: ...


@dataclass(frozen=True)
class RunPlan:
    """What one run does. `night` (a snapshot only) is the local date it is for; `stores` limits it to those store
    ids (None: every live store); `scheduled` is True for the scheduler's runs (False: the owner's Sync now)."""

    kind: RunKind = "full"
    night: str | None = None
    stores: frozenset[int] | None = None
    scheduled: bool = False

    def __post_init__(self) -> None:
        if self.kind not in RUN_KINDS:
            raise ValueError("unknown run kind")
        if (self.kind == "snapshot") != (self.night is not None):
            raise ValueError("a snapshot run, and only one, has a night")


FULL_PLAN = RunPlan()


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
    kind: RunKind | None = None
    night: str | None = None


@dataclass(frozen=True)
class SyncSettings:
    interval_minutes: int
    snapshot_time: SnapshotTime


def sync_settings(connection: sqlite3.Connection) -> SyncSettings:
    """`sync_interval_minutes` and `snapshot_time` as stored, each its default when the stored value isn't valid."""
    try:
        interval = get_setting(connection, "sync_interval_minutes")
    except ValueError:
        interval = None
    if type(interval) is not int or not SYNC_INTERVAL_MIN <= interval <= SYNC_INTERVAL_MAX:
        interval = int(DEFAULTS["sync_interval_minutes"])
    try:
        hour, minute = snapshot_hour_minute(get_setting(connection, "snapshot_time"))
    except ValueError, TypeError:
        hour, minute = snapshot_hour_minute(str(DEFAULTS["snapshot_time"]))
    return SyncSettings(interval, SnapshotTime(hour, minute))


def retention_days(connection: sqlite3.Connection) -> int:
    """`snapshot_retention_days`, or its default when the stored value isn't valid."""
    try:
        value = get_setting(connection, "snapshot_retention_days")
    except ValueError:
        value = None
    if type(value) is int and SNAPSHOT_DAYS_MIN <= value <= SNAPSHOT_DAYS_MAX:
        return value
    return int(DEFAULTS["snapshot_retention_days"])


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
        on_changes: ChangeSink | None = None,
        local: LocalTime | None = None,
    ) -> None:
        self._open = open_connection
        self._factory = client_factory
        self._slots = slots
        self._now = now
        self._monotonic = monotonic
        self._make_stop = make_stop
        self._on_changes = on_changes
        self._local = local if local is not None else LocalTime()
        self._stop: StopSignal = make_stop()
        self._lock = threading.Lock()
        self._state = RunState()
        self._thread: threading.Thread | None = None
        self._closed = False
        self._last_started: dict[RunKind, datetime] = {}

    def state(self) -> RunState:
        with self._lock:
            return replace(self._state, outcomes=dict(self._state.outcomes))

    def last_started(self, kind: RunKind) -> datetime | None:
        """When the last run of that kind started (since this runner was made)."""
        with self._lock:
            return self._last_started.get(kind)

    @property
    def busy(self) -> bool:
        with self._lock:
            return self._thread is not None and self._thread.is_alive()

    def start(self, plan: RunPlan | None = None) -> bool:
        """Start a run on its own thread (a full read when no plan is given). False when one is running (or a stopped
        one hasn't ended yet), and always after `stop()`: the app is shutting down, so no run may begin."""
        chosen = plan if plan is not None else FULL_PLAN
        with self._lock:
            if self._closed or (self._thread is not None and self._thread.is_alive()):
                return False
            self._stop = self._make_stop()
            moment = self._now()
            self._last_started[chosen.kind] = moment
            self._state = RunState(running=True, started_at=to_iso(moment), kind=chosen.kind, night=chosen.night)
            self._thread = threading.Thread(target=self._run, args=(chosen,), name="catalog-sync", daemon=True)
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

    def _run(self, plan: RunPlan) -> None:
        try:
            with closing(self._open()) as connection:
                stores = list_live(connection)
            for row in stores:
                if plan.stores is not None and row.id not in plan.stores:
                    continue
                if self._stop.is_set():
                    break
                outcome = self._read_one(row, plan)
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

    def _read_one(self, listed: StoreRow, plan: RunPlan = FULL_PLAN) -> str | None:
        """Read and save one store; its outcome. Never raises. The store's busy slot is held for the whole read."""
        with self._lock:
            self._state = replace(self._state, current=StoreProgress(listed.id, 0, 0, 0))
        try:
            skipped = self._skip_reason(listed.id, plan)  # before the slot: a skipped store never waits for it
        except sqlite3.Error as error:
            _log.error("Store %s %s: database_error (%s)", listed.code, _what(plan), type(error).__name__)
            return self._record_on_fresh_connection(listed, plan, "database_error")
        if skipped is not None:
            return self._skipped(listed, plan, skipped)
        refused = self._claim(listed.id)
        if refused is not None:
            _log.info("Store %s %s: %s (skipped)", listed.code, _what(plan), refused)
            return refused
        try:
            return self._read_claimed(listed, plan)
        finally:
            self._slots.release(listed.id)

    def _skip_reason(self, store_id: int, plan: RunPlan) -> str | None:
        """Why the store is skipped as it is now, or None. Checked before its busy slot is taken and again after
        (`_read_claimed`), since it can change while the turn waits."""
        with closing(self._open()) as connection:
            row = get_store(connection, store_id)
            if row is None:
                return "store_removed"
            if row.state != "active":
                return "paused"
            return _state_skip(plan, sync_state(connection, store_id))

    def _skipped(self, row: StoreRow, plan: RunPlan, reason: str) -> str:
        """A store skipped: logged, and a snapshot records the night as skipped (a removed store records nothing)."""
        _log.info("Store %s %s: %s (skipped)", row.code, _what(plan), reason)
        if plan.kind == "snapshot" and plan.night is not None and reason != "store_removed":
            try:
                with closing(self._open()) as connection:
                    snapshots.record_skipped(connection, row.id, plan.night, reason=reason, at=to_iso(self._now()))
            except Exception as error:
                _log.error("Store %s: the outcome couldn't be recorded (%s)", row.code, type(error).__name__)
        return reason

    def _claim(self, store_id: int) -> str | None:
        """Take the store's busy slot, waiting while a Test connection or an edit holds it (at most
        `CLAIM_WAIT_SECONDS`). None when taken; else `busy`, or `stopped` when the app shuts down meanwhile. Neither
        counts nor uses a snapshot attempt: the night stays due."""
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

    def _read_claimed(self, listed: StoreRow, plan: RunPlan) -> str | None:
        row = listed  # the code the log names, until the current row is read
        client: WooClient | None = None
        try:
            current, client, failure = self._current(listed.id)
            if current is None:
                return self._skipped(listed, plan, "store_removed")
            row = current
            if row.state != "active":
                return self._skipped(row, plan, "paused")
            with closing(self._open()) as connection:
                state = sync_state(connection, row.id)
                skipped = _state_skip(plan, state)
                if skipped is not None:
                    return self._skipped(row, plan, skipped)
                if plan.kind == "incremental" and state is not None and state.watermark_gmt is not None:
                    return self._incremental(connection, row, client, failure, state.watermark_gmt)
                if plan.kind == "snapshot" and plan.night is not None:
                    return self._snapshot(connection, row, client, failure, plan.night)
                if plan.kind != "full":  # not reached: `_state_skip` and `RunPlan` see to it
                    return self._skipped(row, plan, "internal")
                record_read_started(connection, row.id, to_iso(self._now()))
                if failure is not None or client is None:
                    return self._failed(connection, row, CatalogRead(failure or "internal"))
                if address_changed(connection, row.id, row.url):
                    return self._failed(connection, row, CatalogRead("address_changed"))  # no request is sent
                return self._read_and_save(connection, row, client)
        except AddressMoved:
            return self._record_on_fresh_connection(row, plan, "address_changed")
        except StoreRemoved:
            return self._record_on_fresh_connection(row, plan, "store_removed")
        except snapshots.SnapshotTooLarge:
            return self._record_on_fresh_connection(row, plan, "snapshot_too_large")
        except sqlite3.Error as error:
            _log.error("Store %s %s: database_error (%s)", row.code, _what(plan), type(error).__name__)
            return self._record_on_fresh_connection(row, plan, "database_error")
        except Exception as error:  # a bug (or a change sink's) must not stop the other stores; its type is logged
            _log.error("Store %s %s: internal (%s)", row.code, _what(plan), type(error).__name__)
            return self._record_on_fresh_connection(row, plan, "internal")
        finally:
            if client is not None:
                _close_quietly(client)

    def _record_on_fresh_connection(self, row: StoreRow, plan: RunPlan, reason: str) -> str:
        """Record an outcome the read's own connection may not be able to (it failed on that connection). A second
        failure is only logged: the outcome is still reported in `GET /api/sync`'s `this_run`. Every reason that
        arrives here never counts (`db.catalog.NOT_COUNTED`)."""
        at = to_iso(self._now())
        try:
            with closing(self._open()) as connection:
                if plan.kind == "incremental":
                    record_incremental_failed(connection, row.id, reason=reason, http_status=None, at=at)
                elif plan.kind == "snapshot" and plan.night is not None:
                    self._night_failed(connection, row, plan.night, reason, None)
                else:
                    record_read_failed(connection, row.id, reason=reason, http_status=None, pages=0, total=None, at=at)
        except Exception as error:
            _log.error("Store %s: the outcome couldn't be recorded (%s)", row.code, type(error).__name__)
        if reason in ("address_changed", "store_removed") and plan.kind == "full":
            log_read(row.code, CatalogRead(reason))
        elif reason in ("address_changed", "store_removed", "snapshot_too_large"):
            _log.warning("Store %s %s: %s", row.code, _what(plan), reason)
        return reason

    def _paused_now(self, row: StoreRow, paused: bool) -> None:
        if paused:
            _log.warning("Store %s: 10 failed reads in a row; the store's sync is now auto-paused", row.code)

    def _read_and_save(self, connection: sqlite3.Connection, row: StoreRow, client: WooClient) -> str | None:
        result = read_catalog(
            client,
            spacing_ms=row.spacing_ms,
            stop=self._stop,
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
            seconds=result.seconds,
        )
        log_read(row.code, result)
        return None

    def _failed(self, connection: sqlite3.Connection, row: StoreRow, result: CatalogRead) -> str:
        reason = result.reason or "internal"
        paused = record_read_failed(
            connection,
            row.id,
            reason=reason,
            http_status=result.http_status,
            pages=result.pages,
            total=result.total,
            at=to_iso(self._now()),
        )
        log_read(row.code, result)
        self._paused_now(row, paused and reason != "auto_paused")
        return reason

    # ---- the incremental (SYNC-01) ---------------------------------------------------------------------------------

    def _incremental(
        self,
        connection: sqlite3.Connection,
        row: StoreRow,
        client: WooClient | None,
        failure: str | None,
        watermark: str,
    ) -> str | None:
        record_incremental_started(connection, row.id, to_iso(self._now()))
        if failure is not None or client is None:
            return self._incremental_failed(connection, row, CatalogRead(failure or "internal"))
        if address_changed(connection, row.id, row.url):
            return self._incremental_failed(connection, row, CatalogRead("address_changed"))
        result = read_incremental(
            client,
            watermark=watermark,
            spacing_ms=row.spacing_ms,
            stop=self._stop,
            progress=self._progress(row.id),
            monotonic=self._monotonic,
            now=self._now,
        )
        if result.ok and self._stop.is_set():
            result = replace(result, reason="stopped", products=())
        if not result.ok:
            return self._incremental_failed(connection, row, result)
        summary = save_incremental(
            connection,
            row.id,
            result.products,
            at=to_iso(self._now()),
            read_url=row.url,
            seconds=result.seconds,
            sink=self._on_changes,
        )
        log_incremental(row.code, result, summary.updated + summary.added)
        self._report(row, list(summary.changes))
        return None

    def _incremental_failed(self, connection: sqlite3.Connection, row: StoreRow, result: CatalogRead) -> str:
        reason = result.reason or "internal"
        paused = record_incremental_failed(
            connection, row.id, reason=reason, http_status=result.http_status, at=to_iso(self._now())
        )
        log_incremental(row.code, result, 0)
        self._paused_now(row, paused)
        return reason

    # ---- the snapshot (SYNC-03, SYNC-04) ---------------------------------------------------------------------------

    def _snapshot(
        self,
        connection: sqlite3.Connection,
        row: StoreRow,
        client: WooClient | None,
        failure: str | None,
        night: str,
    ) -> str | None:
        started = self._now()
        try:
            attempt = snapshots.start_attempt(connection, row.id, night, to_iso(started))
        except ValueError:
            held = snapshots.night_row(connection, row.id, night)
            if held is not None and held.state == "running":  # its last attempt was cut off (the app ended)
                snapshots.record_failed(
                    connection,
                    row.id,
                    night,
                    reason="interrupted",
                    http_status=None,
                    at=self._now(),
                    attempt=held.attempts,
                )
                _log.warning("Store %s snapshot of %s: interrupted (no attempt left)", row.code, night)
                return "interrupted"
            _log.info("Store %s snapshot of %s: done (skipped)", row.code, night)
            return "night_done"
        if failure is not None or client is None:
            return self._snapshot_failed(connection, row, night, attempt, SnapshotRead(failure or "internal"))
        if address_changed(connection, row.id, row.url):
            return self._snapshot_failed(connection, row, night, attempt, SnapshotRead("address_changed"))
        expected, catalog_size = snapshots.expected_products(connection, row.id, night)
        settings = sync_settings(connection)
        result = read_snapshot(
            client,
            spacing_ms=row.spacing_ms,
            stop=self._stop,
            expected=expected,
            catalog_size=catalog_size,
            progress=self._progress(row.id),
            monotonic=self._monotonic,
            now=self._now,
        )
        if result.ok and self._stop.is_set():
            result = replace(result, reason="stopped", products=(), variations=(), deleted=())
        if not result.ok:
            return self._snapshot_failed(connection, row, night, attempt, result)
        latest = snapshots.latest_allowed_night(night_of(started, self._local, settings.snapshot_time))
        try:
            summary = snapshots.save_snapshot(
                connection,
                row.id,
                night,
                result.products,
                {wc_id: rows for wc_id, rows in result.variations},
                listing=result.listing or "include_status",
                at=to_iso(self._now()),
                read_url=row.url,
                retention_days=retention_days(connection),
                deleted=result.deleted,
                latest_night=latest,
                sink=self._on_changes,
            )
        except snapshots.NightAhead:
            _log.warning("Store %s snapshot of %s: refused, the night is ahead of this PC's clock", row.code, night)
            return self._snapshot_failed(connection, row, night, attempt, SnapshotRead("internal"))
        log_snapshot(row.code, night, attempt, result)
        self._report(row, list(summary.catalog.changes))
        return None

    def _snapshot_failed(
        self, connection: sqlite3.Connection, row: StoreRow, night: str, attempt: int, result: SnapshotRead
    ) -> str:
        reason = result.reason or "internal"
        self._night_failed(connection, row, night, reason, result.http_status, attempt)
        log_snapshot(row.code, night, attempt, result)
        return reason

    def _night_failed(
        self,
        connection: sqlite3.Connection,
        row: StoreRow,
        night: str,
        reason: str,
        http_status: int | None,
        attempt: int | None = None,
    ) -> None:
        """Record a failed attempt: counted once, then the same-night retry rule (`db.snapshots.record_failed`)."""
        if attempt is None:
            held = snapshots.night_row(connection, row.id, night)
            if held is None or held.state != "running":
                return  # no attempt was started: nothing to record
            attempt = held.attempts
        paused = snapshots.record_failed(
            connection, row.id, night, reason=reason, http_status=http_status, at=self._now(), attempt=attempt
        )
        self._paused_now(row, paused and reason != "auto_paused")

    def _report(self, row: StoreRow, changes: list[Change]) -> None:
        """The counts of the changes a save handed on (inside its transaction), for the log."""
        if not changes:
            return
        tally = counts(changes)
        _log.info(
            "Store %s: changes found outside ShelfSync (changed %d, trashed %d, deleted %d)",
            row.code,
            tally["changed"],
            tally["trashed"],
            tally["deleted"],
        )


def _what(plan: RunPlan) -> str:
    return {"full": "catalog read", "incremental": "incremental read", "snapshot": f"snapshot of {plan.night}"}[
        plan.kind
    ]


def _state_skip(plan: RunPlan, state: SyncStateRow | None) -> str | None:
    """Why the sync state skips the store for this run: auto-paused, or (an incremental) no watermark, (a snapshot)
    no full read that worked yet."""
    if state is not None and state.auto_paused_at is not None:
        return "auto_paused"
    if plan.kind == "incremental" and (state is None or state.watermark_gmt is None):
        return "no_full_read"
    if plan.kind == "snapshot" and (state is None or state.last_ok_at is None):
        return "no_catalog"
    return None


def _close_quietly(client: WooClient) -> None:
    try:
        client.close()
    except Exception as error:  # a close that fails changes nothing for the run
        _log.debug("A store client didn't close cleanly (%s)", type(error).__name__)

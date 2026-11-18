"""The sync scheduler (SYNC-01, SYNC-03): one thread in the app's lifespan that starts the scheduled runs through the
runner (`catalog/runner.py`), so every read keeps its one-run-at-a-time rule, the busy slots and the address guard.

It looks at the wall clock every 60 seconds (the `db/daily.py` pattern, so a sleep is noticed within a minute) and, when
no run is going:
1. starts the **snapshot** of the current night for the stores it is due on (`catalog/schedule.py`), if any;
2. otherwise starts an **incremental** when one interval (`sync_interval_minutes`) has passed since the last incremental
   started (Sync now's included) or since the scheduler started, and some active store can have one (a watermark, not
   auto-paused).
Nothing overlaps: a run that is due while another runs waits for the next check after it ends. Both settings are read
at each check, so a change applies within a minute. A stored value that isn't valid is its default.
"""

import logging
import sqlite3
import threading
from collections.abc import Callable
from contextlib import closing
from dataclasses import dataclass
from datetime import datetime

from shelfsync.catalog.runner import RunPlan, SyncRunner, sync_settings
from shelfsync.catalog.schedule import incremental_due, next_slot, night_due, night_of
from shelfsync.clock import to_iso, utc_now
from shelfsync.db import catalog as db
from shelfsync.db.daily import LocalTime
from shelfsync.db.snapshots import nights_of
from shelfsync.db.stores import list_live

_log = logging.getLogger("shelfsync.catalog")

CHECK_SECONDS = 60.0
STOP_WAIT_SECONDS = 2.0


@dataclass(frozen=True)
class NextRuns:
    """When the scheduled runs come next (UTC): the incremental (None: no store can have one) and each live store's
    snapshot (now when it is due, its retry time when it waits for one, else the next snapshot time)."""

    incremental: datetime | None
    snapshots: dict[int, datetime]
    night: str


class SyncScheduler:
    def __init__(
        self,
        runner: SyncRunner,
        open_connection: Callable[[], sqlite3.Connection],
        *,
        now: Callable[[], datetime] = utc_now,
        local: LocalTime | None = None,
        interval: float = CHECK_SECONDS,
    ) -> None:
        self._runner = runner
        self._open = open_connection
        self._now = now
        self._local = local if local is not None else LocalTime()
        self._interval = interval
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._lock = threading.Lock()  # one check at a time (the loop's, a test's)
        self._started_at: datetime | None = None

    # ---- what is due ----------------------------------------------------------------------------------------------

    def _since(self, now: datetime) -> datetime:
        """When the scheduler started; moved back to `now` when the clock went back past it (F6), so the incremental
        is due once now and then every interval again, not at every check."""
        if self._started_at is None or self._started_at > now:
            self._started_at = now
        return self._started_at

    def snapshot_plan(self, now: datetime) -> RunPlan | None:
        with closing(self._open()) as connection:
            settings = sync_settings(connection)
            night = night_of(now, self._local, settings.snapshot_time)
            stores = list_live(connection)
            rows = nights_of(connection, night)
        stamp = to_iso(now)
        due = frozenset(
            row.id
            for row in stores
            if night_due(
                rows[row.id].state if row.id in rows else None,
                rows[row.id].next_try_at if row.id in rows else None,
                stamp,
            )
        )
        return RunPlan("snapshot", night=night, stores=due, scheduled=True) if due else None

    def _can_increment(self, connection: sqlite3.Connection) -> bool:
        active = db.active_store_ids(connection)
        states = db.sync_states(connection)
        return any(
            (state := states.get(store_id)) is not None
            and state.watermark_gmt is not None
            and state.auto_paused_at is None
            for store_id in active
        )

    def incremental_at(self, now: datetime) -> datetime | None:
        """When the next scheduled incremental is due, or None when no store can have one."""
        with closing(self._open()) as connection:
            settings = sync_settings(connection)
            if not self._can_increment(connection):
                return None
        return incremental_due(
            now, self._since(now), self._runner.last_started("incremental"), settings.interval_minutes
        )

    def next_runs(self) -> NextRuns:
        now = self._now()
        with self._lock:
            incremental = self.incremental_at(now)
        with closing(self._open()) as connection:
            settings = sync_settings(connection)
            night = night_of(now, self._local, settings.snapshot_time)
            stores = list_live(connection)
            rows = nights_of(connection, night)
        stamp = to_iso(now)
        upcoming = next_slot(now, self._local, settings.snapshot_time)
        snapshots: dict[int, datetime] = {}
        for store in stores:
            row = rows.get(store.id)
            if night_due(row.state if row else None, row.next_try_at if row else None, stamp):
                snapshots[store.id] = now
            elif row is not None and row.state == "retry" and row.next_try_at is not None:
                snapshots[store.id] = datetime.fromisoformat(row.next_try_at)
            else:
                snapshots[store.id] = upcoming
        return NextRuns(max(incremental, now) if incremental is not None else None, snapshots, night)

    # ---- one check ------------------------------------------------------------------------------------------------

    def tick(self) -> RunPlan | None:
        """One check: start what is due (the module text says what). Returns the plan started, or None."""
        with self._lock:
            if self._runner.busy or self._runner.closed:
                return None
            now = self._now()
            self._since(now)
            plan = self.snapshot_plan(now)
            if plan is not None:
                return plan if self._runner.start(plan) else None
            due = self.incremental_at(now)
            if due is not None and now >= due:
                incremental = RunPlan("incremental", scheduled=True)
                return incremental if self._runner.start(incremental) else None
            return None

    # ---- start and stop -------------------------------------------------------------------------------------------

    def start(self) -> None:
        if self._thread is not None and self._thread.is_alive():
            self._stop.clear()
            return
        self._stop.clear()
        self._started_at = self._now()
        self._thread = threading.Thread(target=self._loop, name="sync-scheduler", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        thread = self._thread
        if thread is not None:
            thread.join(timeout=STOP_WAIT_SECONDS)

    def _loop(self) -> None:
        while not self._stop.is_set():
            try:
                self.tick()
            except Exception as error:  # nothing here may stop the schedule or the app
                _log.warning("The sync schedule check failed: %s", type(error).__name__)
            if self._stop.wait(self._interval):
                return

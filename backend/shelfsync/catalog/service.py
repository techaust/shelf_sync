"""What the Sync, Catalog and wizard routes talk to (CAT-01, CAT-02, CAT-04, CAT-05, APL-12, UI-WIZ).

`CatalogService` owns the background run (`SyncRunner`) and reads the catalog tables. `WizardService` decides each
wizard step's "done" from real state where it can:
- **stores:** at least one store is saved;
- **storage:** the region and bucket are saved and both S3 key pairs are in Credential Manager (what the Storage Test
  needs, 13); the check is given as a callable (`storage_ready`) by whoever wires the app;
- **test:** the owner's mark (`PUT /api/wizard/test`): nothing in the data says the owner has seen both tests pass;
- **catalog:** every active store has a full read that worked, and there is at least one active store.
The first step not done is where the wizard starts; an install that already has stores and storage starts at `test`.
**`finished`** (Lead (proposed)) is the owner's mark the screen sets on leaving the catalog step: once it is set the
wizard is done (`current` stays null) whatever changes later (a store added, a read that failed).
"""

import sqlite3
import threading
import time
import uuid
import weakref
from collections.abc import Callable
from contextlib import closing
from dataclasses import dataclass
from datetime import datetime

import httpx

from shelfsync.apply.woocommerce import WooClient
from shelfsync.catalog.runner import (
    ChangeSink,
    ClientFactory,
    KeysMissing,
    RunKind,
    RunPlan,
    RunState,
    StopSignal,
    SyncRunner,
)
from shelfsync.catalog.scheduler import SyncScheduler
from shelfsync.clock import utc_now
from shelfsync.db import catalog as db
from shelfsync.db.connection import connect
from shelfsync.db.daily import LocalTime
from shelfsync.db.migrate import migrate
from shelfsync.db.snapshots import NightRow, latest_nights, restorable_nights
from shelfsync.db.stores import StoreRow, get_store, list_live, live_store_count
from shelfsync.db.wizard import marks, set_mark
from shelfsync.paths import DataPaths
from shelfsync.platform.secrets import MemorySecretStore, SecretStore
from shelfsync.secure.credentials import StoreCredentials
from shelfsync.secure.redact import register_secret
from shelfsync.store_service import BusySlots, StoreService


def store_clients(
    secrets: SecretStore,
    transport: Callable[[], httpx.BaseTransport] | None = None,
    monotonic: Callable[[], float] = time.monotonic,
) -> ClientFactory:
    """The app's client factory: each store's saved key pair from Credential Manager. `KeysMissing` when either value
    isn't saved; `SecretStoreError` (raised by `StoreCredentials.read`, never swallowed) when Credential Manager can't
    be read, which the runner reports as `secrets_unavailable`. Both values are registered with the log redaction
    before use. `transport` makes a transport per client (tests only)."""
    credentials = StoreCredentials(secrets)

    def build(row: StoreRow) -> WooClient:
        key, secret = credentials.read(row.id)
        if key is None or secret is None:
            raise KeysMissing
        register_secret(key)
        register_secret(secret)
        return WooClient(
            row.url, key, secret, transport=transport() if transport is not None else None, monotonic=monotonic
        )

    return build


def build_catalog_service(paths: DataPaths, secrets: SecretStore, stores: StoreService) -> CatalogService:
    """The service the running app uses: the data folder's database, the stores' keys in Credential Manager, and
    **the stores service's own busy slots**, so the runner holds a store's slot for its whole read and an edit, a
    removal or a Test connection of that store answers `busy` meanwhile (m3.1 review 1, finding 1; review 2,
    finding 1: built here, in one place, so no caller can leave the slots out). m3.2: with the sync scheduler, which
    the sync router's lifespan starts and stops."""
    return CatalogService(lambda: connect(paths.database), store_clients(secrets), slots=stores.slots, scheduled=True)


def _memory_database(name: str) -> tuple[Callable[[], sqlite3.Connection], sqlite3.Connection]:
    uri = f"file:shelfsync-{name}-{uuid.uuid4().hex}?mode=memory&cache=shared"

    def open_connection() -> sqlite3.Connection:
        connection = sqlite3.connect(uri, uri=True, isolation_level=None, timeout=5.0, check_same_thread=False)
        connection.execute("PRAGMA foreign_keys = ON")
        return connection

    keeper = open_connection()
    migrate(keeper)
    return open_connection, keeper


@dataclass(frozen=True)
class StoreSync:
    """One live store's sync state for `GET /api/sync`."""

    store: StoreRow
    state: db.SyncStateRow | None
    this_run: str | None  # this (or the last) run's outcome for it; None also when the run didn't reach it
    reached: bool  # whether the run reached it
    night: NightRow | None = None  # its latest snapshot night
    next_incremental_at: datetime | None = None  # None: no scheduler, or no incremental for it
    next_snapshot_at: datetime | None = None  # None: no scheduler


@dataclass(frozen=True)
class SyncStatus:
    run: RunState
    stores: list[StoreSync]


@dataclass(frozen=True)
class StoreSnapshots:
    """The nights one of an item's store products can be restored to (local dates, newest first)."""

    store_id: int
    wc_id: int
    nights: list[str]


def choose_kind(active: set[int], states: dict[int, db.SyncStateRow]) -> RunKind:
    """SYNC-05: Sync now is an incremental once every active store has had a full read that worked (and so has a
    watermark), else a full read. Pure."""
    built = bool(active) and all(
        (state := states.get(store_id)) is not None and state.last_ok_at is not None and state.watermark_gmt is not None
        for store_id in active
    )
    return "incremental" if built else "full"


@dataclass(frozen=True)
class ItemSummary:
    item: db.ItemRow
    links: list[db.LinkRow]
    slot_count: int
    on_every_active_store: bool


@dataclass(frozen=True)
class ItemDetail:
    item: db.ItemRow
    links: list[db.LinkRow]
    slots: list[db.SlotRow]


class CatalogService:
    def __init__(
        self,
        open_connection: Callable[[], sqlite3.Connection],
        client_factory: ClientFactory,
        *,
        slots: BusySlots,
        now: Callable[[], datetime] = utc_now,
        monotonic: Callable[[], float] = time.monotonic,
        make_stop: Callable[[], StopSignal] = threading.Event,
        scheduled: bool = False,
        local: LocalTime | None = None,
        on_changes: ChangeSink | None = None,
    ) -> None:
        self._open = open_connection
        self._slug_lock = threading.Lock()
        self.runner = SyncRunner(
            open_connection,
            client_factory,
            now=now,
            monotonic=monotonic,
            make_stop=make_stop,
            slots=slots,
            on_changes=on_changes,
        )
        # The scheduler (m3.2) exists for every service, so `GET /api/sync` can say when runs come next; only a
        # `scheduled` service (the app's) starts its thread in the lifespan. Tests call `tick()` themselves.
        self.scheduler = SyncScheduler(self.runner, open_connection, now=now, local=local)
        self._scheduled = scheduled
        self._keeper: sqlite3.Connection | None = None  # holds a development database in memory

    @classmethod
    def in_memory(cls, secrets: SecretStore | None = None) -> CatalogService:
        """A service on a private in-memory database (no stores, so a run reads nothing): what `create_app` uses when
        it isn't given one, so no test touches a file, Credential Manager or a network by accident."""
        open_connection, keeper = _memory_database("catalog")
        service = cls(
            open_connection,
            store_clients(secrets if secrets is not None else MemorySecretStore()),
            slots=BusySlots(),  # its own: there is no stores service beside it
        )
        service._keeper = keeper
        weakref.finalize(service, keeper.close)
        return service

    # ---- sync ------------------------------------------------------------------------------------------------------

    def start_sync(self, kind: RunKind | None = None) -> RunKind | None:
        """Start a run in the background: `full`, `incremental`, or (None) the one `choose_kind` picks (SYNC-05). The
        kind started, or None when one is already running (or the app is stopping)."""
        if kind is None:
            with closing(self._open()) as connection:
                kind = choose_kind(db.active_store_ids(connection), db.sync_states(connection))
        if kind == "snapshot":
            raise ValueError("a snapshot is the scheduler's")
        return kind if self.runner.start(RunPlan(kind)) else None

    def start_scheduler(self) -> None:
        """The lifespan starts the scheduler's thread for the app's service only (`scheduled`)."""
        if self._scheduled:
            self.scheduler.start()

    def stop(self) -> None:
        self.scheduler.stop()  # first, so no run starts while the runner stops
        self.runner.stop()

    def reopen(self) -> None:
        self.runner.reopen()

    @property
    def closed(self) -> bool:
        return self.runner.closed

    def sync_status(self) -> SyncStatus:
        run = self.runner.state()
        upcoming = self.scheduler.next_runs()
        with closing(self._open()) as connection:
            stores = list_live(connection)
            states = db.sync_states(connection)
            nights = latest_nights(connection)
        entries: list[StoreSync] = []
        for row in stores:
            state = states.get(row.id)
            can_increment = (
                row.state == "active"
                and state is not None
                and state.watermark_gmt is not None
                and state.auto_paused_at is None
            )
            entries.append(
                StoreSync(
                    row,
                    state,
                    run.outcomes.get(row.id),
                    row.id in run.outcomes,
                    nights.get(row.id),
                    upcoming.incremental if can_increment else None,
                    upcoming.snapshots.get(row.id),
                )
            )
        return SyncStatus(run, entries)

    def snapshots(self, item_id: int) -> list[StoreSnapshots] | None:
        """The nights each of an item's store products can be restored to (APL-14's dates). None when there is no
        such item, or no store that isn't removed holds it (as `GET /api/catalog/{id}` answers 404)."""
        with closing(self._open()) as connection:
            if db.item(connection, item_id) is None:
                return None
            links = db.links(connection, item_id)
            if not links:
                return None
            return [
                StoreSnapshots(link.store_id, link.wc_id, restorable_nights(connection, link.store_id, link.wc_id))
                for link in links
            ]

    def resume(self, store_id: int) -> bool:
        """Clear a store's auto-pause (and its failures in a row). False when there is no such live store."""
        with closing(self._open()) as connection:
            if get_store(connection, store_id) is None:
                return False
            db.resume_store(connection, store_id)
        return True

    # ---- the catalog -----------------------------------------------------------------------------------------------

    def items(self) -> list[ItemSummary]:
        with closing(self._open()) as connection:
            rows = db.items(connection)
            links = db.links(connection)
            counts = db.slot_counts(connection)
            active = db.active_store_ids(connection)
        by_item: dict[int, list[db.LinkRow]] = {}
        for link in links:  # links on removed stores aren't here, so an item only they held is left out
            by_item.setdefault(link.item_id, []).append(link)
        return [self._summary(row, by_item[row.id], counts.get(row.id, 0), active) for row in rows if row.id in by_item]

    @staticmethod
    def _summary(row: db.ItemRow, links: list[db.LinkRow], slots: int, active: set[int]) -> ItemSummary:
        present = {link.store_id for link in links if not link.gone}
        return ItemSummary(row, links, slots, bool(active) and active <= present)

    def item(self, item_id: int) -> ItemDetail | None:
        """One item, or None when there is none or no store that isn't removed holds it (as `GET /api/catalog`
        leaves it out)."""
        with closing(self._open()) as connection:
            row = db.item(connection, item_id)
            links = db.links(connection, item_id) if row is not None else []
            if row is None or not links:
                return None
            return ItemDetail(row, links, db.slots(connection, item_id))

    def set_slug(self, item_id: int, slug: str) -> ItemSummary | None:
        """CAT-04: the canonical slug only; nothing changes on any store. None when there is no such item, or no
        store that isn't removed holds it; `db.SlugTaken` when another item has it."""
        with self._slug_lock, closing(self._open()) as connection:
            connection.execute("BEGIN IMMEDIATE")  # the check and the change together
            try:
                held = bool(db.links(connection, item_id))
                changed = held and db.set_canonical_slug(connection, item_id, slug)
                connection.execute("COMMIT")
            except BaseException:
                connection.execute("ROLLBACK")
                raise
            if not changed:
                return None
            row = db.item(connection, item_id)
            links = db.links(connection, item_id)
            counts = db.slot_counts(connection)
            active = db.active_store_ids(connection)
        if row is None:  # can't happen: it was just updated
            return None
        return self._summary(row, links, counts.get(item_id, 0), active)


# ---- the wizard ----------------------------------------------------------------------------------------------------

WIZARD_STEPS = ("stores", "storage", "test", "catalog")
MARKED_STEPS = frozenset({"test", "finished"})  # the owner's marks; the other steps' "done" comes from the data


@dataclass(frozen=True)
class WizardStep:
    step: str
    done: bool
    from_state: bool  # True: read from the data; False: the owner's mark


@dataclass(frozen=True)
class WizardState:
    steps: list[WizardStep]
    current: str | None  # the first step not done; None when every step up to the catalog is done, or finished
    finished: bool = False  # the owner left the catalog step: the wizard is over


def wizard_state(*, has_store: bool, storage_ready: bool, catalog_built: bool, marked: dict[str, bool]) -> WizardState:
    """Each step's "done" (the module text says how) and the first one not done. Pure."""
    done = {
        "stores": has_store,
        "storage": storage_ready,
        "test": marked.get("test", False),
        "catalog": catalog_built,
    }
    steps = [WizardStep(step, done[step], step not in MARKED_STEPS) for step in WIZARD_STEPS]
    finished = marked.get("finished", False)
    current = None if finished else next((step.step for step in steps if not step.done), None)
    return WizardState(steps, current, finished)


class WizardService:
    def __init__(self, open_connection: Callable[[], sqlite3.Connection], storage_ready: Callable[[], bool]) -> None:
        self._open = open_connection
        self._storage_ready = storage_ready
        self._keeper: sqlite3.Connection | None = None

    @classmethod
    def in_memory(cls) -> WizardService:
        open_connection, keeper = _memory_database("wizard")
        service = cls(open_connection, lambda: False)
        service._keeper = keeper
        weakref.finalize(service, keeper.close)
        return service

    def state(self) -> WizardState:
        with closing(self._open()) as connection:
            has_store = live_store_count(connection) > 0
            active = db.active_store_ids(connection)
            states = db.sync_states(connection)
            marked = marks(connection)
        built = bool(active) and all(
            (state := states.get(store_id)) is not None and state.last_ok_at is not None for store_id in active
        )
        return wizard_state(
            has_store=has_store, storage_ready=self._storage_ready(), catalog_built=built, marked=marked
        )

    def mark(self, step: str, done: bool) -> WizardState:
        """Record the owner's mark for a marked step (`ValueError` for any other step)."""
        if step not in MARKED_STEPS:
            raise ValueError("this step's state comes from the data")
        with closing(self._open()) as connection:
            set_mark(connection, step, done)
        return self.state()

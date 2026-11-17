"""What the Sync, Catalog and wizard routes talk to (CAT-01, CAT-02, CAT-04, CAT-05, APL-12, UI-WIZ).

`CatalogService` owns the background run (`SyncRunner`) and reads the catalog tables. `WizardService` decides each
wizard step's "done" from real state where it can:
- **stores:** at least one store is saved;
- **storage:** the region and bucket are saved and both S3 key pairs are in Credential Manager (what the Storage Test
  needs, 13); the check is given as a callable (`storage_ready`) by whoever wires the app;
- **test:** the owner's mark (`PUT /api/wizard/test`): nothing in the data says the owner has seen both tests pass;
- **catalog:** every active store has a full read that worked, and there is at least one active store.
The first step not done is where the wizard starts; an install that already has stores and storage starts at `test`.
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
from shelfsync.catalog.runner import ClientFactory, KeysMissing, RunState, StopSignal, SyncRunner
from shelfsync.clock import utc_now
from shelfsync.db import catalog as db
from shelfsync.db.migrate import migrate
from shelfsync.db.stores import StoreRow, get_store, list_live, live_store_count
from shelfsync.db.wizard import marks, set_mark
from shelfsync.platform.secrets import MemorySecretStore, SecretStore
from shelfsync.secure.credentials import StoreCredentials


def store_clients(
    secrets: SecretStore,
    transport: Callable[[], httpx.BaseTransport] | None = None,
    monotonic: Callable[[], float] = time.monotonic,
) -> ClientFactory:
    """The app's client factory: each store's saved key pair from Credential Manager (`KeysMissing` when there is
    none; `SecretStoreError` when it can't be read). `transport` makes a transport per client (tests only)."""
    credentials = StoreCredentials(secrets)

    def build(row: StoreRow) -> WooClient:
        pair = credentials.pair(row.id)
        if pair is None:
            raise KeysMissing
        return WooClient(
            row.url,
            pair.consumer_key,
            pair.consumer_secret,
            transport=transport() if transport is not None else None,
            monotonic=monotonic,
        )

    return build


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


@dataclass(frozen=True)
class SyncStatus:
    run: RunState
    stores: list[StoreSync]


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
        now: Callable[[], datetime] = utc_now,
        monotonic: Callable[[], float] = time.monotonic,
        make_stop: Callable[[], StopSignal] = threading.Event,
    ) -> None:
        self._open = open_connection
        self._slug_lock = threading.Lock()
        self.runner = SyncRunner(open_connection, client_factory, now=now, monotonic=monotonic, make_stop=make_stop)
        self._keeper: sqlite3.Connection | None = None  # holds a development database in memory

    @classmethod
    def in_memory(cls, secrets: SecretStore | None = None) -> CatalogService:
        """A service on a private in-memory database (no stores, so a run reads nothing): what `create_app` uses when
        it isn't given one, so no test touches a file, Credential Manager or a network by accident."""
        open_connection, keeper = _memory_database("catalog")
        service = cls(open_connection, store_clients(secrets if secrets is not None else MemorySecretStore()))
        service._keeper = keeper
        weakref.finalize(service, keeper.close)
        return service

    # ---- sync ------------------------------------------------------------------------------------------------------

    def start_sync(self) -> bool:
        """Start a full read of every active store in the background; False when one is already running."""
        return self.runner.start()

    def stop(self) -> None:
        self.runner.stop()

    def sync_status(self) -> SyncStatus:
        run = self.runner.state()
        with closing(self._open()) as connection:
            stores = list_live(connection)
            states = db.sync_states(connection)
        return SyncStatus(
            run,
            [StoreSync(row, states.get(row.id), run.outcomes.get(row.id), row.id in run.outcomes) for row in stores],
        )

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
        for link in links:
            by_item.setdefault(link.item_id, []).append(link)
        return [self._summary(row, by_item.get(row.id, []), counts.get(row.id, 0), active) for row in rows]

    @staticmethod
    def _summary(row: db.ItemRow, links: list[db.LinkRow], slots: int, active: set[int]) -> ItemSummary:
        present = {link.store_id for link in links if not link.gone}
        return ItemSummary(row, links, slots, bool(active) and active <= present)

    def item(self, item_id: int) -> ItemDetail | None:
        with closing(self._open()) as connection:
            row = db.item(connection, item_id)
            if row is None:
                return None
            return ItemDetail(row, db.links(connection, item_id), db.slots(connection, item_id))

    def set_slug(self, item_id: int, slug: str) -> ItemSummary | None:
        """CAT-04: the canonical slug only; nothing changes on any store. None when there is no such item;
        `db.SlugTaken` when another item has it."""
        with self._slug_lock, closing(self._open()) as connection:
            if not db.set_canonical_slug(connection, item_id, slug):
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
MARKED_STEPS = frozenset({"test"})  # the steps whose "done" is the owner's mark; the others come from the data


@dataclass(frozen=True)
class WizardStep:
    step: str
    done: bool
    from_state: bool  # True: read from the data; False: the owner's mark


@dataclass(frozen=True)
class WizardState:
    steps: list[WizardStep]
    current: str | None  # the first step not done; None when every step up to the catalog is done


def wizard_state(*, has_store: bool, storage_ready: bool, catalog_built: bool, marked: dict[str, bool]) -> WizardState:
    """Each step's "done" (the module text says how) and the first one not done. Pure."""
    done = {
        "stores": has_store,
        "storage": storage_ready,
        "test": marked.get("test", False),
        "catalog": catalog_built,
    }
    steps = [WizardStep(step, done[step], step not in MARKED_STEPS) for step in WIZARD_STEPS]
    return WizardState(steps, next((step.step for step in steps if not step.done), None))


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

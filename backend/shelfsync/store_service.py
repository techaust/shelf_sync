"""The stores (SET-01, ERR-01): what the Stores API does, with the table (`db/stores.py`), the keys in Credential
Manager (`secure/credentials.py`) and the read client (`apply/woocommerce.py`) behind it.

Rules this module keeps:
- **A save is atomic across the two places.** The row is inserted or updated in an open transaction, the Credential
  Manager entries are written, and only then is the transaction committed; on any failure the transaction is rolled
  back and the entries written are removed (or put back).
- A **host change needs new keys in the same request** (`keys_required`): keys must never go to a server the owner
  didn't give them to.
- Removing a store deletes both Credential Manager entries **first**; if that fails nothing changes. Then the row gets
  `removed_at` (the history from M3 points at store ids).
- **One test per store at a time** (`busy`). A test runs inside the request and writes only its own result row.
- Nothing here logs an address or a value: a store is named by its code.
"""

import ipaddress
import logging
import re
import sqlite3
import threading
import time
import uuid
import weakref
from collections.abc import Callable, Mapping
from contextlib import closing
from dataclasses import dataclass
from datetime import datetime
from typing import Any
from urllib.parse import urlsplit

import httpx

from shelfsync.apply.woocommerce import TOTAL_SECONDS, ReadOutcome, WooClient, run_read_test
from shelfsync.clock import to_iso, utc_now
from shelfsync.db.connection import connect
from shelfsync.db.migrate import migrate
from shelfsync.db.stores import (
    CodeTaken,
    SavedTest,
    StoreRow,
    UrlTaken,
    all_ids,
    get_store,
    insert_store,
    list_live,
    reset_health,
    save_test_result,
    soft_delete,
    update_store,
)
from shelfsync.paths import DataPaths
from shelfsync.platform.secrets import MemorySecretStore, SecretStore, SecretStoreError
from shelfsync.secure.credentials import StoreCredentials
from shelfsync.secure.headers import ErrorCode

_log = logging.getLogger("shelfsync.stores")

MAX_URL_LENGTH = 200
_HOST = re.compile(r"(?=.{1,253}$)[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?(\.[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?)+")
_PATH = re.compile(r"[A-Za-z0-9._~/-]*")  # no `%`: no encoded slashes or dots


class StoreError(Exception):
    """The request can't be done. `status` and `code` become the API's fixed error body."""

    def __init__(self, status: int, code: ErrorCode) -> None:
        super().__init__(code)
        self.status = status
        self.code: ErrorCode = code


def normalize_url(text: str) -> str:
    """`https://host[:port][/path]`, lowercased scheme and host, no trailing slash. ValueError for anything else: not
    https, an IP address or a host without a dot, user information, a query or a fragment, non-ASCII text, or more than
    200 characters."""
    if len(text) > MAX_URL_LENGTH or not text.isascii() or not text.isprintable() or " " in text:
        raise ValueError("not an acceptable store address")
    if "?" in text or "#" in text or "\\" in text:
        raise ValueError("not an acceptable store address")
    parts = urlsplit(text)
    if parts.scheme.lower() != "https" or "@" in parts.netloc:
        raise ValueError("not an acceptable store address")
    host = parts.hostname
    if host is None or _HOST.fullmatch(host) is None or not any(ch.isalpha() for ch in host.rsplit(".", 1)[-1]):
        raise ValueError("not an acceptable store address")
    try:
        ipaddress.ip_address(host)
    except ValueError:
        pass
    else:  # unreachable given the checks above; kept so a change to them can't let an IP literal through
        raise ValueError("not an acceptable store address")
    port = parts.port  # ValueError for a bad port
    if port is not None and not 1 <= port <= 65535:
        raise ValueError("not an acceptable store address")
    path = parts.path.rstrip("/")
    if _PATH.fullmatch(path) is None or "//" in path or any(part in (".", "..") for part in path.split("/")):
        raise ValueError("not an acceptable store address")
    netloc = host if port in (None, 443) else f"{host}:{port}"
    return f"https://{netloc}{path}"


def _authority(url: str) -> str:
    """Host and port: what the keys are tied to."""
    return urlsplit(url).netloc


@dataclass(frozen=True)
class StoreView:
    row: StoreRow
    consumer_key: str | None  # masked
    consumer_secret: str | None  # masked


@dataclass(frozen=True)
class ReadReport:
    outcome: ReadOutcome
    tested_at: str


class StoreService:
    def __init__(
        self,
        *,
        open_connection: Callable[[], sqlite3.Connection],
        secrets: SecretStore,
        transport: httpx.BaseTransport | None = None,
        now: Callable[[], datetime] = utc_now,
        sleep: Callable[[float], None] = time.sleep,
        monotonic: Callable[[], float] = time.monotonic,
    ) -> None:
        self._open = open_connection
        self._credentials = StoreCredentials(secrets)
        self._transport = transport
        self._now = now
        self._sleep = sleep
        self._monotonic = monotonic
        self._busy: set[int] = set()
        self._busy_lock = threading.Lock()
        self._limit_seconds = TOTAL_SECONDS  # a test seam: the whole read test's time limit
        self._grace_seconds = 1.0  # how long past the limit the request waits for the worker to report
        self._keeper: sqlite3.Connection | None = None  # holds a development database in memory

    @classmethod
    def in_memory(
        cls, secrets: SecretStore | None = None, transport: httpx.BaseTransport | None = None
    ) -> StoreService:
        """A service on a private in-memory database and, by default, an in-memory secret store: what `create_app`
        uses when it isn't given one (most tests), so nothing touches a file or Credential Manager."""
        uri = f"file:shelfsync-stores-{uuid.uuid4().hex}?mode=memory&cache=shared"

        def open_connection() -> sqlite3.Connection:
            return sqlite3.connect(uri, uri=True, isolation_level=None, timeout=5.0, check_same_thread=False)

        keeper = open_connection()
        migrate(keeper)
        service = cls(
            open_connection=open_connection,
            secrets=secrets if secrets is not None else MemorySecretStore(),
            transport=transport,
        )
        service._keeper = keeper
        weakref.finalize(service, keeper.close)  # closed when the service is dropped (the database goes with it)
        return service

    # ---- reads -----------------------------------------------------------------------------------------------------

    def _view(self, row: StoreRow) -> StoreView:
        key, secret = self._credentials.masked(row.id)
        return StoreView(row, key, secret)

    def list(self) -> list[StoreView]:
        with closing(self._open()) as connection:
            return [self._view(row) for row in list_live(connection)]

    def get(self, store_id: int) -> StoreView:
        with closing(self._open()) as connection:
            row = get_store(connection, store_id)
        if row is None:
            raise StoreError(404, "not_found")
        return self._view(row)

    def register_secrets(self) -> None:
        """Start-up: every stored key and secret goes into the log redaction. A failure (the database or Credential
        Manager can't be read) is logged as a warning and start-up goes on; the test of that store then answers
        `keys_missing`."""
        try:
            with closing(self._open()) as connection:
                ids = all_ids(connection)
        except sqlite3.Error as error:
            _log.warning(
                "The stores couldn't be listed to register their keys for redaction (%s)", type(error).__name__
            )
            return
        self._credentials.register_all(ids)

    # ---- writes ----------------------------------------------------------------------------------------------------

    def create(
        self,
        *,
        name: str,
        url: str,
        code: str,
        shape: str,
        color: str,
        spacing_ms: int,
        main_button: str,
        consumer_key: str,
        consumer_secret: str,
    ) -> StoreView:
        with closing(self._open()) as connection:
            connection.execute("BEGIN IMMEDIATE")
            store_id: int | None = None
            try:
                store_id = insert_store(
                    connection,
                    name=name,
                    url=url,
                    code=code,
                    shape=shape,
                    color=color,
                    spacing_ms=spacing_ms,
                    main_button=main_button,
                    created_at=to_iso(self._now()),
                )
                self._credentials.save(store_id, consumer_key, consumer_secret)
                connection.execute("COMMIT")
            except UrlTaken:
                _rollback(connection)
                raise StoreError(409, "store_exists") from None
            except CodeTaken:
                _rollback(connection)
                raise StoreError(409, "code_taken") from None
            except SecretStoreError:
                _rollback(connection)
                if store_id is not None:
                    self._credentials.discard(store_id)
                raise StoreError(503, "secrets_unavailable") from None
            except BaseException:
                _rollback(connection)
                if store_id is not None:
                    self._credentials.discard(store_id)
                raise
            row = get_store(connection, store_id)
        if row is None:  # can't happen: the row was just committed
            raise StoreError(404, "not_found")
        _log.info("Store %s was added", row.code)
        return self._view(row)

    # ---- one thing at a time per store -----------------------------------------------------------------------------

    def _claim(self, store_id: int) -> None:
        """Take the store's busy slot, or `busy`. A read test, an edit of the address or the keys, a key replacement
        and a removal each hold it, so none of them can change what another one is working on."""
        with self._busy_lock:
            if store_id in self._busy:
                raise StoreError(409, "busy")
            self._busy.add(store_id)

    def _release(self, store_id: int) -> None:
        with self._busy_lock:
            self._busy.discard(store_id)

    def update(self, store_id: int, changes: Mapping[str, Any], keys: tuple[str, str] | None) -> StoreView:
        fields = dict(changes)
        slot = "url" in fields or keys is not None  # the address or the keys: no test may be running on the old ones
        if slot:
            self._claim(store_id)
        try:
            return self._update(store_id, fields, keys)
        finally:
            if slot:
                self._release(store_id)

    def _update(self, store_id: int, changes: dict[str, Any], keys: tuple[str, str] | None) -> StoreView:
        with closing(self._open()) as connection:
            connection.execute("BEGIN IMMEDIATE")
            saved_old: tuple[str | None, str | None] | None = None
            try:
                row = get_store(connection, store_id)
                if row is None:
                    raise StoreError(404, "not_found")
                if changes.get("url") == row.url:
                    del changes["url"]  # no change: the last test still stands
                moved = "url" in changes and _authority(changes["url"]) != _authority(row.url)
                if moved and keys is None:
                    raise StoreError(422, "keys_required")
                update_store(connection, store_id, changes)
                if moved and keys is not None:
                    return self._move_to_new_host(connection, row, changes, keys)
                if keys is not None:
                    saved_old = self._credentials.read(store_id)
                    self._credentials.save(store_id, *keys)
                    reset_health(connection, store_id)
                connection.execute("COMMIT")
            except UrlTaken:
                _rollback(connection)
                raise StoreError(409, "store_exists") from None
            except CodeTaken:
                _rollback(connection)
                raise StoreError(409, "code_taken") from None
            except SecretStoreError:
                _rollback(connection)
                raise StoreError(503, "secrets_unavailable") from None
            except BaseException:
                _rollback(connection)
                self._restore(store_id, saved_old)
                raise
            updated = get_store(connection, store_id)
        if updated is None:  # can't happen: the row was just updated
            raise StoreError(404, "not_found")
        return self._view(updated)

    def _move_to_new_host(
        self, connection: sqlite3.Connection, old: StoreRow, changes: Mapping[str, Any], keys: tuple[str, str]
    ) -> StoreView:
        """A new host: the old keys are deleted **before** the new address is committed, and the new keys are written
        after it, so no crash leaves keys on a host they weren't given for; every crash point ends with no keys. If
        writing the new keys fails, the old address (and what else was edited) is put back and the old keys are put
        back best-effort. The caller holds the transaction with the edit already in it."""
        try:
            old_pair = self._credentials.read(old.id)
            self._credentials.delete(old.id)
        except SecretStoreError:
            _rollback(connection)
            raise StoreError(503, "secrets_unavailable") from None
        try:
            connection.execute("COMMIT")
        except BaseException:
            _rollback(connection)
            self._credentials.put_back(old.id, *old_pair)  # the old address stays, so the old keys go back with it
            raise
        try:
            self._credentials.save(old.id, *keys)
        except SecretStoreError:
            if self._undo_edit(connection, old, changes):
                self._credentials.put_back(old.id, *old_pair)  # the old address is back, so the old keys may go too
            # else: the new address stays and so does "no keys": the old keys must never sit under it
            raise StoreError(503, "secrets_unavailable") from None
        reset_health(connection, old.id)
        updated = get_store(connection, old.id)
        if updated is None:  # can't happen: the row was just updated
            raise StoreError(404, "not_found")
        return self._view(updated)

    def _undo_edit(self, connection: sqlite3.Connection, old: StoreRow, changes: Mapping[str, Any]) -> bool:
        """Put the columns an edit changed back to what they were (the health stays `unknown`). False when that
        failed: the caller must then leave the store without keys."""
        before = {column: getattr(old, column) for column in changes}
        try:
            return update_store(connection, old.id, before)
        except (UrlTaken, CodeTaken, sqlite3.Error) as error:
            _log.warning("A store's earlier address couldn't be put back (%s)", type(error).__name__)
            return False

    def set_keys(self, store_id: int, consumer_key: str, consumer_secret: str) -> None:
        self._claim(store_id)
        try:
            self._set_keys(store_id, consumer_key, consumer_secret)
        finally:
            self._release(store_id)

    def _set_keys(self, store_id: int, consumer_key: str, consumer_secret: str) -> None:
        with closing(self._open()) as connection:
            connection.execute("BEGIN IMMEDIATE")
            saved_old: tuple[str | None, str | None] | None = None
            try:
                if get_store(connection, store_id) is None:
                    raise StoreError(404, "not_found")
                saved_old = self._credentials.read(store_id)
                self._credentials.save(store_id, consumer_key, consumer_secret)
                reset_health(connection, store_id)
                connection.execute("COMMIT")
            except SecretStoreError:
                _rollback(connection)
                raise StoreError(503, "secrets_unavailable") from None
            except BaseException:
                _rollback(connection)
                self._restore(store_id, saved_old)
                raise

    def delete(self, store_id: int) -> None:
        self._claim(store_id)
        try:
            with closing(self._open()) as connection:
                row = get_store(connection, store_id)
                if row is None:
                    raise StoreError(404, "not_found")
                try:
                    self._credentials.delete(store_id)  # first: if this fails nothing has changed
                except SecretStoreError:
                    raise StoreError(503, "secrets_unavailable") from None
                soft_delete(connection, store_id, to_iso(self._now()))
        finally:
            self._release(store_id)
        _log.info("Store %s was removed", row.code)

    def _restore(self, store_id: int, old: tuple[str | None, str | None] | None) -> None:
        """After a failure that came after the keys were written: put the earlier pair back."""
        if old is not None:
            self._credentials.put_back(store_id, *old)

    # ---- the read test ---------------------------------------------------------------------------------------------

    def test(self, store_id: int) -> ReadReport:
        """Test connection. The busy slot is taken before anything is read, so an edit can't slip in between reading
        the address and the keys and sending them. The test runs on a worker thread and this waits at most the test's
        60 seconds (plus a short grace): httpx's timeouts are per socket operation, so a slow host could otherwise
        hold the request far longer. On overrun the client is closed and the answer is `timeout`; the slot stays taken
        until the worker really ends, so a second test or an edit can't overlap it."""
        self._claim(store_id)
        handed_over = False
        completed = False
        overrun = {"yes": False}
        finished = threading.Event()
        try:
            with closing(self._open()) as connection:
                row = get_store(connection, store_id)
            if row is None:
                raise StoreError(404, "not_found")
            pair = self._credentials.pair(store_id)
            if pair is None:
                raise StoreError(409, "keys_missing")
            client = WooClient(
                row.url,
                pair.consumer_key,
                pair.consumer_secret,
                transport=self._transport,
                monotonic=self._monotonic,
            )
            result: dict[str, Any] = {}

            def work() -> None:
                try:
                    result["outcome"] = run_read_test(
                        client,
                        row.spacing_ms,
                        row.code,
                        sleep=self._sleep,
                        monotonic=self._monotonic,
                        total_seconds=self._limit_seconds,
                    )
                except BaseException as error:  # handed to the request below, never lost in the thread
                    result["error"] = error
                finally:
                    _close_quietly(client)
                    with self._busy_lock:
                        finished.set()
                        if overrun["yes"]:  # the request gave up waiting: only now is the store free
                            self._busy.discard(store_id)

            threading.Thread(target=work, name=f"store-test-{store_id}", daemon=True).start()
            handed_over = True
            completed = finished.wait(self._limit_seconds + self._grace_seconds)
            if completed:
                if "error" in result:
                    raise result["error"]
                outcome: ReadOutcome = result["outcome"]
            else:
                _close_quietly(client)  # best effort: it may free a worker stuck in a socket call
                outcome = ReadOutcome("timeout")
                _log.warning("Store %s read test ran out of time", row.code)
            tested_at = to_iso(self._now())
            with closing(self._open()) as connection:
                save_test_result(
                    connection,
                    store_id,
                    row.url,
                    SavedTest(
                        outcome.health,
                        outcome.reason,
                        outcome.http_status,
                        outcome.latency_ms,
                        outcome.wc_version,
                        outcome.wp_version,
                        outcome.downloadable_count,
                        tested_at,
                    ),
                )
            return ReadReport(outcome, tested_at)
        finally:
            if not handed_over or completed:
                self._release(store_id)  # after the result is saved
            else:  # no answer in time: the worker lets go when it ends (or has, in the meantime)
                with self._busy_lock:
                    if finished.is_set():
                        self._busy.discard(store_id)
                    else:
                        overrun["yes"] = True


def _close_quietly(client: WooClient) -> None:
    try:
        client.close()
    except Exception as error:  # a close that fails changes nothing for the caller
        _log.debug("A store client didn't close cleanly (%s)", type(error).__name__)


def _rollback(connection: sqlite3.Connection) -> None:
    if connection.in_transaction:
        connection.execute("ROLLBACK")


def build_store_service(paths: DataPaths, secrets: SecretStore) -> StoreService:
    """The service the running app uses: the data folder's database and Credential Manager."""
    return StoreService(open_connection=lambda: connect(paths.database), secrets=secrets)


__all__ = [
    "ReadReport",
    "StoreError",
    "StoreService",
    "StoreView",
    "build_store_service",
    "normalize_url",
]

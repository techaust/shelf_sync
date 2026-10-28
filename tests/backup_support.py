"""Helpers for the backup export and import tests (M2.4): two installs on real SQLite files with one secret store each
(the install token in the same store as every other secret, as in the running app), and a way to write any payload into
a file."""

import json
import sqlite3
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient

from shelfsync.api.app import create_app
from shelfsync.api.backup import ExportService
from shelfsync.api.storage import StorageService
from shelfsync.db.connection import connect
from shelfsync.db.migrate import migrate
from shelfsync.db.settings import set_setting
from shelfsync.secure.backup_crypto import canonical, dumps, seal
from shelfsync.secure.token import InstallToken
from shelfsync.store_service import StoreService
from tests.storage_support import GOOD_SETTINGS, RO_ID, RO_SECRET, RW_ID, RW_SECRET
from tests.store_support import KEY, KEY_2, SECRET, SECRET_2, FailingSecretStore, new_store_body
from tests.support import WRITE_HEADERS, FakeClock, Harness

PASSPHRASE = "correct horse battery staple"
GITHUB_TOKEN = "github_pat_" + "11AAAAAAA0aBcDeFgHiJkL_mNoPqRsTuVwXyZ0123456789abcdef"
EXPORT = "/api/backup/export"
IMPORT = "/api/backup/import"
NOW = datetime(2026, 10, 28, 10, 0, 0, tzinfo=UTC)
FAST_N = 2**10  # the scrypt cost the tests use (the module's own constant, lowered by `fast_kdf`)


@dataclass
class Install:
    """One ShelfSync install: its database file, its secret store and an app over both."""

    harness: Harness
    client: TestClient
    secrets: FailingSecretStore
    stores: StoreService
    storage: StorageService
    exports: ExportService
    open_db: Callable[[], sqlite3.Connection]
    path: Path


def make_install(
    tmp_path: Path,
    name: str = "install",
    *,
    secrets: FailingSecretStore | None = None,
    now: Callable[[], datetime] = lambda: NOW,
) -> Install:
    path = tmp_path / f"{name}.db"
    first = connect(path)
    migrate(first)
    first.close()
    secret_store = secrets if secrets is not None else FailingSecretStore()

    def opener() -> sqlite3.Connection:
        return connect(path)

    open_connection = opener
    stores = StoreService(open_connection=open_connection, secrets=secret_store)
    storage = StorageService(open_connection, secret_store)
    exports = ExportService(open_connection, secret_store, storage.lock, now=now)
    clock = FakeClock()
    app = create_app(
        47615, InstallToken(secret_store), clock, ui_dir=None, stores=stores, storage=storage, exports=exports
    )
    harness = Harness(app=app, store=secret_store, clock=clock)
    return Install(harness, harness.signed_in_client(), secret_store, stores, storage, exports, open_connection, path)


def populate(install: Install) -> None:
    """Two stores (one paused), storage settings, both S3 pairs, a GitHub token and three plain settings."""
    client = install.client
    first = client.post("/api/stores", headers=WRITE_HEADERS, json=new_store_body())
    assert first.status_code == 201, first.text
    second = client.post(
        "/api/stores",
        headers=WRITE_HEADERS,
        json=new_store_body(
            name="Store B",
            url="https://store-b.example/shop",
            code="SB",
            shape="square",
            color="teal",
            spacing_ms=400,
            main_button="Get it",
            consumer_key=KEY_2,
            consumer_secret=SECRET_2,
        ),
    )
    assert second.status_code == 201, second.text
    assert (
        client.patch(f"/api/stores/{second.json()['id']}", headers=WRITE_HEADERS, json={"state": "paused"}).status_code
        == 200
    )
    assert client.put("/api/settings/storage", headers=WRITE_HEADERS, json=GOOD_SETTINGS).status_code == 200
    assert (
        client.put(
            "/api/secrets/s3-rw", headers=WRITE_HEADERS, json={"access_key_id": RW_ID, "secret_access_key": RW_SECRET}
        ).status_code
        == 204
    )
    assert (
        client.put(
            "/api/secrets/s3-ro", headers=WRITE_HEADERS, json={"access_key_id": RO_ID, "secret_access_key": RO_SECRET}
        ).status_code
        == 204
    )
    install.secrets.set("github-token", GITHUB_TOKEN)
    connection = install.open_db()
    try:
        set_setting(connection, "theme", "dark")
        set_setting(connection, "log_retention_days", 45)
        set_setting(connection, "db_backups_kept", 12)
    finally:
        connection.close()


def entries(install: Install) -> dict[str, str]:
    """Every entry in the install's secret store (the in-memory fake keeps them in `_values`)."""
    return dict(install.secrets._values)


def rows(install: Install, table: str) -> list[tuple[Any, ...]]:
    connection = install.open_db()
    try:
        return connection.execute(f"SELECT * FROM {table} ORDER BY 1").fetchall()  # nosec B608  # test names only
    finally:
        connection.close()


def export_text(install: Install, passphrase: str | None = None) -> str:
    response = install.client.post(EXPORT, headers=WRITE_HEADERS, json={"passphrase": passphrase})
    assert response.status_code == 200, response.text
    return response.text


def import_response(install: Install, text: str, passphrase: str | None = None) -> Any:
    return install.client.post(IMPORT, headers=WRITE_HEADERS, json={"file": text, "passphrase": passphrase})


def file_for(payload: dict[str, Any], passphrase: str | None = None, *, schema: int = 2) -> str:
    """A `.ssbak` text holding exactly this payload (valid or not)."""
    envelope = seal(
        canonical(payload), passphrase, created_at="2026-10-28T10:00:00Z", app_version="0.1.0", schema=schema
    )
    return dumps(envelope)


def good_payload(**changes: Any) -> dict[str, Any]:
    """A valid payload without secrets, with two stores, for building a refused variant with `changes`."""
    payload: dict[str, Any] = {
        "settings": {
            "port": 47615,
            "theme": "dark",
            "start_with_windows": True,
            "notifications": True,
            "log_retention_days": 30,
            "db_backups_kept": 7,
            "snapshot_retention_days": 30,
        },
        "stores": [
            {
                "code": "SA",
                "name": "Store A",
                "url": "https://store-a.example",
                "shape": "circle",
                "color": "indigo",
                "spacing_ms": 150,
                "main_button": "Download",
                "state": "active",
            },
            {
                "code": "SB",
                "name": "Store B",
                "url": "https://store-b.example",
                "shape": "square",
                "color": "teal",
                "spacing_ms": 200,
                "main_button": "Get",
                "state": "paused",
            },
        ],
        "storage": dict(GOOD_SETTINGS),
        "catalog": None,
    }
    payload.update(changes)
    return payload


def good_secrets(**changes: Any) -> dict[str, Any]:
    secrets: dict[str, Any] = {
        "stores": {
            "SA": {"consumer_key": KEY, "consumer_secret": SECRET},
            "SB": {"consumer_key": KEY_2, "consumer_secret": SECRET_2},
        },
        "s3": {
            "rw": {"access_key_id": RW_ID, "secret_access_key": RW_SECRET},
            "ro": {"access_key_id": RO_ID, "secret_access_key": RO_SECRET},
        },
        "github_token": GITHUB_TOKEN,
    }
    secrets.update(changes)
    return secrets


def tampered(text: str, change: Callable[[dict[str, Any]], object]) -> str:
    envelope = json.loads(text)
    change(envelope)
    return json.dumps(envelope)


class CommitFails:
    """A connection that behaves like the real one but fails when asked to COMMIT (after the Credential Manager writes
    that come before it)."""

    def __init__(self, real: sqlite3.Connection) -> None:
        self._real = real

    def execute(self, sql: str, *args: Any) -> sqlite3.Cursor:
        if sql.strip().upper() == "COMMIT":
            raise sqlite3.OperationalError("disk I/O error")
        return self._real.execute(sql, *args)

    @property
    def in_transaction(self) -> bool:
        return self._real.in_transaction

    def close(self) -> None:
        self._real.close()

"""SET-01, SYS-07: migration 0002 (the `store` table) and the repository in db/stores.py."""

import shutil
import sqlite3
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path

import pytest

from shelfsync.db.backup import migrate_with_backup
from shelfsync.db.connection import connect
from shelfsync.db.migrate import DEFAULT_MIGRATIONS_DIR, applied_versions, migrate
from shelfsync.db.stores import (
    CodeTaken,
    SavedTest,
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
from tests.update_support import data_paths

NOW = "2026-10-28T09:00:00.000000Z"
URL = "https://store-a.example"


@pytest.fixture
def connection(tmp_path: Path) -> Iterator[sqlite3.Connection]:
    conn = connect(tmp_path / "test.db")
    migrate(conn)
    yield conn
    conn.close()


def add(conn: sqlite3.Connection, code: str = "SA", url: str = "https://store-a.example") -> int:
    return insert_store(
        conn, name="Store", url=url, code=code, shape="circle", color="indigo", spacing_ms=150,
        main_button="Download", created_at=NOW,
    )  # fmt: skip


# ---- the migration --------------------------------------------------------------------------------------------------


def test_0002_applies_to_a_0001_database_and_keeps_the_settings(tmp_path: Path) -> None:
    folder = tmp_path / "m"
    folder.mkdir()
    shutil.copy(DEFAULT_MIGRATIONS_DIR / "0001_base.sql", folder / "0001_base.sql")
    paths = data_paths(tmp_path)
    old = connect(paths.database)
    migrate(old, folder)
    old.execute("INSERT INTO setting (key, value_json) VALUES ('theme', '\"dark\"')")
    old.execute("INSERT INTO setting (key, value_json) VALUES ('port', '47616')")
    old.close()

    conn = connect(paths.database)
    assert migrate_with_backup(conn, paths, now=lambda: datetime(2026, 10, 28, 9, 0, tzinfo=UTC)) == [2]
    assert applied_versions(conn) == {1, 2}
    assert conn.execute("SELECT key, value_json FROM setting ORDER BY key").fetchall() == [
        ("port", "47616"),
        ("theme", '"dark"'),
    ]
    assert conn.execute("SELECT COUNT(*) FROM store").fetchone() == (0,)
    conn.close()

    [saved] = list(paths.backups.iterdir())  # the pre-migration backup
    assert saved.name == "pre-migration-0001-to-0002-20261028T090000Z.db"
    check = sqlite3.connect(saved)
    assert applied_versions(check) == {1}
    assert check.execute("SELECT value_json FROM setting WHERE key = 'theme'").fetchone() == ('"dark"',)
    assert check.execute("SELECT name FROM sqlite_master WHERE name = 'store'").fetchone() is None  # as it was
    check.close()


def test_the_migration_is_in_the_folder_in_order() -> None:
    names = [path.name for path in sorted(DEFAULT_MIGRATIONS_DIR.glob("*.sql"))]
    assert names[:2] == ["0001_base.sql", "0002_store.sql"]


@pytest.mark.parametrize(
    "changes",
    [
        {"name": ""}, {"name": "x" * 61}, {"code": "sa"}, {"code": "S"}, {"code": "SAA"}, {"code": "S1"},
        {"shape": "hexagon"},
        {"color": "violet"}, {"color": "#4d4d99"}, {"color": ""},
{"spacing_ms": 49}, {"spacing_ms": 5001}, {"main_button": ""},
        {"main_button": "x" * 41}, {"state": "gone"}, {"health": "fine"},
    ],
)  # fmt: skip
def test_the_tables_own_checks_refuse_a_bad_row(connection: sqlite3.Connection, changes: dict[str, object]) -> None:
    row: dict[str, object] = {
        "name": "Store", "url": "https://a.example", "code": "SA", "shape": "circle", "color": "indigo",
        "spacing_ms": 150, "main_button": "Download", "state": "active", "health": "unknown", "created_at": NOW,
    }  # fmt: skip
    row.update(changes)
    columns = ", ".join(row)
    marks = ", ".join("?" for _ in row)
    with pytest.raises(sqlite3.IntegrityError):
        connection.execute(f"INSERT INTO store ({columns}) VALUES ({marks})", list(row.values()))


def test_defaults_fill_in(connection: sqlite3.Connection) -> None:
    store = get_store(connection, add(connection))
    assert store is not None
    assert (store.spacing_ms, store.main_button, store.state, store.health) == (150, "Download", "active", "unknown")
    assert store.tested_at is None and store.created_at == NOW


# ---- the repository -------------------------------------------------------------------------------------------------


def test_url_and_code_are_unique_among_live_stores_only(connection: sqlite3.Connection) -> None:
    first = add(connection)
    with pytest.raises(UrlTaken):
        add(connection, code="SB")
    with pytest.raises(CodeTaken):
        add(connection, url="https://store-b.example")
    assert soft_delete(connection, first, NOW) is True
    second = add(connection)  # the removed store's address and code are free again
    assert second > first  # and ids are never reused
    assert [s.id for s in list_live(connection)] == [second]
    assert all_ids(connection) == [first, second]  # removed rows still count (their secrets are swept too)


def test_ids_are_not_reused_even_after_the_newest_row_is_removed(connection: sqlite3.Connection) -> None:
    first = add(connection)
    soft_delete(connection, first, NOW)
    assert add(connection) == first + 1


def test_a_removed_store_is_not_found_and_cannot_be_changed(connection: sqlite3.Connection) -> None:
    store_id = add(connection)
    soft_delete(connection, store_id, NOW)
    assert get_store(connection, store_id) is None
    assert update_store(connection, store_id, {"name": "x"}) is False
    assert soft_delete(connection, store_id, NOW) is False


def test_update_changes_only_the_named_columns_and_refuses_others(connection: sqlite3.Connection) -> None:
    store_id = add(connection)
    assert update_store(connection, store_id, {"name": "New", "state": "paused"}) is True
    store = get_store(connection, store_id)
    assert store is not None and (store.name, store.state, store.code) == ("New", "paused", "SA")
    with pytest.raises(KeyError):
        update_store(connection, store_id, {"health": "connected"})
    with pytest.raises(KeyError):
        update_store(connection, store_id, {"id; DROP TABLE store; --": 1})
    assert update_store(connection, store_id, {}) is True
    assert update_store(connection, 999, {}) is False
    assert update_store(connection, 999, {"name": "x"}) is False


def test_update_reports_a_clash_and_changing_the_url_resets_the_health(connection: sqlite3.Connection) -> None:
    one = add(connection)
    two = add(connection, "SB", "https://store-b.example")
    save_test_result(
        connection, two, "https://store-b.example", SavedTest("connected", None, 200, 180, "9.4.1", "6.7", 12, NOW)
    )
    with pytest.raises(UrlTaken):
        update_store(connection, two, {"url": "https://store-a.example"})
    with pytest.raises(CodeTaken):
        update_store(connection, two, {"code": "SA"})
    assert update_store(connection, two, {"name": "Renamed"}) is True
    kept = get_store(connection, two)
    assert kept is not None and kept.health == "connected"  # a rename keeps the last test
    assert update_store(connection, two, {"url": "https://store-c.example"}) is True
    reset = get_store(connection, two)
    assert reset is not None and reset.health == "unknown" and reset.tested_at is None and reset.wc_version is None
    assert get_store(connection, one) is not None


def test_a_test_result_is_saved_on_the_row_and_reset_clears_it(connection: sqlite3.Connection) -> None:
    store_id = add(connection)
    save_test_result(connection, store_id, URL, SavedTest("refused", "keys_refused", 401, None, None, None, None, NOW))
    row = get_store(connection, store_id)
    assert row is not None
    assert (row.health, row.health_reason, row.http_status, row.latency_ms, row.tested_at) == (
        "refused", "keys_refused", 401, None, NOW,
    )  # fmt: skip
    reset_health(connection, store_id)
    again = get_store(connection, store_id)
    assert again is not None and (again.health, again.health_reason, again.http_status) == ("unknown", None, None)


def test_nothing_in_the_repository_commits(connection: sqlite3.Connection) -> None:
    """The caller owns the transaction, so a save that also writes Credential Manager can roll the row back."""
    connection.execute("BEGIN IMMEDIATE")
    add(connection)
    connection.execute("ROLLBACK")
    assert list_live(connection) == []


def test_a_result_is_saved_only_while_the_row_still_has_the_address_that_was_tested(
    connection: sqlite3.Connection,
) -> None:
    store_id = add(connection)
    result = SavedTest("connected", None, 200, 180, "9.4.1", "6.7", 12, NOW)
    update_store(connection, store_id, {"url": "https://store-moved.example"})  # changed under a running test
    assert save_test_result(connection, store_id, URL, result) is False
    row = get_store(connection, store_id)
    assert row is not None and (row.health, row.tested_at) == ("unknown", None)
    assert save_test_result(connection, store_id, "https://store-moved.example", result) is True
    soft_delete(connection, store_id, NOW)
    assert save_test_result(connection, store_id, "https://store-moved.example", result) is False

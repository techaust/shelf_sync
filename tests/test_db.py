"""SYS-07 migrations, SET settings storage, connection pragmas."""

import sqlite3
from collections.abc import Iterator
from pathlib import Path

import pytest

from shelfsync.db.connection import BUSY_TIMEOUT_MS, connect
from shelfsync.db.migrate import MigrationError, applied_versions, discover, migrate
from shelfsync.db.settings import DEFAULTS, get_all_settings, get_setting, set_setting


@pytest.fixture
def connection(tmp_path: Path) -> Iterator[sqlite3.Connection]:
    conn = connect(tmp_path / "test.db")
    yield conn
    conn.close()


def tables(conn: sqlite3.Connection) -> set[str]:
    rows = conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")
    return {row[0] for row in rows}


def test_connection_pragmas(connection: sqlite3.Connection) -> None:
    assert connection.execute("PRAGMA journal_mode").fetchone()[0] == "wal"
    assert connection.execute("PRAGMA foreign_keys").fetchone()[0] == 1
    assert connection.execute("PRAGMA busy_timeout").fetchone()[0] == BUSY_TIMEOUT_MS


def test_fresh_database_gets_0001_only(connection: sqlite3.Connection) -> None:
    assert migrate(connection) == [1]
    assert applied_versions(connection) == {1}
    assert tables(connection) == {"schema_migration", "setting"}
    applied_at = connection.execute("SELECT applied_at FROM schema_migration").fetchone()[0]
    assert applied_at.endswith("Z")


def test_second_run_applies_nothing(connection: sqlite3.Connection) -> None:
    migrate(connection)
    assert migrate(connection) == []
    assert connection.execute("SELECT COUNT(*) FROM schema_migration").fetchone()[0] == 1


def test_broken_migration_rolls_back_and_leaves_versions_unchanged(
    connection: sqlite3.Connection, tmp_path: Path
) -> None:
    folder = tmp_path / "migrations"
    folder.mkdir()
    (folder / "0001_base.sql").write_text(
        "CREATE TABLE schema_migration (version INTEGER PRIMARY KEY, applied_at TEXT NOT NULL);\n"
    )
    (folder / "0002_broken.sql").write_text(
        "CREATE TABLE half_done (id INTEGER);\nINSERT INTO no_such_table VALUES (1);\n"
    )
    with pytest.raises(MigrationError, match=r"0002_broken.sql"):
        migrate(connection, folder)
    assert applied_versions(connection) == {1}
    assert "half_done" not in tables(connection)
    assert not connection.in_transaction


def test_triggers_survive_statement_splitting(connection: sqlite3.Connection, tmp_path: Path) -> None:
    folder = tmp_path / "migrations"
    folder.mkdir()
    (folder / "0001_base.sql").write_text(
        "CREATE TABLE schema_migration (version INTEGER PRIMARY KEY, applied_at TEXT NOT NULL);\n"
        "CREATE TABLE a (x INTEGER);\nCREATE TABLE log (x INTEGER);\n"
        "-- a trigger has semicolons inside\n"
        "CREATE TRIGGER t AFTER INSERT ON a BEGIN INSERT INTO log VALUES (new.x); END;\n"
    )
    migrate(connection, folder)
    connection.execute("INSERT INTO a VALUES (7)")
    assert connection.execute("SELECT x FROM log").fetchone()[0] == 7


def test_unfinished_statement_is_an_error(connection: sqlite3.Connection, tmp_path: Path) -> None:
    folder = tmp_path / "migrations"
    folder.mkdir()
    (folder / "0001_base.sql").write_text("CREATE TABLE schema_migration (version INTEGER")
    with pytest.raises(MigrationError):
        migrate(connection, folder)
    assert tables(connection) == set()


def test_bad_file_names_and_repeated_numbers_are_errors(tmp_path: Path) -> None:
    (tmp_path / "base.sql").write_text("SELECT 1;")
    with pytest.raises(MigrationError, match=r"NNNN_name.sql"):
        discover(tmp_path)
    (tmp_path / "base.sql").unlink()
    (tmp_path / "0001_a.sql").write_text("SELECT 1;")
    (tmp_path / "0001_b.sql").write_text("SELECT 1;")
    with pytest.raises(MigrationError, match="share the number"):
        discover(tmp_path)


def test_database_from_a_newer_version_is_refused(connection: sqlite3.Connection) -> None:
    migrate(connection)
    connection.execute("INSERT INTO schema_migration VALUES (99, '2026-01-01T00:00:00.000000Z')")
    with pytest.raises(MigrationError, match="newer version"):
        migrate(connection)


def test_settings_default_in_code_and_store_json(connection: sqlite3.Connection) -> None:
    migrate(connection)
    assert get_all_settings(connection) == {
        "port": 47615,
        "theme": "system",
        "start_with_windows": True,
        "notifications": True,
        "log_retention_days": 30,
    }
    assert connection.execute("SELECT COUNT(*) FROM setting").fetchone()[0] == 0  # defaults are not rows
    set_setting(connection, "theme", "dark")
    set_setting(connection, "theme", "light")  # overwrite
    set_setting(connection, "notifications", False)
    assert get_setting(connection, "theme") == "light"
    assert get_setting(connection, "notifications") is False
    assert connection.execute("SELECT value_json FROM setting WHERE key = 'theme'").fetchone()[0] == '"light"'


def test_settings_refuse_unknown_keys_and_wrong_types(connection: sqlite3.Connection) -> None:
    migrate(connection)
    with pytest.raises(KeyError):
        get_setting(connection, "nope")
    with pytest.raises(KeyError):
        set_setting(connection, "nope", 1)
    with pytest.raises(TypeError):
        set_setting(connection, "port", "47615")
    with pytest.raises(TypeError):
        set_setting(connection, "port", True)  # a bool is not a port
    assert set(DEFAULTS) == {"port", "theme", "start_with_windows", "notifications", "log_retention_days"}

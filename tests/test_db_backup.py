"""SYS-07: the backup before a migration, and its restore."""

import shutil
import sqlite3
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path

import pytest

from shelfsync.db import backup as backup_module
from shelfsync.db.backup import (
    BACKUP_PREFIX,
    BackupError,
    backup_name,
    check_backup,
    migrate_with_backup,
    restore_backup,
    take_backup,
)
from shelfsync.db.connection import connect
from shelfsync.db.migrate import DEFAULT_MIGRATIONS_DIR, MigrationError, applied_versions
from shelfsync.paths import DataPaths
from shelfsync.update.layout import UpdatePaths
from shelfsync.update.state import StateStore
from tests.update_support import data_paths

NOW = datetime(2026, 10, 27, 10, 15, 30, tzinfo=UTC)


def migrations(tmp_path: Path, *extra: tuple[str, str]) -> Path:
    """The previous release's real schema (0001), plus the given later migrations."""
    folder = tmp_path / "migrations"
    folder.mkdir(parents=True, exist_ok=True)
    shutil.copy(DEFAULT_MIGRATIONS_DIR / "0001_base.sql", folder / "0001_base.sql")
    for name, sql in extra:
        (folder / name).write_text(sql, encoding="utf-8")
    return folder


TWO = ("0002_notes.sql", "CREATE TABLE note (id INTEGER PRIMARY KEY, body TEXT NOT NULL);\n")
BAD = ("0003_bad.sql", "CREATE TABLE ok_before (id INTEGER);\nINSERT INTO does_not_exist VALUES (1);\n")


def database_at_release_one(paths: DataPaths, folder: Path) -> None:
    """A database as the previous release left it: schema 1, with a setting in it."""
    connection = connect(paths.database)
    from shelfsync.db.migrate import migrate

    migrate(connection, folder)
    connection.execute("INSERT INTO setting (key, value_json) VALUES ('theme', '\"dark\"')")
    connection.close()


def versions_of(path: Path) -> set[int]:
    connection = sqlite3.connect(path)
    try:
        return applied_versions(connection)
    finally:
        connection.close()


def test_a_new_database_is_migrated_with_no_backup(tmp_path: Path) -> None:
    paths = data_paths(tmp_path)
    connection = connect(paths.database)
    assert migrate_with_backup(connection, paths, migrations(tmp_path, TWO)) == [1, 2]
    connection.close()
    assert list(paths.backups.iterdir()) == []
    assert StateStore(UpdatePaths(paths)).load().backup is None


def test_nothing_pending_means_no_backup(tmp_path: Path) -> None:
    paths = data_paths(tmp_path)
    folder = migrations(tmp_path)
    database_at_release_one(paths, folder)
    connection = connect(paths.database)
    assert migrate_with_backup(connection, paths, folder) == []
    connection.close()
    assert list(paths.backups.iterdir()) == []


def test_a_pending_migration_on_an_existing_database_is_backed_up_first(tmp_path: Path) -> None:
    paths = data_paths(tmp_path)
    database_at_release_one(paths, migrations(tmp_path))  # only 0001 yet
    folder = migrations(tmp_path, TWO)  # the new release brings 0002
    connection = connect(paths.database)
    assert migrate_with_backup(connection, paths, folder, now=lambda: NOW) == [2]
    connection.close()
    [saved] = list(paths.backups.iterdir())
    assert saved.name == "pre-migration-0001-to-0002-20261027T101530Z.db"
    assert versions_of(saved) == {1}  # the copy is the database as it was
    assert not any(p.name.endswith(("-wal", "-shm")) for p in paths.backups.iterdir())  # one standalone file
    record = StateStore(UpdatePaths(paths)).load().backup
    assert record is not None
    assert (Path(record.path), record.from_schema, record.to_schema) == (saved, 1, 2)
    assert record.at.startswith("2026-10-27T10:15:30")
    check = sqlite3.connect(saved)
    assert check.execute("PRAGMA integrity_check").fetchall() == [("ok",)]
    assert check.execute("SELECT value_json FROM setting WHERE key = 'theme'").fetchone() == ('"dark"',)
    check.close()


def test_the_record_is_written_before_the_migration_runs(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    paths = data_paths(tmp_path)
    database_at_release_one(paths, migrations(tmp_path))
    seen: list[object] = []
    real = backup_module.migrate

    def spy(connection: sqlite3.Connection, folder: Path) -> list[int]:
        seen.append(StateStore(UpdatePaths(paths)).load().backup)
        return real(connection, folder)

    monkeypatch.setattr(backup_module, "migrate", spy)
    connection = connect(paths.database)
    migrate_with_backup(connection, paths, migrations(tmp_path, TWO))
    connection.close()
    assert seen and seen[0] is not None


def test_a_failed_second_migration_restores_the_database_and_still_fails(tmp_path: Path) -> None:
    paths = data_paths(tmp_path)
    database_at_release_one(paths, migrations(tmp_path))
    connection = connect(paths.database)
    with pytest.raises(MigrationError):
        migrate_with_backup(connection, paths, migrations(tmp_path, TWO, BAD), now=lambda: NOW)
    # 0002 had been applied before 0003 failed: the restore undoes it, so the database is exactly release 1's again
    assert versions_of(paths.database) == {1}
    check = sqlite3.connect(paths.database)
    assert check.execute("SELECT name FROM sqlite_master WHERE name IN ('note', 'ok_before')").fetchall() == []
    assert check.execute("SELECT value_json FROM setting WHERE key = 'theme'").fetchone() == ('"dark"',)
    check.close()


def test_a_restore_leaves_no_stale_wal_or_shm(tmp_path: Path) -> None:
    paths = data_paths(tmp_path)
    database_at_release_one(paths, migrations(tmp_path))
    connection = connect(paths.database)
    record = take_backup(connection, paths, 1, 2, lambda: NOW)
    connection.close()
    wal = paths.database.with_name(paths.database.name + "-wal")
    shm = paths.database.with_name(paths.database.name + "-shm")
    wal.write_bytes(b"stale frames from a database that is gone")
    shm.write_bytes(b"stale index")
    restore_backup(record, paths)
    assert not wal.exists() and not shm.exists()
    reopened = connect(paths.database)
    assert applied_versions(reopened) == {1}
    reopened.close()


def test_a_backup_that_fails_its_check_stops_the_migration_before_anything_changes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    paths = data_paths(tmp_path)
    database_at_release_one(paths, migrations(tmp_path))
    monkeypatch.setattr(backup_module, "check_backup", lambda path, schema=None: False)
    connection = connect(paths.database)
    with pytest.raises(MigrationError):
        migrate_with_backup(connection, paths, migrations(tmp_path, TWO))
    connection.close()
    assert versions_of(paths.database) == {1}
    assert list(paths.backups.iterdir()) == []  # the bad copy was removed
    assert StateStore(UpdatePaths(paths)).load().backup is None


def test_a_database_from_a_newer_version_is_refused_without_a_backup(tmp_path: Path) -> None:
    paths = data_paths(tmp_path)
    folder = migrations(tmp_path, TWO)
    connection = connect(paths.database)
    migrate_with_backup(connection, paths, folder)
    with pytest.raises(MigrationError, match="newer version"):
        migrate_with_backup(connection, paths, migrations(tmp_path / "old"))
    connection.close()
    assert list(paths.backups.iterdir()) == []


def test_a_restore_that_cannot_be_done_says_so(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    paths = data_paths(tmp_path)
    database_at_release_one(paths, migrations(tmp_path))

    def refuse(record: object, where: object) -> None:
        raise BackupError("restore_failed")

    monkeypatch.setattr(backup_module, "restore_backup", refuse)
    connection = connect(paths.database)
    with pytest.raises(MigrationError, match="could not be restored"):
        migrate_with_backup(connection, paths, migrations(tmp_path, TWO, BAD))


# ---- take, check and restore ----------------------------------------------------------------------------------------


def test_the_backup_name_holds_both_schema_numbers_and_the_utc_time() -> None:
    assert backup_name(1, 12, NOW) == f"{BACKUP_PREFIX}0001-to-0012-20261027T101530Z.db"


def test_check_backup_wants_a_plain_database_with_the_expected_schema(tmp_path: Path) -> None:
    paths = data_paths(tmp_path)
    database_at_release_one(paths, migrations(tmp_path))
    connection = connect(paths.database)
    record = take_backup(connection, paths, 1, 2, lambda: NOW)
    connection.close()
    saved = Path(record.path)
    assert check_backup(saved) and check_backup(saved, 1)
    assert not check_backup(saved, 2)
    assert not check_backup(tmp_path / "missing.db")
    garbage = tmp_path / "garbage.db"
    garbage.write_bytes(b"this is not a database" * 50)
    assert not check_backup(garbage)
    empty = tmp_path / "empty.db"
    sqlite3.connect(empty).close()
    assert check_backup(empty) and not check_backup(empty, 1)


def test_restore_refuses_a_backup_outside_the_backups_folder_or_with_another_name(tmp_path: Path) -> None:
    paths = data_paths(tmp_path)
    database_at_release_one(paths, migrations(tmp_path))
    connection = connect(paths.database)
    record = take_backup(connection, paths, 1, 2, lambda: NOW)
    connection.close()
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    moved = elsewhere / Path(record.path).name
    shutil.copy(record.path, moved)
    with pytest.raises(BackupError) as caught:
        restore_backup(replace(record, path=str(moved)), paths)
    assert caught.value.code == "backup_invalid"
    renamed = paths.backups / "other.db"
    shutil.copy(record.path, renamed)
    with pytest.raises(BackupError):
        restore_backup(replace(record, path=str(renamed)), paths)


def test_restore_refuses_a_missing_corrupt_or_wrong_schema_backup(tmp_path: Path) -> None:
    paths = data_paths(tmp_path)
    database_at_release_one(paths, migrations(tmp_path))
    before = paths.database.read_bytes()
    connection = connect(paths.database)
    record = take_backup(connection, paths, 1, 2, lambda: NOW)
    connection.close()
    with pytest.raises(BackupError) as wrong:
        restore_backup(replace(record, from_schema=7), paths)
    assert wrong.value.code == "backup_invalid"
    saved = Path(record.path)
    saved.write_bytes(b"corrupt" * 100)
    with pytest.raises(BackupError):
        restore_backup(record, paths)
    saved.unlink()
    with pytest.raises(BackupError) as missing:
        restore_backup(record, paths)
    assert missing.value.code == "backup_missing"
    assert paths.database.read_bytes() == before or paths.database.exists()  # the database is not replaced by junk
    assert not (paths.database.with_name(paths.database.name + ".restore")).exists()


def test_the_backup_of_a_database_that_is_in_use_is_consistent(tmp_path: Path) -> None:
    """The online backup works while another connection holds a write transaction's committed data in the WAL."""
    paths = data_paths(tmp_path)
    database_at_release_one(paths, migrations(tmp_path))
    writer = connect(paths.database)
    writer.execute("INSERT INTO setting (key, value_json) VALUES ('port', '47616')")  # sits in the WAL
    record = take_backup(writer, paths, 1, 2, lambda: NOW)
    writer.close()
    check = sqlite3.connect(record.path)
    assert check.execute("SELECT value_json FROM setting WHERE key = 'port'").fetchone() == ("47616",)
    check.close()


def test_a_backup_failure_reports_a_fixed_code(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    paths = data_paths(tmp_path)
    database_at_release_one(paths, migrations(tmp_path))
    connection = connect(paths.database)
    monkeypatch.setattr(backup_module, "check_backup", lambda path, schema=None: False)
    with pytest.raises(BackupError) as caught:
        take_backup(connection, paths, 1, 2, lambda: NOW)
    assert caught.value.code == "backup_failed"
    connection.close()

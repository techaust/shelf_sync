"""SYS-07: schema numbers, the roll-back snapshot, and the aside and put-back steps of a restore (M1b.2 review)."""

import sqlite3
from pathlib import Path

import pytest

from shelfsync.db import backup as backup_module
from shelfsync.db.backup import BackupError, database_schema, restore_backup, take_backup, take_snapshot
from shelfsync.db.connection import connect
from tests.test_db_backup import NOW, database_at_release_one, migrations
from tests.update_support import data_paths


def test_database_schema_reads_the_highest_migration_or_says_none(tmp_path: Path) -> None:
    paths = data_paths(tmp_path)
    assert database_schema(paths.database) is None  # no file
    paths.database.write_bytes(b"not a database" * 100)
    assert database_schema(paths.database) is None  # not a database
    paths.database.unlink()
    sqlite3.connect(paths.database).close()
    assert database_schema(paths.database) is None  # a database with no migrations
    paths.database.unlink()
    database_at_release_one(paths, migrations(tmp_path))
    assert database_schema(paths.database) == 1


def test_a_backup_whose_copy_fails_the_second_check_is_refused_and_nothing_is_moved(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    paths = data_paths(tmp_path)
    database_at_release_one(paths, migrations(tmp_path))
    connection = connect(paths.database)
    record = take_backup(connection, paths, 1, 2, lambda: NOW)
    connection.close()
    answers = iter([True, False])  # the original passes, the staged copy doesn't
    monkeypatch.setattr(backup_module, "check_backup", lambda path, schema=None: next(answers))
    before = paths.database.read_bytes()
    with pytest.raises(BackupError) as caught:
        restore_backup(record, paths)
    assert caught.value.code == "backup_invalid" and paths.database.read_bytes() == before
    assert not list(paths.root.glob("*.restore")) and not list(paths.root.glob("*.aside"))


def test_a_file_that_cannot_be_put_back_after_a_failed_restore_is_logged(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    paths = data_paths(tmp_path)
    database_at_release_one(paths, migrations(tmp_path))
    connection = connect(paths.database)
    record = take_backup(connection, paths, 1, 2, lambda: NOW)
    connection.close()
    real = backup_module.os.replace

    def flaky(source: object, destination: object) -> None:
        if str(source).endswith((".restore", ".aside")):
            raise OSError("nope")
        real(source, destination)  # type: ignore[arg-type]

    monkeypatch.setattr(backup_module.os, "replace", flaky)
    with pytest.raises(BackupError) as caught:
        restore_backup(record, paths)
    assert caught.value.code == "restore_failed"
    assert "could not be put back" in caplog.text


def test_a_snapshot_of_a_database_that_cannot_be_opened_or_copied_is_a_backup_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    paths = data_paths(tmp_path)
    database_at_release_one(paths, migrations(tmp_path))
    real_connect = sqlite3.connect

    def no_plain_open(target: object, *args: object, **kwargs: object) -> sqlite3.Connection:
        if not kwargs.get("uri"):
            raise sqlite3.OperationalError("unable to open database file")
        return real_connect(target, *args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(backup_module.sqlite3, "connect", no_plain_open)
    with pytest.raises(BackupError):
        take_snapshot(paths, "0.0.2")
    monkeypatch.undo()

    closed = connect(paths.database)
    closed.close()
    with pytest.raises(BackupError):
        take_backup(closed, paths, 1, 2, lambda: NOW)  # a closed connection can't be copied
    assert list(paths.backups.glob("*.db")) == []

    def fails(source: sqlite3.Connection, destination: Path, schema: int) -> None:
        raise sqlite3.OperationalError("disk I/O error")

    monkeypatch.setattr(backup_module, "_write_checked_copy", fails)
    with pytest.raises(BackupError):
        take_snapshot(paths, "0.0.2")
    assert list(paths.backups.glob("pre-rollback-*")) == []
